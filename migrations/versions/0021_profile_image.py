"""Store the optional profile image for each account."""

import sqlalchemy as sa
from alembic import op

revision = "0021_profile_image"
down_revision = "0024_recipe_ratings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("profile_image_path", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "profile_image_path")
