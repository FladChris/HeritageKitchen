from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.api.schemas.favorite_schema import (
    FavoriteCreateRequest,
    FavoriteOrderRequest,
    FavoritePreferences,
    FavoritePreferencesUpdate,
    FavoriteResponse,
    FavoriteSort,
)
from app.core.db import get_db
from app.models.user_model import User
from app.services import favorite_service

router = APIRouter(prefix="/favorites", tags=["favorites"])
DbSession = Annotated[Session, Depends(get_db)]


def get_expected_user(
    current_user: CurrentUser, expected_user_id: int | None = None
) -> User:
    if expected_user_id is not None and current_user.id != expected_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The signed-in account has changed.",
        )
    return current_user


ExpectedUser = Annotated[User, Depends(get_expected_user)]


@router.post(
    "",
    response_model=FavoriteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create favorite",
    description="Creates a new favorite and returns the saved favorite data.",
)
def create_favorite(
    favorite_create_request: FavoriteCreateRequest,
    db_session: DbSession,
    current_user: ExpectedUser,
) -> FavoriteResponse:
    return favorite_service.create_favorite(
        db_session=db_session,
        user_id=current_user.id,
        favorite_create_request=favorite_create_request,
    )


@router.get(
    "",
    response_model=list[FavoriteResponse],
    summary="List favorites",
    description="Returns all favorites of the currently authenticated user.",
)
def list_favorites(
    db_session: DbSession,
    current_user: ExpectedUser,
    response: Response,
    sort: FavoriteSort | None = None,
) -> list[FavoriteResponse]:
    response.headers["Cache-Control"] = "no-store"
    return favorite_service.list_favorites(
        db_session=db_session,
        user_id=current_user.id,
        sort=sort or current_user.favorite_sort or "recent",
    )


@router.get("/preferences", summary="Get personal favorite preferences")
def get_favorite_preferences(
    current_user: ExpectedUser, response: Response
) -> FavoritePreferences:
    response.headers["Cache-Control"] = "no-store"
    return FavoritePreferences(
        sort=current_user.favorite_sort or "recent",
        recipe_view=current_user.recipe_view or "list",
    )


@router.patch(
    "/preferences",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update personal favorite preferences",
)
def update_favorite_preferences(
    request: FavoritePreferencesUpdate,
    db_session: DbSession,
    current_user: ExpectedUser,
) -> None:
    if "sort" in request.model_fields_set:
        current_user.favorite_sort = request.sort
    if "recipe_view" in request.model_fields_set:
        current_user.recipe_view = request.recipe_view
    db_session.commit()


@router.put("/order", summary="Save personal favorite order")
def set_favorite_order(
    request: FavoriteOrderRequest,
    db_session: DbSession,
    current_user: ExpectedUser,
    response: Response,
) -> list[FavoriteResponse]:
    response.headers["Cache-Control"] = "no-store"
    return favorite_service.set_favorite_order(
        db_session=db_session,
        user_id=current_user.id,
        favorite_ids=request.favorite_ids,
    )


@router.get(
    "/{favorite_id}",
    response_model=FavoriteResponse,
    summary="Get favorite",
    description="Returns one favorite of the currently authenticated user.",
)
def get_favorite(
    favorite_id: int,
    db_session: DbSession,
    current_user: ExpectedUser,
    response: Response,
) -> FavoriteResponse:
    response.headers["Cache-Control"] = "no-store"
    return favorite_service.get_favorite(
        db_session=db_session,
        user_id=current_user.id,
        favorite_id=favorite_id,
    )


@router.delete(
    "/{favorite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete favorite",
    description="Deletes one favorite of the currently authenticated user.",
)
def delete_favorite(
    favorite_id: int,
    db_session: DbSession,
    current_user: ExpectedUser,
) -> Response:
    favorite_service.delete_favorite(
        db_session=db_session,
        user_id=current_user.id,
        favorite_id=favorite_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
