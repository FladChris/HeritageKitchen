"""Give registrations still awaiting approval the editor default role."""

import sqlalchemy as sa
from alembic import op

revision = "0020_pending_editor_default"
down_revision = "0019_remove_recipe_families"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Pending self-registrations stored the former reader default.
    op.execute(
        sa.text(
            "UPDATE users SET role = 'EDITOR' "
            "WHERE pending_approval = :pending AND is_active = :active AND role = 'READER'"
        ).bindparams(pending=True, active=False)
    )


def downgrade() -> None:
    # The former default cannot be told apart from a deliberate choice; keep roles.
    pass
