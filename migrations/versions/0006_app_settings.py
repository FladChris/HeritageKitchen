"""Add application settings."""

import sqlalchemy as sa
from alembic import op

revision = "0006_app_settings"
down_revision = "0005_image_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
