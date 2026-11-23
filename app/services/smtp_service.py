import hmac
import json
import logging
import secrets
import smtplib
import ssl
from contextlib import AbstractContextManager, nullcontext, suppress
from datetime import UTC, datetime
from email.message import EmailMessage
from threading import Lock
from time import monotonic

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from filelock import FileLock
from filelock import Timeout as FileLockTimeout
from sqlalchemy import delete, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.api.schemas.smtp_schema import SmtpStatus, SmtpUpdate
from app.core.config import settings
from app.core.db import lock_sqlite_writes, lock_user_writes, sqlite_write_is_busy
from app.models.password_reset_model import PasswordReset
from app.models.smtp_settings_model import SmtpSettings
from app.models.user_model import User

logger = logging.getLogger(__name__)
_sqlite_memory_lock = Lock()
_SQLITE_SMTP_LOCK_TIMEOUT = 5
_DRAFT_TEST_TTL = 300
_draft_tests: dict[int, tuple[float, bytes]] = {}
_draft_test_lock = Lock()
_draft_test_key = secrets.token_bytes(32)
CONFLICT = "Die SMTP-Einstellungen wurden zwischenzeitlich geändert. Lade sie erneut."
SEND_FAILED = "Der SMTP-Versand ist fehlgeschlagen. Details stehen im Serverprotokoll."


def get_settings(db_session: Session) -> SmtpSettings:
    return db_session.scalars(select(SmtpSettings)).one()


def _cipher() -> Fernet:
    return Fernet(settings.mail_credentials_key)


def _password(config: SmtpSettings) -> str:
    if not config.encrypted_password:
        return ""
    return _cipher().decrypt(config.encrypted_password.encode()).decode()


def _is_tested(config: SmtpSettings) -> bool:
    if not (config.host and config.sender and config.tested_at):
        return False
    try:
        if config.username:
            _password(config)
    except (ValueError, InvalidToken):
        return False
    return True


def get_tested_settings(db_session: Session) -> SmtpSettings | None:
    config = db_session.get(SmtpSettings, 1, populate_existing=True)
    return config if config is not None and _is_tested(config) else None


def _account_mail_link_hint() -> str | None:
    if not settings.reset_base_url:
        return "Für Bestätigungs- und Reset-Links fehlt die Servereinstellung RESET_BASE_URL."
    return None


def get_account_mail_settings(db_session: Session) -> SmtpSettings | None:
    return get_tested_settings(db_session) if settings.reset_base_url else None


def account_mail_availability(db_session: Session) -> tuple[bool, str | None]:
    if get_tested_settings(db_session) is None:
        return False, None
    hint = _account_mail_link_hint()
    return hint is None, hint


def sqlite_smtp_lock(db_session: Session) -> AbstractContextManager:
    if db_session.get_bind().dialect.name != "sqlite":
        return nullcontext()
    databases = db_session.connection().exec_driver_sql("PRAGMA database_list")
    path = next(row.file for row in databases.all() if row.name == "main")
    if not path:
        return _sqlite_memory_lock
    return FileLock(
        f"{path}.smtp.lock", timeout=_SQLITE_SMTP_LOCK_TIMEOUT, fallback_to_soft=False
    )


def lock_tested_version(db_session: Session, config: SmtpSettings) -> bool:
    statement = select(SmtpSettings.id).where(
        SmtpSettings.id == config.id,
        SmtpSettings.version == config.version,
        SmtpSettings.tested_at.is_not(None),
    )
    if db_session.get_bind().dialect.name != "sqlite":
        return db_session.scalar(statement.with_for_update()) is not None

    # Check that the database can accept writes before starting delivery.
    # The SMTP file lock keeps the settings stable after we release SQLite's writer.
    try:
        lock_sqlite_writes(db_session)
        is_current = db_session.scalar(statement) is not None
    except OperationalError as error:
        if not sqlite_write_is_busy(error):
            raise
        logger.warning("SMTP delivery was skipped because SQLite is busy.")
        return False
    if is_current:
        db_session.expunge(config)
    db_session.rollback()
    return is_current


def status(config: SmtpSettings) -> SmtpStatus:
    tested = _is_tested(config)
    return SmtpStatus(
        version=config.version,
        host=config.host,
        port=config.port,
        encryption=config.encryption,
        username=config.username,
        sender=config.sender,
        has_password=bool(config.encrypted_password),
        status=(
            "not_configured"
            if not (config.host and config.sender)
            else "tested"
            if tested
            else "untested"
        ),
        account_mail_hint=_account_mail_link_hint() if tested else None,
    )


def _commit(db_session: Session, *, invalidate_account_mail: bool = False) -> None:
    try:
        if invalidate_account_mail:
            # Reset delivery locks SMTP first, then users. Keep the same order.
            db_session.flush()
            if db_session.get_bind().dialect.name != "sqlite":
                lock_user_writes(db_session)
            db_session.execute(
                update(User)
                .where(User.email_verified_at.is_not(None) | User.email_verification_hash.is_not(None))
                .values(
                    email_verified_at=None,
                    email_verification_hash=None,
                    email_verification_expires_at=None,
                )
            )
            db_session.execute(delete(PasswordReset))
        db_session.commit()
    except StaleDataError:
        db_session.rollback()
        raise HTTPException(status_code=409, detail=CONFLICT) from None


def update_settings(db_session: Session, request: SmtpUpdate, admin_id: int) -> SmtpStatus:
    try:
        with sqlite_smtp_lock(db_session):
            return _update_settings(db_session, request, admin_id)
    except FileLockTimeout:
        raise HTTPException(
            status_code=409,
            detail="Ein SMTP-Versand läuft gerade. Versuche es erneut.",
        ) from None


def _settings_values(config: SmtpSettings, request: SmtpUpdate) -> dict:
    values = request.model_dump(exclude={"password", "version"})
    values["encrypted_password"] = config.encrypted_password
    password = request.password.get_secret_value()
    if not request.host:
        values.update(username="", encrypted_password=None)
    elif password:
        try:
            previous_password = _password(config)
        except (ValueError, InvalidToken):
            previous_password = ""
        if not hmac.compare_digest(password.encode(), previous_password.encode()):
            try:
                values["encrypted_password"] = (
                    _cipher().encrypt(password.encode()).decode()
                )
            except ValueError:
                raise HTTPException(
                    status_code=409,
                    detail="Für das SMTP-Passwort muss MAIL_CREDENTIALS_KEY eingerichtet sein.",
                ) from None
    return values


def _fingerprint(config: SmtpSettings) -> bytes:
    values = (
        config.version,
        config.host,
        config.port,
        config.encryption,
        config.username,
        config.sender,
        _password(config),
    )
    return hmac.digest(_draft_test_key, json.dumps(values).encode(), "sha256")


def _draft_was_tested(config: SmtpSettings, admin_id: int) -> bool:
    with _draft_test_lock:
        proof = _draft_tests.get(admin_id)
    if proof is None or proof[0] <= monotonic():
        return False
    try:
        return hmac.compare_digest(proof[1], _fingerprint(config))
    except (ValueError, InvalidToken):
        return False


def _update_settings(db_session: Session, request: SmtpUpdate, admin_id: int) -> SmtpStatus:
    config = get_settings(db_session)
    if config.version != request.version:
        raise HTTPException(status_code=409, detail=CONFLICT)
    values = _settings_values(config, request)
    changed = any(getattr(config, field) != value for field, value in values.items())
    if changed:
        for field, value in values.items():
            setattr(config, field, value)
        config.tested_at = None
    tested = config.tested_at is None and _draft_was_tested(config, admin_id)
    if tested:
        config.tested_at = datetime.now(UTC)
    if changed or tested:
        _commit(db_session, invalidate_account_mail=changed)
    return status(config)


def send_message(
    config: SmtpSettings, *, recipient: str, subject: str, body: str, purpose: str
) -> bool:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.sender
    message["To"] = recipient
    message.set_content(body)

    try:
        password = _password(config) if config.username else ""
        tls_context = (
            ssl.create_default_context() if config.encryption != "none" else None
        )
        if config.encryption == "tls":
            server = smtplib.SMTP_SSL(
                config.host, config.port, timeout=10, context=tls_context
            )
        else:
            server = smtplib.SMTP(config.host, config.port, timeout=10)
        try:
            if config.encryption == "starttls":
                server.starttls(context=tls_context)
            if config.username:
                server.login(config.username, password)
            server.send_message(message)
            # The server already accepted the message even if QUIT fails.
            with suppress(OSError):
                server.quit()
        finally:
            with suppress(OSError):
                server.close()
    except (OSError, ValueError, InvalidToken) as error:
        # SMTP replies may include message data or credentials.
        logger.warning(
            "SMTP %s failed: %s (code %s)",
            purpose,
            type(error).__name__,
            getattr(error, "smtp_code", None),
        )
        return False
    return True


def _send_test_message(config: SmtpSettings, recipient: str) -> bool:
    return send_message(
        config,
        recipient=recipient,
        subject="Heritage Kitchen: SMTP-Test",
        body="Dies ist eine Test-E-Mail aus den Kochbuch-Einstellungen.\n",
        purpose="test",
    )


def test_draft(
    db_session: Session, request: SmtpUpdate, recipient: str, admin_id: int
) -> SmtpStatus:
    config = get_settings(db_session)
    if config.version != request.version:
        raise HTTPException(status_code=409, detail=CONFLICT)
    if not request.host:
        raise HTTPException(status_code=409, detail="Gib SMTP-Server und Absenderadresse ein.")
    draft = SmtpSettings(version=config.version, **_settings_values(config, request))
    try:
        fingerprint = _fingerprint(draft)
    except (ValueError, InvalidToken):
        raise HTTPException(
            status_code=409, detail="Gib das SMTP-Passwort erneut ein."
        ) from None
    with _draft_test_lock:
        _draft_tests.pop(admin_id, None)
    if not _send_test_message(draft, recipient):
        raise HTTPException(status_code=502, detail=SEND_FAILED)
    with _draft_test_lock:
        now = monotonic()
        for key, (expires, _) in list(_draft_tests.items()):
            if expires <= now:
                del _draft_tests[key]
        _draft_tests[admin_id] = (now + _DRAFT_TEST_TTL, fingerprint)
    draft.tested_at = datetime.now(UTC)
    return status(draft)


def send_test(db_session: Session, recipient: str) -> SmtpStatus:
    config = get_settings(db_session)
    if not (config.host and config.sender):
        raise HTTPException(
            status_code=409, detail="Speichere zuerst die SMTP-Einstellungen."
        )
    if not _send_test_message(config, recipient):
        if config.tested_at is not None:
            # Account mail pauses while SMTP is untested; verified addresses stay
            # verified because the configuration itself did not change.
            config.tested_at = None
            _commit(db_session)
        raise HTTPException(status_code=502, detail=SEND_FAILED)
    config.tested_at = datetime.now(UTC)
    _commit(db_session)
    return status(config)


def revoke_invalid_test(db_session: Session) -> None:
    config = get_settings(db_session)
    if config.tested_at is not None and not _is_tested(config):
        config.tested_at = None
        _commit(db_session, invalidate_account_mail=True)
