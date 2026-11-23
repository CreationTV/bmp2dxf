import json
from pathlib import Path

import ezdxf
from PIL import Image, ImageDraw

from bmp2dxf.cli import main


def _write_test_image(path: Path) -> Path:
    image = Image.new("L", (320, 240), 255)
    draw = ImageDraw.Draw(image)
    draw.line([(30, 200), (290, 40)], fill=0, width=10)
    image.save(path)
    return path


def test_cli_presets(capsys):
    assert main(["presets"]) == 0
    out = capsys.readouterr().out
    for name in ("line", "sketch", "logo", "draft"):
        assert name in out


def test_cli_convert_single_file(tmp_path, capsys):
    source = _write_test_image(tmp_path / "drawing.png")
    target = tmp_path / "drawing.dxf"
    code = main(["convert", str(source), "-o", str(target), "--preset", "line"])
    assert code == 0
    assert target.exists()
    doc = ezdxf.readfile(str(target))
    assert len(list(doc.modelspace())) >= 1
    assert "完成" in capsys.readouterr().out


def test_cli_json_output(tmp_path, capsys):
    source = _write_test_image(tmp_path / "drawing.png")
    target = tmp_path / "out"
    code = main(
        [
            "convert",
            str(source),
            "-o",
            str(target),
            "--mode",
            "centerline",
            "--precision",
            "75",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["results"][0]["path_count"] >= 1
    assert Path(payload["results"][0]["output"]).exists()


def test_cli_batch_directory(tmp_path, capsys):
    source_dir = tmp_path / "images"
    source_dir.mkdir()
    _write_test_image(source_dir / "a.png")
    _write_test_image(source_dir / "b.png")
    output_dir = tmp_path / "dxf"
    code = main(
        [
            "convert",
            str(source_dir),
            "-o",
            str(output_dir),
            "--mode",
            "centerline",
        ]
    )
    assert code == 0
    assert len(list(output_dir.glob("*.dxf"))) == 2
    capsys.readouterr()


def test_cli_missing_input(tmp_path, capsys):
    code = main(["convert", str(tmp_path / "missing.png")])
    assert code == 2
    assert "错误" in capsys.readouterr().err


def test_cli_manual_threshold_requires_value(tmp_path):
    source = _write_test_image(tmp_path / "drawing.png")
    code = main(
        [
            "convert",
            str(source),
            "--threshold-mode",
            "manual",
        ]
    )
    assert code == 2
