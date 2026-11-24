"""bmp2dxf - turn bitmaps into clean DXF vectors.

Quick start::

    from bmp2dxf import convert, ConvertOptions, to_dxf_bytes

    result = convert("drawing.png", ConvertOptions(mode="centerline", precision=80))
    data = to_dxf_bytes(result)
    open("drawing.dxf", "wb").write(data)
"""

from __future__ import annotations

from .config import PRESETS, ConvertOptions
from .models import ConversionResult, ConversionStats, VectorPath
from .pipeline import convert, convert_many

__version__ = "1.1.0"

__all__ = [
    "__version__",
    "ConvertOptions",
    "PRESETS",
    "ConversionResult",
    "ConversionStats",
    "VectorPath",
    "convert",
    "convert_many",
    "to_dxf_bytes",
    "to_dxf",
    "to_svg",
]


def __getattr__(name: str):
    # Lazy imports keep ``import bmp2dxf`` fast and avoid pulling Pillow/ezdxf
    # when only the models are needed.
    if name in ("to_dxf", "to_dxf_bytes"):
        from .export.dxf import to_dxf, to_dxf_bytes

        return {"to_dxf": to_dxf, "to_dxf_bytes": to_dxf_bytes}[name]
    if name == "to_svg":
        from .export.svg import to_svg

        return to_svg
    raise AttributeError(f"module 'bmp2dxf' has no attribute {name!r}")
