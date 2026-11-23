from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, RequireAdmin
from app.api.schemas import (
    UserCreateRequest,
    UserCreateResponse,
    UserGetResponse,
    UserListResponse,
    UserUpdateRequest,
    UserUpdateResponse,
)
from app.api.schemas.user_schema import ViewPreferences, ViewPreferencesUpdate
from app.core.db import get_db
from app.services import password_reset_service, user_service, view_preferences_service

router = APIRouter(prefix="/users", tags=["users"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/{user_id}/view-preferences")
def get_view_preferences(
    user_id: int, current_user: CurrentUser, db_session: DbSession, response: Response
) -> ViewPreferences:
    if user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="View preferences belong to another account."
        )
    response.headers["Cache-Control"] = "no-store"
    return view_preferences_service.get_view_preferences(db_session, current_user)


@router.patch("/{user_id}/view-preferences", status_code=status.HTTP_204_NO_CONTENT)
def update_view_preferences(
    user_id: int,
    request: ViewPreferencesUpdate,
    current_user: CurrentUser,
    db_session: DbSession,
) -> None:
    if user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="View preferences belong to another account."
        )
    view_preferences_service.update_view_preferences(db_session, current_user, request)


@router.post(
    "",
    response_model=UserCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
    description="Creates a new user and returns the saved user data.",
)
def create_user(
    user_create_request: UserCreateRequest,
    db_session: DbSession,
    current_user: RequireAdmin,
    background_tasks: BackgroundTasks,
) -> UserCreateResponse:
    return user_service.create_user(
        db_session=db_session,
        user_create_request=user_create_request,
        background_tasks=background_tasks,
    )


@router.get(
    "",
    response_model=list[UserListResponse],
    summary="List users",
    description="Returns all users.",
)
def list_users(db_session: DbSession, current_user: RequireAdmin) -> list[UserListResponse]:
    return user_service.list_users(db_session=db_session)


@router.get(
    "/{user_id}",
    response_model=UserGetResponse,
    summary="Get user",
    description="Returns one user by its ID.",
)
def get_user(
    user_id: int,
    db_session: DbSession,
    current_user: RequireAdmin,
) -> UserGetResponse:
    return user_service.get_user(
        db_session=db_session,
        user_id=user_id,
    )


@router.post("/{user_id}/password-reset", status_code=status.HTTP_204_NO_CONTENT)
def send_password_reset(
    user_id: int, db_session: DbSession, current_user: RequireAdmin
) -> None:
    password_reset_service.request_admin_reset(db_session, user_id)


@router.put(
    "/{user_id}",
    response_model=UserUpdateResponse,
    summary="Update user",
    description="Updates one user by its ID and returns the updated data.",
)
def update_user(
    user_id: int,
    user_update_request: UserUpdateRequest,
    db_session: DbSession,
    current_user: RequireAdmin,
    background_tasks: BackgroundTasks,
) -> UserUpdateResponse:
    return user_service.update_user(
        db_session=db_session,
        user_id=user_id,
        user_update_request=user_update_request,
        actor_id=current_user.id,
        background_tasks=background_tasks,
    )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Deletes one user by its ID.",
)
def delete_user(
    user_id: int,
    db_session: DbSession,
    current_user: RequireAdmin,
) -> Response:
    user_service.delete_user(
        db_session=db_session,
        user_id=user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{user_id}/registration",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reject pending registration",
    description="Permanently deletes a registration that is still awaiting admin approval.",
)
def reject_registration(user_id: int, db_session: DbSession, current_user: RequireAdmin) -> None:
    user_service.delete_user(db_session=db_session, user_id=user_id, pending_only=True)
