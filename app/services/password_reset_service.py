import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException
from filelock import Timeout as FileLockTimeout
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import lock_user_writes, sqlite_write_is_busy
from app.core.security import create_session_token, hash_password, hash_session_token
from app.models.password_reset_model import PasswordReset
from app.models.session_model import UserSession
from app.models.smtp_settings_model import SmtpSettings
from app.models.user_model import User
from app.services import smtp_service

logger = logging.getLogger(__name__)
MAIL_UNAVAILABLE = "Passwort-Reset per E-Mail ist nicht verfügbar."


def _mail_settings(db_session: Session) -> SmtpSettings | None:
    return smtp_service.get_account_mail_settings(db_session)


def _reset_recipient(user: User) -> str | None:
    if not user.is_active or not user.email or user.email_verified_at is None:
        return None
    try:
        return validate_email(user.email, check_deliverability=False).normalized
    except EmailNotValidError:
        return None


def request_reset(db_session: Session, email: str) -> None:
    config = _mail_settings(db_session)
    if config is None:
        return
    users = db_session.scalars(select(User).where(User.email.is_not(None)))
    matches = [user for user in users if user.email.casefold() == email.casefold()]
    if len(matches) == 1 and (recipient := _reset_recipient(matches[0])):
        _send_reset(db_session, config, matches[0], recipient)


def request_admin_reset(db_session: Session, user_id: int) -> None:
    config = _mail_settings(db_session)
    if config is None:
        raise HTTPException(status_code=409, detail=MAIL_UNAVAILABLE)
    user = db_session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    recipient = _reset_recipient(user)
    if recipient is None:
        raise HTTPException(
            status_code=409,
            detail="Das aktive Konto benötigt eine bestätigte E-Mail-Adresse.",
        )
    result = _send_reset(db_session, config, user, recipient)
    if result is None:
        raise HTTPException(status_code=409, detail=MAIL_UNAVAILABLE)
    if not result:
        raise HTTPException(status_code=502, detail=smtp_service.SEND_FAILED)


def _send_reset(
    db_session: Session, config: SmtpSettings, user: User, recipient: str
) -> bool | None:
    user_id, password_hash, verified_at = user.id, user.password_hash, user.email_verified_at
    token = create_session_token()
    link = f"{settings.reset_base_url.rstrip('/')}/reset-password?token={quote(token)}"
    try:
        with smtp_service.sqlite_smtp_lock(db_session):
            if not smtp_service.lock_tested_version(db_session, config):
                db_session.rollback()
                return None
            if not smtp_service.send_message(
                config,
                recipient=recipient,
                subject="Heritage Kitchen: Passwort zurücksetzen",
                body=f"Setze dein Passwort innerhalb einer Stunde zurück: {link}\n",
                purpose="password reset",
            ):
                db_session.rollback()
                return False

            stored = _store_reset_token(
                db_session,
                user_id=user_id,
                recipient=recipient,
                password_hash=password_hash,
                verified_at=verified_at,
                token_hash=hash_session_token(token),
            )
            return True if stored else None
    except FileLockTimeout:
        db_session.rollback()
        logger.warning(
            "SMTP reset was skipped because another SMTP operation is active."
        )
        return None


def _store_reset_token(
    db_session: Session,
    *,
    user_id: int,
    recipient: str,
    password_hash: str,
    verified_at: datetime | None,
    token_hash: str,
) -> bool:
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    for _ in range(2):
        try:
            lock_user_writes(db_session)
            current = db_session.get(User, user_id, populate_existing=True)
            if (
                current is None
                or current.password_hash != password_hash
                or current.email_verified_at != verified_at
                or _reset_recipient(current) != recipient
            ):
                db_session.rollback()
                logger.info(
                    "SMTP reset token was discarded because the account changed."
                )
                return False

            db_session.execute(
                delete(PasswordReset).where(PasswordReset.user_id == user_id)
            )
            db_session.add(
                PasswordReset(
                    user_id=user_id, token_hash=token_hash, expires_at=expires_at
                )
            )
            db_session.commit()
            return True
        except OperationalError as error:
            if not sqlite_write_is_busy(error):
                raise
            db_session.rollback()

    logger.warning("SMTP reset token could not be saved because SQLite is busy.")
    return False


def reset_password(db_session: Session, token: str, password: str) -> None:
    lock_user_writes(db_session)
    error = HTTPException(status_code=400, detail="Invalid or expired reset link.")
    if _mail_settings(db_session) is None:
        raise error
    reset = db_session.scalar(
        select(PasswordReset).where(
            PasswordReset.token_hash == hash_session_token(token)
        )
    )
    if reset is None or reset.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
        raise error
    user = db_session.get(User, reset.user_id)
    if user is None or _reset_recipient(user) is None:
        raise error
    user.password_hash = hash_password(password)
    db_session.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    db_session.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db_session.commit()
