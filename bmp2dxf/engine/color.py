"""Colour-boundary tracing for flat / continuous-tone colour artwork.

The grayscale engines deliberately throw colour away, which is the right
trade-off for line drawings but loses the internal boundaries of a painted
illustration: two adjacent colours can merge into one silhouette, and light
fills can vanish entirely.  This module keeps the RGB data and traces the
boundaries *between colour regions* instead of a single foreground mask.

The boundary raster is handed to the existing centerline engine, so we inherit
its junction pairing, spur pruning, gap bridging, smoothing and de-duplication
rather than growing a second curve-fitting implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.morphology import skeletonize

from ..config import ConvertOptions, Tuning
from ..models import VectorPath
from . import centerline
from .preprocess import PreparedImage


MAX_COLORS = 12
MERGE_DISTANCE = 10.0
INK_MAX_VALUE = 96
INK_MAX_CHROMA = 40
INK_SENTINEL = -2

MIN_CHROMA_FRACTION = 0.03
MIN_FLAT_FRACTION = 0.75
MIN_FILLED_FRACTION = 0.04


@dataclass
class ColorAnalysis:
    labels: np.ndarray
    palette: np.ndarray
    background_label: int
    ink_mask: np.ndarray
    palette_size: int
    chroma_fraction: float
    flat_fraction: float
    quantization_error: float
    filled_fraction: float
    is_color_art: bool
    reason: str


@dataclass
class ColorResult:
    paths: list[VectorPath] = field(default_factory=list)  # work coordinates
    junction_count: int = 0
    spur_prune_count: int = 0
    bridge_count: int = 0
    duplicate_removed: int = 0
    palette_size: int = 0
    warnings: list[str] = field(default_factory=list)


def _merge_near_duplicate_colors(
    labels: np.ndarray, palette: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Merge palette entries that are perceptually nearly identical."""
    count = len(palette)
    if count <= 1:
        return labels, palette
    parent = list(range(count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i in range(count):
        for j in range(i + 1, count):
            if float(np.linalg.norm(palette[i] - palette[j])) <= MERGE_DISTANCE:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri

    roots: dict[int, int] = {}
    remap = np.zeros(count, dtype=np.int32)
    for i in range(count):
        root = find(i)
        if root not in roots:
            roots[root] = len(roots)
        remap[i] = roots[root]

    new_count = len(roots)
    weights = np.bincount(labels.ravel(), minlength=count).astype(np.float64)
    new_palette = np.zeros((new_count, 3), dtype=np.float32)
    for old, new in enumerate(remap):
        new_palette[new] += palette[old] * weights[old]
    totals = np.zeros(new_count, dtype=np.float64)
    for old, new in enumerate(remap):
        totals[new] += weights[old]
    new_palette /= np.maximum(totals[:, None], 1.0)
    return remap[labels], new_palette


def _quantize(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    image = Image.fromarray(rgb, mode="RGB")
    quantized = image.quantize(
        colors=MAX_COLORS,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    local = np.asarray(quantized).astype(np.int32)
    palette = (
        np.asarray(quantized.getpalette(), dtype=np.float32).reshape(-1, 3)
        / 1.0
    )
    used = int(local.max(initial=0)) + 1
    palette = palette[:used]
    return local, palette, used


def _downsample(rgb: np.ndarray, max_side: int = 512) -> np.ndarray:
    height, width = rgb.shape[:2]
    longest = max(height, width)
    if longest <= max_side:
        return rgb
    scale = max_side / float(longest)
    size = (max(2, int(round(width * scale))), max(2, int(round(height * scale))))
    image = Image.fromarray(rgb, mode="RGB").resize(size, Image.Resampling.BILINEAR)
    return np.asarray(image, dtype=np.uint8)


def _flat_fraction(rgb: np.ndarray) -> tuple[float, float]:
    """Fraction of pixels whose local 5x5 colour range is almost zero.

    Flat paint has large constant-colour interiors; photographs and
    watercolour gradients do not.  The quantization error alone is not a good
    discriminator because a 12-colour palette can approximate a smooth
    gradient surprisingly well, so this directly measures local flatness.
    """
    small = _downsample(rgb)
    values = small.astype(np.float32)
    local_max = ndimage.maximum_filter(values, size=(5, 5, 1), mode="nearest")
    local_min = ndimage.minimum_filter(values, size=(5, 5, 1), mode="nearest")
    local_range = np.linalg.norm(local_max - local_min, axis=2)
    flat = float((local_range < 10.0).mean())

    # Pixel-wise colour range, used by the caller as an informational metric.
    chroma = values.max(axis=2) - values.min(axis=2)
    chroma_fraction = float((chroma > 18.0).mean())
    return flat, chroma_fraction


def _label_ink(labels: np.ndarray, palette: np.ndarray) -> np.ndarray:
    palette_max = palette.max(axis=1)
    palette_chroma = palette.max(axis=1) - palette.min(axis=1)
    ink_palette = (palette_max <= INK_MAX_VALUE) & (
        palette_chroma <= INK_MAX_CHROMA
    )
    mask = np.zeros(labels.shape, dtype=bool)
    for index in np.nonzero(ink_palette)[0]:
        mask |= labels == int(index)
    return mask


def _filled_fraction(
    labels: np.ndarray,
    palette: np.ndarray,
    background_label: int,
    diagonal: float,
) -> float:
    total = float(labels.size)
    if total <= 0:
        return 0.0
    threshold = max(4.0, 0.012 * diagonal)
    filled = 0
    for index in range(len(palette)):
        if index == background_label:
            continue
        mask = labels == index
        if not mask.any():
            continue
        components, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
        if count == 0:
            continue
        for component_id in range(1, count + 1):
            component = components == component_id
            area = int(component.sum())
            if area < max(16, int(0.001 * total)):
                continue
            dt = ndimage.distance_transform_edt(component)
            if float(dt.max()) >= threshold:
                filled += area
    return float(filled) / total


def _ink_edges(ink_mask: np.ndarray, diagonal: float) -> np.ndarray:
    """Turn dark ink strokes into one centered boundary line.

    Thin ink is skeletonised; thick ink is outlined on both sides.  The
    resulting raster is still handed to the centerline engine, which cleans up
    junctions and short spurs.
    """
    edges = np.zeros(ink_mask.shape, dtype=bool)
    components, count = ndimage.label(ink_mask, structure=np.ones((3, 3), dtype=bool))
    if count == 0:
        return edges
    threshold = max(4.0, 0.012 * diagonal)
    for component_id in range(1, count + 1):
        component = components == component_id
        area = int(component.sum())
        if area < 4:
            continue
        dt = ndimage.distance_transform_edt(component)
        if float(dt.max()) > threshold:
            eroded = ndimage.binary_erosion(
                component, structure=np.ones((3, 3), dtype=bool), border_value=0
            )
            edges |= component & ~eroded
        else:
            edges |= skeletonize(component)
    return edges


def _color_boundary_mask(
    labels: np.ndarray,
    palette: np.ndarray,
    background_label: int,
    ink_mask: np.ndarray,
) -> np.ndarray:
    """Rasterise the boundaries between adjacent non-ink colour regions."""
    # Anti-aliased pixels at the edge of a black line are often quantized to a
    # dark chromatic colour rather than pure black.  Expand the ink mask a
    # little for the purpose of *suppressing* colour boundaries, while the ink
    # centerline itself is still derived from the core mask only.
    suppress_ink = ndimage.binary_dilation(
        ink_mask, structure=np.ones((3, 3), dtype=bool), iterations=4
    )
    effective = labels.astype(np.int32).copy()
    effective[suppress_ink] = INK_SENTINEL
    padded = np.pad(effective, 1, mode="constant", constant_values=background_label)
    center = padded[1:-1, 1:-1]
    neighbours = (
        padded[:-2, 1:-1],
        padded[2:, 1:-1],
        padded[1:-1, :-2],
        padded[1:-1, 2:],
    )
    boundary = np.zeros(labels.shape, dtype=bool)
    for neighbour in neighbours:
        different = center != neighbour
        # Ink-to-colour / ink-to-background transitions are handled separately
        # by _ink_edges(); drawing them here would duplicate the ink line.
        touches_ink = (center == INK_SENTINEL) | (neighbour == INK_SENTINEL)
        boundary |= different & ~touches_ink

    diagonal = float(np.hypot(*labels.shape))
    boundary |= _ink_edges(ink_mask, diagonal)
    # A one-pixel dilation makes the boundary raster 8-connected and gives the
    # skeleton engine a little room at T-junctions.
    boundary = ndimage.binary_dilation(
        boundary, structure=np.ones((3, 3), dtype=bool)
    )
    return boundary


def probe_color(rgb: np.ndarray) -> bool:
    """Cheap first pass used by automatic mode.

    Quantizing and measuring connected colour regions is unnecessary for a
    photo or a grayscale-looking image, and those are by far the common cases.
    This checks the two cheapest discriminators first so ``auto`` does not pay
    the colour-analysis cost when it is clearly not colour artwork.
    """
    flat_fraction, chroma_fraction = _flat_fraction(rgb)
    return (
        chroma_fraction >= MIN_CHROMA_FRACTION
        and flat_fraction >= MIN_FLAT_FRACTION
    )


def analyze_color(rgb: np.ndarray) -> ColorAnalysis:
    """Quantize flat colour art and measure whether it is worth colour tracing."""
    local, palette, used = _quantize(rgb)
    labels, palette = _merge_near_duplicate_colors(local, palette)
    palette_size = len(palette)
    if palette_size == 0:
        palette = np.asarray([[255.0, 255.0, 255.0]], dtype=np.float32)
        palette_size = 1
        labels = np.zeros(rgb.shape[:2], dtype=np.int32)

    border = np.concatenate(
        [labels[:2].ravel(), labels[-2:].ravel(), labels[:, :2].ravel(), labels[:, -2:].ravel()]
    )
    background_label = int(np.bincount(border, minlength=palette_size).argmax())
    ink_mask = _label_ink(labels, palette)

    flat_fraction, chroma_fraction = _flat_fraction(rgb)
    diagonal = float(np.hypot(*labels.shape))
    filled_fraction = _filled_fraction(
        labels, palette, background_label, diagonal
    )

    palette_for_error = palette[labels]
    quantization_error = float(
        np.abs(palette_for_error - rgb.astype(np.float32)).mean()
    )

    is_color_art = (
        chroma_fraction >= MIN_CHROMA_FRACTION
        and flat_fraction >= MIN_FLAT_FRACTION
        and filled_fraction >= MIN_FILLED_FRACTION
    )
    if is_color_art:
        reason = (
            "检测到彩色平涂画面（彩色像素 "
            f"{chroma_fraction * 100:.0f}%，局部平坦度 {flat_fraction * 100:.0f}%，"
            f"填充区域 {filled_fraction * 100:.0f}%），自动使用彩色边界模式。"
        )
    else:
        reason = (
            "图像不是明显的彩色平涂画面；彩色模式会直接追踪颜色区域边界，"
            "连续色调照片可能产生较多碎线。"
        )

    return ColorAnalysis(
        labels=labels,
        palette=palette,
        background_label=background_label,
        ink_mask=ink_mask,
        palette_size=palette_size,
        chroma_fraction=chroma_fraction,
        flat_fraction=flat_fraction,
        quantization_error=quantization_error,
        filled_fraction=filled_fraction,
        is_color_art=is_color_art,
        reason=reason,
    )


def extract_color_paths(
    prepared: PreparedImage,
    tuning: Tuning,
    options: ConvertOptions,
    analysis: ColorAnalysis | None = None,
) -> ColorResult:
    """Trace colour-region boundaries and reuse the centerline engine."""
    if prepared.rgb is None:
        return ColorResult(
            warnings=["没有可用的彩色数据；已回退到轮廓模式。"],
        )
    analysis = analysis or analyze_color(prepared.rgb)
    if analysis.palette_size <= 1:
        return ColorResult(
            palette_size=analysis.palette_size,
            warnings=["图像几乎是单色，未找到颜色区域边界。"],
        )

    boundary = _color_boundary_mask(
        analysis.labels,
        analysis.palette,
        analysis.background_label,
        analysis.ink_mask,
    )
    if not boundary.any():
        return ColorResult(
            palette_size=analysis.palette_size,
            warnings=["没有找到彩色区域边界；请尝试提高精度或改用其他模式。"],
        )

    traced = centerline.extract_centerlines(boundary, tuning, options)
    paths = [
        VectorPath(path.points, path.closed, "outline")
        for path in traced.paths
    ]
    warnings = list(traced.warnings)
    if analysis.palette_size >= MAX_COLORS:
        warnings.append(
            "检测到的颜色接近调色板数量上限；如果画面有渐变，可先提高对比度或减少渐变再转换。"
        )
    return ColorResult(
        paths=paths,
        junction_count=traced.junction_count,
        spur_prune_count=traced.spur_prune_count,
        bridge_count=traced.bridge_count,
        duplicate_removed=traced.duplicate_removed,
        palette_size=analysis.palette_size,
        warnings=warnings,
    )
