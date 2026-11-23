from datetime import datetime, timedelta
from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core import db
from app.models import Category, Recipe


@pytest.fixture
def cookbook(client):
    credentials = {"username": "chefmax", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    category = client.post("/api/categories", json={"name": "Backen"}).json()["id"]

    def create(title="Kuchen", **fields):
        response = client.post("/api/recipes", json={"title": title, "category_id": category, **fields})
        assert response.status_code == 201, response.text
        return response.json()

    return create


def test_history_days_roundtrip_defaults_limits_and_partial_update(client, cookbook):
    recipe = cookbook()
    url = f'/api/recipes/{recipe["id"]}'
    assert recipe["history"] is None
    assert recipe["preparation_days"] == 1
    history = "Von Oma.\nJeden Sonntag gab es Kuchen."
    for days in [1, 2, 14]:
        response = client.put(url, json={"history": history, "preparation_days": days})
        assert response.status_code == 200
        assert client.get(url).json()["history"] == history
        assert client.get(url).json()["preparation_days"] == days
    assert client.put(url, json={"summary": "Neue Beschreibung"}).json()["preparation_days"] == 14
    for days in [0, 15, None, 1.5, True, "2"]:
        assert client.put(url, json={"preparation_days": days}).status_code == 422
        assert client.post("/api/recipes", json={"title": "Test", "category_id": recipe["category_id"], "preparation_days": days}).status_code == 422
    assert client.put(url, json={"history": "x" * 5000}).status_code == 200
    assert client.put(url, json={"history": "x" * 5001}).status_code == 422
    for blank in ["  \n  ", "", None]:
        assert client.put(url, json={"history": blank}).json()["history"] is None
    assert cookbook(history=history, preparation_days=14)["history"] == history


def test_summary_does_not_fetch_recipe_contents_and_newest_order_is_stable(client):
    now = datetime(2026, 1, 1)
    with Session(db.engine) as session:
        category = Category(name="Backen")
        session.add(category)
        session.flush()
        # Created date takes precedence over id; tied dates use descending ids.
        for title, created in [("C", now), ("B", now + timedelta(days=1)), ("A", now + timedelta(days=1)), ("D", now - timedelta(days=1))]:
            session.add(Recipe(title=title, created_at=created, category_id=category.id, history="x" * 5000))
        session.commit()
    statements = []

    def record(connection, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        response = client.get("/api/recipes", params={"summary": True, "sort": "newest", "page_size": 3})
    finally:
        event.remove(db.engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    assert [r["title"] for r in response.json()["items"]] == ["A", "B", "C"]
    assert response.json()["total"] == 4
    for recipe in response.json()["items"]:
        assert not {"history", "ingredients", "ingredient_groups", "steps", "notes", "important_notes"} & recipe.keys()
        assert recipe["preparation_days"] == 1
    assert len(statements) == 4  # Count, recipes, categories, images. No N+1.
    assert not any("recipe_ingredients" in s or "recipes.history" in s for s in statements)
    assert [r["title"] for r in client.get("/api/recipes").json()["items"]] == ["A", "B", "C", "D"]
    assert client.get("/api/recipes", params={"sort": "invalid"}).status_code == 422


def test_invalid_ingredient_group_rolls_back_recipe_update(client, cookbook):
    original = cookbook("Original", ingredients=[{"position": 0, "name": "Mehl"}])
    url = f'/api/recipes/{original["id"]}'
    response = client.put(url, json={
        "title": "Darf nicht bleiben",
        "ingredients": [{"position": 0, "name": "Wasser", "group_position": 99}],
    })
    assert response.status_code == 422
    unchanged = client.get(url).json()
    assert unchanged["title"] == original["title"]
    assert unchanged["ingredients"] == original["ingredients"]


def test_pdf_public_unicode_all_sections_and_one_page(client, cookbook, tmp_path):
    recipe = cookbook(
        'Omas süße Öl-Küchlein', origin_person="Großmutter", history="Jeden Sonntag.\nSeit ½ Jahrhundert.",
        summary="Für Gäste & Familie <3", preparation_days=2, preparation_time=20,
        cooking_time=40, cooking_time_max=45, rest_time=1440, rest_time_max=2880,
        servings=12, important_notes="Auf 180 °C vorheizen.", notes="Kühl aufbewahren.",
        ingredient_groups=[{"position": 0, "name": "Für den Teig"}, {"position": 1, "name": "Für den Guss"}],
        ingredients=[{"position": i, "name": f"Zutat {i+1}", "amount": "0.5" if i == 0 else 100, "unit": "g", "group_position": 0 if i < 8 else 1} for i in range(12)],
        steps=[{"position": i, "instruction": "Die Zutaten gründlich verrühren und den Teig ruhen lassen.", "heading": "Tag 1 – am Vorabend" if i == 0 else "Tag 2" if i == 4 else None, "note": "Nicht zu heiß." if i == 7 else None} for i in range(8)],
    )
    client.post("/api/auth/logout")
    response = client.get(f'/api/recipes/{recipe["id"]}/pdf')
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''Omas%20s%C3%BC%C3%9Fe" in response.headers["content-disposition"]
    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    for expected in [recipe["title"], "Großmutter", "Seit ½ Jahrhundert.", "180 °C", "Für Gäste & Familie <3", "Über 2 Tage", "Arbeit: 20 Min.", "Ruhezeit: 1–2 Tage", "40–45 Min.", "Für 12 Portionen", "Wichtiger Hinweis", "Für den Teig", "Für den Guss", "0,5 g Zutat 1", "Tag 1 – am Vorabend", "Tag 2", "Nicht zu heiß.", "Kühl aufbewahren.", "Seite 1"]:
        assert expected in text
    assert float(reader.pages[0].mediabox.width) == pytest.approx(595.2756, abs=0.01)
    (tmp_path / "recipe.pdf").write_bytes(response.content)


@pytest.mark.parametrize("export", ["recipe", "cookbook"])
def test_pdf_exports_preserve_literal_text_days_and_step_times(client, cookbook, export):
    recipe = cookbook(
        "Öl & <Zucker>",
        summary="<b>Familienrezept</b> & Öl\nZweite Zeile",
        preparation_days=2,
        day_titles=["Anrühren", "Ruhen"],
        steps=[
            {"position": 0, "day": 1, "instruction": "Mit <Löffel> & Geduld rühren.",
             "duration_minutes": 25, "time_kind": "preparation"},
            {"position": 1, "day": 2, "instruction": "Abgedeckt ruhen lassen.",
             "duration_minutes": 1440, "time_kind": "rest"},
        ],
    )
    path = f'/api/recipes/{recipe["id"]}/pdf' if export == "recipe" else "/api/settings/export/pdf"
    response = client.get(path)
    assert response.status_code == 200
    document = PdfReader(BytesIO(response.content))
    text = "\n".join(page.extract_text() for page in document.pages)
    for expected in [
        "Öl & <Zucker>", "<b>Familienrezept</b> & Öl", "Zweite Zeile",
        "Tag 1 – Anrühren", "Tag 2 – Ruhen", "Mit <Löffel> & Geduld rühren.",
        "Arbeit: 25 Min.", "Ruhezeit: 1 Tag",
    ]:
        assert expected in text


def test_pdf_missing_minimal_and_long_recipe(client, cookbook, tmp_path):
    assert client.get('/api/recipes/999999/pdf').status_code == 404
    minimal = cookbook("Minimal")
    response = client.get(f'/api/recipes/{minimal["id"]}/pdf')
    assert response.status_code == 200
    assert "Minimal" in PdfReader(BytesIO(response.content)).pages[0].extract_text()
    long_recipe = cookbook("Langes Rezept", history="Geschichte " * 400, steps=[{"position": i, "instruction": "Lange Anweisung. " * 90, "heading": f"Abschnitt {i+1}"} for i in range(12)], notes="Letzter Hinweis")
    response = client.get(f'/api/recipes/{long_recipe["id"]}/pdf')
    assert response.status_code == 200
    (tmp_path / "recipe-long.pdf").write_bytes(response.content)
    pages = PdfReader(BytesIO(response.content)).pages
    assert len(pages) > 2
    assert "Letzter Hinweis" in pages[-1].extract_text()
    for number, page in enumerate(pages, 1):
        assert f"Seite {number}" in page.extract_text()


def test_multiline_title_pdf_finishes_with_searchable_text(cookbook):
    import subprocess
    import sys

    recipe = cookbook(("a\n" * 74).strip())
    # Keep a regression in ReportLab from hanging the entire test worker.
    import json
    result = subprocess.run(
        [sys.executable, "-c", (
            "import sys; from app.api.schemas.recipe_schema import RecipeResponse; "
            "from app.services.recipe_pdf_service import render_recipe_pdf; "
            "sys.stdout.buffer.write(render_recipe_pdf(RecipeResponse.model_validate_json(sys.stdin.read())))"
        )], input=json.dumps(recipe).encode(), capture_output=True, timeout=10, check=True,
    )
    pages = PdfReader(BytesIO(result.stdout)).pages
    assert len(pages) == 1
    assert " ".join(pages[0].extract_text().split()).count("a") >= 74


def test_pdf_uses_current_portions_without_changing_stored_amounts(client, cookbook):
    recipe = cookbook(
        "Portionstest", servings=4, important_notes="Backofen vorheizen",
        ingredient_groups=[{"position": 0, "name": "Teig"}],
        ingredients=[
            {"position": 0, "name": "Mehl", "amount": "500", "unit": "g", "group_position": 0},
            {"position": 1, "name": "Eier", "amount": "3", "group_position": 0},
            {"position": 2, "name": "Salz nach Geschmack", "group_position": 0},
        ],
        steps=[{"position": 0, "instruction": "Verrühren", "duration_minutes": 15, "time_kind": "preparation"}],
    )
    recipe_id = recipe["id"]
    assert client.post(f"/api/recipes/{recipe_id}/comments", json={"text": "Nicht exportieren"}).status_code == 201
    assert client.put(f"/api/recipes/{recipe_id}/ratings", json={"stars": 4.5}).status_code == 200
    assert client.post("/api/auth/logout").status_code == 204

    response = client.get(f"/api/recipes/{recipe_id}/pdf", params={"factor": "1.5"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
    for expected in ["Für 6 Portionen", "750 g Mehl", "4,5 Eier", "Salz nach Geschmack", "Teig",
                     "Arbeit: 15 Min.", "Backofen vorheizen"]:
        assert expected in text
    assert "Nicht exportieren" not in text
    assert "4.5 Sterne" not in text
    stored = client.get(f"/api/recipes/{recipe_id}").json()
    assert stored["servings"] == 4
    assert [item["amount"] for item in stored["ingredients"]] == ["500.000", "3.000", None]

    for invalid in ["0", "-1", "1001", "abc", "NaN"]:
        assert client.get(f"/api/recipes/{recipe_id}/pdf", params={"factor": invalid}).status_code == 422
    unscaled = client.get(f"/api/recipes/{recipe_id}/pdf").content
    assert "500 g Mehl" in PdfReader(BytesIO(unscaled)).pages[0].extract_text()


def test_pdf_preserves_approximate_amounts_and_scales_without_base_servings(client, cookbook):
    ingredients = [
        ("Mehl", "100", "g"),
        ("Hefe", "0.617", "g"),
        ("Salz", "1", "Prise"),
        ("Pfeffer", "2", "Prisen"),
        ("Muskat", "1", "Messerspitze"),
        ("Zimt", "2", "Messerspitzen"),
        ("Zucker", "1", "  NACH GESCHMACK "),
        ("Kräuter", None, "nach Geschmack"),
    ]
    recipe = cookbook("Portionstest", ingredients=[
        {"position": position, "name": name, "amount": amount, "unit": unit}
        for position, (name, amount, unit) in enumerate(ingredients)
    ])
    assert recipe["servings"] is None
    path = f"/api/recipes/{recipe['id']}"

    def pdf_text(factor):
        response = client.get(f"{path}/pdf", params={"factor": factor})
        assert response.status_code == 200
        return [
            " ".join(line.split())
            for page in PdfReader(BytesIO(response.content)).pages
            for line in page.extract_text().splitlines()
        ]

    doubled = pdf_text("2")
    assert "200 g Mehl" in doubled
    assert "1,234 g Hefe" in doubled
    assert "0,823 g Hefe" in pdf_text("1.3333")
    for expected in [
        "1 Prise Salz", "2 Prisen Pfeffer", "1 Messerspitze Muskat",
        "2 Messerspitzen Zimt", "1 NACH GESCHMACK Zucker", "nach Geschmack Kräuter",
    ]:
        assert expected in doubled
    assert client.get(path).json()["ingredients"] == recipe["ingredients"]


def test_pdf_omits_uploaded_images(client, cookbook):
    from PIL import Image

    recipe = cookbook("Bildertest")
    url = f"/api/recipes/{recipe['id']}"
    photo = BytesIO()
    Image.new("RGB", (120, 80), "red").save(photo, format="JPEG")
    image = client.post(f"{url}/images", files={"image": ("bild.jpg", photo.getvalue(), "image/jpeg")})
    assert image.status_code == 201, image.text
    assert image.json()["is_main"] is True

    response = client.get(f"{url}/pdf")
    assert response.status_code == 200
    pages = PdfReader(BytesIO(response.content)).pages
    assert "Bildertest" in pages[0].extract_text()
    assert all(not page.images for page in pages)
