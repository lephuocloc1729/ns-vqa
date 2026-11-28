"""Uploaded images: checked, then kept in the upload folder under their sha256 (one copy per photo)."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

IMAGE_TYPES = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


def save_image(upload_dir: Path, data: bytes, max_bytes: int) -> tuple[str, Path]:
    """Check the bytes are a JPEG, PNG or WEBP of at most `max_bytes`, and keep them. HTTP errors for a bad one."""
    if len(data) > max_bytes:
        raise HTTPException(413, f"image larger than {max_bytes // (1024 * 1024)} MB")
    if not data:
        raise HTTPException(400, "empty image")
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = im.format
            im.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise HTTPException(415, "not a readable image")
    if fmt not in IMAGE_TYPES:
        raise HTTPException(415, f"image type {fmt} not accepted (JPEG, PNG or WEBP)")
    sha = hashlib.sha256(data).hexdigest()
    path = upload_dir / f"{sha}{IMAGE_TYPES[fmt]}"
    if not path.exists():
        path.write_bytes(data)
    return sha, path


def find_image(upload_dir: Path, sha: str) -> Path | None:
    for ext in IMAGE_TYPES.values():
        p = upload_dir / f"{sha}{ext}"
        if p.exists():
            return p
    return None


def write_thumbnail(source: Path, target: Path, size: int = 480) -> None:
    """A small JPEG for a gallery (turned upright from the photo's EXIF orientation)."""
    with Image.open(source) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((size, size))
        target.parent.mkdir(parents=True, exist_ok=True)
        im.convert("RGB").save(target, "JPEG", quality=82)
