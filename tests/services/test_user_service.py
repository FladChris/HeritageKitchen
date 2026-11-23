from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from app.api.schemas.user_schema import (
    UserCreateRequest,
    UserCreateResponse,
    UserGetResponse,
    UserListResponse,
    UserUpdateRequest,
    UserUpdateResponse,
)
from app.models.favorite_model import Favorite
from app.models.user_model import User, UserRole
from app.services import user_service

CREATED_AT = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
UPDATED_AT = datetime(2026, 6, 28, 12, 30, tzinfo=UTC)


def create_user_model(**overrides) -> User:
    user_data = {
        "id": 1,
        "username": "recipefan",
        "email": "recipefan@example.com",
        "password_hash": "hash123",
        "role": UserRole.READER,
        "is_active": True,
        "pending_approval": False,
        "created_at": CREATED_AT,
        "updated_at": UPDATED_AT,
    }
    user_data.update(overrides)
    return User(**user_data)


def test_create_user():
    db_session = Mock()
    db_session.execute.return_value = []

    def add_database_values(user: User) -> None:
        user.id = 1
        user.created_at = CREATED_AT

    db_session.add.side_effect = add_database_values

    user_create_request = UserCreateRequest(
        username="recipefan",
        password="supersecret123",
        role=UserRole.READER,
        is_active=True,
    )

    with patch(
        "app.services.user_service.hash_password",
        return_value="hash123",
    ) as hash_password_mock:
        user = user_service.create_user(
            db_session=db_session,
            user_create_request=user_create_request,
        )

    assert isinstance(user, UserCreateResponse)
    assert user.id == 1
    assert user.username == "recipefan"
    assert user.email is None
    assert user.role == UserRole.READER
    assert user.is_active is True

    saved_user = db_session.add.call_args.args[0]
    assert saved_user.password_hash == "hash123"
    assert not hasattr(saved_user, "password")
    hash_password_mock.assert_called_once_with("supersecret123")
    db_session.add.assert_called_once()
    db_session.commit.assert_called_once()


def test_list_users():
    db_session = Mock()
    first_user = create_user_model(id=1, username="homecook")
    second_user = create_user_model(id=2, username="recipefan")
    db_session.scalars.return_value = [first_user, second_user]

    users = user_service.list_users(db_session=db_session)

    assert len(users) == 2
    assert all(isinstance(user, UserListResponse) for user in users)
    assert users[0].username == "homecook"
    assert users[1].username == "recipefan"
    db_session.scalars.assert_called_once()


def test_get_user():
    db_session = Mock()
    user = create_user_model()
    user.favorites = [Favorite(id=1, user_id=1, recipe_id=12)]
    db_session.get.return_value = user

    result = user_service.get_user(db_session=db_session, user_id=1)

    assert isinstance(result, UserGetResponse)
    assert result.username == "recipefan"
    assert result.updated_at == UPDATED_AT
    assert len(result.favorites) == 1
    assert result.favorites[0].recipe_id == 12
    db_session.get.assert_called_once_with(User, 1)


def test_get_user_raises_not_found():
    db_session = Mock()
    db_session.get.return_value = None

    with pytest.raises(HTTPException) as error:
        user_service.get_user(db_session=db_session, user_id=999)

    assert error.value.status_code == 404
    assert error.value.detail == "User not found."


def test_update_user():
    db_session = Mock()
    db_session.execute.return_value = []
    user = create_user_model()
    db_session.get.return_value = user
    user_update_request = UserUpdateRequest(
        username="newrecipefan",
        password="newsecret123",
    )

    with patch(
        "app.services.user_service.hash_password",
        return_value="new-hash",
    ) as hash_password_mock:
        updated_user = user_service.update_user(
            db_session=db_session,
            user_id=1,
            user_update_request=user_update_request,
        )

    assert isinstance(updated_user, UserUpdateResponse)
    assert updated_user.username == "newrecipefan"
    assert updated_user.email == "recipefan@example.com"
    assert user.password_hash == "new-hash"
    hash_password_mock.assert_called_once_with("newsecret123")
    db_session.get.assert_called_once_with(User, 1, populate_existing=True)
    db_session.commit.assert_called_once()


def test_update_user_without_password_keeps_password_hash():
    db_session = Mock()
    db_session.execute.return_value = []
    user = create_user_model()
    db_session.get.return_value = user
    user_update_request = UserUpdateRequest(username="newrecipefan")

    with patch("app.services.user_service.hash_password") as hash_password_mock:
        user_service.update_user(
            db_session=db_session,
            user_id=1,
            user_update_request=user_update_request,
        )

    assert user.password_hash == "hash123"
    hash_password_mock.assert_not_called()


def test_update_user_raises_not_found():
    db_session = Mock()
    db_session.get.return_value = None
    user_update_request = UserUpdateRequest(username="newrecipefan")

    with pytest.raises(HTTPException) as error:
        user_service.update_user(
            db_session=db_session,
            user_id=999,
            user_update_request=user_update_request,
        )

    assert error.value.status_code == 404
    assert error.value.detail == "User not found."


def test_delete_user():
    db_session = Mock()
    user = create_user_model()
    db_session.get.return_value = user

    result = user_service.delete_user(db_session=db_session, user_id=1)

    assert result is None
    db_session.get.assert_called_once_with(User, 1, populate_existing=True)
    deletion = db_session.execute.call_args.args[0]
    assert deletion.is_delete and deletion.table.name == "users"
    db_session.commit.assert_called_once()


def test_delete_user_raises_not_found():
    db_session = Mock()
    db_session.get.return_value = None

    with pytest.raises(HTTPException) as error:
        user_service.delete_user(db_session=db_session, user_id=999)

    assert error.value.status_code == 404
    assert error.value.detail == "User not found."
