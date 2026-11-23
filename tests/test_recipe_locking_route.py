import io
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.app import app, media_files
from app.api.dependencies import DbSession, authentication_error, get_current_user
from app.api.schemas import RecipeUpdateRequest
from app.core import config
from app.core.db import create_database_engine, get_db
from app.models import Base, Category, RecipeImage, User
from app.models.user_model import UserRole
from app.services import recipe_image_service, recipe_image_storage, recipe_service


@pytest.fixture
def versions(tmp_path, monkeypatch, request):
    if getattr(request, "param", "sqlite") == "postgresql":
        url = os.environ.get("TEST_DATABASE_URL")
        if not url or make_url(url).get_backend_name() != "postgresql":
            pytest.skip("TEST_DATABASE_URL must point to PostgreSQL for this case")
        schema = f"test_recipe_version_route_{uuid4().hex}"
        engine = create_database_engine(make_url(url).update_query_dict({"options": f"-csearch_path={schema}"}))
        with engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {schema}"))
    else:
        schema = None
        engine = create_database_engine(f"sqlite:///{tmp_path / 'versions.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Category(id=1, name="Kuchen"), Category(id=2, name="Desserts"),
            User(id=1, username="Petra", password_hash="unused", role=UserRole.ADMIN),
            User(id=2, username="Lena", password_hash="unused", role=UserRole.EDITOR),
            User(id=3, username="Tim", password_hash="unused", role=UserRole.READER),
        ])
        session.commit()

    def test_db():
        with Session(engine) as session:
            yield session

    def user(db: DbSession):
        if actor.id is None:
            raise authentication_error()
        return db.get(User, actor.id)

    actor = SimpleNamespace(id=2)
    monkeypatch.setitem(app.dependency_overrides, get_db, test_db)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, user)
    image_settings = replace(config.settings, recipe_images_dir=str(tmp_path))
    monkeypatch.setattr(recipe_image_service, "settings", image_settings)
    monkeypatch.setattr(recipe_image_storage, "settings", image_settings)
    monkeypatch.setattr(media_files, "all_directories", [str(tmp_path)])
    monkeypatch.setattr(media_files, "directory", str(tmp_path))
    try:
        yield TestClient(app), engine, actor, tmp_path
    finally:
        if schema:
            with engine.begin() as connection:
                connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        engine.dispose()


def create_recipe(client, **extra):
    response = client.post("/api/recipes", json={"title": "Apfelkuchen", "category_id": 1, **extra})
    assert response.status_code == 201
    assert response.json()["version"] == 1
    return f"/api/recipes/{response.json()['id']}"


def jpeg(color):
    image = io.BytesIO()
    Image.new("RGB", (10, 10), color).save(image, "JPEG")
    return {"image": ("photo.jpg", image.getvalue(), "image/jpeg")}


@pytest.mark.parametrize("versions", ["sqlite", "postgresql"], indirect=True)
def test_recipe_deletion_keeps_shared_and_unmanaged_files(versions):
    client, engine, _, directory = versions
    owner = create_recipe(client)
    other = create_recipe(client)
    owner_id, other_id = (int(path.rsplit("/", 1)[1]) for path in (owner, other))
    current, historical = [client.post(f"{owner}/images", files=jpeg("red")).json() for _ in range(2)]
    current_file, historical_file = [
        directory / str(owner_id) / Path(image["file_path"]).name for image in (current, historical)
    ]
    unmanaged = current_file.with_name("old.jpg")
    unmanaged.write_bytes(b"unmanaged")
    with Session(engine) as session:
        session.add_all([
            RecipeImage(recipe_id=owner_id, file_path="/old.jpg", is_main=False),
            RecipeImage(recipe_id=other_id, file_path=current["file_path"], is_main=False),
            RecipeImage(recipe_id=other_id, file_path=historical["file_path"], is_main=False),
        ])
        session.commit()
    with Session(engine) as session:
        session.execute(delete(RecipeImage).where(
            RecipeImage.recipe_id == other_id, RecipeImage.file_path == historical["file_path"],
        ))
        session.commit()
    assert client.delete(owner).status_code == 204
    assert current_file.exists() and not historical_file.exists() and unmanaged.exists()
    assert client.delete(other).status_code == 204
    recipe_image_storage.retry_recipe_file_deletions(engine)
    assert not current_file.exists() and not historical_file.exists()
    assert unmanaged.read_bytes() == b"unmanaged"


@pytest.mark.parametrize("versions", ["sqlite", "postgresql"], indirect=True)
@pytest.mark.parametrize("operation", ["upload", "crop"])
@pytest.mark.parametrize("outcome", ["committed", "rolled_back", "unknown", "committed_unknown"])
def test_upload_file_cleanup_requires_a_confirmed_database_outcome(versions, monkeypatch, operation, outcome):
    client, engine, _, directory = versions
    path = create_recipe(client)
    if operation == "crop":
        original = client.post(f"{path}/images", files=jpeg("red")).json()
    existing = set(directory.glob("*/*.jpg"))
    commit = Session.commit
    commit_failed = False

    def unconfirmed_commit(session):
        nonlocal commit_failed
        if outcome.startswith("committed"):
            commit(session)
        commit_failed = True
        raise RuntimeError("Commit acknowledgement lost")

    def reject_verification(*args):
        if commit_failed and outcome.endswith("unknown"):
            raise OperationalError(None, None, RuntimeError("Database unreachable"))

    event.listen(engine, "before_cursor_execute", reject_verification)
    try:
        with monkeypatch.context() as patch, pytest.raises(RuntimeError, match="acknowledgement lost"):
            patch.setattr(Session, "commit", unconfirmed_commit)
            if operation == "upload":
                client.post(f"{path}/images", files=jpeg("blue"))
            else:
                client.put(f"/api/recipe-images/{original['id']}/crop", files=jpeg("blue"))
    finally:
        event.remove(engine, "before_cursor_execute", reject_verification)

    new_files = set(directory.glob("*/*.jpg")) - existing
    assert len(new_files) == (0 if outcome == "rolled_back" else 1)
    recipe = client.get(path).json()
    if outcome.startswith("committed"):
        assert Path(recipe["images"][0]["file_path"]).name == next(iter(new_files)).name
        version = 2 if operation == "upload" else 3
        assert recipe["version"] == version
        assert next(iter(new_files)).is_file()
    else:
        assert recipe["version"] == (1 if operation == "upload" else 2)

    recipe_image_storage.retry_recipe_file_deletions(engine)
    expected = new_files if outcome.startswith("committed") else existing
    assert set(directory.glob("*/*.jpg")) == expected
    assert not list(directory.glob("*/.*.jpg.pending"))


@pytest.mark.parametrize("versions", ["sqlite", "postgresql"], indirect=True)
def test_recipe_detail_stays_consistent_with_a_concurrent_write(versions):
    client, engine, _, _ = versions
    path = create_recipe(client, ingredients=[{"position": 0, "name": "Flour"}])
    recipe_id = int(path.rsplit("/", 1)[1])
    if engine.dialect.name == "sqlite":
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode = WAL")
    attempted = False
    update_data = RecipeUpdateRequest(title="Updated", ingredients=[{"position": 0, "name": "Milk"}])

    def write_before_children_are_loaded(state):
        nonlocal attempted
        if state.is_relationship_load and not attempted:
            attempted = True
            try:
                with Session(engine) as session:
                    if engine.dialect.name == "postgresql":
                        session.execute(text("SET LOCAL lock_timeout = '150ms'"))
                    recipe_service.update_recipe(
                        db_session=session, recipe_id=recipe_id,
                        recipe_update_request=update_data, expected_version=1,
                    )
            except OperationalError as exc:
                if getattr(exc.orig, "sqlstate", None) != "55P03":
                    raise

    event.listen(Session, "do_orm_execute", write_before_children_are_loaded)
    try:
        response = client.get(path)
    finally:
        event.remove(Session, "do_orm_execute", write_before_children_are_loaded)
    assert attempted
    assert response.status_code == 200
    detail = response.json()
    assert (detail["version"], detail["title"], detail["ingredients"][0]["name"]) == (1, "Apfelkuchen", "Flour")
    # SQLite allows the concurrent write in WAL mode. PostgreSQL blocks it
    # while the detail response holds a shared lock.
    updated = client.get(path).json()
    if engine.dialect.name == "postgresql":
        updated = client.put(path, json=update_data.model_dump(exclude_unset=True)).json()
    assert (updated["version"], updated["title"], updated["ingredients"][0]["name"]) == (2, "Updated", "Milk")


def test_deleted_recipe_id_is_not_reused_with_model_schema(versions):
    client, _, _, _ = versions
    original = create_recipe(client)
    assert client.delete(original).status_code == 204
    replacement = create_recipe(client)
    assert original != replacement
    assert client.get(original).status_code == 404


def test_concurrent_writes_keep_both_changes_and_advance_revision(versions):
    client, _, _, _ = versions
    path = create_recipe(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda field: client.put(path, json=field), [{"notes": "A"}, {"history": "B"}]))
    assert all(response.status_code == 200 for response in results)
    current = client.get(path).json()
    assert current["version"] == 3
    assert current["notes"] == "A"
    assert current["history"] == "B"


def test_group_only_update_preserves_ingredients_in_multiple_groups(versions):
    client, _, _, _ = versions
    path = create_recipe(
        client,
        ingredient_groups=[{"position": 1, "name": "Teig"}, {"position": 2, "name": "Creme"}],
        ingredients=[
            {"position": 0, "name": "Mehl", "group_position": 1},
            {"position": 1, "name": "Milch", "group_position": 2},
        ],
    )
    groups = [{"position": 1, "name": "Boden"}, {"position": 2, "name": "Füllung"}]
    updated = client.put(path, json={"ingredient_groups": groups})

    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert [
        (ingredient["name"], ingredient["group_position"])
        for ingredient in updated.json()["ingredients"]
    ] == [("Mehl", 1), ("Milch", 2)]
    assert [group["name"] for group in updated.json()["ingredient_groups"]] == [
        "Boden",
        "Füllung",
    ]


@pytest.mark.parametrize("recipe_id", [0, -7])
def test_retries_upload_markers_for_legacy_recipe_ids(versions, recipe_id):
    _, engine, _, directory = versions
    stored = directory / str(recipe_id) / f"{uuid4()}.jpg"
    stored.parent.mkdir()
    recipe_image_storage.track_recipe_upload(stored)
    stored.write_bytes(b"orphan")

    recipe_image_storage.retry_recipe_file_deletions(engine)

    assert not list(stored.parent.iterdir())


@pytest.mark.parametrize("versions", ["sqlite", "postgresql"], indirect=True)
def test_ticket_127_minimal_duplicate_recipes_and_category_move(versions):
    client, _, _, _ = versions
    first = create_recipe(client)
    second = create_recipe(client)
    assert first != second
    results = client.get("/api/recipes", params={"category_id": 1, "search": "Apfelkuchen"})
    assert results.status_code == 200
    assert {item["id"] for item in results.json()["items"]} == {
        int(path.rsplit("/", 1)[1]) for path in (first, second)
    }
    assert results.json()["total"] == 2

    for title in ("", "   "):
        assert client.post("/api/recipes", json={"title": title, "category_id": 1}).status_code == 422
    for data in ({"title": "Ohne Kategorie"}, {"title": "Falsch", "category_id": 999}):
        assert client.post("/api/recipes", json=data).status_code in (404, 422)

    assert client.put(first, json={
        "title": "Apfelkuchen", "category_id": 2, "notes": "Gemeinsame Notiz",
        "ingredients": [{"position": 0, "name": "Mehl", "amount": "1.333", "unit": "g"}],
        "steps": [{"position": 0, "instruction": "Vermengen"}],
    }).status_code == 200
    assert client.put(second, json={"category_id": 2}).status_code == 200
    assert client.get("/api/recipes", params={"category_id": 1}).json()["total"] == 0
    assert client.get("/api/recipes", params={"category_id": 2}).json()["total"] == 2
    assert client.get(first).json()["notes"] == "Gemeinsame Notiz"
    assert client.get(first).json()["ingredients"][0]["amount"] == "1.333"


@pytest.mark.parametrize("versions", ["sqlite", "postgresql"], indirect=True)
def test_ticket_127_permanent_delete_clears_social_history_and_image_files(versions):
    from sqlalchemy import select

    from app.models import Favorite
    from app.models.recipe_comment_model import RecipeComment
    from app.models.recipe_rating_model import RecipeRating
    from app.models.user_model import UserRecipePosition

    client, engine, actor, directory = versions
    path = create_recipe(client, ingredients=[{"position": 0, "name": "Mehl", "amount": "100"}])
    recipe_id = int(path.rsplit("/", 1)[1])
    untouched = create_recipe(client)
    image = client.post(f"{path}/images", files=jpeg("red")).json()
    stored = directory / str(recipe_id) / Path(image["file_path"]).name
    assert stored.is_file()

    assert client.put(path, json={"notes": "Geänderte Fassung"}).status_code == 200
    assert client.post(f"{path}/comments", json={"text": "Gut!"}).status_code == 201
    assert client.put(f"{path}/ratings", json={"stars": 4.5}).status_code == 200
    assert client.post("/api/favorites", json={"recipe_id": recipe_id}).status_code == 201
    actor.id = 1
    assert client.post("/api/favorites", json={"recipe_id": recipe_id}).status_code == 201
    with Session(engine) as session:
        session.add(UserRecipePosition(user_id=1, recipe_id=recipe_id, position=0))
        session.commit()

    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404
    assert client.put(path, json={"title": "Wieder da"}).status_code == 404
    assert client.get(untouched).status_code == 200
    assert client.get("/api/recipes", params={"search": "Apfelkuchen"}).json()["total"] == 1
    assert client.get("/api/favorites").json() == []
    with Session(engine) as session:
        for model in (RecipeImage, RecipeComment, RecipeRating, Favorite, UserRecipePosition):
            assert session.scalars(select(model).where(model.recipe_id == recipe_id)).all() == []
    recipe_image_storage.retry_recipe_file_deletions(engine)
    assert not stored.exists()


@pytest.mark.parametrize("versions", ["sqlite", "postgresql"], indirect=True)
def test_conditional_updates_detect_conflict_and_allow_explicit_retry(versions):
    client, _, _, _ = versions
    path = create_recipe(client)
    first = client.get(path)
    assert first.headers["etag"] == '"1"'

    updated = client.put(path, json={"title": "A hat geändert"}, headers={"If-Match": '"1"'})
    assert updated.status_code == 200
    assert updated.headers["etag"] == '"2"'

    stale = client.put(path, json={"title": "B hat geändert"}, headers={"If-Match": '"1"'})
    assert stale.status_code == 409
    detail = stale.json()["detail"]
    assert detail["code"] == "recipe_version_conflict"
    assert (detail["expected_version"], detail["current_version"]) == (1, 2)
    assert detail["current"]["title"] == "A hat geändert"
    assert client.get(path).json()["title"] == "A hat geändert"
    confirmed = client.put(path, json={"title": "B hat geändert"}, headers={"If-Match": '"2"'})
    assert confirmed.status_code == 200
    assert confirmed.json()["version"] == 3
    assert client.get(path).json()["title"] == "B hat geändert"


@pytest.mark.parametrize("versions", ["sqlite", "postgresql"], indirect=True)
def test_retry_is_blocked_if_another_editor_saves_again(versions):
    client, _, _, _ = versions
    path = create_recipe(client)
    assert client.put(path, json={"notes": "A"}, headers={"If-Match": '"1"'}).status_code == 200
    stale = client.put(path, json={"notes": "B"}, headers={"If-Match": '"1"'})
    assert stale.status_code == 409
    assert stale.json()["detail"]["current_version"] == 2

    assert client.put(path, json={"notes": "C"}, headers={"If-Match": '"2"'}).status_code == 200
    second_conflict = client.put(path, json={"notes": "B"}, headers={"If-Match": '"2"'})
    assert second_conflict.status_code == 409
    assert second_conflict.json()["detail"]["current_version"] == 3
    assert client.get(path).json()["notes"] == "C"


@pytest.mark.parametrize("versions", ["sqlite", "postgresql"], indirect=True)
def test_deleted_recipe_cannot_be_recreated_by_stale_editor(versions):
    client, _, _, _ = versions
    path = create_recipe(client)
    original = client.get(path).json()["id"]
    assert client.delete(path).status_code == 204
    stale = client.put(path, json={"title": "Verwaister Entwurf"}, headers={"If-Match": '"1"'})
    assert stale.status_code == 404
    assert stale.json()["detail"] == "Recipe deleted while editing."
    assert client.get(path).status_code == 404
    replacement = create_recipe(client)
    assert int(replacement.rsplit("/", 1)[1]) != original


def test_edit_requires_valid_strong_revision_precondition(versions):
    client, _, _, _ = versions
    path = create_recipe(client)
    # .request bypasses the compatibility wrapper in the legacy test client.
    assert client.request("PUT", path, json={"title": "No revision"}).status_code == 428
    for value in ('W/"1"', "*", '"0"', "invalid", '"1", "2"'):
        response = client.request(
            "PUT", path, json={"title": "Invalid"}, headers={"If-Match": value}
        )
        assert response.status_code == 400
    assert client.get(path).json()["version"] == 1


def test_comments_do_not_bump_recipe_version_or_cause_conflicts(versions):
    client, _, _, _ = versions
    path = create_recipe(client)
    assert client.post(f"{path}/comments", json={"text": "Lecker!"}).status_code == 201
    assert client.put(f"{path}/ratings", json={"stars": 4}).status_code == 200
    assert client.get(path).json()["version"] == 1
    saved = client.put(path, json={"title": "Neu"}, headers={"If-Match": '"1"'})
    assert saved.status_code == 200
    assert saved.json()["version"] == 2


def test_image_writes_report_recipe_version_before_and_after(versions):
    client, _, _, _ = versions
    path = create_recipe(client)
    upload = client.post(f"{path}/images", files=jpeg("red"))
    assert (upload.headers["x-recipe-version-before"], upload.headers["x-recipe-version"]) == ("1", "2")
    link = f"/api/recipe-images/{upload.json()['id']}"
    alt = client.put(link, json={"alt_text": "Kuchen"})
    assert (alt.headers["x-recipe-version-before"], alt.headers["x-recipe-version"]) == ("2", "3")
    deleted = client.delete(link)
    assert (deleted.headers["x-recipe-version-before"], deleted.headers["x-recipe-version"]) == ("3", "4")


def test_own_image_change_returns_current_version_for_following_save(versions):
    client, _, _, _ = versions
    path = create_recipe(client)
    assert client.post(f"{path}/images", files=jpeg("red")).status_code == 201
    current = client.get(path)
    assert current.json()["version"] == 2
    saved = client.put(path, json={"title": "Neu"}, headers={"If-Match": current.headers["etag"]})
    assert saved.status_code == 200


@pytest.mark.parametrize("mutation", ["upload", "alt", "main", "crop", "delete", "reorder"])
@pytest.mark.parametrize("precondition", ["missing", "malformed", "stale", "current", "deleted"])
def test_image_mutations_require_current_recipe_version(versions, mutation, precondition):
    client, _, _, directory = versions
    path = create_recipe(client)
    first = client.post(f"{path}/images", files=jpeg("red")).json()
    second = client.post(f"{path}/images", files=jpeg("blue")).json()
    before = client.get(path).json()
    files = {file: file.read_bytes() for file in directory.glob("*/*") if file.is_file()}
    link = f"/api/recipe-images/{first['id']}"
    requests = {
        "upload": ("POST", f"{path}/images", {"files": jpeg("green")}),
        "alt": ("PUT", link, {"json": {"alt_text": "stale alt"}}),
        "main": ("PUT", f"/api/recipe-images/{second['id']}", {"json": {"is_main": True}}),
        "crop": ("PUT", f"{link}/crop", {"files": jpeg("green")}),
        "delete": ("DELETE", link, {}),
        "reorder": ("PUT", f"{path}/images/order", {"json": {"image_ids": [second['id'], first['id']]}}),
    }
    method, url, kwargs = requests[mutation]
    if precondition == "deleted":
        assert client.delete(path).status_code == 204
        files = {file: file.read_bytes() for file in directory.glob("*/*") if file.is_file()}
    value = {"stale": '"1"', "malformed": "3"}.get(precondition, f'"{before["version"]}"')
    headers = {} if precondition == "missing" else {"If-Match": value}
    response = client.request(method, url, headers=headers, **kwargs)
    if precondition == "current":
        assert response.status_code == {"upload": 201, "delete": 204}.get(mutation, 200)
        assert response.headers["x-recipe-version-before"] == str(before["version"])
        assert response.headers["x-recipe-version"] == str(before["version"] + 1)
        assert client.get(path).json()["version"] == before["version"] + 1
        return
    assert response.status_code == {"missing": 428, "malformed": 400, "stale": 409, "deleted": 404}[precondition]
    detail = response.json()["detail"]
    if precondition == "stale":
        assert detail["code"] == "recipe_version_conflict"
        assert detail["expected_version"] == 1
        assert detail["current_version"] == before["version"]
        assert "current" in detail
    elif precondition != "deleted":
        assert detail == {"missing": "If-Match header required.", "malformed": "Invalid recipe If-Match header."}[precondition]
    if precondition == "deleted":
        assert client.get(path).status_code == 404
    else:
        assert client.get(path).json() == before
    assert {file: file.read_bytes() for file in directory.glob("*/*") if file.is_file()} == files



@pytest.mark.parametrize(("operation", "change"), [
    ("upload", "version"), ("crop", "version"),
    ("upload", "delete"), ("crop", "delete"), ("upload", "limit"),
])
def test_image_processing_precedes_write_lock_and_rechecks_preconditions(versions, monkeypatch, operation, change):
    client, _, _, directory = versions
    path = create_recipe(client)
    original = client.post(f"{path}/images", files=jpeg("red")).json()
    version = client.get(path).json()["version"]
    prepare = recipe_image_service._prepare_upload
    processed = False
    after_change = None
    files_after_change = None

    def prepare_with_concurrent_change(image, **kwargs):
        nonlocal processed, after_change, files_after_change
        result = prepare(image, **kwargs)
        # Another request must be able to commit during Pillow processing.
        # The former order would hit SQLite's write timeout here.
        if change == "limit":
            # Keep the version unchanged to check the limit independently.
            monkeypatch.setattr(recipe_image_service, "MAX_RECIPE_IMAGES", 1)
        elif change == "delete":
            url = path if operation == "upload" else f"/api/recipe-images/{original['id']}"
            assert client.delete(url).status_code == 204
        else:
            assert client.put(path, json={"title": "Concurrent edit"}).status_code == 200
        after_change = client.get(path)
        files_after_change = {file: file.read_bytes() for file in directory.glob("*/*") if file.is_file()}
        processed = True
        return result

    monkeypatch.setattr(recipe_image_service, "_prepare_upload", prepare_with_concurrent_change)
    url = f"{path}/images" if operation == "upload" else f"/api/recipe-images/{original['id']}/crop"
    response = client.request("POST" if operation == "upload" else "PUT", url,
                              files=jpeg("green"), headers={"If-Match": f'"{version}"'})
    assert processed
    assert response.status_code == (404 if change == "delete" else 409)
    current = client.get(path)
    assert current.status_code == after_change.status_code
    assert current.json() == after_change.json()
    assert {file: file.read_bytes() for file in directory.glob("*/*") if file.is_file()} == files_after_change
    assert not list(directory.glob("*/.*.pending"))


def test_history_routes_and_setting_are_removed(versions):
    client, _, actor, _ = versions
    path = create_recipe(client)
    actor.id = 1
    assert client.get(f"{path}/versions").status_code == 404
    assert client.get(f"{path}/versions/1/images/0").status_code == 404
    assert client.post(f"{path}/versions/1/restore", json={}).status_code == 404
    key = "show_recipe_version_history"
    assert key not in client.get("/api/settings").json()
    assert client.put("/api/settings", json={key: True}).status_code == 422
