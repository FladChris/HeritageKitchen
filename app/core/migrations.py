from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.core import db


def run_migrations(engine: Engine | None = None) -> None:
    engine = engine or db.engine
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))

    with engine.connect() as connection:
        foreign_keys_enabled = (
            connection.dialect.name == "sqlite"
            and connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        )
        if foreign_keys_enabled:
            # SQLite batch migrations replace tables referenced by foreign keys.
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
        if connection.in_transaction():
            connection.commit()

        try:
            with connection.begin():
                config.attributes["connection"] = connection
                inspector = inspect(connection)
                if inspector.has_table("users") and not inspector.has_table("alembic_version"):
                    command.stamp(config, "0001_baseline")
                command.upgrade(config, "head")
        finally:
            if foreign_keys_enabled:
                connection.exec_driver_sql("PRAGMA foreign_keys = ON")
                connection.commit()
