from datetime import UTC, datetime

from pydantic import AliasPath, Field, field_validator

from app.api.schemas.base_schema import BaseRequest, BaseSchema


class RecipeCommentRequest(BaseRequest):
    text: str = Field(min_length=1, max_length=5000)


class RecipeCommentResponse(BaseSchema):
    id: int
    recipe_id: int
    author_id: int | None
    author_username: str | None = Field(
        default=None, validation_alias=AliasPath("author", "username")
    )
    text: str
    created_at: datetime
    edited_at: datetime | None

    @field_validator("created_at", "edited_at")
    @classmethod
    def use_utc_for_naive_timestamps(cls, value: datetime | None) -> datetime | None:
        # SQLite returns UTC datetimes without their timezone.
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
