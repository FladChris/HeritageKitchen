from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.api.schemas.base_schema import BaseRequest, BaseSchema
from app.api.schemas.validation_helpers import require_unique_values

FavoriteSort = Literal["recent", "name", "manual"]


class FavoriteResponse(BaseSchema):
    id: int = Field(description="Unique ID of the favorite.", examples=[1])
    user_id: int = Field(
        description="ID of the user who owns the favorite.", examples=[1]
    )
    recipe_id: int = Field(
        description="ID of the recipe marked as favorite.",
        examples=[12],
    )

    created_at: datetime | None = Field(description="Time favorited, if recorded.")

    @field_validator("created_at")
    @classmethod
    def use_utc_for_naive_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class FavoriteCreateRequest(BaseRequest):
    recipe_id: int = Field(
        ge=1,
        description="ID of the recipe to store as a favorite.",
        examples=[12],
    )


class FavoriteOrderRequest(BaseRequest):
    favorite_ids: list[Annotated[int, Field(strict=True, gt=0)]]

    @field_validator("favorite_ids")
    @classmethod
    def require_unique_ids(cls, value: list[int]) -> list[int]:
        return require_unique_values(value, "Each favorite must appear exactly once.")


class FavoritePreferences(BaseSchema):
    sort: FavoriteSort
    recipe_view: Literal["list", "grid"]


class FavoritePreferencesUpdate(BaseRequest):
    sort: FavoriteSort | None = None
    recipe_view: Literal["list", "grid"] | None = None
