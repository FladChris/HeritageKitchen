"""Distinguish registrations awaiting approval from disabled accounts."""

import sqlalchemy as sa
from alembic import op

revision = "0017_user_pending_approval"
down_revision = "0016_recipe_family_history_days"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("pending_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "pending_approval")
