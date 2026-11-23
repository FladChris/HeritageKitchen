import io
from dataclasses import replace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from PIL import Image

from app.core.config import settings
from app.services import recipe_image_service


def _jpeg_bytes(width: int, height: int, color=(200, 100, 50)) -> bytes:
    image = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _fake_upload(content: bytes, content_type: str = "image/jpeg"):
    upload = Mock()
    upload.content_type = content_type
    upload.file = io.BytesIO(content)
    return upload


def test_resize_and_reencode_shrinks_oversized_image():
    original = _jpeg_bytes(4000, 3000)

    processed = recipe_image_service._resize_and_reencode(original)

    result = Image.open(io.BytesIO(processed))
    assert result.format == "JPEG"
    assert max(result.size) == settings.recipe_image_max_dimension
    assert len(processed) < len(original)


def test_resize_and_reencode_does_not_upscale_small_image():
    original = _jpeg_bytes(200, 150)

    processed = recipe_image_service._resize_and_reencode(original)

    result = Image.open(io.BytesIO(processed))
    assert result.size == (200, 150)


def test_resize_and_reencode_converts_png_to_jpeg():
    image = Image.new("RGBA", (300, 300), color=(10, 20, 30, 255))
    buf = io.BytesIO()
    image.save(buf, format="PNG")

    processed = recipe_image_service._resize_and_reencode(buf.getvalue())

    result = Image.open(io.BytesIO(processed))
    assert result.format == "JPEG"


def test_resize_and_reencode_rejects_unreadable_file():
    with pytest.raises(HTTPException) as e:
        recipe_image_service._resize_and_reencode(b"not an image")

    assert e.value.status_code == 415


def test_store_upload_rejects_unsupported_content_type():
    with pytest.raises(HTTPException) as e:
        recipe_image_service.store_upload(
            _fake_upload(b"whatever", content_type="application/pdf"), "1"
        )

    assert e.value.status_code == 415


def test_store_upload_rejects_oversized_upload(monkeypatch):
    monkeypatch.setattr(
        recipe_image_service,
        "settings",
        replace(settings, recipe_image_max_bytes=10),
    )
    with pytest.raises(HTTPException) as e:
        recipe_image_service.store_upload(_fake_upload(_jpeg_bytes(100, 100)), "1")

    assert e.value.status_code == 413


def test_store_upload_stores_resized_jpeg_regardless_of_input_format(tmp_path, monkeypatch):
    monkeypatch.setattr(
        recipe_image_service,
        "settings",
        replace(settings, recipe_images_dir=str(tmp_path)),
    )
    png_image = Image.new("RGBA", (3000, 2000), color=(1, 2, 3, 255))
    buf = io.BytesIO()
    png_image.save(buf, format="PNG")

    path = recipe_image_service.store_upload(
        _fake_upload(buf.getvalue(), content_type="image/png"), "1"
    )

    assert path.endswith(".jpg")
    stored_files = list((tmp_path / "1").iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].suffix == ".jpg"

    stored_image = Image.open(stored_files[0])
    assert stored_image.format == "JPEG"
    assert max(stored_image.size) == settings.recipe_image_max_dimension
