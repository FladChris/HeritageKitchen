import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import db
from app.models.category_model import Category
from app.models.recipe_model import Recipe


@pytest.fixture(params=[False, True], ids=["default-collation", "nondeterministic-icu"])
def recipe_search_client(client, request):
    if request.param:
        if db.engine.dialect.name != "postgresql":
            pytest.skip("PostgreSQL ICU collation")
        with db.engine.begin() as connection:
            if not connection.scalar(text("SELECT 1 FROM pg_collation WHERE collprovider = 'i' LIMIT 1")):
                pytest.skip("PostgreSQL does not have ICU collations")
            connection.execute(text(
                "CREATE COLLATION test_recipe_search_ci "
                "(provider = icu, locale = 'und-u-ks-level2', deterministic = false)"
            ))
            connection.execute(text(
                "ALTER TABLE recipes ALTER COLUMN title TYPE varchar "
                "COLLATE test_recipe_search_ci"
            ))
    try:
        yield client
    finally:
        if request.param:
            with db.engine.begin() as connection:
                connection.execute(text('ALTER TABLE recipes ALTER COLUMN title TYPE varchar COLLATE "default"'))
                connection.execute(text("DROP COLLATION test_recipe_search_ci"))


def test_recipe_search_matches_title_parts_and_returns_empty_results(recipe_search_client):
    with Session(db.engine) as session:
        category = Category(name="Backen")
        session.add_all([
            Recipe(title="Grillbrote", category=category),
            Recipe(title="Apfelkuchen", category=category),
        ])
        session.commit()

    for term, expected_titles in (
        ("Grill", ["Grillbrote"]),
        ("brote", ["Grillbrote"]),
        ("illb", ["Grillbrote"]),
        ("grill", ["Grillbrote"]),
        ("Pasta", []),
        ("%", []),
    ):
        response = recipe_search_client.get("/api/recipes", params={"search": term, "summary": True})
        assert response.status_code == 200
        payload = response.json()
        assert [item["title"] for item in payload["items"]] == expected_titles
        assert payload["total"] == len(expected_titles)


def test_category_counts_and_recipe_pages_beyond_first_hundred(client):
    with Session(db.engine) as session:
        baking = Category(name="Backen")
        soups = Category(name="Suppen")
        session.add_all([baking, soups])
        session.flush()
        session.add_all(
            Recipe(title=f"Kuchen {index:03d}", category_id=baking.id)
            for index in range(175)
        )
        session.add_all(
            Recipe(title=f"Suppe {index:03d}", category_id=soups.id)
            for index in range(75)
        )
        baking_id = baking.id
        session.commit()

    categories = client.get("/api/categories").json()
    assert {item["name"]: item["recipe_count"] for item in categories} == {
        "Backen": 175,
        "Suppen": 75,
    }

    assert client.get(f"/api/categories/{baking_id}").json()["recipe_count"] == 175

    titles = []
    for page in range(1, 10):
        response = client.get(
            "/api/recipes",
            params={"category_id": baking_id, "page": page, "page_size": 20, "summary": True},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 175
        titles.extend(recipe["title"] for recipe in payload["items"])
    assert titles == [f"Kuchen {index:03d}" for index in range(175)]

    search = client.get(
        "/api/recipes", params={"search": "Kuchen", "page": 2, "page_size": 100}
    )
    assert search.status_code == 200
    assert search.json()["total"] == 175
    assert len(search.json()["items"]) == 75
