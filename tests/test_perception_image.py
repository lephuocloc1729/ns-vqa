"""vqa/perception/image.py: orientation, RGB, native size, scale, hash. Images are
made in the test; no dataset file is read."""

import io

import pytest
from PIL import Image

from vqa.perception.image import image_hash, native_size, prepare, prepare_file


def png(w, h, mode="RGB", exif_orientation=None, colour=(200, 30, 30)):
    im = Image.new(mode, (w, h), colour if mode == "RGB" else None)
    buf = io.BytesIO()
    if exif_orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        im.save(buf, format="JPEG", exif=exif.tobytes())
    else:
        im.save(buf, format="PNG")
    return buf.getvalue()


def test_small_images_are_not_upscaled():
    p = prepare(png(700, 476))
    assert p.size == p.original_size == (700, 476) and p.scale == 1.0


@pytest.mark.parametrize("w, h", [(2496, 1402), (2425, 2560), (4000, 300), (1200, 1100)])
def test_large_images_fit_long_edge_and_area(w, h):
    nw, nh = native_size(w, h)
    assert max(nw, nh) <= 1568 and nw * nh <= 1_150_000 * 1.005
    assert abs(nw / w - nh / h) < 0.01                       # aspect ratio kept
    p = prepare(png(w, h))
    assert p.size == (nw, nh) and p.scale == pytest.approx(nw / w)


def test_exif_orientation_is_applied():
    # orientation 6: the stored 300x100 image is displayed rotated, as 100x300
    p = prepare(png(300, 100, exif_orientation=6))
    assert p.original_size == (100, 300)


def test_output_is_rgb_jpeg():
    p = prepare(png(64, 32, mode="RGBA"))
    with Image.open(io.BytesIO(p.jpeg)) as im:
        assert im.format == "JPEG" and im.mode == "RGB"
    block = p.content_block()
    assert block["type"] == "image" and block["source"]["media_type"] == "image/jpeg"


def test_hash_is_of_the_original_bytes_and_ignores_the_file_name(tmp_path):
    data = png(320, 200)
    a, b = tmp_path / "public_test_1_1.png", tmp_path / "anything_else.png"
    a.write_bytes(data)
    b.write_bytes(data)
    assert prepare_file(a).sha256 == prepare_file(b).sha256 == image_hash(data)
    assert prepare(png(320, 200, colour=(0, 0, 255))).sha256 != image_hash(data)


def test_boxes_map_back_onto_the_original():
    p = prepare(png(3136, 1000))              # sent at half size or less
    x0, y0, x1, y1 = p.to_original((100, 50, 200, 150))
    assert x0 == round(100 / p.scale) and y1 == round(150 / p.scale)
    assert p.tokens == int(p.size[0] * p.size[1] / 750) + 1
