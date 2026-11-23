"""Generate ready-to-inspect DXF examples and README preview images.

Run with the project virtual environment::

    .\\.venv\\Scripts\\python.exe scripts\\make_examples.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from bmp2dxf import ConvertOptions, convert
from bmp2dxf.export.dxf import to_dxf_bytes


ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
IMAGES = ROOT / "docs" / "images"


JOBS = [
    (
        "mechanical_centerline",
        "samples/mechanical.png",
        ConvertOptions(
            mode="centerline", precision=82, gap_close=16, smoothing=55
        ),
        "机械线稿：粗线条单线化、交叉口连续、断线桥接",
    ),
    (
        "logo_outline",
        "samples/logo.png",
        ConvertOptions(mode="outline", precision=85, smoothing=40),
        "图标/标志：轮廓 + 孔洞保留",
    ),
    (
        "text_outline",
        "samples/text.png",
        ConvertOptions(mode="outline", precision=85, smoothing=40),
        "文字轮廓：保留 O/R 的内孔",
    ),
    (
        "sketch_scan_centerline",
        "samples/sketch_scan.jpg",
        ConvertOptions(
            mode="auto", precision=80, gap_close=10, smoothing=55
        ),
        "扫描手绘稿：自动局部阈值 + 中心线",
    ),
]


def render_overlay(image: Image.Image, result, target: Path) -> None:
    rgb = image.convert("RGB").copy()
    draw = ImageDraw.Draw(rgb)
    width = max(2, int(round(min(rgb.size) / 450)))
    for path in result.paths:
        points = [(float(x), float(y)) for x, y in path.points]
        if path.kind == "centerline":
            color = (228, 40, 40)
        elif path.kind == "hole":
            color = (206, 40, 190)
        else:
            color = (24, 112, 230)
        if path.closed:
            points = points + [points[0]]
        draw.line(points, fill=color, width=width)
    target.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(target)


def main() -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    IMAGES.mkdir(parents=True, exist_ok=True)
    print(f"{'name':26s} {'paths':>6s} {'points':>7s} {'mm':>9s} {'dxf KB':>8s}")
    for name, source_rel, options, _note in JOBS:
        source = ROOT / source_rel
        raw = source.read_bytes()
        result = convert(raw, options)
        dxf = to_dxf_bytes(
            result,
            dpi=float(options.dpi),
            version=str(options.dxf_version),
        )
        dxf_path = EXAMPLES / f"{name}.dxf"
        dxf_path.write_bytes(dxf)
        image = Image.open(source)
        render_overlay(image, result, IMAGES / f"{name}_overlay.png")
        stats = result.stats
        print(
            f"{name:26s} {stats.path_count:6d} {stats.point_count:7d} "
            f"{stats.total_length_mm:9.1f} {len(dxf) / 1024:8.1f}"
        )
        for warning in result.warnings:
            print(f"  warning: {warning}")


if __name__ == "__main__":
    main()
