from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from smart_laundry.image_storage import (
    CARD_IMAGE_SIZE,
    ImageStorageError,
    crop_item_image,
    save_item_image,
    validate_crop_box,
)


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


def test_crop_image_uses_card_size() -> None:
    cropped = crop_item_image(
        _png_bytes((1200, 900)),
        {"left": 0.065, "top": 0.0, "width": 0.87, "height": 1.0},
    )

    assert cropped.size == CARD_IMAGE_SIZE


def test_crop_box_outside_image_is_rejected() -> None:
    with pytest.raises(ImageStorageError, match="超出原图"):
        validate_crop_box(
            {"left": 0.8, "top": 0.1, "width": 0.4, "height": 0.5}
        )


def test_crop_box_with_wrong_aspect_ratio_is_rejected() -> None:
    with pytest.raises(ImageStorageError, match="比例"):
        crop_item_image(
            _png_bytes((1200, 900)),
            {"left": 0.1, "top": 0.1, "width": 0.5, "height": 0.5},
        )


def test_cropped_image_is_saved_at_exact_card_size(tmp_path: Path) -> None:
    target = save_item_image(
        _png_bytes((1200, 900)),
        tmp_path / "uploads",
        crop_box={"left": 0.065, "top": 0.0, "width": 0.87, "height": 1.0},
    )

    with Image.open(target) as image:
        assert image.size == CARD_IMAGE_SIZE
