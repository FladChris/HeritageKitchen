from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.api.schemas.base_schema import BaseRequest, BaseSchema
from app.api.schemas.category_schema import CategoryResponse
from app.api.schemas.recipe_image_schema import RecipeImageResponse
from app.api.schemas.validation_helpers import (
    normalize_optional_text_value,
    require_text_value,
    require_unique_values,
)


def parse_amount(value: str | float | Decimal | None) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if "/" in value:
            parts = value.split("/")
            if len(parts) != 2:
                raise ValueError("Invalid amount")
            try:
                amount = Decimal(parts[0]) / Decimal(parts[1])
            except (InvalidOperation, ZeroDivisionError) as exc:
                raise ValueError("Invalid amount") from exc
        else:
            try:
                amount = Decimal(value)
            except InvalidOperation as exc:
                raise ValueError("Invalid amount") from exc
    else:
        amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid amount")
    return amount


class RecipeIngredientResponse(BaseSchema):
    id: int = Field(description="Unique ID of the ingredient entry.", examples=[1])
    recipe_id: int = Field(description="ID of the related recipe.", examples=[12])
    group_position: int | None = None
    position: int = Field(
        description="Order of the ingredient within the recipe.", examples=[0]
    )
    name: str = Field(description="Name of the ingredient.", examples=["Flour"])
    amount: Decimal | None = None
    unit: str | None = None
    note: str | None = Field(
        description="Optional note for the ingredient.", examples=["sifted"]
    )


class RecipeIngredientCreateRequest(BaseRequest):
    group_position: int | None = Field(default=None, ge=0)
    position: int = Field(
        ge=0,
        description="Position of the ingredient within the recipe.",
        examples=[0],
    )
    name: str = Field(
        min_length=1,
        max_length=150,
        description="Name of the ingredient.",
        examples=["Flour"],
    )
    amount: Decimal | None = None
    unit: str | None = Field(default=None, max_length=50)
    note: str | None = Field(
        default=None,
        max_length=255,
        description="Optional note for the ingredient.",
        examples=["sifted"],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return require_text_value(value, "name")

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: str | Decimal | None) -> Decimal | None:
        return parse_amount(value)

    @field_validator("unit", "note")
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text_value(value)


class RecipeIngredientUpdateRequest(BaseRequest):
    group_position: int | None = Field(default=None, ge=0)
    position: int | None = Field(
        default=None,
        ge=0,
        description="New optional position of the ingredient within the recipe.",
        examples=[0],
    )
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
        description="New optional name of the ingredient.",
        examples=["Flour"],
    )
    amount: Decimal | None = None
    unit: str | None = Field(default=None, max_length=50)
    note: str | None = Field(
        default=None,
        max_length=255,
        description="New optional note for the ingredient.",
        examples=["sifted"],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return require_text_value(value, "name")

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: str | Decimal | None) -> Decimal | None:
        return parse_amount(value)

    @field_validator("unit", "note")
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text_value(value)


class RecipeIngredientGroupResponse(BaseSchema):
    id: int
    recipe_id: int
    position: int
    name: str


class RecipeIngredientGroupRequest(BaseRequest):
    position: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=150)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return require_text_value(value, "name")


StepTimeKind = Literal["preparation", "cooking", "rest"]
MAX_STEP_MINUTES = 14 * 24 * 60


class RecipeStepResponse(BaseSchema):
    id: int = Field(description="Unique ID of the recipe step.", examples=[1])
    recipe_id: int = Field(description="ID of the related recipe.", examples=[12])
    position: int = Field(
        description="Order of the step within the recipe.", examples=[0]
    )
    instruction: str = Field(
        description="Instruction for this recipe step.",
        examples=["Mix all dry ingredients."],
    )
    heading: str | None = Field(
        description="Optional section heading shown above this step, e.g. Day 1.",
        examples=["Day 1"],
    )
    is_important: bool = Field(
        description="Whether the step is especially important.",
        examples=[False],
    )
    note: str | None = Field(
        description="Optional note for the step.", examples=["Do not overmix."]
    )
    duration_minutes: int | None = Field(
        default=None, description="Optional explicit duration of the step in minutes.", examples=[20]
    )
    time_kind: StepTimeKind | None = Field(
        default=None, description="Kind of the step duration: preparation, cooking or rest."
    )
    day: int = Field(default=1, description="Preparation day the step belongs to.", examples=[1])


class RecipeStepCreateRequest(BaseRequest):
    position: int = Field(
        ge=0,
        description="Position of the step within the recipe.",
        examples=[0],
    )
    instruction: str = Field(
        min_length=1,
        max_length=2000,
        description="Instruction for the recipe step.",
        examples=["Mix all dry ingredients."],
    )
    heading: str | None = Field(
        default=None,
        max_length=100,
        description="Optional section heading shown above this step, e.g. Day 1.",
        examples=["Day 1"],
    )
    is_important: bool = Field(
        default=False,
        description="Whether the step is especially important.",
        examples=[False],
    )
    note: str | None = Field(
        default=None,
        max_length=255,
        description="Optional note for the step.",
        examples=["Do not overmix."],
    )
    duration_minutes: int | None = Field(
        default=None,
        ge=1,
        le=MAX_STEP_MINUTES,
        strict=True,
        description="Optional explicit duration of the step in minutes.",
        examples=[20],
    )
    time_kind: StepTimeKind | None = Field(
        default=None,
        description="Kind of the step duration: preparation, cooking or rest.",
    )
    day: int = Field(
        default=1, ge=1, le=14, strict=True,
        description="Preparation day the step belongs to.", examples=[1],
    )

    @field_validator("instruction")
    @classmethod
    def validate_instruction(cls, value: str) -> str:
        return require_text_value(value, "instruction")

    @field_validator("heading", "note")
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text_value(value)

    @model_validator(mode="after")
    def validate_step_time(self) -> "RecipeStepCreateRequest":
        if (self.duration_minutes is None) != (self.time_kind is None):
            raise ValueError("duration_minutes and time_kind must be set together")
        return self


class RecipeStepUpdateRequest(BaseRequest):
    position: int | None = Field(
        default=None,
        ge=0,
        description="New optional position of the step within the recipe.",
        examples=[0],
    )
    instruction: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
        description="New optional instruction for the recipe step.",
        examples=["Mix all dry ingredients."],
    )
    heading: str | None = Field(
        default=None,
        max_length=100,
        description="New optional section heading shown above this step.",
        examples=["Day 1"],
    )
    is_important: bool | None = Field(
        default=None,
        description="New optional importance status of the step.",
        examples=[False],
    )
    note: str | None = Field(
        default=None,
        max_length=255,
        description="New optional note for the step.",
        examples=["Do not overmix."],
    )

    @field_validator("instruction")
    @classmethod
    def validate_instruction(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return require_text_value(value, "instruction")

    @field_validator("heading", "note")
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text_value(value)


class RecipeResponse(BaseSchema):
    version: int
    history: str | None = None
    preparation_days: int = 1
    day_titles: list[str] | None = None
    id: int = Field(description="Unique ID of the recipe.", examples=[12])
    title: str = Field(description="Title of the recipe.", examples=["Chocolate Cake"])
    summary: str | None = Field(
        description="Optional short description of the recipe.",
        examples=["A rich and moist chocolate cake."],
    )
    preparation_time: int | None = Field(
        description="Optional preparation time in minutes.",
        examples=[20],
    )
    cooking_time: int | None = Field(
        description="Optional cooking time in minutes.", examples=[35]
    )
    cooking_time_max: int | None = Field(
        description="Optional upper end of the cooking time in minutes.", examples=[45]
    )
    rest_time: int | None = Field(
        description="Optional resting time in minutes.", examples=[15]
    )
    rest_time_max: int | None = Field(
        description="Optional upper end of the resting time in minutes.", examples=[30]
    )
    servings: int | None = Field(
        description="Optional number of servings.", examples=[8]
    )
    origin_person: str | None = None
    notes: str | None = Field(
        description="Optional general notes for the recipe.",
        examples=["Best served slightly warm."],
    )
    important_notes: str | None = Field(
        description="Optional especially important notes for the recipe.",
        examples=["Check with a skewer before removing from oven."],
    )
    category_id: int | None = Field(
        description="Optional ID of the assigned category.",
        examples=[1],
    )
    created_at: datetime = Field(
        description="Timestamp when the recipe was created.",
        examples=["2026-06-23T10:00:00"],
    )
    updated_at: datetime = Field(
        description="Timestamp when the recipe was last updated.",
        examples=["2026-06-23T10:30:00"],
    )
    category: CategoryResponse | None = Field(
        default=None,
        description="Optional embedded category of the recipe.",
    )
    images: list[RecipeImageResponse] = Field(
        default_factory=list,
        description="List of images that belong to the recipe.",
    )
    ingredients: list[RecipeIngredientResponse] = Field(
        default_factory=list,
        description="List of ingredients in the recipe.",
    )
    ingredient_groups: list[RecipeIngredientGroupResponse] = Field(default_factory=list)
    steps: list[RecipeStepResponse] = Field(
        default_factory=list,
        description="List of preparation steps in the recipe.",
    )


class StepTimesResponse(BaseSchema):
    preparation: int | None = None
    cooking: int | None = None
    rest: int | None = None


class RecipeSummaryResponse(BaseSchema):
    version: int
    id: int
    title: str
    summary: str | None
    origin_person: str | None
    preparation_days: int
    preparation_time: int | None
    cooking_time: int | None
    cooking_time_max: int | None
    rest_time: int | None
    rest_time_max: int | None
    servings: int | None
    category_id: int | None
    category: CategoryResponse | None
    images: list[RecipeImageResponse] = Field(default_factory=list)
    step_times: StepTimesResponse = Field(
        default_factory=StepTimesResponse, description="Summed step durations per time kind."
    )
    created_at: datetime
    updated_at: datetime


class OtherCategoryHit(BaseSchema):
    id: int = Field(description="Category with matching recipes.", examples=[3])
    name: str = Field(description="Category name.", examples=["Backen"])
    count: int = Field(ge=1, description="Number of matching recipes in this category.", examples=[4])


class RecipeListResponse(BaseSchema):
    items: list[RecipeResponse | RecipeSummaryResponse] = Field(
        description="Recipes on the requested page.",
    )
    total: int = Field(
        ge=0,
        description="Total number of recipes matching the search.",
        examples=[42],
    )
    other_categories: list[OtherCategoryHit] = Field(
        default_factory=list,
        description="Other categories with matches; only set when a search within a category has no match.",
    )
    page: int = Field(
        ge=1,
        description="Current page number.",
        examples=[1],
    )
    page_size: int = Field(
        ge=1,
        le=100,
        description="Maximum number of recipes per page.",
        examples=[20],
    )


class RecipeCreateRequest(BaseRequest):
    history: str | None = Field(default=None, max_length=5000)
    preparation_days: int = Field(default=1, ge=1, le=14, strict=True)
    day_titles: list[Annotated[str, Field(max_length=100)]] | None = Field(default=None, max_length=14)
    title: str = Field(
        min_length=1,
        max_length=150,
        description="Title of the recipe to create.",
        examples=["Chocolate Cake"],
    )
    summary: str | None = Field(
        default=None,
        max_length=500,
        description="Optional short description of the recipe.",
        examples=["A rich and moist chocolate cake."],
    )
    preparation_time: int | None = Field(
        default=None,
        ge=0,
        description="Optional preparation time in minutes.",
        examples=[20],
    )
    cooking_time: int | None = Field(
        default=None,
        ge=0,
        description="Optional cooking time in minutes.",
        examples=[35],
    )
    cooking_time_max: int | None = Field(
        default=None,
        ge=0,
        description="Optional upper end of the cooking time in minutes.",
        examples=[70],
    )
    rest_time: int | None = Field(
        default=None,
        ge=0,
        description="Optional resting time in minutes.",
        examples=[15],
    )
    rest_time_max: int | None = Field(
        default=None,
        ge=0,
        description="Optional upper end of the resting time in minutes.",
        examples=[30],
    )
    servings: int | None = Field(
        default=None,
        ge=1,
        description="Optional number of servings.",
        examples=[8],
    )
    origin_person: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(
        default=None,
        max_length=4000,
        description="Optional general notes for the recipe.",
        examples=["Best served slightly warm."],
    )
    important_notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional especially important notes for the recipe.",
        examples=["Check with a skewer before removing from oven."],
    )
    category_id: int = Field(
        ge=1,
        description="ID of the category for the recipe.",
        examples=[1],
    )
    ingredients: list[RecipeIngredientCreateRequest] = Field(
        default_factory=list,
        description="List of ingredients to create with the recipe.",
        examples=[
            [
                {
                    "position": 0,
                    "name": "Flour",
                    "note": "sifted",
                }
            ]
        ],
    )
    ingredient_groups: list[RecipeIngredientGroupRequest] = Field(default_factory=list)
    steps: list[RecipeStepCreateRequest] = Field(
        default_factory=list,
        description="List of preparation steps to create with the recipe.",
        examples=[
            [
                {
                    "position": 0,
                    "instruction": "Mix all dry ingredients.",
                    "heading": "Day 1",
                    "is_important": False,
                    "note": "Do not overmix.",
                }
            ]
        ],
    )

    @field_validator("day_titles")
    @classmethod
    def normalize_day_titles(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else [title.strip() for title in value]

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return require_text_value(value, "title")

    @field_validator("summary", "origin_person", "history", "notes", "important_notes")
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text_value(value)

    @model_validator(mode="after")
    def validate_nested_positions(self) -> "RecipeCreateRequest":
        group_positions = require_unique_values(
            [group.position for group in self.ingredient_groups],
            "ingredient group positions must be unique",
        )
        if any(ingredient.group_position is not None and ingredient.group_position not in group_positions for ingredient in self.ingredients):
            raise ValueError("ingredient group does not exist")
        require_unique_values(
            [ingredient.position for ingredient in self.ingredients],
            "ingredient positions must be unique",
        )
        require_unique_values(
            [step.position for step in self.steps], "step positions must be unique"
        )

        return self


class RecipeUpdateRequest(BaseRequest):
    history: str | None = Field(default=None, max_length=5000)
    preparation_days: int = Field(default=1, ge=1, le=14, strict=True)
    day_titles: list[Annotated[str, Field(max_length=100)]] | None = Field(default=None, max_length=14)
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
        description="New optional title of the recipe.",
        examples=["Chocolate Cake"],
    )
    summary: str | None = Field(
        default=None,
        max_length=500,
        description="New optional short description of the recipe.",
        examples=["A rich and moist chocolate cake."],
    )
    preparation_time: int | None = Field(
        default=None,
        ge=0,
        description="New optional preparation time in minutes.",
        examples=[20],
    )
    cooking_time: int | None = Field(
        default=None,
        ge=0,
        description="New optional cooking time in minutes.",
        examples=[35],
    )
    cooking_time_max: int | None = Field(
        default=None,
        ge=0,
        description="New optional upper end of the cooking time in minutes.",
        examples=[70],
    )
    rest_time: int | None = Field(
        default=None,
        ge=0,
        description="New optional resting time in minutes.",
        examples=[15],
    )
    rest_time_max: int | None = Field(
        default=None,
        ge=0,
        description="New optional upper end of the resting time in minutes.",
        examples=[30],
    )
    servings: int | None = Field(
        default=None,
        ge=1,
        description="New optional number of servings.",
        examples=[8],
    )
    origin_person: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(
        default=None,
        max_length=4000,
        description="New optional general notes for the recipe.",
        examples=["Best served slightly warm."],
    )
    important_notes: str | None = Field(
        default=None,
        max_length=1000,
        description="New optional especially important notes for the recipe.",
        examples=["Check with a skewer before removing from oven."],
    )
    category_id: int | None = Field(
        default=None,
        ge=1,
        description="New optional ID of the category for the recipe.",
        examples=[1],
    )
    ingredients: list[RecipeIngredientCreateRequest] | None = Field(
        default=None,
        description="Optional complete replacement list of ingredients.",
        examples=[
            [
                {
                    "position": 0,
                    "name": "Flour",
                    "note": "sifted",
                }
            ]
        ],
    )
    ingredient_groups: list[RecipeIngredientGroupRequest] | None = None
    steps: list[RecipeStepCreateRequest] | None = Field(
        default=None,
        description="Optional complete replacement list of preparation steps.",
        examples=[
            [
                {
                    "position": 0,
                    "instruction": "Mix all dry ingredients.",
                    "heading": "Day 1",
                    "is_important": False,
                    "note": "Do not overmix.",
                }
            ]
        ],
    )

    @field_validator("day_titles")
    @classmethod
    def normalize_day_titles(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else [title.strip() for title in value]

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return require_text_value(value, "title")

    @field_validator("summary", "origin_person", "history", "notes", "important_notes")
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text_value(value)

    @model_validator(mode="after")
    def validate_nested_positions(self) -> "RecipeUpdateRequest":
        if "category_id" in self.model_fields_set and self.category_id is None:
            raise ValueError("category_id must not be null")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title must not be null")

        if self.ingredient_groups is not None:
            group_positions = require_unique_values(
                [group.position for group in self.ingredient_groups],
                "ingredient group positions must be unique",
            )
            if self.ingredients is not None and any(ingredient.group_position is not None and ingredient.group_position not in group_positions for ingredient in self.ingredients):
                raise ValueError("ingredient group does not exist")
        if self.ingredients is not None:
            require_unique_values(
                [ingredient.position for ingredient in self.ingredients],
                "ingredient positions must be unique",
            )

        if self.steps is not None:
            require_unique_values(
                [step.position for step in self.steps], "step positions must be unique"
            )

        return self
