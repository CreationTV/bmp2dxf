"""Polyline maths: simplification, corner preserving smoothing, bridging.

The helpers in this module work on ``(N, 2)`` float arrays in working-image
coordinates (x, y) and are deliberately free of image semantics so they can
be unit tested on their own.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
from scipy.spatial import cKDTree

from ..models import VectorPath


# ---------------------------------------------------------------------------
# basic helpers
# ---------------------------------------------------------------------------

def dedupe_points(points: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 2:
        return pts
    keep = np.ones(len(pts), dtype=bool)
    keep[1:] = np.linalg.norm(np.diff(pts, axis=0), axis=1) > eps
    return pts[keep]


def polyline_length(points: np.ndarray, closed: bool = False) -> float:
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 2:
        return 0.0
    total = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
    if closed:
        total += float(np.linalg.norm(pts[0] - pts[-1]))
    return total


def polygon_area(points: np.ndarray) -> float:
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 3:
        return 0.0
    x, y = pts[:, 0], pts[:, 1]
    return abs(0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def bbox(points: np.ndarray) -> tuple[float, float, float, float]:
    pts = np.asarray(points, dtype=np.float64)
    return (
        float(pts[:, 0].min()),
        float(pts[:, 1].min()),
        float(pts[:, 0].max()),
        float(pts[:, 1].max()),
    )


def bbox_overlap(a: tuple[float, ...], b: tuple[float, ...], pad: float = 0.0) -> bool:
    return not (
        a[2] + pad < b[0]
        or b[2] + pad < a[0]
        or a[3] + pad < b[1]
        or b[3] + pad < a[1]
    )


def densify(points: np.ndarray, step: float, closed: bool = False) -> np.ndarray:
    """Resample a polyline so consecutive samples are at most ``step`` apart."""
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 2 or step <= 0:
        return pts
    if closed and not np.allclose(pts[0], pts[-1]):
        pts = np.vstack([pts, pts[:1]])
    seg = np.diff(pts, axis=0)
    lengths = np.linalg.norm(seg, axis=1)
    chunks: list[np.ndarray] = []
    for start, seg_vec, seg_len in zip(pts[:-1], seg, lengths):
        if seg_len <= 0:
            continue
        count = max(1, int(math.ceil(seg_len / step)))
        ts = np.linspace(0.0, 1.0, count + 1)[:-1]
        chunks.append(start + ts[:, None] * seg_vec)
    chunks.append(pts[-1:])
    return np.vstack(chunks)


# ---------------------------------------------------------------------------
# Ramer-Douglas-Peucker
# ---------------------------------------------------------------------------

def _point_segment_distances(
    points: np.ndarray, start: np.ndarray, end: np.ndarray
) -> np.ndarray:
    ab = end - start
    denom = float(np.dot(ab, ab))
    ap = points - start
    if denom <= 1e-12:
        return np.linalg.norm(ap, axis=1)
    t = np.clip((ap @ ab) / denom, 0.0, 1.0)
    projected = start + t[:, None] * ab
    return np.linalg.norm(points - projected, axis=1)


def rdp(points: np.ndarray, epsilon: float, closed: bool = False) -> np.ndarray:
    """Iterative vectorised Ramer-Douglas-Peucker simplification."""
    pts = dedupe_points(np.asarray(points, dtype=np.float64))
    if len(pts) <= 2:
        return pts
    if epsilon <= 0:
        return pts

    original_len = len(pts)
    if closed:
        pts = np.vstack([pts, pts[:1]])
    elif np.allclose(pts[0], pts[-1]) and len(pts) > 2:
        # An explicit closing point on an open path would create a degenerate
        # double end; drop it and treat the path as closed.
        pts = pts[:-1]
        closed = True
        pts = np.vstack([pts, pts[:1]])

    keep = np.zeros(len(pts), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        segment = pts[first + 1 : last]
        distances = _point_segment_distances(segment, pts[first], pts[last])
        if distances.size == 0:
            continue
        local = int(np.argmax(distances))
        if float(distances[local]) > epsilon:
            index = first + 1 + local
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))

    result = pts[keep]
    if closed and len(result) > 1:
        result = result[:-1]
    if len(result) == 1 and original_len > 1:
        # Degenerate simplification - fall back to two extreme points.
        result = np.vstack([pts[0], pts[len(pts) // 2]])
    return result


# ---------------------------------------------------------------------------
# corner preserving Chaikin smoothing
# ---------------------------------------------------------------------------

def chaikin(points: np.ndarray, iterations: int, closed: bool = False) -> np.ndarray:
    pts = dedupe_points(np.asarray(points, dtype=np.float64))
    if iterations <= 0 or len(pts) < 3:
        return pts
    for _ in range(iterations):
        n = len(pts)
        if closed:
            nxt = np.roll(pts, -1, axis=0)
            q = 0.75 * pts + 0.25 * nxt
            r = 0.25 * pts + 0.75 * nxt
            new = np.empty((2 * n, 2), dtype=np.float64)
            new[0::2] = q
            new[1::2] = r
            pts = new
        else:
            nxt = pts[1:]
            cur = pts[:-1]
            q = 0.75 * cur + 0.25 * nxt
            r = 0.25 * cur + 0.75 * nxt
            new = np.empty((2 * (n - 1) + 2, 2), dtype=np.float64)
            new[0] = pts[0]
            new[-1] = pts[-1]
            new[1:-1:2] = q
            new[2:-1:2] = r
            pts = new
    return pts


def _interior_angles(points: np.ndarray, closed: bool) -> np.ndarray:
    """Interior angle (radians) at each vertex; endpoints get pi for open paths."""
    pts = points
    n = len(pts)
    angles = np.full(n, math.pi, dtype=np.float64)
    if n < 3:
        return angles
    if closed:
        prev = np.roll(pts, 1, axis=0)
        nxt = np.roll(pts, -1, axis=0)
    else:
        prev = np.vstack([pts[:1], pts[:-1]])
        nxt = np.vstack([pts[1:], pts[-1:]])
    a = prev - pts
    b = nxt - pts
    norm = np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)
    valid = norm > 1e-12
    cosang = np.ones(n, dtype=np.float64)
    cosang[valid] = np.clip(
        (a[valid] * b[valid]).sum(axis=1) / norm[valid], -1.0, 1.0
    )
    angles[valid] = np.arccos(cosang[valid])
    if not closed:
        angles[0] = angles[-1] = math.pi
    return angles


def find_corners(
    points: np.ndarray, closed: bool, threshold_deg: float = 100.0
) -> list[int]:
    pts = dedupe_points(points)
    if len(pts) < 3:
        return []
    angles = np.degrees(_interior_angles(pts, closed))
    threshold = float(threshold_deg) if threshold_deg > 0 else 0.0
    corners: list[int] = []
    if closed:
        for i in range(len(pts)):
            if angles[i] < threshold:
                corners.append(i)
    else:
        for i in range(1, len(pts) - 1):
            if angles[i] < threshold:
                corners.append(i)
    # Suppress dense runs of corner detections (keep the sharpest one).
    if len(corners) > 1:
        filtered: list[int] = []
        for idx in corners:
            if not filtered or idx - filtered[-1] > 2:
                filtered.append(idx)
            else:
                # keep the sharper corner of two adjacent candidates
                if angles[idx] < angles[filtered[-1]]:
                    filtered[-1] = idx
        corners = filtered
    return corners


def _smooth_section(
    section: np.ndarray, iterations: int, epsilon: float, closed: bool
) -> np.ndarray:
    if len(section) < 2:
        return section
    if len(section) == 2:
        return section.copy()
    if iterations > 0:
        section = chaikin(section, iterations, closed=closed)
    return rdp(section, epsilon, closed=closed)


def smooth_polyline(
    points: np.ndarray,
    closed: bool,
    epsilon: float,
    smoothing_iters: int,
    corner_angle_deg: float = 100.0,
) -> np.ndarray:
    """Simplify and smooth a polyline while preserving sharp corners.

    The input is usually a jaggy 8-connected skeleton path or a marching
    squares contour.  A small pre-simplification removes pixel noise, sharp
    corners are split off and kept, and the remaining sections are rounded
    with Chaikin corner cutting before a final Douglas-Peucker pass.
    """
    pts = dedupe_points(np.asarray(points, dtype=np.float64))
    if len(pts) < 2:
        return pts
    if len(pts) == 2:
        return pts
    if closed and np.allclose(pts[0], pts[-1]) and len(pts) > 3:
        pts = pts[:-1]
    if len(pts) < 3:
        return pts

    pre_eps = min(0.6, max(0.22, epsilon * 0.5))
    base = rdp(pts, pre_eps, closed=closed)
    if len(base) < 3:
        base = pts

    corners = find_corners(base, closed, corner_angle_deg)
    if not corners:
        if closed:
            if smoothing_iters > 0:
                base = chaikin(base, smoothing_iters, closed=True)
            result = rdp(base, epsilon, closed=True)
        else:
            result = _smooth_section(base, smoothing_iters, epsilon, closed=False)
        return dedupe_points(result)

    # Open path: simple ordered sections.
    if not closed:
        result_parts: list[np.ndarray] = []
        start = 0
        for corner in corners + [len(base) - 1]:
            section = base[start : corner + 1]
            smooth = _smooth_section(section, smoothing_iters, epsilon, closed=False)
            if len(result_parts) == 0:
                result_parts.append(smooth)
            else:
                result_parts.append(smooth[1:])
            start = corner
        result = np.vstack(result_parts)
        return dedupe_points(result)

    # Closed path: rotate so the first corner is at index 0, then smooth each
    # arc between consecutive corners as an open section.
    base = np.roll(base, -corners[0], axis=0)
    shifted = [(c - corners[0]) % len(base) for c in corners]
    shifted.sort()
    if shifted[0] != 0:
        shifted.insert(0, 0)
    sections: list[np.ndarray] = []
    for a, b in zip(shifted, shifted[1:] + [len(base)]):
        section = base[a : b + 1] if b < len(base) else np.vstack([base[a:], base[:1]])
        sections.append(_smooth_section(section, smoothing_iters, epsilon, closed=False))
    # merge, dropping duplicated shared corners
    merged = sections[0].copy()
    for section in sections[1:]:
        merged = np.vstack([merged, section[1:]])
    if len(merged) > 1 and np.allclose(merged[0], merged[-1]):
        merged = merged[:-1]
    return dedupe_points(merged)


# ---------------------------------------------------------------------------
# tangents, gap bridging and endpoint extension
# ---------------------------------------------------------------------------

def endpoint_tangent(
    points: np.ndarray, at_start: bool, span: float = 8.0
) -> np.ndarray:
    """Unit tangent pointing *outwards* (away from the stroke body)."""
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 2:
        return np.array([0.0, 0.0])
    if at_start:
        anchor = pts[0]
        rest = pts[1:]
        dist = np.linalg.norm(rest - anchor, axis=1)
        idx = int(np.searchsorted(dist, span))
        if idx >= len(rest):
            idx = len(rest) - 1
        direction = anchor - rest[idx]
    else:
        anchor = pts[-1]
        rest = pts[:-1][::-1]
        dist = np.linalg.norm(rest - anchor, axis=1)
        idx = int(np.searchsorted(dist, span))
        if idx >= len(rest):
            idx = len(rest) - 1
        direction = anchor - rest[idx]
    norm = float(np.linalg.norm(direction))
    if norm < 1e-9:
        return np.array([0.0, 0.0])
    return direction / norm


def hermite_bridge(
    start: np.ndarray,
    tangent_start: np.ndarray,
    end: np.ndarray,
    tangent_end: np.ndarray,
    step: float = 1.0,
) -> np.ndarray:
    """Tangent continuous cubic between two open stroke ends.

    ``tangent_start`` points out of the first stroke and ``tangent_end`` out of
    the second one.  The returned array excludes both endpoint coordinates.
    """
    start = np.asarray(start, dtype=np.float64)
    end = np.asarray(end, dtype=np.float64)
    distance = float(np.linalg.norm(end - start))
    if distance < 1e-6:
        return np.empty((0, 2), dtype=np.float64)
    m0 = np.asarray(tangent_start, dtype=np.float64) * distance
    m1 = -np.asarray(tangent_end, dtype=np.float64) * distance
    count = max(2, int(math.ceil(distance / max(step, 0.5))))
    t = np.linspace(0.0, 1.0, count + 1)[1:-1]
    t2 = t * t
    t3 = t2 * t
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    return (
        h00[:, None] * start
        + h10[:, None] * m0
        + h01[:, None] * end
        + h11[:, None] * m1
    )


def extend_endpoint(
    points: np.ndarray,
    at_start: bool,
    mask: np.ndarray,
    radius_px: float,
    max_extra: float | None = None,
) -> np.ndarray:
    """Push a skeleton end towards the stroke cap.

    Thinning retracts stroke ends by roughly half the stroke width.  Walking
    along the endpoint tangent until the foreground mask ends recovers the
    original cap position and avoids visibly shortened lines.
    """
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < 2:
        return pts
    if max_extra is None:
        max_extra = max(1.0, float(radius_px) * 1.1 + 1.0)
    if max_extra <= 0.5:
        return pts
    tangent = endpoint_tangent(pts, at_start)
    if float(np.linalg.norm(tangent)) < 1e-9:
        return pts
    anchor = pts[0] if at_start else pts[-1]
    h, w = mask.shape
    step = 0.5
    distance = 0.0
    last_inside = anchor
    while distance + step <= max_extra:
        distance += step
        candidate = anchor + tangent * distance
        x = int(round(candidate[0]))
        y = int(round(candidate[1]))
        if x < 0 or y < 0 or x >= w or y >= h or not mask[y, x]:
            break
        last_inside = candidate
    if float(np.linalg.norm(last_inside - anchor)) < 0.5:
        return pts
    if at_start:
        # Prepend far -> near so the path starts at the recovered cap.
        seg = last_inside - anchor
        length = float(np.linalg.norm(seg))
        count = max(1, int(math.ceil(length / 1.0)))
        samples = [anchor + seg * (i / count) for i in range(count, 0, -1)]
        return np.vstack([np.array(samples, dtype=np.float64), pts])
    seg = last_inside - anchor
    length = float(np.linalg.norm(seg))
    count = max(1, int(math.ceil(length / 1.0)))
    samples = [anchor + seg * (i / count) for i in range(1, count + 1)]
    return np.vstack([pts, np.array(samples, dtype=np.float64)])


# ---------------------------------------------------------------------------
# duplicate / overlap removal
# ---------------------------------------------------------------------------

def find_duplicate_paths(
    paths: Iterable[VectorPath], tolerance: float = 1.2, min_coverage: float = 0.78
) -> tuple[list[VectorPath], int]:
    """Drop paths that trace almost exactly the same geometry as a longer one.

    Only a fraction of samples near another *longer* path is considered a
    duplicate, so crossing lines are never removed.
    """
    items = list(paths)
    if len(items) <= 1:
        return items, 0
    order = sorted(range(len(items)), key=lambda i: items[i].length, reverse=True)
    kept: list[int] = []
    trees: dict[int, cKDTree] = {}
    removed: set[int] = set()
    boxes = {i: bbox(items[i].points) for i in range(len(items))}

    for idx in order:
        path = items[idx]
        is_dup = False
        for keep_idx in kept:
            longer = items[keep_idx]
            if not bbox_overlap(boxes[idx], boxes[keep_idx], pad=tolerance * 2):
                continue
            if path.length > longer.length * 1.02:
                continue
            tree = trees.get(keep_idx)
            if tree is None:
                dense = densify(longer.points, max(tolerance * 0.6, 0.5), longer.closed)
                tree = cKDTree(dense)
                trees[keep_idx] = tree
            samples = densify(path.points, max(tolerance * 1.5, 1.0), path.closed)
            if len(samples) == 0:
                continue
            distances, _ = tree.query(samples, k=1)
            coverage = float(np.mean(distances <= tolerance))
            if coverage >= min_coverage:
                is_dup = True
                break
        if is_dup:
            removed.add(idx)
        else:
            kept.append(idx)

    if not removed:
        return items, 0
    return [p for i, p in enumerate(items) if i not in removed], len(removed)
