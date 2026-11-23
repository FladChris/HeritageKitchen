import logging
import re
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import lock_sqlite_writes
from app.models.recipe_image_deletion_model import RecipeImageDeletion
from app.models.recipe_image_model import RecipeImage
from app.models.recipe_model import Recipe

_UPLOAD_MARKER = re.compile(
    r"\.([a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}\.jpg)\.pending"
)
logger = logging.getLogger(__name__)


def stored_recipe_image(recipe_id: int, file_path: str) -> Path | None:
    # Only unlink files owned by this recipe's managed upload directory.
    prefix = f"{settings.media_url_prefix}/{recipe_id}/"
    if not file_path.startswith(prefix):
        return None
    filename = file_path[len(prefix):]
    if not filename or filename.endswith((".", " ")) or any(char in filename for char in "/\\:\x00"):
        return None
    directory = Path(settings.recipe_images_dir).resolve() / str(recipe_id)
    path = directory / filename
    return path if path.resolve().is_relative_to(directory) else None


def queue_recipe_file_deletions(db: Session, recipe_id: int, paths: set[str]) -> bool:
    if not paths:
        return False
    queued = set(db.scalars(
        select(RecipeImageDeletion.file_path).where(
            RecipeImageDeletion.recipe_id == recipe_id,
            RecipeImageDeletion.file_path.in_(paths),
        )
    ))
    db.add_all(RecipeImageDeletion(recipe_id=recipe_id, file_path=path) for path in paths - queued)
    return True


def _lock_recipe_for_cleanup(db: Session, recipe_id: int) -> None:
    lock_sqlite_writes(db)
    db.scalar(select(Recipe.id).where(Recipe.id == recipe_id).with_for_update(key_share=True, nowait=True))


def _upload_marker(stored: Path) -> Path:
    return stored.with_name(f".{stored.name}.pending")


def track_recipe_upload(stored: Path) -> None:
    # The marker must survive a database outage or an interrupted upload.
    _upload_marker(stored).touch(exist_ok=False)


def finish_recipe_upload(recipe_id: int, file_path: str) -> None:
    try:
        stored = stored_recipe_image(recipe_id, file_path)
        if stored is not None:
            _upload_marker(stored).unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not clear recipe upload marker for %s", file_path)


def _pending_uploads(recipe_id: int | None) -> dict[int, dict[str, Path]]:
    uploads: dict[int, dict[str, Path]] = {}
    root = Path(settings.recipe_images_dir).resolve()
    folder = "*" if recipe_id is None else str(recipe_id)
    for marker in root.glob(f"{folder}/.*.jpg.pending"):
        match = _UPLOAD_MARKER.fullmatch(marker.name)
        if not match or marker.parent.is_symlink():
            continue
        directory = marker.parent.name
        if not re.fullmatch(r"0|-?[1-9][0-9]*", directory):
            continue
        prefix = f"{settings.media_url_prefix}/{directory}"
        uploads.setdefault(int(directory), {})[f"{prefix}/{match[1]}"] = marker
    return uploads


def _retry_recipe_file_deletions(
    engine: Engine, recipe_id: int, uploads: dict[str, Path]
) -> None:
    with Session(engine) as db, db.begin():
        _lock_recipe_for_cleanup(db, recipe_id)
        pending = {
            entry.file_path: entry
            for entry in db.scalars(
                select(RecipeImageDeletion)
                .where(RecipeImageDeletion.recipe_id == recipe_id)
                .with_for_update(skip_locked=True)
            )
        }
        paths = pending.keys() | uploads.keys()
        if not paths:
            return
        referenced = set(db.scalars(select(RecipeImage.file_path).where(RecipeImage.file_path.in_(paths))))
        for path in paths:
            try:
                stored = stored_recipe_image(recipe_id, path)
                if stored is not None and path not in referenced:
                    stored.unlink(missing_ok=True)
                if path in uploads and stored is not None:
                    uploads[path].unlink(missing_ok=True)
                if path in pending and (stored is None or path not in referenced):
                    db.delete(pending[path])
            except OSError:
                logger.exception("Could not reconcile pending recipe image %s", path)


def retry_recipe_file_deletions(engine: Engine, recipe_id: int | None = None) -> None:
    try:
        uploads = _pending_uploads(recipe_id)
    except OSError:
        logger.exception("Could not discover pending recipe image uploads")
        uploads = {}
    try:
        if recipe_id is None:
            with Session(engine) as db:
                recipe_ids = set(db.scalars(select(RecipeImageDeletion.recipe_id).distinct()))
            recipe_ids.update(uploads)
        else:
            recipe_ids = {recipe_id}
    except SQLAlchemyError:
        logger.exception("Could not load pending recipe image deletions")
        return

    for pending_recipe_id in recipe_ids:
        try:
            _retry_recipe_file_deletions(engine, pending_recipe_id, uploads.get(pending_recipe_id, {}))
        except SQLAlchemyError:
            logger.exception("Could not retry image deletions for recipe %s", pending_recipe_id)
