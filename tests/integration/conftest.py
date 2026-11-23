import os
from collections import defaultdict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.api.app import app, media_files
from app.core import db, rate_limit
from app.core.config import settings
from app.core.migrations import run_migrations
from app.models import Base


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Each isolated database also gets an isolated in-process login limiter.
    monkeypatch.setattr(rate_limit, "_attempts_by_ip", defaultdict(list))
    database_url = os.environ.get("TEST_DATABASE_URL") or (
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    )
    engine = db.create_database_engine(database_url)
    monkeypatch.setattr(db, "engine", engine)
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    run_migrations(engine)

    images_dir = tmp_path / "recipe-images"
    images_dir.mkdir()
    original_images_dir = settings.recipe_images_dir
    original_cookie_secure = settings.session_cookie_secure
    object.__setattr__(settings, "recipe_images_dir", str(images_dir))
    object.__setattr__(settings, "session_cookie_secure", False)
    monkeypatch.setattr(media_files, "all_directories", [str(images_dir)])

    session_factory = sessionmaker(bind=engine)

    def get_test_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[db.get_db] = get_test_db
    try:
        # TestClient without a context manager does not run the production lifespan.
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(db.get_db, None)
        object.__setattr__(settings, "recipe_images_dir", original_images_dir)
        object.__setattr__(settings, "session_cookie_secure", original_cookie_secure)
        engine.dispose()
