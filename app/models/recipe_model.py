from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import Base

if TYPE_CHECKING:
    from app.models.category_model import Category
    from app.models.favorite_model import Favorite
    from app.models.recipe_comment_model import RecipeComment
    from app.models.recipe_image_model import RecipeImage


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = (
        CheckConstraint("preparation_days BETWEEN 1 AND 14", name="ck_recipe_preparation_days"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    title: Mapped[str]
    summary: Mapped[str | None]
    preparation_time: Mapped[int | None]  # minutes
    cooking_time: Mapped[int | None]  # minutes
    cooking_time_max: Mapped[int | None]  # minutes, upper end of a range
    rest_time: Mapped[int | None]  # minutes
    rest_time_max: Mapped[int | None]  # minutes, upper end of a range
    servings: Mapped[int | None]
    history: Mapped[str | None]
    preparation_days: Mapped[int] = mapped_column(default=1, server_default="1")
    day_titles: Mapped[list[str] | None] = mapped_column(JSON)  # optional titles, one entry per day
    origin_person: Mapped[str | None]
    notes: Mapped[str | None]
    important_notes: Mapped[str | None]
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    category: Mapped["Category | None"] = relationship(back_populates="recipes")
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", passive_deletes=True
    )
    comments: Mapped[list["RecipeComment"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
    images: Mapped[list["RecipeImage"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan",
        order_by="RecipeImage.position, RecipeImage.id",
    )
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeIngredient.position",
    )
    ingredient_groups: Mapped[list["RecipeIngredientGroup"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan",
        order_by="RecipeIngredientGroup.position",
    )
    steps: Mapped[list["RecipeStep"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeStep.position",
    )


class RecipeIngredientGroup(Base):
    __tablename__ = "recipe_ingredient_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    position: Mapped[int]
    name: Mapped[str]

    recipe: Mapped["Recipe"] = relationship(back_populates="ingredient_groups")
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(back_populates="group")


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    position: Mapped[int]
    group_id: Mapped[int | None] = mapped_column(ForeignKey("recipe_ingredient_groups.id"))
    name: Mapped[str]
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit: Mapped[str | None]
    note: Mapped[str | None]  # chopped, room temperature, optional

    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients")
    group: Mapped["RecipeIngredientGroup | None"] = relationship(back_populates="ingredients")

    @property
    def group_position(self) -> int | None:
        return self.group.position if self.group else None


class RecipeStep(Base):
    __tablename__ = "recipe_steps"
    __table_args__ = (
        CheckConstraint("day BETWEEN 1 AND 14", name="ck_recipe_step_day"),
        CheckConstraint(
            "(duration_minutes IS NULL AND time_kind IS NULL) OR "
            "(duration_minutes IS NOT NULL AND time_kind IS NOT NULL AND duration_minutes BETWEEN 1 AND 20160 AND time_kind IN ('preparation', 'cooking', 'rest'))",
            name="ck_recipe_step_time",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    position: Mapped[int]
    instruction: Mapped[str]
    heading: Mapped[str | None]
    is_important: Mapped[bool] = mapped_column(default=False)
    note: Mapped[str | None]
    duration_minutes: Mapped[int | None]
    time_kind: Mapped[str | None]  # preparation, cooking or rest
    day: Mapped[int] = mapped_column(default=1, server_default="1")

    recipe: Mapped["Recipe"] = relationship(back_populates="steps")
