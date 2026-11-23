from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUser, DbSession
from app.api.schemas.recipe_comment_schema import (
    RecipeCommentRequest,
    RecipeCommentResponse,
)
from app.services import recipe_comment_service

router = APIRouter(prefix="/recipes/{recipe_id}/comments", tags=["recipe comments"])


@router.get("")
def list_comments(recipe_id: int, db_session: DbSession) -> list[RecipeCommentResponse]:
    return recipe_comment_service.list_comments(db_session, recipe_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_comment(
    recipe_id: int, request: RecipeCommentRequest, db_session: DbSession, current_user: CurrentUser
) -> RecipeCommentResponse:
    return recipe_comment_service.create_comment(db_session, recipe_id, current_user, request.text)


@router.put("/{comment_id}")
def update_comment(
    recipe_id: int,
    comment_id: int,
    request: RecipeCommentRequest,
    db_session: DbSession,
    current_user: CurrentUser,
) -> RecipeCommentResponse:
    return recipe_comment_service.update_comment(
        db_session, recipe_id, comment_id, current_user, request.text
    )


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    recipe_id: int, comment_id: int, db_session: DbSession, current_user: CurrentUser
) -> Response:
    recipe_comment_service.delete_comment(db_session, recipe_id, comment_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
