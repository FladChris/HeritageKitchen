"""Remove duration, temperature and method from recipe steps."""

import sqlalchemy as sa
from alembic import op

revision = "0010_remove_step_details"
down_revision = "0009_remove_ingredient_quantity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recipe_steps") as batch_op:
        batch_op.drop_column("duration_minutes")
        batch_op.drop_column("temperature_celsius")
        batch_op.drop_column("cooking_method")


def downgrade() -> None:
    with op.batch_alter_table("recipe_steps") as batch_op:
        batch_op.add_column(sa.Column("duration_minutes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("temperature_celsius", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cooking_method", sa.String(), nullable=True))
