from app.core.security import (
    create_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)


def test_hash_password_uses_argon2id():
    password_hash = hash_password("supersecret123")

    assert password_hash.startswith("$argon2id$")


def test_verify_password_accepts_matching_password():
    password_hash = hash_password("supersecret123")

    assert verify_password("supersecret123", password_hash) is True


def test_verify_password_rejects_wrong_password():
    password_hash = hash_password("supersecret123")

    assert verify_password("wrong-password", password_hash) is False


def test_hash_password_uses_unique_salts():
    first_hash = hash_password("supersecret123")
    second_hash = hash_password("supersecret123")

    assert first_hash != second_hash


def test_create_session_token_returns_unique_tokens():
    first_token = create_session_token()
    second_token = create_session_token()

    assert first_token != second_token


def test_hash_session_token_returns_stable_sha256_hash():
    session_token = create_session_token()

    first_hash = hash_session_token(session_token)
    second_hash = hash_session_token(session_token)

    assert first_hash == second_hash
    assert first_hash != session_token
    assert len(first_hash) == 64
