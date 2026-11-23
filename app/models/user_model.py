from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Literal

from sqlalchemy import ForeignKey, String, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import Base

if TYPE_CHECKING:
    from app.models.favorite_model import Favorite
    from app.models.recipe_comment_model import RecipeComment
    from app.models.session_model import UserSession


class UserRole(StrEnum):
    READER = "reader"
    EDITOR = "editor"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"
    __table_args__: ClassVar[dict[str, bool]] = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    email: Mapped[str | None] = mapped_column(unique=True)
    password_hash: Mapped[str]
    email_verified_at: Mapped[datetime | None]
    email_verification_hash: Mapped[str | None] = mapped_column(unique=True, index=True)
    email_verification_expires_at: Mapped[datetime | None]
    profile_image_path: Mapped[str | None]
    role: Mapped[UserRole] = mapped_column(default=UserRole.READER)
    is_active: Mapped[bool] = mapped_column(default=True)
    pending_approval: Mapped[bool] = mapped_column(server_default=false())
    category_sort: Mapped[Literal["manual", "name", "count"] | None] = mapped_column(String(6))
    recipe_view: Mapped[Literal["list", "grid"] | None] = mapped_column(String(4))
    favorite_sort: Mapped[Literal["recent", "name", "manual"] | None] = mapped_column(String(6))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    recipe_comments: Mapped[list["RecipeComment"]] = relationship(back_populates="author")
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    category_positions: Mapped[list["UserCategoryPosition"]] = relationship(
        cascade="all, delete-orphan"
    )
    recipe_positions: Mapped[list["UserRecipePosition"]] = relationship(
        cascade="all, delete-orphan"
    )


class UserCategoryPosition(Base):
    __tablename__ = "user_category_positions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int]


class UserRecipePosition(Base):
    __tablename__ = "user_recipe_positions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int]
