import io
import logging
import uuid
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException, Response, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.schemas import RecipeImageResponse, RecipeImageUpdateRequest
from app.core.config import settings
from app.models.recipe_image_model import RecipeImage
from app.models.recipe_model import Recipe
from app.services import recipe_image_storage, recipe_lock_service

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Every upload is re-encoded as JPEG regardless of the original format, so
# storage stays small, predictable, and widely browser-compatible.
_OUTPUT_EXTENSION = ".jpg"

MAX_RECIPE_IMAGES = 20


def _resize_and_reencode(image_bytes: bytes, *, profile: bool = False) -> bytes:
    """Shrink to settings.recipe_image_max_dimension and re-save as JPEG.

    Runs on every upload so a multi-megapixel phone photo never ends up
    stored (and re-downloaded for a small thumbnail) at full size. Also
    applies the EXIF orientation so photos taken upright on a phone don't
    end up sideways once the tag is dropped on re-save.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if profile:
            if image.format not in {"JPEG", "PNG"}:
                raise HTTPException(status_code=415, detail="Erlaubt sind JPG und PNG.")
            if min(image.size) < 200:
                raise HTTPException(status_code=422, detail="Das Bild muss mindestens 200 × 200 Pixel groß sein.")
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File could not be read as an image.",
        ) from exc

    image = ImageOps.exif_transpose(image)
    if profile:
        size = min(*image.size, settings.recipe_image_max_dimension)
        image = ImageOps.fit(image, (size, size))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    max_dimension = settings.recipe_image_max_dimension
    image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    output = io.BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=settings.recipe_image_jpeg_quality,
        optimize=True,
    )
    return output.getvalue()


def store_upload(
    image: UploadFile, folder: str, *, track_recipe_upload: bool = False, profile: bool = False
) -> str:
    """Prüft, verkleinert und speichert ein Bild, gibt den öffentlichen Pfad zurück."""
    processed_bytes = _prepare_upload(image, profile=profile)
    return _store_processed_upload(processed_bytes, folder, track_recipe_upload=track_recipe_upload)


def _prepare_upload(image: UploadFile, *, profile: bool = False) -> bytes:
    content_types = {"image/jpeg", "image/png"} if profile else _ALLOWED_CONTENT_TYPES
    if image.content_type not in content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Erlaubt sind JPG und PNG." if profile else "Only JPEG, PNG and WebP images are allowed.",
        )

    limit = min(settings.recipe_image_max_bytes, 20 * 1024 * 1024) if profile else settings.recipe_image_max_bytes
    image_bytes = image.file.read(limit + 1)
    if len(image_bytes) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image must not be larger than "
            f"{limit // (1024 * 1024)} MB.",
        )

    return _resize_and_reencode(image_bytes, profile=profile)


def _store_processed_upload(
    processed_bytes: bytes, folder: str, *, track_recipe_upload: bool = False,
) -> str:
    image_dir = Path(settings.recipe_images_dir) / folder
    image_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}{_OUTPUT_EXTENSION}"
    stored = image_dir / filename
    if track_recipe_upload:
        recipe_image_storage.track_recipe_upload(stored)
    stored.write_bytes(processed_bytes)
    return f"{settings.media_url_prefix}/{folder}/{filename}"


def remove_stored_upload(image_path: str | None) -> None:
    if image_path:
        relative_path = image_path.removeprefix(f"{settings.media_url_prefix}/")
        (Path(settings.recipe_images_dir) / relative_path).unlink(missing_ok=True)


def create_recipe_image(
    *,
    db_session: Session,
    recipe_id: int,
    image: UploadFile,
    alt_text: str | None,
    expected_version: int,
) -> RecipeImageResponse:
    if db_session.scalar(select(Recipe.id).where(Recipe.id == recipe_id)) is None:
        raise HTTPException(404, "Recipe not found.")
    with _prepared_upload(db_session, recipe_id, image) as processed_bytes:
        recipe = recipe_lock_service.lock_recipe(db_session, recipe_id)
        recipe_lock_service.require_recipe_version(db_session, recipe, expected_version)
        images = recipe.images
        if len(images) >= MAX_RECIPE_IMAGES:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"A recipe can have at most {MAX_RECIPE_IMAGES} images. Remove one before adding another.",
            )
        recipe_image = RecipeImage(
            file_path=_store_processed_upload(processed_bytes, str(recipe_id), track_recipe_upload=True),
            alt_text=alt_text,
            is_main=not images,
            position=max((image.position for image in images), default=-1) + 1,
        )
        images.append(recipe_image)
        return _commit_image_upload(db_session, recipe, recipe_image)


def apply_version_headers(db: Session, response: Response) -> None:
    before, after = db.info.pop("recipe_revision_headers")
    response.headers["X-Recipe-Version-Before"] = str(before)
    response.headers["X-Recipe-Version"] = str(after)


def _lock_image(db: Session, image_id: int, expected_version: int) -> tuple[Recipe, RecipeImage]:
    recipe_id = select(RecipeImage.recipe_id).where(RecipeImage.id == image_id).scalar_subquery()
    recipe = recipe_lock_service.lock_recipe(db, recipe_id, not_found="Recipe image not found.")
    image = next((image for image in recipe.images if image.id == image_id), None)
    if image is None:
        raise HTTPException(404, "Recipe image not found.")
    recipe_lock_service.require_recipe_version(db, recipe, expected_version)
    return recipe, image


def _commit_image_change(
    db: Session, recipe: Recipe, image: RecipeImage | None = None,
) -> RecipeImageResponse | None:
    version_before = recipe.version
    recipe.version += 1
    db.flush()
    db.info["recipe_revision_headers"] = (version_before, recipe.version)
    response = RecipeImageResponse.model_validate(image) if image is not None else None
    db.commit()
    return response


def _commit_image_upload(
    db: Session, recipe: Recipe, image: RecipeImage,
) -> RecipeImageResponse:
    recipe_id, path = recipe.id, image.file_path
    response = _commit_image_change(db, recipe, image)
    recipe_image_storage.finish_recipe_upload(recipe_id, path)
    return response


@contextmanager
def _prepared_upload(db: Session, recipe_id: int, image: UploadFile):
    # Decode/resize before BEGIN IMMEDIATE / the recipe row lock. Store only
    # under the lock, so orphan cleanup cannot remove an in-flight upload.
    try:
        yield _prepare_upload(image)
    except Exception:
        try:
            db.rollback()
        except SQLAlchemyError:
            logging.getLogger(__name__).exception("Could not roll back recipe image upload for %s", recipe_id)
        else:
            recipe_image_storage.retry_recipe_file_deletions(db.get_bind().engine, recipe_id)
        raise


def crop_recipe_image(
    *, db_session: Session, recipe_image_id: int, image: UploadFile,
    expected_version: int,
) -> RecipeImageResponse:
    recipe_id = db_session.scalar(select(RecipeImage.recipe_id).where(RecipeImage.id == recipe_image_id))
    if recipe_id is None:
        raise HTTPException(404, "Recipe image not found.")
    with _prepared_upload(db_session, recipe_id, image) as processed_bytes:
        recipe, existing = _lock_image(db_session, recipe_image_id, expected_version)
        recipe_image_storage.queue_recipe_file_deletions(db_session, recipe_id, {existing.file_path})
        existing.file_path = _store_processed_upload(processed_bytes, str(recipe_id), track_recipe_upload=True)
        response = _commit_image_upload(db_session, recipe, existing)
        recipe_image_storage.retry_recipe_file_deletions(db_session.get_bind().engine, recipe_id)
        return response


def list_recipe_images(*, db_session: Session) -> list[RecipeImageResponse]:
    recipe_images = db_session.scalars(select(RecipeImage).order_by(RecipeImage.id))
    return [
        RecipeImageResponse.model_validate(recipe_image)
        for recipe_image in recipe_images
    ]


def get_recipe_image(
    *, db_session: Session, recipe_image_id: int
) -> RecipeImageResponse:
    recipe_image = db_session.get(RecipeImage, recipe_image_id)
    if recipe_image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipe image not found.",
        )

    return RecipeImageResponse.model_validate(recipe_image)


def update_recipe_image(
    *,
    db_session: Session,
    recipe_image_id: int,
    recipe_image_update_request: RecipeImageUpdateRequest,
    expected_version: int,
) -> RecipeImageResponse:
    recipe, recipe_image = _lock_image(db_session, recipe_image_id, expected_version)

    update_data = recipe_image_update_request.model_dump(exclude_unset=True)
    if update_data.get("is_main"):
        # pro Rezept gibt es nur ein Hauptbild
        for other in recipe.images:
            other.is_main = other is recipe_image
    if "alt_text" in update_data:
        recipe_image.alt_text = update_data["alt_text"]

    return _commit_image_change(db_session, recipe, recipe_image)


def delete_recipe_image(
    *, db_session: Session, recipe_image_id: int, expected_version: int,
) -> None:
    recipe, image = _lock_image(db_session, recipe_image_id, expected_version)
    recipe_id = recipe.id
    recipe_image_storage.queue_recipe_file_deletions(db_session, recipe_id, {image.file_path})
    recipe.images.remove(image)
    if image.is_main and recipe.images:
        recipe.images[0].is_main = True
    _commit_image_change(db_session, recipe)
    recipe_image_storage.retry_recipe_file_deletions(db_session.get_bind().engine, recipe_id)


def reorder_recipe_images(
    *, db_session: Session, recipe_id: int, image_ids: list[int], expected_version: int,
) -> list[RecipeImageResponse]:
    recipe = recipe_lock_service.lock_recipe(db_session, recipe_id)
    recipe_lock_service.require_recipe_version(db_session, recipe, expected_version)
    images = {image.id: image for image in recipe.images}
    if len(image_ids) != len(set(image_ids)) or set(image_ids) != images.keys():
        raise HTTPException(422, "The order must list every image of the recipe exactly once.")
    for position, image_id in enumerate(image_ids):
        images[image_id].position = position
    db_session.flush()
    db_session.expire(recipe, ["images"])
    result = [RecipeImageResponse.model_validate(image) for image in recipe.images]
    _commit_image_change(db_session, recipe)
    return result
