from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_session
from app.api.routes import auth_route
from app.api.schemas.auth_schema import UserLoginRequest
from app.api.schemas.user_schema import UserResponse
from app.core.config import settings
from app.core.db import get_db
from app.models.session_model import UserSession
from app.models.user_model import User, UserRole


def test_session_cookie_defaults_to_httponly():
    assert settings.session_cookie_httponly is True


@pytest.mark.parametrize(
    ("mode", "headers", "secure"),
    [
        ("auto", [], False),
        ("auto", [(b"x-forwarded-proto", b"https")], True),
        ("true", [], True),
        ("false", [(b"x-forwarded-proto", b"https")], False),
    ],
)
def test_login_cookie_secure_mode(mode, headers, secure):
    request = Request({"type": "http", "scheme": "http", "path": "/auth/login", "headers": headers})
    response = Response()
    with (
        patch("app.api.routes.auth_route.auth_service.login_user", return_value=(Mock(), "token")),
        patch("app.api.routes.auth_route.settings", SimpleNamespace(
            session_cookie_secure=mode,
            session_cookie_name="test_session",
            session_cookie_path="/",
            session_cookie_samesite="lax",
            session_cookie_httponly=True,
            session_lifetime_days=7,
        )),
    ):
        auth_route.login_user(
            login_request=UserLoginRequest(username="test", password="password123"),
            request=request,
            response=response,
            db_session=Mock(),
        )
    assert ("Secure" in response.headers["set-cookie"]) is secure


def test_login_user_sets_session_cookie():
    db_session = Mock()
    response = Response()
    login_request = UserLoginRequest(
        username="recipefan",
        password="supersecret123",
    )
    user = UserResponse(
        id=1,
        username="recipefan",
        email="recipefan@example.com",
        role=UserRole.READER,
        is_active=True,
        pending_approval=False,
        created_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
    )

    cookie_settings = SimpleNamespace(
        session_cookie_httponly=False,
        session_cookie_name="test_session",
        session_cookie_path="/api",
        session_cookie_samesite="strict",
        session_cookie_secure="true",
        session_lifetime_days=2,
    )

    with (
        patch(
            "app.api.routes.auth_route.auth_service.login_user",
            return_value=(user, "raw-session-token"),
        ) as login_user_mock,
        patch("app.api.routes.auth_route.settings", cookie_settings),
    ):
        result = auth_route.login_user(
            login_request=login_request,
            request=Request({"type": "http", "scheme": "http", "headers": []}),
            response=response,
            db_session=db_session,
        )

    cookie = response.headers["set-cookie"]
    assert result == user
    assert "test_session=raw-session-token" in cookie
    assert "HttpOnly" not in cookie
    assert "Max-Age=172800" in cookie
    assert "Path=/api" in cookie
    assert "SameSite=strict" in cookie
    assert "Secure" in cookie
    login_user_mock.assert_called_once_with(
        db_session=db_session,
        login_request=login_request,
    )


def test_get_me_returns_current_user():
    current_user = User(
        id=1,
        username="recipefan",
        email="recipefan@example.com",
        password_hash="argon2-hash",
        role=UserRole.READER,
        is_active=True,
        pending_approval=False,
        created_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
    )

    result = auth_route.get_me(current_user=current_user)

    assert isinstance(result, UserResponse)
    assert result.id == 1
    assert result.username == "recipefan"


def test_logout_user_deletes_session_and_cookie():
    db_session = Mock()
    response = Response()
    user_session = UserSession(id=1, user_id=2, token_hash="hashed-session-token")
    cookie_settings = SimpleNamespace(
        session_cookie_httponly=True,
        session_cookie_name="test_session",
        session_cookie_path="/api",
        session_cookie_samesite="strict",
        session_cookie_secure="true",
    )

    with (
        patch("app.api.routes.auth_route.delete_session") as delete_session_mock,
        patch("app.api.routes.auth_route.settings", cookie_settings),
    ):
        result = auth_route.logout_user(
            request=Request({"type": "http", "scheme": "http", "headers": []}),
            response=response,
            user_session=user_session,
            db_session=db_session,
        )

    cookie = response.headers["set-cookie"]
    assert result is None
    assert response.status_code == 204
    assert "test_session=" in cookie
    assert "HttpOnly" in cookie
    assert "Max-Age=0" in cookie
    assert "Path=/api" in cookie
    assert "SameSite=strict" in cookie
    assert "Secure" in cookie
    delete_session_mock.assert_called_once_with(
        db_session=db_session,
        user_session=user_session,
    )


def test_logout_endpoint_returns_empty_response_and_deletes_cookie():
    db_session = Mock()
    user_session = UserSession(id=1, user_id=2, token_hash="hashed-session-token")
    test_app = FastAPI()
    test_app.include_router(auth_route.router)

    def override_get_db() -> Mock:
        return db_session

    def override_get_current_session() -> UserSession:
        return user_session

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_session] = override_get_current_session
    client = TestClient(test_app)
    client.cookies.set(settings.session_cookie_name, "raw-session-token")

    response = client.post("/auth/logout")

    assert response.status_code == 204
    assert response.content == b""
    assert "Max-Age=0" in response.headers["set-cookie"]
    db_session.delete.assert_called_once_with(user_session)
    db_session.commit.assert_called_once()
