"""Add optional section heading to recipe steps."""

import sqlalchemy as sa
from alembic import op

revision = "0015_step_heading"
down_revision = "0014_image_is_main"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recipe_steps") as batch_op:
        batch_op.add_column(sa.Column("heading", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("recipe_steps") as batch_op:
        batch_op.drop_column("heading")
