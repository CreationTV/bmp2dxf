"""DXF export with millimetre units, layers and closed polylines."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import ezdxf
import numpy as np

from ..config import VALID_DXF_VERSIONS
from ..models import ConversionResult, VectorPath


LAYER_COLORS = {
    "CENTERLINE": 4,  # cyan
    "OUTLINE": 7,  # white / black depending on background
}


def _resolve_settings(
    result: ConversionResult,
    dpi: float | None,
    version: str | None,
) -> tuple[float, str]:
    options = result.options or {}
    if dpi is None:
        dpi = float(options.get("dpi", 96.0) or 96.0)
    dpi = max(10.0, float(dpi))
    if version is None:
        version = str(options.get("dxf_version", "R2000"))
    version = version.upper()
    if version not in VALID_DXF_VERSIONS:
        version = "R2000"
    return dpi, version


def _to_dxf_points(path: VectorPath, height: float, mm_per_px: float) -> np.ndarray:
    pts = path.points.copy()
    # DXF has a Y axis pointing up; image pixels point down.
    pts[:, 0] = pts[:, 0] * mm_per_px
    pts[:, 1] = (height - pts[:, 1]) * mm_per_px
    if path.closed and len(pts) > 1 and np.allclose(pts[0], pts[-1], atol=1e-9):
        pts = pts[:-1]
    return np.round(pts, 5)


def build_document(
    result: ConversionResult,
    *,
    dpi: float | None = None,
    version: str | None = None,
    include_metadata: bool = True,
) -> ezdxf.document.Drawing:
    """Build an :mod:`ezdxf` document from a conversion result."""
    dpi, version = _resolve_settings(result, dpi, version)
    mm_per_px = 25.4 / dpi
    height = float(result.source_height or result.stats.source_height or 0)
    width = float(result.source_width or result.stats.source_width or 0)
    if height <= 0 or width <= 0:
        raise ValueError("conversion result has no valid source dimensions")

    doc = ezdxf.new(version, setup=False)
    doc.header["$INSUNITS"] = 4  # millimetres
    doc.header["$MEASUREMENT"] = 1  # metric
    doc.header["$LUNITS"] = 2  # decimal
    doc.header["$LUPREC"] = 4
    if include_metadata:
        try:
            doc.header["$PROJECTNAME"] = "bmp2dxf"
        except Exception:
            pass

    for layer_name, color in LAYER_COLORS.items():
        if layer_name not in doc.layers:
            doc.layers.add(layer_name, color=color, linetype="CONTINUOUS")

    msp = doc.modelspace()
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for path in result.paths:
        pts = _to_dxf_points(path, height, mm_per_px)
        if len(pts) < 2:
            continue
        attribs = {"layer": path.layer}
        if version == "R12":
            msp.add_polyline2d(
                pts.tolist(), close=bool(path.closed), dxfattribs=attribs
            )
        else:
            msp.add_lwpolyline(
                pts.tolist(),
                close=bool(path.closed),
                dxfattribs=attribs,
            )
        min_x = min(min_x, float(pts[:, 0].min()))
        max_x = max(max_x, float(pts[:, 0].max()))
        min_y = min(min_y, float(pts[:, 1].min()))
        max_y = max(max_y, float(pts[:, 1].max()))

    if np.isfinite([min_x, min_y, max_x, max_y]).all() and max_x >= min_x:
        doc.header["$EXTMIN"] = (min_x, min_y, 0.0)
        doc.header["$EXTMAX"] = (max_x, max_y, 0.0)
    else:
        doc.header["$EXTMIN"] = (0.0, 0.0, 0.0)
        doc.header["$EXTMAX"] = (width * mm_per_px, height * mm_per_px, 0.0)

    try:
        doc.set_modelspace_vport(
            height=max(height * mm_per_px, 1.0),
            center=(width * mm_per_px / 2.0, height * mm_per_px / 2.0),
        )
    except Exception:
        pass
    return doc


def to_dxf_bytes(
    result: ConversionResult,
    *,
    dpi: float | None = None,
    version: str | None = None,
) -> bytes:
    """Serialise a conversion result as DXF bytes."""
    doc = build_document(result, dpi=dpi, version=version)
    stream = StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def to_dxf(
    result: ConversionResult,
    target: str | Path | Any,
    *,
    dpi: float | None = None,
    version: str | None = None,
) -> Path:
    """Write a conversion result to a ``.dxf`` file and return its path."""
    data = to_dxf_bytes(result, dpi=dpi, version=version)
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
