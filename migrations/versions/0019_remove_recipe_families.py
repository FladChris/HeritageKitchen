"""Remove recipe family associations while preserving recipe contents."""

import sqlalchemy as sa
from alembic import op

revision = "0019_remove_recipe_families"
down_revision = "0018_user_view_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_index("ix_recipes_family_id")
        batch_op.drop_constraint("fk_recipes_family_id", type_="foreignkey")
        batch_op.drop_column("family_id")
    op.drop_table("recipe_families")


def downgrade() -> None:
    # Restore the schema with every recipe independent, since links were discarded.
    op.create_table("recipe_families", sa.Column("id", sa.Integer(), primary_key=True))
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.add_column(sa.Column("family_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_recipes_family_id", "recipe_families", ["family_id"], ["id"])
        batch_op.create_index("ix_recipes_family_id", ["family_id"])
