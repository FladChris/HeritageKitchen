"""Local recovery: set an administrator password from inside the container.

Usage: python -m app.admin_password <username>
"""

import sys
from getpass import getpass

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.schemas.validation_helpers import require_text_value
from app.core.db import dbSession, lock_user_writes
from app.core.security import hash_password
from app.models.password_reset_model import PasswordReset
from app.models.session_model import UserSession
from app.models.user_model import User, UserRole
from app.services.login_identifiers import find_login_user_id

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 255


class RecoveryError(Exception):
    pass


def set_admin_password(db_session: Session, username: str, password: str) -> None:
    try:
        password = require_text_value(password, "password")
    except ValueError as error:
        raise RecoveryError("Das Passwort darf nicht leer sein.") from error
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise RecoveryError(
            f"Das Passwort braucht {MIN_PASSWORD_LENGTH} bis "
            f"{MAX_PASSWORD_LENGTH} Zeichen (ohne Leerzeichen am Rand)."
        )
    password_hash = hash_password(password)
    lock_user_writes(db_session)
    user_id = find_login_user_id(db_session, username)
    user = db_session.get(User, user_id, populate_existing=True) if user_id else None
    if user is None or user.role != UserRole.ADMIN:
        db_session.rollback()
        raise RecoveryError("Kein Administratorkonto mit diesem Benutzernamen.")
    if not user.is_active:
        db_session.rollback()
        raise RecoveryError(
            "Das Administratorkonto ist deaktiviert; Passwort nicht gesetzt."
        )
    user.password_hash = password_hash
    db_session.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    db_session.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db_session.commit()


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Aufruf: python -m app.admin_password <Benutzername>", file=sys.stderr)
        return 2
    password = getpass("Neues Passwort: ")
    if password != getpass("Neues Passwort wiederholen: "):
        print("Die Passwörter stimmen nicht überein.", file=sys.stderr)
        return 1
    try:
        with dbSession() as db_session:
            set_admin_password(db_session, argv[0], password)
    except RecoveryError as error:
        print(error, file=sys.stderr)
        return 1
    print("Passwort gesetzt. Alle bisherigen Sitzungen und Reset-Links sind ungültig.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
