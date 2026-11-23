"""Store home view preferences and category positions per user."""

import sqlalchemy as sa
from alembic import op

revision = "0018_user_view_preferences"
down_revision = "0017_user_pending_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("category_sort", sa.String(6)))
    op.add_column("users", sa.Column("recipe_view", sa.String(4)))
    op.create_table(
        "user_category_positions",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_user_category_positions_category_id",
        "user_category_positions",
        ["category_id"],
    )


def downgrade() -> None:
    op.drop_table("user_category_positions")
    op.drop_column("users", "recipe_view")
    op.drop_column("users", "category_sort")
