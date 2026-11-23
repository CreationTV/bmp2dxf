import math

import numpy as np
from PIL import Image, ImageDraw

from bmp2dxf import ConvertOptions, convert
from bmp2dxf.engine import geometry

from tools import (
    SAMPLES,
    disk_image,
    line_image,
    max_distance_to_segment,
    point_segment_distance,
    render,
    to_png,
)


def _convert(image: Image.Image, **options):
    return convert(to_png(image), ConvertOptions(**options))


def test_thick_stroke_becomes_single_centerline():
    """A 24 px wide stroke must not turn into several parallel lines."""
    image = line_image(line_width=24)
    result = _convert(
        image, mode="centerline", precision=80, gap_close=6, smoothing=50
    )
    assert result.stats.mode_used == "centerline"
    assert len(result.paths) == 1, [p.length for p in result.paths]
    path = result.paths[0]
    assert not path.closed
    assert abs(path.length - math.hypot(600, 400)) < 25
    start, end = np.array([100.0, 500.0]), np.array([700.0, 100.0])
    assert min(np.linalg.norm(path.points[0] - start), np.linalg.norm(path.points[0] - end)) < 12
    assert min(np.linalg.norm(path.points[-1] - start), np.linalg.norm(path.points[-1] - end)) < 12
    assert max_distance_to_segment(path.points, start, end) < 3.0
    assert all(p.length > 100 for p in result.paths)


def test_outline_mode_of_thick_stroke_is_closed_loop():
    """Outline mode intentionally traces the silhouette (one closed loop)."""
    image = line_image(line_width=24)
    center = _convert(image, mode="centerline", precision=80, gap_close=6)
    outline = _convert(image, mode="outline", precision=80, smoothing=45)
    assert len(outline.paths) == 1
    loop = outline.paths[0]
    assert loop.closed
    assert loop.length > center.paths[0].length * 1.5
    assert loop.length < center.paths[0].length * 2.3


def test_x_crossing_is_resolved_into_two_continuous_lines():
    def draw(d: ImageDraw.ImageDraw, s: int) -> None:
        d.line([(80 * s, 620 * s), (620 * s, 80 * s)], fill=0, width=16 * s)
        d.line([(80 * s, 80 * s), (620 * s, 620 * s)], fill=0, width=16 * s)

    image = render(700, 700, draw)
    result = _convert(image, mode="centerline", precision=80, gap_close=6)
    assert result.stats.junction_count >= 1
    assert len(result.paths) == 2, [round(p.length, 1) for p in result.paths]
    center = np.array([350.0, 350.0])
    for path in result.paths:
        assert not path.closed
        assert path.length > 700
        # The straight path has only its two endpoints as vertices, so measure
        # the distance to the polyline itself rather than to the vertices.
        closest = min(
            point_segment_distance(center, a, b)
            for a, b in zip(path.points[:-1], path.points[1:])
        )
        assert closest < 4.0
        assert path.length > 60
    # No tiny connector stroke may remain in the middle of the crossing.
    assert all(p.length > 200 for p in result.paths)


def test_gap_bridging_connects_broken_line():
    def draw(d: ImageDraw.ImageDraw, s: int) -> None:
        d.line([(80 * s, 150 * s), (360 * s, 150 * s)], fill=0, width=12 * s)
        d.line([(392 * s, 150 * s), (720 * s, 150 * s)], fill=0, width=12 * s)

    image = render(800, 300, draw)
    broken = _convert(image, mode="centerline", precision=80, gap_close=0)
    assert len(broken.paths) == 2
    bridged = _convert(image, mode="centerline", precision=80, gap_close=50)
    assert len(bridged.paths) == 1
    assert bridged.stats.bridge_count >= 1
    path = bridged.paths[0]
    assert abs(path.points[0][0] - 80) < 8
    assert abs(path.points[-1][0] - 720) < 8
    assert path.length > 600


def test_dashed_line_is_joined_when_gap_bridging_enabled():
    def draw(d: ImageDraw.ImageDraw, s: int) -> None:
        for x in (60, 130, 200, 270, 340, 410):
            d.line([(x * s, 100 * s), ((x + 42) * s, 100 * s)], fill=0, width=8 * s)

    image = render(600, 200, draw)
    joined = _convert(image, mode="centerline", precision=80, gap_close=30)
    assert len(joined.paths) == 1
    assert joined.stats.bridge_count >= 4
    assert joined.paths[0].length > 350


def test_broken_crossing_bridges_along_each_line():
    """Four gap-separated arms of an X must join into two diagonals, not an H."""

    def draw(d: ImageDraw.ImageDraw, s: int) -> None:
        d.line([(80 * s, 620 * s), (330 * s, 370 * s)], fill=0, width=12 * s)
        d.line([(370 * s, 330 * s), (620 * s, 80 * s)], fill=0, width=12 * s)
        d.line([(80 * s, 80 * s), (330 * s, 330 * s)], fill=0, width=12 * s)
        d.line([(370 * s, 370 * s), (620 * s, 620 * s)], fill=0, width=12 * s)

    image = render(700, 700, draw)
    result = _convert(image, mode="centerline", precision=80, gap_close=80)
    assert result.stats.path_count == 2
    assert result.stats.bridge_count == 2
    for path in result.paths:
        a, b = path.points[0], path.points[-1]
        # Each stroke must connect two *opposite* corners of the canvas.
        assert abs(a[0] - b[0]) > 400
        assert abs(a[1] - b[1]) > 400
        assert path.length > 700


def test_t_junction_and_parallel_lines_are_not_merged():
    def draw(d: ImageDraw.ImageDraw, s: int) -> None:
        d.line([(100 * s, 300 * s), (700 * s, 300 * s)], fill=0, width=12 * s)
        d.line([(400 * s, 300 * s), (400 * s, 640 * s)], fill=0, width=12 * s)
        d.line([(100 * s, 180 * s), (700 * s, 180 * s)], fill=0, width=8 * s)
        d.line([(100 * s, 210 * s), (700 * s, 210 * s)], fill=0, width=8 * s)

    image = render(800, 700, draw)
    result = _convert(image, mode="centerline", precision=80, gap_close=40)
    assert result.stats.path_count == 4
    assert result.stats.bridge_count == 0
    lengths = sorted(p.length for p in result.paths)
    assert abs(lengths[0] - 340) < 40  # the vertical T branch
    assert sum(1 for p in result.paths if p.length > 550) >= 3


def test_closed_ring_stays_one_closed_centerline():
    image = disk_image(fill=False, outline_width=6)
    result = _convert(image, mode="centerline", precision=80, gap_close=5, smoothing=55)
    assert len(result.paths) == 1
    path = result.paths[0]
    assert path.closed
    assert not result.paths_by_kind("hole")
    expected = 2 * math.pi * 147.0
    assert abs(path.length - expected) / expected < 0.05
    assert path.points.shape[0] > 12


def test_auto_mode_chooses_centerline_for_strokes_and_outline_for_disk():
    line = _convert(line_image(), mode="auto", precision=80)
    assert line.stats.mode_used == "centerline"
    disk = _convert(disk_image(), mode="auto", precision=80)
    assert disk.stats.mode_used == "outline"
    assert len(disk.paths) == 1 and disk.paths[0].closed


def test_centerline_mode_warns_on_filled_blob():
    result = _convert(disk_image(), mode="centerline", precision=80)
    assert any("实心" in warning for warning in result.warnings)


def test_precision_dial_increases_detail():
    image = disk_image(fill=False, outline_width=6)
    low = _convert(image, mode="centerline", precision=35, gap_close=5)
    high = _convert(image, mode="centerline", precision=98, gap_close=5)
    assert high.stats.point_count > low.stats.point_count
    assert high.stats.simplify_px < low.stats.simplify_px


def test_small_details_survive_at_high_precision():
    def draw(d: ImageDraw.ImageDraw, s: int) -> None:
        d.line([(40 * s, 60 * s), (660 * s, 60 * s)], fill=0, width=6 * s)
        for radius in (4, 6, 10, 16):
            cx = 120 + radius * 2 + 30
            d.ellipse(
                [
                    (cx - radius) * s,
                    (250 - radius) * s,
                    (cx + radius) * s,
                    (250 + radius) * s,
                ],
                outline=0,
                width=3 * s,
            )

    image = render(700, 400, draw)
    high = _convert(image, mode="outline", precision=95)
    low = _convert(image, mode="outline", precision=20)
    assert len(high.paths) > len(low.paths)
    assert len(high.paths) >= 5


def test_thin_line_is_not_lost():
    image = line_image(width=640, height=480, start=(40, 240), end=(600, 240), line_width=2)
    result = _convert(image, mode="centerline", precision=85, gap_close=6)
    assert len(result.paths) == 1
    assert result.paths[0].length > 540


def test_sample_mechanical_is_processed_cleanly():
    image = Image.open(SAMPLES / "mechanical.png")
    result = _convert(image, mode="centerline", precision=82, gap_close=16, smoothing=55)
    assert result.stats.path_count > 15
    assert result.stats.closed_path_count >= 8  # circles and small holes
    assert result.stats.path_count < 60
    assert result.stats.point_count < 1000
    for path in result.paths:
        assert np.isfinite(path.points).all()
        assert path.length > 1.0
