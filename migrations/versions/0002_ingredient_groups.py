"""Add ingredient groups."""

import sqlalchemy as sa
from alembic import op

revision = "0002_ingredient_groups"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_ingredient_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recipe_id", sa.Integer(), sa.ForeignKey("recipes.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
    )
    with op.batch_alter_table("recipe_ingredients") as batch_op:
        batch_op.add_column(sa.Column("group_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_recipe_ingredients_group_id", "recipe_ingredient_groups", ["group_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("recipe_ingredients") as batch_op:
        batch_op.drop_constraint("fk_recipe_ingredients_group_id", type_="foreignkey")
        batch_op.drop_column("group_id")
    op.drop_table("recipe_ingredient_groups")
