import base64
import logging
import smtplib
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from sqlite3 import SQLITE_BUSY
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text, update
from sqlalchemy.orm import Session

from app.api.routes import auth_route, settings_route, user_route
from app.core import rate_limit
from app.core.config import settings
from app.core.db import get_db
from app.core.migrations import run_migrations
from app.core.security import hash_session_token
from app.models import PasswordReset, User, UserRole
from app.services import password_reset_service, smtp_service
from app.services.auth_service import create_user_session

SMTP = "/settings/smtp"
TEST_MAIL = {"recipient": "petra@example.com"}
PASSWORD = "supersecret123"
CONFIG = {
    "host": "mail.example.com",
    "port": 587,
    "encryption": "starttls",
    "username": "mail-user",
    "password": " a test password ",
    "sender": "cookbook@example.com",
}


def save_settings(browser, config=CONFIG):
    version = browser.get(SMTP).json()["version"]
    return browser.put(SMTP, json={**config, "version": version})


def mark_verified(engine):
    with engine.begin() as connection:
        connection.execute(update(User).values(email_verified_at=datetime.now(UTC)))


def mail_token(server, path, email):
    message = server.send_message.call_args.args[0]
    assert message["To"] == email
    link = urlsplit(message.get_content().split()[-1])
    assert (link.scheme, link.netloc, link.path) == ("https", "cookbook.example.com", path)
    return parse_qs(link.query)["token"][0]


@pytest.fixture
def clients(tmp_path, monkeypatch):
    monkeypatch.setattr(rate_limit, "_attempts_by_ip", defaultdict(list))
    monkeypatch.setitem(settings.__dict__, "login_rate_limit_max_attempts", 100)
    monkeypatch.setitem(
        settings.__dict__, "reset_base_url", "https://cookbook.example.com"
    )
    monkeypatch.setitem(
        settings.__dict__,
        "mail_credentials_key",
        base64.urlsafe_b64encode(b"k" * 32).decode(),
    )
    engine = create_engine(f"sqlite:///{(tmp_path / 'smtp.db').as_posix()}")
    run_migrations(engine)
    app = FastAPI()
    for routes in (auth_route, settings_route, user_route):
        app.include_router(routes.router)

    def get_test_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = get_test_db

    def client(role=None, *, username=None):
        browser = TestClient(app)
        if role is not None:
            username = username or role.value
            with Session(engine) as session:
                user = User(
                    username=username,
                    email=f"{username}@example.com",
                    password_hash="unused",
                    role=role,
                    is_active=True,
                )
                session.add(user)
                session.flush()
                browser.cookies.set(
                    settings.session_cookie_name,
                    create_user_session(db_session=session, user_id=user.id),
                )
        return browser

    try:
        yield client, engine
    finally:
        engine.dispose()


@pytest.fixture
def mail_server(monkeypatch):
    server = Mock()
    smtp = Mock(return_value=server)
    smtp_ssl = Mock(return_value=server)
    monkeypatch.setattr(smtplib, "SMTP", smtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", smtp_ssl)
    return server, smtp, smtp_ssl


@pytest.mark.parametrize("admin_creation", [False, True])
def test_new_account_email_requires_single_use_confirmation(
    clients, mail_server, admin_creation
):
    client, engine = clients
    admin, public = client(UserRole.ADMIN), client()
    server, _, _ = mail_server
    assert save_settings(admin).status_code == 200
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    assert public.get("/auth/email-available").json() == {"available": True}

    email = "lena@example.com"
    account = {"username": "lena", "email": email, "password": PASSWORD}
    created = admin.post("/users", json=account) if admin_creation else public.post(
        "/auth/register", json=account
    )
    assert created.status_code == 201
    assert created.json()["email_verified_at"] is None
    user_id = created.json()["id"]
    token = mail_token(server, "/verify-email", email)
    if not admin_creation:
        assert admin.put(f"/users/{user_id}", json={"is_active": True}).status_code == 200
    credentials = {"username": email.upper(), "password": PASSWORD}
    assert public.post("/auth/login", json=credentials).status_code == 401
    assert admin.post(f"/users/{user_id}/password-reset").status_code == 409
    server.reset_mock()
    assert public.post("/auth/reset-request", json={"email": email}).status_code == 204
    server.send_message.assert_not_called()
    with Session(engine) as session:
        user = session.get(User, user_id)
        assert user.email_verification_hash == hash_session_token(token)
        assert user.email_verification_hash != token
        user.email_verification_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    assert public.post("/auth/verify-email", json={"token": token}).status_code == 400
    assert public.post("/auth/login", json={"username": "lena", "password": PASSWORD}).status_code == 200
    resend = {"email": email, "current_password": PASSWORD}
    assert public.patch("/auth/me", json=resend).status_code == 200
    new_token = mail_token(server, "/verify-email", email)
    assert token != new_token
    assert public.post("/auth/verify-email", json={"token": token}).status_code == 400
    assert public.post("/auth/verify-email", json={"token": new_token}).status_code == 204
    assert public.post("/auth/verify-email", json={"token": new_token}).status_code == 400
    assert public.post("/auth/login", json=credentials).status_code == 200
    assert admin.get(f"/users/{user_id}").json()["email_verified_at"]
    assert admin.post(f"/users/{user_id}/password-reset").status_code == 204
    mail_token(server, "/reset-password", email)


@pytest.mark.parametrize("invalidation", ["changed", "removed"])
def test_smtp_invalidation_requires_reverification(clients, mail_server, invalidation):
    client, engine = clients
    admin, owner = client(UserRole.ADMIN), client()
    server, _, _ = mail_server
    assert save_settings(admin).status_code == 200
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    created = admin.post("/users", json={"username": "lena", "password": PASSWORD})
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert owner.post("/auth/login", json={"username": "lena", "password": PASSWORD}).status_code == 200

    email = "lena@example.com"
    assert owner.patch("/auth/me", json={"email": email}).status_code == 422
    assert owner.patch("/auth/me", json={
        "email": email, "current_password": "wrong",
    }).status_code == 400
    assert owner.patch("/auth/me", json={"email": email, "current_password": PASSWORD}).status_code == 200
    first_token = mail_token(server, "/verify-email", email)
    assert owner.post("/auth/verify-email", json={"token": first_token}).status_code == 204
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    assert owner.get("/auth/me").json()["email_verified_at"]
    assert admin.post(f"/users/{user_id}/password-reset").status_code == 204
    reset_token = mail_token(server, "/reset-password", email)

    waiting_email = "waiting@example.com"
    waiting = admin.post("/users", json={
        "username": "waiting", "password": PASSWORD, "email": waiting_email,
    })
    assert waiting.status_code == 201
    pending_token = mail_token(server, "/verify-email", waiting_email)
    change = (
        {"host": "", "sender": ""} if invalidation == "removed"
        else {"sender": "replacement@example.com"}
    )
    assert save_settings(admin, {**CONFIG, **change}).status_code == 200

    assert owner.get("/auth/email-available").json() == {"available": False}
    assert owner.get("/auth/me").json()["email"] == email
    assert owner.get("/auth/me").json()["email_verified_at"] is None
    with Session(engine) as session:
        assert session.scalar(select(PasswordReset)) is None
    if invalidation == "removed":
        assert save_settings(admin).status_code == 200
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    assert owner.post("/auth/verify-email", json={"token": pending_token}).status_code == 400
    credentials = {"username": email, "password": PASSWORD}
    assert owner.post("/auth/login", json=credentials).status_code == 401
    assert admin.post(f"/users/{user_id}/password-reset").status_code == 409

    assert owner.patch("/auth/me", json={"email": email, "current_password": PASSWORD}).status_code == 200
    token = mail_token(server, "/verify-email", email)
    assert owner.post("/auth/verify-email", json={"token": token}).status_code == 204
    assert owner.post("/auth/login", json=credentials).status_code == 200
    assert owner.post("/auth/reset-password", json={
        "token": reset_token, "new_password": "another-password",
    }).status_code == 400
    new_email = "new@example.com"
    assert owner.patch("/auth/me", json={
        "email": new_email, "current_password": PASSWORD,
    }).status_code == 200
    next_token = mail_token(server, "/verify-email", new_email)
    assert owner.post("/auth/login", json=credentials).status_code == 401
    assert owner.post("/auth/login", json={**credentials, "username": new_email}).status_code == 401
    assert owner.post("/auth/verify-email", json={"token": next_token}).status_code == 204
    assert owner.post("/auth/login", json={**credentials, "username": new_email}).status_code == 200


@pytest.mark.parametrize(
    ("role", "status"), [(None, 401), (UserRole.READER, 403), (UserRole.EDITOR, 403)]
)
def test_only_admins_manage_smtp_and_request_a_reset_for_an_account(
    clients, role, status
):
    client, _ = clients
    browser = client(role)
    assert browser.get(SMTP).status_code == status
    assert browser.put(SMTP, json={**CONFIG, "version": 1}).status_code == status
    assert browser.post(f"{SMTP}/test", json=TEST_MAIL).status_code == status
    assert browser.post("/users/1/password-reset").status_code == status


def test_tested_smtp_without_link_base_reports_missing_configuration(clients, mail_server, monkeypatch):
    client, _ = clients
    admin, public = client(UserRole.ADMIN), client()
    monkeypatch.setitem(settings.__dict__, "reset_base_url", "")
    assert save_settings(admin).json()["status"] == "untested"
    assert public.get("/auth/email-available").json() == {"available": False}

    tested = admin.post(f"{SMTP}/test", json=TEST_MAIL)
    assert tested.status_code == 200
    assert tested.json()["status"] == "tested"
    hint = tested.json()["account_mail_hint"]
    assert "RESET_BASE_URL" in hint
    assert admin.get(SMTP).json()["account_mail_hint"] == hint
    for path in ("/auth/email-available", "/auth/reset-available"):
        response = public.get(path)
        assert response.json() == {"available": False, "hint": hint}
        assert response.headers["cache-control"] == "no-store"
    rejected = public.post("/auth/register", json={
        "username": "Lena", "password": PASSWORD, "email": "lena@example.com",
    })
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == hint


@pytest.mark.parametrize(
    "change",
    [
        {"host": "new.example.com"},
        {"port": 465},
        {"encryption": "tls"},
        {"username": "new-user"},
        {"password": "new password"},
        {"sender": "new@example.com"},
    ],
)
def test_only_effective_changes_revoke_test_status(clients, mail_server, change):
    client, engine = clients
    admin, public = client(UserRole.ADMIN), client()
    client(UserRole.READER)
    server, smtp, _ = mail_server
    reset_url = "/auth/reset-request"
    reset_email = {"email": "admin@example.com"}

    assert admin.get(SMTP).json()["status"] == "not_configured"
    assert public.get("/auth/reset-available").json() == {"available": False}
    assert public.post(reset_url, json=reset_email).status_code == 204
    assert (
        admin.put("/users/2", json={"password": "another-password"}).status_code == 200
    )
    saved = save_settings(admin)
    assert saved.status_code == 200
    assert saved.json()["status"] == "untested"
    assert saved.json()["has_password"] is True
    assert "password" not in saved.json()
    assert "password" not in admin.get(SMTP).json()
    with Session(engine) as session:
        encrypted = session.scalar(text("SELECT encrypted_password FROM smtp_settings"))
        assert encrypted and CONFIG["password"] not in encrypted

    assert public.post(reset_url, json=reset_email).status_code == 204
    server.send_message.assert_not_called()
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    smtp.assert_called_once_with(CONFIG["host"], CONFIG["port"], timeout=10)
    server.starttls.assert_called_once()
    server.login.assert_called_once_with(CONFIG["username"], CONFIG["password"])
    message = server.send_message.call_args.args[0]
    assert message["From"] == CONFIG["sender"]
    assert message["To"] == TEST_MAIL["recipient"]
    assert public.get("/auth/reset-available").json() == {"available": True}

    unchanged = save_settings(admin, {**CONFIG, "password": ""})
    assert unchanged.json()["status"] == "tested"
    assert save_settings(admin).json()["status"] == "tested"
    assert save_settings(admin, {**CONFIG, **change}).json()["status"] == "untested"
    assert public.get("/auth/reset-available").json() == {"available": False}
    assert public.post(reset_url, json=reset_email).status_code == 204
    assert admin.post("/users/1/password-reset").status_code == 409
    server.send_message.assert_called_once()


def test_reset_delivery_and_failures_have_neutral_public_response(
    clients, mail_server, caplog
):
    client, engine = clients
    admin, public = client(UserRole.ADMIN), client()
    another_admin = client(UserRole.ADMIN, username="petra")
    server, _, smtp_ssl = mail_server
    assert save_settings(admin, {**CONFIG, "encryption": "tls"}).status_code == 200
    server.send_message.side_effect = smtplib.SMTPDataError(
        554, b"private server reply"
    )
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 502
    assert admin.get(SMTP).json()["status"] == "untested"
    server.send_message.side_effect = None
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    smtp_ssl.assert_called()
    server.starttls.assert_not_called()
    mark_verified(engine)

    assert another_admin.post("/users/1/password-reset").status_code == 204
    message = server.send_message.call_args.args[0]
    assert message["To"] == "admin@example.com"
    assert message["From"] == CONFIG["sender"]
    assert "https://cookbook.example.com/reset-password?token=" in message.get_content()
    assert "einer Stunde" in message.get_content()
    with Session(engine) as session:
        assert session.scalar(select(PasswordReset)) is not None

    server.send_message.side_effect = smtplib.SMTPDataError(
        554, b"private server reply"
    )
    smtp_logger = logging.getLogger("app.services.smtp_service")
    smtp_logger.addHandler(caplog.handler)
    try:
        known = public.post("/auth/reset-request", json={"email": "ADMIN@example.com"})
        unknown = public.post(
            "/auth/reset-request", json={"email": "unknown@example.com"}
        )
    finally:
        smtp_logger.removeHandler(caplog.handler)
    assert (
        (known.status_code, known.content)
        == (unknown.status_code, unknown.content)
        == (204, b"")
    )
    assert "SMTPDataError" in caplog.text
    assert "private server reply" not in caplog.text
    assert admin.post("/users/1/password-reset").status_code == 502
    server.send_message.side_effect = None
    assert (
        public.post(
            "/auth/reset-request", json={"email": "ADMIN@example.com"}
        ).status_code
        == 204
    )
    assert server.send_message.call_args.args[0]["To"] == "admin@example.com"


def test_concurrent_change_does_not_inherit_an_old_test(clients, mail_server):
    client, _ = clients
    first, second = client(UserRole.ADMIN), client()
    second.cookies = first.cookies
    server, _, _ = mail_server
    assert save_settings(first).status_code == 200

    def change_sender(_):
        assert (
            save_settings(second, {**CONFIG, "sender": "new@example.com"}).status_code
            == 200
        )

    server.send_message.side_effect = change_sender
    assert first.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 409
    assert first.get(SMTP).json()["status"] == "untested"


def test_invalid_smtp_requests_do_not_echo_credentials(clients):
    client, _ = clients
    admin = client(UserRole.ADMIN)
    invalid = save_settings(admin, {**CONFIG, "password": {"raw": "a private value"}})
    assert invalid.status_code == 422
    assert "a private value" not in invalid.text

    invalid = admin.post(
        f"{SMTP}/test",
        json={**TEST_MAIL, "settings": {**CONFIG, "version": 1, "port": 0}},
    )
    assert invalid.status_code == 422
    assert CONFIG["password"] not in invalid.text


def test_draft_smtp_test_leaves_storage_unchanged_until_save(clients, mail_server):
    client, engine = clients
    admin = client(UserRole.ADMIN)
    server, smtp, _ = mail_server
    before = admin.get(SMTP).json()
    draft = {**CONFIG, "version": before["version"]}
    request = {**TEST_MAIL, "settings": draft}
    assert client(UserRole.EDITOR).post(f"{SMTP}/test", json=request).status_code == 403

    response = admin.post(f"{SMTP}/test", json=request)
    assert response.status_code == 200
    assert response.json()["status"] == "tested"
    assert "password" not in response.json()
    assert CONFIG["password"] not in response.text
    smtp.assert_called_once_with(CONFIG["host"], CONFIG["port"], timeout=10)
    server.login.assert_called_once_with(CONFIG["username"], CONFIG["password"])
    assert admin.get(SMTP).json() == before
    with Session(engine) as session:
        stored = smtp_service.get_settings(session)
        assert stored.encrypted_password is None
        assert stored.tested_at is None

    saved = admin.put(SMTP, json=draft)
    assert saved.status_code == 200
    assert saved.json()["status"] == "tested"
    assert admin.get(SMTP).json() == saved.json()


@pytest.mark.parametrize(
    "difference", ["password", "settings", "admin", "expiry", "failed_retry", None]
)
def test_draft_smtp_proof_matches_saved_values_and_admin(
    clients, mail_server, monkeypatch, difference
):
    client, _ = clients
    admin = client(UserRole.ADMIN)
    server, _, _ = mail_server
    assert save_settings(admin).status_code == 200
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    before = admin.get(SMTP).json()
    draft = {**CONFIG, "sender": "new@example.com", "password": "", "version": before["version"]}
    request = {**TEST_MAIL, "settings": draft}
    assert admin.post(f"{SMTP}/test", json=request).status_code == 200
    assert admin.get(SMTP).json() == before
    server.login.assert_called_with(CONFIG["username"], CONFIG["password"])

    if difference == "password":
        draft["password"] = "different"
    elif difference == "settings":
        draft["port"] = 465
    elif difference == "admin":
        admin = client(UserRole.ADMIN, username="other-admin")
    elif difference == "expiry":
        monkeypatch.setattr(smtp_service, "monotonic", lambda: float("inf"))
    elif difference == "failed_retry":
        server.login.side_effect = smtplib.SMTPAuthenticationError(535, CONFIG["password"].encode())
        failed = admin.post(f"{SMTP}/test", json=request)
        assert failed.status_code == 502
        assert CONFIG["password"] not in failed.text
        assert admin.get(SMTP).json() == before

    expected = "tested" if difference is None else "untested"
    saved = admin.put(SMTP, json=draft)
    assert saved.status_code == 200
    assert saved.json()["status"] == expected
    assert admin.get(SMTP).json() == saved.json()


def test_password_is_optional_and_can_only_be_saved_with_an_external_key(
    clients, mail_server, monkeypatch
):
    client, _ = clients
    admin = client(UserRole.ADMIN)
    server, _, _ = mail_server
    monkeypatch.setitem(settings.__dict__, "mail_credentials_key", "")

    assert save_settings(admin).status_code == 409
    assert admin.get(SMTP).json()["status"] == "not_configured"
    saved = save_settings(admin, {**CONFIG, "username": "", "password": ""})
    assert saved.status_code == 200
    assert saved.json()["has_password"] is False
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).json()["status"] == "tested"
    server.login.assert_not_called()


def test_stale_smtp_form_cannot_restore_old_server_with_new_credentials(
    clients, mail_server
):
    client, _ = clients
    first = client(UserRole.ADMIN)
    second = client(UserRole.ADMIN, username="petra")
    server, smtp, _ = mail_server
    assert first.put(SMTP, json={**CONFIG, "version": 1}).status_code == 200
    loaded = second.get(SMTP).json()
    updated = first.put(
        SMTP,
        json={
            **CONFIG,
            "version": loaded["version"],
            "host": "new.example.com",
            "password": "new password",
        },
    )
    assert updated.status_code == 200

    stale = second.put(
        SMTP,
        json={
            **CONFIG,
            "version": loaded["version"],
            "sender": "new@example.com",
            "password": "",
        },
    )
    assert stale.status_code == 409
    assert second.get(SMTP).json() == updated.json()
    assert first.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    smtp.assert_called_once_with("new.example.com", CONFIG["port"], timeout=10)
    server.login.assert_called_once_with(CONFIG["username"], "new password")


@pytest.mark.parametrize("by_admin", [False, True])
def test_reset_does_not_send_if_smtp_changes_during_recipient_lookup(
    clients, mail_server, monkeypatch, by_admin
):
    client, engine = clients
    admin, public = client(UserRole.ADMIN), client()
    client(UserRole.READER)
    server, _, _ = mail_server
    assert save_settings(admin).status_code == 200
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    mark_verified(engine)
    server.reset_mock()

    get_recipient = password_reset_service._reset_recipient

    def change_before_send(user):
        assert (
            save_settings(admin, {**CONFIG, "sender": "new@example.com"}).status_code
            == 200
        )
        return get_recipient(user)

    monkeypatch.setattr(password_reset_service, "_reset_recipient", change_before_send)
    if by_admin:
        assert admin.post("/users/2/password-reset").status_code == 409
    else:
        response = public.post(
            "/auth/reset-request", json={"email": "reader@example.com"}
        )
        assert (response.status_code, response.content) == (204, b"")
    server.send_message.assert_not_called()
    with Session(engine) as session:
        assert session.scalar(select(PasswordReset)) is None


def test_unauthenticated_smtp_retest_works_after_encryption_key_loss(
    clients, mail_server, monkeypatch
):
    client, engine = clients
    admin = client(UserRole.ADMIN)
    server, _, _ = mail_server
    assert save_settings(admin).status_code == 200
    monkeypatch.setitem(settings.__dict__, "mail_credentials_key", "")
    saved = save_settings(admin, {**CONFIG, "username": "", "password": ""})
    assert saved.json()["has_password"] is True
    tested = admin.post(f"{SMTP}/test", json=TEST_MAIL)
    assert tested.status_code == 200
    assert tested.json()["status"] == "tested"
    assert admin.get("/auth/reset-available").json() == {"available": True}
    mark_verified(engine)
    assert admin.post("/users/1/password-reset").status_code == 204
    server.login.assert_not_called()
    with Session(engine) as session:
        assert session.scalar(text("SELECT encrypted_password FROM smtp_settings"))


def test_public_reset_remains_neutral_when_sqlite_writer_is_busy(clients, mail_server):
    client, engine = clients
    admin, public = client(UserRole.ADMIN), client()
    client(UserRole.READER)
    server, _, _ = mail_server
    assert save_settings(admin).status_code == 200
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    mark_verified(engine)
    server.reset_mock()

    @event.listens_for(engine, "checkout")
    def skip_busy_wait(connection, _record, _proxy):
        connection.execute("PRAGMA busy_timeout = 0").close()

    with engine.begin() as writer:
        writer.execute(text("BEGIN IMMEDIATE"))
        for address in ("reader@example.com", "unknown@example.com"):
            response = public.post("/auth/reset-request", json={"email": address})
            assert (response.status_code, response.content) == (204, b"")
    server.send_message.assert_not_called()


def test_smtp_reset_coordinates_smtp_changes_without_blocking_other_sqlite_writes(
    clients, mail_server, monkeypatch
):
    client, engine = clients
    admin = client(UserRole.ADMIN)
    second_admin = client(UserRole.ADMIN, username="petra")
    client(UserRole.READER)
    server, _, _ = mail_server
    assert save_settings(admin).status_code == 200
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    mark_verified(engine)
    monkeypatch.setattr(smtp_service, "_SQLITE_SMTP_LOCK_TIMEOUT", 0)
    changed = {**CONFIG, "sender": "new@example.com"}

    def save_profile_during_delivery(_message):
        with engine.begin() as writer:
            writer.exec_driver_sql("PRAGMA busy_timeout = 0")
            writer.execute(text("UPDATE users SET username = 'Tim' WHERE id = 3"))
        assert save_settings(second_admin, changed).status_code == 409

    server.send_message.side_effect = save_profile_during_delivery
    assert admin.post("/users/3/password-reset").status_code == 204
    with Session(engine) as session:
        assert session.get(User, 3).username == "Tim"
        assert session.scalar(select(PasswordReset)) is not None
    assert save_settings(second_admin, changed).json()["status"] == "untested"


@pytest.mark.parametrize(
    "account_change",
    [
        {"email": "new@example.com"},
        {"password_hash": "new-password-hash"},
        {"is_active": False},
    ],
)
def test_reset_does_not_store_token_for_account_changed_during_smtp(
    clients, mail_server, account_change
):
    client, engine = clients
    admin = client(UserRole.ADMIN)
    client(UserRole.READER)
    server, _, _ = mail_server
    assert save_settings(admin).status_code == 200
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    mark_verified(engine)
    server.reset_mock()

    def change_account(_message):
        with engine.begin() as writer:
            writer.execute(update(User).where(User.id == 2).values(**account_change))

    server.send_message.side_effect = change_account
    assert admin.post("/users/2/password-reset").status_code == 409
    server.send_message.assert_called_once()
    with Session(engine) as session:
        assert session.scalar(select(PasswordReset)) is None


def test_reset_retries_sqlite_token_write_without_resending(clients, mail_server):
    client, engine = clients
    admin = client(UserRole.ADMIN)
    client(UserRole.READER)
    server, _, _ = mail_server
    assert save_settings(admin).status_code == 200
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    mark_verified(engine)
    server.reset_mock()

    @event.listens_for(engine, "checkout")
    def skip_busy_wait(connection, _record, _proxy):
        connection.execute("PRAGMA busy_timeout = 0").close()

    contention = []
    with engine.connect() as writer:

        @event.listens_for(engine, "handle_error")
        def release_after_first_failure(context):
            if (
                getattr(context.original_exception, "sqlite_errorcode", None)
                == SQLITE_BUSY
            ):
                contention.append(context.statement)
                writer.rollback()

        def start_writer(_message):
            writer.exec_driver_sql("BEGIN IMMEDIATE")

        server.send_message.side_effect = start_writer
        try:
            assert admin.post("/users/2/password-reset").status_code == 204
        finally:
            event.remove(engine, "handle_error", release_after_first_failure)

    assert len(contention) == 1
    server.send_message.assert_called_once()
    with Session(engine) as session:
        assert session.scalar(select(PasswordReset)) is not None


def test_failed_smtp_test_pauses_account_mail_without_unverifying_emails(clients, mail_server):
    client, _engine = clients
    admin, owner = client(UserRole.ADMIN), client()
    server, _, _ = mail_server
    assert save_settings(admin).status_code == 200
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    assert admin.post("/users", json={"username": "lena", "password": PASSWORD}).status_code == 201
    assert owner.post("/auth/login", json={"username": "lena", "password": PASSWORD}).status_code == 200
    email = "lena@example.com"
    assert owner.patch("/auth/me", json={"email": email, "current_password": PASSWORD}).status_code == 200
    token = mail_token(server, "/verify-email", email)
    assert owner.post("/auth/verify-email", json={"token": token}).status_code == 204
    credentials = {"username": email, "password": PASSWORD}

    # A transient delivery failure marks SMTP as untested. Changes or removal revoke verification.
    server.send_message.side_effect = smtplib.SMTPDataError(554, b"not accepted")
    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 502
    assert admin.get(SMTP).json()["status"] == "untested"
    server.send_message.side_effect = None
    assert owner.get("/auth/email-available").json() == {"available": False}
    assert owner.post("/auth/login", json=credentials).status_code == 401
    assert owner.get("/auth/me").json()["email_verified_at"]

    assert admin.post(f"{SMTP}/test", json=TEST_MAIL).status_code == 200
    assert owner.post("/auth/login", json=credentials).status_code == 200
