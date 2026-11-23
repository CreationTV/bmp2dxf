"""Command line entry point: ``python -m bmp2dxf.web --port 8765``."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .server import DEFAULT_HOST, DEFAULT_PORT, run_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bmp2dxf.web",
        description="启动 bmp2dxf 本地 Web 工作台（位图转 DXF）。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="监听地址（默认仅本机访问）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="监听端口；被占用时可换一个端口",
    )
    parser.add_argument(
        "--open",
        dest="open_browser",
        action="store_true",
        help="启动后自动打开浏览器（默认）",
    )
    parser.add_argument(
        "--no-open",
        dest="open_browser",
        action="store_false",
        help="不自动打开浏览器",
    )
    parser.set_defaults(open_browser=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_server(
            host=args.host,
            port=args.port,
            open_browser=bool(args.open_browser),
            block=True,
        )
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print("\n[bmp2dxf] 已停止 Web 服务。")
        return 0
    if result is None:
        return 0
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
