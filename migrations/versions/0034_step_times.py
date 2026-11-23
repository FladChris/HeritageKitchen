"""Add optional step durations, step days and day titles."""

import sqlalchemy as sa
from alembic import op

revision = "0034_step_times"
down_revision = "0030_personal_recipe_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.add_column(sa.Column("day_titles", sa.JSON(), nullable=True))
    with op.batch_alter_table("recipe_steps") as batch_op:
        batch_op.add_column(sa.Column("day", sa.Integer(), nullable=False, server_default="1"))
        batch_op.create_check_constraint("ck_recipe_step_day", "day BETWEEN 1 AND 14")
        batch_op.add_column(sa.Column("duration_minutes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("time_kind", sa.String(), nullable=True))
        batch_op.create_check_constraint(
            "ck_recipe_step_time",
            "(duration_minutes IS NULL AND time_kind IS NULL) OR "
            "(duration_minutes IS NOT NULL AND time_kind IS NOT NULL AND duration_minutes BETWEEN 1 AND 20160 AND time_kind IN ('preparation', 'cooking', 'rest'))",
        )


def downgrade() -> None:
    with op.batch_alter_table("recipe_steps") as batch_op:
        batch_op.drop_constraint("ck_recipe_step_time", type_="check")
        batch_op.drop_constraint("ck_recipe_step_day", type_="check")
        batch_op.drop_column("day")
        batch_op.drop_column("time_kind")
        batch_op.drop_column("duration_minutes")
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_column("day_titles")
