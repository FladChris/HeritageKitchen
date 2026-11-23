"""Add independent linked recipes, recipe history and preparation day spans."""

import sqlalchemy as sa
from alembic import op

revision = "0016_recipe_family_history_days"
down_revision = "0015_step_heading"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("recipe_families", sa.Column("id", sa.Integer(), primary_key=True))
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.add_column(sa.Column("history", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("preparation_days", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("family_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_recipes_family_id", "recipe_families", ["family_id"], ["id"])
        batch_op.create_index("ix_recipes_family_id", ["family_id"])
        batch_op.create_check_constraint("ck_recipe_preparation_days", "preparation_days BETWEEN 1 AND 14")


def downgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_constraint("ck_recipe_preparation_days", type_="check")
        batch_op.drop_index("ix_recipes_family_id")
        batch_op.drop_constraint("fk_recipes_family_id", type_="foreignkey")
        batch_op.drop_column("family_id")
        batch_op.drop_column("preparation_days")
        batch_op.drop_column("history")
    op.drop_table("recipe_families")
