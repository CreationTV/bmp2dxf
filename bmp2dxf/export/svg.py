"""SVG preview/export of the vector result."""

from __future__ import annotations

from html import escape
from typing import Mapping

from ..models import ConversionResult


DEFAULT_COLORS = {
    "centerline": "#38bdf8",
    "outline": "#fb923c",
    "hole": "#f472b6",
}


def _path_data(points, closed: bool, ndigits: int) -> str:
    if len(points) < 2:
        return ""
    first = points[0]
    parts = [f"M{first[0]:.{ndigits}f} {first[1]:.{ndigits}f}"]
    for x, y in points[1:]:
        parts.append(f"L{x:.{ndigits}f} {y:.{ndigits}f}")
    if closed:
        parts.append("Z")
    return " ".join(parts)


def to_svg(
    result: ConversionResult,
    *,
    colors: Mapping[str, str] | None = None,
    stroke_width: float | None = None,
    background: str | None = None,
    non_scaling_stroke: bool = True,
    title: str = "bmp2dxf",
) -> str:
    """Render the vector paths as a standalone SVG document.

    The viewBox uses source-image pixel coordinates, which makes the SVG a
    perfect overlay for the original bitmap.
    """
    colors = {**DEFAULT_COLORS, **(colors or {})}
    width = result.source_width or result.stats.source_width or 1
    height = result.source_height or result.stats.source_height or 1
    if stroke_width is None:
        # Preview stroke width in source pixels.  With non-scaling strokes this
        # stays comfortable on screen regardless of how large the bitmap is.
        stroke_width = max(1.2, min(width, height) / 300.0)

    groups: dict[str, list[str]] = {"centerline": [], "outline": [], "hole": []}
    for path in result.paths:
        d = _path_data(path.points, path.closed, 2)
        if d:
            groups.setdefault(path.kind, []).append(d)

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'preserveAspectRatio="xMidYMid meet">'
        ),
        f"<title>{escape(title)}</title>",
    ]
    if background:
        parts.append(
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="{background}"/>'
        )
    parts.append('<g fill="none" stroke-linecap="round" stroke-linejoin="round">')
    for kind in ("outline", "hole", "centerline"):
        if not groups.get(kind):
            continue
        color = colors.get(kind, "#ffffff")
        # Holes use a dashed style in previews so they are distinguishable.
        dash = ' stroke-dasharray="6 4"' if kind == "hole" else ""
        parts.append(
            f'<g fill="none" stroke="{color}" stroke-width="{stroke_width:g}"'
            f' data-kind="{kind}"{dash}>'
        )
        for d in groups[kind]:
            effect = ' vector-effect="non-scaling-stroke"' if non_scaling_stroke else ""
            parts.append(f'<path d="{d}"{effect}/>')
        parts.append("</g>")
    parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts)
