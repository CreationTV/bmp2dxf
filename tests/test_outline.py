import math

import numpy as np
from PIL import Image, ImageDraw

from bmp2dxf import ConvertOptions, convert

from tools import SAMPLES, disk_image, donut_image, render, to_png


def _convert(image: Image.Image, **options):
    return convert(to_png(image), ConvertOptions(**options))


def test_filled_disk_is_one_closed_outline():
    result = _convert(disk_image(), mode="outline", precision=85, smoothing=45)
    assert result.stats.path_count == 1
    path = result.paths[0]
    assert path.closed and path.kind == "outline"
    expected_area = math.pi * 150**2
    assert abs(abs(path.signed_area) - expected_area) / expected_area < 0.05
    assert path.length > 850


def test_donut_has_outer_outline_and_hole():
    result = _convert(donut_image(), mode="outline", precision=85, smoothing=45)
    assert result.stats.path_count == 2
    kinds = sorted(path.kind for path in result.paths)
    assert kinds == ["hole", "outline"]
    hole = next(p for p in result.paths if p.kind == "hole")
    outer = next(p for p in result.paths if p.kind == "outline")
    assert abs(abs(hole.signed_area) - math.pi * 80**2) / (math.pi * 80**2) < 0.08
    assert abs(abs(outer.signed_area) - math.pi * 170**2) / (math.pi * 170**2) < 0.05
    assert abs(hole.signed_area) < abs(outer.signed_area)


def test_nested_island_inside_hole():
    def draw(d: ImageDraw.ImageDraw, s: int) -> None:
        d.ellipse([50 * s, 50 * s, 450 * s, 450 * s], fill=0)
        d.ellipse([120 * s, 120 * s, 380 * s, 380 * s], fill=255)
        d.ellipse([200 * s, 200 * s, 300 * s, 300 * s], fill=0)

    result = _convert(render(500, 500, draw), mode="outline", precision=85, smoothing=40)
    assert result.stats.path_count == 3
    assert sum(1 for p in result.paths if p.kind == "hole") == 1
    assert sum(1 for p in result.paths if p.kind == "outline") == 2
    # The innermost island must be classified as an outline, not a hole.
    smallest = min(result.paths, key=lambda p: abs(p.signed_area))
    assert smallest.kind == "outline"


def test_text_holes_are_preserved():
    image = Image.open(SAMPLES / "text.png")
    result = convert(
        image,
        ConvertOptions(mode="outline", precision=85, smoothing=40),
    )
    assert result.stats.path_count == 8  # six outer letters + O/R counters
    assert sum(1 for p in result.paths if p.kind == "hole") == 2
    assert all(p.closed for p in result.paths)
    assert result.stats.point_count < 600


def test_logo_auto_uses_outline_and_keeps_details():
    image = Image.open(SAMPLES / "logo.png")
    result = convert(image, ConvertOptions(mode="auto", precision=85, smoothing=40))
    assert result.stats.mode_used == "outline"
    assert result.stats.path_count >= 7
    holes = [p for p in result.paths if p.kind == "hole"]
    assert len(holes) == 2  # the ring and the triangle counter
    assert all(p.closed for p in result.paths)


def test_small_holes_dropped_at_low_precision():
    def draw(d: ImageDraw.ImageDraw, s: int) -> None:
        d.ellipse([60 * s, 60 * s, 460 * s, 460 * s], fill=0)
        for radius, (cx, cy) in (
            (2, (170, 170)),
            (3, (250, 170)),
            (5, (350, 170)),
            (10, (170, 300)),
        ):
            d.ellipse(
                [
                    (cx - radius) * s,
                    (cy - radius) * s,
                    (cx + radius) * s,
                    (cy + radius) * s,
                ],
                fill=255,
            )

    image = render(540, 540, draw)
    high = _convert(image, mode="outline", precision=96)
    low = _convert(image, mode="outline", precision=25)
    assert len(high.paths) > len(low.paths)
    assert sum(1 for p in high.paths if p.kind == "hole") >= 3


def test_outline_paths_are_finite_and_closed():
    image = Image.open(SAMPLES / "logo.png")
    result = convert(image, ConvertOptions(mode="outline", precision=78))
    assert result.paths
    for path in result.paths:
        assert path.closed
        assert len(path.points) >= 3
        assert np.isfinite(path.points).all()
        assert path.length > 3
