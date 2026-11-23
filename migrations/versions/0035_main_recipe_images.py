"""Promote the first gallery image where no main image has been set."""

import sqlalchemy as sa
from alembic import op

revision = "0035_main_recipe_images"
down_revision = "0034_step_times"
branch_labels = None
depends_on = None


def _promote_first(images: list[dict] | None) -> bool:
    if images and not any(image["is_main"] for image in images):
        images[0]["is_main"] = True
        return True
    return False


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE recipe_images
        SET is_main = TRUE
        WHERE id IN (
            SELECT id
            FROM (
                SELECT id,
                       ROW_NUMBER() OVER (PARTITION BY recipe_id ORDER BY position, id) AS gallery_rank,
                       SUM(CASE WHEN is_main THEN 1 ELSE 0 END)
                           OVER (PARTITION BY recipe_id) AS main_count
                FROM recipe_images
            ) AS gallery
            WHERE gallery_rank = 1 AND main_count = 0
        )
    """))

    versions = sa.table(
        "recipe_versions",
        sa.column("recipe_id", sa.Integer),
        sa.column("version", sa.Integer),
        sa.column("snapshot", sa.JSON),
        sa.column("changes", sa.JSON),
    )
    connection = op.get_bind()
    # Snapshots and image diffs already store images in gallery order.
    rows = connection.execute(sa.select(versions)).fetchall()
    for row in rows:
        snapshot_changed = isinstance(row.snapshot, dict) and _promote_first(row.snapshot.get("images"))
        image_diff = row.changes.get("images") if isinstance(row.changes, dict) else None
        before_changed = after_changed = False
        if isinstance(image_diff, dict):
            before_changed = _promote_first(image_diff.get("before"))
            after_changed = _promote_first(image_diff.get("after"))
        if snapshot_changed or before_changed or after_changed:
            connection.execute(
                versions.update()
                .where(versions.c.recipe_id == row.recipe_id, versions.c.version == row.version)
                .values(snapshot=row.snapshot, changes=row.changes)
            )


def downgrade() -> None:
    # A backfilled cover cannot be distinguished from a cover picked by an editor.
    pass
