from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.app import app
from app.core import db, rate_limit
from app.core.config import settings
from app.core.security import hash_session_token
from app.models.password_reset_model import PasswordReset


class MailServer:
    message = None

    def __init__(self, *args, **kwargs):
        pass

    def starttls(self, **kwargs):
        pass

    def close(self):
        pass

    def quit(self):
        pass

    def send_message(self, message):
        MailServer.message = message


def test_reset_link_expiry_once_and_unknown_email(client, monkeypatch):
    monkeypatch.setattr("app.services.smtp_service.smtplib.SMTP", MailServer)
    monkeypatch.setitem(settings.__dict__, "reset_base_url", "https://example.com")
    rate_limit._attempts_by_ip.clear()
    old_limit = settings.login_rate_limit_max_attempts
    object.__setattr__(settings, "login_rate_limit_max_attempts", 100)
    try:
        credentials = {
            "username": "chefmax",
            "email": "chef@example.com",
            "password": "supersecret123",
        }
        assert (
            client.post(
                "/api/auth/register",
                json={"username": credentials["username"], "password": credentials["password"]},
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "username": credentials["username"],
                    "password": credentials["password"],
                },
            ).status_code
            == 200
        )
        second_device = TestClient(app)
        assert second_device.post("/api/auth/login", json={
            "username": credentials["username"],
            "password": credentials["password"],
        }).status_code == 200
        smtp = client.get("/api/settings/smtp")
        assert smtp.status_code == 200
        assert (
            client.put(
                "/api/settings/smtp",
                json={
                    "version": smtp.json()["version"],
                    "host": "mail.example",
                    "port": 587,
                    "encryption": "starttls",
                    "sender": "app@example.com",
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/settings/smtp/test", json={"recipient": "chef@example.com"}
            ).status_code
            == 200
        )
        assert client.patch("/api/auth/me", json={
            "email": credentials["email"], "current_password": credentials["password"],
        }).status_code == 200
        verification_token = parse_qs(
            urlparse(MailServer.message.get_content().split()[-1]).query
        )["token"][0]
        assert client.post(
            "/api/auth/verify-email", json={"token": verification_token}
        ).status_code == 204
        MailServer.message = None
        known = client.post(
            "/api/auth/reset-request", json={"email": "chef@example.com"}
        )
        unknown = client.post(
            "/api/auth/reset-request", json={"email": "nobody@example.com"}
        )
        assert known.status_code == unknown.status_code == 204
        token = parse_qs(urlparse(MailServer.message.get_content().split()[-1]).query)[
            "token"
        ][0]
        assert client.post(
            "/api/auth/reset-request", json={"email": "chef@example.com"}
        ).status_code == 204
        newer_token = parse_qs(urlparse(MailServer.message.get_content().split()[-1]).query)[
            "token"
        ][0]
        assert newer_token != token
        assert client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": "newsecret123"},
        ).status_code == 400
        token = newer_token
        query = select(PasswordReset).where(PasswordReset.token_hash == hash_session_token(token))
        with Session(db.engine) as session:
            reset = session.scalar(query)
            assert reset.token_hash != token
            reset.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            session.commit()
        data = {"token": token, "new_password": "newsecret123"}
        assert client.post("/api/auth/reset-password", json=data).status_code == 400
        with Session(db.engine) as session:
            reset = session.scalar(query)
            reset.expires_at = datetime.now(UTC) + timedelta(hours=1)
            session.commit()
        assert client.post("/api/auth/reset-password", json=data).status_code == 204
        assert client.get("/api/auth/me").status_code == 401
        assert second_device.get("/api/auth/me").status_code == 401
        assert client.post("/api/auth/reset-password", json=data).status_code == 400
        assert (
            TestClient(app)
            .post(
                "/api/auth/login",
                json={"username": "chefmax", "password": "newsecret123"},
            )
            .status_code
            == 200
        )
    finally:
        object.__setattr__(settings, "login_rate_limit_max_attempts", old_limit)
        rate_limit._attempts_by_ip.clear()


def test_admin_password_reset_requires_admin_and_revokes_sessions(client):
    rate_limit._attempts_by_ip.clear()
    assert client.get("/api/auth/reset-available").json() == {"available": False}
    assert (
        client.post(
            "/api/auth/register",
            json={"username": "chefmax", "password": "supersecret123"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "chefmax", "password": "supersecret123"},
        ).status_code
        == 200
    )
    user = client.post(
        "/api/users", json={"username": "guest", "password": "guestsecret123"}
    ).json()
    reset_data = {"token": "previously-issued-token", "new_password": "resetsecret123"}
    with Session(db.engine) as session:
        session.add(PasswordReset(
            user_id=user["id"],
            token_hash=hash_session_token(reset_data["token"]),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ))
        session.commit()
    guest = TestClient(app)
    assert (
        guest.post(
            "/api/auth/login", json={"username": "guest", "password": "guestsecret123"}
        ).status_code
        == 200
    )
    second_device = TestClient(app)
    assert second_device.post("/api/auth/login", json={
        "username": "guest", "password": "guestsecret123",
    }).status_code == 200
    assert (
        guest.put(
            f"/api/users/{user['id']}", json={"password": "anothersecret123"}
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/api/users/{user['id']}", json={"password": "anothersecret123"}
        ).status_code
        == 200
    )
    assert guest.get("/api/auth/me").status_code == 401
    assert second_device.get("/api/auth/me").status_code == 401
    assert guest.post("/api/auth/reset-password", json=reset_data).status_code == 400
    assert guest.post("/api/auth/login", json={
        "username": "guest", "password": "anothersecret123",
    }).status_code == 200
    rate_limit._attempts_by_ip.clear()
