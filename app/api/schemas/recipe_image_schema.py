from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from app.api.schemas.base_schema import BaseRequest, BaseSchema
from app.api.schemas.validation_helpers import normalize_optional_text_value

RecipeImageAltText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=255),
    AfterValidator(normalize_optional_text_value),
] | None


class RecipeImageResponse(BaseSchema):
    id: int = Field(description="Unique ID of the recipe image.", examples=[3])
    recipe_id: int = Field(description="ID of the related recipe.", examples=[12])
    file_path: str = Field(
        description="Public path to the stored image file, usable as an img src.",
        examples=["/media/recipe-images/12/3f9c1e1e-...-webp.jpg"],
    )
    alt_text: str | None = Field(
        description="Optional alt text for the recipe image.",
        examples=["Chocolate cake on a cooling rack"],
    )
    is_main: bool = Field(description="Whether this is the main image of the recipe.")


class RecipeImageOrderRequest(BaseRequest):
    image_ids: list[int] = Field(
        description="All image IDs of the recipe in the new gallery order.",
        examples=[[5, 3, 4]],
    )


class RecipeImageUpdateRequest(BaseRequest):
    is_main: bool | None = Field(
        default=None,
        description="Set true to make this the main image of its recipe.",
    )
    alt_text: RecipeImageAltText = Field(
        default=None,
        description="New optional alt text for the recipe image.",
        examples=["Chocolate cake on a cooling rack"],
    )
