from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import authentication_error
from app.api.schemas.recipe_comment_schema import RecipeCommentResponse
from app.core.db import lock_sqlite_writes
from app.models.recipe_comment_model import RecipeComment
from app.models.recipe_model import Recipe
from app.models.user_model import User, UserRole


def _require_recipe(db_session: Session, recipe_id: int, *, for_create: bool = False) -> None:
    lock = {"read": True, "key_share": True} if for_create else None
    if db_session.get(Recipe, recipe_id, with_for_update=lock) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found.")


def list_comments(db_session: Session, recipe_id: int) -> list[RecipeCommentResponse]:
    _require_recipe(db_session, recipe_id)
    comments = db_session.scalars(
        select(RecipeComment)
        .options(joinedload(RecipeComment.author))
        .where(RecipeComment.recipe_id == recipe_id)
        .order_by(RecipeComment.created_at, RecipeComment.id)
    )
    return [RecipeCommentResponse.model_validate(comment) for comment in comments]


def create_comment(
    db_session: Session, recipe_id: int, current_user: User, text: str
) -> RecipeCommentResponse:
    lock_sqlite_writes(db_session)
    # Keep both parent rows valid until the insert also on SQLite without foreign keys.
    author = db_session.get(
        User,
        current_user.id,
        populate_existing=True,
        with_for_update={"read": True, "key_share": True},
    )
    if author is None or not author.is_active:
        raise authentication_error()
    _require_recipe(db_session, recipe_id, for_create=True)
    comment = RecipeComment(recipe_id=recipe_id, author=author, text=text)
    db_session.add(comment)
    db_session.flush()
    response = RecipeCommentResponse.model_validate(comment)
    db_session.commit()
    return response


def _get_comment_for_write(db_session: Session, recipe_id: int, comment_id: int) -> RecipeComment:
    lock_sqlite_writes(db_session)
    comment = db_session.scalar(
        select(RecipeComment)
        .where(RecipeComment.recipe_id == recipe_id, RecipeComment.id == comment_id)
        .with_for_update()
    )
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found.")
    return comment


def update_comment(
    db_session: Session, recipe_id: int, comment_id: int, current_user: User, text: str
) -> RecipeCommentResponse:
    comment = _get_comment_for_write(db_session, recipe_id, comment_id)
    if comment.author_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot edit this comment.")
    comment.text = text
    comment.edited_at = datetime.now(UTC)
    response = RecipeCommentResponse.model_validate(comment)
    db_session.commit()
    return response


def delete_comment(db_session: Session, recipe_id: int, comment_id: int, current_user: User) -> None:
    comment = _get_comment_for_write(db_session, recipe_id, comment_id)
    if comment.author_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot delete this comment.")
    db_session.delete(comment)
    db_session.commit()
