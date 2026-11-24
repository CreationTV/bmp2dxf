"""Conversion options and the adaptive internal tuning derived from them."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


VALID_MODES = ("auto", "centerline", "outline", "color")
VALID_THRESHOLD_METHODS = ("auto", "otsu", "adaptive", "manual")
VALID_INVERT = ("auto", "yes", "no")
VALID_DXF_VERSIONS = ("R12", "R2000", "R2010", "R2018")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class ConvertOptions:
    """User facing conversion settings.

    Precision is a single 0-100 dial: higher means more detail, more DXF
    vertices and a larger working resolution.  All other controls are
    optional refinements.

    ``gap_close`` and ``min_detail`` are expressed in **source image pixels**
    so that the same value behaves consistently for images of different
    resolutions.
    """

    mode: str = "auto"
    precision: int = 70
    threshold_method: str = "auto"
    threshold: float | None = None
    invert: str | bool = "auto"
    gap_close: float = 4.0
    smoothing: int = 55
    corner_angle: float = 100.0
    min_detail: float = 0.0
    dpi: float = 96.0
    max_dim: int = 0
    extend_ends: bool = True
    denoise: bool = True
    dxf_version: str = "R2000"

    def __post_init__(self) -> None:
        self.normalize()

    # -- validation ---------------------------------------------------------
    def normalize(self) -> None:
        mode = str(self.mode).strip().lower()
        if mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {VALID_MODES}, got {self.mode!r}")
        self.mode = mode

        self.precision = int(round(_clamp(float(self.precision), 0, 100)))

        method = str(self.threshold_method).strip().lower()
        if method not in VALID_THRESHOLD_METHODS:
            raise ValueError(
                f"threshold_method must be one of {VALID_THRESHOLD_METHODS}"
            )
        self.threshold_method = method
        if method == "manual":
            if self.threshold is None:
                raise ValueError("manual threshold requires a threshold value")
            self.threshold = float(_clamp(float(self.threshold), 0, 255))
        elif self.threshold is not None:
            self.threshold = float(_clamp(float(self.threshold), 0, 255))

        invert = self.invert
        if isinstance(invert, bool):
            invert = "yes" if invert else "no"
        invert = str(invert).strip().lower()
        if invert in ("true", "1", "on"):
            invert = "yes"
        elif invert in ("false", "0", "off"):
            invert = "no"
        if invert not in VALID_INVERT:
            raise ValueError(f"invert must be one of {VALID_INVERT}")
        self.invert = invert  # type: ignore[assignment]

        self.gap_close = float(_clamp(float(self.gap_close), 0.0, 200.0))
        self.smoothing = int(round(_clamp(float(self.smoothing), 0, 100)))
        self.corner_angle = float(_clamp(float(self.corner_angle), 20.0, 170.0))
        self.min_detail = float(max(0.0, float(self.min_detail)))
        self.dpi = float(_clamp(float(self.dpi), 10.0, 2400.0))
        self.max_dim = int(_clamp(float(self.max_dim), 0, 8000))
        self.extend_ends = bool(self.extend_ends)
        self.denoise = bool(self.denoise)

        version = str(self.dxf_version).strip().upper()
        if not version.startswith("R") or version not in VALID_DXF_VERSIONS:
            raise ValueError(f"dxf_version must be one of {VALID_DXF_VERSIONS}")
        self.dxf_version = version

    # -- derived values -----------------------------------------------------
    def target_max_dim(self) -> int:
        """Working resolution limit for the current precision."""
        if self.max_dim > 0:
            return self.max_dim
        return int(round(950 + 14.5 * self.precision))  # 950 .. 2400 px

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ConvertOptions":
        """Build options from a (possibly partial / stringly typed) mapping."""
        if not data:
            return cls()
        allowed = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean: dict[str, Any] = {}
        for key, value in data.items():
            if key not in allowed or value is None:
                continue
            clean[key] = value
        if "threshold" in clean and clean["threshold"] in ("", "auto", "None"):
            clean["threshold"] = None
        return cls(**clean)


@dataclass(frozen=True)
class Tuning:
    """Internal parameters resolved from options + working resolution."""

    work_scale: float
    simplify_px: float
    min_feature_px: float
    min_area_px: float
    min_length_px: float
    spur_px: float
    gap_px: float
    smoothing_iters: int
    input_blur_sigma: float

    @property
    def min_feature_source_px(self) -> float:
        return self.min_feature_px / self.work_scale


def derive_tuning(options: ConvertOptions, work_w: int, work_h: int, work_scale: float) -> Tuning:
    """Map the precision dial and the working resolution to algorithm values.

    All values are in *working image* pixels, except :attr:`work_scale`.
    """
    p = options.precision / 100.0
    low = 1.0 - p
    diag = max(1.0, (work_w**2 + work_h**2) ** 0.5)

    # Detail tolerance of the Douglas-Peucker pass.  Precision 100 keeps the
    # raw pixel skeleton, lower values smooth more aggressively.
    simplify_px = _clamp(0.30 + (low**1.6) * 0.0050 * diag, 0.30, 14.0)

    # Smallest feature (stroke width / dot size) that is preserved.
    if options.min_detail > 0:
        min_feature_px = options.min_detail * work_scale
    else:
        min_feature_px = max(1.5, (low**2) * 0.012 * diag)

    min_area_px = max(1.0, 0.65 * min_feature_px**2)
    min_length_px = max(2.0, 1.15 * min_feature_px)
    spur_px = max(3.0, 2.4 * min_feature_px)
    gap_px = _clamp(options.gap_close * work_scale, 0.0, 60.0)

    smoothing_iters = int(round(_clamp(options.smoothing / 34.0, 0, 3)))
    blur_sigma = 0.0
    if options.denoise:
        blur_sigma = 0.35 + low * 0.45  # 0.35 .. 0.80 px

    return Tuning(
        work_scale=work_scale,
        simplify_px=simplify_px,
        min_feature_px=min_feature_px,
        min_area_px=min_area_px,
        min_length_px=min_length_px,
        spur_px=spur_px,
        gap_px=gap_px,
        smoothing_iters=smoothing_iters,
        input_blur_sigma=blur_sigma,
    )


PRESETS: dict[str, dict[str, Any]] = {
    "line": {  # 线稿 / 工程图
        "mode": "centerline",
        "precision": 78,
        "gap_close": 5.0,
        "smoothing": 50,
        "threshold_method": "auto",
    },
    "sketch": {  # 手绘 / 扫描
        "mode": "centerline",
        "precision": 66,
        "gap_close": 8.0,
        "smoothing": 68,
        "threshold_method": "auto",
    },
    "logo": {  # 图标 / 标志轮廓
        "mode": "outline",
        "precision": 84,
        "gap_close": 2.0,
        "smoothing": 45,
        "threshold_method": "otsu",
    },
    "draft": {  # 快速草稿
        "mode": "centerline",
        "precision": 35,
        "gap_close": 10.0,
        "smoothing": 85,
        "threshold_method": "auto",
    },
}
