"""Add recipe image type."""

import sqlalchemy as sa
from alembic import op

revision = "0005_image_type"
down_revision = "0004_ingredient_amount"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recipe_images") as batch_op:
        batch_op.add_column(
            sa.Column("image_type", sa.String(), nullable=False, server_default="dish")
        )


def downgrade() -> None:
    with op.batch_alter_table("recipe_images") as batch_op:
        batch_op.drop_column("image_type")
