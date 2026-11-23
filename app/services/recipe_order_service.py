from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.schemas.recipe_order_schema import RecipeOrderRequest
from app.models.category_model import Category
from app.models.recipe_model import Recipe
from app.models.user_model import User, UserRecipePosition


def set_recipe_order(*, db_session: Session, user: User, order: RecipeOrderRequest) -> None:
    if db_session.get(Category, order.category_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    current_ids = set(
        db_session.scalars(select(Recipe.id).where(Recipe.category_id == order.category_id))
    )
    if set(order.recipe_ids) != current_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recipes have changed. Reload before saving their order.",
        )
    db_session.execute(
        delete(UserRecipePosition).where(
            UserRecipePosition.user_id == user.id, UserRecipePosition.recipe_id.in_(current_ids)
        )
    )
    db_session.add_all(
        UserRecipePosition(user_id=user.id, recipe_id=recipe_id, position=position)
        for position, recipe_id in enumerate(order.recipe_ids)
    )
    db_session.commit()


def place_recipe_last(db_session: Session, recipe_id: int, category_id: int | None) -> None:
    """Drop the recipe from all personal orders, then append it where a user ordered its category."""
    # Also remove positions on SQLite, where foreign keys may be disabled.
    db_session.execute(
        delete(UserRecipePosition).where(UserRecipePosition.recipe_id == recipe_id)
    )
    if category_id is None:
        return
    last_positions = db_session.execute(
        select(UserRecipePosition.user_id, func.max(UserRecipePosition.position))
        .join(Recipe, Recipe.id == UserRecipePosition.recipe_id)
        .where(Recipe.category_id == category_id)
        .group_by(UserRecipePosition.user_id)
    ).all()
    db_session.add_all(
        UserRecipePosition(user_id=user_id, recipe_id=recipe_id, position=last + 1)
        for user_id, last in last_positions
    )
