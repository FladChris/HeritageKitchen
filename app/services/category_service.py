import re
from pathlib import Path
from unicodedata import combining, normalize

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.api.schemas.category_schema import (
    CategoryCreateRequest,
    CategoryOrderRequest,
    CategoryResponse,
    CategoryUpdateRequest,
)
from app.api.schemas.user_schema import ViewPreferencesUpdate
from app.core.config import settings
from app.core.db import lock_sqlite_writes
from app.models.category_model import Category
from app.models.recipe_model import Recipe
from app.models.user_model import User, UserCategoryPosition
from app.services import view_preferences_service
from app.services.recipe_image_service import store_upload


def _lock_category_name_writes(db_session: Session) -> None:
    # Serialize the check and write even when no categories exist yet.
    if db_session.get_bind().dialect.name == "postgresql":
        db_session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('heritagekitchen:category-name'))")
        )
    else:
        lock_sqlite_writes(db_session)


def _category_name_key(name: str) -> str:
    folded = "".join(char for char in normalize("NFD", name.casefold()) if not combining(char))
    return re.sub(r"([aou])e", r"\1", folded)


def _require_unique_category_name(
    db_session: Session, name: str, *, exclude_id: int | None = None
) -> None:
    name_key = _category_name_key(name)
    for category_id, existing_name in db_session.execute(select(Category.id, Category.name)):
        if category_id != exclude_id and _category_name_key(existing_name) == name_key:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Category name already exists.",
            )


def _category_response(db_session: Session, category: Category) -> CategoryResponse:
    count = db_session.scalar(
        select(func.count(Recipe.id)).where(Recipe.category_id == category.id)
    ) or 0
    return CategoryResponse.model_validate(category).model_copy(update={"recipe_count": count})


def create_category(
    *,
    db_session: Session,
    category_create_request: CategoryCreateRequest,
) -> CategoryResponse:
    _lock_category_name_writes(db_session)
    _require_unique_category_name(db_session, category_create_request.name)
    category = Category(**category_create_request.model_dump())
    db_session.add(category)
    db_session.commit()
    return _category_response(db_session, category)


def list_categories(*, db_session: Session) -> list[CategoryResponse]:
    rows = db_session.execute(
        select(Category, func.count(Recipe.id))
        .outerjoin(Recipe, Recipe.category_id == Category.id)
        .group_by(Category.id)
        .order_by(Category.name, Category.id)
    )
    return [
        CategoryResponse.model_validate(category).model_copy(update={"recipe_count": count})
        for category, count in rows
    ]


def set_category_order(
    *, db_session: Session, user: User, order: CategoryOrderRequest
) -> list[CategoryResponse]:
    current_ids = set(db_session.scalars(select(Category.id)).all())
    if set(order.category_ids) != current_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Categories have changed. Reload before saving their order.",
        )
    view_preferences_service.update_view_preferences(
        db_session, user, ViewPreferencesUpdate(category_order=order, category_sort="manual")
    )
    positions = {category_id: index for index, category_id in enumerate(order.category_ids)}
    return sorted(
        list_categories(db_session=db_session),
        key=lambda category: positions.get(category.id, len(positions)),
    )


def get_category(*, db_session: Session, category_id: int) -> CategoryResponse:
    category = db_session.get(Category, category_id)

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found.",
        )

    return _category_response(db_session, category)


def require_category_for_assignment(
    db_session: Session, category_id: int, *, sqlite_locked: bool = False,
) -> Category:
    # Hold the category until the recipe is saved so deletion cannot race assignment.
    if not sqlite_locked:
        lock_sqlite_writes(db_session)
    category = db_session.get(
        Category, category_id, with_for_update={"read": True, "key_share": True}
    )
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found.",
        )
    return category


def update_category(
    *,
    db_session: Session,
    category_id: int,
    category_update_request: CategoryUpdateRequest,
) -> CategoryResponse:
    name = category_update_request.name
    if name is not None:
        _lock_category_name_writes(db_session)
    category = db_session.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found.",
        )
    if name is not None and name != category.name:
        _require_unique_category_name(db_session, name, exclude_id=category_id)
    update_data = category_update_request.model_dump(exclude_unset=True)

    for fieldname, fieldvalue in update_data.items():
        setattr(category, fieldname, fieldvalue)

    db_session.commit()
    return _category_response(db_session, category)


def delete_category(*, db_session: Session, category_id: int) -> None:
    lock_sqlite_writes(db_session)
    category = db_session.get(Category, category_id, with_for_update=True)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found.",
        )

    assigned_recipe_count = db_session.scalar(
        select(func.count(Recipe.id)).where(Recipe.category_id == category_id)
    )
    if assigned_recipe_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category still has recipes assigned and cannot be deleted.",
        )

    old_path = category.image_path
    # Also remove personal positions on SQLite, where foreign keys may be disabled.
    db_session.execute(
        delete(UserCategoryPosition).where(UserCategoryPosition.category_id == category_id)
    )
    db_session.delete(category)
    db_session.commit()
    _remove_image_file(old_path)


def _remove_image_file(image_path: str | None) -> None:
    if not image_path:
        return
    # /media/recipe-images/categories/3/x.jpg -> recipe-images-Ordner/categories/3/x.jpg
    relative_path = image_path.removeprefix(settings.media_url_prefix).lstrip("/")
    categories_dir = (Path(settings.recipe_images_dir) / "categories").resolve()
    file_path = (Path(settings.recipe_images_dir) / relative_path).resolve()
    # Only uploaded category images may be deleted, never other media files.
    if file_path.is_relative_to(categories_dir):
        file_path.unlink(missing_ok=True)


def set_category_image(
    *, db_session: Session, category_id: int, image: UploadFile
) -> CategoryResponse:
    category = db_session.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found.",
        )

    old_path = category.image_path
    new_path = store_upload(image, f"categories/{category_id}")
    try:
        category.image_path = new_path
        db_session.commit()
    except Exception:
        db_session.rollback()
        _remove_image_file(new_path)
        raise
    _remove_image_file(old_path)
    return _category_response(db_session, category)


def remove_category_image(*, db_session: Session, category_id: int) -> CategoryResponse:
    category = db_session.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found.",
        )

    old_path = category.image_path
    category.image_path = None
    db_session.commit()
    _remove_image_file(old_path)
    return _category_response(db_session, category)
