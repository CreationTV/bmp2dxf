"""Portable/desktop entry point used by the Windows PyInstaller build.

Double-clicking the portable executable starts the local web workbench and
opens the default browser.  Passing command-line arguments still exposes the
normal ``bmp2dxf`` CLI (``convert`` / ``serve`` / ``presets``).
"""

from __future__ import annotations

import multiprocessing
import os
import sys
import threading
import webbrowser
from typing import Sequence

from . import __version__
from .web.server import DEFAULT_HOST, DEFAULT_PORT, PortInUseError, create_server


def _setup_windows_console() -> None:
    """Use UTF-8 for Chinese status lines in cmd/PowerShell consoles."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
        kernel32.SetConsoleTitleW(f"bmp2dxf {__version__}")
    except Exception:  # pragma: no cover - best-effort console setup
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _serve_portable(host: str = DEFAULT_HOST) -> int:
    """Start the local server, preferring the default port then any free port."""
    from .web.server import _configure_logging

    _configure_logging()
    server = None
    fallback = False
    try:
        server = create_server(host, DEFAULT_PORT)
    except PortInUseError:
        fallback = True
        try:
            server = create_server(host, 0)
        except OSError as exc:
            print(f"[bmp2dxf] 无法启动本地服务：{exc}", file=sys.stderr, flush=True)
            return 1

    socket_host, socket_port = server.server_address[0], server.server_address[1]
    url = f"http://{socket_host}:{socket_port}/"
    print("", flush=True)
    print("  bmp2dxf · 位图转矢量工作台", flush=True)
    print(f"  版本 {__version__}    地址 {url}", flush=True)
    if fallback:
        print(f"  {DEFAULT_PORT} 端口已被占用，已自动改用 {socket_port}。", flush=True)
    print("  关闭此窗口或按 Ctrl+C 可停止服务。", flush=True)
    print("", flush=True)

    browser = threading.Timer(0.6, webbrowser.open, args=(url,))
    browser.daemon = True
    if not os.environ.get("BMP2DXF_NO_BROWSER"):
        browser.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[bmp2dxf] 已停止 Web 服务。", flush=True)
    finally:
        server.server_close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the frozen executable and ``python -m bmp2dxf.portable``."""
    multiprocessing.freeze_support()
    _setup_windows_console()
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        from .cli import main as cli_main

        return cli_main(args)
    return _serve_portable()


if __name__ == "__main__":  # pragma: no cover - interactive
    raise SystemExit(main())
