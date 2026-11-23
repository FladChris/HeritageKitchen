from collections import defaultdict
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import auth_route, settings_route, user_route
from app.core import rate_limit
from app.core.config import settings
from app.core.db import get_db
from app.core.security import hash_password
from app.models import Base, SmtpSettings, User, UserRole
from app.services import recipe_image_service, smtp_service
from app.services.auth_service import create_user_session

PASSWORD = "supersecret123"
OTHER_PASSWORD = "another-secret123"


@pytest.fixture
def profiles_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'profiles.db').as_posix()}")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def tested_smtp(profiles_db, monkeypatch):
    monkeypatch.setitem(settings.__dict__, "reset_base_url", "https://cookbook.example.com")
    monkeypatch.setattr(smtp_service, "send_message", lambda *args, **kwargs: True)
    with Session(profiles_db) as db:
        db.add(SmtpSettings(
            id=1, host="mail.example", port=25, encryption="none", username="",
            sender="cookbook@example.com", tested_at=datetime.now(UTC),
        ))
        db.commit()


@pytest.fixture
def accounts(profiles_db, tmp_path, monkeypatch):
    app = FastAPI()
    for route in (auth_route, user_route, settings_route):
        app.include_router(route.router)
    monkeypatch.setattr(rate_limit, "_attempts_by_ip", defaultdict(list))
    monkeypatch.setattr(
        rate_limit, "settings", replace(settings, login_rate_limit_max_attempts=30)
    )
    monkeypatch.setattr(
        recipe_image_service,
        "settings",
        replace(settings, recipe_images_dir=str(tmp_path / "images")),
    )
    hashes = {
        password: hash_password(password) for password in (PASSWORD, OTHER_PASSWORD)
    }

    def get_test_db():
        with Session(profiles_db) as db:
            yield db

    def add(username, *, role=UserRole.READER, password=PASSWORD, **fields):
        with Session(profiles_db) as db:
            user = User(
                username=username, password_hash=hashes[password], role=role, **fields
            )
            db.add(user)
            db.flush()
            user_id = user.id
            token = create_user_session(db_session=db, user_id=user_id)
        client = TestClient(app)
        client.cookies.set(settings.session_cookie_name, token)
        return client, user_id

    app.dependency_overrides[get_db] = get_test_db
    return TestClient(app), add


def login(client, identifier, password=PASSWORD):
    return client.post(
        "/auth/login", json={"username": identifier, "password": password}
    )


def test_email_requires_tested_smtp_but_username_login_still_works(accounts):
    visitor, add = accounts
    admin, _ = add("Admin", role=UserRole.ADMIN)
    owner, user_id = add("Lena", email="legacy@example.com")
    assert visitor.get("/auth/email-available").json() == {"available": False}
    for client, path in ((visitor, "/auth/register"), (admin, "/users")):
        response = client.post(path, json={
            "username": "NewAccount", "email": "new@example.com", "password": PASSWORD,
        })
        assert response.status_code == 409
        assert "SMTP" in response.json()["detail"]
    assert owner.patch("/auth/me", json={
        "email": "new@example.com", "current_password": PASSWORD,
    }).status_code == 409
    assert owner.get("/auth/me").json()["email"] == "legacy@example.com"
    assert login(visitor, "LEGACY@example.com").status_code == 401
    assert login(visitor, "LENA").json()["id"] == user_id
    assert owner.patch("/auth/me", json={"email": None}).status_code == 422
    assert owner.patch("/auth/me", json={
        "email": None, "current_password": "wrong",
    }).status_code == 400
    removed = owner.patch("/auth/me", json={"email": None, "current_password": PASSWORD})
    assert removed.status_code == 200
    assert removed.json()["email"] is None


def test_username_can_change_but_cannot_collide_with_another_email(accounts):
    visitor, add = accounts
    owner, user_id = add("Lena")
    add("Tim", email="reserved@example.com")
    for username in ("ab", "x" * 33, None):
        assert owner.patch("/auth/me", json={"username": username}).status_code == 422
    for username in ("TIM", "RESERVED@example.com"):
        assert owner.patch("/auth/me", json={"username": username}).status_code == 409
    response = owner.patch("/auth/me", json={"username": "NeueLena"})
    assert response.status_code == 200
    assert response.json()["username"] == "NeueLena"
    assert "display_name" not in response.json()
    assert login(visitor, "Lena").status_code == 401
    assert login(visitor, "neuelena").json()["id"] == user_id


def test_login_accepts_username_and_long_email_ignoring_case(accounts, tested_smtp):
    visitor, add = accounts
    email = "long.family.cookbook.identifier@very-long.example.com"
    _, user_id = add("HÉlène", email=email, email_verified_at=datetime.now(UTC))
    for identifier in ("hélène", email.upper()):
        response = login(visitor, identifier)
        assert response.status_code == 200
        assert response.json()["id"] == user_id


def test_legacy_username_wins_and_ambiguous_matches_fail(accounts, tested_smtp):
    visitor, add = accounts
    _, winner = add("Tim@example.com")
    verified_at = datetime.now(UTC)
    add("EmailOwner", email="tim@example.com", password=OTHER_PASSWORD, email_verified_at=verified_at)
    add("Doppel", email="SHARED@example.com", email_verified_at=verified_at)
    add("doppel", email="shared@example.com", email_verified_at=verified_at)

    assert login(visitor, "TIM@example.com").json()["id"] == winner
    for identifier, password in (
        ("TIM@example.com", OTHER_PASSWORD),
        ("DOPPEL", PASSWORD),
        ("shared@example.com", PASSWORD),
    ):
        response = login(visitor, identifier, password)
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid username or password."}
        assert "set-cookie" not in response.headers


@pytest.mark.parametrize("path", ["/auth/register", "/users"])
def test_new_accounts_reject_all_collision_types_and_allow_empty_emails(accounts, tested_smtp, path):
    visitor, add = accounts
    admin, _ = add("Tim@example.com", role=UserRole.ADMIN, email="Lena@example.com")
    client = visitor if path == "/auth/register" else admin
    for identifiers in (
        {"username": "TIM@example.com"},
        {"username": "LENA@example.com"},
        {"username": "Free", "email": "LENA@example.com"},
        {"username": "Free", "email": "TIM@example.com"},
    ):
        response = client.post(
            path, json={"password": PASSWORD, **identifiers}
        )
        assert response.status_code == 409

    for username, email in (("Hilde", None), ("Lena", "  ")):
        response = client.post(
            path, json={"username": username, "password": PASSWORD, "email": email}
        )
        assert response.status_code == 201
        assert response.json()["email"] is None


def test_admin_updates_check_only_changed_identifiers(accounts, tested_smtp):
    _, add = accounts
    admin, _ = add("Admin", role=UserRole.ADMIN, email="taken@example.com")
    _, user_id = add("taken@example.com", email="Own@example.com", email_verified_at=datetime.now(UTC))
    path = f"/users/{user_id}"
    assert (
        admin.put(
            path, json={"username": "taken@example.com"}
        ).status_code
        == 200
    )
    assert admin.put(path, json={"username": "ADMIN"}).status_code == 409
    assert admin.put(path, json={"email": "new@example.com"}).status_code == 422
    assert admin.put(
        path, json={"email": "TAKEN@example.com", "current_password": PASSWORD}
    ).status_code == 409
    updated = admin.put(path, json={
        "username": "Free", "email": "own@example.com", "current_password": PASSWORD,
    })
    assert updated.status_code == 200
    assert updated.json()["username"] == "Free"


@pytest.mark.parametrize("role", list(UserRole))
def test_personal_settings_are_available_to_every_role_and_only_update_the_current_account(
    accounts, tested_smtp, role
):
    visitor, add = accounts
    other, other_id = add("Tim@example.com", email="Lena@example.com")
    client, user_id = add("Lena", role=role, email="lena@example.com", email_verified_at=datetime.now(UTC))
    assert visitor.patch("/auth/me", json={"username": "Neu"}).status_code == 401
    assert (
        client.patch("/auth/me", json={"id": other_id, "role": "admin"}).status_code
        == 422
    )
    if role != UserRole.ADMIN:
        assert client.put("/settings", json={"cookbook_name": "Neu"}).status_code == 403
        assert (
            client.put(f"/users/{other_id}", json={"username": "Neu"}).status_code
            == 403
        )

    # Saving the legacy address along with a new name keeps the existing collision intact.
    updated = client.patch(
        "/auth/me", json={"username": "Kochlena", "email": "lena@example.com"}
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == user_id
    assert updated.json()["username"] == "Kochlena"
    assert updated.json()["role"] == role.value
    assert other.get("/auth/me").json()["username"] == "Tim@example.com"
    assert (
        client.patch(
            "/auth/me", json={"email": "TIM@example.com", "current_password": PASSWORD}
        ).status_code == 409
    )
    assert (
        client.patch(
            "/auth/me", json={"email": "Lena@new.example.com", "current_password": PASSWORD}
        ).status_code
        == 200
    )
    assert login(visitor, "LENA@NEW.EXAMPLE.COM").status_code == 401
    assert client.patch(
        "/auth/me", json={"email": "", "current_password": PASSWORD}
    ).json()["email"] is None


def test_profile_image_replacement_removal_and_account_deletion(accounts):
    visitor, add = accounts
    admin, _ = add("Admin", role=UserRole.ADMIN)
    lena, lena_id = add("Lena")
    tim, _ = add("Tim", role=UserRole.EDITOR)
    image = BytesIO()
    Image.new("RGB", (250, 200), "red").save(image, format="PNG")
    upload = {"image": ("photo.png", image.getvalue(), "image/png")}
    endpoint = "/auth/me/image"

    def upload_image(client):
        response = client.post(endpoint, files=upload)
        assert response.status_code == 200
        url = response.json()["profile_image_path"]
        path = Path(recipe_image_service.settings.recipe_images_dir) / url.removeprefix(
            f"{settings.media_url_prefix}/"
        )
        assert path.is_file()
        with Image.open(path) as saved:
            assert saved.size == (200, 200)
        assert client.get("/auth/me").json()["profile_image_path"] == url
        return path

    assert visitor.post(endpoint, files=upload).status_code == 401
    assert visitor.delete(endpoint).status_code == 401
    too_small = BytesIO()
    Image.new("RGB", (199, 200)).save(too_small, format="PNG")
    assert lena.post(
        endpoint, files={"image": ("small.png", too_small.getvalue(), "image/png")}
    ).status_code == 422
    assert lena.get("/auth/me").json()["profile_image_path"] is None
    first = upload_image(lena)
    timg = upload_image(tim)
    response = lena.post(
        endpoint, files={"image": ("invalid.png", b"not an image", "image/png")}
    )
    assert response.status_code == 415
    assert first.is_file()
    second = upload_image(lena)
    assert second != first and not first.exists()
    assert lena.delete(endpoint).json()["profile_image_path"] is None
    assert not second.exists() and timg.is_file()
    final = upload_image(lena)
    assert admin.delete(f"/users/{lena_id}").status_code == 204
    assert not final.exists() and timg.is_file()


def test_password_change_requires_current_password(accounts):
    visitor, add = accounts
    client, user_id = add("Lena")
    path = "/auth/password"
    assert client.post(path, json={"new_password": OTHER_PASSWORD}).status_code == 422
    assert (
        client.post(
            path, json={"current_password": "wrong", "new_password": OTHER_PASSWORD}
        ).status_code
        == 400
    )
    assert (
        client.post(
            path, json={"current_password": PASSWORD, "new_password": OTHER_PASSWORD}
        ).status_code
        == 204
    )
    assert login(visitor, "Lena", OTHER_PASSWORD).json()["id"] == user_id
