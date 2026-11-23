"""Move the shared category order into accounts without personal positions."""

import json

import sqlalchemy as sa
from alembic import op

revision = "0027_personal_category_order"
down_revision = "0021_profile_image"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    settings = sa.table("app_settings", sa.column("key"), sa.column("value"))
    shared_order = settings.c.key == "category_order"
    value = connection.scalar(sa.select(settings.c.value).where(shared_order))
    if value is None:
        return

    category_ids = json.loads(value)
    if not isinstance(category_ids, list) or any(
        type(category_id) is not int for category_id in category_ids
    ):
        raise ValueError("The shared category order must contain a list of category IDs.")

    categories = sa.table("categories", sa.column("id", sa.Integer()))
    existing_ids = set(connection.scalars(sa.select(categories.c.id)))
    order = {
        category_id: position
        for position, category_id in enumerate(category_ids)
        if category_id in existing_ids
    }
    if order:
        users = sa.table(
            "users", sa.column("id", sa.Integer()), sa.column("category_sort", sa.String())
        )
        positions = sa.table(
            "user_category_positions",
            sa.column("user_id", sa.Integer()),
            sa.column("category_id", sa.Integer()),
            sa.column("position", sa.Integer()),
        )
        without_order = ~sa.select(positions.c.user_id).where(
            positions.c.user_id == users.c.id
        ).exists()
        user_ids = connection.scalars(sa.select(users.c.id).where(without_order)).all()
        if user_ids:
            connection.execute(
                users.update()
                .where(without_order, users.c.category_sort.is_(None))
                .values(category_sort="manual")
            )
            connection.execute(
                positions.insert(),
                [
                    {"user_id": user_id, "category_id": category_id, "position": position}
                    for user_id in user_ids
                    for category_id, position in order.items()
                ],
            )

    connection.execute(settings.delete().where(shared_order))


def downgrade() -> None:
    # The migrated positions belong to each account and may already have been edited.
    # Keep them; there is no longer a canonical shared order to restore.
    pass
