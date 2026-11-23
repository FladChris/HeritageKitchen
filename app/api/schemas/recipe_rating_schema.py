from pydantic import BaseModel, Field, field_validator

from app.api.schemas.base_schema import BaseRequest


class RecipeRatingRequest(BaseRequest):
    stars: float = Field(
        strict=True, ge=1, le=5, description="Rating in half-star steps."
    )

    @field_validator("stars")
    @classmethod
    def validate_half_stars(cls, stars: float) -> float:
        if stars * 2 not in range(2, 11):
            raise ValueError("Use half-star steps.")
        return stars


class RecipeRatingEntry(BaseModel):
    username: str
    stars: float


class RecipeRatingSummary(BaseModel):
    average: float | None
    count: int
    ratings: list[RecipeRatingEntry]
