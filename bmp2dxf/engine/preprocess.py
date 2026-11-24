"""Grayscale normalisation, polarity detection, resampling and binarisation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage

from ..config import ConvertOptions
from .image_io import LoadedImage, load_image


@dataclass
class PreparedImage:
    """The raster the vectorisers actually work on."""

    gray: np.ndarray  # uint8, working resolution, foreground darker than background
    mask: np.ndarray  # bool, True = foreground
    threshold: float
    threshold_method: str  # actual method: otsu / adaptive / manual
    auto_method_reason: str
    inverted: bool

    source_width: int
    source_height: int
    work_width: int
    work_height: int
    scale_x: float
    scale_y: float
    work_scale: float

    warnings: list[str] = field(default_factory=list)
    image_format: str = ""
    # Working-resolution RGB copy (uint8) when the source has colour.  The
    # colour-boundary engine works on this directly instead of the gray mask.
    rgb: np.ndarray | None = None


def _odd(value: int) -> int:
    value = int(value)
    return value if value % 2 == 1 else value + 1


def _background_brightness_spread(
    gray: np.ndarray,
    grid: int = 6,
    neutral: np.ndarray | None = None,
) -> float:
    """Estimate how much the page/background brightness varies.

    The image is split into tiles and each tile's *bright* percentile is
    measured.  Tiles dominated by ink are ignored.  Uniform drawings (even
    with huge solid shapes) therefore report a small spread, while a scanned
    page with vignetting or a lighting gradient reports a large one.

    When a colour image is supplied, only near-neutral pixels are measured.
    Saturated fills are not "lighting" and must not make the whole image look
    unevenly lit; that would wrongly switch a flat colour artwork to a local
    adaptive threshold.
    """
    h, w = gray.shape
    gh = max(2, min(grid, h // 64 if h >= 128 else 2))
    gw = max(2, min(grid, w // 64 if w >= 128 else 2))
    levels: list[float] = []
    for iy in range(gh):
        y0 = int(round(iy * h / gh))
        y1 = int(round((iy + 1) * h / gh))
        if y1 <= y0:
            continue
        for ix in range(gw):
            x0 = int(round(ix * w / gw))
            x1 = int(round((ix + 1) * w / gw))
            if x1 <= x0:
                continue
            tile = gray[y0:y1, x0:x1]
            if tile.size < 64:
                continue
            if neutral is not None:
                tile_neutral = neutral[y0:y1, x0:x1]
                # If a tile has very few neutral pixels it is almost certainly
                # a coloured painted area, not the page/background.
                if float(tile_neutral.mean()) < 0.08:
                    continue
                values = tile[tile_neutral]
                if values.size < 32:
                    continue
                level = float(np.percentile(values, 80.0))
            else:
                level = float(np.percentile(tile, 80.0))
            if level > 100.0:  # ignore tiles that are mostly foreground
                levels.append(level)
    if len(levels) < 3:
        return 0.0
    values = np.asarray(levels)
    lo, hi = np.percentile(values, [10.0, 90.0])
    return float(hi - lo)


def _otsu(gray: np.ndarray) -> float:
    """Otsu threshold on an 8-bit array, without relying on scikit-image."""
    values = np.clip(gray, 0, 255).astype(np.uint8)
    hist = np.bincount(values.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 127.0
    levels = np.arange(256, dtype=np.float64)
    weight_bg = np.cumsum(hist)
    weight_fg = total - weight_bg
    sum_total = np.dot(hist, levels)
    sum_bg = np.cumsum(hist * levels)
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg
        between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
    between = np.nan_to_num(between, nan=-1.0, posinf=-1.0, neginf=-1.0)
    return float(np.argmax(between))


def _line_art_threshold(gray: np.ndarray) -> float:
    """Otsu threshold, corrected for the sparse-ink case.

    Otsu is ill-conditioned when foreground ink covers only a few percent of
    the page: the class means are weighted heavily towards the paper and the
    optimum can collapse to the darkest ink level, which throws away faint
    anti-aliased strokes.  If Otsu lands too close to either intensity
    extreme we fall back to the midpoint between robust ink/paper levels.
    """
    threshold = _otsu(gray)
    lo, hi = (float(v) for v in np.percentile(gray, [1.0, 99.0]))
    span = hi - lo
    if span >= 20.0:
        low_band = lo + 0.25 * span
        high_band = lo + 0.75 * span
        if threshold < low_band or threshold > high_band:
            threshold = 0.5 * (lo + hi)
    return threshold


def _sauvola(gray: np.ndarray) -> np.ndarray:
    """Per-pixel Sauvola threshold map (0..255)."""
    from skimage.filters import threshold_sauvola

    h, w = gray.shape
    window = max(15, _odd(int(min(h, w) / 16)))
    window = min(window, 201)
    try:
        return threshold_sauvola(
            gray, window_size=window, k=0.2, r=128.0
        ).astype(np.float32)
    except Exception:  # pragma: no cover - extremely defensive
        return np.full_like(gray, _line_art_threshold(gray), dtype=np.float32)


def detect_inversion(gray: np.ndarray) -> tuple[bool, float]:
    """Guess whether the drawing is light-on-dark.

    Returns ``(inverted, border_median)``.  A small border band is judged, so
    a white page with a dark drawing is left untouched while a black sticker
    with white line art is inverted.
    """
    h, w = gray.shape
    band = max(1, min(6, h // 20, w // 20))
    strips = [
        gray[:band, :],
        gray[-band:, :],
        gray[:, :band],
        gray[:, -band:],
    ]
    border = np.concatenate([s.ravel() for s in strips])
    if border.size == 0:
        return False, 255.0
    median = float(np.median(border))
    return median < 110.0, median


def _resize_plan(
    width: int, height: int, options: ConvertOptions
) -> tuple[int, int, float]:
    max_side = max(width, height)
    target = options.target_max_dim()
    factor = 1.0
    if max_side > target:
        factor = target / max_side
    elif max_side < 700:
        factor = min(8.0, 700.0 / max_side)
    work_w = max(1, int(round(width * factor)))
    work_h = max(1, int(round(height * factor)))
    return work_w, work_h, factor


def _resize_gray(gray: np.ndarray, work_w: int, work_h: int) -> np.ndarray:
    if gray.shape[1] == work_w and gray.shape[0] == work_h:
        return np.ascontiguousarray(gray, dtype=np.float32)
    image = Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8), mode="L")
    image = image.resize((work_w, work_h), Image.Resampling.LANCZOS)
    return np.asarray(image, dtype=np.float32)


def _resize_rgb(rgb: np.ndarray, work_w: int, work_h: int) -> np.ndarray:
    rgb_u8 = np.ascontiguousarray(np.clip(rgb, 0, 255).astype(np.uint8))
    if rgb_u8.shape[1] == work_w and rgb_u8.shape[0] == work_h:
        return rgb_u8
    image = Image.fromarray(rgb_u8, mode="RGB")
    image = image.resize((work_w, work_h), Image.Resampling.LANCZOS)
    return np.ascontiguousarray(np.asarray(image, dtype=np.uint8))


def _looks_like_photo(gray: np.ndarray, mask: np.ndarray) -> bool:
    """A conservative heuristic: continuous-tone photos vectorise poorly."""
    values = np.clip(gray, 0, 255).astype(np.uint8)
    hist = np.bincount(values.ravel(), minlength=256).astype(np.float64)
    hist /= max(1.0, hist.sum())
    midtone = float(hist[70:200].sum())
    fg = float(mask.mean()) if mask.size else 0.0
    if midtone > 0.45 and 0.15 < fg < 0.9:
        return True
    return False


def prepare(
    source: Any,
    options: ConvertOptions,
    loaded: LoadedImage | None = None,
) -> PreparedImage:
    """Load and normalise an image for vectorisation."""
    loaded = loaded or load_image(source)
    warnings = list(loaded.warnings)
    gray_src = loaded.gray
    if gray_src.size == 0:
        raise ValueError("图片内容为空")

    # -- polarity -----------------------------------------------------------
    auto_inverted, border_median = detect_inversion(gray_src)
    if options.invert == "yes":
        inverted = True
    elif options.invert == "no":
        inverted = False
    else:
        inverted = auto_inverted
    gray_fg = (255.0 - gray_src) if inverted else gray_src.copy()

    # -- working resolution -------------------------------------------------
    work_w, work_h, factor = _resize_plan(
        loaded.source_width, loaded.source_height, options
    )
    gray = _resize_gray(gray_fg, work_w, work_h)
    scale_x = work_w / float(loaded.source_width)
    scale_y = work_h / float(loaded.source_height)
    work_scale = (scale_x + scale_y) * 0.5

    rgb_work: np.ndarray | None = None
    neutral: np.ndarray | None = None
    if loaded.rgb is not None and loaded.rgb.ndim == 3:
        rgb_work = _resize_rgb(loaded.rgb, work_w, work_h)

    if factor < 1.0:
        warnings.append(
            f"图片已缩放至 {work_w}×{work_h} 进行矢量化（精度 {options.precision}，"
            "提高精度可保留更多细节）。"
        )

    # -- gentle denoise -----------------------------------------------------
    if options.denoise:
        sigma = 0.35 + (1.0 - options.precision / 100.0) * 0.45
        if sigma > 0.01:
            gray = ndimage.gaussian_filter(gray, sigma=sigma, mode="nearest")
            if rgb_work is not None:
                blurred = ndimage.gaussian_filter(
                    rgb_work.astype(np.float32),
                    sigma=(sigma, sigma, 0.0),
                    mode="nearest",
                )
                rgb_work = np.clip(blurred, 0, 255).astype(np.uint8)

    if rgb_work is not None:
        chroma_work = (
            rgb_work.max(axis=2).astype(np.int16)
            - rgb_work.min(axis=2).astype(np.int16)
        )
        neutral = chroma_work <= 12

    # -- threshold ----------------------------------------------------------
    method = options.threshold_method
    auto_reason = ""
    if method == "auto":
        if options.threshold is not None:
            method = "manual"
            auto_reason = "使用手动阈值。"
        else:
            bg_spread = _background_brightness_spread(gray, neutral=neutral)
            if bg_spread > 12.0:
                method = "adaptive"
                auto_reason = (
                    f"检测到背景光照不均（亮度起伏 {bg_spread:.0f}/255），"
                    "自动使用局部自适应阈值。"
                )
            else:
                method = "otsu"
                auto_reason = "背景较均匀，自动使用 Otsu 全局阈值。"

    if method == "manual":
        if options.threshold is None:
            threshold = float(_line_art_threshold(gray))
            method = "otsu"
            auto_reason = "阈值模式为手动但未提供数值，回退到 Otsu。"
        else:
            threshold = float(options.threshold)
        mask = gray < threshold
    elif method == "adaptive":
        levels = _sauvola(gray)
        mask = gray < levels
        threshold = float(np.median(levels))
    else:
        method = "otsu"
        threshold = float(_line_art_threshold(gray))
        mask = gray < threshold

    mask = np.ascontiguousarray(mask, dtype=bool)
    fg_fraction = float(mask.mean()) if mask.size else 0.0

    if options.threshold_method == "manual" and options.threshold is not None:
        threshold = float(options.threshold)
        method = "manual"
        auto_reason = "使用手动阈值。"

    # -- sanity warnings ----------------------------------------------------
    if fg_fraction < 0.0002:
        warnings.append(
            "几乎没有检测到前景线条：请尝试降低阈值、勾选/取消「反相」，或选择局部自适应阈值。"
        )
    elif fg_fraction > 0.92:
        warnings.append(
            "前景几乎覆盖整张图片，可能背景判断反了：请尝试切换「反相」或调整阈值。"
        )
    if _looks_like_photo(gray, mask):
        warnings.append(
            "这似乎是一张连续色调照片而非线稿；转换结果可能只是一些色块轮廓。"
            "对照片建议先做描线/二值化预处理。"
        )
    if 20 < border_median < 235 and options.invert == "auto":
        pass  # neutral background, nothing to warn about

    return PreparedImage(
        gray=np.clip(gray, 0, 255).astype(np.uint8),
        mask=mask,
        threshold=threshold,
        threshold_method=method,
        auto_method_reason=auto_reason,
        inverted=inverted,
        source_width=loaded.source_width,
        source_height=loaded.source_height,
        work_width=work_w,
        work_height=work_h,
        scale_x=scale_x,
        scale_y=scale_y,
        work_scale=work_scale,
        warnings=warnings,
        image_format=loaded.image_format,
        rgb=rgb_work,
    )
