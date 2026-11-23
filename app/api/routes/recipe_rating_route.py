from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DbSession
from app.api.schemas.recipe_rating_schema import (
    RecipeRatingRequest,
    RecipeRatingSummary,
)
from app.services import recipe_rating_service

router = APIRouter(prefix="/recipes/{recipe_id}/ratings", tags=["recipe ratings"])


@router.get("")
def get_recipe_ratings(recipe_id: int, db_session: DbSession) -> RecipeRatingSummary:
    return recipe_rating_service.get_ratings(db_session, recipe_id)


@router.put("")
def save_recipe_rating(
    recipe_id: int,
    rating: RecipeRatingRequest,
    db_session: DbSession,
    current_user: CurrentUser,
) -> RecipeRatingSummary:
    return recipe_rating_service.save_rating(
        db_session, recipe_id, current_user.id, rating.stars
    )


@router.delete("")
def remove_recipe_rating(
    recipe_id: int, db_session: DbSession, current_user: CurrentUser
) -> RecipeRatingSummary:
    return recipe_rating_service.remove_rating(db_session, recipe_id, current_user.id)
