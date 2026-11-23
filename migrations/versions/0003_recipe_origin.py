"""Add recipe origin details."""

import sqlalchemy as sa
from alembic import op

revision = "0003_recipe_origin"
down_revision = "0002_ingredient_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.add_column(sa.Column("origin_person", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("source_page", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_column("source_page")
        batch_op.drop_column("origin_person")
