import pytest
from pydantic import ValidationError

from app.api.schemas.category_schema import CategoryOrderRequest
from app.api.schemas.favorite_schema import FavoriteOrderRequest
from app.api.schemas.recipe_order_schema import RecipeOrderRequest
from app.api.schemas.recipe_schema import RecipeCreateRequest, RecipeUpdateRequest

ORDER_SCHEMAS = [
    (CategoryOrderRequest, "category_ids", {}, "Each category must appear exactly once."),
    (RecipeOrderRequest, "recipe_ids", {"category_id": 1}, "Each recipe must appear exactly once."),
    (FavoriteOrderRequest, "favorite_ids", {}, "Each favorite must appear exactly once."),
]


@pytest.mark.parametrize(("schema", "field", "extra", "message"), ORDER_SCHEMAS)
def test_duplicate_order_ids_keep_their_field_and_error_message(schema, field, extra, message):
    with pytest.raises(ValidationError) as caught:
        schema.model_validate({**extra, field: [2, 1, 2]})
    error, = caught.value.errors()
    assert error["loc"] == (field,)
    assert error["msg"] == f"Value error, {message}"


@pytest.mark.parametrize(("schema", "field", "extra", "message"), ORDER_SCHEMAS)
@pytest.mark.parametrize("ids", [[], [3, 1, 2]])
def test_order_validation_preserves_empty_and_unsorted_unique_lists(schema, field, extra, message, ids):
    request = schema.model_validate({**extra, field: ids})
    assert request.model_dump() == {**extra, field: ids}


@pytest.mark.parametrize(("schema", "field", "extra", "message"), ORDER_SCHEMAS)
@pytest.mark.parametrize("invalid_id", [True, "2", 0])
def test_order_ids_remain_strict_positive_integers(schema, field, extra, message, invalid_id):
    with pytest.raises(ValidationError) as caught:
        schema.model_validate({**extra, field: [invalid_id]})
    assert caught.value.errors()[0]["loc"] == (field, 0)


@pytest.mark.parametrize("schema", [RecipeCreateRequest, RecipeUpdateRequest])
@pytest.mark.parametrize(("field", "items", "message"), [
    ("ingredient_groups", [{"position": 0, "name": "Teig"}, {"position": 0, "name": "Guss"}],
     "ingredient group positions must be unique"),
    ("ingredients", [{"position": 0, "name": "Mehl"}, {"position": 0, "name": "Zucker"}],
     "ingredient positions must be unique"),
    ("steps", [{"position": 0, "instruction": "Rühren"}, {"position": 0, "instruction": "Backen"}],
     "step positions must be unique"),
])
def test_duplicate_recipe_positions_keep_their_error_message(schema, field, items, message):
    with pytest.raises(ValidationError) as caught:
        schema.model_validate({"title": "Kuchen", "category_id": 1, field: items})
    error, = caught.value.errors()
    assert error["loc"] == ()
    assert error["msg"] == f"Value error, {message}"


@pytest.mark.parametrize("schema", [RecipeCreateRequest, RecipeUpdateRequest])
def test_unique_positions_still_require_references_to_supplied_ingredient_groups(schema):
    with pytest.raises(ValidationError) as caught:
        schema.model_validate({
            "title": "Kuchen", "category_id": 1,
            "ingredient_groups": [{"position": 0, "name": "Teig"}],
            "ingredients": [{"position": 0, "name": "Mehl", "group_position": 7}],
        })
    assert caught.value.errors()[0]["msg"] == "Value error, ingredient group does not exist"


@pytest.mark.parametrize("payload", [
    {"title": "Neuer Titel"},
    {"ingredient_groups": []},
    {"ingredients": []},
    {"steps": []},
    # A partial ingredient replacement can refer to a group already in the database.
    {"ingredients": [{"position": 0, "name": "Mehl", "group_position": 7}]},
])
def test_partial_recipe_updates_keep_omitted_lists_unset(payload):
    request = RecipeUpdateRequest.model_validate(payload)
    assert request.model_fields_set == payload.keys()
    assert request.model_dump(exclude_unset=True).keys() == payload.keys()
