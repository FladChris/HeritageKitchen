from sqlite3 import SQLITE_BUSY, SQLITE_LOCKED

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _enable_sqlite_foreign_keys(connection, _connection_record) -> None:
    autocommit = connection.autocommit
    connection.autocommit = True
    try:
        connection.execute("PRAGMA foreign_keys = ON").close()
    finally:
        connection.autocommit = autocommit


def create_database_engine(database_url: str) -> Engine:
    engine = create_engine(database_url)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


engine = create_database_engine(settings.database_url)
dbSession = sessionmaker(bind=engine)


def sqlite_write_is_busy(error: OperationalError) -> bool:
    # The low byte of an extended SQLite error code is its primary code.
    code = getattr(error.orig, "sqlite_errorcode", 0) & 0xFF
    return code in (SQLITE_BUSY, SQLITE_LOCKED)


def lock_sqlite_writes(db_session: Session) -> None:
    if db_session.get_bind().dialect.name == "sqlite":
        db_session.execute(text("BEGIN IMMEDIATE"))


def lock_user_writes(db_session: Session) -> None:
    if db_session.get_bind().dialect.name == "postgresql":
        db_session.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
    else:
        lock_sqlite_writes(db_session)


def get_db():
    db: Session = dbSession()
    try:
        yield db
    finally:
        db.close()
