from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import Base

if TYPE_CHECKING:
    from app.models.recipe_model import Recipe


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str | None]
    image_path: Mapped[str | None]
    image_alt_text: Mapped[str | None]

    recipes: Mapped[list["Recipe"]] = relationship(back_populates="category")
