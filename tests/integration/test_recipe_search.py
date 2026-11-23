PASSWORD = "supersecret123"


def setup(client):
    admin = {"username": "searchadmin", "password": PASSWORD}
    assert client.post("/api/auth/register", json=admin).status_code == 201
    assert client.post("/api/auth/login", json=admin).status_code == 200
    return {
        name: client.post("/api/categories", json={"name": name}).json()["id"]
        for name in ["Kuchen", "Grillen", "Backen"]
    }


def add_recipe(client, title, category_id, **extra):
    response = client.post("/api/recipes", json={"title": title, "category_id": category_id, **extra})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def search(client, term, **params):
    response = client.get("/api/recipes", params={"search": term, "page_size": 100, **params})
    assert response.status_code == 200, response.text
    return response.json()


def titles(client, term, **params):
    return [recipe["title"] for recipe in search(client, term, **params)["items"]]


def test_search_ignores_case_umlauts_and_accents(client):
    cake = setup(client)["Kuchen"]
    add_recipe(client, "Käsespätzle", cake)
    add_recipe(client, "Crème brûlée", cake)
    add_recipe(client, "Fußball-Torte", cake)
    assert titles(client, "kasespatzle") == ["Käsespätzle"]
    assert titles(client, "KÄSESPÄTZLE") == ["Käsespätzle"]
    assert titles(client, "creme brulee") == ["Crème brûlée"]
    assert titles(client, "fussball") == ["Fußball-Torte"]
    assert titles(client, "Fußball") == ["Fußball-Torte"]


def test_search_covers_all_recipe_texts_and_comments(client):
    cake = setup(client)["Kuchen"]
    fields = {
        "Kurz": {"summary": "Safran"},
        "Herkunft": {"origin_person": "Tante Safran"},
        "Geschichte": {"history": "Safran aus Spanien"},
        "Notiz": {"notes": "Safran"},
        "Wichtig": {"important_notes": "Safran"},
        "Zutat": {"ingredients": [{"position": 1, "name": "Safran"}]},
        "Schritt": {"steps": [{"position": 1, "instruction": "Safran zugeben"}]},
    }
    for title, extra in fields.items():
        add_recipe(client, title, cake, **extra)
    commented = add_recipe(client, "Kommentiert", cake)
    add_recipe(client, "Ohne", cake)
    comment = client.post(f"/api/recipes/{commented}/comments", json={"text": "Mit Safran besser"})
    assert comment.status_code == 201, comment.text
    assert sorted(titles(client, "safran")) == sorted([*fields, "Kommentiert"])
    deleted = client.delete(f"/api/recipes/{commented}/comments/{comment.json()['id']}")
    assert deleted.status_code == 204, deleted.text
    assert "Kommentiert" not in titles(client, "safran")


def test_search_orders_title_before_ingredients_before_other_texts(client):
    cake = setup(client)["Kuchen"]
    add_recipe(client, "A Notiz", cake, notes="Apfel")
    add_recipe(client, "B Zutat", cake, ingredients=[{"position": 1, "name": "Apfel"}])
    add_recipe(client, "C Apfelkuchen", cake)
    add_recipe(client, "D Apfeltorte", cake, notes="Apfel", ingredients=[{"position": 1, "name": "Apfel"}])
    assert titles(client, "apfel") == ["C Apfelkuchen", "D Apfeltorte", "B Zutat", "A Notiz"]


def test_search_stays_in_category_and_offers_other_categories_as_counts(client):
    categories = setup(client)
    add_recipe(client, "Brotsuppe", categories["Backen"])
    add_recipe(client, "Brotzeit", categories["Backen"], ingredients=[{"position": 1, "name": "Brot"}])
    add_recipe(client, "Roggenbrot", categories["Kuchen"])
    add_recipe(client, "Steak", categories["Grillen"])
    result = search(client, "brot", category_id=categories["Grillen"])
    assert result["items"] == [] and result["total"] == 0
    assert result["other_categories"] == [
        {"id": categories["Backen"], "name": "Backen", "count": 2},
        {"id": categories["Kuchen"], "name": "Kuchen", "count": 1},
    ]
    hit = search(client, "brot", category_id=categories["Backen"])
    assert hit["total"] == 2 and hit["other_categories"] == []
    assert search(client, "brot")["other_categories"] == []
    nothing = search(client, "zzz", category_id=categories["Grillen"])
    assert nothing["total"] == 0 and nothing["other_categories"] == []


def test_search_folds_uppercase_and_extended_letters_on_both_sides(client):
    cake = setup(client)["Kuchen"]
    add_recipe(client, "Ölsardinen", cake)
    add_recipe(client, "Čevapčići", cake)
    add_recipe(client, "ÄPFEL", cake)
    assert titles(client, "ol") == ["Ölsardinen"]
    assert titles(client, "Ölsar") == ["Ölsardinen"]
    assert titles(client, "cevapcici") == ["Čevapčići"]
    assert titles(client, "Čevapčići") == ["Čevapčići"]
    assert titles(client, "apfel") == ["ÄPFEL"]


def test_search_folds_umlaut_spellings_in_both_directions(client):
    cake = setup(client)["Kuchen"]
    add_recipe(client, "Käsespätzle", cake)
    add_recipe(client, "Oel und Gruenkohl", cake)
    assert titles(client, "KAESespaetzle") == ["Käsespätzle"]
    assert titles(client, "Öl und Grünkohl") == ["Oel und Gruenkohl"]


def test_search_matches_group_and_day_titles_with_correct_relevance(client):
    cake = setup(client)["Kuchen"]
    add_recipe(client, "A Tagesplan", cake, day_titles=["Füllung vorbereiten"])
    add_recipe(client, "B Gruppe", cake, ingredient_groups=[{"position": 0, "name": "Füllung"}])
    add_recipe(client, "C Füllung", cake)
    add_recipe(client, "Ohne", cake, day_titles=None)
    add_recipe(client, "Leer", cake, day_titles=[])
    assert titles(client, "fuellung") == ["C Füllung", "B Gruppe", "A Tagesplan"]
    # JSON encoding and SQL wildcards must not create false matches.
    assert titles(client, '["') == []
    assert titles(client, "%") == []
