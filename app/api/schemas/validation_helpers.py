from typing import Annotated

from pydantic import BeforeValidator, EmailStr, StringConstraints


def require_text_value(value: str, field_name: str) -> str:
    stripped_value = value.strip()
    if not stripped_value:
        raise ValueError(f"{field_name} must not be empty")
    return stripped_value


def normalize_optional_text_value(value: str | None) -> str | None:
    if not value:
        return None
    stripped_value = value.strip()
    return stripped_value or None


def require_unique_values(values: list[int], message: str) -> list[int]:
    if len(values) != len(set(values)):
        raise ValueError(message)
    return values


def _empty_email_as_none(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


OptionalEmail = Annotated[EmailStr | None, BeforeValidator(_empty_email_as_none)]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=32)]
