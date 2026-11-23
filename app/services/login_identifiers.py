from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_model import User
from app.services.smtp_service import get_account_mail_settings


def require_available_identifiers(
    db_session: Session,
    *,
    username: str | None = None,
    email: str | None = None,
    exclude_user_id: int | None = None,
) -> None:
    """Check new identifiers while the caller holds the user write lock."""
    identifiers = {value.casefold() for value in (username, email) if value}
    if not identifiers:
        return

    query = select(User.username, User.email)
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    # SQLite LOWER() only folds ASCII. Use the same Unicode comparison on both databases.
    for existing_username, existing_email in db_session.execute(query):
        if existing_username.casefold() in identifiers or (
            existing_email and existing_email.casefold() in identifiers
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username or email already registered.",
            )


def find_login_user_id(db_session: Session, identifier: str) -> int | None:
    identifier = identifier.casefold()
    usernames = []
    emails = []
    for user_id, username, email, verified_at in db_session.execute(
        select(User.id, User.username, User.email, User.email_verified_at)
    ):
        if username.casefold() == identifier:
            usernames.append(user_id)
        elif email and email.casefold() == identifier:
            emails.append((user_id, verified_at))

    if usernames:
        return usernames[0] if len(usernames) == 1 else None
    if len(emails) == 1 and emails[0][1] and get_account_mail_settings(db_session) is not None:
        return emails[0][0]
    return None
