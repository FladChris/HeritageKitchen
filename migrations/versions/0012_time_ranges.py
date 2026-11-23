"""Add upper end for cooking and resting time."""

import sqlalchemy as sa
from alembic import op

revision = "0012_time_ranges"
down_revision = "0011_remove_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.add_column(sa.Column("cooking_time_max", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("rest_time_max", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_column("rest_time_max")
        batch_op.drop_column("cooking_time_max")
