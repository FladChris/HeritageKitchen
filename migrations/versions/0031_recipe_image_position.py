"""Add a persistent gallery position to recipe images."""

import sqlalchemy as sa
from alembic import op

revision = "0031_recipe_image_position"
down_revision = "0028_favorite_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recipe_images") as batch_op:
        batch_op.add_column(sa.Column("position", sa.Integer(), nullable=False, server_default="0"))
    # Backfill by image ID, the order version snapshots already store; the main image stays flagged separately.
    op.execute(
        "UPDATE recipe_images SET position = ("
        "SELECT count(*) FROM recipe_images AS earlier "
        "WHERE earlier.recipe_id = recipe_images.recipe_id AND earlier.id < recipe_images.id)"
    )


def downgrade() -> None:
    with op.batch_alter_table("recipe_images") as batch_op:
        batch_op.drop_column("position")
