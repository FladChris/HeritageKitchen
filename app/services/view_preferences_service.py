from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.api.schemas.user_schema import ViewPreferences, ViewPreferencesUpdate
from app.models.category_model import Category
from app.models.user_model import User, UserCategoryPosition


def get_view_preferences(db_session: Session, user: User) -> ViewPreferences:
    category_ids = db_session.scalars(
        select(UserCategoryPosition.category_id)
        .where(UserCategoryPosition.user_id == user.id)
        .order_by(UserCategoryPosition.position)
    ).all()
    return ViewPreferences(
        category_sort=user.category_sort or ("manual" if category_ids else "name"),
        recipe_view=user.recipe_view or "list",
        category_ids=list(category_ids),
    )


def update_view_preferences(
    db_session: Session, user: User, request: ViewPreferencesUpdate
) -> None:
    values = request.model_dump(exclude_unset=True, exclude={"category_order"})
    if request.category_order is not None:
        # Lock the user's row before replacing their positions, even for an order-only update.
        values.setdefault("category_sort", User.category_sort)
    if values:
        db_session.execute(update(User).where(User.id == user.id).values(**values))

    if request.category_order is not None:
        category_ids = request.category_order.category_ids
        # A category can have been deleted since the page was opened.
        existing_ids = set(
            db_session.scalars(
                select(Category.id)
                .where(Category.id.in_(category_ids))
                .order_by(Category.id)
                .with_for_update(read=True, key_share=True)
            )
        )
        db_session.execute(
            delete(UserCategoryPosition).where(UserCategoryPosition.user_id == user.id)
        )
        db_session.add_all(
            UserCategoryPosition(
                user_id=user.id, category_id=category_id, position=position
            )
            for position, category_id in enumerate(category_ids)
            if category_id in existing_ids
        )
    db_session.commit()
