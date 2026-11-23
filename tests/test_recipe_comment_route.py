from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.app import app
from app.core.config import settings
from app.core.db import get_db
from app.models import Base, Recipe, RecipeComment, User, UserRole
from app.services.auth_service import create_user_session
from app.services.user_service import delete_user

COMMENTS = "/api/recipes/1/comments"


@pytest.fixture
def cookbook(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'comments.db').as_posix()}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        "app.services.recipe_image_storage.settings",
        replace(settings, recipe_images_dir=str(tmp_path)),
    )

    def get_test_db():
        with Session(engine) as session:
            yield session

    monkeypatch.setitem(app.dependency_overrides, get_db, get_test_db)
    clients = {"guest": TestClient(app)}
    with Session(engine) as session:
        session.add_all([Recipe(id=1, title="Apfelkuchen"), Recipe(id=2, title="Brot")])
        for name, role in [
            ("Tim", UserRole.READER),
            ("Lena", UserRole.EDITOR),
            ("Petra", UserRole.ADMIN),
            ("inactive", UserRole.READER),
        ]:
            user = User(
                username=name, password_hash="unused", role=role, is_active=name != "inactive"
            )
            session.add(user)
            session.flush()
            token = create_user_session(db_session=session, user_id=user.id)
            client = TestClient(app)
            client.cookies.set(settings.session_cookie_name, token)
            clients[name] = client
    try:
        yield clients, engine
    finally:
        for client in clients.values():
            client.close()
        engine.dispose()


def test_comments_are_public_chronological_and_keep_creation_time_on_edit(cookbook):
    clients, _ = cookbook
    for name in ("Tim", "Lena", "Petra"):
        response = clients[name].post(COMMENTS, json={"text": f"Beitrag von {name}"})
        assert response.status_code == 201

    response = clients["guest"].get(COMMENTS)
    assert response.headers["Cache-Control"] == "no-store"
    comments = response.json()
    assert [comment["author_username"] for comment in comments] == ["Tim", "Lena", "Petra"]
    first, *rest = comments
    assert datetime.fromisoformat(first["created_at"]).tzinfo == UTC
    assert first["edited_at"] is None
    path = f"{COMMENTS}/{first['id']}"
    response = clients["Tim"].put(path, json={"text": "Weniger Zucker."})
    assert response.status_code == 200
    edited = response.json()
    assert edited["text"] == "Weniger Zucker."
    assert edited["created_at"] == first["created_at"]
    assert edited["edited_at"] is not None
    assert edited["author_username"] == "Tim"
    assert clients["guest"].get(COMMENTS).json() == [edited, *rest]


@pytest.mark.parametrize("text", ["", " \t\n\u2003"])
def test_blank_comments_cannot_be_created_or_saved(cookbook, text):
    clients, _ = cookbook
    tim = clients["Tim"]
    assert tim.post(COMMENTS, json={"text": text}).status_code == 422
    comment = tim.post(COMMENTS, json={"text": "Gültig"}).json()
    response = tim.put(f"{COMMENTS}/{comment['id']}", json={"text": text})
    assert response.status_code == 422
    assert tim.get(COMMENTS).json() == [comment]


def test_comment_writes_require_authorship_except_admin_delete(cookbook):
    clients, _ = cookbook
    for name in ("guest", "inactive"):
        assert clients[name].post(COMMENTS, json={"text": "Test"}).status_code == 401
    tim = clients["Tim"]
    comment = tim.post(COMMENTS, json={"text": "Test"}).json()
    path = f"{COMMENTS}/{comment['id']}"
    guest = clients["guest"]
    assert guest.put(path, json={"text": "Test"}).status_code == 401
    assert guest.delete(path).status_code == 401
    for name in ("Lena", "Petra"):
        assert clients[name].put(path, json={"text": "Fremde Änderung"}).status_code == 403
    assert clients["Lena"].delete(path).status_code == 403
    assert tim.delete(f"/api/recipes/2/comments/{comment['id']}").status_code == 404
    assert tim.put(
        f"/api/recipes/2/comments/{comment['id']}", json={"text": "Test"}
    ).status_code == 404
    assert clients["Petra"].delete(path).status_code == 204
    own = tim.post(COMMENTS, json={"text": "Noch ein Kommentar"}).json()
    assert tim.delete(f"{COMMENTS}/{own['id']}").status_code == 204
    assert guest.get(COMMENTS).json() == []
    assert guest.get("/api/recipes/999/comments").status_code == 404
    assert tim.post("/api/recipes/999/comments", json={"text": "Test"}).status_code == 404


def test_comment_mutations_do_not_touch_recipe_and_deletions_preserve_associations(cookbook):
    clients, engine = cookbook
    tim = clients["Tim"]
    before = tim.get("/api/recipes/1").json()
    comment = tim.post(COMMENTS, json={"text": "Test"}).json()
    path = f"{COMMENTS}/{comment['id']}"
    assert tim.put(path, json={"text": "Überarbeitet"}).status_code == 200
    transient = tim.post(COMMENTS, json={"text": "Vorübergehend"}).json()
    assert tim.delete(f"{COMMENTS}/{transient['id']}").status_code == 204
    assert tim.get("/api/recipes/1").json() == before
    assert tim.post("/api/recipes/2/comments", json={"text": "Zum Brot"}).status_code == 201

    with Session(engine) as session:
        delete_user(db_session=session, user_id=comment["author_id"])
    (retained,) = clients["guest"].get(COMMENTS).json()
    assert retained["text"] == "Überarbeitet"
    assert retained["author_id"] is None
    assert retained["author_username"] is None
    assert clients["Lena"].delete("/api/recipes/1").status_code == 204
    with Session(engine) as session:
        assert session.scalars(select(RecipeComment.recipe_id)).all() == [2]
