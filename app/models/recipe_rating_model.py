from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import Base


class RecipeRating(Base):
    __tablename__ = "recipe_ratings"
    __table_args__ = (
        CheckConstraint(
            "half_stars IN (2, 3, 4, 5, 6, 7, 8, 9, 10)",
            name="ck_recipe_ratings_half_stars",
        ),
    )

    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    half_stars: Mapped[int]
