"""Administrator-only, point-in-time exports of cookbook content (not a backup)."""

import json
from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.schemas.recipe_schema import RecipeResponse
from app.core.config import settings
from app.models.app_setting_model import AppSetting
from app.models.category_model import Category
from app.models.recipe_comment_model import RecipeComment
from app.models.recipe_model import Recipe
from app.models.recipe_rating_model import RecipeRating
from app.models.user_model import User
from app.services.cookbook_pdf_service import render_cookbook_pdf


class ExportUnavailable(Exception):
    """A complete and internally consistent export cannot be produced."""


def _media_location(public_path: str) -> tuple[str, Path]:
    """Only allow managed cookbook media, never arbitrary paths from the database."""
    prefix = settings.media_url_prefix.rstrip("/") + "/"
    if not public_path.startswith(prefix):
        raise ExportUnavailable("An image has an invalid storage path.")
    relative = public_path[len(prefix):]
    parts = relative.split("/")
    if not parts or any(
        part in ("", ".", "..") or part.endswith((".", " "))
        or any(char in part for char in "\\:\x00")
        for part in parts
    ):
        raise ExportUnavailable("An image has an invalid storage path.")
    root = Path(settings.recipe_images_dir).resolve()
    stored = root.joinpath(*parts)
    if not stored.resolve().is_relative_to(root):
        raise ExportUnavailable("An image points outside the media directory.")
    return "images/" + "/".join(parts), stored


def _read_media(public_path: str) -> bytes:
    _, stored = _media_location(public_path)
    try:
        content = stored.read_bytes()
        # Never label a ZIP complete if an image is unreadable/corrupted.
        with Image.open(BytesIO(content)) as image:
            image.verify()
        return content
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise ExportUnavailable("A referenced image is unavailable or invalid.") from exc


def _collect(db: Session, *, include_archive_data: bool) -> tuple[dict, list[RecipeResponse], dict[str, str]]:
    """Run every query inside the same repeatable-read database snapshot."""
    categories = db.scalars(select(Category).order_by(Category.name, Category.id)).all()
    recipes = db.scalars(select(Recipe).order_by(Recipe.title, Recipe.id)).all()
    users = {
        user_id: username
        for user_id, username in db.execute(
            select(User.id, User.username)
        )
    }
    comments = defaultdict(list)
    ratings = defaultdict(list)
    for row in db.scalars(
        select(RecipeComment).order_by(
            RecipeComment.recipe_id, RecipeComment.created_at, RecipeComment.id
        )
    ):
        comments[row.recipe_id].append({
            "id": row.id,
            "author_id": row.author_id,
            "author_name": users.get(row.author_id, "Gelöschter Benutzer"),
            "text": row.text,
            "created_at": row.created_at.isoformat(),
            "edited_at": row.edited_at.isoformat() if row.edited_at else None,
        })
    for row in db.scalars(
        select(RecipeRating).order_by(RecipeRating.recipe_id, RecipeRating.user_id)
    ):
        ratings[row.recipe_id].append({
            "user_id": row.user_id,
            "user_name": users.get(row.user_id, "Gelöschter Benutzer"),
            "half_stars": row.half_stars,
        })
    media: dict[str, str] = {}

    def register(path: str) -> str:
        if path not in media:
            archive_path, _ = _media_location(path)
            media[path] = archive_path
        return media[path]

    category_data = []
    for category in categories:
        category_data.append({
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "image_path": category.image_path,
            "image_alt_text": category.image_alt_text,
            "image_archive_path": register(category.image_path)
            if include_archive_data and category.image_path else None,
        })

    recipe_data = []
    pdf_recipes = []
    for recipe in recipes:
        view = RecipeResponse.model_validate(recipe)
        pdf_recipes.append(view)
        data = view.model_dump(mode="json")
        for item, image in zip(data["images"], recipe.images, strict=True):
            item["position"] = image.position
            if include_archive_data:
                item["archive_path"] = register(image.file_path)
        if include_archive_data:
            data["comments"] = comments[recipe.id]
            data["ratings"] = ratings[recipe.id]
        recipe_data.append(data)
    manifest = {
        "format": "heritagekitchen-cookbook",
        "format_version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "description": "Lesbarer Kochbuchexport; kein Backup und kein Importformat.",
        "categories": category_data,
        "recipes": recipe_data,
    }
    return manifest, pdf_recipes, media


def _build_export(db_session: Session, fmt: str) -> bytes:
    # Authentication may already have queried db_session; an independent
    # transaction is necessary to select the isolation level before the first read.
    with Session(bind=db_session.get_bind()) as snapshot, snapshot.begin():
        dialect = snapshot.get_bind().dialect.name
        if dialect == "postgresql":
            snapshot.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        elif dialect == "sqlite":
            # SQLAlchemy's implicit transaction alone does not issue SQLite BEGIN.
            # An explicit BEGIN pins one snapshot across all subsequent SELECTs.
            snapshot.execute(text("BEGIN"))

        manifest, pdf_recipes, paths = _collect(
            snapshot, include_archive_data=fmt == "zip"
        )
        if fmt == "pdf":
            from app.api.routes.settings_route import DEFAULTS  # avoids import cycle

            values = {
                key: setting.value if (setting := snapshot.get(AppSetting, key)) else default
                for key, default in DEFAULTS.items()
            }
            return render_cookbook_pdf(
                pdf_recipes, values["cookbook_name"], values["footer_text"]
            )

        media_bytes = {path: _read_media(path) for path in sorted(paths)}
        manifest["media"] = [
            {
                "source_path": path,
                "archive_path": paths[path],
                "sha256": sha256(media_bytes[path]).hexdigest(),
                "bytes": len(media_bytes[path]),
            }
            for path in sorted(paths)
        ]
        output = BytesIO()
        with ZipFile(output, mode="w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr(
                "cookbook.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            for path in sorted(paths):
                archive.writestr(paths[path], media_bytes[path])
        return output.getvalue()


def export_cookbook(db_session: Session, fmt: str) -> bytes:
    if fmt not in ("zip", "pdf"):
        raise ValueError("Unsupported cookbook export format.")
    try:
        return _build_export(db_session, fmt)
    except ExportUnavailable as exc:
        # No response bytes have been returned; callers cannot receive a partial file.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
