from datetime import UTC, datetime

from app.models.session_model import UserSession


def test_user_session_model_contains_session_data():
    expires_at = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    user_session = UserSession(
        id=1,
        user_id=2,
        token_hash="token-hash",
        expires_at=expires_at,
    )

    assert user_session.user_id == 2
    assert user_session.token_hash == "token-hash"
    assert user_session.expires_at == expires_at


def test_user_session_token_hash_is_unique_and_indexed():
    token_hash_column = UserSession.__table__.c.token_hash

    assert token_hash_column.unique is True
    assert token_hash_column.index is True
