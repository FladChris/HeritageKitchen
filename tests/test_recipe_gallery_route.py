import io
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.api.app import app, media_files
from app.api.dependencies import get_current_user
from app.core import config
from app.core.db import create_database_engine, get_db
from app.models import Base, Category, User
from app.models.user_model import UserRole
from app.services import recipe_image_service, recipe_image_storage


@pytest.fixture
def gallery(tmp_path, monkeypatch):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'gallery.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Category(id=1, name="Kuchen"),
            User(id=1, username="Petra", password_hash="unused", role=UserRole.ADMIN),
        ])
        session.commit()

    def test_db():
        with Session(engine) as session:
            yield session

    def user():
        with Session(engine) as session:
            return session.get(User, 1)

    monkeypatch.setitem(app.dependency_overrides, get_db, test_db)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, user)
    image_settings = replace(config.settings, recipe_images_dir=str(tmp_path))
    monkeypatch.setattr(recipe_image_service, "settings", image_settings)
    monkeypatch.setattr(recipe_image_storage, "settings", image_settings)
    monkeypatch.setattr(media_files, "all_directories", [str(tmp_path)])
    monkeypatch.setattr(media_files, "directory", str(tmp_path))
    try:
        yield TestClient(app), tmp_path
    finally:
        engine.dispose()


def jpeg(color="red"):
    data = io.BytesIO()
    Image.new("RGB", (10, 10), color).save(data, "JPEG")
    return {"image": ("photo.jpg", data.getvalue(), "image/jpeg")}


def new_recipe(client):
    response = client.post("/api/recipes", json={"title": "Apfelkuchen", "category_id": 1})
    assert response.status_code == 201
    return f"/api/recipes/{response.json()['id']}"


def upload(client, path, count):
    return [client.post(f"{path}/images", files=jpeg()).json() for _ in range(count)]


def gallery_ids(client, path):
    return [image["id"] for image in client.get(path).json()["images"]]


def test_twenty_first_image_is_rejected_without_changing_the_gallery(gallery):
    client, directory = gallery
    path = new_recipe(client)
    images = upload(client, path, 20)
    assert client.put(f"/api/recipe-images/{images[3]['id']}", json={"is_main": True}).status_code == 200
    version = client.get(path).json()["version"]
    files = set(directory.glob("*/*.jpg"))

    response = client.post(f"{path}/images", files=jpeg("blue"))

    assert response.status_code == 409
    assert "20" in response.json()["detail"]
    assert set(directory.glob("*/*.jpg")) == files
    detail = client.get(path).json()
    assert detail["version"] == version
    assert [image["id"] for image in detail["images"]] == [image["id"] for image in images]
    assert [image["id"] for image in detail["images"] if image["is_main"]] == [images[3]["id"]]


def test_gallery_order_is_persistent_and_validated_with_alt_text(gallery):
    client, _ = gallery
    path = new_recipe(client)
    a, b, c = upload(client, path, 3)
    assert client.put(f"/api/recipe-images/{a['id']}", json={"alt_text": "Damals"}).status_code == 200

    reordered = client.put(f"{path}/images/order", json={"image_ids": [c["id"], a["id"], b["id"]]})
    assert reordered.status_code == 200
    assert [image["id"] for image in reordered.json()] == [c["id"], a["id"], b["id"]]
    assert gallery_ids(client, path) == [c["id"], a["id"], b["id"]]
    version = client.get(path).json()["version"]

    for invalid in ([a["id"], b["id"]], [a["id"], b["id"], b["id"]], [a["id"], b["id"], c["id"], 999], [a["id"], b["id"], 999]):
        assert client.put(f"{path}/images/order", json={"image_ids": invalid}).status_code == 422
    assert gallery_ids(client, path) == [c["id"], a["id"], b["id"]]
    assert client.get(path).json()["version"] == version

    assert client.put(f"/api/recipe-images/{a['id']}", json={"alt_text": "Später"}).status_code == 200
    assert client.put(f"{path}/images/order", json={"image_ids": [a["id"], b["id"], c["id"]]}).status_code == 200
    images = client.get(path).json()["images"]
    assert [image["id"] for image in images] == [a["id"], b["id"], c["id"]]
    assert [image["alt_text"] for image in images] == ["Später", None, None]


def test_deleting_the_main_image_promotes_the_first_remaining_image(gallery):
    client, _ = gallery
    path = new_recipe(client)
    a, b, c = upload(client, path, 3)
    assert client.put(f"/api/recipe-images/{a['id']}", json={"is_main": True}).status_code == 200
    assert client.put(f"{path}/images/order", json={"image_ids": [a["id"], c["id"], b["id"]]}).status_code == 200

    assert client.delete(f"/api/recipe-images/{a['id']}").status_code == 204
    images = client.get(path).json()["images"]
    assert [(image["id"], image["is_main"]) for image in images] == [(c["id"], True), (b["id"], False)]

    assert client.delete(f"/api/recipe-images/{b['id']}").status_code == 204
    assert client.get(path).json()["images"][0]["is_main"] is True
    assert client.delete(f"/api/recipe-images/{c['id']}").status_code == 204
    assert client.get(path).json()["images"] == []


def test_deleting_a_non_main_image_keeps_the_main_image(gallery):
    client, _ = gallery
    path = new_recipe(client)
    a, b, c = upload(client, path, 3)
    assert client.put(f"/api/recipe-images/{b['id']}", json={"is_main": True}).status_code == 200
    assert client.delete(f"/api/recipe-images/{a['id']}").status_code == 204
    assert [(image["id"], image["is_main"]) for image in client.get(path).json()["images"]] == [
        (b["id"], True), (c["id"], False),
    ]


@pytest.mark.parametrize("submitted, expected", [
    ("  Kuchen auf dem Teller  ", "Kuchen auf dem Teller"),
    ("   ", None),
    (" " + "x" * 255 + " ", "x" * 255),
])
def test_upload_normalizes_optional_alt_text(gallery, submitted, expected):
    client, _ = gallery
    path = new_recipe(client)

    response = client.post(f"{path}/images", files=jpeg(), data={"alt_text": submitted})

    assert response.status_code == 201
    assert response.json()["alt_text"] == expected
    assert client.get(path).json()["images"][0]["alt_text"] == expected


def test_upload_rejects_too_long_alt_text_without_saving_an_image(gallery):
    client, directory = gallery
    path = new_recipe(client)
    before = client.get(path).json()

    response = client.post(f"{path}/images", files=jpeg(), data={"alt_text": "x" * 256})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "alt_text"]
    assert client.get(path).json() == before
    assert list(directory.glob("*/*.jpg")) == []


def test_alt_text_can_be_changed_and_cleared(gallery):
    client, _ = gallery
    path = new_recipe(client)
    (image,) = upload(client, path, 1)
    link = f"/api/recipe-images/{image['id']}"
    assert client.put(link, json={"alt_text": "Kuchen"}).json()["alt_text"] == "Kuchen"
    assert client.put(link, json={"is_main": True}).json()["alt_text"] == "Kuchen"
    assert client.put(link, json={"alt_text": None}).json()["alt_text"] is None
    assert client.put(link, json={"alt_text": "  "}).json()["alt_text"] is None
