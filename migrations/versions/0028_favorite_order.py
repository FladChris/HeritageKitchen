"""Store favorite timestamps, personal positions and sorting preferences."""

import sqlalchemy as sa
from alembic import op

revision = "0028_favorite_order"
down_revision = "0025_recipe_versions"
branch_labels = None
depends_on = None

FK_NAMES = {"fk": "%(table_name)s_%(column_0_name)s_fkey"}


def upgrade() -> None:
    # Older SQLite installations could contain favorites with missing parents.
    favorites = sa.table("favorites", sa.column("user_id"), sa.column("recipe_id"))
    users = sa.table("users", sa.column("id"))
    recipes = sa.table("recipes", sa.column("id"))
    user_exists = (
        sa.select(users.c.id).where(users.c.id == favorites.c.user_id).exists()
    )
    recipe_exists = (
        sa.select(recipes.c.id).where(recipes.c.id == favorites.c.recipe_id).exists()
    )
    op.execute(favorites.delete().where(sa.or_(~user_exists, ~recipe_exists)))
    with op.batch_alter_table(
        "users",
        recreate="always" if op.get_context().dialect.name == "sqlite" else "auto",
        table_kwargs={"sqlite_autoincrement": True},
    ) as batch_op:
        batch_op.add_column(sa.Column("favorite_sort", sa.String(6)))
    with op.batch_alter_table(
        "favorites",
        naming_convention=FK_NAMES,
        table_kwargs={"sqlite_autoincrement": True},
    ) as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("position", sa.Integer()))
        for column, parent in (("user_id", "users"), ("recipe_id", "recipes")):
            name = f"favorites_{column}_fkey"
            batch_op.drop_constraint(name, type_="foreignkey")
            batch_op.create_foreign_key(
                name, parent, [column], ["id"], ondelete="CASCADE"
            )
    op.create_index("ix_favorites_recipe_id", "favorites", ["recipe_id"])


def downgrade() -> None:
    op.drop_index("ix_favorites_recipe_id", table_name="favorites")
    with op.batch_alter_table(
        "favorites",
        naming_convention=FK_NAMES,
        table_kwargs={"sqlite_autoincrement": False},
    ) as batch_op:
        for column, parent in (("user_id", "users"), ("recipe_id", "recipes")):
            name = f"favorites_{column}_fkey"
            batch_op.drop_constraint(name, type_="foreignkey")
            batch_op.create_foreign_key(name, parent, [column], ["id"])
        batch_op.drop_column("position")
        batch_op.drop_column("created_at")
    with op.batch_alter_table(
        "users",
        recreate="always" if op.get_context().dialect.name == "sqlite" else "auto",
        table_kwargs={"sqlite_autoincrement": False},
    ) as batch_op:
        batch_op.drop_column("favorite_sort")
