import io
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from PIL import Image
from sqlalchemy import func, inspect, select

from app.core import db
from app.models.session_model import UserSession


def test_registration_and_session(client):
    assert "users" in inspect(db.engine).get_table_names()
    assert client.get("/api/auth/me").status_code == 401

    registration = {"username": "chefmax", "password": "supersecret123"}
    response = client.post("/api/auth/register", json=registration)
    assert response.status_code == 201
    assert response.json()["role"] == "admin"
    assert response.json()["is_active"] is True
    assert response.json()["pending_approval"] is False

    response = client.post("/api/auth/login", json=registration)
    assert response.status_code == 200
    assert "heritagekitchen_session" in client.cookies
    assert client.get("/api/auth/me").json()["username"] == "chefmax"
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_self_registration_requires_admin_approval(client):
    admin = {"username": "chefmax", "password": "supersecret123"}
    editor = {"username": "secondchef", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=admin).status_code == 201
    response = client.post("/api/auth/register", json=editor)
    assert response.status_code == 201
    assert "set-cookie" not in response.headers
    registered = response.json()
    assert registered["role"] == "editor"
    assert registered["is_active"] is False
    assert registered["pending_approval"] is True
    assert client.post("/api/auth/register", json=editor).status_code == 409

    response = client.post("/api/auth/login", json=editor)
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    with db.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(UserSession)) == 0

    user_path = f"/api/users/{registered['id']}"
    assert client.put(user_path, json={"is_active": True}).status_code == 401
    assert client.post("/api/auth/login", json=admin).status_code == 200
    disabled = client.post("/api/users", json={
        "username": "disabledchef", "password": "supersecret123", "is_active": False,
    }).json()
    assert disabled["is_active"] is False
    assert disabled["pending_approval"] is False
    ordinary_reader = {"username": "guestchef", "password": "supersecret123"}
    assert client.post("/api/users", json=ordinary_reader).status_code == 201
    assert client.post("/api/auth/logout").status_code == 204
    assert client.post("/api/auth/login", json=ordinary_reader).status_code == 200
    assert client.put(user_path, json={"is_active": True}).status_code == 403
    assert client.post("/api/auth/logout").status_code == 204

    assert client.post("/api/auth/login", json=admin).status_code == 200
    users = {user["username"]: user for user in client.get("/api/users").json()}
    assert users["secondchef"]["pending_approval"] is True
    assert users["disabledchef"]["pending_approval"] is False
    response = client.put(user_path, json={"is_active": True})
    assert response.status_code == 200
    assert response.json()["is_active"] is True
    assert response.json()["pending_approval"] is False
    assert client.post("/api/auth/logout").status_code == 204

    response = client.post("/api/auth/login", json=editor)
    assert response.status_code == 200
    assert response.json()["role"] == "editor"
    assert client.get("/api/auth/me").json()["username"] == "secondchef"


def test_concurrent_registrations_create_only_one_bootstrap_admin(client):
    barrier = Barrier(2, timeout=10)

    def register(username):
        barrier.wait()
        return client.post("/api/auth/register", json={
            "username": username, "password": "supersecret123",
        })

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(register, ["chefmax", "secondchef"]))

    assert [response.status_code for response in responses] == [201, 201]
    assert sorted(
        (user["role"], user["is_active"], user["pending_approval"])
        for user in (response.json() for response in responses)
    ) == [("admin", True, False), ("editor", False, True)]


@pytest.mark.filterwarnings("error::sqlalchemy.exc.SAWarning")
def test_ingredient_groups(client):
    credentials = {"username": "chefmax", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    category_id = client.post("/api/categories", json={"name": "Backen"}).json()["id"]

    response = client.post("/api/recipes", json={
        "title": "Torte",
        "category_id": category_id,
        "ingredient_groups": [
            {"position": 0, "name": "Teig"},
            {"position": 1, "name": "Sahne"},
        ],
        "ingredients": [
            {"position": 0, "group_position": 1, "name": "Sahne"},
            {"position": 1, "group_position": 0, "name": "Mehl"},
            {"position": 2, "group_position": 0, "name": "Eier"},
        ],
    })
    assert response.status_code == 201, response.text
    recipe_id = response.json()["id"]
    recipe = client.get(f"/api/recipes/{recipe_id}").json()
    assert [group["name"] for group in recipe["ingredient_groups"]] == ["Teig", "Sahne"]
    assert [(item["name"], item["group_position"]) for item in recipe["ingredients"]] == [
        ("Sahne", 1), ("Mehl", 0), ("Eier", 0)
    ]

    response = client.put(f"/api/recipes/{recipe_id}", json={
        "ingredient_groups": [{"position": 0, "name": "Schokoguss"}],
        "ingredients": [{"position": 0, "group_position": 0, "name": "Schokolade"}],
    })
    assert response.status_code == 200, response.text
    recipe = client.get(f"/api/recipes/{recipe_id}").json()
    assert [group["name"] for group in recipe["ingredient_groups"]] == ["Schokoguss"]
    assert recipe["ingredients"][0]["group_position"] == 0

    plain = client.post("/api/recipes", json={
        "title": "Brot", "category_id": category_id,
        "ingredients": [{"position": 0, "name": "Wasser"}]
    })
    assert plain.status_code == 201, plain.text
    assert plain.json()["ingredient_groups"] == []
    assert plain.json()["ingredients"][0]["group_position"] is None


def test_ingredient_amounts(client):
    credentials = {"username": "chefmax", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    category_id = client.post("/api/categories", json={"name": "Suppen"}).json()["id"]

    response = client.post("/api/recipes", json={
        "title": "Suppe",
        "category_id": category_id,
        "ingredients": [
            {"position": 0, "name": "Salz", "amount": "1/2", "unit": "TL"},
            {"position": 1, "name": "Öl", "amount": "4,5", "unit": "EL"},
            {"position": 2, "name": "Wasser", "amount": "1", "unit": "Schuss"},
        ],
    })
    assert response.status_code == 201, response.text
    recipe_id = response.json()["id"]
    ingredients = client.get(f"/api/recipes/{recipe_id}").json()["ingredients"]
    assert [(item["amount"], item["unit"]) for item in ingredients] == [
        ("0.500", "TL"), ("4.500", "EL"), ("1.000", "Schuss")
    ]

    response = client.put(f"/api/recipes/{recipe_id}", json={
        "ingredients": [{"position": 0, "name": "Salz", "amount": "2.25", "unit": "g"}]
    })
    assert response.status_code == 200, response.text
    assert response.json()["ingredients"][0]["amount"] == "2.250"


def test_recipe_origin(client):
    credentials = {"username": "chefmax", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    category_id = client.post("/api/categories", json={"name": "Backen"}).json()["id"]

    response = client.post("/api/recipes", json={
        "title": "Apfelkuchen",
        "category_id": category_id,
        "origin_person": " Oma Susi ",
    })
    assert response.status_code == 201, response.text
    recipe_id = response.json()["id"]
    assert response.json()["origin_person"] == "Oma Susi"
    assert client.get(f"/api/recipes/{recipe_id}").json()["origin_person"] == "Oma Susi"

    response = client.put(f"/api/recipes/{recipe_id}", json={"origin_person": "  "})
    assert response.status_code == 200, response.text
    assert response.json()["origin_person"] is None

    response = client.post("/api/recipes", json={"title": "Brot", "category_id": category_id})
    assert response.status_code == 201, response.text
    assert response.json()["origin_person"] is None

def test_recipe_favorite_and_image_flow(client):
    registration = {"username": "chefmax", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=registration).status_code == 201
    assert client.post("/api/auth/login", json=registration).status_code == 200

    response = client.post("/api/categories", json={"name": "Desserts"})
    assert response.status_code == 201
    category_id = response.json()["id"]
    assert client.get(f"/api/categories/{category_id}").json()["name"] == "Desserts"

    assert client.post("/api/recipes", json={"title": "Brot"}).status_code == 422
    assert client.post("/api/recipes", json={"title": "Brot", "category_id": None}).status_code == 422
    assert client.post("/api/recipes", json={"title": "Brot", "category_id": 999}).status_code == 404

    response = client.post("/api/recipes", json={
        "title": "Kuchen",
        "category_id": category_id,
        "ingredients": [{"position": 0, "name": "Mehl", "amount": "250", "unit": "g"}],
        "steps": [{"position": 0, "instruction": "VerrÃ¼hren"}],
    })
    assert response.status_code == 201, response.text
    recipe_id = response.json()["id"]
    assert client.put(f"/api/recipes/{recipe_id}", json={"category_id": None}).status_code == 422
    assert client.put(f"/api/recipes/{recipe_id}", json={"title": None}).status_code == 422
    assert client.put(f"/api/recipes/{recipe_id}", json={"category_id": 999}).status_code == 404
    recipe = client.get(f"/api/recipes/{recipe_id}").json()
    assert recipe["ingredients"][0]["name"] == "Mehl"
    assert recipe["steps"][0]["instruction"] == "VerrÃ¼hren"

    response = client.put(f"/api/recipes/{recipe_id}", json={
        "title": "Apfelkuchen",
        "ingredients": [{"position": 0, "name": "Ã„pfel", "amount": "2"}],
        "steps": [{"position": 0, "instruction": "Backen"}],
    })
    assert response.status_code == 200, response.text
    recipe = client.get(f"/api/recipes/{recipe_id}").json()
    assert recipe["category_id"] == category_id
    assert recipe["title"] == "Apfelkuchen"
    assert [item["name"] for item in recipe["ingredients"]] == ["Ã„pfel"]
    assert [item["instruction"] for item in recipe["steps"]] == ["Backen"]

    response = client.post("/api/favorites", json={"recipe_id": recipe_id})
    assert response.status_code == 201, response.text
    favorite_id = response.json()["id"]
    assert len(client.get("/api/favorites").json()) == 1
    assert client.delete(f"/api/favorites/{favorite_id}").status_code == 204
    assert client.get("/api/favorites").json() == []

    image = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(image, format="PNG")
    response = client.post(
        f"/api/recipes/{recipe_id}/images",
        files={"image": ("cake.png", image.getvalue(), "image/png")},
        data={"alt_text": "Kuchen"},
    )
    assert response.status_code == 201, response.text
    image_record = response.json()
    assert client.get(f"/api/recipe-images/{image_record['id']}").json() == image_record
    category_image = client.post(
        f"/api/categories/{category_id}/image",
        files={"image": ("cat.png", image.getvalue(), "image/png")},
    )
    assert category_image.status_code == 200, category_image.text
    category_path = category_image.json()["image_path"]
    assert client.get(category_path).status_code == 200
    removed = client.delete(f"/api/categories/{category_id}/image")
    assert removed.json()["image_path"] is None
    assert client.get(category_path).status_code == 404
    image_response = client.get(image_record["file_path"])
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(image_response.content)).size == (2, 2)

    response = client.put(
        f"/api/recipe-images/{image_record['id']}", json={"alt_text": "Kuchen frisch"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["alt_text"] == "Kuchen frisch"

    response = client.post(
        f"/api/recipes/{recipe_id}/images",
        files={"image": ("second.png", image.getvalue(), "image/png")},
    )
    second_id = response.json()["id"]
    response = client.put(f"/api/recipe-images/{second_id}", json={"is_main": True})
    assert response.status_code == 200, response.text
    images = client.get(f"/api/recipes/{recipe_id}").json()["images"]
    assert [item["id"] for item in images] == [image_record["id"], second_id]
    assert [item["is_main"] for item in images] == [False, True]
