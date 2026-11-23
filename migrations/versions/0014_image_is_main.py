"""Add main image flag."""

import sqlalchemy as sa
from alembic import op

revision = "0014_image_is_main"
down_revision = "0013_remove_image_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recipe_images") as batch_op:
        batch_op.add_column(
            sa.Column("is_main", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("recipe_images") as batch_op:
        batch_op.drop_column("is_main")
