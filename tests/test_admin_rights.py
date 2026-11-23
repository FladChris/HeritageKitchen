from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.api.routes import (
    auth_route,
    category_route,
    recipe_route,
    settings_route,
    user_route,
)
from app.core import rate_limit
from app.core.config import settings
from app.core.db import get_db
from app.core.security import hash_password
from app.models import Base, User, UserRole
from app.models.favorite_model import Favorite
from app.models.recipe_model import Recipe
from app.services import auth_service
from app.services.auth_service import create_user_session

PASSWORD = "supersecret123"


@pytest.fixture
def client_for(tmp_path, monkeypatch):
    monkeypatch.setattr(rate_limit, "_attempts_by_ip", defaultdict(list))
    engine = create_engine(f"sqlite:///{(tmp_path / 'rights.db').as_posix()}")
    Base.metadata.create_all(engine)
    password_hash = hash_password(PASSWORD)
    app = FastAPI()
    for routes in (
        auth_route,
        category_route,
        recipe_route,
        settings_route,
        user_route,
    ):
        app.include_router(routes.router)

    def get_test_db():
        with Session(engine) as session:
            yield session

    def make_client(role=None, *, username=None, active=True):
        client = TestClient(app)
        if role is None:
            return client, None
        with Session(engine) as session:
            user = User(
                username=username or role.value,
                password_hash=password_hash,
                role=role,
                is_active=active,
            )
            session.add(user)
            session.flush()
            user_id = user.id
            token = create_user_session(db_session=session, user_id=user_id)
            client.cookies.set(settings.session_cookie_name, token)
        return client, user_id

    app.dependency_overrides[get_db] = get_test_db
    try:
        yield make_client, engine
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("role", "status"), [(None, 401), (UserRole.READER, 403), (UserRole.EDITOR, 403)]
)
def test_category_management_requires_admin(client_for, role, status):
    make_client, _ = client_for
    client, _ = make_client(role)

    for method, path, payload in [
        ("POST", "/categories", {"json": {"name": "Kuchen"}}),
        ("PUT", "/categories/1", {"json": {"name": "Desserts"}}),
        ("DELETE", "/categories/1", {}),
        (
            "POST",
            "/categories/1/image",
            {"files": {"image": ("cake.png", b"image", "image/png")}},
        ),
        ("DELETE", "/categories/1/image", {}),
    ]:
        assert client.request(method, path, **payload).status_code == status


@pytest.mark.parametrize(
    ("role", "status"), [(None, 401), (UserRole.READER, 403), (UserRole.EDITOR, 403)]
)
def test_user_management_and_cookbook_settings_require_admin(client_for, role, status):
    make_client, _ = client_for
    client, _ = make_client(role)

    for method, path, payload in [
        ("GET", "/users", {}),
        ("GET", "/users/1", {}),
        ("POST", "/users", {"json": {"username": "tim", "password": PASSWORD}}),
        ("PUT", "/users/1", {"json": {"role": "admin"}}),
        ("DELETE", "/users/1", {}),
        ("DELETE", "/users/1/registration", {}),
        ("PUT", "/settings", {"json": {"cookbook_name": "Familienkochbuch"}}),
        ("GET", "/settings/database", {}),
    ]:
        assert client.request(method, path, **payload).status_code == status


def test_registration_status_changes_after_bootstrap(client_for):
    make_client, _ = client_for
    visitor, _ = make_client()

    def assert_status(first_account):
        response = visitor.get("/auth/registration-status")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {"first_account": first_account}

    assert_status(True)
    response = visitor.post("/auth/register", json={
        "username": "petra", "password": PASSWORD,
    })
    assert response.status_code == 201
    user = response.json()
    assert user["email"] is None
    assert (user["role"], user["is_active"], user["pending_approval"]) == ("admin", True, False)
    assert_status(False)


def test_admin_can_reject_pending_registration_and_free_its_credentials(client_for):
    make_client, _ = client_for
    admin, _ = make_client(UserRole.ADMIN)
    visitor, _ = make_client()
    credentials = {"username": "tim", "password": PASSWORD}
    response = visitor.post("/auth/register", json=credentials)
    assert response.status_code == 201
    user_path = f"/users/{response.json()['id']}"
    rejection_path = f"{user_path}/registration"

    assert admin.delete(rejection_path).status_code == 204
    assert admin.get(user_path).status_code == 404
    assert admin.delete(rejection_path).status_code == 404
    assert visitor.post("/auth/login", json=credentials).status_code == 401
    assert settings.session_cookie_name not in visitor.cookies

    response = visitor.post("/auth/register", json=credentials)
    assert response.status_code == 201
    assert response.json()["pending_approval"] is True


@pytest.mark.parametrize("active", [True, False])
def test_admin_cannot_reject_a_regular_account(client_for, active):
    make_client, _ = client_for
    admin, _ = make_client(UserRole.ADMIN)
    _, user_id = make_client(UserRole.EDITOR, active=active)

    assert admin.delete(f"/users/{user_id}/registration").status_code == 409
    response = admin.get(f"/users/{user_id}")
    assert response.status_code == 200
    assert response.json()["is_active"] is active


def test_editor_can_move_recipe_and_admin_can_delete_emptied_category(client_for):
    make_client, _ = client_for
    admin, _ = make_client(UserRole.ADMIN)
    editor, _ = make_client(UserRole.EDITOR)
    reader, _ = make_client(UserRole.READER)

    def add_category(name):
        response = admin.post("/categories", json={"name": name})
        assert response.status_code == 201
        assert response.json()["recipe_count"] == 0
        return response.json()["id"]

    original = add_category("Kuchen")
    target = add_category("Desserts")
    assert (
        admin.put(f"/categories/{target}", json={"name": "Nachtisch"}).status_code
        == 200
    )
    payload = {"title": "Apfelkuchen", "category_id": original}
    assert reader.post("/recipes", json=payload).status_code == 403
    created = editor.post("/recipes", json=payload)
    assert created.status_code == 201
    recipe_id = created.json()["id"]
    assert (
        reader.put(f"/recipes/{recipe_id}", json={"category_id": target}).status_code
        == 403
    )

    refused = admin.delete(f"/categories/{original}")
    assert refused.status_code == 409
    assert (
        refused.json()["detail"]
        == "Category still has recipes assigned and cannot be deleted."
    )
    assert (
        editor.put(f"/recipes/{recipe_id}", json={"category_id": target}).status_code
        == 200
    )
    assert (
        reader.get("/recipes", params={"category_id": original}).json()["items"] == []
    )
    items = reader.get("/recipes", params={"category_id": target}).json()["items"]
    assert [recipe["id"] for recipe in items] == [recipe_id]
    assert {c["id"]: c["recipe_count"] for c in reader.get("/categories").json()} == {
        original: 0,
        target: 1,
    }
    assert admin.delete(f"/categories/{original}").status_code == 204


def test_category_cannot_be_deleted_during_recipe_creation(client_for):
    make_client, engine = client_for
    admin, _ = make_client(UserRole.ADMIN)
    editor, _ = make_client(UserRole.EDITOR)
    category_id = admin.post("/categories", json={"name": "Kuchen"}).json()["id"]
    recipe_insert = Event()
    category_delete = Event()
    resume_insert = Event()

    @event.listens_for(engine, "before_cursor_execute")
    def pause_recipe_insert(_connection, _cursor, statement, *_args):
        if statement.startswith("INSERT INTO recipes "):
            recipe_insert.set()
            assert resume_insert.wait(5)
        elif recipe_insert.is_set() and (
            statement == "BEGIN IMMEDIATE"
            or statement.startswith("DELETE FROM categories ")
        ):
            category_delete.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        creating = pool.submit(
            editor.post,
            "/recipes",
            json={"title": "Apfelkuchen", "category_id": category_id},
        )
        try:
            assert recipe_insert.wait(5)
            deleting = pool.submit(admin.delete, f"/categories/{category_id}")
            assert category_delete.wait(5)
        finally:
            resume_insert.set()
        assert creating.result().status_code == 201
        assert deleting.result().status_code == 409


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        ("PUT", {"json": {"role": "editor"}}),
        ("PUT", {"json": {"is_active": False}}),
        ("DELETE", {}),
    ],
)
def test_cannot_remove_last_active_admin_even_with_an_inactive_admin(
    client_for, method, payload
):
    make_client, _ = client_for
    admin, admin_id = make_client(UserRole.ADMIN)
    make_client(UserRole.ADMIN, username="inactive", active=False)

    response = admin.request(method, f"/users/{admin_id}", **payload)
    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "At least one administrator account must remain active."
    )
    assert admin.get("/auth/me").json()["role"] == "admin"
    assert admin.get("/users").status_code == 200


def test_admin_can_assign_admin_role_then_give_up_own_rights(client_for):
    make_client, _ = client_for
    admin, admin_id = make_client(UserRole.ADMIN)
    editor, editor_id = make_client(UserRole.EDITOR)
    response = admin.post(
        "/users",
        json={
            "username": "tim",
            "password": PASSWORD,
            "role": "reader",
        },
    )
    assert response.status_code == 201
    users = {user["username"]: user for user in admin.get("/users").json()}
    assert users["tim"]["email_verified_at"] is None
    assert users["tim"]["email"] is None
    assert users["tim"]["role"] == "reader"

    assert admin.put(f"/users/{editor_id}", json={"role": "admin"}).status_code == 200
    assert editor.get("/users").status_code == 200
    assert admin.put(f"/users/{admin_id}", json={"role": "editor"}).status_code == 200
    assert admin.get("/auth/me").json()["role"] == "editor"
    assert admin.get("/users").status_code == 403
    assert admin.post("/categories", json={"name": "Kuchen"}).status_code == 403


def test_concurrent_admin_removals_leave_one_active_admin(client_for):
    make_client, engine = client_for
    first, first_id = make_client(UserRole.ADMIN)
    second, second_id = make_client(UserRole.ADMIN, username="second")
    barrier = Barrier(2, timeout=5)

    def demote():
        barrier.wait()
        return first.put(f"/users/{first_id}", json={"role": "editor"})

    def deactivate():
        barrier.wait()
        return second.put(f"/users/{second_id}", json={"is_active": False})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(demote), pool.submit(deactivate)]
        assert sorted(result.result().status_code for result in results) == [200, 409]
    with Session(engine) as session:
        assert (
            len(
                session.scalars(
                    select(User).where(User.role == UserRole.ADMIN, User.is_active)
                ).all()
            )
            == 1
        )


def test_deactivation_revokes_all_sessions_even_after_reactivation(client_for):
    make_client, _ = client_for
    admin, _ = make_client(UserRole.ADMIN)
    reader, reader_id = make_client(UserRole.READER)
    second_device, _ = make_client()
    credentials = {"username": "reader", "password": PASSWORD}
    assert second_device.post("/auth/login", json=credentials).status_code == 200

    assert (
        admin.put(f"/users/{reader_id}", json={"is_active": False}).status_code == 200
    )
    assert reader.get("/auth/me").status_code == 401
    assert reader.post("/auth/login", json=credentials).status_code == 401
    assert admin.put(f"/users/{reader_id}", json={"is_active": True}).status_code == 200
    assert second_device.get("/auth/me").status_code == 401
    assert reader.get("/auth/me").status_code == 401
    assert reader.post("/auth/login", json=credentials).status_code == 200
    assert reader.get("/auth/me").status_code == 200


def test_reactivation_does_not_revive_sessions_left_from_earlier_deactivation(client_for):
    make_client, _ = client_for
    admin, _ = make_client(UserRole.ADMIN)
    stale_device, reader_id = make_client(UserRole.READER, active=False)

    assert admin.put(f"/users/{reader_id}", json={"is_active": True}).status_code == 200
    assert stale_device.get("/auth/me").status_code == 401


@pytest.mark.parametrize("field", ["username", "role", "is_active"])
def test_user_update_rejects_explicit_null(client_for, field):
    make_client, _ = client_for
    admin, _ = make_client(UserRole.ADMIN)
    _, reader_id = make_client(UserRole.READER)

    response = admin.put(f"/users/{reader_id}", json={field: None})

    assert response.status_code == 422


def test_login_cannot_issue_session_if_user_was_deactivated_during_login(
    client_for, monkeypatch
):
    make_client, _ = client_for
    admin, _ = make_client(UserRole.ADMIN)
    _, reader_id = make_client(UserRole.READER)
    signed_out, _ = make_client()
    verify_password = auth_service.verify_password

    def deactivate_during_verification(password, password_hash):
        verified = verify_password(password, password_hash)
        assert (
            admin.put(f"/users/{reader_id}", json={"is_active": False}).status_code
            == 200
        )
        return verified

    monkeypatch.setattr(auth_service, "verify_password", deactivate_during_verification)
    result = signed_out.post(
        "/auth/login", json={"username": "reader", "password": PASSWORD}
    )
    assert result.status_code == 401
    assert settings.session_cookie_name not in signed_out.cookies


def test_admin_can_delete_another_admin_with_favorites(client_for):
    make_client, engine = client_for
    admin, _ = make_client(UserRole.ADMIN)
    other_admin, other_id = make_client(UserRole.ADMIN, username="other")
    with Session(engine) as session:
        recipe = Recipe(title="Apfelkuchen")
        session.add(recipe)
        session.flush()
        recipe_id = recipe.id
        session.add(Favorite(user_id=other_id, recipe_id=recipe_id))
        session.commit()

    assert admin.delete(f"/users/{other_id}").status_code == 204
    assert admin.get(f"/users/{other_id}").status_code == 404
    assert other_admin.get("/auth/me").status_code == 401
    with Session(engine) as session:
        assert session.get(Recipe, recipe_id) is not None
        assert session.scalar(select(Favorite)) is None
