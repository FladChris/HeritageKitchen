from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.app import app
from app.core.config import settings
from app.core.db import create_database_engine, get_db
from app.core.security import hash_session_token
from app.models import Base, Recipe, User, UserRole, UserSession
from app.services import recipe_image_storage


@pytest.fixture
def ratings(tmp_path, monkeypatch):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'ratings.db'}")
    Base.metadata.create_all(engine)
    image_settings = replace(settings, recipe_images_dir=str(tmp_path))
    monkeypatch.setattr(recipe_image_storage, "settings", image_settings)

    with Session(engine) as db:
        db.add(Recipe(id=1, title="Apfelkuchen"))
        for user_id, role in enumerate(UserRole, start=1):
            db.add(
                User(id=user_id, username=role.value, password_hash="hash", role=role)
            )
        db.flush()
        for user_id in range(1, 4):
            db.add(
                UserSession(
                    user_id=user_id,
                    token_hash=hash_session_token(str(user_id)),
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
        db.commit()

    def test_db():
        with Session(engine) as db:
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, test_db)
    try:
        yield TestClient(app), engine
    finally:
        engine.dispose()


PATH = "/api/recipes/1/ratings"
EMPTY = {"average": None, "count": 0, "ratings": []}


def login(client, user_id):
    client.cookies.set(settings.session_cookie_name, str(user_id))


def test_rounding_replacement_and_own_removal_leave_recipe_content_unchanged(ratings):
    client, _ = ratings
    recipe = client.get("/api/recipes/1").json()
    assert client.get(PATH).json() == EMPTY
    assert client.put(PATH, json={"stars": 4.5}).status_code == 401
    assert client.delete(PATH).status_code == 401

    login(client, 1)
    assert client.put(PATH, json={"stars": 4.5}).json()["average"] == 4.5
    login(client, 2)
    assert client.put(PATH, json={"stars": 5}).json() == {
        "average": 5.0,
        "count": 2,
        "ratings": [
            {"username": "editor", "stars": 5},
            {"username": "reader", "stars": 4.5},
        ],
    }
    login(client, 3)
    assert client.delete(PATH).json()["count"] == 2
    assert client.put(PATH, json={"stars": 1.0}).json()["count"] == 3
    assert client.delete(PATH).json()["count"] == 2

    login(client, 1)
    updated = client.put(PATH, json={"stars": 4}).json()
    assert updated["average"] == 4.5
    assert updated["count"] == 2
    login(client, 2)
    assert client.delete(PATH).json() == {
        "average": 4.0,
        "count": 1,
        "ratings": [{"username": "reader", "stars": 4}],
    }
    client.cookies.clear()
    assert client.get(PATH).json()["count"] == 1
    assert client.get("/api/recipes/1").json() == recipe

    login(client, 1)
    assert client.delete(PATH).json() == EMPTY


@pytest.mark.parametrize("stars", [0.5, 5.5, 4.2, True, "4.5"])
def test_invalid_ratings_are_rejected(ratings, stars):
    client, _ = ratings
    login(client, 1)
    assert client.put(PATH, json={"stars": stars}).status_code == 422
    assert client.get(PATH).json() == EMPTY


def test_missing_recipe_returns_not_found(ratings):
    client, _ = ratings
    login(client, 1)
    path = "/api/recipes/99/ratings"
    assert client.get(path).status_code == 404
    assert client.put(path, json={"stars": 4}).status_code == 404
    assert client.delete(path).status_code == 404


def test_deactivation_preserves_rating_and_deletion_recalculates_summary(ratings):
    client, engine = ratings
    login(client, 1)
    assert client.put(PATH, json={"stars": 3}).status_code == 200
    login(client, 2)
    assert client.put(PATH, json={"stars": 5}).status_code == 200

    with Session(engine) as db:
        db.get(User, 2).is_active = False
        db.commit()
    assert client.put(PATH, json={"stars": 2}).status_code == 401
    assert client.get(PATH).json()["average"] == 4.0
    with Session(engine) as db:
        db.get(User, 2).is_active = True
        db.commit()
    assert client.get(PATH).json()["ratings"][0] == {"username": "editor", "stars": 5}

    with Session(engine) as db:
        db.execute(delete(UserSession).where(UserSession.user_id == 2))
        db.execute(delete(User).where(User.id == 2))
        db.commit()
    assert client.get(PATH).json() == {
        "average": 3.0,
        "count": 1,
        "ratings": [{"username": "reader", "stars": 3}],
    }
    with Session(engine) as db:
        db.execute(delete(UserSession).where(UserSession.user_id == 1))
        db.execute(delete(User).where(User.id == 1))
        db.commit()
    assert client.get(PATH).json() == EMPTY


def test_recipe_delete_cascades_to_ratings(ratings):
    from app.models.recipe_rating_model import RecipeRating

    client, engine = ratings
    login(client, 2)
    assert client.put(PATH, json={"stars": 5}).status_code == 200
    assert client.delete("/api/recipes/1").status_code == 204
    assert client.get(PATH).status_code == 404
    with Session(engine) as db:
        assert db.scalars(select(RecipeRating)).all() == []
