"""Generate the Windows application icon (packaging/bmp2dxf.ico)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packaging" / "bmp2dxf.ico"
PAPER = (243, 230, 207, 255)
INK = (46, 31, 20, 255)
ACCENT = (224, 165, 38, 255)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in ("georgiab.ttf", "timesbd.ttf", "segoeuib.ttf"):
        path = Path("C:/Windows/Fonts") / candidate
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _draw(size: int) -> Image.Image:
    scale = 4
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    pad = int(canvas * 0.07)
    border = max(2, int(canvas * 0.055))
    draw.ellipse(
        (pad, pad, canvas - pad, canvas - pad),
        fill=ACCENT,
        outline=INK,
        width=border,
    )
    # A small cream crescent echoes the paper/stamp look of the web UI.
    draw.arc(
        (int(canvas * 0.19), int(canvas * 0.18), int(canvas * 0.81), int(canvas * 0.82)),
        start=205,
        end=335,
        fill=PAPER,
        width=max(2, int(canvas * 0.035)),
    )
    text = "b2d"
    font = _font(int(canvas * 0.35))
    box = draw.textbbox((0, 0), text, font=font)
    x = (canvas - (box[2] - box[0])) / 2 - box[0]
    y = (canvas - (box[3] - box[1])) / 2 - box[1] + int(canvas * 0.02)
    draw.text((x, y), text, font=font, fill=INK)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [_draw(size) for size in sizes]
    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"written {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
