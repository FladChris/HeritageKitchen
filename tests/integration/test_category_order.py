from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.app import app
from app.core import db
from app.models.category_model import Category
from app.models.recipe_model import Recipe


def sign_in_admin(client):
    credentials = {"username": "categoryadmin", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200


def create_categories():
    with Session(db.engine) as session:
        categories = [Category(name=name) for name in ["Brot", "Kuchen", "Suppen"]]
        session.add_all(categories)
        session.flush()
        session.add(Recipe(title="Bauernbrot", category_id=categories[0].id))
        ids = [category.id for category in categories]
        session.commit()
        return ids


def test_saved_category_order_is_personal_and_keeps_counts(client):
    sign_in_admin(client)
    ids = create_categories()
    requested = [ids[2], ids[0], ids[1]]
    response = client.put("/api/categories/order", json={"category_ids": requested})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert [category["id"] for category in response.json()] == requested
    assert [category["recipe_count"] for category in response.json()] == [0, 1, 0]
    assert client.post("/api/auth/logout").status_code == 204
    assert [category["id"] for category in client.get("/api/categories").json()] == ids
    assert client.get("/api/settings").status_code == 200
    assert client.post("/api/auth/login", json={
        "username": "categoryadmin", "password": "supersecret123",
    }).status_code == 200
    assert category_positions(client) == requested


def category_positions(client):
    user_id = client.get("/api/auth/me").json()["id"]
    return client.get(f"/api/users/{user_id}/view-preferences").json()["category_ids"]


def test_category_order_survives_new_deleted_and_renamed_categories(client):
    sign_in_admin(client)
    ids = create_categories()
    assert client.put("/api/categories/order", json={"category_ids": ids[::-1]}).status_code == 200
    created = client.post("/api/categories", json={"name": "Aufläufe"}).json()
    assert client.put(f"/api/categories/{ids[2]}", json={"name": "Zucchini"}).status_code == 200
    assert client.delete(f"/api/categories/{ids[1]}").status_code == 204
    assert category_positions(client) == [ids[2], ids[0]]
    assert created["id"] in [category["id"] for category in client.get("/api/categories").json()]
    # A stale tab must not silently save an incomplete set of categories.
    assert client.put("/api/categories/order", json={"category_ids": ids}).status_code == 409


def test_category_order_rejects_invalid_sets_without_changing_saved_order(client):
    sign_in_admin(client)
    ids = create_categories()
    for value, expected in [
        ([ids[0], ids[0], ids[2]], 422),
        (ids[:2], 409),
        (ids + [99999], 409),
        ([True, ids[1], ids[2]], 422),
        ([str(ids[0]), ids[1], ids[2]], 422),
        ([0, ids[1], ids[2]], 422),
    ]:
        assert client.put("/api/categories/order", json={"category_ids": value}).status_code == expected
    assert category_positions(client) == []


def test_new_category_cannot_inherit_a_deleted_category_position(client):
    sign_in_admin(client)
    ids = create_categories()
    assert client.put("/api/categories/order", json={"category_ids": ids[::-1]}).status_code == 200
    assert client.delete(f"/api/categories/{ids[2]}").status_code == 204
    created = client.post("/api/categories", json={"name": "Aufläufe"})
    assert created.status_code == 201
    # SQLite may reuse the deleted highest ID; a new category still belongs at the end.
    assert category_positions(client) == [ids[1], ids[0]]
    assert created.json()["id"] not in category_positions(client)


def test_any_signed_in_user_can_change_only_their_category_order(client):
    assert client.put("/api/categories/order", json={"category_ids": []}).status_code == 401
    sign_in_admin(client)
    ids = create_categories()
    for role in ["reader", "editor"]:
        assert client.post("/api/users", json={
            "username": role, "password": "supersecret123", "role": role
        }).status_code == 201
    client.post("/api/auth/logout")
    for role in ["reader", "editor"]:
        client.post("/api/auth/login", json={"username": role, "password": "supersecret123"})
        assert category_positions(client) == []
        assert client.put("/api/categories/order", json={"category_ids": ids[::-1]}).status_code == 200
        assert category_positions(client) == ids[::-1]
        assert [category["id"] for category in client.get("/api/categories").json()] == ids
        client.post("/api/auth/logout")


def test_personal_view_is_private_persistent_and_independent_of_other_accounts(client):
    password = "supersecret123"
    sign_in_admin(client)
    admin_path = f"/api/users/{client.get('/api/auth/me').json()['id']}/view-preferences"
    ids = create_categories()
    for name in ["readerone", "readertwo"]:
        assert client.post("/api/users", json={"username": name, "password": password}).status_code == 201
    assert client.put("/api/categories/order", json={"category_ids": ids}).status_code == 200
    client.post("/api/auth/logout")
    assert client.get(admin_path).status_code == 401
    assert client.patch(admin_path, json={"recipe_view": "grid"}).status_code == 401

    def login(device, username):
        response = device.post("/api/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200
        return f"/api/users/{response.json()['id']}/view-preferences"

    first_path = login(client, "readerone")
    assert client.get(first_path).json() == {
        "category_ids": [], "category_sort": "name", "recipe_view": "list"
    }
    assert client.patch(first_path, json={
        "category_order": {"category_ids": ids[::-1]}, "category_sort": "name"
    }).status_code == 204
    assert client.patch(first_path, json={"recipe_view": "grid"}).status_code == 204
    assert client.patch(first_path, json={"category_sort": "count"}).status_code == 204
    assert client.patch(first_path, json={
        "category_order": {"category_ids": [ids[0], ids[0]]}
    }).status_code == 422
    second_device = TestClient(app)
    assert login(second_device, "readerone") == first_path
    stored = second_device.get(first_path)
    assert stored.headers["cache-control"] == "no-store"
    assert stored.json() == {"category_ids": ids[::-1], "category_sort": "count", "recipe_view": "grid"}

    client.post("/api/auth/logout")
    second_path = login(client, "readertwo")
    assert client.get(first_path).status_code == 403
    assert client.patch(first_path, json={"recipe_view": "list"}).status_code == 403
    assert client.get(second_path).json() == {
        "category_ids": [], "category_sort": "name", "recipe_view": "list"
    }
    client.post("/api/auth/logout")
    assert login(client, "categoryadmin") == admin_path
    assert client.patch(first_path, json={"category_sort": "manual"}).status_code == 403
    assert client.delete(f"/api/categories/{ids[-1]}").status_code == 204
    new_category = client.post("/api/categories", json={"name": "Aufläufe"})
    assert new_category.status_code == 201
    assert category_positions(client) == ids[:-1]
    assert second_device.get(first_path).json() == {
        "category_ids": ids[-2::-1], "category_sort": "count", "recipe_view": "grid"
    }
