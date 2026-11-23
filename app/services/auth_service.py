from datetime import UTC, datetime, timedelta

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    PasswordChangeRequest,
    UserCreateResponse,
    UserLoginRequest,
    UserRegistrationRequest,
    UserResponse,
)
from app.core.config import settings
from app.core.db import lock_user_writes
from app.core.security import (
    create_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.models.password_reset_model import PasswordReset
from app.models.session_model import UserSession
from app.models.user_model import User, UserRole
from app.services.email_verification_service import require_available_email, set_email
from app.services.login_identifiers import (
    find_login_user_id,
    require_available_identifiers,
)


def is_first_account(*, db_session: Session) -> bool:
    return db_session.scalar(select(User.id).limit(1)) is None


def register_user(
    *,
    db_session: Session,
    registration_request: UserRegistrationRequest,
    background_tasks: BackgroundTasks | None = None,
) -> UserCreateResponse:
    password_hash = hash_password(registration_request.password)
    # Serialize first-account and identifier checks with concurrent account writes.
    lock_user_writes(db_session)
    require_available_email(db_session, registration_request.email)
    require_available_identifiers(
        db_session, username=registration_request.username, email=registration_request.email
    )
    first_user = is_first_account(db_session=db_session)

    user = User(
        username=registration_request.username,
        password_hash=password_hash,
        role=UserRole.ADMIN if first_user else UserRole.EDITOR,
        is_active=first_user,
        pending_approval=not first_user,
    )
    db_session.add(user)
    set_email(db_session, user, registration_request.email, background_tasks=background_tasks)

    try:
        db_session.commit()
    except IntegrityError as error:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered.",
        ) from error

    return UserCreateResponse.model_validate(user)


def create_user_session(*, db_session: Session, user_id: int) -> str:
    session_token = create_session_token()
    user_session = UserSession(
        user_id=user_id,
        token_hash=hash_session_token(session_token),
        expires_at=datetime.now(UTC) + timedelta(days=settings.session_lifetime_days),
    )
    db_session.add(user_session)
    db_session.commit()
    return session_token


def login_user(
    *,
    db_session: Session,
    login_request: UserLoginRequest,
) -> tuple[UserResponse, str]:
    user_id = find_login_user_id(db_session, login_request.username)
    user = db_session.get(User, user_id) if user_id is not None else None

    if (
        user is None
        or not verify_password(login_request.password, user.password_hash)
        or not user.is_active
    ):
        raise _invalid_login()

    # Recheck after password verification in case the credentials or account changed.
    password_hash = user.password_hash
    lock_user_writes(db_session)
    if find_login_user_id(db_session, login_request.username) != user_id:
        raise _invalid_login()
    user = db_session.get(User, user_id, populate_existing=True)
    if user is None or not user.is_active or user.password_hash != password_hash:
        raise _invalid_login()

    session_token = create_user_session(db_session=db_session, user_id=user.id)
    return UserResponse.model_validate(user), session_token


def _invalid_login() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password.",
    )


def change_password(
    *, db_session: Session, user: User, user_session: UserSession,
    password_request: PasswordChangeRequest,
) -> None:
    if not verify_password(password_request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    if password_request.new_password == password_request.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from current password.",
        )

    verified_hash = user.password_hash
    new_hash = hash_password(password_request.new_password)
    # Recheck under the account write lock: a concurrent reset or admin password
    # set must not be overwritten by a request verified against the old password.
    lock_user_writes(db_session)
    user = db_session.get(User, user.id, populate_existing=True)
    session_still_valid = db_session.scalar(
        select(UserSession.id).where(UserSession.id == user_session.id)
    )
    if user is None or not user.is_active or session_still_valid is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    if user.password_hash != verified_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The password was changed in the meantime.",
        )

    user.password_hash = new_hash
    db_session.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    db_session.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.id != user_session.id,
        )
    )
    db_session.commit()
