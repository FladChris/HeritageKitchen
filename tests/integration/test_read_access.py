from io import BytesIO

from PIL import Image
from sqlalchemy.orm import Session

from app.core import db
from app.models.app_setting_model import AppSetting


def test_guest_can_read_even_with_legacy_login_requirement(client):
    admin = {"username": "chef", "password": "supersecret123"}
    assert client.post("/api/auth/register", json=admin).status_code == 201
    assert client.post("/api/auth/login", json=admin).status_code == 200

    category = client.post("/api/categories", json={"name": "Backen"})
    assert category.status_code == 201
    category_url = f"/api/categories/{category.json()['id']}"
    note = "Den Kuchen vor dem Anschneiden abkühlen lassen."
    recipe = client.post(
        "/api/recipes",
        json={"title": "Kuchen", "category_id": category.json()["id"], "notes": note},
    )
    assert recipe.status_code == 201
    recipe_url = f"/api/recipes/{recipe.json()['id']}"
    image = BytesIO()
    Image.new("RGB", (2, 2), "red").save(image, format="PNG")
    files = {"image": ("cake.png", image.getvalue(), "image/png")}
    uploaded = client.post(f"{recipe_url}/images", files=files)
    assert uploaded.status_code == 201
    photo = uploaded.json()
    category_image = client.post(f"{category_url}/image", files=files)
    assert category_image.status_code == 200

    with Session(db.engine) as session:
        session.add(AppSetting(key="require_login_for_reading", value="true"))
        session.commit()

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401

    paths = [
        "/api/recipes",
        recipe_url,
        "/api/categories",
        category_url,
        "/api/recipe-images",
        f"/api/recipe-images/{photo['id']}",
        photo["file_path"],
        category_image.json()["image_path"],
        f"{recipe_url}/pdf",
        "/api/settings",
    ]

    responses = {}
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["Cache-Control"] == "no-store", path
        responses[path] = response

    assert responses[recipe_url].json()["notes"] == note
    pdf = responses[f"{recipe_url}/pdf"]
    assert pdf.headers["Content-Type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")
    for path in [photo["file_path"], category_image.json()["image_path"]]:
        assert responses[path].headers["Content-Type"] == "image/jpeg"
        response = client.head(path)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
