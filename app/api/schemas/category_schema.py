from typing import Annotated

from pydantic import Field, field_validator

from app.api.schemas.base_schema import BaseRequest, BaseSchema
from app.api.schemas.validation_helpers import (
    normalize_optional_text_value,
    require_text_value,
    require_unique_values,
)


class CategoryResponse(BaseSchema):
    id: int = Field(description="Unique ID of the category.", examples=[1])
    recipe_count: int | None = Field(
        default=None, ge=0, description="Number of recipes in the category, when requested."
    )
    name: str = Field(
        description="Display name of the category.", examples=["Desserts"]
    )
    description: str | None = Field(
        description="Optional description of the category.",
        examples=["Sweet dishes, cakes, and pastries."],
    )
    image_path: str | None = Field(
        description="Optional path to the category image.",
        examples=["/uploads/categories/desserts.jpg"],
    )
    image_alt_text: str | None = Field(
        description="Optional alt text for the category image.",
        examples=["Assorted desserts on a table"],
    )


class CategoryOrderRequest(BaseRequest):
    category_ids: list[Annotated[int, Field(strict=True, gt=0)]]

    @field_validator("category_ids")
    @classmethod
    def require_unique_ids(cls, value: list[int]) -> list[int]:
        return require_unique_values(value, "Each category must appear exactly once.")


class CategoryCreateRequest(BaseRequest):
    name: str = Field(
        min_length=1,
        max_length=100,
        description="Name of the category to create.",
        examples=["Desserts"],
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Optional description of the category.",
        examples=["Sweet dishes, cakes, and pastries."],
    )
    image_alt_text: str | None = Field(
        default=None,
        max_length=255,
        description="Optional alt text for the category image.",
        examples=["Assorted desserts on a table"],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return require_text_value(value, "name")

    @field_validator("description", "image_alt_text")
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text_value(value)


class CategoryUpdateRequest(BaseRequest):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="New name of the category.",
        examples=["Desserts"],
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="New optional description of the category.",
        examples=["Sweet dishes, cakes, and pastries."],
    )
    image_alt_text: str | None = Field(
        default=None,
        max_length=255,
        description="New optional alt text for the category image.",
        examples=["Assorted desserts on a table"],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("name must not be null")
        return require_text_value(value, "name")

    @field_validator("description", "image_alt_text")
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text_value(value)
