import io
from pathlib import Path

import ezdxf
import numpy as np

from bmp2dxf import ConvertOptions, convert
from bmp2dxf.export.dxf import build_document, to_dxf, to_dxf_bytes
from bmp2dxf.export.svg import to_svg
from bmp2dxf.models import ConversionResult, ConversionStats, VectorPath

from tools import line_image, to_png


def test_dxf_is_readable_and_scaled_in_millimetres():
    result = convert(
        to_png(line_image()), ConvertOptions(mode="centerline", precision=80)
    )
    data = to_dxf_bytes(result, dpi=96, version="R2000")
    assert data.startswith(b"0\nSECTION") or b"SECTION" in data[:200]
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    assert doc.header["$INSUNITS"] == 4
    entities = list(doc.modelspace())
    assert len(entities) == len(result.paths)
    for entity in entities:
        assert entity.dxf.layer == "CENTERLINE"
        assert entity.dxftype() == "LWPOLYLINE"
    auditor = doc.audit()
    assert not auditor.has_errors


def test_dxf_y_axis_is_flipped_and_closed_flag_kept():
    path_a = VectorPath(np.array([[0.0, 0.0], [100.0, 0.0]]), closed=False)
    path_b = VectorPath(
        np.array([[0.0, 50.0], [50.0, 50.0], [50.0, 25.0]]), closed=True
    )
    result = ConversionResult(
        paths=[path_a, path_b],
        stats=ConversionStats(source_width=100, source_height=50),
        source_width=100,
        source_height=50,
        options={"dpi": 96, "dxf_version": "R2000"},
    )
    doc = ezdxf.read(
        io.StringIO(to_dxf_bytes(result, dpi=96).decode("utf-8"))
    )
    entities = list(doc.modelspace())
    assert len(entities) == 2
    scale = 25.4 / 96.0
    top = entities[0]
    ys = [point[1] for point in top.get_points("xy")]
    # DXF stores coordinates with limited precision; 0.0001 mm is plenty.
    assert all(abs(y - 50 * scale) < 1e-4 for y in ys)
    assert top.closed is False
    bottom = entities[1]
    ys = [point[1] for point in bottom.get_points("xy")]
    assert any(abs(y - 0 * scale) < 1e-4 for y in ys)
    assert any(abs(y - 25 * scale) < 1e-4 for y in ys)
    assert bottom.closed is True


def test_dxf_layers():
    center = VectorPath(np.array([[0.0, 0.0], [10.0, 10.0]]), kind="centerline")
    outer = VectorPath(
        np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]]), closed=True, kind="outline"
    )
    hole = VectorPath(
        np.array([[2.0, 2.0], [4.0, 2.0], [4.0, 4.0]]), closed=True, kind="hole"
    )
    result = ConversionResult(
        paths=[center, outer, hole],
        stats=ConversionStats(source_width=100, source_height=100),
        source_width=100,
        source_height=100,
        options={"dpi": 96, "dxf_version": "R2000"},
    )
    doc = build_document(result)
    layers = [entity.dxf.layer for entity in doc.modelspace()]
    assert layers == ["CENTERLINE", "OUTLINE", "OUTLINE"]


def test_r12_uses_polylines():
    result = convert(
        to_png(line_image()), ConvertOptions(mode="centerline", precision=80)
    )
    data = to_dxf_bytes(result, version="R12")
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    assert doc.dxfversion == "AC1009"
    assert len(list(doc.modelspace().query("POLYLINE"))) == len(result.paths)


def test_write_dxf_file(tmp_path):
    result = convert(to_png(line_image()), ConvertOptions(mode="centerline"))
    target = tmp_path / "out" / "drawing.dxf"
    returned = to_dxf(result, target)
    assert returned == target
    assert target.exists() and target.stat().st_size > 1000
    doc = ezdxf.readfile(str(target))
    assert len(list(doc.modelspace())) == len(result.paths)


def test_svg_preview():
    result = convert(
        to_png(line_image()), ConvertOptions(mode="centerline", precision=80)
    )
    svg = to_svg(result, background="#ffffff")
    assert svg.startswith("<?xml")
    assert "<svg" in svg and "</svg>" in svg
    assert f'viewBox="0 0 {result.source_width} {result.source_height}"' in svg
    assert 'data-kind="centerline"' in svg
    assert svg.count("<path") == len(result.paths)
