from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, UploadFile
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from app.api.dependencies import get_current_user
from app.api.routes import category_route, recipe_route, user_route
from app.core.config import settings
from app.core.db import get_db
from app.models import AppSetting, Base, Category, User, UserRole
from app.services import category_service, recipe_image_service


@pytest.fixture
def category_client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'categories.db'}")
    Base.metadata.create_all(engine)
    user = SimpleNamespace(id=1, role=UserRole.ADMIN)

    def test_db():
        with Session(engine) as session:
            yield session

    def test_user(db_session: Annotated[Session, Depends(get_db)]):
        return db_session.get(User, user.id) or user

    app = FastAPI()
    app.include_router(category_route.router)
    app.include_router(recipe_route.router)
    app.include_router(user_route.router)
    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_user] = test_user
    try:
        with TestClient(app) as client:
            yield client, engine, user
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("existing", "duplicate"),
    [
        ("Kuchen", "kuchen"),
        ("Kuchen", "KUCHEN"),
        ("Küche", "Kuche"),
        ("Kueche", "Kuche"),
        ("Küche", "KUECHE"),
        ("Öl", "Oel"),
        ("Äpfel", "Aepfel"),
        ("Straße", "STRASSE"),
        ("Café", "CAFE\u0301"),
    ],
)
def test_create_rejects_equivalent_category_names(category_client, existing, duplicate):
    client, _, _ = category_client
    created = client.post("/categories", json={"name": existing})
    assert created.status_code == 201

    refused = client.post("/categories", json={"name": duplicate})
    assert refused.status_code == 409
    assert refused.json()["detail"] == "Category name already exists."
    assert [category["name"] for category in client.get("/categories").json()] == [existing]


def test_rename_excludes_itself_and_rejects_other_equivalent_names(category_client):
    client, _, _ = category_client
    kitchen = client.post("/categories", json={"name": "Küche"}).json()
    bread = client.post("/categories", json={"name": "Brot"}).json()
    kitchen_url = f"/categories/{kitchen['id']}"
    bread_url = f"/categories/{bread['id']}"

    refused = client.put(bread_url, json={"name": "KUECHE", "description": "Neue Beschreibung"})
    assert refused.status_code == 409
    assert client.get(bread_url).json() == bread

    renamed = client.put(kitchen_url, json={"name": "KUECHE"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "KUECHE"
    assert client.put(kitchen_url, json={"name": "KUECHE"}).status_code == 200


def test_legacy_duplicates_can_be_read_and_edited_without_renaming(category_client):
    client, engine, _ = category_client
    with Session(engine) as session:
        category = Category(name="Küche")
        session.add_all([category, Category(name="Kueche")])
        session.commit()
        url = f"/categories/{category.id}"

    assert {category["name"] for category in client.get("/categories").json()} == {"Küche", "Kueche"}
    assert client.put(url, json={"description": "Eingemachtes"}).status_code == 200
    assert client.put(url, json={"name": "Küche"}).status_code == 200
    assert client.put(url, json={"name": "KÜCHE"}).status_code == 409
    assert client.put(url, json={"name": "Vorrat"}).status_code == 200
    assert client.get(url).json()["description"] == "Eingemachtes"


def test_category_name_cannot_be_cleared(category_client):
    client, _, _ = category_client
    category = client.post("/categories", json={"name": "Küche"}).json()
    url = f"/categories/{category['id']}"
    assert client.put(url, json={"name": None}).status_code == 422
    assert client.get(url).json() == category


def test_recipe_creation_requires_an_existing_category(category_client):
    client, _, user = category_client
    user.role = UserRole.EDITOR
    payload = {"title": "Apfelkuchen"}

    assert client.post("/recipes", json=payload).status_code == 422
    assert client.post("/recipes", json={**payload, "category_id": 1}).status_code == 404
    assert client.get("/categories").json() == []
    assert client.get("/recipes").json()["total"] == 0
    assert client.post("/categories", json={"name": "Kuchen"}).status_code == 403

    user.role = UserRole.ADMIN
    category = client.post("/categories", json={"name": "Kuchen"})
    assert category.status_code == 201
    user.role = UserRole.EDITOR
    assert (
        client.post("/recipes", json={**payload, "category_id": category.json()["id"]}).status_code
        == 201
    )


def test_category_image_upload_replaces_the_previous_file_and_can_be_removed(
    category_client, tmp_path, monkeypatch
):
    client, _, _ = category_client
    image_settings = replace(settings, recipe_images_dir=str(tmp_path))
    monkeypatch.setattr(category_service, "settings", image_settings)
    monkeypatch.setattr(recipe_image_service, "settings", image_settings)
    category = client.post("/categories", json={"name": "Kuchen"}).json()
    category_url = f"/categories/{category['id']}"
    image_url = f"{category_url}/image"
    image_dir = tmp_path / "categories" / str(category["id"])

    def upload(color):
        image = BytesIO()
        Image.new("RGB", (8, 8), color).save(image, "PNG")
        response = client.post(image_url, files={"image": ("bild.png", image.getvalue(), "image/png")})
        assert response.status_code == 200
        path = response.json()["image_path"]
        assert client.get(category_url).json()["image_path"] == path
        assert [file.name for file in image_dir.iterdir()] == [path.rsplit("/", 1)[1]]
        return path

    assert upload("red") != upload("blue")
    removed = client.delete(image_url)
    assert removed.status_code == 200
    assert client.get(category_url).json()["image_path"] is None
    assert list(image_dir.iterdir()) == []


@pytest.mark.parametrize("has_existing_image", [False, True])
def test_failed_category_image_commit_removes_new_file_and_preserves_old_image(
    category_client, tmp_path, monkeypatch, has_existing_image
):
    client, engine, _ = category_client
    image_settings = replace(settings, recipe_images_dir=str(tmp_path))
    monkeypatch.setattr(category_service, "settings", image_settings)
    monkeypatch.setattr(recipe_image_service, "settings", image_settings)
    category_id = client.post("/categories", json={"name": "Kuchen"}).json()["id"]
    image = BytesIO()
    Image.new("RGB", (8, 8), "red").save(image, "PNG")
    image_bytes = image.getvalue()
    old_path = None
    if has_existing_image:
        response = client.post(
            f"/categories/{category_id}/image",
            files={"image": ("old.png", image_bytes, "image/png")},
        )
        assert response.status_code == 200
        old_path = response.json()["image_path"]

    image_dir = tmp_path / "categories" / str(category_id)
    old_files = {path: path.read_bytes() for path in image_dir.glob("*")}
    with Session(engine) as session:
        def fail_commit():
            session.flush()
            raise RuntimeError("Database commit failed")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="Database commit failed"):
            category_service.set_category_image(
                db_session=session,
                category_id=category_id,
                image=UploadFile(
                    filename="new.png", file=BytesIO(image_bytes),
                    headers=Headers({"content-type": "image/png"}),
                ),
            )

        assert {path: path.read_bytes() for path in image_dir.glob("*")} == old_files
        # Rollback must restore the session as well as the persisted image reference.
        assert session.get(Category, category_id).image_path == old_path

    assert client.get(f"/categories/{category_id}").json()["image_path"] == old_path


def test_category_list_uses_current_counts_and_ignores_old_shared_order(category_client):
    client, engine, _ = category_client
    cake = client.post("/categories", json={"name": "Kuchen"}).json()["id"]
    bread = client.post("/categories", json={"name": "Brot"}).json()["id"]
    with Session(engine) as session:
        session.add(AppSetting(key="category_order", value=f"[{cake}, {bread}]"))
        session.commit()

    def counts():
        return [(row["name"], row["recipe_count"]) for row in client.get("/categories").json()]

    recipe = client.post("/recipes", json={"title": "Apfelkuchen", "category_id": cake})
    assert recipe.status_code == 201
    assert counts() == [("Brot", 0), ("Kuchen", 1)]
    url = f"/recipes/{recipe.json()['id']}"
    assert client.put(url, json={"category_id": bread}).status_code == 200
    assert counts() == [("Brot", 1), ("Kuchen", 0)]
    assert client.put(f"/categories/{bread}", json={"name": "Vollkornbrot"}).status_code == 200
    assert client.delete(f"/categories/{cake}").status_code == 204
    assert counts() == [("Vollkornbrot", 1)]


def test_category_sort_and_order_are_private_account_preferences(category_client):
    client, engine, user = category_client
    cake = client.post("/categories", json={"name": "Kuchen"}).json()["id"]
    bread = client.post("/categories", json={"name": "Brot"}).json()["id"]
    with Session(engine) as session:
        session.add_all([User(username=name, password_hash="hash") for name in ("lena", "tim")])
        session.commit()

    lena = "/users/1/view-preferences"
    tim = "/users/2/view-preferences"
    default = {"category_sort": "name", "category_ids": [], "recipe_view": "list"}
    assert client.get(lena).json() == default
    assert client.put("/categories/order", json={"category_ids": [cake, bread]}).status_code == 200
    assert client.get(lena).json() == {**default, "category_sort": "manual", "category_ids": [cake, bread]}
    assert client.patch(lena, json={"category_sort": "count"}).status_code == 204
    assert client.get(lena).json() == {**default, "category_sort": "count", "category_ids": [cake, bread]}
    assert client.patch(tim, json={"category_sort": "manual"}).status_code == 403
    user.id = 2
    assert client.get(tim).json() == default
    assert client.get(lena).status_code == 403


def test_category_image_path_is_not_client_writable(category_client):
    client, _, _ = category_client
    assert client.post(
        "/categories", json={"name": "Kuchen", "image_path": "/media/recipe-images/1/x.jpg"}
    ).status_code == 422
    category = client.post("/categories", json={"name": "Kuchen"}).json()
    assert client.put(
        f"/categories/{category['id']}", json={"image_path": "/media/recipe-images/../x"}
    ).status_code == 422


def test_category_image_removal_never_deletes_files_outside_category_images(tmp_path, monkeypatch):
    image_settings = replace(settings, recipe_images_dir=str(tmp_path / "images"))
    monkeypatch.setattr(category_service, "settings", image_settings)
    recipe_image = tmp_path / "images" / "1" / "photo.jpg"
    outside = tmp_path / "secret.txt"
    for path in (recipe_image, outside):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("keep")

    category_service._remove_image_file("/media/recipe-images/1/photo.jpg")
    category_service._remove_image_file("/media/recipe-images/categories/../../secret.txt")

    assert recipe_image.exists()
    assert outside.exists()
