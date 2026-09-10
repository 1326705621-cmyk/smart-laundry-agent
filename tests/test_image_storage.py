from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from smart_laundry.image_storage import ImageStorageError, save_item_image


def _png_bytes(size: tuple[int, int] = (80, 60)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=(120, 150, 170)).save(buffer, "PNG")
    return buffer.getvalue()


def test_valid_image_is_saved_with_random_webp_name(tmp_path: Path) -> None:
    target = save_item_image(_png_bytes((2000, 1200)), tmp_path / "uploads")

    assert target.exists()
    assert target.suffix == ".webp"
    with Image.open(target) as image:
        assert max(image.size) <= 1600


def test_invalid_image_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ImageStorageError, match="有效"):
        save_item_image(b"not an image", tmp_path)


def test_empty_image_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ImageStorageError, match="为空"):
        save_item_image(b"", tmp_path)
