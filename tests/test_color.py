"""Colour-painted artwork: internal region boundaries must survive."""

from __future__ import annotations

import numpy as np
from PIL import Image

from bmp2dxf import ConvertOptions, convert
from bmp2dxf.engine import color as color_engine
from bmp2dxf.engine.image_io import load_image
from bmp2dxf.engine.preprocess import prepare

from tools import (
    color_art_image,
    color_ink_image,
    disk_image,
    line_image,
    photo_like_image,
    to_png,
)


def _convert(image: Image.Image, **options):
    return convert(to_png(image), ConvertOptions(**options))


def test_rgb_is_preserved_for_colour_input():
    image = color_art_image(400, 260)
    loaded = load_image(to_png(image))
    assert loaded.rgb is not None
    assert loaded.rgb.shape == (260, 400, 3)
    assert loaded.rgb.dtype == np.uint8

    gray = load_image(to_png(line_image(width=200, height=120)))
    assert gray.rgb is None


def test_prepare_keeps_colour_at_working_resolution():
    image = color_art_image(500, 320)
    options = ConvertOptions(mode="color", precision=60)
    path = to_png(image)
    loaded = load_image(path)
    prepared = prepare(path, options, loaded=loaded)
    assert prepared.rgb is not None
    assert prepared.rgb.shape == prepared.mask.shape + (3,)


def test_flat_colour_art_auto_selects_colour_mode():
    image = color_art_image()
    result = _convert(image, precision=70)
    assert result.stats.mode_used == "color"
    assert result.stats.path_count >= 4
    assert all(path.kind == "outline" for path in result.paths)
    assert all(path.layer == "OUTLINE" for path in result.paths)
    # The boundary between the touching red and blue rectangles is not part of
    # the outer silhouette; it must still be present.
    internal = [
        path
        for path in result.paths
        if not path.closed
        and abs(float(path.points[:, 0].min()) - float(path.points[:, 0].max())) < 3
        and float(path.points[:, 1].max()) - float(path.points[:, 1].min()) > 100
    ]
    assert internal, [path.points.tolist() for path in result.paths]


def test_explicit_colour_mode_matches_auto_for_colour_art():
    image = color_art_image()
    auto = _convert(image, precision=70)
    explicit = _convert(image, mode="color", precision=70)
    assert explicit.stats.mode_used == "color"
    assert len(explicit.paths) == len(auto.paths)
    assert explicit.stats.point_count == auto.stats.point_count


def test_photo_is_not_automatically_treated_as_colour_art():
    image = photo_like_image()
    rgb = np.asarray(image.convert("RGB"))
    assert color_engine.probe_color(rgb) is False
    result = _convert(image, precision=70)
    assert result.stats.mode_used != "color"


def test_colour_mode_falls_back_to_outline_for_grayscale_input():
    image = line_image(
        width=400, height=240, start=(40, 200), end=(360, 40), line_width=14
    )
    result = _convert(image, mode="color", precision=70)
    assert result.stats.mode_used == "outline"
    assert result.paths
    assert any("彩色" in warning or "回退" in warning for warning in result.warnings)


def test_black_ink_inside_colour_art_does_not_create_duplicate_lines():
    image = color_ink_image()
    result = _convert(image, mode="color", precision=70)
    assert result.stats.mode_used == "color"
    # One line per ink stroke/colour boundary; no short fragments around the
    # anti-aliased edge of the black outlines.
    assert len(result.paths) == 3, [round(path.length, 1) for path in result.paths]
    assert all(path.length > 50 for path in result.paths)


def test_grayscale_modes_are_unchanged_by_colour_support():
    line = _convert(line_image(width=300, height=180, line_width=16), precision=70)
    assert line.stats.mode_used == "centerline"

    disk = _convert(disk_image(300, 300, bbox=(50, 50, 250, 250)), precision=70)
    assert disk.stats.mode_used == "outline"
