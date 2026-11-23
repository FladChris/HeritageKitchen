from importlib import import_module

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.staticfiles import StaticFiles

from app.api.app import SPAMount, SPAStaticFiles


@pytest.fixture
def client(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    (build / "index.html").write_text("<html>Heritage Kitchen</html>")
    (build / "service-worker.js").write_text("// worker")
    (build / "_app").mkdir()
    (build / "_app" / "bundle.js").write_text("// bundle")
    outside = tmp_path / "secret.txt"
    outside.write_text("private")
    (build / "leak.txt").symlink_to(outside)
    images = tmp_path / "images"
    images.mkdir()
    (images / "recipe.jpg").write_bytes(b"image")
    app = FastAPI()

    @app.get("/api/error")
    def api_error():
        from fastapi import HTTPException

        raise HTTPException(403, "denied")

    app.mount("/media/recipe-images", StaticFiles(directory=images))
    app.router.routes.append(
        SPAMount("/", app=SPAStaticFiles(directory=build, html=True))
    )
    return TestClient(app)


@pytest.mark.parametrize(
    "path",
    ["/", "/recipes", "/recipes/123", "/login", "/recipes/123/edit",
     "/verify-email?token=sample", "/account/password"],
)
def test_spa_navigation(client, path):
    response = client.get(path, headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "Heritage Kitchen" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_assets_media_and_head(client):
    assert client.get("/_app/bundle.js").text == "// bundle"
    assert client.get("/media/recipe-images/recipe.jpg").content == b"image"
    response = client.head("/recipes/123")
    assert response.status_code == 200
    assert response.content == b""
    assert client.get("/service-worker.js").headers["cache-control"] == "no-cache"


@pytest.mark.parametrize(
    "path",
    [
        "/api",
        "/api/missing",
        "/media",
        "/media/missing",
        "/media/recipe-images/missing.jpg",
        "/health/missing",
        "/docs/missing",
        "/openapi.json/missing",
        "/missing.js",
        "/_app/missing",
        "/leak.txt",
        "/%2e%2e/secret.txt",
        "/%252e%252e/secret",
        "/x%5c..%5csecret",
        "/x/%00",
    ],
)
def test_no_spa_fallback_for_api_assets_or_traversal(client, path):
    response = client.get(path, headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert "Heritage Kitchen" not in response.text
    assert "private" not in response.text


def test_api_error_and_non_navigation_keep_status(client):
    assert client.get("/api/error").status_code == 403
    assert client.post("/api/error").status_code == 405
    assert (
        client.get("/recipes", headers={"Accept": "application/json"}).status_code
        == 404
    )
    assert client.post("/recipes").status_code == 405


def test_backend_without_build_returns_404(tmp_path):
    app = FastAPI()
    app.mount("/", SPAStaticFiles(directory=tmp_path / "missing", check_dir=False))
    assert TestClient(app).get("/").status_code == 404


def test_real_app_preserves_api_and_docs_routes():
    module = import_module("app.api.app")
    client = TestClient(module.app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/health").status_code == 405
    assert client.get("/api/not-a-route").status_code == 404
    assert client.get("/media/not-a-route").status_code == 404
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
