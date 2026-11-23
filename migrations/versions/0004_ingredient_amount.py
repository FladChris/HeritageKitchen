"""Add structured ingredient amounts."""

import re
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision = "0004_ingredient_amount"
down_revision = "0003_recipe_origin"
branch_labels = None
depends_on = None

UNITS = "g|kg|ml|l|EL|TL|Prise|Stück|Päckchen"
QUANTITY = re.compile(rf"^([0-9]+(?:[,.][0-9]+|/[0-9]+)?)\s+({UNITS})$")


def upgrade() -> None:
    with op.batch_alter_table("recipe_ingredients") as batch_op:
        batch_op.add_column(sa.Column("amount", sa.Numeric(12, 3), nullable=True))
        batch_op.add_column(sa.Column("unit", sa.String(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, quantity FROM recipe_ingredients WHERE quantity IS NOT NULL"))
    for row in rows:
        match = QUANTITY.fullmatch(row.quantity.strip())
        if match:
            value, unit = match.groups()
            if "/" in value:
                numerator, denominator = value.split("/")
                if int(denominator) == 0:
                    continue
                amount = Decimal(numerator) / Decimal(denominator)
            else:
                amount = Decimal(value.replace(",", "."))
            connection.execute(
                sa.text("UPDATE recipe_ingredients SET amount = :amount, unit = :unit WHERE id = :id"),
                {"amount": str(amount), "unit": unit, "id": row.id},
            )


def downgrade() -> None:
    with op.batch_alter_table("recipe_ingredients") as batch_op:
        batch_op.drop_column("unit")
        batch_op.drop_column("amount")
