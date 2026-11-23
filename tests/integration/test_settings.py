from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.app import app
from app.api.routes.settings_route import DEFAULTS
from app.core import db
from app.models.app_setting_model import AppSetting


def test_database_info_requires_admin(client):
    assert client.get('/api/settings/database').status_code == 401
    admin = {"username": "databaseadmin", "password": "supersecret123"}
    client.post('/api/auth/register', json=admin)
    client.post('/api/auth/login', json=admin)
    response = client.get('/api/settings/database')
    assert response.status_code == 200
    assert response.json() == {"backend": db.engine.dialect.name}
    for role in ['reader', 'editor']:
        assert client.post('/api/users', json={"username": role, "password": "supersecret123", "role": role}).status_code == 201
    client.post('/api/auth/logout')
    for role in ['reader', 'editor']:
        client.post('/api/auth/login', json={"username": role, "password": "supersecret123"})
        assert client.get('/api/settings/database').status_code == 403
        assert client.get('/api/settings').json() == DEFAULTS
        client.post('/api/auth/logout')


def test_settings_save_and_reset(client):
    assert client.get("/api/settings").json() == DEFAULTS
    credentials = {"username": "chefmax", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200

    response = client.put("/api/settings", json={"home_tagline": "  Unsere Rezepte  "})
    assert response.status_code == 200
    assert response.json() == {**DEFAULTS, "home_tagline": "Unsere Rezepte"}
    assert TestClient(app).get("/api/settings").json() == response.json()

    response = client.put("/api/settings", json={"home_tagline": "   "})
    assert response.status_code == 200
    assert client.get("/api/settings").json() == DEFAULTS


def test_settings_reject_long_text(client):
    credentials = {"username": "chefmax", "password": "supersecret123"}
    client.post("/api/auth/register", json=credentials)
    client.post("/api/auth/login", json=credentials)
    assert client.put("/api/settings", json={"home_tagline": "x" * 200}).status_code == 200
    assert client.put("/api/settings", json={"home_tagline": "x" * 201}).status_code == 422
    assert client.get("/api/settings").json() == {**DEFAULTS, "home_tagline": "x" * 200}


def test_settings_requires_admin(client):
    assert client.put("/api/settings", json={"home_tagline": "Test"}).status_code == 401
    admin = {"username": "chefmax", "password": "supersecret123"}
    reader = {"username": "reader", "password": "supersecret123"}
    client.post("/api/auth/register", json=admin)
    client.post("/api/auth/login", json=admin)
    assert client.post("/api/users", json={**reader, "role": "reader"}).status_code == 201
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json=reader)
    assert client.put("/api/settings", json={"home_tagline": "Test"}).status_code == 403
    assert client.get("/api/settings").json() == DEFAULTS


def test_removed_read_login_setting_is_rejected(client):
    old_key = "require_login_for_reading"
    credentials = {"username": "chefmax", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200

    response = client.put("/api/settings", json={old_key: True, "home_title": "Changed"})
    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["loc"] == ["body", old_key]
    assert error["type"] == "extra_forbidden"
    assert old_key not in client.get("/api/settings").json()
    assert client.get("/api/settings").json() == DEFAULTS
    with Session(db.engine) as session:
        assert session.get(AppSetting, old_key) is None


def test_cookbook_names_public_partial_updates_and_validation(client):
    credentials = {"username": "chefmax", "password": "supersecret123"}
    client.post("/api/auth/register", json=credentials)
    client.post("/api/auth/login", json=credentials)
    assert client.get("/api/settings").json() == DEFAULTS
    response = client.put("/api/settings", json={"cookbook_name": "  Unsere Familienküche  ", "home_title": "  Familienrezepte  "})
    assert response.status_code == 200
    expected = {**DEFAULTS, "cookbook_name": "Unsere Familienküche", "home_title": "Familienrezepte"}
    assert response.json() == expected
    assert TestClient(app).get("/api/settings").json() == expected
    assert client.put("/api/settings", json={"home_tagline": ""}).json() == expected
    for field in ["cookbook_name", "home_title"]:
        for value in ["", "   ", None, "x" * 101]:
            assert client.put("/api/settings", json={field: value}).status_code == 422
        assert client.put("/api/settings", json={field: "x" * 100}).status_code == 200
    for role in ["reader", "editor"]:
        assert client.post("/api/users", json={"username": role, "password": "supersecret123", "role": role}).status_code == 201
    client.post("/api/auth/logout")
    for role in ["reader", "editor"]:
        client.post("/api/auth/login", json={"username": role, "password": "supersecret123"})
        assert client.put("/api/settings", json={"cookbook_name": "Test", "home_title": "Test"}).status_code == 403
        client.post("/api/auth/logout")
    assert client.put("/api/settings", json={"cookbook_name": "Test"}).status_code == 401


def test_footer_text_is_public_persistent_and_admin_only(client):
    assert client.get("/api/settings").json()["footer_text"] == ""

    admin = {"username": "footeradmin", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=admin).status_code == 201
    assert client.post("/api/auth/login", json=admin).status_code == 200

    response = client.put(
        "/api/settings",
        json={
            "cookbook_name": "Familienrezepte",
            "home_title": "Was kochen wir heute?",
            "footer_text": "  Mit Liebe gesammelt seit 2026  ",
        },
    )
    assert response.status_code == 200
    expected = {
        **DEFAULTS,
        "cookbook_name": "Familienrezepte",
        "home_title": "Was kochen wir heute?",
        "footer_text": "Mit Liebe gesammelt seit 2026",
    }
    assert response.json() == expected
    assert TestClient(app).get("/api/settings").json() == expected

    assert client.put("/api/settings", json={"cookbook_name": "Neuer Name"}).status_code == 200
    assert client.get("/api/settings").json()["footer_text"] == expected["footer_text"]
    for invalid in [None, "x" * 201]:
        assert client.put("/api/settings", json={"footer_text": invalid}).status_code == 422
    assert client.get("/api/settings").json()["footer_text"] == expected["footer_text"]

    for role in ["reader", "editor"]:
        assert client.post(
            "/api/users",
            json={"username": f"footer{role}", "password": "supersecret123", "role": role},
        ).status_code == 201
    client.post("/api/auth/logout")
    for role in ["reader", "editor"]:
        credentials = {"username": f"footer{role}", "password": "supersecret123"}
        assert client.post("/api/auth/login", json=credentials).status_code == 200
        assert client.put("/api/settings", json={"footer_text": "Unerlaubt"}).status_code == 403
        assert client.get("/api/settings").json()["footer_text"] == expected["footer_text"]
        client.post("/api/auth/logout")

    assert client.put("/api/settings", json={"footer_text": "Unerlaubt"}).status_code == 401
    assert client.post("/api/auth/login", json=admin).status_code == 200
    response = client.put("/api/settings", json={"footer_text": "   "})
    assert response.status_code == 200
    assert response.json()["footer_text"] == ""
    assert response.json()["cookbook_name"] == "Neuer Name"
    assert TestClient(app).get("/api/settings").json()["footer_text"] == ""
