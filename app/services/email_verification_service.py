import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import BackgroundTasks, HTTPException
from filelock import Timeout as FileLockTimeout
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import lock_user_writes
from app.core.security import create_session_token, hash_session_token
from app.models.password_reset_model import PasswordReset
from app.models.user_model import User
from app.services import smtp_service

UNAVAILABLE = (
    "E-Mail ist erst verfügbar, wenn SMTP eingerichtet und erfolgreich getestet wurde."
)
logger = logging.getLogger(__name__)


def require_available_email(db_session: Session, email: str | None) -> None:
    if not email:
        return
    available, hint = smtp_service.account_mail_availability(db_session)
    if not available:
        raise HTTPException(status_code=409, detail=hint or UNAVAILABLE)


def set_email(
    db_session: Session,
    user: User,
    email: str | None,
    *,
    background_tasks: BackgroundTasks | None,
) -> None:
    if user.email != email:
        user.email = email
        user.email_verified_at = None
        if user.id is not None:
            db_session.execute(
                delete(PasswordReset).where(PasswordReset.user_id == user.id)
            )
    if email and user.email_verified_at is None:
        token = create_session_token()
        user.email_verification_hash = hash_session_token(token)
        user.email_verification_expires_at = datetime.now(UTC) + timedelta(hours=1)
        if background_tasks is not None:
            background_tasks.add_task(send_verification, db_session, email, token)
    elif not email:
        user.email_verification_hash = None
        user.email_verification_expires_at = None


def send_verification(db_session: Session, email: str, token: str) -> None:
    config = smtp_service.get_account_mail_settings(db_session)
    if config is None:
        return
    try:
        with smtp_service.sqlite_smtp_lock(db_session):
            if not smtp_service.lock_tested_version(db_session, config):
                return
            current_email = db_session.scalar(
                select(User.email).where(
                    User.email_verification_hash == hash_session_token(token)
                )
            )
            if current_email != email:
                return
            link = f"{settings.reset_base_url.rstrip('/')}/verify-email?token={quote(token)}"
            smtp_service.send_message(
                config,
                recipient=email,
                subject="Heritage Kitchen: E-Mail bestätigen",
                body=f"Bestätige deine E-Mail-Adresse innerhalb einer Stunde: {link}\n",
                purpose="email verification",
            )
    except FileLockTimeout:
        logger.warning(
            "Email verification was skipped because another SMTP operation is active."
        )
    finally:
        db_session.rollback()


def verify_email(db_session: Session, token: str) -> None:
    lock_user_writes(db_session)
    error = HTTPException(
        status_code=400, detail="Der Bestätigungslink ist ungültig oder abgelaufen."
    )
    if smtp_service.get_account_mail_settings(db_session) is None:
        raise error
    user = db_session.scalar(
        select(User).where(User.email_verification_hash == hash_session_token(token))
    )
    now = datetime.now(UTC)
    if (
        user is None
        or not user.email
        or user.email_verification_expires_at is None
        or user.email_verification_expires_at.replace(tzinfo=UTC) <= now
    ):
        raise error
    user.email_verified_at = now
    user.email_verification_hash = None
    user.email_verification_expires_at = None
    db_session.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    db_session.commit()
