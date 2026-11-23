from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import Base

if TYPE_CHECKING:
    from app.models.recipe_model import Recipe


class RecipeImage(Base):
    __tablename__ = "recipe_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    file_path: Mapped[str] = mapped_column(index=True)
    alt_text: Mapped[str | None]
    is_main: Mapped[bool] = mapped_column(default=False, server_default=false())
    position: Mapped[int] = mapped_column(default=0, server_default="0")

    recipe: Mapped["Recipe"] = relationship(back_populates="images")
