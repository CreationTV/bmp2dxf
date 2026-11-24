"""High level conversion pipeline (bitmap -> VectorPath list)."""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from .config import ConvertOptions, derive_tuning
from .engine import centerline as centerline_engine
from .engine import color as color_engine
from .engine import outline as outline_engine
from .engine.image_io import load_image
from .engine.preprocess import prepare
from .models import ConversionResult, ConversionStats, VectorPath


def _scale_path_to_source(
    path: VectorPath, scale_x: float, scale_y: float
) -> VectorPath:
    points = path.points.copy()
    points[:, 0] /= scale_x
    points[:, 1] /= scale_y
    return VectorPath(points, closed=path.closed, kind=path.kind)


def convert(
    source: Any,
    options: ConvertOptions | dict[str, Any] | None = None,
) -> ConversionResult:
    """Convert a bitmap into vector paths.

    Parameters
    ----------
    source:
        File path, raw bytes, binary stream or ``PIL.Image``.
    options:
        :class:`ConvertOptions` or a partial dict with the same keys.
    """
    if isinstance(options, dict):
        options = ConvertOptions.from_dict(options)
    options = options or ConvertOptions()
    started = time.perf_counter()

    loaded = load_image(source)
    prepared = prepare(source, options, loaded=loaded)
    tuning = derive_tuning(
        options, prepared.work_width, prepared.work_height, prepared.work_scale
    )

    stats = ConversionStats(
        source_width=prepared.source_width,
        source_height=prepared.source_height,
        work_width=prepared.work_width,
        work_height=prepared.work_height,
        work_scale=prepared.work_scale,
        mode_requested=options.mode,
        threshold=prepared.threshold,
        threshold_method=prepared.threshold_method,
        inverted=prepared.inverted,
        mm_per_px=25.4 / options.dpi,
        output_width_mm=prepared.source_width * 25.4 / options.dpi,
        output_height_mm=prepared.source_height * 25.4 / options.dpi,
        min_feature_px=tuning.min_feature_source_px,
        simplify_px=tuning.simplify_px / tuning.work_scale,
    )
    warnings: list[str] = list(prepared.warnings)

    color_analysis = None
    if prepared.rgb is not None:
        if options.mode == "auto":
            # Cheap colour-first probe: photos and monochrome-ish RGB inputs
            # must not pay the full quantize/region analysis cost.
            if color_engine.probe_color(prepared.rgb):
                color_analysis = color_engine.analyze_color(prepared.rgb)
        elif options.mode == "color":
            color_analysis = color_engine.analyze_color(prepared.rgb)

    mode_used = options.mode
    auto_reason = ""
    skeleton = None
    dt = None
    if options.mode == "auto":
        if color_analysis is not None and color_analysis.is_color_art:
            mode_used = "color"
            auto_reason = color_analysis.reason
        elif not prepared.mask.any():
            mode_used = "centerline"
            auto_reason = "空图像。"
        else:
            mode_used, auto_reason, skeleton, dt = centerline_engine.decide_mode(
                prepared.mask
            )
    elif options.mode == "color":
        if color_analysis is None:
            mode_used = "outline"
            auto_reason = "彩色模式需要彩色图片；已回退到轮廓模式。"
            warnings.append(
                "这张图片没有可用的颜色信息（灰度/16 位/浮点图），"
                "彩色模式已回退到轮廓模式。"
            )
        else:
            mode_used = "color"
            auto_reason = "手动选择彩色边界模式。"
            if not color_analysis.is_color_art:
                warnings.append(
                    "图像不是明显的彩色平涂画面；彩色模式会直接追踪所有颜色区域边界，"
                    "连续色调照片可能产生较多碎线。"
                )
    else:
        auto_reason = "手动选择模式。"
    stats.mode_used = mode_used
    stats.auto_reason = auto_reason

    if mode_used == "color":
        # In colour mode the grayscale foreground warnings are not meaningful:
        # a full-page flat colour can legitimately cover almost everything.
        warnings = [
            message
            for message in warnings
            if "几乎没有检测到前景" not in message
            and "前景几乎覆盖整张图片" not in message
            and "连续色调照片" not in message
        ]

    work_paths: list[VectorPath] = []
    if mode_used == "color":
        color_result = color_engine.extract_color_paths(
            prepared, tuning, options, analysis=color_analysis
        )
        work_paths = color_result.paths
        stats.junction_count = color_result.junction_count
        stats.spur_prune_count = color_result.spur_prune_count
        stats.bridge_count = color_result.bridge_count
        stats.duplicate_removed = color_result.duplicate_removed
        warnings.extend(color_result.warnings)
    elif prepared.mask.any():
        if mode_used == "centerline":
            if skeleton is None or dt is None:
                skeleton, dt = centerline_engine.compute_skeleton(prepared.mask)
            blob_fraction = centerline_engine.filled_blob_fraction(
                prepared.mask, dt
            )
            if blob_fraction > 0.20:
                warnings.append(
                    f"检测到 {blob_fraction * 100:.0f}% 的墨迹属于实心填充区域；"
                    "中心线模式会沿实心块生成骨架线，若想保留外形轮廓请切换为"
                    "「轮廓」模式。"
                )
            center = centerline_engine.extract_centerlines(
                prepared.mask,
                tuning,
                options,
                skeleton=skeleton,
                dt=dt,
            )
            work_paths = center.paths
            stats.junction_count = center.junction_count
            stats.spur_prune_count = center.spur_prune_count
            stats.bridge_count = center.bridge_count
            stats.duplicate_removed = center.duplicate_removed
            warnings.extend(center.warnings)
        else:
            outline = outline_engine.extract_outlines(prepared, tuning, options)
            work_paths = outline.paths
            warnings.extend(outline.warnings)

    paths = [
        _scale_path_to_source(p, prepared.scale_x, prepared.scale_y)
        for p in work_paths
    ]

    stats.path_count = len(paths)
    stats.point_count = int(sum(len(p.points) for p in paths))
    stats.closed_path_count = int(sum(1 for p in paths if p.closed))
    stats.total_length_px = float(sum(p.length for p in paths))
    stats.total_length_mm = stats.total_length_px * stats.mm_per_px
    stats.duration_ms = (time.perf_counter() - started) * 1000.0

    if not paths and (prepared.mask.any() or mode_used == "color"):
        warnings.append("未生成任何矢量路径；请尝试调整精度、阈值或模式。")
    # Deduplicate warnings while preserving order.
    seen: set[str] = set()
    unique_warnings = []
    for message in warnings:
        if message not in seen:
            seen.add(message)
            unique_warnings.append(message)

    return ConversionResult(
        paths=paths,
        stats=stats,
        warnings=unique_warnings,
        options=options.to_dict(),
        image_format=loaded.image_format,
        source_width=prepared.source_width,
        source_height=prepared.source_height,
    )


def convert_many(
    sources: list[Any], options: ConvertOptions | dict[str, Any] | None = None
) -> list[ConversionResult]:
    """Convenience helper used by the batch CLI."""
    return [convert(source, options) for source in sources]


def path_count(result: ConversionResult) -> int:
    return len(result.paths)


def total_length(result: ConversionResult) -> float:
    return float(sum(path.length for path in result.paths))


def bbox_pixels(result: ConversionResult) -> tuple[float, float, float, float] | None:
    return result.bbox()
