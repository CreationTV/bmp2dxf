"""Shared helpers for the test-suite (not collected by pytest)."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


def render(
    width: int,
    height: int,
    draw_fn,
    scale: int = 3,
    background: int = 255,
) -> Image.Image:
    """Draw at ``scale`` and downsample, yielding anti-aliased grayscale art."""
    image = Image.new("L", (width * scale, height * scale), background)
    draw = ImageDraw.Draw(image)
    draw_fn(draw, scale)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def line_image(
    width: int = 800,
    height: int = 600,
    start=(100, 500),
    end=(700, 100),
    line_width: int = 24,
    background: int = 255,
) -> Image.Image:
    def draw(d: ImageDraw.ImageDraw, s: int) -> None:
        d.line(
            [(start[0] * s, start[1] * s), (end[0] * s, end[1] * s)],
            fill=0,
            width=line_width * s,
        )

    return render(width, height, draw, background=background)


def disk_image(
    width: int = 500,
    height: int = 500,
    bbox=None,
    fill: bool = True,
    outline_width: int = 0,
    background: int = 255,
) -> Image.Image:
    bbox = bbox or (100, 100, 400, 400)

    def draw(d: ImageDraw.ImageDraw, s: int) -> None:
        scaled = [int(v * s) for v in bbox]
        if fill:
            d.ellipse(scaled, fill=0)
        else:
            d.ellipse(scaled, outline=0, width=max(1, outline_width * s))

    return render(width, height, draw, background=background)


def donut_image(
    width: int = 500, height: int = 500, outer=(80, 80, 420, 420), inner=(170, 170, 330, 330)
) -> Image.Image:
    def draw(d: ImageDraw.ImageDraw, s: int) -> None:
        d.ellipse([int(v * s) for v in outer], fill=0)
        d.ellipse([int(v * s) for v in inner], fill=255)

    return render(width, height, draw)


def color_art_image(width: int = 600, height: int = 400) -> Image.Image:
    """Flat colour blocks with adjacent fills, similar to a painted sketch."""
    scale = 3
    image = Image.new("RGB", (width * scale, height * scale), "white")
    draw = ImageDraw.Draw(image)
    red = (214, 72, 58)
    blue = (60, 120, 190)
    green = (70, 145, 92)
    yellow = (236, 176, 45)
    draw.rectangle(
        [40 * scale, 40 * scale, 300 * scale, 185 * scale], fill=red
    )
    draw.rectangle(
        [300 * scale, 40 * scale, 560 * scale, 185 * scale], fill=blue
    )
    draw.rectangle(
        [40 * scale, 205 * scale, 280 * scale, 360 * scale], fill=green
    )
    draw.ellipse(
        [330 * scale, 215 * scale, 520 * scale, 360 * scale], fill=yellow
    )
    return image.resize((width, height), Image.Resampling.LANCZOS)


def color_ink_image(width: int = 500, height: int = 380) -> Image.Image:
    """Colour fills with black ink outlines, as in a marker drawing."""
    scale = 3
    image = Image.new("RGB", (width * scale, height * scale), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        [70 * scale, 55 * scale, 290 * scale, 220 * scale],
        fill=(210, 80, 55),
        outline=0,
        width=5 * scale,
    )
    draw.ellipse(
        [310 * scale, 120 * scale, 450 * scale, 300 * scale],
        fill=(80, 145, 190),
        outline=0,
        width=5 * scale,
    )
    draw.line(
        [(60 * scale, 310 * scale), (450 * scale, 310 * scale)],
        fill=0,
        width=5 * scale,
    )
    return image.resize((width, height), Image.Resampling.LANCZOS)


def photo_like_image(width: int = 320, height: int = 240) -> Image.Image:
    """A smooth gradient with noise: high chroma but not flat colour art."""
    rng = np.random.default_rng(7)
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    red = 170.0 + 60.0 * xx + 18.0 * np.sin(xx * 8.0)
    green = 110.0 + 80.0 * yy + 18.0 * np.cos(yy * 5.0)
    blue = 80.0 + 90.0 * xx * yy
    array = np.dstack([red, green, blue])
    array += rng.normal(0.0, 10.0, array.shape)
    array = np.clip(array, 0, 255).astype(np.uint8)
    return Image.fromarray(array, mode="RGB").filter(ImageFilter.GaussianBlur(0.9))


def point_segment_distance(point, start, end) -> float:
    point = np.asarray(point, dtype=float)
    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    ab = end - start
    denom = float(np.dot(ab, ab))
    if denom <= 1e-12:
        return float(np.linalg.norm(point - start))
    t = float(np.clip(np.dot(point - start, ab) / denom, 0.0, 1.0))
    return float(np.linalg.norm(point - (start + t * ab)))


def max_distance_to_segment(points: np.ndarray, start, end) -> float:
    return max(
        point_segment_distance(point, start, end) for point in np.asarray(points)
    )


def assert_close(a: float, b: float, tolerance: float = 1e-6) -> None:
    assert abs(a - b) <= tolerance, f"{a} != {b} (tolerance {tolerance})"
