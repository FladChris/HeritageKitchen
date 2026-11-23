import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import create_database_engine
from app.core.migrations import run_migrations
from app.models import Base, Recipe, User


def migration_head():
    return ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_account_email_migration_preserves_users_and_recipe_attribution(tmp_path, dialect):
    database_url = f"sqlite:///{tmp_path / 'account-email.db'}"
    if dialect == "postgresql":
        database_url = os.environ.get("TEST_DATABASE_URL")
        if not database_url or make_url(database_url).get_backend_name() != "postgresql":
            pytest.skip("TEST_DATABASE_URL must point to PostgreSQL for this case")

    engine = create_engine(database_url)
    config = Config("alembic.ini")
    parent = "0035_main_recipe_images"
    try:
        with engine.connect() as connection:
            connection.begin()
            if dialect == "postgresql":
                schema = f"test_account_email_{uuid4().hex}"
                connection.execute(text(f"CREATE SCHEMA {schema}"))
                connection.execute(text(f"SET LOCAL search_path TO {schema}"))
            config.attributes["connection"] = connection
            command.upgrade(config, parent)
            if dialect == "sqlite":
                connection.commit()
                connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            connection.execute(text(
                "INSERT INTO users (id, username, email, password_hash, role, is_active, display_name) "
                "VALUES (1, 'tim', 'tim@example.com', 'hash', 'EDITOR', TRUE, 'Tim Klarname')"
            ))
            connection.execute(text("INSERT INTO recipes (id, title) VALUES (2, 'Brot')"))
            connection.execute(text(
                "INSERT INTO recipe_comments (id, recipe_id, author_id, text, created_at) "
                "VALUES (3, 2, 1, 'Knusprig', CURRENT_TIMESTAMP)"
            ))
            connection.execute(Table("recipe_versions", MetaData(), autoload_with=connection).insert(), {
                "recipe_id": 2, "version": 1, "editor_id": 1, "snapshot": {"title": "Brot"},
                "changes": {}, "imported": False, "created_at": datetime.now(UTC),
            })
            connection.execute(text(
                "INSERT INTO password_resets (user_id, token_hash, expires_at) "
                "VALUES (1, 'existing-reset', CURRENT_TIMESTAMP)"
            ))

            command.upgrade(config, "0036_verified_account_email")
            columns = {column["name"] for column in inspect(connection).get_columns("users")}
            assert "display_name" not in columns
            assert connection.execute(text(
                "SELECT id, username, email, password_hash, email_verified_at FROM users"
            )).one() == (1, "tim", "tim@example.com", "hash", None)
            assert connection.scalar(text("SELECT token_hash FROM password_resets")) == "existing-reset"

            command.downgrade(config, parent)
            columns = {column["name"] for column in inspect(connection).get_columns("users")}
            assert not any(column.startswith("email_verif") for column in columns)
            assert connection.execute(text(
                "SELECT username, email, display_name FROM users"
            )).one() == ("tim", "tim@example.com", "tim")
            assert connection.execute(text("SELECT id, title FROM recipes")).one() == (2, "Brot")
            assert connection.execute(text(
                "SELECT id, recipe_id, author_id, text FROM recipe_comments"
            )).one() == (3, 2, 1, "Knusprig")
            assert connection.execute(text(
                "SELECT recipe_id, version, editor_id FROM recipe_versions"
            )).one() == (2, 1, 1)
            if dialect == "sqlite":
                assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    finally:
        engine.dispose()


def test_favorite_migration_preserves_legacy_rows_and_adds_delete_cascades(tmp_path):
    url = f"sqlite:///{tmp_path / 'favorites.db'}"
    legacy_engine = create_engine(url)
    config = Config("alembic.ini")
    revision = ScriptDirectory.from_config(config).get_revision("0028_favorite_order")
    parent_revision = revision.down_revision
    try:
        with legacy_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, parent_revision)
            connection.execute(text(
                "INSERT INTO users (id, username, password_hash, role, is_active) VALUES "
                "(1, 'tim', 'hash', 'READER', TRUE), (2, 'lena', 'hash', 'EDITOR', TRUE), "
                "(10, 'max', 'hash', 'READER', TRUE)"
            ))
            connection.execute(text(
                "INSERT INTO recipes (id, title) VALUES (1, 'Brot'), (2, 'Kuchen')"
            ))
            connection.execute(text(
                "INSERT INTO favorites (id, user_id, recipe_id) VALUES "
                "(7, 1, 1), (9, 1, 2), (12, 2, 1), (13, 1, 99), (14, 99, 2)"
            ))
            command.upgrade(config, revision.revision)
    finally:
        legacy_engine.dispose()

    engine = create_database_engine(url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == revision.revision
            )
            assert connection.execute(text(
                "SELECT id, user_id, recipe_id, created_at, position FROM favorites ORDER BY id"
            )).all() == [(7, 1, 1, None, None), (9, 1, 2, None, None), (12, 2, 1, None, None)]
            connection.execute(text("DELETE FROM recipes WHERE id = 1"))
            assert connection.scalars(text("SELECT id FROM favorites")).all() == [9]
            new_id = connection.scalar(text(
                "INSERT INTO favorites (user_id, recipe_id) VALUES (2, 2) RETURNING id"
            ))
            assert new_id > 12
            connection.execute(text("DELETE FROM users WHERE id = 1"))
            assert connection.scalars(text("SELECT id FROM favorites")).all() == [new_id]

            connection.execute(text("DELETE FROM users WHERE id = 10"))
            next_user = connection.scalar(text(
                "INSERT INTO users (username, password_hash, role, is_active) "
                "VALUES ('petra', 'hash', 'READER', TRUE) RETURNING id"
            ))
            assert next_user > 10

    finally:
        engine.dispose()

    downgrade_engine = create_engine(url)
    try:
        with downgrade_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, parent_revision)
            assert connection.execute(text("SELECT * FROM favorites")).all() == [(new_id, 2, 2)]
    finally:
        downgrade_engine.dispose()


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_recipe_versions_backfill_preserves_fields_and_category_identity(tmp_path, dialect):
    database_url = f"sqlite:///{tmp_path / 'versions.db'}"
    if dialect == "postgresql":
        database_url = os.environ.get("TEST_DATABASE_URL")
        if not database_url or make_url(database_url).get_backend_name() != "postgresql":
            pytest.skip("TEST_DATABASE_URL must point to PostgreSQL for this case")
    # Alembic batch mode requires disabled SQLite foreign keys on its
    # migration connection, as in the application's migration runner.
    engine = create_engine(database_url)
    config = Config("alembic.ini")
    revision = ScriptDirectory.from_config(config).get_revision("0025_recipe_versions")
    parent_revision = revision.down_revision
    try:
        with engine.connect() as connection:
            connection.begin()
            if dialect == "postgresql":
                schema_name = f"test_recipe_versions_{uuid4().hex}"
                connection.execute(text(f"CREATE SCHEMA {schema_name}"))
                connection.execute(text(f"SET LOCAL search_path TO {schema_name}"))
            config.attributes["connection"] = connection
            command.upgrade(config, parent_revision)
            connection.execute(text("INSERT INTO categories (id, name) VALUES (7, 'Brot')"))
            connection.execute(text(
                "INSERT INTO recipes (id, title, history, preparation_days, category_id) "
                "VALUES (3, 'Brot', 'Von Oma', 2, 7), (4, 'Suppe', NULL, 1, NULL)"
            ))
            connection.execute(text(
                "INSERT INTO recipe_ingredient_groups (id, recipe_id, position, name) "
                "VALUES (8, 3, 1, 'Teig')"
            ))
            connection.execute(text(
                "INSERT INTO recipe_ingredients (recipe_id, position, group_id, name, amount) "
                "VALUES (3, 0, 8, 'Mehl', 12.375)"
            ))
            connection.execute(text(
                "INSERT INTO recipe_steps (recipe_id, position, instruction, is_important) "
                "VALUES (3, 0, 'Kneten', TRUE)"
            ))
            connection.execute(text(
                "INSERT INTO recipe_images (recipe_id, file_path, alt_text, is_main) "
                "VALUES (3, '/old.jpg', 'Brotlaib', TRUE)"
            ))
            command.upgrade(config, revision.revision)
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == revision.revision
            )
            rows = connection.execute(text("SELECT id, version FROM recipes ORDER BY id")).all()
            assert rows == [(3, 1), (4, 1)]
            versions = inspect(connection).get_columns("recipe_versions")
            assert "snapshot" in {column["name"] for column in versions}
            snapshot = connection.scalar(
                text("SELECT snapshot FROM recipe_versions WHERE recipe_id = 3")
            )
            if isinstance(snapshot, str):
                snapshot = json.loads(snapshot)
            assert snapshot["history"] == "Von Oma"
            assert snapshot["category_name"] == "Brot"
            assert snapshot["ingredients"][0]["amount"] == "12.375"
            assert snapshot["ingredients"][0]["group_position"] == 1
            assert snapshot["steps"][0]["instruction"] == "Kneten"
            assert snapshot["images"] == [{"file_path": "/old.jpg", "alt_text": "Brotlaib", "is_main": True}]
            insert_recipe = text("INSERT INTO recipes (title) VALUES ('Neu') RETURNING id")
            first_id = connection.scalar(insert_recipe)
            assert first_id > 4
            connection.execute(text("DELETE FROM recipes WHERE id = :id"), {"id": first_id})
            next_id = connection.scalar(insert_recipe)
            assert next_id > first_id
            connection.execute(text("DELETE FROM recipes WHERE id = :id"), {"id": next_id})
            command.downgrade(config, parent_revision)
            assert not inspect(connection).has_table("recipe_versions")
            assert connection.scalar(text("SELECT file_path FROM recipe_images")) == "/old.jpg"
            command.upgrade(config, revision.revision)
            assert connection.scalar(insert_recipe) > next_id
            if dialect == "sqlite":
                assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_main_image_backfill_preserves_gallery_order_and_versions(tmp_path, dialect):
    database_url = f"sqlite:///{tmp_path / 'main-images.db'}"
    if dialect == "postgresql":
        database_url = os.environ.get("TEST_DATABASE_URL")
        if not database_url or make_url(database_url).get_backend_name() != "postgresql":
            pytest.skip("TEST_DATABASE_URL must point to PostgreSQL for this case")

    engine = create_engine(database_url)
    config = Config("alembic.ini")
    try:
        with engine.connect() as connection:
            connection.begin()
            if dialect == "postgresql":
                schema_name = f"test_main_images_{uuid4().hex}"
                connection.execute(text(f"CREATE SCHEMA {schema_name}"))
                connection.execute(text(f"SET LOCAL search_path TO {schema_name}"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0034_step_times")
            connection.execute(text("INSERT INTO recipes (id, title) VALUES (1, 'Brot'), (2, 'Suppe'), (3, 'Kuchen')"))
            connection.execute(text(
                "INSERT INTO recipe_images (id, recipe_id, file_path, alt_text, position, is_main) VALUES "
                "(10, 1, '/last.jpg', NULL, 2, FALSE), (11, 1, '/first.jpg', 'Brot', 0, FALSE), "
                "(12, 1, '/tied.jpg', NULL, 0, FALSE), (13, 2, '/side.jpg', NULL, 0, FALSE), "
                "(14, 2, '/cover.jpg', NULL, 1, TRUE)"
            ))
            first = {"file_path": "/first.jpg", "alt_text": "Brot", "is_main": False}
            last = {"file_path": "/last.jpg", "alt_text": None, "is_main": False}
            tied = {"file_path": "/tied.jpg", "alt_text": None, "is_main": False}
            changes = {"images": {"before": [last], "after": [first, tied, last]}}
            table = Table("recipe_versions", MetaData(), autoload_with=connection)
            created_at = datetime.now(UTC)
            connection.execute(table.insert(), [
                {"recipe_id": 1, "version": 1, "created_at": created_at, "imported": False,
                 "snapshot": {"images": [first, tied, last]}, "changes": changes},
                {"recipe_id": 2, "version": 1, "imported": True, "snapshot": {"images": [
                    {"file_path": "/side.jpg", "is_main": False}, {"file_path": "/cover.jpg", "is_main": True},
                ]}, "created_at": created_at, "changes": {}},
                {"recipe_id": 3, "version": 1, "created_at": created_at, "imported": True,
                 "snapshot": {"title": "Kuchen"}, "changes": {}},
                {"recipe_id": 3, "version": 2, "created_at": created_at, "imported": True,
                 "snapshot": {"images": [first]}, "changes": None},
                {"recipe_id": 3, "version": 3, "created_at": created_at, "imported": True,
                 "snapshot": {"images": []}, "changes": ["legacy"]},
                {"recipe_id": 3, "version": 4, "created_at": created_at, "imported": True,
                 "snapshot": {"images": []}, "changes": {"images": None}},
            ])

            command.upgrade(config, "0035_main_recipe_images")
            command.downgrade(config, "0034_step_times")
            command.upgrade(config, "0035_main_recipe_images")
            assert connection.execute(text(
                "SELECT id, recipe_id, file_path, alt_text, position, is_main FROM recipe_images ORDER BY id"
            )).all() == [
                (10, 1, "/last.jpg", None, 2, False), (11, 1, "/first.jpg", "Brot", 0, True),
                (12, 1, "/tied.jpg", None, 0, False), (13, 2, "/side.jpg", None, 0, False),
                (14, 2, "/cover.jpg", None, 1, True),
            ]
            history = connection.execute(
                select(table.c.snapshot, table.c.changes).order_by(table.c.recipe_id, table.c.version)
            ).all()
            promoted_first = dict(first, is_main=True)
            assert history[0] == (
                {"images": [promoted_first, tied, last]},
                {"images": {"before": [dict(last, is_main=True)], "after": [promoted_first, tied, last]}},
            )
            assert [image["is_main"] for image in history[1].snapshot["images"]] == [False, True]
            assert history[2:] == [
                ({"title": "Kuchen"}, {}),
                ({"images": [promoted_first]}, None),
                ({"images": []}, ["legacy"]),
                ({"images": []}, {"images": None}),
            ]
    finally:
        engine.dispose()


def test_fresh_database_matches_models(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    try:
        run_migrations(engine)
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "compare_type": True,
                    "include_name": lambda name, type_, parent_names: (
                        type_ != "table" or name != "alembic_version"
                    ),
                },
            )
            assert compare_metadata(context, Base.metadata) == []
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                migration_head()
            )
    finally:
        engine.dispose()


def test_existing_database_is_stamped_and_repeated_run_preserves_data(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'existing.db'}")
    try:
        config = Config("alembic.ini")
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0001_baseline")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (username, password_hash, role, is_active) VALUES ('existing', 'hash', 'READER', 1)"))
            connection.execute(text("INSERT INTO recipes (title) VALUES ('Kuchen')"))
            connection.execute(text("INSERT INTO recipe_ingredients (recipe_id, position, name, quantity) VALUES (1, 0, 'Mehl', '250 g')"))
            connection.execute(text("INSERT INTO recipe_ingredients (recipe_id, position, name, quantity) VALUES (1, 1, 'Wasser', '1 Schuss')"))
            connection.execute(text("INSERT INTO recipe_images (recipe_id, file_path) VALUES (1, '/old.jpg')"))

        run_migrations(engine)
        run_migrations(engine)

        with Session(engine) as session:
            assert session.scalar(text("PRAGMA foreign_keys")) == 1
            assert session.scalars(select(User.username)).all() == ["existing"]
            recipe = session.scalar(select(Recipe))
            assert recipe.ingredients[0].name == "Mehl"
            assert recipe.ingredients[0].amount == 250
            assert recipe.ingredients[0].unit == "g"
            assert recipe.ingredients[1].unit == "Schuss"
            assert recipe.ingredients[1].amount == 1
            assert recipe.ingredients[0].group_position is None
            assert recipe.origin_person is None
            assert recipe.history is None
            assert recipe.preparation_days == 1
            assert session.scalar(text("SELECT version_num FROM alembic_version")) == (
                migration_head()
            )
            assert session.scalar(text("SELECT count(*) FROM alembic_version")) == 1
    finally:
        engine.dispose()


def test_profile_image_migration_preserves_existing_login_collisions(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'profile-image.db'}")
    config = Config("alembic.ini")
    old_accounts = [("Lena", "Hilde@example.com"), ("HILDE@example.com", "hilde@example.com")]
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0024_recipe_ratings")
            connection.execute(
                text("INSERT INTO users (username, email, password_hash, role, is_active) "
                     "VALUES (:username, :email, 'hash', 'READER', true)"),
                [{"username": username, "email": email} for username, email in old_accounts],
            )
            command.upgrade(config, "0021_profile_image")

            accounts = connection.execute(
                select(User.username, User.email, User.profile_image_path).order_by(User.id)
            ).all()
            assert accounts == [(username, email, None) for username, email in old_accounts]
    finally:
        engine.dispose()


def test_view_preferences_migration_preserves_accounts_and_shared_order(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'view-preferences.db'}")
    config = Config("alembic.ini")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0017_user_pending_approval")
            connection.execute(text(
                "INSERT INTO users (username, password_hash, role, is_active) "
                "VALUES ('reader', 'hash', 'READER', 1)"
            ))
            connection.execute(text("INSERT INTO app_settings VALUES ('category_order', '[1]')"))
            command.upgrade(config, "0018_user_view_preferences")
            assert connection.execute(
                select(User.username, User.category_sort, User.recipe_view)
            ).one() == ("reader", None, None)
            assert connection.scalar(text("SELECT value FROM app_settings")) == "[1]"
            command.downgrade(config, "0017_user_pending_approval")
            assert "user_category_positions" not in inspect(connection).get_table_names()
            assert connection.scalar(text("SELECT username FROM users")) == "reader"
    finally:
        engine.dispose()


def test_shared_category_order_migrates_only_to_accounts_without_positions(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'category-order.db'}")
    config = Config("alembic.ini")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0021_profile_image")
            connection.execute(text("INSERT INTO categories (id, name) VALUES (1, 'Brot'), (2, 'Kuchen')"))
            connection.execute(text(
                "INSERT INTO users (id, username, password_hash, role, is_active, category_sort, recipe_view) VALUES "
                "(1, 'Lena', 'hash', 'READER', true, NULL, NULL), "
                "(2, 'Tim', 'hash', 'EDITOR', true, NULL, 'grid'), "
                "(3, 'Petra', 'hash', 'ADMIN', true, 'name', NULL), "
                "(4, 'Hilde', 'hash', 'READER', false, NULL, NULL)"
            ))
            connection.execute(text("INSERT INTO user_category_positions VALUES (2, 1, 0), (2, 2, 1)"))
            connection.execute(text(
                "INSERT INTO app_settings VALUES ('category_order', '[2, 99, 1]'), ('cookbook_name', 'Kochbuch')"
            ))

            command.upgrade(config, "0027_personal_category_order")

            def positions():
                return connection.execute(text(
                    "SELECT user_id, category_id FROM user_category_positions ORDER BY user_id, position"
                )).all()

            expected = [(1, 2), (1, 1), (2, 1), (2, 2), (3, 2), (3, 1), (4, 2), (4, 1)]
            assert positions() == expected
            assert connection.execute(text("SELECT key, value FROM app_settings")).all() == [
                ("cookbook_name", "Kochbuch")
            ]
            assert connection.execute(text(
                "SELECT id, category_sort, recipe_view FROM users ORDER BY id"
            )).all() == [(1, "manual", None), (2, None, "grid"), (3, "name", None), (4, "manual", None)]

            command.downgrade(config, "0021_profile_image")
            command.upgrade(config, "0027_personal_category_order")
            assert positions() == expected
    finally:
        engine.dispose()


def test_personal_recipe_order_migration_preserves_existing_data(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'recipe-order.db'}")
    config = Config("alembic.ini")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0031_recipe_image_position")
            connection.execute(text("INSERT INTO categories (id, name) VALUES (1, 'Brot')"))
            connection.execute(text(
                "INSERT INTO users (id, username, password_hash, role, is_active) "
                "VALUES (1, 'Lena', 'hash', 'READER', true)"
            ))
            connection.execute(text("INSERT INTO recipes (id, title, category_id) VALUES (1, 'Bauernbrot', 1)"))

            command.upgrade(config, "0030_personal_recipe_order")
            assert connection.scalar(text("SELECT COUNT(*) FROM user_recipe_positions")) == 0
            connection.execute(text("INSERT INTO user_recipe_positions VALUES (1, 1, 0)"))

            command.downgrade(config, "0031_recipe_image_position")
            assert "user_recipe_positions" not in inspect(connection).get_table_names()
            assert connection.scalar(text("SELECT title FROM recipes")) == "Bauernbrot"
    finally:
        engine.dispose()


def test_approval_migration_preserves_existing_account_statuses(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'approval.db'}")
    config = Config("alembic.ini")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0016_recipe_family_history_days")
            connection.execute(text(
                "INSERT INTO users (username, password_hash, role, is_active) VALUES "
                "('admin', 'hash', 'ADMIN', 1), ('disabled', 'hash', 'READER', 0)"
            ))
            command.upgrade(config, "head")
            assert connection.execute(
                select(User.username, User.role, User.is_active, User.pending_approval)
                .order_by(User.username)
            ).all() == [("admin", "admin", True, False), ("disabled", "reader", False, False)]
            command.downgrade(config, "0016_recipe_family_history_days")
            assert "pending_approval" not in {
                column["name"] for column in inspect(connection).get_columns("users")
            }
    finally:
        engine.dispose()


def test_pending_registrations_get_editor_default_and_others_keep_roles(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pending.db'}")
    config = Config("alembic.ini")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0019_remove_recipe_families")
            connection.execute(text(
                "INSERT INTO users (username, password_hash, role, is_active, pending_approval) VALUES "
                "('pending', 'hash', 'READER', 0, 1), ('reader', 'hash', 'READER', 1, 0), "
                "('disabled', 'hash', 'READER', 0, 0)"
            ))
            command.upgrade(config, "0020_pending_editor_default")
            assert connection.execute(
                select(User.username, User.role).order_by(User.username)
            ).all() == [("disabled", "reader"), ("pending", "editor"), ("reader", "reader")]
    finally:
        engine.dispose()


def test_recipe_comments_migration_preserves_data_and_sets_delete_actions(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'comments.db'}")
    config = Config("alembic.ini")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0020_pending_editor_default")
            connection.execute(text(
                "INSERT INTO users (username, password_hash, role, is_active) "
                "VALUES ('tim', 'hash', 'READER', 1), ('lena', 'hash', 'EDITOR', 1)"
            ))
            connection.execute(text(
                "INSERT INTO recipes (title, notes) VALUES ('Kuchen', 'Abkühlen lassen')"
            ))

        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            config.attributes["connection"] = connection
            command.upgrade(config, "0023_recipe_comments")
            assert connection.execute(text("SELECT username FROM users ORDER BY id")).all() == [
                ("tim",), ("lena",)
            ]
            assert connection.execute(text("SELECT title, notes FROM recipes")).one() == (
                "Kuchen", "Abkühlen lassen"
            )
            connection.execute(text(
                "INSERT INTO recipe_comments (recipe_id, author_id, text, created_at) "
                "VALUES (1, 1, 'Mit Zimt', CURRENT_TIMESTAMP)"
            ))
            connection.execute(text("DELETE FROM users WHERE id = 1"))
            assert connection.execute(text("SELECT author_id, text FROM recipe_comments")).one() == (
                None, "Mit Zimt"
            )
            connection.execute(text("DELETE FROM recipes WHERE id = 1"))
            assert connection.scalar(text("SELECT count(*) FROM recipe_comments")) == 0
            command.downgrade(config, "0020_pending_editor_default")
            assert not inspect(connection).has_table("recipe_comments")
            assert connection.scalar(text("SELECT username FROM users")) == "lena"
    finally:
        engine.dispose()


def test_recipe_ratings_migration_preserves_existing_data_and_enforces_constraints(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ratings.db'}")
    config = Config("alembic.ini")
    source = "0023_recipe_comments"
    target = "0024_recipe_ratings"
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, source)
            connection.execute(text("INSERT INTO recipes (id, title) VALUES (1, 'Kuchen')"))
            connection.execute(text(
                "INSERT INTO users (id, username, password_hash, role, is_active) "
                "VALUES (1, 'reader', 'hash', 'READER', 1)"
            ))
            command.upgrade(config, target)

        with engine.begin() as connection:
            assert connection.execute(text("SELECT * FROM recipe_ratings")).all() == []
            foreign_keys = inspect(connection).get_foreign_keys("recipe_ratings")
            assert {
                (fk["referred_table"], fk["options"].get("ondelete")) for fk in foreign_keys
            } == {("recipes", "CASCADE"), ("users", "CASCADE")}
            insert = text("INSERT INTO recipe_ratings (recipe_id, user_id, half_stars) VALUES (1, 1, :value)")
            for value in (1, 2.5, 11):
                with pytest.raises(IntegrityError), connection.begin_nested():
                    connection.execute(insert, {"value": value})
            connection.execute(insert, {"value": 9})
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(insert, {"value": 10})

        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, source)
            assert not inspect(connection).has_table("recipe_ratings")
            assert connection.scalar(text("SELECT username FROM users")) == "reader"
            assert connection.scalar(text("SELECT title FROM recipes")) == "Kuchen"
    finally:
        engine.dispose()


def test_source_page_migration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'source_page.db'}")
    try:
        config = Config("alembic.ini")
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0007_password_resets")
            connection.execute(text("INSERT INTO recipes (title, origin_person, source_page) VALUES ('Kuchen', 'Oma', '7')"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0008_remove_source_page")
            assert "source_page" not in {column["name"] for column in inspect(connection).get_columns("recipes")}
            assert connection.scalar(text("SELECT origin_person FROM recipes WHERE title = 'Kuchen'")) == "Oma"
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0007_password_resets")
            assert "source_page" in {column["name"] for column in inspect(connection).get_columns("recipes")}
            assert connection.scalar(text("SELECT source_page FROM recipes WHERE title = 'Kuchen'")) is None
    finally:
        engine.dispose()


def test_quantity_migration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'quantities.db'}")
    try:
        config = Config("alembic.ini")
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0008_remove_source_page")
            connection.execute(text("INSERT INTO recipes (title) VALUES ('Test')"))
            cases = [
                ("Gelatine", "3 Blatt Gelatine", None, None),
                ("Schokoflocken", "1-2 Pakete", None, None),
                ("Rum", "1-2 EL", None, "optional"),
                ("Eier", "3-4", None, None),
                ("Zitronensaft", "etwas", None, None),
                ("Sahne", "1,5-2,5 Becher", None, None),
                ("Mehl", "alter Text", 5, "gesiebt"),
            ]
            for position, (name, quantity, amount, note) in enumerate(cases):
                connection.execute(text("""INSERT INTO recipe_ingredients
                    (recipe_id, position, name, quantity, amount, note)
                    VALUES (1, :position, :name, :quantity, :amount, :note)"""),
                    {"position": position, "name": name, "quantity": quantity, "amount": amount, "note": note})
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0015_step_heading")
            assert "quantity" not in {column["name"] for column in inspect(connection).get_columns("recipe_ingredients")}
            rows = connection.execute(text("SELECT amount, unit, note FROM recipe_ingredients ORDER BY position")).all()
            assert [(float(row.amount) if row.amount is not None else None, row.unit, row.note) for row in rows] == [
                (3, "Blatt", None), (2, "Pakete", None), (2, "EL", "optional"),
                (4, None, None), (None, None, "etwas"), (2.5, "Becher", None),
                (5, None, "gesiebt"),
            ]
            command.downgrade(config, "0008_remove_source_page")
            assert "quantity" in {column["name"] for column in inspect(connection).get_columns("recipe_ingredients")}
    finally:
        engine.dispose()


def test_family_history_days_migration_preserves_existing_content_and_downgrades(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'family-history.db'}")
    config = Config("alembic.ini")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0015_step_heading")
            connection.execute(text("INSERT INTO recipes (title, origin_person, rest_time) VALUES ('Brot', 'Oma', 1440)"))
            connection.execute(text("INSERT INTO recipe_ingredients (recipe_id, position, name, amount, unit) VALUES (1, 0, 'Mehl', 500, 'g')"))
            connection.execute(text("INSERT INTO recipe_steps (recipe_id, position, instruction, heading, is_important) VALUES (1, 0, 'Ruhen lassen', 'Tag 1', 0)"))
            connection.execute(text("INSERT INTO recipe_images (recipe_id, file_path, is_main) VALUES (1, '/bread.jpg', 1)"))
            command.upgrade(config, "0016_recipe_family_history_days")
            assert connection.execute(text("SELECT title, history, preparation_days, family_id FROM recipes")).one() == ("Brot", None, 1, None)
            connection.execute(text("INSERT INTO recipe_families (id) VALUES (1)"))
            connection.execute(text("UPDATE recipes SET family_id=1, history='Erinnerung', preparation_days=2"))
            command.downgrade(config, "0015_step_heading")
            assert connection.execute(text("SELECT title, origin_person, rest_time FROM recipes")).one() == ("Brot", "Oma", 1440)
            assert connection.execute(text("SELECT name, amount, unit FROM recipe_ingredients")).one() == ("Mehl", 500, "g")
            assert connection.execute(text("SELECT instruction, heading FROM recipe_steps")).one() == ("Ruhen lassen", "Tag 1")
            assert connection.scalar(text("SELECT file_path FROM recipe_images")) == "/bread.jpg"
            command.upgrade(config, "head")
            assert connection.scalar(text("SELECT preparation_days FROM recipes")) == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_remove_recipe_families_preserves_both_recipes_and_their_contents(tmp_path, dialect):
    database_url = f"sqlite:///{tmp_path / 'remove-families.db'}"
    if dialect == "postgresql":
        database_url = os.environ.get("TEST_DATABASE_URL")
        if not database_url or make_url(database_url).get_backend_name() != "postgresql":
            pytest.skip("TEST_DATABASE_URL must point to PostgreSQL for this case")
    engine = create_engine(database_url)
    config = Config("alembic.ini")
    try:
        with engine.connect() as connection:
            connection.begin()
            if dialect == "postgresql":
                # Closing the connection rolls back the isolated test schema.
                schema_name = f"test_recipe_migration_{uuid4().hex}"
                connection.execute(text(f"CREATE SCHEMA {schema_name}"))
                connection.execute(text(f"SET LOCAL search_path TO {schema_name}"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0018_user_view_preferences")
            connection.execute(text("INSERT INTO recipe_families (id) VALUES (1)"))
            recipes = [
                (7, "Große Form", 12, 500, "In einer 28-cm-Form backen.", "/large.jpg"),
                (19, "Kleine Form", 8, 350, "In einer 20-cm-Form backen.", "/small.jpg"),
            ]
            for recipe_id, title, servings, amount, instruction, file_path in recipes:
                connection.execute(text(
                    "INSERT INTO recipes (id, family_id, title, servings, history, preparation_days) "
                    "VALUES (:id, 1, :title, :servings, :history, 2)"
                ), {"id": recipe_id, "title": title, "servings": servings, "history": f"Omas {title}"})
                connection.execute(text(
                    "INSERT INTO recipe_ingredients (recipe_id, position, name, amount, unit) "
                    "VALUES (:id, 0, 'Mehl', :amount, 'g')"
                ), {"id": recipe_id, "amount": amount})
                connection.execute(text(
                    "INSERT INTO recipe_steps (recipe_id, position, instruction, heading, is_important) "
                    "VALUES (:id, 0, :instruction, 'Backen', FALSE)"
                ), {"id": recipe_id, "instruction": instruction})
                connection.execute(text(
                    "INSERT INTO recipe_images (recipe_id, file_path, alt_text, is_main) "
                    "VALUES (:id, :file_path, :title, TRUE)"
                ), {"id": recipe_id, "file_path": file_path, "title": title})

            recipe_columns = ", ".join(
                column["name"] for column in inspect(connection).get_columns("recipes")
                if column["name"] != "family_id"
            )
            content_queries = [
                text(f"SELECT {recipe_columns} FROM recipes ORDER BY id"),
                text("SELECT * FROM recipe_ingredients ORDER BY id"),
                text("SELECT * FROM recipe_steps ORDER BY id"),
                text("SELECT * FROM recipe_images ORDER BY id"),
            ]
            original_contents = [connection.execute(query).all() for query in content_queries]

            command.upgrade(config, "0019_remove_recipe_families")
            schema = inspect(connection)
            assert not schema.has_table("recipe_families")
            assert "family_id" not in {column["name"] for column in schema.get_columns("recipes")}
            assert "ix_recipes_family_id" not in {index["name"] for index in schema.get_indexes("recipes")}
            assert "fk_recipes_family_id" not in {fk["name"] for fk in schema.get_foreign_keys("recipes")}
            assert [connection.execute(query).all() for query in content_queries] == original_contents

            command.downgrade(config, "0018_user_view_preferences")
            schema = inspect(connection)
            assert "ix_recipes_family_id" in {index["name"] for index in schema.get_indexes("recipes")}
            assert "fk_recipes_family_id" in {fk["name"] for fk in schema.get_foreign_keys("recipes")}
            assert connection.scalar(text("SELECT count(*) FROM recipe_families")) == 0
            assert connection.execute(text("SELECT id, family_id FROM recipes ORDER BY id")).all() == [
                (7, None), (19, None),
            ]
            assert [connection.execute(query).all() for query in content_queries] == original_contents
    finally:
        engine.dispose()


def test_recipe_image_position_migration_keeps_existing_order_and_downgrades(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'image-position.db'}")
    config = Config("alembic.ini")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0028_favorite_order")
            connection.execute(text("INSERT INTO recipes (title) VALUES ('Brot'), ('Kuchen')"))
            connection.execute(text(
                "INSERT INTO recipe_images (id, recipe_id, file_path, alt_text, is_main) VALUES "
                "(1, 1, '/a.jpg', 'A', 0), (2, 2, '/x.jpg', NULL, 1), (3, 1, '/b.jpg', NULL, 1), (4, 1, '/c.jpg', NULL, 0)"
            ))
            command.upgrade(config, "0031_recipe_image_position")
            rows = connection.execute(text(
                "SELECT id, position, file_path, alt_text, is_main FROM recipe_images ORDER BY id"
            )).all()
            assert rows == [
                (1, 0, "/a.jpg", "A", 0), (2, 0, "/x.jpg", None, 1),
                (3, 1, "/b.jpg", None, 1), (4, 2, "/c.jpg", None, 0),
            ]
            command.downgrade(config, "0028_favorite_order")
            assert "position" not in {column["name"] for column in inspect(connection).get_columns("recipe_images")}
            assert connection.scalar(text("SELECT count(*) FROM recipe_images")) == 4
    finally:
        engine.dispose()


def test_step_time_migration_keeps_existing_steps_and_downgrades(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'step-times.db'}")
    config = Config("alembic.ini")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0030_personal_recipe_order")
            connection.execute(text("INSERT INTO recipes (id, title, cooking_time) VALUES (1, 'Brot', 45)"))
            connection.execute(text(
                "INSERT INTO recipe_steps (id, recipe_id, position, instruction, heading, is_important, note) "
                "VALUES (1, 1, 0, '20 Minuten backen', 'Tag 1', 1, 'Vorsicht')"
            ))
            command.upgrade(config, "0034_step_times")
            assert connection.execute(text(
                "SELECT instruction, heading, is_important, note, duration_minutes, time_kind, day FROM recipe_steps"
            )).all() == [("20 Minuten backen", "Tag 1", 1, "Vorsicht", None, None, 1)]
            assert connection.execute(text("SELECT cooking_time, preparation_days, day_titles FROM recipes")).one() == (45, 1, None)
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text("UPDATE recipe_steps SET day = 15"))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text("UPDATE recipe_steps SET duration_minutes = 20"))
            connection.execute(text("UPDATE recipe_steps SET duration_minutes = 20, time_kind = 'cooking'"))
            command.downgrade(config, "0030_personal_recipe_order")
            columns = {column["name"] for column in inspect(connection).get_columns("recipe_steps")}
            assert {"duration_minutes", "time_kind", "day"}.isdisjoint(columns)
            assert connection.scalar(text("SELECT instruction FROM recipe_steps")) == "20 Minuten backen"
    finally:
        engine.dispose()


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_removing_recipe_history_preserves_live_recipe_and_recreates_empty_history(tmp_path, dialect):
    database_url = f"sqlite:///{tmp_path / 'remove-history.db'}"
    if dialect == "postgresql":
        database_url = os.environ.get("TEST_DATABASE_URL")
        if not database_url or make_url(database_url).get_backend_name() != "postgresql":
            pytest.skip("TEST_DATABASE_URL must point to PostgreSQL for this case")
    engine = create_engine(database_url)
    config = Config("alembic.ini")
    parent = "0036_verified_account_email"
    revision = "0037_remove_recipe_versions"
    try:
        with engine.connect() as connection:
            connection.begin()
            if dialect == "postgresql":
                schema = f"test_remove_history_{uuid4().hex}"
                connection.execute(text(f"CREATE SCHEMA {schema}"))
                connection.execute(text(f"SET LOCAL search_path TO {schema}"))
            config.attributes["connection"] = connection
            command.upgrade(config, parent)
            connection.execute(text("INSERT INTO recipes (id, title, version) VALUES (1, 'Brot', 7)"))
            connection.execute(text(
                "INSERT INTO recipe_images (recipe_id, file_path, position, is_main) "
                "VALUES (1, '/media/1/current.jpg', 0, TRUE)"
            ))
            connection.execute(text(
                "INSERT INTO app_settings (key, value) VALUES "
                "('show_recipe_version_history', 'true'), ('cookbook_name', 'Familienrezepte')"
            ))
            history = Table("recipe_versions", MetaData(), autoload_with=connection)
            connection.execute(history.insert(), {
                "recipe_id": 1, "version": 6, "imported": False, "created_at": datetime.now(UTC),
                "snapshot": {"images": [{"file_path": "/media/1/old.jpg"}]}, "changes": {},
            })

            command.upgrade(config, revision)
            assert not inspect(connection).has_table("recipe_versions")
            assert connection.execute(text("SELECT key, value FROM app_settings")).all() == [
                ("cookbook_name", "Familienrezepte")
            ]
            assert connection.execute(text("SELECT title, version FROM recipes")).one() == ("Brot", 7)
            assert connection.scalar(text("SELECT file_path FROM recipe_images")) == "/media/1/current.jpg"
            assert inspect(connection).has_table("recipe_image_deletions")

            command.downgrade(config, parent)
            assert connection.scalar(text("SELECT count(*) FROM recipe_versions")) == 0
            assert connection.scalar(text("SELECT version FROM recipes")) == 7
    finally:
        engine.dispose()
