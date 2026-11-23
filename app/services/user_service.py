from fastapi import BackgroundTasks, HTTPException, UploadFile, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.api.schemas import UserCreateRequest, UserUpdateRequest
from app.api.schemas.user_schema import (
    ProfileUpdateRequest,
    UserCreateResponse,
    UserGetResponse,
    UserListResponse,
    UserResponse,
    UserUpdateResponse,
)
from app.core.db import lock_user_writes
from app.core.security import hash_password, verify_password
from app.models.favorite_model import Favorite
from app.models.password_reset_model import PasswordReset
from app.models.recipe_comment_model import RecipeComment
from app.models.recipe_rating_model import RecipeRating
from app.models.session_model import UserSession
from app.models.user_model import (
    User,
    UserCategoryPosition,
    UserRecipePosition,
    UserRole,
)
from app.services.email_verification_service import require_available_email, set_email
from app.services.login_identifiers import require_available_identifiers
from app.services.recipe_image_service import remove_stored_upload, store_upload


def create_user(
    *,
    db_session: Session,
    user_create_request: UserCreateRequest,
    background_tasks: BackgroundTasks | None = None,
) -> UserCreateResponse:
    password_hash = hash_password(user_create_request.password)
    lock_user_writes(db_session)
    require_available_email(db_session, user_create_request.email)
    require_available_identifiers(
        db_session, username=user_create_request.username, email=user_create_request.email
    )
    user = User(
        username=user_create_request.username,
        password_hash=password_hash,
        role=user_create_request.role,
        is_active=user_create_request.is_active,
        pending_approval=False,
    )
    db_session.add(user)
    set_email(db_session, user, user_create_request.email, background_tasks=background_tasks)
    db_session.commit()
    return UserCreateResponse.model_validate(user)


def list_users(*, db_session: Session) -> list[UserListResponse]:
    users = db_session.scalars(select(User).order_by(User.username))
    return [UserListResponse.model_validate(user) for user in users]


def get_user(*, db_session: Session, user_id: int) -> UserGetResponse:
    user = db_session.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return UserGetResponse.model_validate(user)


def _require_another_active_admin(db_session: Session, user: User) -> None:
    if user.role != UserRole.ADMIN or not user.is_active:
        return
    other_admin = db_session.scalar(
        select(User.id)
        .where(User.id != user.id, User.role == UserRole.ADMIN, User.is_active)
        .limit(1)
    )
    if other_admin is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="At least one administrator account must remain active.",
        )


def _active_profile_for_update(db_session: Session, user_id: int) -> User:
    lock_user_writes(db_session)
    user = db_session.get(User, user_id, populate_existing=True)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    return user


def update_profile(
    db_session: Session, user_id: int, request: ProfileUpdateRequest,
    background_tasks: BackgroundTasks | None = None,
) -> UserResponse:
    user = _active_profile_for_update(db_session, user_id)
    _update_identifiers(db_session, user, request, user, background_tasks)
    db_session.commit()
    return UserResponse.model_validate(user)


def _update_identifiers(
    db_session: Session, user: User, request: ProfileUpdateRequest,
    actor: User | None, background_tasks: BackgroundTasks | None,
) -> None:
    username = request.username
    email = request.email
    update_email = "email" in request.model_fields_set and (
        email != user.email or (email is not None and user.email_verified_at is None)
    )
    if "email" in request.model_fields_set:
        require_available_email(db_session, email)
    if update_email:
        if not request.current_password:
            raise HTTPException(status_code=422, detail="Gib dein aktuelles Passwort ein.")
        if actor is None or not actor.is_active or not verify_password(request.current_password, actor.password_hash):
            raise HTTPException(status_code=400, detail="Das aktuelle Passwort ist falsch.")

    require_available_identifiers(
        db_session,
        username=username if username != user.username else None,
        email=email if email != user.email else None,
        exclude_user_id=user.id,
    )
    if username is not None:
        user.username = username
    if update_email:
        set_email(db_session, user, email, background_tasks=background_tasks)


def set_profile_image(
    db_session: Session, user_id: int, image: UploadFile | None
) -> UserResponse:
    new_path = store_upload(image, f"profiles/{user_id}", profile=True) if image is not None else None
    try:
        user = _active_profile_for_update(db_session, user_id)
        old_path = user.profile_image_path
        user.profile_image_path = new_path
        db_session.commit()
    except Exception:
        db_session.rollback()
        remove_stored_upload(new_path)
        raise

    remove_stored_upload(old_path)
    return UserResponse.model_validate(user)


def update_user(
    *,
    db_session: Session,
    user_id: int,
    user_update_request: UserUpdateRequest,
    actor_id: int | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> UserUpdateResponse:
    lock_user_writes(db_session)
    user = db_session.get(User, user_id, populate_existing=True)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    actor = (
        db_session.get(User, actor_id, populate_existing=True)
        if actor_id is not None and "email" in user_update_request.model_fields_set
        else None
    )
    _update_identifiers(db_session, user, user_update_request, actor, background_tasks)
    update_data = user_update_request.model_dump(
        exclude_unset=True, exclude={"username", "email", "current_password"}
    )
    password = update_data.pop("password", None)
    activating = update_data.get("is_active") is True
    deactivating = update_data.get("is_active") is False
    # Any status change ends old sessions so reactivation never revives them.
    status_changed = "is_active" in update_data and update_data["is_active"] != user.is_active
    if deactivating or update_data.get("role", user.role) != UserRole.ADMIN:
        _require_another_active_admin(db_session, user)

    for field_name, field_value in update_data.items():
        setattr(user, field_name, field_value)

    if activating:
        user.pending_approval = False

    if password is not None:
        user.password_hash = hash_password(password)
        db_session.execute(
            delete(PasswordReset).where(PasswordReset.user_id == user.id)
        )
    if status_changed or password is not None:
        db_session.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
        db_session.execute(delete(UserSession).where(UserSession.user_id == user.id))

    db_session.commit()
    return UserUpdateResponse.model_validate(user)


def delete_user(*, db_session: Session, user_id: int, pending_only: bool = False) -> None:
    lock_user_writes(db_session)
    user = db_session.get(User, user_id, populate_existing=True)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if pending_only and (not user.pending_approval or user.is_active):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending registrations can be rejected.",
        )

    _require_another_active_admin(db_session, user)
    image_path = user.profile_image_path
    # Remove personal rows even when SQLite does not enforce foreign keys.
    for model in (
        Favorite, UserCategoryPosition, UserRecipePosition, UserSession, PasswordReset, RecipeRating
    ):
        db_session.execute(delete(model).where(model.user_id == user.id))
    # Recipes and comments remain after the account is deleted.
    db_session.execute(
        update(RecipeComment).where(RecipeComment.author_id == user.id).values(author_id=None)
    )
    db_session.execute(delete(User).where(User.id == user.id))
    db_session.commit()
    remove_stored_upload(image_path)
