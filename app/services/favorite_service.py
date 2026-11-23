from datetime import UTC, datetime
from unicodedata import combining, normalize

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas.favorite_schema import (
    FavoriteCreateRequest,
    FavoriteResponse,
    FavoriteSort,
)
from app.core.db import lock_sqlite_writes
from app.models.favorite_model import Favorite
from app.models.recipe_model import Recipe
from app.models.user_model import User


def create_favorite(
    *,
    db_session: Session,
    user_id: int,
    favorite_create_request: FavoriteCreateRequest,
) -> FavoriteResponse:
    recipe = db_session.get(Recipe, favorite_create_request.recipe_id)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipe not found.",
        )

    favorite = Favorite(
        user_id=user_id,
        recipe_id=favorite_create_request.recipe_id,
        created_at=datetime.now(UTC),
    )
    db_session.add(favorite)

    try:
        db_session.commit()
    except IntegrityError as error:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recipe is already marked as favorite.",
        ) from error

    return FavoriteResponse.model_validate(favorite)


def list_favorites(
    *,
    db_session: Session,
    user_id: int,
    sort: FavoriteSort = "recent",
) -> list[FavoriteResponse]:
    statement = select(Favorite).where(Favorite.user_id == user_id)
    if sort == "name":
        rows = db_session.execute(
            statement.add_columns(Recipe.title, Recipe.created_at).join(Favorite.recipe)
        )
        ordered_rows = sorted(
            rows,
            key=lambda row: (_title_key(row.title), row.created_at, row[0].recipe_id),
        )
        favorites = [favorite for favorite, _, _ in ordered_rows]
    elif sort == "manual":
        # Unpositioned favorites follow the saved order in insertion order.
        favorites = db_session.scalars(
            statement.order_by(Favorite.position.asc().nulls_last(), Favorite.id)
        )
    else:
        favorites = db_session.scalars(
            statement.order_by(
                Favorite.created_at.desc().nulls_last(), Favorite.id.desc()
            )
        )
    return [FavoriteResponse.model_validate(favorite) for favorite in favorites]


def _title_key(title: str) -> str:
    return "".join(
        char for char in normalize("NFD", title.casefold()) if not combining(char)
    )


def set_favorite_order(
    *,
    db_session: Session,
    user_id: int,
    favorite_ids: list[int],
) -> list[FavoriteResponse]:
    lock_sqlite_writes(db_session)
    # Account deletion locks the user before cascading to its favorites.
    owner = db_session.scalar(
        select(User.id).where(User.id == user_id, User.is_active).with_for_update()
    )
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User account is no longer active.",
        )

    favorites = {
        favorite.id: favorite
        for favorite in db_session.scalars(
            select(Favorite)
            .where(Favorite.user_id == user_id)
            .order_by(Favorite.id)
            .with_for_update()
        )
    }
    if favorites.keys() != set(favorite_ids):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Favorites have changed. Reload before saving their order.",
        )

    ordered_favorites = [favorites[favorite_id] for favorite_id in favorite_ids]
    for position, favorite in enumerate(ordered_favorites):
        favorite.position = position
    result = [
        FavoriteResponse.model_validate(favorite) for favorite in ordered_favorites
    ]
    db_session.commit()
    return result


def get_favorite(
    *,
    db_session: Session,
    user_id: int,
    favorite_id: int,
) -> FavoriteResponse:
    favorite = db_session.scalar(
        select(Favorite).where(
            Favorite.id == favorite_id,
            Favorite.user_id == user_id,
        )
    )
    if favorite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite not found.",
        )

    return FavoriteResponse.model_validate(favorite)


def delete_favorite(
    *,
    db_session: Session,
    user_id: int,
    favorite_id: int,
) -> None:
    favorite = db_session.scalar(
        select(Favorite).where(
            Favorite.id == favorite_id,
            Favorite.user_id == user_id,
        )
    )
    if favorite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite not found.",
        )

    db_session.delete(favorite)
    db_session.commit()
