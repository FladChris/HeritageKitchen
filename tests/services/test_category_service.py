from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.api.schemas.category_schema import (
    CategoryCreateRequest,
    CategoryResponse,
    CategoryUpdateRequest,
)
from app.models.category_model import Category
from app.services import category_service


def test_create_category():
    db_session = Mock()
    db_session.execute.return_value = []

    def add_category_id(category: Category) -> None:
        category.id = 1

    db_session.add.side_effect = add_category_id

    category_create_request = CategoryCreateRequest(
        name="Desserts",
        description="This is a test category",
        image_alt_text="Test Category Image",
    )

    category = category_service.create_category(
        db_session=db_session,
        category_create_request=category_create_request,
    )

    assert isinstance(category, CategoryResponse)
    assert category.id == 1
    assert category.name == "Desserts"
    assert category.description == "This is a test category"
    assert category.image_path is None
    assert category.image_alt_text == "Test Category Image"

    db_session.add.assert_called_once()
    db_session.commit.assert_called_once()


def test_list_categories():
    db_session = Mock()
    db_session.get.return_value = None
    first_category = Category(id=1, name="Desserts")
    second_category = Category(id=2, name="Main Dishes")
    db_session.execute.return_value = [(first_category, 2), (second_category, 0)]

    categories = category_service.list_categories(db_session=db_session)

    assert len(categories) == 2
    assert all(isinstance(category, CategoryResponse) for category in categories)
    assert categories[0].name == "Desserts"
    assert categories[0].recipe_count == 2
    assert categories[1].name == "Main Dishes"
    assert categories[1].recipe_count == 0
    db_session.execute.assert_called_once()


def test_get_category():
    db_session = Mock()
    category = Category(id=1, name="Desserts")
    db_session.get.return_value = category

    result = category_service.get_category(db_session=db_session, category_id=1)

    assert isinstance(result, CategoryResponse)
    assert result.name == "Desserts"
    db_session.get.assert_called_once_with(Category, 1)


def test_get_category_raises_not_found():
    db_session = Mock()
    db_session.get.return_value = None

    with pytest.raises(HTTPException) as e:
        category_service.get_category(db_session=db_session, category_id=999)

    assert e.value.status_code == 404
    assert e.value.detail == "Category not found."


def test_update_category():
    db_session = Mock()
    category = Category(
        id=1,
        name="Desserts",
        description="Old description",
        image_path="/old-path.jpg",
        image_alt_text="Old alt text",
    )
    db_session.get.return_value = category
    db_session.execute.return_value = [(1, category.name)]
    category_update_request = CategoryUpdateRequest(
        name="Cakes",
        description="New description",
    )

    updated_category = category_service.update_category(
        db_session=db_session,
        category_id=1,
        category_update_request=category_update_request,
    )

    assert isinstance(updated_category, CategoryResponse)
    assert updated_category.name == "Cakes"
    assert updated_category.description == "New description"
    assert updated_category.image_path == "/old-path.jpg"
    assert updated_category.image_alt_text == "Old alt text"
    db_session.commit.assert_called_once()


def test_update_category_raises_not_found():
    db_session = Mock()
    db_session.get.return_value = None
    category_update_request = CategoryUpdateRequest(name="Cakes")

    with pytest.raises(HTTPException) as e:
        category_service.update_category(
            db_session=db_session,
            category_id=999,
            category_update_request=category_update_request,
        )

    assert e.value.status_code == 404
    assert e.value.detail == "Category not found."


def test_delete_category():
    db_session = Mock()
    category = Category(id=1, name="Desserts")
    db_session.get.side_effect = [category, None]
    db_session.scalar.return_value = 0

    result = category_service.delete_category(db_session=db_session, category_id=1)

    assert result is None
    db_session.delete.assert_called_once_with(category)
    db_session.commit.assert_called_once()


def test_delete_category_raises_conflict_when_recipes_assigned():
    db_session = Mock()
    category = Category(id=1, name="Desserts")
    db_session.get.return_value = category
    db_session.scalar.return_value = 2

    with pytest.raises(HTTPException) as e:
        category_service.delete_category(db_session=db_session, category_id=1)

    assert e.value.status_code == 409
    assert e.value.detail == (
        "Category still has recipes assigned and cannot be deleted."
    )
    db_session.delete.assert_not_called()


def test_delete_category_raises_not_found():
    db_session = Mock()
    db_session.get.return_value = None

    with pytest.raises(HTTPException) as e:
        category_service.delete_category(db_session=db_session, category_id=999)

    assert e.value.status_code == 404
    assert e.value.detail == "Category not found."
