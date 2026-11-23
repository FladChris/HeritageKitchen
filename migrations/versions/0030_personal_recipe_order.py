"""Store a personal recipe order per user."""

import sqlalchemy as sa
from alembic import op

revision = "0030_personal_recipe_order"
down_revision = "0031_recipe_image_position"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_recipe_positions",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "recipe_id",
            sa.Integer(),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_user_recipe_positions_recipe_id", "user_recipe_positions", ["recipe_id"]
    )


def downgrade() -> None:
    op.drop_table("user_recipe_positions")
