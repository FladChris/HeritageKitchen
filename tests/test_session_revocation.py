from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app import admin_password
from app.api.routes import auth_route, user_route
from app.core.config import settings
from app.core.db import get_db
from app.core.security import hash_password, verify_password
from app.models import Base, PasswordReset, SmtpSettings, User, UserRole, UserSession
from app.services import smtp_service
from app.services.auth_service import create_user_session

PASSWORD = "supersecret123"


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'revocation.db').as_posix()}")
    Base.metadata.create_all(engine)
    monkeypatch.setitem(settings.__dict__, "reset_base_url", "https://cookbook.example.com")
    monkeypatch.setattr(smtp_service, "send_message", lambda *args, **kwargs: True)
    with Session(engine) as db:
        db.add(SmtpSettings(
            id=1, host="mail.example", port=25, encryption="none", username="",
            sender="cookbook@example.com", tested_at=datetime.now(UTC),
        ))
        db.commit()
    app = FastAPI()
    for route in (auth_route, user_route):
        app.include_router(route.router)

    def get_test_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = get_test_db

    def add(username, role=UserRole.READER, email=None):
        with Session(engine) as db:
            user = User(
                username=username,
                email=email,
                email_verified_at=datetime.now(UTC) if email else None,
                password_hash=hash_password(PASSWORD),
                role=role,
            )
            db.add(user)
            db.flush()
            user_id = user.id
            db.add(
                PasswordReset(
                    user_id=user_id,
                    token_hash=f"reset-{username}",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
            token = create_user_session(db_session=db, user_id=user_id)
        client = TestClient(app)
        client.cookies.set(settings.session_cookie_name, token)
        return client, user_id

    try:
        yield engine, add
    finally:
        engine.dispose()


def count(engine, model, user_id):
    with Session(engine) as db:
        return db.scalar(
            select(func.count()).select_from(model).where(model.user_id == user_id)
        )


def test_own_password_change_revokes_reset_links_and_keeps_current_session(env):
    engine, add = env
    client, user_id = add("lena", email="lena@example.com")
    response = client.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": "brand-new-secret1"},
    )
    assert response.status_code == 204
    assert count(engine, PasswordReset, user_id) == 0
    assert count(engine, UserSession, user_id) == 1


def test_failed_password_change_keeps_reset_links(env):
    engine, add = env
    client, user_id = add("lena")
    response = client.post(
        "/auth/password",
        json={"current_password": "wrong-password1", "new_password": "brand-new-secret1"},
    )
    assert response.status_code == 400
    assert count(engine, PasswordReset, user_id) == 1


def test_own_email_change_revokes_reset_links_but_other_edits_do_not(env):
    engine, add = env
    client, user_id = add("lena", email="lena@example.com")
    assert client.patch("/auth/me", json={"username": "Kochlena"}).status_code == 200
    assert count(engine, PasswordReset, user_id) == 1
    assert client.patch("/auth/me", json={"email": "lena@example.com"}).status_code == 200
    assert count(engine, PasswordReset, user_id) == 1
    assert client.patch("/auth/me", json={
        "email": "neu@example.com", "current_password": PASSWORD,
    }).status_code == 200
    assert count(engine, PasswordReset, user_id) == 0


def test_admin_email_change_revokes_reset_links_of_that_account(env):
    engine, add = env
    admin, _ = add("petra", UserRole.ADMIN)
    _, tim_id = add("tim", email="tim@example.com")
    response = admin.put(f"/users/{tim_id}", json={
        "email": "tim2@example.com", "current_password": PASSWORD,
    })
    assert response.status_code == 200
    assert count(engine, PasswordReset, tim_id) == 0


def test_local_command_sets_admin_password_and_revokes_everything(env):
    engine, add = env
    _, admin_id = add("petra", UserRole.ADMIN)
    with Session(engine) as db:
        admin_password.set_admin_password(db, "petra", "recovered-secret1")
    with Session(engine) as db:
        assert verify_password("recovered-secret1", db.get(User, admin_id).password_hash)
    assert count(engine, UserSession, admin_id) == 0
    assert count(engine, PasswordReset, admin_id) == 0


@pytest.mark.parametrize(
    ("username", "password"),
    [("unknown", "recovered-secret1"), ("tim", "recovered-secret1"), ("petra", "short"), ("petra", "          ")],
)
def test_local_command_rejects_unknown_non_admin_and_weak_password(env, username, password):
    engine, add = env
    _, admin_id = add("petra", UserRole.ADMIN)
    add("tim")
    with Session(engine) as db, pytest.raises(admin_password.RecoveryError):
        admin_password.set_admin_password(db, username, password)
    assert count(engine, UserSession, admin_id) == 1


def test_main_prompts_twice_and_rejects_mismatch(env, monkeypatch):
    engine, add = env
    _, admin_id = add("petra", UserRole.ADMIN)
    monkeypatch.setattr(admin_password, "dbSession", lambda: Session(engine))
    answers = iter(["recovered-secret1", "different-secret1"])
    monkeypatch.setattr(admin_password, "getpass", lambda _prompt: next(answers))
    assert admin_password.main(["petra"]) == 1
    assert count(engine, UserSession, admin_id) == 1
    answers = iter(["recovered-secret1", "recovered-secret1"])
    assert admin_password.main(["petra"]) == 0
    assert count(engine, UserSession, admin_id) == 0


def test_local_command_trims_password_so_login_works(env):
    engine, add = env
    _, admin_id = add("petra", UserRole.ADMIN)
    with Session(engine) as db:
        admin_password.set_admin_password(db, "petra", "  recovered-secret1  ")
    with Session(engine) as db:
        assert verify_password("recovered-secret1", db.get(User, admin_id).password_hash)


def test_local_command_refuses_inactive_admin(env):
    engine, add = env
    _, admin_id = add("petra", UserRole.ADMIN)
    with Session(engine) as db:
        db.get(User, admin_id).is_active = False
        db.commit()
    with Session(engine) as db, pytest.raises(admin_password.RecoveryError):
        admin_password.set_admin_password(db, "petra", "recovered-secret1")
    with Session(engine) as db:
        assert verify_password(PASSWORD, db.get(User, admin_id).password_hash)


def test_deactivation_revokes_reset_links(env):
    engine, add = env
    admin, _ = add("petra", UserRole.ADMIN)
    _, tim_id = add("tim", email="tim@example.com")
    assert admin.put(f"/users/{tim_id}", json={"is_active": False}).status_code == 200
    assert count(engine, PasswordReset, tim_id) == 0
