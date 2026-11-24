"""Command line interface for bmp2dxf."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .config import PRESETS, ConvertOptions
from .export.dxf import to_dxf_bytes
from .pipeline import convert


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".gif",
    ".ico",
    ".pnm",
    ".ppm",
    ".pgm",
    ".pbm",
    ".tga",
    ".psd",
    ".jp2",
    ".j2k",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bmp2dxf",
        description="把位图（PNG/JPEG/WebP/BMP/TIFF…）转换为可编辑的 DXF 矢量图。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  bmp2dxf convert drawing.png -o drawing.dxf
  bmp2dxf convert sketch.jpg --preset sketch --precision 85 -g 8
  bmp2dxf convert scans/ -o out/ --recursive --mode centerline
  bmp2dxf serve --port 8765
  bmp2dxf presets
""",
    )
    parser.add_argument("--version", action="version", version=f"bmp2dxf {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    convert_p = sub.add_parser(
        "convert", help="转换一个或多个位图", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    convert_p.add_argument("inputs", nargs="+", type=Path, help="输入图片文件或目录")
    convert_p.add_argument("-o", "--output", type=Path, help="输出 .dxf 文件或目录")
    convert_p.add_argument(
        "--preset", choices=sorted(PRESETS), help="快捷预设（可被后面的显式参数覆盖）"
    )
    convert_p.add_argument(
        "-m", "--mode", choices=("auto", "centerline", "outline", "color"), help="转换模式"
    )
    convert_p.add_argument(
        "-p", "--precision", type=int, metavar="0-100", help="转换精度（默认 70）"
    )
    convert_p.add_argument(
        "--threshold-mode",
        choices=("auto", "otsu", "adaptive", "manual"),
        help="阈值方式",
    )
    convert_p.add_argument("--threshold", type=float, metavar="0-255", help="手动阈值")
    convert_p.add_argument(
        "--invert", choices=("auto", "yes", "no"), help="是否反相（自动/是/否）"
    )
    convert_p.add_argument(
        "-g", "--gap", type=float, metavar="PX", help="断线连接距离，单位：原图像素"
    )
    convert_p.add_argument("--smoothing", type=int, metavar="0-100", help="平滑强度")
    convert_p.add_argument("--corner-angle", type=float, metavar="DEG", help="拐角保留夹角")
    convert_p.add_argument(
        "--min-detail", type=float, metavar="PX", help="最小细节尺寸；0 = 自动"
    )
    convert_p.add_argument("--dpi", type=float, help="输出 DXF 使用的 DPI（默认 96）")
    convert_p.add_argument("--max-dim", type=int, help="处理分辨率上限；0 = 自动")
    convert_p.add_argument("--dxf-version", choices=("R12", "R2000", "R2010", "R2018"))
    convert_p.add_argument("--no-denoise", action="store_true", help="关闭轻微去噪")
    convert_p.add_argument("--no-extend", action="store_true", help="不延伸被骨架缩短的线端")
    convert_p.add_argument(
        "-r", "--recursive", action="store_true", help="递归扫描输入目录"
    )
    convert_p.add_argument(
        "-f", "--force", action="store_true", help="覆盖已存在的 DXF 文件"
    )
    convert_p.add_argument("--json", action="store_true", help="以 JSON 输出结果统计")
    convert_p.add_argument("-q", "--quiet", action="store_true", help="只输出错误")

    serve_p = sub.add_parser("serve", help="启动本地 Web 界面")
    serve_p.add_argument("--host", default="127.0.0.1", help="监听地址")
    serve_p.add_argument("--port", type=int, default=8765, help="监听端口")
    serve_p.add_argument(
        "--no-open", action="store_false", dest="open_browser", help="不自动打开浏览器"
    )
    serve_p.set_defaults(open_browser=True)

    sub.add_parser("presets", help="列出可用预设")
    return parser


def _collect_inputs(inputs: Sequence[Path], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        if item.is_dir():
            pattern = "**/*" if recursive else "*"
            for path in sorted(item.glob(pattern)):
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                    files.append(path)
        elif item.is_file():
            files.append(item)
        else:
            raise FileNotFoundError(f"输入不存在：{item}")
    if not files:
        raise ValueError("没有找到可转换的图片文件")
    return files


def _build_options(args: argparse.Namespace) -> ConvertOptions:
    data: dict[str, Any] = {}
    if args.preset:
        data.update(PRESETS[args.preset])
    explicit = {
        "mode": args.mode,
        "precision": args.precision,
        "threshold_method": args.threshold_mode,
        "threshold": args.threshold,
        "invert": args.invert,
        "gap_close": args.gap,
        "smoothing": args.smoothing,
        "corner_angle": args.corner_angle,
        "min_detail": args.min_detail,
        "dpi": args.dpi,
        "max_dim": args.max_dim,
        "dxf_version": args.dxf_version,
    }
    for key, value in explicit.items():
        if value is not None:
            data[key] = value
    if args.threshold_mode == "manual" and args.threshold is None:
        raise ValueError("--threshold-mode manual 需要同时提供 --threshold")
    if args.no_denoise:
        data["denoise"] = False
    if args.no_extend:
        data["extend_ends"] = False
    try:
        return ConvertOptions(**data)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"参数错误：{exc}") from exc


def _resolve_output(output: Path | None, source: Path, multiple: bool) -> Path:
    if output is None:
        return source.with_suffix(".dxf")
    if multiple:
        if output.suffix.lower() == ".dxf":
            raise ValueError("转换多个文件时 --output 必须是目录，不能是单个 .dxf 文件")
        return output / (source.stem + ".dxf")
    if output.suffix.lower() == ".dxf":
        return output
    return output / (source.stem + ".dxf")


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{num_bytes} B"


def _cmd_convert(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    options = _build_options(args)
    files = _collect_inputs(args.inputs, args.recursive)
    multiple = len(files) > 1
    results: list[dict[str, Any]] = []
    failures = 0

    explicit_file = (
        not multiple
        and args.output is not None
        and args.output.suffix.lower() == ".dxf"
    )
    for source in files:
        target = _resolve_output(args.output, source, multiple)
        target.parent.mkdir(parents=True, exist_ok=True)
        if explicit_file and target.exists() and not args.force:
            print(f"[跳过] 输出已存在：{target}（使用 -f 覆盖）", file=sys.stderr)
            failures += 1
            continue
        item_started = time.perf_counter()
        try:
            result = convert(source, options)
            dxf = to_dxf_bytes(
                result,
                dpi=float(options.dpi),
                version=str(options.dxf_version),
            )
            target.write_bytes(dxf)
        except Exception as exc:  # noqa: BLE001 - CLI boundary
            failures += 1
            print(f"[失败] {source}: {exc}", file=sys.stderr)
            continue
        elapsed = (time.perf_counter() - item_started) * 1000.0
        results.append(
            {
                "input": str(source),
                "output": str(target),
                "bytes": len(dxf),
                **result.stats.to_dict(),
                "warnings": list(result.warnings),
                "elapsed_ms_wall": round(elapsed, 1),
            }
        )
        if not args.quiet and not args.json:
            stats = result.stats
            print(
                f"[OK] {source.name}  {stats.source_width}×{stats.source_height} → "
                f"{stats.path_count} 条路径 / {stats.point_count} 个节点 / "
                f"{stats.total_length_mm:.1f} mm   [{stats.mode_used}]"
            )
            print(f"  → {target}  ({_format_size(len(dxf))})")
            for warning in result.warnings:
                print(f"  ! {warning}")

    if args.json:
        payload = {
            "ok": failures == 0,
            "count": len(results),
            "failed": failures,
            "results": results,
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 1),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif not args.quiet:
        ok = len(results)
        print(f"\n完成：{ok} 个成功，{failures} 个失败。")
    return 0 if failures == 0 else 1


def _cmd_serve(args: argparse.Namespace) -> int:
    try:
        from .web.server import run_server
    except ImportError as exc:  # pragma: no cover - depends on optional assets
        print(
            "Web 界面模块未安装或文件缺失，请从项目完整目录运行。\n"
            f"详细信息：{exc}",
            file=sys.stderr,
        )
        return 2
    try:
        run_server(
            host=args.host,
            port=args.port,
            open_browser=bool(args.open_browser),
            block=True,
        )
    except KeyboardInterrupt:
        print("\n已停止。")
    return 0


def _cmd_presets() -> int:
    print("可用预设：")
    for name, values in PRESETS.items():
        summary = ", ".join(f"{key}={value}" for key, value in values.items())
        print(f"  {name:8s} {summary}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "convert":
            return _cmd_convert(args)
        if args.command == "serve":
            return _cmd_serve(args)
        if args.command == "presets":
            return _cmd_presets()
    except (ValueError, FileNotFoundError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    parser.print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
