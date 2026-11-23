from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import Base

if TYPE_CHECKING:
    from app.models.recipe_model import Recipe
    from app.models.user_model import User


class RecipeComment(Base):
    __tablename__ = "recipe_comments"
    __table_args__ = (
        Index("ix_recipe_comments_recipe_created", "recipe_id", "created_at", "id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recipe: Mapped["Recipe"] = relationship(back_populates="comments")
    author: Mapped["User | None"] = relationship(back_populates="recipe_comments")
