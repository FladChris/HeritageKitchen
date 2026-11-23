from pydantic import Field, field_validator

from app.api.schemas.base_schema import BaseRequest
from app.api.schemas.validation_helpers import (
    OptionalEmail,
    Username,
    require_text_value,
)


class UserLoginRequest(BaseRequest):
    username: str = Field(
        min_length=1,
        max_length=254,
        description="Username or email address used for login.",
        examples=["chefmax", "recipefan@example.com"],
    )
    password: str = Field(
        min_length=1,
        max_length=255,
        description="Plain-text password used for login.",
        examples=["example-password"],
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return require_text_value(value, "username")

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return require_text_value(value, "password")


class PasswordChangeRequest(BaseRequest):
    current_password: str = Field(min_length=1, max_length=255)
    new_password: str = Field(min_length=8, max_length=255)

    @field_validator("current_password", "new_password")
    @classmethod
    def validate_password(cls, value: str, info) -> str:
        return require_text_value(value, info.field_name)


class UserRegistrationRequest(BaseRequest):
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

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return require_text_value(value, "password")
