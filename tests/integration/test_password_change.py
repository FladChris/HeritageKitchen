import pytest
from fastapi.testclient import TestClient

from app.api.app import app
from app.core import rate_limit
from app.core.config import settings


@pytest.fixture(autouse=True)
def allow_password_flow_logins():
    previous_limit = settings.login_rate_limit_max_attempts
    rate_limit._attempts_by_ip.clear()
    object.__setattr__(settings, "login_rate_limit_max_attempts", 100)
    try:
        yield
    finally:
        object.__setattr__(settings, "login_rate_limit_max_attempts", previous_limit)
        rate_limit._attempts_by_ip.clear()


def test_password_change_preserves_current_session_and_revokes_other_sessions(client):
    credentials = {"username": "chefmax", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200

    other_client = TestClient(app)
    assert other_client.post("/api/auth/login", json=credentials).status_code == 200
    assert other_client.get("/api/auth/me").status_code == 200

    response = client.post("/api/auth/password", json={
        "current_password": "supersecret123",
        "new_password": "different-secret123",
    })
    assert response.status_code == 204
    assert client.get("/api/auth/me").status_code == 200
    assert other_client.get("/api/auth/me").status_code == 401

    login_client = TestClient(app)
    assert login_client.post("/api/auth/login", json=credentials).status_code == 401
    assert login_client.post("/api/auth/login", json={
        "username": "chefmax", "password": "different-secret123",
    }).status_code == 200


def test_password_change_rejects_wrong_current_password_without_changing_it(client):
    credentials = {"username": "chefmax", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    response = client.post("/api/auth/password", json={
        "current_password": "wrong-password", "new_password": "different-secret123",
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Current password is incorrect."
    assert TestClient(app).post("/api/auth/login", json=credentials).status_code == 200


def test_password_change_rejects_short_and_same_password(client):
    credentials = {"username": "chefmax", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    assert client.post("/api/auth/password", json={
        "current_password": "supersecret123", "new_password": "short",
    }).status_code == 422
    response = client.post("/api/auth/password", json={
        "current_password": "supersecret123", "new_password": "supersecret123",
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "New password must differ from current password."


def test_password_change_requires_authentication(client):
    response = client.post("/api/auth/password", json={
        "current_password": "supersecret123", "new_password": "different-secret123",
    })
    assert response.status_code == 401


def test_password_change_does_not_overwrite_a_concurrent_password_reset(client, monkeypatch):
    from sqlalchemy import delete, update

    from app.core import db
    from app.core.security import hash_password
    from app.models.session_model import UserSession
    from app.models.user_model import User
    from app.services import auth_service

    credentials = {"username": "chefmax", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200

    original_hash = auth_service.hash_password

    def reset_while_hashing(password):
        # Simulates an administrator setting a password after the old one was verified.
        with db.engine.begin() as connection:
            connection.execute(
                update(User).where(User.username == "chefmax")
                .values(password_hash=hash_password("admin-set-secret123"))
            )
            connection.execute(delete(UserSession))
        return original_hash(password)

    monkeypatch.setattr(auth_service, "hash_password", reset_while_hashing)
    response = client.post("/api/auth/password", json={
        "current_password": "supersecret123",
        "new_password": "stale-request-secret123",
    })
    assert response.status_code == 401

    login_client = TestClient(app)
    assert login_client.post("/api/auth/login", json={
        "username": "chefmax", "password": "stale-request-secret123",
    }).status_code == 401
    assert login_client.post("/api/auth/login", json={
        "username": "chefmax", "password": "admin-set-secret123",
    }).status_code == 200
