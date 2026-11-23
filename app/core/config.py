import os
from dataclasses import dataclass, field


def _database_url_from_env() -> str:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return database_url
    sqlite_path = os.environ.get("SQLITE_DATABASE_PATH") or "./heritagekitchen.db"
    return f"sqlite:///{sqlite_path}"


def _app_version_from_env() -> str:
    return os.environ.get("APP_VERSION") or "0.1.0"


def _session_cookie_secure_from_env() -> str:
    return os.environ.get("SESSION_COOKIE_SECURE", "auto").strip().lower()


@dataclass(frozen=True)
class Settings:
    app_name: str = "Heritage Kitchen API"
    app_version: str = field(default_factory=_app_version_from_env)
    app_description: str = (
        "Self-hosted cookbook backend for small private or shared setups"
    )
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_reload: bool = True
    # Defaults to zero-config SQLite; set DATABASE_URL (e.g. a
    # postgresql+psycopg://... connection string) to use Postgres instead.
    database_url: str = field(default_factory=_database_url_from_env)
    recipe_images_dir: str = "recipe-images"
    # Cap on the raw upload before processing -- generous enough that a
    # modern phone photo is never rejected. The stored file ends up much
    # smaller since every upload is resized/recompressed on the server.
    recipe_image_max_bytes: int = 20 * 1024 * 1024  # 20 MB
    recipe_image_allowed_content_types: tuple[str, ...] = (
        "image/jpeg",
        "image/png",
        "image/webp",
    )
    # Every uploaded image is resized to fit within this on its longest
    # edge and re-encoded as JPEG, so recipe photos stay small and fast
    # to load regardless of what came straight off someone's phone.
    recipe_image_max_dimension: int = 1600
    recipe_image_jpeg_quality: int = 82
    media_url_prefix: str = "/media/recipe-images"
    session_cookie_httponly: bool = True
    session_cookie_name: str = "heritagekitchen_session"
    session_cookie_path: str = "/"
    session_cookie_samesite: str = "lax"
    session_cookie_secure: str = field(default_factory=_session_cookie_secure_from_env)
    session_lifetime_days: int = 7
    login_rate_limit_max_attempts: int = 5
    login_rate_limit_window_seconds: int = 60
    reset_base_url: str = field(
        default_factory=lambda: os.environ.get("RESET_BASE_URL", "")
    )
    mail_credentials_key: str = field(
        default_factory=lambda: os.environ.get("MAIL_CREDENTIALS_KEY", ""),
        repr=False,
    )


settings = Settings()
