"""Outline tracing for logos, icons and filled artwork."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from skimage import measure

from ..config import ConvertOptions, Tuning
from ..models import VectorPath
from . import geometry
from .preprocess import PreparedImage


PAD = 2


@dataclass
class OutlineResult:
    paths: list[VectorPath] = field(default_factory=list)  # work coordinates
    outer_count: int = 0
    hole_count: int = 0
    warnings: list[str] = field(default_factory=list)


def _signed_area_xy(points: np.ndarray) -> float:
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 3:
        return 0.0
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _find_raw_contours(
    prepared: PreparedImage, options: ConvertOptions
) -> tuple[list[np.ndarray], bool]:
    """Return contours in work pixel coordinates and whether foreground is high.

    For global/manual thresholds the grayscale image is contoured at the
    threshold value, which produces sub-pixel accurate edges on anti-aliased
    artwork.  For adaptive thresholds a single global level does not exist, so
    the binary mask is contoured instead.
    """
    if (
        prepared.threshold_method in ("otsu", "manual")
        and 0.5 < prepared.threshold < 254.5
    ):
        source = prepared.gray.astype(np.float32)
        padded = np.pad(source, PAD, mode="constant", constant_values=255.0)
        level = float(prepared.threshold)
        try:
            raw = measure.find_contours(
                padded, level, fully_connected="high", positive_orientation="low"
            )
        except TypeError:  # older scikit-image
            raw = measure.find_contours(padded, level)
        return [c - PAD for c in raw], False

    source = prepared.mask.astype(np.float32)
    padded = np.pad(source, PAD, mode="constant", constant_values=0.0)
    try:
        raw = measure.find_contours(
            padded, 0.5, fully_connected="high", positive_orientation="high"
        )
    except TypeError:  # older scikit-image
        raw = measure.find_contours(padded, 0.5)
    return [c - PAD for c in raw], True


def extract_outlines(
    prepared: PreparedImage,
    tuning: Tuning,
    options: ConvertOptions,
) -> OutlineResult:
    raw_contours, foreground_is_high = _find_raw_contours(prepared, options)
    if not raw_contours:
        return OutlineResult(warnings=["没有找到可转换的轮廓。"])

    work_h, work_w = prepared.mask.shape
    paths: list[VectorPath] = []
    outer_count = 0
    hole_count = 0
    warnings: list[str] = []

    # The orientation convention differs between skimage versions and value
    # polarities.  The largest contour is always an outer boundary; every
    # contour with the same winding direction is an outer, the opposite
    # winding ones are holes (even-odd nesting).
    signed_areas = []
    for raw in raw_contours:
        if len(raw) < 4:
            signed_areas.append(0.0)
            continue
        xy = np.column_stack([raw[:, 1], raw[:, 0]]).astype(np.float64)
        signed_areas.append(_signed_area_xy(xy))
    outer_sign = 1.0
    if signed_areas:
        largest = int(np.argmax(np.abs(signed_areas)))
        outer_sign = 1.0 if signed_areas[largest] >= 0 else -1.0

    for raw, area_signed in zip(raw_contours, signed_areas):
        if len(raw) < 4:
            continue
        # (row, col) -> (x, y)
        xy = np.column_stack([raw[:, 1], raw[:, 0]]).astype(np.float64)
        # Keep only contours inside the image proper; padding guarantees a
        # closed loop in almost all cases.
        if not np.isfinite(xy).all():
            continue
        area = abs(area_signed)
        if area < max(1.0, tuning.min_area_px * 0.8):
            continue
        is_hole = (area_signed * outer_sign) < 0
        if is_hole and area < tuning.min_area_px * 1.1:
            continue
        simplified = geometry.smooth_polyline(
            xy,
            closed=True,
            epsilon=tuning.simplify_px,
            smoothing_iters=tuning.smoothing_iters,
            corner_angle_deg=options.corner_angle,
        )
        if len(simplified) < 3:
            continue
        final_area = geometry.polygon_area(simplified)
        if final_area < tuning.min_area_px * 0.7:
            continue
        path = VectorPath(
            simplified, closed=True, kind="hole" if is_hole else "outline"
        )
        paths.append(path)
        if is_hole:
            hole_count += 1
        else:
            outer_count += 1

    if not paths:
        warnings.append("轮廓都小于最小细节尺寸；请提高精度或降低最小细节。")

    # Draw large shapes first (nice for SVG preview and stable DXF order).
    paths.sort(key=lambda p: abs(p.signed_area), reverse=True)
    return OutlineResult(
        paths=paths,
        outer_count=outer_count,
        hole_count=hole_count,
        warnings=warnings,
    )
