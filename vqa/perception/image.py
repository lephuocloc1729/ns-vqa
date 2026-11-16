"""Image prep for the scene call (docs/plans/phase-3.md, item 3).

- EXIF orientation is applied, the image is converted to RGB, and it is resized so
  the long edge is at most 1568 px and the area at most about 1.15 MP. It is never
  upscaled. This is the model's native size, so pixel boxes in a reply map straight
  back onto the image (DESIGN.md, coordinates guide).
- The scale factor is kept, so a box on the sent image maps back onto the original.
- The image hash is the sha256 of the original file's bytes. It is the scene
  cache's image key. The file name is never used: callers pass bytes.
"""

from __future__ import annotations

import base64
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

LONG_EDGE = 1568
MAX_PIXELS = 1_150_000
JPEG_QUALITY = 90
PREP_VERSION = "img1"   # part of a prompt version's config: change it if the prep changes


def native_size(w: int, h: int) -> tuple[int, int]:
    """The size an image of w x h is sent at: long edge <= 1568, area <= ~1.15 MP,
    never upscaled."""
    s = min(1.0, LONG_EDGE / max(w, h), (MAX_PIXELS / (w * h)) ** 0.5)
    return max(1, round(w * s)), max(1, round(h * s))


def image_hash(data: bytes) -> str:
    """sha256 of the original file's bytes (the scene cache's image key)."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class PreparedImage:
    sha256: str                     # of the original bytes
    original_size: tuple[int, int]  # after EXIF orientation
    size: tuple[int, int]           # as sent
    scale: float                    # size / original_size, the same on both axes
    jpeg: bytes                     # the image as sent

    @property
    def tokens(self) -> int:
        """Approximate image tokens: width x height / 750."""
        return int(self.size[0] * self.size[1] / 750) + 1

    def content_block(self) -> dict:
        """The image as an API content block."""
        return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": base64.b64encode(self.jpeg).decode("ascii")}}

    def to_original(self, box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        """A pixel box (x0, y0, x1, y1) on the sent image, mapped onto the original."""
        return tuple(round(v / self.scale) for v in box)  # type: ignore[return-value]


def prepare(data: bytes) -> PreparedImage:
    """Prepare an image's bytes for the scene call."""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        ow, oh = im.size
        nw, nh = native_size(ow, oh)
        if (nw, nh) != (ow, oh):
            im = im.resize((nw, nh), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return PreparedImage(sha256=image_hash(data), original_size=(ow, oh), size=(nw, nh),
                         scale=nw / ow, jpeg=buf.getvalue())


def prepare_file(path: str | Path) -> PreparedImage:
    """prepare() on a file's bytes; the name plays no part."""
    return prepare(Path(path).read_bytes())
