from typing import Annotated

from pydantic import Field, field_validator

from app.api.schemas.base_schema import BaseRequest
from app.api.schemas.validation_helpers import require_unique_values


class RecipeOrderRequest(BaseRequest):
    category_id: Annotated[int, Field(strict=True, gt=0)]
    recipe_ids: list[Annotated[int, Field(strict=True, gt=0)]]

    @field_validator("recipe_ids")
    @classmethod
    def require_unique_ids(cls, value: list[int]) -> list[int]:
        return require_unique_values(value, "Each recipe must appear exactly once.")
