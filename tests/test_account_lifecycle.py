import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.api.schemas import UserUpdateRequest
from app.core.db import create_database_engine
from app.models import (
    Base,
    Category,
    Favorite,
    Recipe,
    RecipeComment,
    RecipeRating,
    User,
    UserRole,
    UserSession,
)
from app.models.user_model import UserCategoryPosition
from app.services import recipe_rating_service, user_service


@pytest.fixture(params=["sqlite-without-foreign-keys", "postgresql"])
def engine(request, tmp_path):
    schema = None
    if request.param == "postgresql":
        url = os.environ.get("TEST_DATABASE_URL")
        if not url or make_url(url).get_backend_name() != "postgresql":
            pytest.skip("TEST_DATABASE_URL must point to PostgreSQL for this case")
        schema = f"test_account_lifecycle_{uuid4().hex}"
        engine = create_database_engine(
            make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
        )
        with engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {schema}"))
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle.db'}")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        if schema:
            with engine.begin() as connection:
                connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        engine.dispose()


def seed(session: Session, image_path: str | None = None) -> None:
    now = datetime.now(UTC)
    session.add_all(
        [
            User(id=1, username="petra", password_hash="x", role=UserRole.ADMIN),
            User(
                id=2, username="tim", password_hash="x",
                role=UserRole.EDITOR, profile_image_path=image_path,
            ),
            User(id=3, username="lena", password_hash="x", role=UserRole.READER),
            Category(id=1, name="Kuchen"),
            Recipe(id=1, title="Apfelkuchen", category_id=1),
        ]
    )
    session.flush()
    session.add_all(
        [
            RecipeComment(recipe_id=1, author_id=2, text="Mit Zimt"),
            RecipeRating(recipe_id=1, user_id=2, half_stars=10),
            RecipeRating(recipe_id=1, user_id=3, half_stars=6),
            Favorite(user_id=2, recipe_id=1),
            UserCategoryPosition(user_id=2, category_id=1, position=0),
            UserSession(
                user_id=2, token_hash="tim-token", expires_at=now + timedelta(days=1)
            ),
        ]
    )
    session.commit()


def test_permanent_deletion_keeps_recipes_and_removes_personal_data(engine, tmp_path):
    image = tmp_path / "profile.png"
    image.write_bytes(b"png")
    with Session(engine) as session:
        seed(session, str(image))
        user_service.delete_user(db_session=session, user_id=2)

    with Session(engine) as session:
        assert session.get(User, 2) is None
        assert session.get(Recipe, 1) is not None
        (comment,) = session.scalars(select(RecipeComment)).all()
        assert comment.text == "Mit Zimt"
        assert comment.author_id is None
        assert session.scalars(select(Favorite)).all() == []
        assert session.scalars(select(UserCategoryPosition)).all() == []
        assert session.scalars(select(UserSession)).all() == []
        assert session.scalars(select(RecipeRating.user_id)).all() == [3]
        ratings = recipe_rating_service.get_ratings(session, 1)
        assert (ratings.average, ratings.count) == (3.0, 1)
    assert not image.exists()


def test_deactivation_keeps_personal_data_until_reactivation(engine):
    with Session(engine) as session:
        seed(session)
        user_service.update_user(
            db_session=session, user_id=2,
            user_update_request=UserUpdateRequest(is_active=False),
        )

    with Session(engine) as session:
        assert session.scalars(select(UserSession)).all() == []
        assert session.get(User, 2).is_active is False
        user_service.update_user(
            db_session=session, user_id=2,
            user_update_request=UserUpdateRequest(is_active=True),
        )

    with Session(engine) as session:
        assert session.scalars(select(UserSession)).all() == []
        assert session.scalars(select(RecipeComment.author_id)).all() == [2]
        assert sorted(session.scalars(select(RecipeRating.user_id))) == [2, 3]
        assert session.scalars(select(Favorite.user_id)).all() == [2]
        assert session.scalars(select(UserCategoryPosition.user_id)).all() == [2]
        assert recipe_rating_service.get_ratings(session, 1).count == 2


def test_last_active_admin_cannot_be_deleted(engine):
    with Session(engine) as session:
        seed(session)
        with pytest.raises(HTTPException) as error:
            user_service.delete_user(db_session=session, user_id=1)
        assert error.value.status_code == 409
        assert session.get(User, 1) is not None
