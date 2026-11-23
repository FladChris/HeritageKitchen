"""Add password reset tokens."""

import sqlalchemy as sa
from alembic import op

revision = "0007_password_resets"
down_revision = "0006_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_password_resets_token_hash", "password_resets", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_password_resets_token_hash", table_name="password_resets")
    op.drop_table("password_resets")
