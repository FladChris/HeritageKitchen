"""Remove recipe source, the origin person is enough."""

import sqlalchemy as sa
from alembic import op

revision = "0011_remove_source"
down_revision = "0010_remove_step_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT id, origin_person, notes, source_name, source_url FROM recipes "
        "WHERE source_name IS NOT NULL OR source_url IS NOT NULL"
    )).all()
    for row in rows:
        origin_person = row.origin_person
        notes = row.notes
        if row.source_name and not origin_person:
            origin_person = row.source_name
        elif row.source_name and row.source_name != origin_person:
            notes = "\n".join(part for part in (notes, f"Quelle: {row.source_name}") if part)
        if row.source_url:
            notes = "\n".join(part for part in (notes, f"Quelle: {row.source_url}") if part)
        connection.execute(sa.text(
            "UPDATE recipes SET origin_person=:origin_person, notes=:notes WHERE id=:id"
        ), {"origin_person": origin_person, "notes": notes, "id": row.id})

    with op.batch_alter_table("recipes") as batch_op:
        batch_op.drop_column("source_name")
        batch_op.drop_column("source_url")


def downgrade() -> None:
    with op.batch_alter_table("recipes") as batch_op:
        batch_op.add_column(sa.Column("source_name", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("source_url", sa.String(), nullable=True))
