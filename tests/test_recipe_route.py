from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.routes.recipe_route import router
from app.core.db import get_db
from app.models import Base, Category, User
from app.models.user_model import UserRole


@pytest.fixture
def recipe_client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'recipes.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        category = Category(name="Kuchen")
        session.add_all([category, User(id=1, username="Lena", password_hash="unused", role=UserRole.EDITOR)])
        session.commit()
        category_id = category.id

    def test_db():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_user] = lambda: User(id=1, role=UserRole.EDITOR)
    try:
        with TestClient(app) as client:
            yield client, category_id
    finally:
        engine.dispose()


@pytest.mark.parametrize("field", ["family_id", "linked_recipe_id", "variants"])
def test_recipe_writes_reject_removed_fields_as_extras(recipe_client, field):
    client, category_id = recipe_client
    payload = {"title": "Apfelkuchen", "category_id": category_id}
    recipe = client.post("/recipes", json=payload).json()
    value = [] if field == "variants" else recipe["id"]
    responses = [
        client.post("/recipes", json={**payload, field: value}),
        client.put(f"/recipes/{recipe['id']}", json={"title": "Geändert", field: value}),
    ]
    for response in responses:
        assert response.status_code == 422
        error, = response.json()["detail"]
        assert error["type"] == "extra_forbidden"
        assert error["loc"] == ["body", field]
    assert client.get("/recipes").json()["total"] == 1
    assert client.get(f"/recipes/{recipe['id']}").json()["title"] == payload["title"]


def test_recipes_keep_individual_content_and_store_tin_instructions_as_text(recipe_client):
    client, category_id = recipe_client
    payload = {"title": "Apfelkuchen", "category_id": category_id}
    small = client.post("/recipes", json={**payload, "title": "Kleiner Apfelkuchen", "servings": 8})
    assert small.status_code == 201
    ingredient_note = "Für die 20-cm-Form reichen 350 g Mehl."
    instruction = "Für die 28-cm-Form 500 g Mehl verwenden und 45 Minuten backen."
    large = client.post("/recipes", json={
        **payload,
        "servings": 12,
        "ingredients": [{"position": 0, "name": "Mehl", "amount": 500, "unit": "g", "note": ingredient_note}],
        "steps": [{"position": 0, "instruction": instruction}],
    })
    assert large.status_code == 201
    large_id = large.json()["id"]
    updated = client.put(f"/recipes/{large_id}", json={"title": "Großer Apfelkuchen"})
    assert updated.status_code == 200
    detail = client.get(f"/recipes/{large_id}").json()
    assert detail["servings"] == 12
    assert detail["ingredients"][0]["amount"] == "500.000"
    assert detail["ingredients"][0]["note"] == ingredient_note
    assert detail["steps"][0]["instruction"] == instruction
    assert client.get(f"/recipes/{small.json()['id']}").json() == small.json()

    recipes = client.get("/recipes").json()["items"]
    assert {recipe["id"] for recipe in recipes} == {large_id, small.json()["id"]}
    for recipe in [small.json(), large.json(), updated.json(), detail, *recipes]:
        assert {"family_id", "linked_recipe_id", "variants"}.isdisjoint(recipe)


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/recipes", {"title": "Kuchen", "category_id": 1}),
        ("PUT", "/recipes/1", {"title": "Neuer Titel"}),
        ("DELETE", "/recipes/1", None),
    ],
)
def test_anonymous_recipe_writes_require_login(method, path, payload):
    app = FastAPI()
    app.include_router(router)
    session = Mock()
    app.dependency_overrides[get_db] = lambda: session

    response = TestClient(app).request(method, path, json=payload)

    assert response.status_code == 401
    assert session.mock_calls == []


def test_step_times_are_stored_returned_and_replaced(recipe_client):
    client, category_id = recipe_client
    steps = [
        {"position": 0, "instruction": "Teig kneten", "duration_minutes": 20, "time_kind": "preparation"},
        {"position": 1, "instruction": "20 Minuten ruhen"},
        {"position": 2, "instruction": "Backen", "duration_minutes": 20160, "time_kind": "cooking"},
    ]
    created = client.post("/recipes", json={"title": "Brot", "category_id": category_id, "steps": steps})
    assert created.status_code == 201
    stored = [(s["duration_minutes"], s["time_kind"]) for s in created.json()["steps"]]
    assert stored == [(20, "preparation"), (None, None), (20160, "cooking")]
    recipe_id = created.json()["id"]
    kept = client.put(f"/recipes/{recipe_id}", json={"title": "Brot 2"})
    assert [s["duration_minutes"] for s in kept.json()["steps"]] == [20, None, 20160]
    cleared = client.put(f"/recipes/{recipe_id}", json={"steps": [{"position": 0, "instruction": "Teig kneten"}]})
    assert cleared.json()["steps"][0]["duration_minutes"] is None
    assert cleared.json()["steps"][0]["time_kind"] is None


@pytest.mark.parametrize("step_time", [
    {"duration_minutes": 10},
    {"time_kind": "rest"},
    {"duration_minutes": 0, "time_kind": "rest"},
    {"duration_minutes": -5, "time_kind": "rest"},
    {"duration_minutes": 20161, "time_kind": "rest"},
    {"duration_minutes": 10.5, "time_kind": "rest"},
    {"duration_minutes": 10, "time_kind": "timer"},
])
def test_invalid_step_times_are_rejected_on_create_and_update(recipe_client, step_time):
    client, category_id = recipe_client
    step = {"position": 0, "instruction": "Ruhen", **step_time}
    assert client.post("/recipes", json={"title": "Brot", "category_id": category_id, "steps": [step]}).status_code == 422
    recipe = client.post("/recipes", json={"title": "Brot", "category_id": category_id}).json()
    assert client.put(f"/recipes/{recipe['id']}", json={"steps": [step]}).status_code == 422
    assert client.get(f"/recipes/{recipe['id']}").json()["steps"] == []


def day_recipe(client, category_id, **extra):
    payload = {
        "title": "Sauerteigbrot", "category_id": category_id, "preparation_days": 3,
        "steps": [
            {"position": 0, "instruction": "Vorteig", "day": 1},
            {"position": 1, "instruction": "Teig", "day": 2},
            {"position": 2, "instruction": "Backen", "day": 3},
        ],
        **extra,
    }
    response = client.post("/recipes", json=payload)
    assert response.status_code == 201
    return response.json()


def test_steps_belong_to_days_with_optional_day_titles(recipe_client):
    client, category_id = recipe_client
    recipe = day_recipe(client, category_id, day_titles=["Einlegen", "", "  Backen  "])
    assert [step["day"] for step in recipe["steps"]] == [1, 2, 3]
    assert recipe["day_titles"] == ["Einlegen", "", "Backen"]
    single = client.post("/recipes", json={"title": "Kuchen", "category_id": category_id, "steps": [{"position": 0, "instruction": "Mischen"}]}).json()
    assert single["steps"][0]["day"] == 1
    assert single["day_titles"] is None


@pytest.mark.parametrize("payload", [
    {"preparation_days": 2, "steps": [{"position": 0, "instruction": "x", "day": 3}]},
    {"steps": [{"position": 0, "instruction": "x", "day": 2}]},
    {"steps": [{"position": 0, "instruction": "x", "day": 0}]},
    {"preparation_days": 14, "steps": [{"position": 0, "instruction": "x", "day": 15}]},
    {"preparation_days": 2, "day_titles": ["A", "B", "C"]},
    {"day_titles": ["x" * 101]},
])
def test_days_outside_the_preparation_days_are_rejected(recipe_client, payload):
    client, category_id = recipe_client
    assert client.post("/recipes", json={"title": "Brot", "category_id": category_id, **payload}).status_code == 422
    assert client.get("/recipes").json()["total"] == 0


def test_reducing_days_requires_reassigning_steps_from_removed_days(recipe_client):
    client, category_id = recipe_client
    recipe = day_recipe(client, category_id, day_titles=["A", "B", "C"])
    url = f"/recipes/{recipe['id']}"
    assert client.put(url, json={"preparation_days": 2}).status_code == 422
    assert client.put(url, json={"steps": [{"position": 0, "instruction": "x", "day": 4}]}).status_code == 422
    unchanged = client.get(url).json()
    assert unchanged["preparation_days"] == 3
    assert [step["day"] for step in unchanged["steps"]] == [1, 2, 3]
    assert unchanged["day_titles"] == ["A", "B", "C"]

    reassigned = [{"position": i, "instruction": s["instruction"], "day": min(s["day"], 2)} for i, s in enumerate(recipe["steps"])]
    ok = client.put(url, json={"preparation_days": 2, "day_titles": ["A", "B"], "steps": reassigned})
    assert ok.status_code == 200
    assert [step["day"] for step in ok.json()["steps"]] == [1, 2, 2]
    assert ok.json()["day_titles"] == ["A", "B"]
    single = {"preparation_days": 1, "day_titles": None, "steps": [{"position": 0, "instruction": "x", "day": 1}]}
    assert client.put(url, json=single).status_code == 200


def test_summary_list_exposes_step_times_for_cards(recipe_client):
    client, category_id = recipe_client
    steps = [{"position": 0, "instruction": "Backen", "duration_minutes": 35, "time_kind": "cooking"}]
    client.post("/recipes", json={"title": "Brot", "category_id": category_id, "cooking_time": 45, "steps": steps})
    item = client.get("/recipes", params={"summary": True}).json()["items"][0]
    assert item["step_times"] == {"preparation": None, "cooking": 35, "rest": None}
    assert "steps" not in item
