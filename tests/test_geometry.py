import numpy as np
import pytest

from bmp2dxf.engine import geometry
from bmp2dxf.models import VectorPath


def test_rdp_removes_collinear_points():
    pts = np.array([[0, 0], [10, 0.05], [20, -0.05], [30, 0]], dtype=float)
    out = geometry.rdp(pts, 0.5)
    assert len(out) == 2
    assert np.allclose(out[0], [0, 0])
    assert np.allclose(out[-1], [30, 0])


def test_rdp_preserves_sharp_corner():
    pts = np.array([[0, 0], [25, 0], [50, 0], [50, 25], [50, 50]], dtype=float)
    out = geometry.rdp(pts, 1.0)
    assert np.allclose(out[1], [50, 0])
    assert len(out) == 3


def test_rdp_closed_keeps_loop_small():
    angles = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    pts = np.column_stack([np.cos(angles) * 100, np.sin(angles) * 100])
    out = geometry.rdp(pts, 1.0, closed=True)
    assert 8 <= len(out) <= 80
    assert not np.allclose(out[0], out[-1])
    length = geometry.polyline_length(out, closed=True)
    assert abs(length - 2 * np.pi * 100) < 5.0


def test_chaikin_keeps_endpoints():
    pts = np.array([[0, 0], [50, 20], [100, 0]], dtype=float)
    out = geometry.chaikin(pts, 2, closed=False)
    assert np.allclose(out[0], pts[0])
    assert np.allclose(out[-1], pts[-1])
    assert len(out) > len(pts)


def test_chaikin_closed_stays_closed():
    pts = np.array([[0, 0], [50, 0], [50, 50], [0, 50]], dtype=float)
    out = geometry.chaikin(pts, 2, closed=True)
    assert len(out) > len(pts)
    assert not np.allclose(out[0], out[-1])
    assert len(out) == len(pts) * 4


def test_corner_detection():
    pts = np.array([[0, 0], [25, 0], [50, 0], [50, 25], [50, 50]], dtype=float)
    corners = geometry.find_corners(pts, closed=False, threshold_deg=100)
    assert 2 in corners


def test_smooth_polyline_preserves_corner():
    pts = np.array(
        [[0, 0], [10, 0], [20, 0], [30, 0], [30, 10], [30, 20], [30, 30]],
        dtype=float,
    )
    out = geometry.smooth_polyline(
        pts, closed=False, epsilon=0.4, smoothing_iters=2, corner_angle_deg=100
    )
    assert np.min(np.linalg.norm(out - np.array([30.0, 0.0]), axis=1)) < 1e-6
    assert len(out) >= 3


def test_smooth_polyline_closed():
    angles = np.linspace(0, 2 * np.pi, 300, endpoint=False)
    pts = np.column_stack([np.cos(angles) * 80, np.sin(angles) * 80])
    out = geometry.smooth_polyline(
        pts, closed=True, epsilon=0.6, smoothing_iters=2, corner_angle_deg=100
    )
    assert len(out) >= 8
    assert not np.allclose(out[0], out[-1])
    radial = np.linalg.norm(out, axis=1)
    assert np.max(np.abs(radial - 80)) < 2.0


def test_extend_endpoint_reaches_mask_boundary():
    mask = np.zeros((40, 80), dtype=bool)
    mask[15:25, 10:70] = True
    pts = np.array([[60.0, 20.0], [40.0, 20.0], [15.0, 20.0]])
    out = geometry.extend_endpoint(pts, at_start=True, mask=mask, radius_px=5)
    assert out[0, 0] > 65
    assert np.allclose(out[-1], pts[-1])
    assert np.max(np.abs(out[:, 1] - 20)) < 0.1

    out2 = geometry.extend_endpoint(pts, at_start=False, mask=mask, radius_px=5)
    assert out2[-1, 0] < 15


def test_hermite_bridge_is_continuous():
    pts = geometry.hermite_bridge(
        np.array([0.0, 0.0]),
        np.array([1.0, 0.0]),
        np.array([20.0, 0.0]),
        np.array([-1.0, 0.0]),
        step=1.0,
    )
    assert len(pts) > 2
    assert np.max(np.abs(pts[:, 1])) < 0.01
    assert pts[0, 0] > 0
    assert pts[-1, 0] < 20


def test_densify_open_and_closed():
    open_pts = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]])
    dense = geometry.densify(open_pts, 2.0)
    assert np.allclose(dense[0], open_pts[0])
    assert np.allclose(dense[-1], open_pts[-1])
    assert np.max(np.linalg.norm(np.diff(dense, axis=0), axis=1)) <= 2.0001
    closed = geometry.densify(open_pts, 2.0, closed=True)
    assert np.linalg.norm(closed[0] - closed[-1]) < 2.0


def test_duplicate_path_removal_keeps_crossing_line():
    base = np.column_stack([np.linspace(0, 100, 50), np.zeros(50)])
    duplicate = base + np.array([0.0, 0.5])
    crossing = np.column_stack([np.linspace(40, 60, 30), np.linspace(-30, 30, 30)])
    paths = [
        VectorPath(base),
        VectorPath(duplicate),
        VectorPath(crossing),
    ]
    kept, removed = geometry.find_duplicate_paths(paths, tolerance=1.0)
    assert removed == 1
    assert len(kept) == 2
    assert any(np.allclose(p.points[-1], crossing[-1]) for p in kept)


def test_polyline_area_and_length():
    square = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=float)
    assert geometry.polygon_area(square) == pytest.approx(100.0)
    assert geometry.polyline_length(square, closed=True) == pytest.approx(40.0)
    assert geometry.bbox(square) == (0.0, 0.0, 10.0, 10.0)
