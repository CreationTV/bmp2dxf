"""Public data model of the bitmap -> DXF converter.

All :class:`VectorPath` coordinates are expressed in **source image pixels**
(origin top-left, x to the right, y downwards), regardless of any internal
resampling performed by the conversion pipeline.  Exporters are responsible
for converting them to their target coordinate system (DXF uses millimetres
and a Y axis pointing upwards).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np


LAYER_FOR_KIND = {
    "centerline": "CENTERLINE",
    "outline": "OUTLINE",
    "hole": "OUTLINE",
}


@dataclass
class VectorPath:
    """One polyline of the vector result.

    Attributes
    ----------
    points:
        ``(N, 2)`` array of ``(x, y)`` source-pixel coordinates.
    closed:
        Whether the first and the last point are implicitly connected.
    kind:
        ``"centerline"``, ``"outline"`` or ``"hole"``.
    """

    points: np.ndarray
    closed: bool = False
    kind: str = "centerline"

    def __post_init__(self) -> None:
        pts = np.asarray(self.points, dtype=np.float64)
        if pts.ndim != 2 or pts.shape[1] != 2:
            raise ValueError(f"points must have shape (N, 2), got {pts.shape}")
        if pts.shape[0] < 2:
            raise ValueError("a path needs at least two points")
        if not np.isfinite(pts).all():
            raise ValueError("path contains non-finite coordinates")
        self.points = np.ascontiguousarray(pts, dtype=np.float64)

    @property
    def layer(self) -> str:
        return LAYER_FOR_KIND.get(self.kind, "OUTLINE")

    @property
    def length(self) -> float:
        pts = self.points
        if len(pts) < 2:
            return 0.0
        segment = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        total = float(segment.sum())
        if self.closed:
            total += float(np.linalg.norm(pts[0] - pts[-1]))
        return total

    @property
    def signed_area(self) -> float:
        """Shoelace area (positive for counter-clockwise in image coordinates)."""
        pts = self.points
        x, y = pts[:, 0], pts[:, 1]
        return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

    def copy(self) -> "VectorPath":
        return VectorPath(self.points.copy(), self.closed, self.kind)

    def transformed(self, matrix: np.ndarray) -> "VectorPath":
        pts = np.asarray(matrix, dtype=np.float64) @ np.column_stack(
            (self.points, np.ones(len(self.points)))
        ).T
        return VectorPath(pts.T, self.closed, self.kind)

    def to_dict(self, ndigits: int = 4) -> dict[str, Any]:
        pts = np.round(self.points, ndigits).tolist()
        return {"points": pts, "closed": bool(self.closed), "kind": self.kind}


@dataclass
class ConversionStats:
    source_width: int = 0
    source_height: int = 0
    work_width: int = 0
    work_height: int = 0
    work_scale: float = 1.0

    mode_requested: str = "auto"
    mode_used: str = "auto"
    auto_reason: str = ""
    threshold: float = 0.0
    threshold_method: str = "otsu"
    inverted: bool = False

    path_count: int = 0
    point_count: int = 0
    total_length_px: float = 0.0
    total_length_mm: float = 0.0
    closed_path_count: int = 0

    junction_count: int = 0
    bridge_count: int = 0
    spur_prune_count: int = 0
    duplicate_removed: int = 0

    mm_per_px: float = 25.4 / 96.0
    output_width_mm: float = 0.0
    output_height_mm: float = 0.0
    min_feature_px: float = 0.0
    simplify_px: float = 0.0
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_width": self.source_width,
            "source_height": self.source_height,
            "work_width": self.work_width,
            "work_height": self.work_height,
            "work_scale": round(self.work_scale, 4),
            "mode_requested": self.mode_requested,
            "mode_used": self.mode_used,
            "auto_reason": self.auto_reason,
            "threshold": round(self.threshold, 2),
            "threshold_method": self.threshold_method,
            "inverted": bool(self.inverted),
            "path_count": self.path_count,
            "point_count": self.point_count,
            "total_length_px": round(self.total_length_px, 2),
            "total_length_mm": round(self.total_length_mm, 2),
            "closed_path_count": self.closed_path_count,
            "junction_count": self.junction_count,
            "bridge_count": self.bridge_count,
            "spur_prune_count": self.spur_prune_count,
            "duplicate_removed": self.duplicate_removed,
            "mm_per_px": round(self.mm_per_px, 6),
            "output_width_mm": round(self.output_width_mm, 2),
            "output_height_mm": round(self.output_height_mm, 2),
            "min_feature_px": round(self.min_feature_px, 2),
            "simplify_px": round(self.simplify_px, 2),
            "duration_ms": round(self.duration_ms, 1),
        }


@dataclass
class ConversionResult:
    """Result of one conversion."""

    paths: list[VectorPath] = field(default_factory=list)
    stats: ConversionStats = field(default_factory=ConversionStats)
    warnings: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    image_format: str = ""
    source_width: int = 0
    source_height: int = 0

    @property
    def width(self) -> int:
        return self.source_width

    @property
    def height(self) -> int:
        return self.source_height

    def __len__(self) -> int:
        return len(self.paths)

    def __iter__(self) -> Iterable[VectorPath]:
        return iter(self.paths)

    def paths_by_kind(self, kind: str) -> list[VectorPath]:
        return [p for p in self.paths if p.kind == kind]

    def bbox(self) -> tuple[float, float, float, float] | None:
        """Bounding box in source pixels: ``(min_x, min_y, max_x, max_y)``."""
        if not self.paths:
            return None
        all_pts = np.concatenate([p.points for p in self.paths], axis=0)
        return (
            float(all_pts[:, 0].min()),
            float(all_pts[:, 1].min()),
            float(all_pts[:, 0].max()),
            float(all_pts[:, 1].max()),
        )

    def to_dict(self, include_paths: bool = False) -> dict[str, Any]:
        data = {
            "stats": self.stats.to_dict(),
            "warnings": list(self.warnings),
            "options": dict(self.options),
            "image_format": self.image_format,
            "source_width": self.source_width,
            "source_height": self.source_height,
        }
        if include_paths:
            data["paths"] = [p.to_dict() for p in self.paths]
        return data
