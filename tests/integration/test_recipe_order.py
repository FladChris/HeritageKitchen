from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.app import app
from app.core import db
from app.models.recipe_model import Recipe

PASSWORD = "supersecret123"


def login(device, username):
    response = device.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200


def setup(client):
    admin = {"username": "orderadmin", "password": PASSWORD}
    assert client.post("/api/auth/register", json=admin).status_code == 201
    login(client, "orderadmin")
    for name in ["lena", "tim"]:
        assert client.post("/api/users", json={"username": name, "password": PASSWORD}).status_code == 201
    return {
        name: client.post("/api/categories", json={"name": name}).json()["id"]
        for name in ["Kuchen", "Grillen"]
    }


def add_recipe(client, title, category_id):
    response = client.post("/api/recipes", json={"title": title, "category_id": category_id})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def titles(device, **params):
    params = {"sort": "manual", "page_size": 100, **params}
    response = device.get("/api/recipes", params=params)
    assert response.status_code == 200, response.text
    return [recipe["title"] for recipe in response.json()["items"]]


def save_order(device, category_id, recipe_ids):
    return device.put("/api/recipes/order", json={"category_id": category_id, "recipe_ids": recipe_ids})


def as_user(username):
    device = TestClient(app)
    login(device, username)
    return device


def test_personal_recipe_order_is_per_user_and_category(client):
    categories = setup(client)
    cake, grill = categories["Kuchen"], categories["Grillen"]
    a, b, c = (add_recipe(client, title, cake) for title in "ABC")
    g1, g2 = add_recipe(client, "G1", grill), add_recipe(client, "G2", grill)
    lena, tim = as_user("lena"), as_user("tim")
    assert save_order(lena, cake, [c, a, b]).status_code == 204
    assert save_order(lena, grill, [g2, g1]).status_code == 204
    assert save_order(tim, cake, [b, c, a]).status_code == 204
    assert titles(lena, category_id=cake) == ["C", "A", "B"]
    assert titles(tim, category_id=cake) == ["B", "C", "A"]
    assert save_order(lena, grill, [g1, g2]).status_code == 204
    assert titles(lena, category_id=cake) == ["C", "A", "B"]
    assert titles(tim, category_id=grill) == ["G1", "G2"]
    # The order survives a new login on another device.
    assert titles(as_user("lena"), category_id=cake) == ["C", "A", "B"]


def test_manual_sort_requires_login_and_order_rejects_stale_sets(client):
    categories = setup(client)
    cake = categories["Kuchen"]
    a, b = add_recipe(client, "A", cake), add_recipe(client, "B", cake)
    anonymous = TestClient(app)
    assert anonymous.get("/api/recipes", params={"sort": "manual"}).status_code == 401
    assert save_order(anonymous, cake, [a, b]).status_code == 401
    # Positions only make sense inside one category.
    assert as_user("lena").get("/api/recipes", params={"sort": "manual"}).status_code == 422
    lena = as_user("lena")
    for ids in ([a], [a, b, 999], [a, a, b]):
        assert save_order(lena, cake, ids).status_code in (409, 422)
    assert save_order(lena, 999, []).status_code == 404
    assert titles(lena, category_id=cake) == ["A", "B"]


def test_new_and_moved_recipes_go_last_for_every_user(client):
    categories = setup(client)
    cake, grill = categories["Kuchen"], categories["Grillen"]
    a, b, c = (add_recipe(client, title, cake) for title in "ABC")
    moved = add_recipe(client, "Grillbrot", grill)
    lena, tim = as_user("lena"), as_user("tim")
    assert save_order(lena, cake, [c, b, a]).status_code == 204
    assert save_order(tim, cake, [b, a, c]).status_code == 204
    assert save_order(lena, grill, [moved]).status_code == 204

    assert client.put(f"/api/recipes/{moved}", json={"category_id": cake}).status_code == 200
    add_recipe(client, "Mohnkuchen", cake)
    assert titles(lena, category_id=cake) == ["C", "B", "A", "Grillbrot", "Mohnkuchen"]
    assert titles(tim, category_id=cake) == ["B", "A", "C", "Grillbrot", "Mohnkuchen"]
    assert titles(lena, category_id=grill) == []
    # Saving the full list again leaves nothing orphaned in the old category.
    assert save_order(lena, grill, []).status_code == 204


def test_deleting_a_recipe_keeps_the_remaining_order(client):
    cake = setup(client)["Kuchen"]
    a, b, c = (add_recipe(client, title, cake) for title in "ABC")
    lena = as_user("lena")
    assert save_order(lena, cake, [c, a, b]).status_code == 204
    assert client.delete(f"/api/recipes/{a}").status_code == 204
    assert titles(lena, category_id=cake) == ["C", "B"]
    assert save_order(lena, cake, [b, c]).status_code == 204
    assert titles(lena, category_id=cake) == ["B", "C"]


def test_title_sort_breaks_ties_by_creation_time_then_id(client):
    cake = setup(client)["Kuchen"]
    add_recipe(client, "Zitronenkuchen", cake)
    add_recipe(client, "birnenkuchen", cake)
    ids = [
        add_recipe(client, title, cake)
        for title in ("Apfelkuchen", "äpfelkuchen", "apfelkuchen", "Äpfelkuchen")
    ]
    # Age decides first, and the ID only breaks exact ties.
    times = [datetime(2026, 1, 3), datetime(2026, 1, 1), datetime(2026, 1, 2), datetime(2026, 1, 2)]
    with Session(db.engine) as session:
        for recipe_id, created_at in zip(ids, times, strict=True):
            session.get(Recipe, recipe_id).created_at = created_at
        session.commit()
    listed = client.get("/api/recipes", params={"sort": "title"}).json()["items"]
    assert [recipe["id"] for recipe in listed[:4]] == [ids[1], ids[2], ids[3], ids[0]]
    assert [recipe["title"] for recipe in listed[4:]] == ["birnenkuchen", "Zitronenkuchen"]


def test_search_relevance_precedes_personal_order(client):
    cake = setup(client)["Kuchen"]
    only_text = client.post("/api/recipes", json={
        "title": "Aachener Torte", "summary": "mit Apfel", "category_id": cake,
    }).json()["id"]
    in_title = add_recipe(client, "Apfelkuchen", cake)
    also_title = add_recipe(client, "Apfelstrudel", cake)
    lena = as_user("lena")
    assert save_order(lena, cake, [only_text, also_title, in_title]).status_code == 204
    assert titles(lena, category_id=cake, search="apfel") == [
        "Apfelstrudel", "Apfelkuchen", "Aachener Torte",
    ]
    assert titles(lena, category_id=cake, search="apfel", sort="title") == [
        "Apfelkuchen", "Apfelstrudel", "Aachener Torte",
    ]
    assert titles(lena, category_id=cake) == ["Aachener Torte", "Apfelstrudel", "Apfelkuchen"]
