"""Store one independent half-star rating per user and recipe."""

import sqlalchemy as sa
from alembic import op

revision = "0024_recipe_ratings"
down_revision = "0023_recipe_comments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_ratings",
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("half_stars", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "half_stars IN (2, 3, 4, 5, 6, 7, 8, 9, 10)",
            name="ck_recipe_ratings_half_stars",
        ),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("recipe_id", "user_id"),
    )
    op.create_index("ix_recipe_ratings_user_id", "recipe_ratings", ["user_id"])


def downgrade() -> None:
    op.drop_table("recipe_ratings")
