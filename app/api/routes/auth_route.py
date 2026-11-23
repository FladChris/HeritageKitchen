from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import EmailStr, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentSession, CurrentUser, delete_session
from app.api.schemas import (
    PasswordChangeRequest,
    UserCreateResponse,
    UserLoginRequest,
    UserRegistrationRequest,
    UserResponse,
)
from app.api.schemas.base_schema import BaseRequest
from app.api.schemas.user_schema import ProfileUpdateRequest
from app.core.config import settings
from app.core.db import get_db
from app.core.rate_limit import enforce_login_rate_limit
from app.services import (
    auth_service,
    email_verification_service,
    password_reset_service,
    smtp_service,
    user_service,
)

router = APIRouter(prefix="/auth", tags=["auth"])
DbSession = Annotated[Session, Depends(get_db)]


def cookie_secure(request: Request) -> bool:
    mode = settings.session_cookie_secure
    if mode == "true":
        return True
    if mode == "false":
        return False
    return request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"


class ResetRequest(BaseRequest):
    email: EmailStr


class MailTokenRequest(BaseRequest):
    token: str = Field(min_length=1, max_length=255)


class ResetPasswordRequest(MailTokenRequest):
    new_password: str = Field(min_length=8, max_length=255)


@router.get("/reset-available")
@router.get("/email-available")
def reset_available(db_session: DbSession, response: Response) -> dict[str, bool | str]:
    response.headers["Cache-Control"] = "no-store"
    available, hint = smtp_service.account_mail_availability(db_session)
    result: dict[str, bool | str] = {"available": available}
    if hint is not None:
        result["hint"] = hint
    return result


@router.post(
    "/verify-email", status_code=204, dependencies=[Depends(enforce_login_rate_limit)]
)
def verify_email(data: MailTokenRequest, db_session: DbSession) -> None:
    email_verification_service.verify_email(db_session, data.token)


@router.post(
    "/reset-request", status_code=204, dependencies=[Depends(enforce_login_rate_limit)]
)
def request_password_reset(
    data: ResetRequest, db_session: DbSession, background_tasks: BackgroundTasks
) -> None:
    # SMTP latency must not reveal whether the submitted address belongs to an account.
    background_tasks.add_task(
        password_reset_service.request_reset, db_session, str(data.email)
    )


@router.post(
    "/reset-password", status_code=204, dependencies=[Depends(enforce_login_rate_limit)]
)
def reset_password(data: ResetPasswordRequest, db_session: DbSession) -> None:
    password_reset_service.reset_password(db_session, data.token, data.new_password)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Returns the currently authenticated user.",
)
def get_me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse, summary="Update the current user's profile")
def update_me(
    data: ProfileUpdateRequest, current_user: CurrentUser, db_session: DbSession,
    background_tasks: BackgroundTasks,
) -> UserResponse:
    return user_service.update_profile(db_session, current_user.id, data, background_tasks)


@router.post("/me/image", response_model=UserResponse, summary="Set the current user's profile image")
def set_my_image(
    image: Annotated[UploadFile, File()], current_user: CurrentUser, db_session: DbSession
) -> UserResponse:
    return user_service.set_profile_image(db_session, current_user.id, image)


@router.delete("/me/image", response_model=UserResponse, summary="Remove the current user's profile image")
def remove_my_image(current_user: CurrentUser, db_session: DbSession) -> UserResponse:
    return user_service.set_profile_image(db_session, current_user.id, None)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change current user's password",
)
def change_password(
    password_request: PasswordChangeRequest,
    current_user: CurrentUser,
    user_session: CurrentSession,
    db_session: DbSession,
) -> None:
    auth_service.change_password(
        db_session=db_session,
        user=current_user,
        user_session=user_session,
        password_request=password_request,
    )


@router.post(
    "/login",
    response_model=UserResponse,
    summary="Log in user",
    description="Authenticates a user and starts a server-side session.",
    dependencies=[Depends(enforce_login_rate_limit)],
)
def login_user(
    login_request: UserLoginRequest,
    request: Request,
    response: Response,
    db_session: DbSession,
) -> UserResponse:
    user, session_token = auth_service.login_user(
        db_session=db_session,
        login_request=login_request,
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        max_age=settings.session_lifetime_days * 24 * 60 * 60,
        httponly=settings.session_cookie_httponly,
        secure=cookie_secure(request),
        samesite=settings.session_cookie_samesite,
        path=settings.session_cookie_path,
    )
    return user


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out user",
    description="Ends the current user session and removes its cookie.",
)
def logout_user(
    request: Request,
    response: Response,
    user_session: CurrentSession,
    db_session: DbSession,
) -> None:
    delete_session(db_session=db_session, user_session=user_session)
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=settings.session_cookie_httponly,
        secure=cookie_secure(request),
        samesite=settings.session_cookie_samesite,
        path=settings.session_cookie_path,
    )
    response.status_code = status.HTTP_204_NO_CONTENT


@router.get("/registration-status", summary="Get registration setup status")
def registration_status(db_session: DbSession, response: Response) -> dict[str, bool]:
    response.headers["Cache-Control"] = "no-store"
    return {"first_account": auth_service.is_first_account(db_session=db_session)}


@router.post(
    "/register",
    response_model=UserCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register user",
    description="Registers the first user as an active admin and later users as pending editors.",
)
def register_user(
    registration_request: UserRegistrationRequest,
    db_session: DbSession,
    background_tasks: BackgroundTasks,
) -> UserCreateResponse:
    return auth_service.register_user(
        db_session=db_session,
        registration_request=registration_request,
        background_tasks=background_tasks,
    )
