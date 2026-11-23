"""Use usernames for attribution and require email verification."""

import sqlalchemy as sa
from alembic import op

revision = "0036_verified_account_email"
down_revision = "0035_main_recipe_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime()))
    op.add_column("users", sa.Column("email_verification_hash", sa.String()))
    op.add_column("users", sa.Column("email_verification_expires_at", sa.DateTime()))
    op.create_index(
        "ix_users_email_verification_hash",
        "users",
        ["email_verification_hash"],
        unique=True,
    )
    # Native DROP COLUMN keeps the users table and its foreign-key references intact.
    op.drop_column("users", "display_name")


def downgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String()))
    op.execute(sa.text("UPDATE users SET display_name = username"))
    op.drop_index("ix_users_email_verification_hash", table_name="users")
    op.drop_column("users", "email_verification_expires_at")
    op.drop_column("users", "email_verification_hash")
    op.drop_column("users", "email_verified_at")
