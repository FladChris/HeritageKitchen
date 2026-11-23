"""Remove stored recipe history and its display setting."""

import sqlalchemy as sa
from alembic import op

revision = "0037_remove_recipe_versions"
down_revision = "0036_verified_account_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    settings = sa.table("app_settings", sa.column("key", sa.String()))
    op.execute(settings.delete().where(settings.c.key == "show_recipe_version_history"))
    op.drop_table("recipe_versions")


def downgrade() -> None:
    op.create_table(
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
