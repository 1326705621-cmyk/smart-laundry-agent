"""验证并保存用户上传的物品图片。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Mapping
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_IMAGE_BYTES = 5 * 1024 * 1024
CARD_IMAGE_SIZE = (1160, 1000)


class ImageStorageError(ValueError):
    """上传内容不是可安全处理的图片。"""


def _load_image(content: bytes) -> Image.Image:
    """校验上传内容并按 EXIF 方向还原图片。"""

    if not content:
        raise ImageStorageError("上传的图片为空。")
    if len(content) > MAX_IMAGE_BYTES:
        raise ImageStorageError("图片不能超过 5 MB。")

    try:
        image = Image.open(BytesIO(content))
        image.verify()
        image = Image.open(BytesIO(content))
        image = ImageOps.exif_transpose(image)
        image.load()
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ImageStorageError("文件不是有效的 JPG、PNG 或 WebP 图片。") from error
    return image


def validate_item_image(content: bytes) -> tuple[int, int]:
    """在打开预览器前校验图片，返回按 EXIF 还原后的尺寸。"""

    return _load_image(content).size


def validate_crop_box(crop_box: Mapping[str, object]) -> dict[str, float]:
    """校验浏览器返回的归一化裁剪框，防止越界或空白图片。"""

    try:
        normalized = {
            key: float(crop_box[key]) for key in ("left", "top", "width", "height")
        }
    except (KeyError, TypeError, ValueError) as error:
        raise ImageStorageError("图片构图参数无效，请重新调整预览。") from error

    left = normalized["left"]
    top = normalized["top"]
    width = normalized["width"]
    height = normalized["height"]
    tolerance = 1e-4
    if (
        left < -tolerance
        or top < -tolerance
        or width <= 0
        or height <= 0
        or left + width > 1 + tolerance
        or top + height > 1 + tolerance
    ):
        raise ImageStorageError("图片构图超出原图范围，请重新调整预览。")
    return {
        "left": max(0.0, left),
        "top": max(0.0, top),
        "width": min(width, 1.0 - max(0.0, left)),
        "height": min(height, 1.0 - max(0.0, top)),
    }


def crop_item_image(
    content: bytes,
    crop_box: Mapping[str, object],
    *,
    output_size: tuple[int, int] = CARD_IMAGE_SIZE,
) -> Image.Image:
    """按预览框裁剪并输出与物品卡一致比例的图片。"""

    image = _load_image(content)
    crop = validate_crop_box(crop_box)
    image_width, image_height = image.size
    left = round(crop["left"] * image_width)
    top = round(crop["top"] * image_height)
    right = round((crop["left"] + crop["width"]) * image_width)
    bottom = round((crop["top"] + crop["height"]) * image_height)
    right = min(image_width, max(left + 1, right))
    bottom = min(image_height, max(top + 1, bottom))
    crop_ratio = (right - left) / (bottom - top)
    expected_ratio = output_size[0] / output_size[1]
    if abs(crop_ratio - expected_ratio) > 0.02:
        raise ImageStorageError("图片构图比例无效，请重新调整预览。")
    return image.crop((left, top, right, bottom)).resize(
        output_size, Image.Resampling.LANCZOS
    )


def cropped_item_image_bytes(
    content: bytes, crop_box: Mapping[str, object]
) -> bytes:
    """生成供 Streamlit 展示的最终卡片预览，不写入磁盘。"""

    buffer = BytesIO()
    crop_item_image(content, crop_box).save(buffer, "WEBP", quality=88, method=4)
    return buffer.getvalue()


def save_item_image(
    content: bytes,
    upload_directory: str | Path,
    *,
    crop_box: Mapping[str, object] | None = None,
) -> Path:
    """校验图片，可按预览构图裁剪，并保存为随机名称的 WebP 文件。"""

    image = _load_image(content)
    processed = (
        crop_item_image(content, crop_box) if crop_box is not None else image.copy()
    )
    if crop_box is None:
        processed.thumbnail((1600, 1600))

    directory = Path(upload_directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    image_id = uuid4().hex
    target = directory / f"{image_id}.webp"
    processed.save(target, "WEBP", quality=88, method=4)
    return target
