import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from bmp2dxf import ConvertOptions, convert
from bmp2dxf.pipeline import convert_many

from tools import disk_image, line_image, to_png


def _formats_image() -> Image.Image:
    image = Image.new("RGB", (360, 240), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.line([(40, 200), (320, 40)], fill=(0, 0, 0), width=10)
    draw.ellipse([(80, 80), (160, 160)], outline=(0, 0, 0), width=5)
    return image


@pytest.mark.parametrize(
    "fmt, mime",
    [
        ("PNG", "PNG"),
        ("JPEG", "JPEG"),
        ("WEBP", "WEBP"),
        ("BMP", "BMP"),
        ("TIFF", "TIFF"),
    ],
)
def test_common_bitmap_formats(fmt, mime):
    image = _formats_image()
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    result = convert(
        buffer.getvalue(),
        ConvertOptions(mode="centerline", precision=70),
    )
    assert result.image_format == mime
    assert result.stats.path_count >= 2
    assert result.source_width == 360
    assert result.source_height == 240


def test_palette_and_rgba_images_load():
    rgba = Image.new("RGBA", (300, 200), (255, 255, 255, 0))
    draw = ImageDraw.Draw(rgba)
    draw.line([(30, 170), (270, 30)], fill=(0, 0, 0, 255), width=8)
    result = convert(to_png(rgba), ConvertOptions(mode="centerline", precision=70))
    assert result.stats.path_count == 1
    assert result.stats.inverted is False

    palette = rgba.convert("P")
    result2 = convert(to_png(palette), ConvertOptions(mode="auto", precision=70))
    assert result2.stats.path_count >= 1


def test_white_on_black_is_auto_inverted():
    image = Image.new("L", (600, 400), 0)
    draw = ImageDraw.Draw(image)
    draw.line([(60, 340), (540, 60)], fill=255, width=12)
    result = convert(to_png(image), ConvertOptions(mode="centerline", precision=80))
    assert result.stats.inverted is True
    assert result.stats.path_count == 1
    assert result.paths[0].length > 350

    forced = convert(
        to_png(image),
        ConvertOptions(mode="centerline", precision=80, invert="no"),
    )
    assert forced.stats.inverted is False


def test_blank_image_returns_empty_result_with_warning():
    image = Image.new("L", (320, 240), 255)
    result = convert(to_png(image), ConvertOptions(mode="auto"))
    assert result.stats.path_count == 0
    assert result.paths == []
    assert result.warnings
    assert any("前景" in warning or "空白" in warning for warning in result.warnings)


def test_invalid_image_raises_value_error():
    with pytest.raises(ValueError):
        convert(b"this is definitely not an image")
    with pytest.raises(ValueError):
        convert(b"")


def test_stats_are_consistent():
    result = convert(
        to_png(line_image()), ConvertOptions(mode="centerline", precision=80)
    )
    stats = result.stats
    assert stats.path_count == len(result.paths)
    assert stats.point_count == sum(len(p.points) for p in result.paths)
    assert stats.total_length_px == pytest.approx(
        sum(p.length for p in result.paths)
    )
    assert stats.closed_path_count == sum(1 for p in result.paths if p.closed)
    assert stats.duration_ms > 0
    assert stats.source_width == 800 and stats.source_height == 600
    assert stats.mode_used == "centerline"
    assert stats.output_width_mm == pytest.approx(800 * 25.4 / 96)
    assert stats.output_height_mm == pytest.approx(600 * 25.4 / 96)


def test_dpi_only_affects_output_scale():
    image = to_png(line_image())
    a = convert(image, ConvertOptions(mode="centerline", precision=80, dpi=96))
    b = convert(image, ConvertOptions(mode="centerline", precision=80, dpi=192))
    assert a.stats.total_length_px == pytest.approx(b.stats.total_length_px, rel=1e-6)
    assert a.stats.total_length_mm == pytest.approx(
        b.stats.total_length_mm * 2.0, rel=1e-3
    )
    assert a.stats.mm_per_px == pytest.approx(b.stats.mm_per_px * 2.0)


def test_paths_stay_inside_source_bounds():
    image = io.BytesIO()
    Image.open(Path("samples/mechanical.png")).save(image, format="PNG")
    result = convert(image.getvalue(), ConvertOptions(mode="centerline", precision=82))
    assert result.paths
    all_points = np.vstack([p.points for p in result.paths])
    assert all_points[:, 0].min() >= -2
    assert all_points[:, 1].min() >= -2
    assert all_points[:, 0].max() <= result.stats.source_width + 2
    assert all_points[:, 1].max() <= result.stats.source_height + 2


def test_precision_increases_point_count():
    image = to_png(disk_image(fill=False, outline_width=6))
    low = convert(
        image, ConvertOptions(mode="centerline", precision=25, gap_close=4)
    )
    high = convert(
        image, ConvertOptions(mode="centerline", precision=95, gap_close=4)
    )
    assert high.stats.point_count > low.stats.point_count
    assert low.stats.path_count == 1 and high.stats.path_count == 1


def test_convert_accepts_pil_bytes_and_path(tmp_path):
    pil = line_image()
    from_pil = convert(pil, ConvertOptions(mode="centerline", precision=70))
    from_bytes = convert(to_png(pil), ConvertOptions(mode="centerline", precision=70))
    path = tmp_path / "line.png"
    path.write_bytes(to_png(pil))
    from_path = convert(path, ConvertOptions(mode="centerline", precision=70))
    for result in (from_pil, from_bytes, from_path):
        assert result.stats.path_count == 1


def test_options_validation():
    with pytest.raises(ValueError):
        ConvertOptions(mode="nope")
    with pytest.raises(ValueError):
        ConvertOptions(threshold_method="manual")
    with pytest.raises(ValueError):
        ConvertOptions(dxf_version="R9999")
    options = ConvertOptions.from_dict(
        {"mode": "outline", "precision": "88", "unknown": 5}
    )
    assert options.mode == "outline" and options.precision == 88
    assert ConvertOptions(precision=150).precision == 100
    assert ConvertOptions(gap_close=-4).gap_close == 0


def test_convert_many():
    results = convert_many(
        [to_png(line_image()), to_png(disk_image())],
        ConvertOptions(mode="auto", precision=70),
    )
    assert len(results) == 2
