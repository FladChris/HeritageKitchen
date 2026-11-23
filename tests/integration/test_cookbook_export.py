"""Administrator-only, consistent and complete cookbook downloads."""

import io
import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.api.app import app
from app.api.dependencies import DbSession, get_current_user
from app.core import config
from app.core.db import create_database_engine, get_db
from app.models import Base, Category, Recipe, User
from app.models.app_setting_model import AppSetting
from app.models.user_model import UserRole
from app.services import (
    cookbook_export_service,
    recipe_image_service,
    recipe_image_storage,
)


@pytest.fixture(params=["sqlite", "postgresql"])
def export_client(tmp_path, monkeypatch, request):
    schema = None
    url = None
    if request.param == "postgresql":
        url = os.environ.get("TEST_DATABASE_URL")
        if not url or make_url(url).get_backend_name() != "postgresql":
            pytest.skip("Set TEST_DATABASE_URL for PostgreSQL export acceptance tests")
        schema = "test_cookbook_export_" + uuid4().hex
        base = create_database_engine(url)
        with base.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {schema}"))
        base.dispose()
        engine = create_database_engine(
            make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
        )
    else:
        engine = create_database_engine(f"sqlite:///{tmp_path / 'export.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Category(id=1, name="Kuchen"),
            User(id=1, username="Petra", password_hash="SECRET_HASH_DO_NOT_EXPORT",
                 role=UserRole.ADMIN),
            User(id=2, username="Lena", password_hash="another-secret",
                 role=UserRole.EDITOR),
            User(id=3, username="Tim", password_hash="another-secret",
                 role=UserRole.READER),
        ])
        db.commit()
    actor = SimpleNamespace(id=1)

    def test_db():
        with Session(engine) as db:
            yield db

    def scoped_user(db: DbSession):
        return db.get(User, actor.id)

    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_user] = scoped_user
    image_settings = replace(config.settings, recipe_images_dir=str(tmp_path / "images"))
    directory = Path(image_settings.recipe_images_dir)
    directory.mkdir()
    monkeypatch.setattr(recipe_image_service, "settings", image_settings)
    monkeypatch.setattr(recipe_image_storage, "settings", image_settings)
    monkeypatch.setattr(cookbook_export_service, "settings", image_settings)
    try:
        yield TestClient(app), actor, engine, directory
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        engine.dispose()
        if schema and url:
            base = create_database_engine(url)
            with base.begin() as connection:
                connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            base.dispose()


def photo(color):
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color).save(buf, "JPEG")
    return {"image": ("cake.jpg", buf.getvalue(), "image/jpeg")}


def recipe_with_social_content(client, directory):
    recipe = client.post("/api/recipes", json={
        "title": "Apfelkuchen", "category_id": 1,
        "ingredients": [{"position": 0, "name": "Mehl", "amount": "500", "unit": "g"}],
        "steps": [{"position": 0, "instruction": "Teig verrühren"}],
        "history": "Von Uroma Anna", "notes": "Lauwarm servieren",
    })
    assert recipe.status_code == 201
    recipe_id = recipe.json()["id"]
    first = client.post(f"/api/recipes/{recipe_id}/images", files=photo("red"))
    assert first.status_code == 201
    first_image = first.json()
    historical_bytes = (directory / str(recipe_id) / Path(first_image["file_path"]).name).read_bytes()
    assert client.put(f"/api/recipe-images/{first_image['id']}",
                      json={"is_main": True}).status_code == 200
    replacement = client.put(
        f"/api/recipe-images/{first_image['id']}/crop", files=photo("blue")
    )
    assert replacement.status_code == 200
    assert replacement.json()["file_path"] != first_image["file_path"]
    comment = client.post(f"/api/recipes/{recipe_id}/comments", json={"text": "Weniger Zucker"})
    assert comment.status_code == 201
    rating = client.put(f"/api/recipes/{recipe_id}/ratings", json={"stars": 4.5})
    assert rating.status_code == 200
    return recipe_id, first_image, historical_bytes


def test_zip_includes_current_images_social_content_without_secrets(export_client):
    client, actor, _, directory = export_client
    actor.id = 2
    recipe_id, historical, _ = recipe_with_social_content(client, directory)
    renamed = client.patch("/api/auth/me", json={"username": "Kochlena"})
    assert renamed.status_code == 200
    comments = client.get(f"/api/recipes/{recipe_id}/comments").json()
    assert {comment["author_username"] for comment in comments} == {"Kochlena"}
    actor.id = 1
    response = client.get("/api/settings/export/zip")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("cookbook.json"))
        assert manifest["format_version"] == 1
        assert [category["name"] for category in manifest["categories"]] == ["Kuchen"]
        data, = manifest["recipes"]
        assert data["id"] == recipe_id
        assert data["ingredients"][0]["name"] == "Mehl"
        assert data["history"] == "Von Uroma Anna"
        assert [comment["text"] for comment in data["comments"]] == ["Weniger Zucker"]
        assert {comment["author_name"] for comment in data["comments"]} == {"Kochlena"}
        assert data["ratings"][0]["half_stars"] == 9
        assert "versions" not in data
        assert all(image["file_path"] != historical["file_path"] for image in data["images"])
        for image in data["images"]:
            assert archive.read(image["archive_path"])
        assert "SECRET_HASH_DO_NOT_EXPORT" not in archive.read("cookbook.json").decode()
        assert not any(name.startswith("accounts/") for name in archive.namelist())


def test_pdf_is_readable_and_excludes_social_content(export_client):
    client, actor, _, directory = export_client
    actor.id = 2
    recipe_with_social_content(client, directory)
    actor.id = 1
    response = client.get("/api/settings/export/pdf")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    document = PdfReader(io.BytesIO(response.content))
    document_text = "\n".join(page.extract_text() for page in document.pages)
    assert "Apfelkuchen" in document_text
    assert "Mehl" in document_text
    assert "Teig verrühren" in document_text
    assert "Von Uroma Anna" in document_text
    assert "Weniger Zucker" not in document_text
    assert "4.5" not in document_text
    assert all(not page.images for page in document.pages)


def export_during_recipe_update(export_client, format):
    client, _, engine, directory = export_client
    recipe_id, historical, historical_bytes = recipe_with_social_content(client, directory)
    recipe_url = f"/api/recipes/{recipe_id}"
    before = client.get(recipe_url).json()
    old_image, = before["images"]
    old_image_bytes = (directory / str(recipe_id) / Path(old_image["file_path"]).name).read_bytes()
    assert old_image_bytes != historical_bytes
    (directory / str(recipe_id) / Path(historical["file_path"]).name).write_bytes(historical_bytes)
    if engine.dialect.name == "sqlite":
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA journal_mode = WAL").scalar() == "wal"

    changed = False

    def update_before_relationship_read(state):
        nonlocal changed
        if changed or not state.is_relationship_load or state.session.bind is not engine:
            return
        # The export has already read the recipe row. Commit a new version
        # through a separate connection before it reads ingredients and images.
        changed = True
        with Session(engine) as writer, writer.begin():
            if engine.dialect.name == "postgresql":
                writer.execute(text("SET LOCAL lock_timeout = '2s'"))
            recipe = writer.get(Recipe, recipe_id)
            recipe.title = "Pflaumenkuchen"
            recipe.ingredients[0].name = "Hafer"
            recipe.images[0].file_path = historical["file_path"]
            recipe.version += 1

    event.listen(Session, "do_orm_execute", update_before_relationship_read)
    try:
        response = client.get(f"/api/settings/export/{format}")
    finally:
        event.remove(Session, "do_orm_execute", update_before_relationship_read)

    assert changed
    after = client.get(recipe_url).json()
    assert (after["version"], after["title"], after["ingredients"][0]["name"]) == (
        before["version"] + 1, "Pflaumenkuchen", "Hafer",
    )
    assert after["images"][0]["file_path"] == historical["file_path"]
    assert response.status_code == 200, response.text
    return response.content, before["version"], old_image["file_path"], old_image_bytes


def test_zip_keeps_one_snapshot_during_recipe_update(export_client):
    content, old_version, old_image_path, old_image_bytes = export_during_recipe_update(
        export_client, "zip"
    )
    with ZipFile(io.BytesIO(content)) as archive:
        data, = json.loads(archive.read("cookbook.json"))["recipes"]
        assert (data["version"], data["title"], data["ingredients"][0]["name"]) == (
            old_version, "Apfelkuchen", "Mehl",
        )
        image, = data["images"]
        assert image["file_path"] == old_image_path
        assert archive.read(image["archive_path"]) == old_image_bytes


def test_pdf_keeps_one_snapshot_during_recipe_update(export_client):
    content, _, _, _ = export_during_recipe_update(export_client, "pdf")
    document = PdfReader(io.BytesIO(content))
    content = "\n".join(page.extract_text() for page in document.pages)
    assert "Apfelkuchen" in content and "Mehl" in content
    assert "Pflaumenkuchen" not in content and "Hafer" not in content


@pytest.mark.parametrize("format", ["zip", "pdf"])
def test_reader_and_editor_cannot_export(export_client, format):
    client, actor, _, _ = export_client
    for user_id in (2, 3):
        actor.id = user_id
        assert client.get("/api/settings/export/" + format).status_code == 403


def test_missing_current_image_fails_without_partial_zip(export_client):
    client, actor, _, directory = export_client
    actor.id = 2
    recipe_id, _, _ = recipe_with_social_content(client, directory)
    image, = client.get(f"/api/recipes/{recipe_id}").json()["images"]
    actor.id = 1
    (directory / str(recipe_id) / Path(image["file_path"]).name).unlink()
    response = client.get("/api/settings/export/zip")
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/json"
    assert not response.content.startswith(b"PK")


def test_empty_cookbook_can_be_exported(export_client):
    client, _, _, _ = export_client
    for format in ("zip", "pdf"):
        response = client.get("/api/settings/export/" + format)
        assert response.status_code == 200


def multi_day_recipe(client):
    response = client.post("/api/recipes", json={
        "title": "Sauerteigbrot", "category_id": 1,
        "preparation_days": 2, "day_titles": ["Ansatz", "Backen"],
        "ingredients": [{"position": 0, "name": "Roggenmehl"}],
        "steps": [
            {"position": 0, "instruction": "Ansatz mischen", "day": 1,
             "duration_minutes": 20, "time_kind": "preparation"},
            {"position": 1, "instruction": "Brot backen", "day": 2,
             "duration_minutes": 45, "time_kind": "cooking"},
        ],
    })
    assert response.status_code == 201, response.text


def test_exports_include_step_times_and_days(export_client):
    client, _, _, _ = export_client
    multi_day_recipe(client)
    with ZipFile(io.BytesIO(client.get("/api/settings/export/zip").content)) as archive:
        data, = json.loads(archive.read("cookbook.json"))["recipes"]
    assert data["preparation_days"] == 2
    assert data["day_titles"] == ["Ansatz", "Backen"]
    assert [(s["day"], s["duration_minutes"], s["time_kind"]) for s in data["steps"]] == [
        (1, 20, "preparation"), (2, 45, "cooking"),
    ]
    document = PdfReader(io.BytesIO(client.get("/api/settings/export/pdf").content))
    document_text = "\n".join(page.extract_text() for page in document.pages)
    assert "Tag 1 – Ansatz" in document_text
    assert "Tag 2 – Backen" in document_text
    assert "20 Min." in document_text


def test_pdf_uses_configured_cookbook_name_and_footer(export_client):
    client, _, engine, _ = export_client
    with Session(engine) as db:
        db.add_all([
            AppSetting(key="cookbook_name", value="Omas Rezepte"),
            AppSetting(key="footer_text", value="Mit Liebe gekocht"),
        ])
        db.commit()
    document = PdfReader(io.BytesIO(client.get("/api/settings/export/pdf").content))
    text_content = document.pages[0].extract_text()
    assert "Omas Rezepte" in text_content
    assert "Mit Liebe gekocht" in text_content
    assert "Familienkochbuch" not in text_content
    assert "Omas Rezepte" in document.metadata.author


def test_pdf_falls_back_to_default_name_without_settings(export_client):
    client, _, _, _ = export_client
    document = PdfReader(io.BytesIO(client.get("/api/settings/export/pdf").content))
    assert "Heritage Kitchen" in document.pages[0].extract_text()


def test_missing_current_image_does_not_block_pdf(export_client):
    client, actor, _, directory = export_client
    actor.id = 2
    recipe_id, _, _ = recipe_with_social_content(client, directory)
    image, = client.get(f"/api/recipes/{recipe_id}").json()["images"]
    assert image["is_main"]
    (directory / str(recipe_id) / Path(image["file_path"]).name).unlink()

    actor.id = 1
    response = client.get("/api/settings/export/pdf")
    assert response.status_code == 200, response.text
    pages = PdfReader(io.BytesIO(response.content)).pages
    assert "Apfelkuchen" in pages[1].extract_text()
    assert all(not page.images for page in pages)
