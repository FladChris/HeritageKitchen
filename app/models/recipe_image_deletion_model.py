from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import Base


class RecipeImageDeletion(Base):
    __tablename__ = "recipe_image_deletions"

    # The entry must survive deletion of the owning recipe.
    recipe_id: Mapped[int] = mapped_column(primary_key=True)
    file_path: Mapped[str] = mapped_column(primary_key=True)
