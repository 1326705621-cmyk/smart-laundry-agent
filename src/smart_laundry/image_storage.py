"""验证并保存用户上传的物品图片。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError


MAX_IMAGE_BYTES = 5 * 1024 * 1024


class ImageStorageError(ValueError):
    """上传内容不是可安全处理的图片。"""


def save_item_image(content: bytes, upload_directory: str | Path) -> Path:
    """校验图片、限制尺寸，并保存为随机名称的 WebP 文件。"""

    if not content:
        raise ImageStorageError("上传的图片为空。")
    if len(content) > MAX_IMAGE_BYTES:
        raise ImageStorageError("图片不能超过 5 MB。")

    try:
        image = Image.open(BytesIO(content))
        image.verify()
        image = Image.open(BytesIO(content))
        image.thumbnail((1600, 1600))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ImageStorageError("文件不是有效的 JPG、PNG 或 WebP 图片。") from error

    directory = Path(upload_directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{uuid4().hex}.webp"
    image.save(target, "WEBP", quality=88, method=4)
    return target
