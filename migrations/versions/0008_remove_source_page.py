"""Remove recipe source page."""

import sqlalchemy as sa
from alembic import op

revision = "0008_remove_source_page"
down_revision = "0007_password_resets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_column("source_page")


def downgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.add_column(sa.Column("source_page", sa.String(), nullable=True))
