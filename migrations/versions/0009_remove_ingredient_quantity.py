"""Convert remaining ingredient quantities and remove free text."""

import re
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision = "0009_remove_ingredient_quantity"
down_revision = "0008_remove_source_page"
branch_labels = None
depends_on = None

NUMBER = r"\d+(?:[,.]\d+|/\d+)?"
QUANTITY = re.compile(rf"^({NUMBER})(?:\s*[-–]\s*({NUMBER}))?(?:\s+(.+))?$")


def number(value: str) -> Decimal:
    if "/" in value:
        top, bottom = value.split("/")
        return Decimal(top) / Decimal(bottom)
    return Decimal(value.replace(",", "."))


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT id, name, quantity, amount, unit, note FROM recipe_ingredients WHERE quantity IS NOT NULL"
    )).all()
    for row in rows:
        if row.amount is not None:
            continue
        value = row.quantity.strip()
        match = QUANTITY.fullmatch(value)
        if match:
            try:
                amount = max(number(part) for part in match.group(1, 2) if part)
            except ZeroDivisionError:
                match = None
        if match:
            rest = (match.group(3) or "").strip()
            words = rest.split()
            unit = words[0] if words else None
            extra = " ".join(words[1:])
            if extra.casefold() == row.name.strip().casefold():
                extra = ""
            note = " – ".join(part for part in (row.note, extra) if part) or None
            connection.execute(sa.text(
                "UPDATE recipe_ingredients SET amount=:amount, unit=:unit, note=:note WHERE id=:id"
            ), {"amount": str(amount), "unit": unit, "note": note, "id": row.id})
        elif value:
            note = " – ".join(part for part in (row.note, value) if part)
            connection.execute(sa.text(
                "UPDATE recipe_ingredients SET note=:note WHERE id=:id"
            ), {"note": note, "id": row.id})

    with op.batch_alter_table("recipe_ingredients") as batch_op:
        batch_op.drop_column("quantity")


def downgrade() -> None:
    with op.batch_alter_table("recipe_ingredients") as batch_op:
        batch_op.add_column(sa.Column("quantity", sa.String(), nullable=True))
