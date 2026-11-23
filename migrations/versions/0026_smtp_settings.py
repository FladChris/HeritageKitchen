"""Store the cookbook's central SMTP settings and test status."""

import sqlalchemy as sa
from alembic import op

revision = "0026_smtp_settings"
down_revision = "0027_personal_category_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    settings = op.create_table(
        "smtp_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("host", sa.String(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("encryption", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("sender", sa.String(), nullable=False),
        sa.Column("encrypted_password", sa.Text()),
        sa.Column("tested_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_smtp_settings_singleton"),
    )
    op.bulk_insert(
        settings,
        [
            {
                "id": 1,
                "host": "",
                "port": 587,
                "encryption": "starttls",
                "username": "",
                "sender": "",
                "version": 1,
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("smtp_settings")
