from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.app import app
from app.core.config import settings
from app.core.db import create_database_engine, get_db
from app.core.security import hash_session_token
from app.models import Base, Favorite, Recipe, User, UserRole, UserSession

PATH = "/api/favorites"


@pytest.fixture
def favorites(tmp_path, monkeypatch):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'favorites.db'}")
    Base.metadata.create_all(engine)

    def test_db():
        with Session(engine) as db:
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, test_db)
    with Session(engine) as db:
        db.add_all(
            User(id=user_id, username=role.value, role=role, password_hash="hash")
            for user_id, role in enumerate(UserRole, start=1)
        )
        db.add_all(
            [
                Recipe(id=1, title="Zitronenkuchen"),
                Recipe(id=2, title="Apfelkuchen", created_at=datetime(2024, 1, 1)),
                Recipe(id=3, title="Apfelkuchen", created_at=datetime(2023, 1, 1)),
                Recipe(id=4, title="Apfelkuchen", created_at=datetime(2024, 1, 1)),
                Recipe(id=5, title="Brot"),
            ]
        )
        db.commit()

    def client(user_id=None):
        result = TestClient(app)
        if user_id is not None:
            token = f"session-{user_id}-{datetime.now(UTC).isoformat()}"
            with Session(engine) as db:
                db.add(
                    UserSession(
                        user_id=user_id,
                        token_hash=hash_session_token(token),
                        expires_at=datetime.now(UTC) + timedelta(days=1),
                    )
                )
                db.commit()
            result.cookies.set(settings.session_cookie_name, token)
        return result

    try:
        yield client, engine
    finally:
        engine.dispose()


def add(client, recipe_id):
    response = client.post(PATH, json={"recipe_id": recipe_id})
    assert response.status_code == 201, response.text
    return response.json()


def recipes(client, sort=None):
    response = client.get(PATH, params={"sort": sort} if sort else None)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return [favorite["recipe_id"] for favorite in response.json()]


def test_recent_and_alphabetical_sort_use_favorite_time_and_stable_recipe_ties(
    favorites,
):
    client, engine = favorites
    reader = client(1)
    with Session(engine) as db:
        db.add_all(
            [
                Favorite(id=11, user_id=1, recipe_id=2),
                Favorite(id=12, user_id=1, recipe_id=1),
            ]
        )
        db.commit()

    before = datetime.now(UTC)
    first = add(reader, 4)
    second = add(reader, 3)
    assert (
        before
        <= datetime.fromisoformat(first["created_at"])
        <= datetime.fromisoformat(second["created_at"])
        <= datetime.now(UTC)
    )
    assert recipes(reader) == [3, 4, 1, 2]
    assert [row["created_at"] for row in reader.get(PATH).json()[2:]] == [None, None]
    assert recipes(reader, "name") == [3, 2, 4, 1]
    assert recipes(reader, "manual") == [2, 1, 4, 3]

    with Session(engine) as db:
        db.get(Favorite, second["id"]).created_at = before - timedelta(days=1)
        db.commit()
    assert recipes(reader) == [4, 3, 1, 2]


def test_personal_order_and_preferences_are_account_scoped_and_new_entries_append(
    favorites,
):
    client, _ = favorites
    reader, editor, admin, guest = [client(user_id) for user_id in (1, 2, 3, None)]
    for method, path, payload in [
        ("GET", PATH, {}),
        ("POST", PATH, {"recipe_id": 1}),
        ("GET", f"{PATH}/preferences", {}),
        ("PATCH", f"{PATH}/preferences", {"sort": "name"}),
        ("PUT", f"{PATH}/order", {"favorite_ids": []}),
    ]:
        assert guest.request(method, path, json=payload).status_code == 401

    a, b, c = [add(reader, recipe_id) for recipe_id in (1, 2, 3)]
    other = add(editor, 2)
    assert add(admin, 2)["user_id"] == 3
    payload = {"favorite_ids": [c["id"], a["id"], b["id"]]}
    assert reader.get(f"{PATH}/{other['id']}").status_code == 404
    assert reader.delete(f"{PATH}/{other['id']}").status_code == 404
    assert editor.put(f"{PATH}/order", json=payload).status_code == 409
    duplicate_ids = {"favorite_ids": [a["id"], a["id"], b["id"], c["id"]]}
    assert reader.put(f"{PATH}/order", json=duplicate_ids).status_code == 422
    assert reader.put(f"{PATH}/order", json=payload).status_code == 200
    assert (
        reader.patch(
            f"{PATH}/preferences", json={"sort": "manual", "recipe_view": "grid"}
        ).status_code
        == 204
    )
    assert recipes(reader) == [3, 1, 2]
    assert recipes(editor) == [2]
    assert editor.get(f"{PATH}/preferences").json() == {
        "sort": "recent",
        "recipe_view": "list",
    }

    reader = client(1)
    assert reader.get(f"{PATH}/preferences").json() == {
        "sort": "manual",
        "recipe_view": "grid",
    }
    assert reader.get("/api/users/1/view-preferences").json()["recipe_view"] == "grid"
    add(reader, 4)
    assert reader.put(f"{PATH}/order", json=payload).status_code == 409
    assert recipes(reader) == [3, 1, 2, 4]
    assert reader.delete(f"{PATH}/{a['id']}").status_code == 204
    assert add(reader, 1)["recipe_id"] == 1
    assert recipes(reader) == [3, 2, 4, 1]
    assert recipes(reader, "recent") == [1, 4, 3, 2]


def test_recipe_and_account_deletion_clean_up_but_deactivation_keeps_favorites(
    favorites,
):
    client, engine = favorites
    reader, editor, admin = [client(user_id) for user_id in (1, 2, 3)]
    add(reader, 1)
    add(reader, 2)
    add(editor, 1)
    add(editor, 2)

    assert admin.delete("/api/recipes/1").status_code == 204
    assert recipes(reader) == recipes(editor) == [2]

    assert admin.put("/api/users/1", json={"is_active": False}).status_code == 200
    assert reader.get(PATH).status_code == 401
    assert admin.put("/api/users/1", json={"is_active": True}).status_code == 200
    assert reader.get(PATH).status_code == 401
    assert recipes(client(1)) == [2]

    assert admin.delete("/api/users/1").status_code == 204
    assert recipes(editor) == [2]
    with Session(engine) as db:
        assert db.scalars(select(Favorite.user_id)).all() == [2]
        assert db.get(Recipe, 2) is not None


def test_favorite_list_has_no_fixed_limit(favorites):
    client, engine = favorites
    with Session(engine) as db:
        db.add_all([Recipe(id=id_, title=f"Rezept {id_}") for id_ in range(10, 210)])
        db.flush()
        db.add_all([Favorite(user_id=1, recipe_id=id_) for id_ in range(10, 210)])
        db.commit()
    reader = client(1)
    add(reader, 1)
    result = recipes(reader)
    assert len(result) == 201
    assert result[0] == 1
    assert result[1:] == list(range(209, 9, -1))


def test_favorite_requests_reject_a_changed_session_in_another_tab(favorites):
    client, _ = favorites
    stale_tab, other_account = client(1), client(2)
    add(stale_tab, 1)
    first, second = [add(other_account, recipe_id) for recipe_id in (4, 5)]
    prior_account = {"expected_user_id": 1}
    stale_tab.cookies.set(
        settings.session_cookie_name,
        other_account.cookies.get(settings.session_cookie_name),
    )

    for method, suffix, payload in [
        ("GET", "", None),
        ("POST", "", {"recipe_id": 3}),
        ("GET", f"/{first['id']}", None),
        ("DELETE", f"/{first['id']}", None),
        ("GET", "/preferences", None),
        ("PATCH", "/preferences", {"sort": "name", "recipe_view": "grid"}),
        ("PUT", "/order", {"favorite_ids": [second["id"], first["id"]]}),
    ]:
        response = stale_tab.request(
            method, PATH + suffix, params=prior_account, json=payload
        )
        assert response.status_code == 403

    assert recipes(other_account, "manual") == [4, 5]
    assert other_account.get(f"{PATH}/preferences").json() == {
        "sort": "recent",
        "recipe_view": "list",
    }
    current = stale_tab.get(PATH, params={"expected_user_id": 2})
    assert [row["recipe_id"] for row in current.json()] == [5, 4]
