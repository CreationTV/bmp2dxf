"""Local web interface for bmp2dxf.

Start it with::

    python -m bmp2dxf.web --port 8765

or from Python::

    from bmp2dxf.web import run_server
    run_server(open_browser=True)
"""

from __future__ import annotations

from .server import (
    Bmp2DxfWebServer,
    PortInUseError,
    create_server,
    run_server,
)

__all__ = [
    "Bmp2DxfWebServer",
    "PortInUseError",
    "create_server",
    "run_server",
]
