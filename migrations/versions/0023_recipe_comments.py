"""Store comments separately from recipe content."""

import sqlalchemy as sa
from alembic import op

revision = "0023_recipe_comments"
down_revision = "0020_pending_editor_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "recipe_id",
            sa.Integer(),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_recipe_comments_author_id", "recipe_comments", ["author_id"])
    op.create_index(
        "ix_recipe_comments_recipe_created",
        "recipe_comments",
        ["recipe_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_table("recipe_comments")
