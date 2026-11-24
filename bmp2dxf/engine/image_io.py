"""Robust loading of all bitmap formats supported by Pillow."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


SUPPORTED_FORMATS = "PNG, JPEG, WebP, BMP, TIFF, GIF, ICO, PNM, TGA, PSD, JPEG2000"


@dataclass
class LoadedImage:
    gray: np.ndarray
    source_width: int
    source_height: int
    image_format: str = ""
    mode: str = ""
    warnings: list[str] = field(default_factory=list)
    # Original colours (uint8 RGB) for images that have them.  ``None`` for
    # grayscale / 16-bit / float inputs: their colour information is either
    # absent or fragile to preserve through Pillow's modes.
    rgb: np.ndarray | None = None


def _to_gray_array(
    image: Image.Image,
) -> tuple[np.ndarray, list[str], np.ndarray | None]:
    """Convert any Pillow image into a float32 grayscale array in 0..255.

    Also returns an RGB array when the source carries meaningful colour, which
    lets the colour-boundary engine run before grayscale information is lost.
    """
    warnings: list[str] = []
    mode = image.mode

    if mode in ("I;16", "I;16B", "I;16L", "I;16N"):
        arr = np.asarray(image).astype(np.float64)
        scale = 65535.0 if arr.max(initial=0) > 255 else 255.0
        arr = np.clip(arr / scale * 255.0, 0, 255)
        return arr.astype(np.float32), warnings, None

    if mode == "I":
        arr = np.asarray(image).astype(np.float64)
        high = float(arr.max()) if arr.size else 0.0
        if high > 255:
            arr = arr * (255.0 / high)
        return np.clip(arr, 0, 255).astype(np.float32), warnings, None

    if mode == "F":
        arr = np.asarray(image, dtype=np.float64)
        finite = arr[np.isfinite(arr)]
        if finite.size and float(finite.max()) <= 1.0001:
            arr = arr * 255.0
        return np.clip(arr, 0, 255).astype(np.float32), warnings, None

    # Anything with transparency is composited on white, which is what a
    # person would expect when vectorising a logo or sticker.
    has_alpha = mode in ("RGBA", "LA", "PA") or (
        mode == "P" and "transparency" in image.info
    )
    if has_alpha:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, rgba)

    # Monochrome bitmaps have no colour information worth preserving.
    if image.mode == "1":
        return np.asarray(image.convert("L"), dtype=np.float32), warnings, None
    if image.mode in ("L", "LA"):
        return np.asarray(image.convert("L"), dtype=np.float32), warnings, None

    rgb_image = image if image.mode == "RGB" else image.convert("RGB")
    rgb = np.asarray(rgb_image, dtype=np.uint8)
    gray = np.asarray(rgb_image.convert("L"), dtype=np.float32)
    return gray, warnings, np.ascontiguousarray(rgb)


def load_image(source: Any) -> LoadedImage:
    """Load a bitmap from a path, bytes, file object or Pillow image.

    Parameters
    ----------
    source:
        ``str | Path``, raw ``bytes``, a binary file object or a
        :class:`PIL.Image.Image`.
    """
    warnings: list[str] = []

    if isinstance(source, Image.Image):
        image = source
        fmt = image.format or "PIL"
    else:
        if isinstance(source, (str, Path)):
            try:
                image = Image.open(source)
            except UnidentifiedImageError as exc:
                raise ValueError(
                    f"无法识别的图片格式，支持：{SUPPORTED_FORMATS}"
                ) from exc
            except FileNotFoundError:
                raise
        elif isinstance(source, (bytes, bytearray, memoryview)):
            if not source:
                raise ValueError("图片数据为空")
            try:
                image = Image.open(io.BytesIO(bytes(source)))
            except UnidentifiedImageError as exc:
                raise ValueError(
                    f"无法识别的图片格式，支持：{SUPPORTED_FORMATS}"
                ) from exc
        elif hasattr(source, "read"):
            data = source.read()
            if not data:
                raise ValueError("图片数据为空")
            try:
                image = Image.open(io.BytesIO(data))
            except UnidentifiedImageError as exc:
                raise ValueError(
                    f"无法识别的图片格式，支持：{SUPPORTED_FORMATS}"
                ) from exc
        else:
            raise TypeError(
                "source must be a path, bytes, binary file object or PIL.Image"
            )
        fmt = image.format or ""

    try:
        image.seek(0)
    except EOFError:
        pass

    if getattr(image, "n_frames", 1) > 1:
        warnings.append("检测到动图，只转换第一帧。")

    image = ImageOps.exif_transpose(image)
    fmt = fmt or image.format or ""
    width, height = image.size
    if width < 1 or height < 1:
        raise ValueError("图片尺寸无效")
    if width * height > 120_000_000:
        raise ValueError("图片像素超过 1.2 亿，请先缩小后再转换")

    gray, extra_warnings, rgb = _to_gray_array(image)
    warnings.extend(extra_warnings)
    return LoadedImage(
        gray=np.ascontiguousarray(gray, dtype=np.float32),
        source_width=int(width),
        source_height=int(height),
        image_format=str(fmt).upper(),
        mode=image.mode,
        warnings=warnings,
        rgb=rgb,
    )


def load_image_from_stream(stream: BinaryIO) -> LoadedImage:
    return load_image(stream)
