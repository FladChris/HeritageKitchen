from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.schemas.auth_schema import UserLoginRequest, UserRegistrationRequest
from app.api.schemas.user_schema import UserCreateResponse, UserResponse
from app.models.session_model import UserSession
from app.models.user_model import User, UserRole
from app.services import auth_service

CREATED_AT = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


def create_registration_request() -> UserRegistrationRequest:
    return UserRegistrationRequest(
        username="recipefan",
        password="supersecret123",
    )


def add_database_values(user: User) -> None:
    user.id = 1
    user.created_at = CREATED_AT


def create_user_model(*, is_active: bool = True) -> User:
    return User(
        id=1,
        username="recipefan",
        email="recipefan@example.com",
        password_hash="argon2-hash",
        role=UserRole.READER,
        is_active=is_active,
        pending_approval=False,
        created_at=CREATED_AT,
    )


def create_login_request() -> UserLoginRequest:
    return UserLoginRequest(
        username="recipefan",
        password="supersecret123",
    )


@pytest.mark.parametrize(
    ("existing_user_id", "role", "active"),
    [(None, UserRole.ADMIN, True), (1, UserRole.EDITOR, False)],
)
def test_register_assigns_role_and_approval_status(existing_user_id, role, active):
    db_session = Mock()
    db_session.scalar.return_value = existing_user_id
    db_session.execute.return_value = []
    db_session.add.side_effect = add_database_values

    with patch(
        "app.services.auth_service.hash_password",
        return_value="argon2-hash",
    ) as hash_password_mock:
        result = auth_service.register_user(
            db_session=db_session,
            registration_request=create_registration_request(),
        )

    assert isinstance(result, UserCreateResponse)
    assert result.role == role
    assert result.is_active is active
    assert result.pending_approval is not active

    saved_user = db_session.add.call_args.args[0]
    assert saved_user.password_hash == "argon2-hash"
    assert saved_user.role == role
    assert saved_user.is_active is active
    assert saved_user.pending_approval is not active
    hash_password_mock.assert_called_once_with("supersecret123")
    db_session.commit.assert_called_once()


@pytest.mark.parametrize("field", [{"role": UserRole.ADMIN}, {"is_active": True}, {"pending_approval": False}])
def test_registration_request_rejects_account_privileges(field):
    with pytest.raises(ValidationError):
        UserRegistrationRequest(
            username="recipefan",
            email="recipefan@example.com",
            password="supersecret123",
            **field,
        )


def test_register_user_returns_conflict_for_duplicate_credentials():
    db_session = Mock()
    db_session.scalar.return_value = 1
    db_session.execute.return_value = []
    db_session.commit.side_effect = IntegrityError(
        "insert user",
        {},
        Exception("duplicate"),
    )

    with (
        patch(
            "app.services.auth_service.hash_password",
            return_value="argon2-hash",
        ),
        pytest.raises(HTTPException) as error,
    ):
        auth_service.register_user(
            db_session=db_session,
            registration_request=create_registration_request(),
        )

    assert error.value.status_code == 409
    assert error.value.detail == "Username or email already registered."
    db_session.rollback.assert_called_once()


def test_create_user_session_stores_only_token_hash():
    db_session = Mock()
    expected_expiration = datetime.now(UTC) + timedelta(days=7)

    with (
        patch(
            "app.services.auth_service.create_session_token",
            return_value="raw-session-token",
        ),
        patch(
            "app.services.auth_service.hash_session_token",
            return_value="hashed-session-token",
        ) as hash_session_token_mock,
    ):
        session_token = auth_service.create_user_session(
            db_session=db_session,
            user_id=1,
        )

    saved_session = db_session.add.call_args.args[0]
    assert isinstance(saved_session, UserSession)
    assert saved_session.user_id == 1
    assert saved_session.token_hash == "hashed-session-token"
    assert expected_expiration <= saved_session.expires_at
    assert saved_session.expires_at <= expected_expiration + timedelta(seconds=1)
    assert session_token == "raw-session-token"
    hash_session_token_mock.assert_called_once_with("raw-session-token")
    db_session.commit.assert_called_once()


def test_login_user_creates_session_for_valid_credentials():
    db_session = Mock()
    user_model = create_user_model()
    db_session.execute.return_value = [(user_model.id, user_model.username, user_model.email, None)]
    db_session.get.return_value = user_model

    with (
        patch(
            "app.services.auth_service.verify_password",
            return_value=True,
        ) as verify_password_mock,
        patch(
            "app.services.auth_service.create_user_session",
            return_value="raw-session-token",
        ) as create_user_session_mock,
    ):
        user, session_token = auth_service.login_user(
            db_session=db_session,
            login_request=create_login_request(),
        )

    assert isinstance(user, UserResponse)
    assert user.id == 1
    assert session_token == "raw-session-token"
    verify_password_mock.assert_called_once_with("supersecret123", "argon2-hash")
    create_user_session_mock.assert_called_once_with(db_session=db_session, user_id=1)


def test_login_user_rejects_unknown_user():
    db_session = Mock()
    db_session.execute.return_value = []

    with (
        patch("app.services.auth_service.verify_password") as verify_password_mock,
        patch("app.services.auth_service.create_user_session") as session_mock,
        pytest.raises(HTTPException) as error,
    ):
        auth_service.login_user(
            db_session=db_session,
            login_request=create_login_request(),
        )

    assert error.value.status_code == 401
    assert error.value.detail == "Invalid username or password."
    verify_password_mock.assert_not_called()
    session_mock.assert_not_called()


def test_login_user_rejects_wrong_password():
    db_session = Mock()
    user = create_user_model()
    db_session.execute.return_value = [(user.id, user.username, user.email, None)]
    db_session.get.return_value = user

    with (
        patch("app.services.auth_service.verify_password", return_value=False),
        patch("app.services.auth_service.create_user_session") as session_mock,
        pytest.raises(HTTPException) as error,
    ):
        auth_service.login_user(
            db_session=db_session,
            login_request=create_login_request(),
        )

    assert error.value.status_code == 401
    assert error.value.detail == "Invalid username or password."
    session_mock.assert_not_called()


def test_login_user_rejects_inactive_user():
    db_session = Mock()
    user = create_user_model(is_active=False)
    db_session.execute.return_value = [(user.id, user.username, user.email, None)]
    db_session.get.return_value = user

    with (
        patch("app.services.auth_service.verify_password", return_value=True),
        patch("app.services.auth_service.create_user_session") as session_mock,
        pytest.raises(HTTPException) as error,
    ):
        auth_service.login_user(
            db_session=db_session,
            login_request=create_login_request(),
        )

    assert error.value.status_code == 401
    assert error.value.detail == "Invalid username or password."
    session_mock.assert_not_called()
