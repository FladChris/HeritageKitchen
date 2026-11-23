from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import CurrentUser, get_current_session, get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.session_model import UserSession
from app.models.user_model import User


def create_user_session(*, expires_at: datetime | None = None) -> UserSession:
    return UserSession(
        id=1,
        user_id=2,
        token_hash="hashed-session-token",
        expires_at=expires_at or datetime.now(UTC) + timedelta(days=1),
    )


def test_get_current_session_rejects_missing_cookie():
    db_session = Mock()

    with pytest.raises(HTTPException) as error:
        get_current_session(db_session=db_session, session_token=None)

    assert error.value.status_code == 401
    assert error.value.detail == "Not authenticated."
    db_session.scalar.assert_not_called()


def test_get_current_session_rejects_unknown_token():
    db_session = Mock()
    db_session.scalar.return_value = None

    with (
        patch(
            "app.api.dependencies.hash_session_token",
            return_value="hashed-session-token",
        ) as hash_session_token_mock,
        pytest.raises(HTTPException) as error,
    ):
        get_current_session(
            db_session=db_session,
            session_token="raw-session-token",
        )

    assert error.value.status_code == 401
    hash_session_token_mock.assert_called_once_with("raw-session-token")


def test_get_current_session_returns_valid_session():
    db_session = Mock()
    user_session = create_user_session()
    db_session.scalar.return_value = user_session

    result = get_current_session(
        db_session=db_session,
        session_token="raw-session-token",
    )

    assert result is user_session
    db_session.delete.assert_not_called()


def test_get_current_session_deletes_expired_session():
    db_session = Mock()
    user_session = create_user_session(
        expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
    )
    db_session.scalar.return_value = user_session

    with pytest.raises(HTTPException) as error:
        get_current_session(
            db_session=db_session,
            session_token="raw-session-token",
        )

    assert error.value.status_code == 401
    db_session.delete.assert_called_once_with(user_session)
    db_session.commit.assert_called_once()


def test_get_current_user_returns_active_user():
    db_session = Mock()
    user_session = create_user_session()
    user = User(id=2, is_active=True)
    db_session.get.return_value = user

    result = get_current_user(
        user_session=user_session,
        db_session=db_session,
    )

    assert result is user
    db_session.get.assert_called_once_with(User, 2)
    db_session.delete.assert_not_called()


@pytest.mark.parametrize("user", [None, User(id=2, is_active=False)])
def test_get_current_user_rejects_unavailable_user(user: User | None):
    db_session = Mock()
    user_session = create_user_session()
    db_session.get.return_value = user

    with pytest.raises(HTTPException) as error:
        get_current_user(
            user_session=user_session,
            db_session=db_session,
        )

    assert error.value.status_code == 401
    assert error.value.detail == "Not authenticated."
    db_session.delete.assert_called_once_with(user_session)
    db_session.commit.assert_called_once()


def test_current_user_dependency_reads_session_cookie():
    db_session = Mock()
    db_session.scalar.return_value = create_user_session()
    db_session.get.return_value = User(id=2, is_active=True)
    test_app = FastAPI()

    def override_get_db() -> Mock:
        return db_session

    @test_app.get("/protected")
    def protected_route(current_user: CurrentUser) -> dict[str, int]:
        return {"user_id": current_user.id}

    test_app.dependency_overrides[get_db] = override_get_db
    client = TestClient(test_app)
    client.cookies.set(settings.session_cookie_name, "raw-session-token")

    response = client.get("/protected")

    assert response.status_code == 200
    assert response.json() == {"user_id": 2}
