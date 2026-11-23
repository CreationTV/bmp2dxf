r"""Generate the demo images shipped in ``samples/``.

Run with the project virtual environment::

    .\.venv\Scripts\python.exe scripts\make_samples.py

The images are deterministic (fixed random seeds) and are intentionally
difficult in different ways: thick strokes, crossings, broken lines, tiny
details, filled shapes, anti-aliased text and a noisy scanned sketch.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


def _scale(points, s: int):
    return [(float(x) * s, float(y) * s) for x, y in points]


def render(W: int, H: int, draw_fn, scale: int = 3, background: int = 255) -> Image.Image:
    image = Image.new("L", (W * scale, H * scale), background)
    draw = ImageDraw.Draw(image)
    draw_fn(draw, scale)
    image = image.resize((W, H), Image.Resampling.LANCZOS)
    return image


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
        Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        Path(r"C:\Windows\Fonts\DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


# ---------------------------------------------------------------------------
# 1. mechanical line drawing (centerline demo)
# ---------------------------------------------------------------------------

def make_mechanical() -> Image.Image:
    W, H = 1200, 900

    def draw(d: ImageDraw.ImageDraw, s: int) -> None:
        def line(points, width):
            d.line(_scale(points, s), fill=0, width=int(width * s), joint="curve")

        # Outer frame, rounded corners.
        d.rounded_rectangle(
            [int(90 * s), int(80 * s), int(1110 * s), int(820 * s)],
            radius=int(24 * s),
            outline=0,
            width=int(10 * s),
        )
        # Central flange with a ring.
        d.ellipse(
            [int(240 * s), int(240 * s), int(620 * s), int(620 * s)],
            outline=0,
            width=int(9 * s),
        )
        d.ellipse(
            [int(375 * s), int(375 * s), int(485 * s), int(485 * s)],
            outline=0,
            width=int(7 * s),
        )
        # Crosshair through the flange with a deliberate gap on the left.
        line([(90, 430), (230, 430)], 6)
        line([(630, 430), (750, 430)], 6)
        line([(430, 240), (430, 350)], 6)
        line([(430, 520), (430, 640)], 6)
        # Thick diagonal bar, broken in the middle (gap bridging demo).
        line([(150, 750), (520, 380)], 18)
        line([(536, 364), (620, 280)], 18)
        # Slot / pocket with sharp corners.
        d.rounded_rectangle(
            [int(800 * s), int(600 * s), int(1050 * s), int(690 * s)],
            radius=int(16 * s),
            outline=0,
            width=int(8 * s),
        )
        # Small bolt holes: details that low precision should drop.
        for cx, cy, r in (
            (860, 270, 13),
            (925, 270, 13),
            (990, 270, 13),
            (860, 320, 7),
            (925, 320, 7),
            (990, 320, 7),
        ):
            d.ellipse(
                [
                    int((cx - r) * s),
                    int((cy - r) * s),
                    int((cx + r) * s),
                    int((cy + r) * s),
                ],
                outline=0,
                width=int(4 * s),
            )
        # Dashed centre line across the lower part.
        x = 780
        while x < 1080:
            line([(x, 500), (min(x + 36, 1080), 500)], 4)
            x += 52
        # A little arrow.
        line([(760, 790), (1080, 790)], 5)
        line([(1080, 790), (1045, 772)], 5)
        line([(1080, 790), (1045, 808)], 5)
        # Two short strokes that look like a joint detail.
        line([(760, 150), (820, 180), (760, 210)], 5)

    return render(W, H, draw)


# ---------------------------------------------------------------------------
# 2. filled logo (outline demo)
# ---------------------------------------------------------------------------

def make_logo() -> Image.Image:
    W, H = 1000, 800

    def draw(d: ImageDraw.ImageDraw, s: int) -> None:
        # Big filled ring.
        d.ellipse(
            [int(120 * s), int(160 * s), int(460 * s), int(500 * s)],
            fill=0,
        )
        d.ellipse(
            [int(220 * s), int(260 * s), int(360 * s), int(400 * s)],
            fill=255,
        )
        # Filled triangle with a round hole.
        d.polygon(
            _scale([(560, 130), (860, 500), (560, 500)], s),
            fill=0,
        )
        d.ellipse(
            [int(655 * s), int(330 * s), int(735 * s), int(410 * s)],
            fill=255,
        )
        # Thick curved bar.
        d.arc(
            [int(160 * s), int(520 * s), int(560 * s), int(760 * s)],
            start=20,
            end=160,
            fill=0,
            width=int(48 * s),
        )
        # Small solid dots and thin decorative lines (detail preservation).
        for cx, cy, r in ((820, 650, 11), (870, 650, 7), (920, 650, 4)):
            d.ellipse(
                [int((cx - r) * s), int((cy - r) * s), int((cx + r) * s), int((cy + r) * s)],
                fill=0,
            )
        d.line(
            _scale([(620, 650), (940, 650)], s),
            fill=0,
            width=int(3 * s),
        )
        d.line(
            _scale([(620, 690), (940, 690)], s),
            fill=0,
            width=int(2 * s),
        )
        # Star / spark.
        cx, cy, outer, inner = 830, 230, 60, 24
        points = []
        for i in range(16):
            radius = outer if i % 2 == 0 else inner
            angle = -np.pi / 2 + i * np.pi / 8
            points.append((cx + radius * np.cos(angle), cy + radius * np.sin(angle)))
        d.polygon(_scale(points, s), fill=0)

    return render(W, H, draw)


# ---------------------------------------------------------------------------
# 3. text (outline + centerline demo)
# ---------------------------------------------------------------------------

def make_text() -> Image.Image:
    W, H = 1000, 430
    image = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(image)
    draw.text((55, 45), "VECTOR", fill=0, font=font(210))
    return image


# ---------------------------------------------------------------------------
# 4. scanned / noisy sketch (adaptive threshold demo)
# ---------------------------------------------------------------------------

def make_sketch() -> Image.Image:
    rng = np.random.default_rng(20261123)
    W, H = 1100, 800
    scale = 2

    image = Image.new("L", (W * scale, H * scale), 255)
    d = ImageDraw.Draw(image)

    def rough_line(points, width, jitter=1.2):
        pts = np.asarray(points, dtype=float) * scale
        # densify and perturb so the line looks hand drawn
        dense = []
        for p, q in zip(pts[:-1], pts[1:]):
            steps = max(2, int(np.linalg.norm(q - p) / (6 * scale)))
            for t in np.linspace(0, 1, steps, endpoint=False):
                point = p + (q - p) * t
                point = point + rng.normal(0, jitter * scale, 2)
                dense.append(tuple(point))
        dense.append(tuple(pts[-1]))
        dense = [tuple(map(float, p)) for p in dense]
        d.line(dense, fill=0, width=int(width * scale), joint="curve")

    # A simple house / workshop sketch.
    rough_line([(170, 640), (170, 330), (470, 160), (770, 330), (770, 640), (170, 640)], 6)
    rough_line([(470, 160), (470, 330)], 5)
    d.rectangle([int(250 * scale), int(400 * scale), int(390 * scale), int(520 * scale)], outline=0, width=int(5 * scale))
    d.rectangle([int(540 * scale), int(400 * scale), int(700 * scale), int(640 * scale)], outline=0, width=int(5 * scale))
    d.ellipse([int(290 * scale), int(440 * scale), int(350 * scale), int(500 * scale)], outline=0, width=int(4 * scale))
    # Crossed measurement lines.
    rough_line([(120, 720), (900, 720)], 4)
    rough_line([(120, 700), (120, 740)], 4)
    rough_line([(900, 700), (900, 740)], 4)
    rough_line([(820, 250), (1000, 570)], 4)
    rough_line([(800, 570), (1020, 250)], 4)
    # Small annotations.
    for yy in range(700, 780, 20):
        rough_line([(950, yy), (1020, yy)], 2)
    # Gap in the roofline (eraser).
    d.rectangle([int(420 * scale), int(180 * scale), int(455 * scale), int(210 * scale)], fill=255)
    # Speckles + paper grain.
    image = image.resize((W, H), Image.Resampling.LANCZOS)
    arr = np.asarray(image, dtype=np.float32)
    # Uneven illumination: brighter left, darker right/bottom.
    xx = np.linspace(-1, 1, W)[None, :]
    yy = np.linspace(-1, 1, H)[:, None]
    shade = 1.0 - 0.12 * (xx * 0.5 + 0.5) - 0.10 * (yy * 0.5 + 0.5)
    arr = arr * shade + rng.normal(0, 4.0, arr.shape)
    arr = np.clip(arr, 0, 255)
    image = Image.fromarray(arr.astype(np.uint8), "L")
    image = image.filter(ImageFilter.GaussianBlur(0.8))
    return image


# ---------------------------------------------------------------------------
# 5. tiny pixel icon
# ---------------------------------------------------------------------------

def make_icon() -> Image.Image:
    size = 64
    image = Image.new("L", (size, size), 255)
    d = ImageDraw.Draw(image)
    d.polygon([(30, 4), (12, 34), (28, 34), (22, 60), (52, 26), (34, 26)], fill=0)
    d.rectangle([44, 44, 58, 58], outline=0, width=3)
    return image


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    jobs = {
        "mechanical.png": (make_mechanical(), {}),
        "logo.png": (make_logo(), {}),
        "text.png": (make_text(), {}),
        "sketch_scan.jpg": (make_sketch(), {"quality": 82}),
        "icon.png": (make_icon(), {}),
    }
    for name, (image, kwargs) in jobs.items():
        path = SAMPLES / name
        image.save(path, **kwargs)
        print(f"wrote {path.relative_to(ROOT)}  {image.size[0]}x{image.size[1]}")


if __name__ == "__main__":
    main()
