import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.security import hash_session_token
from app.models.session_model import UserSession
from app.models.user_model import User, UserRole

DbSession = Annotated[Session, Depends(get_db)]
SessionToken = Annotated[
    str | None,
    Cookie(alias=settings.session_cookie_name),
]


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
    )


def delete_session(*, db_session: Session, user_session: UserSession) -> None:
    db_session.delete(user_session)
    db_session.commit()


def get_current_session(
    db_session: DbSession,
    session_token: SessionToken = None,
) -> UserSession:
    if session_token is None:
        raise authentication_error()

    token_hash = hash_session_token(session_token)
    user_session = db_session.scalar(
        select(UserSession).where(UserSession.token_hash == token_hash)
    )
    if user_session is None:
        raise authentication_error()

    expires_at = user_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at <= datetime.now(UTC):
        delete_session(db_session=db_session, user_session=user_session)
        raise authentication_error()

    return user_session


CurrentSession = Annotated[UserSession, Depends(get_current_session)]


def get_current_user(
    user_session: CurrentSession,
    db_session: DbSession,
) -> User:
    user = db_session.get(User, user_session.user_id)
    if user is None or not user.is_active:
        delete_session(db_session=db_session, user_session=user_session)
        raise authentication_error()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_optional_user(db_session: DbSession, session_token: SessionToken = None) -> User | None:
    if session_token is None:
        return None
    try:
        return get_current_user(get_current_session(db_session, session_token), db_session)
    except HTTPException:
        return None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]

_ROLE_RANK: dict[UserRole, int] = {
    UserRole.READER: 0,
    UserRole.EDITOR: 1,
    UserRole.ADMIN: 2,
}


def require_role(minimum_role: UserRole):
    def role_dependency(current_user: CurrentUser) -> User:
        if _ROLE_RANK[current_user.role] < _ROLE_RANK[minimum_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your role does not allow this action.",
            )
        return current_user

    return role_dependency


RequireEditor = Annotated[User, Depends(require_role(UserRole.EDITOR))]
RequireAdmin = Annotated[User, Depends(require_role(UserRole.ADMIN))]


def get_expected_recipe_version(
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> int:
    if if_match is None:
        raise HTTPException(status_code=428, detail="If-Match header required.")
    matched = re.fullmatch(r'"([1-9][0-9]*)"', if_match.strip())
    if matched is None:
        raise HTTPException(status_code=400, detail="Invalid recipe If-Match header.")
    return int(matched.group(1))


ExpectedRecipeVersion = Annotated[int, Depends(get_expected_recipe_version)]
