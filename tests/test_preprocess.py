import numpy as np
from PIL import Image, ImageDraw

from bmp2dxf import ConvertOptions
from bmp2dxf.engine.image_io import load_image
from bmp2dxf.engine.preprocess import (
    _background_brightness_spread,
    detect_inversion,
    prepare,
)

from tools import disk_image, line_image, to_png


def test_detect_inversion():
    white = np.full((100, 100), 255, dtype=np.float32)
    white[40:60, 10:90] = 0
    inverted, border = detect_inversion(white)
    assert inverted is False
    assert border > 200

    black = np.zeros((100, 100), dtype=np.float32)
    black[40:60, 10:90] = 255
    inverted, border = detect_inversion(black)
    assert inverted is True
    assert border < 20


def test_background_spread_distinguishes_gradient():
    uniform = np.full((600, 800), 250, dtype=np.float32)
    uniform[100:150, 100:700] = 20
    assert _background_brightness_spread(uniform) < 12

    x = np.linspace(0, 1, 800, dtype=np.float32)[None, :]
    gradient = np.repeat((255 - 120 * x), 600, axis=0)
    gradient[100:150, 100:700] = 20
    assert _background_brightness_spread(gradient) > 12


def test_auto_threshold_uniform_page_uses_otsu():
    image = line_image()
    loaded = load_image(to_png(image))
    prepared = prepare(None, ConvertOptions(mode="centerline", precision=80), loaded)
    assert prepared.threshold_method == "otsu"
    assert prepared.mask.any()


def test_auto_threshold_gradient_page_uses_adaptive():
    width, height = 900, 600
    x = np.linspace(0, 1, width, dtype=np.float32)[None, :]
    background = np.repeat(255 - 140 * x, height, axis=0)
    image = Image.fromarray(background.astype(np.uint8), "L")
    draw = ImageDraw.Draw(image)
    for y in range(100, 560, 90):
        draw.line([(60, y), (840, y)], fill=25, width=3)
    loaded = load_image(to_png(image))
    prepared = prepare(None, ConvertOptions(mode="centerline", precision=80), loaded)
    assert prepared.threshold_method == "adaptive"
    assert prepared.mask.mean() < 0.2


def test_solid_disk_threshold_stays_global():
    loaded = load_image(to_png(disk_image()))
    prepared = prepare(None, ConvertOptions(mode="outline", precision=80), loaded)
    assert prepared.threshold_method == "otsu"
    assert prepared.mask.mean() > 0.2


def test_alpha_is_composited_on_white():
    rgba = Image.new("RGBA", (200, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(rgba)
    draw.rectangle([40, 30, 160, 90], fill=(0, 0, 0, 255))
    loaded = load_image(to_png(rgba))
    assert loaded.gray[0, 0] > 250
    assert loaded.gray[60, 100] < 10
    prepared = prepare(None, ConvertOptions(mode="outline", precision=80), loaded)
    assert prepared.inverted is False
    y = int(round(60 * prepared.scale_y))
    x = int(round(100 * prepared.scale_x))
    assert prepared.mask[y, x]


def test_16bit_grayscale_loads():
    array = np.zeros((60, 80), dtype=np.uint16)
    array[:, 40:] = 65535
    image = Image.fromarray(array)
    loaded = load_image(image)
    assert loaded.gray.dtype == np.float32
    assert loaded.gray.min() <= 1
    assert loaded.gray.max() >= 254


def test_prepare_upscales_tiny_images():
    image = Image.new("L", (64, 64), 255)
    draw = ImageDraw.Draw(image)
    draw.line([(8, 56), (56, 8)], fill=0, width=4)
    loaded = load_image(to_png(image))
    prepared = prepare(None, ConvertOptions(mode="centerline", precision=80), loaded)
    assert prepared.work_width > 300
    assert prepared.work_scale > 2.0
    assert prepared.mask.any()
