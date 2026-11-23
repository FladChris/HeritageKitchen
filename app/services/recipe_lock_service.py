from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import ScalarSelect

from app.core.db import lock_sqlite_writes
from app.models.recipe_model import Recipe, RecipeIngredient

RECIPE_FIELDS = (
    "title", "summary", "preparation_time", "cooking_time", "cooking_time_max",
    "rest_time", "rest_time_max", "servings", "history", "preparation_days", "day_titles",
    "origin_person", "notes", "important_notes", "category_id",
)
GROUP_FIELDS = ("position", "name")
INGREDIENT_FIELDS = ("position", "name", "unit", "note", "group_position")
STEP_FIELDS = ("position", "instruction", "heading", "is_important", "note")
STEP_TIME_FIELDS = ("duration_minutes", "time_kind")
IMAGE_FIELDS = ("file_path", "alt_text", "is_main")


def lock_recipe(
    db: Session, recipe_id: int | ScalarSelect[int], *, not_found: str = "Recipe not found.",
) -> Recipe:
    lock_sqlite_writes(db)
    recipe = db.scalar(select(Recipe).where(Recipe.id == recipe_id).with_for_update(key_share=True))
    if recipe is None:
        raise HTTPException(404, not_found)
    return recipe


def require_recipe_version(db: Session, recipe: Recipe, expected_version: int) -> None:
    """Check the client precondition after acquiring the recipe write lock."""
    if recipe.version != expected_version:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "recipe_version_conflict",
                "expected_version": expected_version,
                "current_version": recipe.version,
                "current": _current_state(db, recipe),
            },
        )


def _fields(row, names) -> dict:
    return {name: getattr(row, name) for name in names}


def _current_state(db: Session, recipe: Recipe) -> dict:
    # Numeric ingredient amounts must match the values rounded by the database.
    ingredients = db.scalars(
        select(RecipeIngredient)
        .where(RecipeIngredient.recipe_id == recipe.id)
        .order_by(RecipeIngredient.position, RecipeIngredient.id)
        .execution_options(populate_existing=True)
    )
    return {
        **_fields(recipe, RECIPE_FIELDS),
        "category_name": recipe.category.name if recipe.category else None,
        "ingredient_groups": [
            _fields(group, GROUP_FIELDS)
            for group in sorted(recipe.ingredient_groups, key=lambda group: (group.position, group.id))
        ],
        "ingredients": [
            dict(_fields(item, INGREDIENT_FIELDS), amount=None if item.amount is None else format(item.amount, ".3f"))
            for item in ingredients
        ],
        "steps": [
            _fields(step, STEP_FIELDS + STEP_TIME_FIELDS + ("day",))
            for step in sorted(recipe.steps, key=lambda step: (step.position, step.id))
        ],
        "images": [
            _fields(image, IMAGE_FIELDS)
            for image in sorted(recipe.images, key=lambda image: (image.position, image.id))
        ],
    }
