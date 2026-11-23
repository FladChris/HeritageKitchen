from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.api.dependencies import authentication_error
from app.api.schemas.recipe_rating_schema import RecipeRatingEntry, RecipeRatingSummary
from app.core.db import lock_sqlite_writes
from app.models import Recipe, RecipeRating, User


def _recipe_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found."
    )


def get_ratings(db: Session, recipe_id: int) -> RecipeRatingSummary:
    rows = db.execute(
        select(User.username, RecipeRating.half_stars)
        .select_from(Recipe)
        .outerjoin(RecipeRating, RecipeRating.recipe_id == Recipe.id)
        .outerjoin(User, User.id == RecipeRating.user_id)
        .where(Recipe.id == recipe_id)
        .order_by(User.username)
    ).all()
    if not rows:
        raise _recipe_not_found()
    if rows[0].half_stars is None:
        return RecipeRatingSummary(average=None, count=0, ratings=[])

    ratings = [
        RecipeRatingEntry(username=username, stars=half_stars / 2)
        for username, half_stars in rows
    ]
    count = len(ratings)

    total = sum(half_stars for _, half_stars in rows)
    # Round the mean in half-star units, rounding exact ties up.
    rounded_half_stars = (2 * total + count) // (2 * count)
    return RecipeRatingSummary(
        average=rounded_half_stars / 2, count=count, ratings=ratings
    )


def _lock_rating_parents(db: Session, recipe_id: int, user_id: int) -> None:
    lock_sqlite_writes(db)
    # Block deactivation and deletion while the rating is being written.
    active_user_id = db.scalar(
        select(User.id)
        .where(User.id == user_id, User.is_active)
        .with_for_update(read=True)
    )
    if active_user_id is None:
        raise authentication_error()
    existing_recipe_id = db.scalar(
        select(Recipe.id)
        .where(Recipe.id == recipe_id)
        .with_for_update(read=True, key_share=True)
    )
    if existing_recipe_id is None:
        raise _recipe_not_found()


def save_rating(
    db: Session, recipe_id: int, user_id: int, stars: float
) -> RecipeRatingSummary:
    _lock_rating_parents(db, recipe_id, user_id)
    insert = (
        sqlite_insert if db.get_bind().dialect.name == "sqlite" else postgresql_insert
    )
    half_stars = int(stars * 2)
    db.execute(
        insert(RecipeRating)
        .values(recipe_id=recipe_id, user_id=user_id, half_stars=half_stars)
        .on_conflict_do_update(
            index_elements=[RecipeRating.recipe_id, RecipeRating.user_id],
            set_={"half_stars": half_stars},
        )
    )
    result = get_ratings(db, recipe_id)
    db.commit()
    return result


def remove_rating(db: Session, recipe_id: int, user_id: int) -> RecipeRatingSummary:
    _lock_rating_parents(db, recipe_id, user_id)
    db.execute(
        delete(RecipeRating).where(
            RecipeRating.recipe_id == recipe_id,
            RecipeRating.user_id == user_id,
        )
    )
    result = get_ratings(db, recipe_id)
    db.commit()
    return result
