"""Keep the 50 most recent recipe states, including their image references."""

from datetime import UTC

import sqlalchemy as sa
from alembic import op

revision = "0025_recipe_versions"
down_revision = "0026_smtp_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _add_recipe_version_column()
    op.create_index("ix_recipe_images_file_path", "recipe_images", ["file_path"])
    op.create_table(
        "recipe_image_deletions",
        sa.Column("recipe_id", sa.Integer(), primary_key=True),
        sa.Column("file_path", sa.String(), primary_key=True),
    )
    versions = op.create_table(
        "recipe_versions",
        sa.Column("recipe_id", sa.Integer(), sa.ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("editor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported", sa.Boolean(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
    )
    op.create_index("ix_recipe_versions_editor_id", "recipe_versions", ["editor_id"])
    op.create_index("ix_recipe_versions_category_id", "recipe_versions", ["category_id"])
    _backfill(op.get_bind(), versions)


def _add_recipe_version_column() -> None:
    connection = op.get_bind()
    version = sa.Column("version", sa.Integer(), server_default="1", nullable=False)
    if connection.dialect.name == "sqlite":
        ddl = connection.scalar(sa.text("SELECT sql FROM sqlite_master WHERE name = 'recipes' AND type = 'table'"))
        if "AUTOINCREMENT" not in ddl.upper():
            with op.batch_alter_table("recipes", recreate="always", table_kwargs={"sqlite_autoincrement": True}) as batch:
                batch.add_column(version)
            return

    op.add_column("recipes", version)
    if connection.dialect.name == "postgresql":
        # Imports with explicit IDs can leave the sequence behind. Preserve a
        # higher sequence value, including IDs used by recipes since deleted.
        connection.execute(sa.text("""
            DO $$
            DECLARE
                recipe_sequence regclass := pg_get_serial_sequence('recipes', 'id');
                highest_id integer := (SELECT max(id) FROM recipes);
                sequence_value bigint;
                sequence_called boolean;
            BEGIN
                EXECUTE format('SELECT last_value, is_called FROM %s', recipe_sequence)
                    INTO sequence_value, sequence_called;
                IF highest_id > sequence_value OR (highest_id = sequence_value AND NOT sequence_called) THEN
                    PERFORM setval(recipe_sequence, highest_id);
                END IF;
            END $$;
        """))


def _backfill(connection, versions) -> None:
    metadata = sa.MetaData()

    def table(name):
        return sa.Table(name, metadata, autoload_with=connection, resolve_fks=False).c

    recipes = table("recipes")
    categories = table("categories")
    groups = table("recipe_ingredient_groups")
    ingredients = table("recipe_ingredients")
    steps = table("recipe_steps")
    images = table("recipe_images")
    fields = (
        "title", "summary", "preparation_time", "cooking_time", "cooking_time_max",
        "rest_time", "rest_time_max", "servings", "history", "preparation_days",
        "origin_person", "notes", "important_notes", "category_id",
    )
    source = (
        sa.select(recipes.id, recipes.updated_at, *(recipes[field] for field in fields),
                  categories.name.label("category_name"), categories.id.label("live_category_id"))
        .outerjoin(categories.id.table, recipes.category_id == categories.id)
        .order_by(recipes.id)
    )
    for batch in connection.execute(source).mappings().partitions(200):
        values = []
        for recipe in batch:
            recipe_id = recipe["id"]
            snapshot = {field: recipe[field] for field in (*fields, "category_name")}
            snapshot["ingredient_groups"] = [
                dict(row) for row in connection.execute(
                    sa.select(groups.position, groups.name)
                    .where(groups.recipe_id == recipe_id).order_by(groups.position, groups.id)
                ).mappings()
            ]
            snapshot["ingredients"] = [
                dict(row, amount=None if row.amount is None else format(row.amount, ".3f"))
                for row in connection.execute(
                    sa.select(ingredients.position, ingredients.name, ingredients.amount,
                              ingredients.unit, ingredients.note, groups.position.label("group_position"))
                    .outerjoin(groups.id.table, ingredients.group_id == groups.id)
                    .where(ingredients.recipe_id == recipe_id).order_by(ingredients.position, ingredients.id)
                ).mappings()
            ]
            snapshot["steps"] = [
                dict(row) for row in connection.execute(
                    sa.select(steps.position, steps.instruction, steps.heading, steps.is_important, steps.note)
                    .where(steps.recipe_id == recipe_id).order_by(steps.position, steps.id)
                ).mappings()
            ]
            snapshot["images"] = [
                dict(row) for row in connection.execute(
                    sa.select(images.file_path, images.alt_text, images.is_main)
                    .where(images.recipe_id == recipe_id).order_by(images.id)
                ).mappings()
            ]
            values.append({
                "recipe_id": recipe_id,
                "version": 1,
                "editor_id": None,
                "category_id": recipe["live_category_id"],
                "created_at": recipe["updated_at"].astimezone(UTC) if recipe["updated_at"].tzinfo
                else recipe["updated_at"].replace(tzinfo=UTC),
                "imported": True,
                "snapshot": snapshot,
                "changes": {},
            })
        connection.execute(versions.insert(), values)


def downgrade() -> None:
    op.drop_table("recipe_versions")
    op.drop_table("recipe_image_deletions")
    op.drop_index("ix_recipe_images_file_path", table_name="recipe_images")
    # Keep SQLite's high-water mark across downgrade and re-upgrade.
    op.drop_column("recipes", "version")
