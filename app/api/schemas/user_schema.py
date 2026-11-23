from datetime import datetime
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator

from app.api.schemas.base_schema import BaseRequest, BaseSchema
from app.api.schemas.category_schema import CategoryOrderRequest
from app.api.schemas.favorite_schema import FavoriteResponse
from app.api.schemas.validation_helpers import (
    OptionalEmail,
    Username,
    require_text_value,
)
from app.models import UserRole


class ViewPreferencesUpdate(BaseRequest):
    category_sort: Literal["manual", "name", "count"] | None = None
    recipe_view: Literal["list", "grid"] | None = None
    category_order: CategoryOrderRequest | None = None


class ViewPreferences(BaseSchema):
    category_sort: Literal["manual", "name", "count"]
    recipe_view: Literal["list", "grid"]
    category_ids: list[int]


class UserResponse(BaseSchema):
    id: int = Field(description="Unique ID of the user.", examples=[1])
    username: str = Field(
        description="Unique username of the user.", examples=["chefmax"]
    )
    email: OptionalEmail = Field(
        description="Optional email address of the user.",
        examples=["recipefan@example.com"],
    )
    email_verified_at: datetime | None = None
    profile_image_path: str | None = None
    role: UserRole = Field(
        description="Role of the user in the system.", examples=["reader"]
    )
    is_active: bool = Field(description="Whether the user is active.", examples=[True])
    pending_approval: bool = Field(description="Whether the user is awaiting admin approval.")
    created_at: datetime = Field(
        description="Timestamp when the user was created.",
        examples=["2026-06-28T12:00:00"],
    )


class UserCreateRequest(BaseRequest):
    username: Username = Field(
        description="Required username for login.",
        examples=["chefmax"],
    )
    email: OptionalEmail = Field(
        default=None,
        description="Optional email address of the user.",
        examples=["recipefan@example.com"],
    )
    password: str = Field(
        min_length=8,
        max_length=255,
        description="Plain-text password that will be hashed before storage.",
        examples=["example-password"],
    )
    role: UserRole = Field(
        default=UserRole.READER,
        description="Role assigned to the user.",
        examples=["reader"],
    )
    is_active: bool = Field(
        default=True,
        description="Whether the user is active immediately.",
        examples=[True],
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return require_text_value(value, "password")

class UserCreateResponse(UserResponse):
    pass


class UserListResponse(UserResponse):
    pass


class UserGetResponse(UserResponse):
    updated_at: datetime = Field(
        description="Timestamp when the user was last updated.",
        examples=["2026-06-28T12:30:00"],
    )
    favorites: list[FavoriteResponse] = Field(
        default_factory=list,
        description="List of favorites that belong to the user.",
    )


class UserUpdateResponse(UserResponse):
    pass


class ProfileUpdateRequest(BaseRequest):
    username: Username | None = None
    email: OptionalEmail = None
    current_password: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("username")
    @classmethod
    def reject_null_username(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("username must not be null.")
        return value


class UserUpdateRequest(ProfileUpdateRequest):
    password: str | None = Field(
        default=None,
        min_length=8,
        max_length=255,
        description="New optional password that will be hashed before storage.",
        examples=["example-password"],
    )
    role: UserRole | None = Field(
        default=None,
        description="New optional role of the user.",
        examples=["editor"],
    )
    is_active: bool | None = Field(
        default=None,
        description="New optional active status of the user.",
        examples=[True],
    )

    @field_validator("role", "is_active")
    @classmethod
    def reject_explicit_null(cls, value: object, info: ValidationInfo) -> object:
        # Omitted fields keep their default; an explicit null cannot be stored.
        if value is None:
            raise ValueError(f"{info.field_name} must not be null.")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return require_text_value(value, "password")
