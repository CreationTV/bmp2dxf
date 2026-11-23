"""Centerline extraction: from a binary mask to clean, continuous polylines.

The implementation is a small computational-geometry pipeline around a
one-pixel skeleton:

1. skeletonise the mask and build a graph of skeleton branches,
2. contract short junction-to-junction connectors (an X crossing in a pixel
   skeleton usually appears as two nearby T junctions),
3. prune short spurs caused by stroke caps and noise,
4. pair branches at every junction by tangent continuity, so a crossing turns
   into two continuous strokes instead of four interrupted ones,
5. assemble strokes, bridge small gaps and extend retracted stroke caps,
6. simplify/smooth with corner preservation and remove duplicated overlaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable

import numpy as np
from scipy import ndimage
from skimage.morphology import skeletonize

from ..config import Tuning
from ..models import VectorPath
from . import geometry

NEIGHBOURS_8 = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


@dataclass
class _Junction:
    id: int
    center: np.ndarray
    pixels: np.ndarray = field(default_factory=lambda: np.empty((0, 2)))
    incident: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class _Edge:
    id: int
    points: np.ndarray  # work coordinates, ordered from node_a side to node_b side
    node_a: int | None
    node_b: int | None
    length: float
    closed: bool = False


@dataclass
class _Stroke:
    points: np.ndarray
    closed: bool
    start_free: bool
    end_free: bool
    start_radius: float = 1.0
    end_radius: float = 1.0


@dataclass
class CenterlineResult:
    paths: list[VectorPath] = field(default_factory=list)  # work coordinates
    junction_count: int = 0
    spur_prune_count: int = 0
    bridge_count: int = 0
    duplicate_removed: int = 0
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# skeleton and automatic mode selection
# ---------------------------------------------------------------------------

def compute_skeleton(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(skeleton, distance_transform)`` for a boolean mask."""
    mask = np.ascontiguousarray(mask, dtype=bool)
    skel = skeletonize(mask)
    dt = ndimage.distance_transform_edt(mask)
    return skel, dt


def filled_blob_fraction(
    mask: np.ndarray, dt: np.ndarray | None = None
) -> float:
    """Fraction of foreground area that sits in compact, filled blobs.

    Thin or thick *strokes* have an elongated footprint and a small distance
    transform radius relative to the image.  A filled disc, rectangle or bold
    solid logo mark has a compact footprint and a large inscribed radius.
    Those are the cases where outline tracing is the right choice.
    """
    if not mask.any():
        return 0.0
    if dt is None:
        dt = ndimage.distance_transform_edt(mask)
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    if count == 0:
        return 0.0
    h, w = mask.shape
    diagonal = math.hypot(h, w)
    total = float(mask.sum())
    indices = np.arange(1, count + 1)
    areas = np.asarray(
        ndimage.sum_labels(mask, labels, indices), dtype=np.float64
    )
    max_dt = np.asarray(ndimage.maximum(dt, labels, indices), dtype=np.float64)
    boxes = ndimage.find_objects(labels)
    blob_area = 0.0
    for idx, area in enumerate(areas):
        box = boxes[idx]
        if box is None or area < max(8.0, 0.002 * total):
            continue
        height = box[0].stop - box[0].start
        width = box[1].stop - box[1].start
        aspect = max(height, width) / max(1.0, min(height, width))
        if max_dt[idx] >= max(8.0, 0.045 * diagonal) and aspect <= 3.0:
            blob_area += float(area)
    return blob_area / max(1.0, total)


def decide_mode(mask: np.ndarray) -> tuple[str, str, np.ndarray | None, np.ndarray]:
    """Guess whether a centerline or an outline tracing suits the image.

    Uniform-width drawings (even very thick pen strokes) are treated as line
    art.  If a significant share of the black area belongs to compact filled
    blobs, outline tracing preserves the silhouette much better.
    """
    fg_area = int(mask.sum())
    if fg_area == 0:
        return "centerline", "图像内容很少，默认使用中心线模式。", None, np.zeros_like(
            mask, dtype=np.float64
        )
    dt = ndimage.distance_transform_edt(mask)
    blob_fraction = filled_blob_fraction(mask, dt)
    if blob_fraction > 0.20:
        return (
            "outline",
            f"检测到较大比例的实心填充区域（约 {blob_fraction * 100:.0f}% 的墨迹面积），"
            "自动使用轮廓模式以完整保留外形和细节。",
            None,
            dt,
        )
    skel = skeletonize(mask)
    return (
        "centerline",
        "检测为线条/均匀笔画图形，自动使用中心线模式：粗线只生成一根线。",
        skel,
        dt,
    )


# ---------------------------------------------------------------------------
# skeleton graph construction
# ---------------------------------------------------------------------------

def _neighbour_degree(skeleton: np.ndarray) -> np.ndarray:
    kernel = np.ones((3, 3), dtype=np.uint8)
    kernel[1, 1] = 0
    return ndimage.convolve(
        skeleton.astype(np.uint8), kernel, mode="constant", cval=0
    )


def _order_component(coords_rc: np.ndarray, width: int) -> tuple[np.ndarray, bool]:
    """Order the pixels of a thin component and classify it as path or cycle.

    ``coords_rc`` are ``(row, col)`` pairs.  Returns ordered ``(row, col)`` and
    a boolean telling whether the component is a closed cycle.
    """
    count = len(coords_rc)
    if count == 0:
        return coords_rc, False
    if count == 1:
        return coords_rc.copy(), False

    lookup = {
        (int(r), int(c)): i for i, (r, c) in enumerate(coords_rc)
    }
    adj: list[list[int]] = [[] for _ in range(count)]
    for i, (r, c) in enumerate(coords_rc):
        r, c = int(r), int(c)
        for dr, dc in NEIGHBOURS_8:
            j = lookup.get((r + dr, c + dc))
            if j is not None:
                adj[i].append(j)

    degrees = [len(a) for a in adj]
    ends = [i for i, d in enumerate(degrees) if d == 1]
    is_cycle = not ends
    start = ends[0] if ends else 0
    order = [start]
    seen = {start}
    current = start
    while True:
        candidates = [j for j in adj[current] if j not in seen]
        if not candidates:
            break
        if len(candidates) > 1:
            # Only possible on unusual skeletons; prefer the direction that is
            # not a sharp turn back towards the previous pixel.
            if len(order) >= 2:
                prev = coords_rc[order[-2]].astype(float)
                cur = coords_rc[order[-1]].astype(float)
                forward = cur - prev
                best = None
                best_score = -2.0
                for cand in candidates:
                    vec = coords_rc[cand].astype(float) - cur
                    norm = float(np.linalg.norm(vec) * np.linalg.norm(forward))
                    score = float(np.dot(vec, forward) / norm) if norm > 0 else -2
                    if score > best_score:
                        best_score = score
                        best = cand
                nxt = int(best)
            else:
                nxt = candidates[0]
        else:
            nxt = candidates[0]
        order.append(nxt)
        seen.add(nxt)
        current = nxt

    if is_cycle:
        # Verify the walk closed the loop and visited everything.
        closed = len(order) == count and start in adj[current]
        if len(order) != count:
            # Fallback: greedy nearest-neighbour ordering (defensive only).
            remaining = [i for i in range(count) if i not in seen]
            while remaining:
                cur_pt = coords_rc[order[-1]].astype(float)
                dists = [
                    float(np.linalg.norm(coords_rc[i].astype(float) - cur_pt))
                    for i in remaining
                ]
                nxt = remaining[int(np.argmin(dists))]
                order.append(nxt)
                seen.add(nxt)
                remaining.remove(nxt)
            closed = False
        return coords_rc[np.asarray(order, dtype=np.int64)], closed

    if len(order) != count:
        remaining = [i for i in range(count) if i not in seen]
        while remaining:
            cur_pt = coords_rc[order[-1]].astype(float)
            dists = [
                float(np.linalg.norm(coords_rc[i].astype(float) - cur_pt))
                for i in remaining
            ]
            nxt = remaining[int(np.argmin(dists))]
            order.append(nxt)
            seen.add(nxt)
            remaining.remove(nxt)
    return coords_rc[np.asarray(order, dtype=np.int64)], False


def _junction_for_end(
    pixel_rc: np.ndarray,
    zone_labels: np.ndarray,
    centres: dict[int, np.ndarray],
) -> int | None:
    r, c = int(pixel_rc[0]), int(pixel_rc[1])
    found: set[int] = set()
    h, w = zone_labels.shape
    for dr, dc in NEIGHBOURS_8:
        rr, cc = r + dr, c + dc
        if 0 <= rr < h and 0 <= cc < w:
            label = int(zone_labels[rr, cc])
            if label > 0:
                found.add(label - 1)
    if not found:
        return None
    if len(found) == 1:
        return found.pop()
    point = np.array([c, r], dtype=float)
    return min(found, key=lambda j: float(np.linalg.norm(centres[j] - point)))


def _extract_edges(
    skeleton: np.ndarray,
) -> tuple[list[_Edge], dict[int, _Junction], np.ndarray]:
    h, w = skeleton.shape
    degree = _neighbour_degree(skeleton)
    junction_pixels = skeleton & (degree >= 3)
    if not junction_pixels.any():
        junction_zone = np.zeros_like(skeleton, dtype=bool)
    else:
        junction_zone = ndimage.binary_dilation(
            junction_pixels, structure=np.ones((3, 3), dtype=bool), iterations=1
        )
    zone_labels, zone_count = ndimage.label(
        junction_zone, structure=np.ones((3, 3), dtype=bool)
    )

    # Junction centres from actual junction pixels (not the dilated zone).
    junction_pixels_by_zone: dict[int, list[np.ndarray]] = {}
    if zone_count and junction_pixels.any():
        jp_rc = np.argwhere(junction_pixels)
        for r, c in jp_rc:
            label = int(zone_labels[r, c])
            if label > 0:
                junction_pixels_by_zone.setdefault(label - 1, []).append(
                    np.array([c, r], dtype=float)
                )
    centres: dict[int, np.ndarray] = {}
    for label in range(zone_count):
        pts = junction_pixels_by_zone.get(label)
        if pts:
            centres[label] = np.mean(np.asarray(pts, dtype=float), axis=0)
        else:
            zone_skel = np.argwhere((zone_labels == label + 1) & skeleton)
            if len(zone_skel):
                centres[label] = np.mean(
                    np.column_stack([zone_skel[:, 1], zone_skel[:, 0]]), axis=0
                )

    junctions: dict[int, _Junction] = {}
    for label in range(zone_count):
        if label not in centres:
            continue
        pixels = np.asarray(junction_pixels_by_zone.get(label, []), dtype=float)
        junctions[label] = _Junction(label, centres[label], pixels)

    remaining = skeleton & ~junction_zone
    component_labels, component_count = ndimage.label(
        remaining, structure=np.ones((3, 3), dtype=bool)
    )
    if component_count == 0:
        return [], junctions, zone_labels

    coords_rc = np.argwhere(remaining)
    component_ids = component_labels[remaining]
    order = np.argsort(component_ids, kind="stable")
    coords_sorted = coords_rc[order]
    ids_sorted = component_ids[order]
    bounds = np.searchsorted(
        ids_sorted, np.arange(1, component_count + 2), side="left"
    )

    edges: list[_Edge] = []
    for comp in range(1, component_count + 1):
        start_idx = int(bounds[comp - 1])
        end_idx = int(bounds[comp])
        comp_coords = coords_sorted[start_idx:end_idx]
        if len(comp_coords) < 2:
            continue
        ordered_rc, is_cycle = _order_component(comp_coords, w)
        xy = np.column_stack(
            [ordered_rc[:, 1].astype(float), ordered_rc[:, 0].astype(float)]
        )
        if is_cycle:
            edge = _Edge(
                id=len(edges),
                points=xy,
                node_a=None,
                node_b=None,
                length=geometry.polyline_length(xy, closed=True),
                closed=True,
            )
            edges.append(edge)
            continue
        node_a = _junction_for_end(ordered_rc[0], zone_labels, centres)
        node_b = _junction_for_end(ordered_rc[-1], zone_labels, centres)
        edge = _Edge(
            id=len(edges),
            points=xy,
            node_a=node_a,
            node_b=node_b,
            length=geometry.polyline_length(xy, closed=False),
            closed=False,
        )
        edges.append(edge)
    return edges, junctions, zone_labels


# ---------------------------------------------------------------------------
# union-find for contracting junctions
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self, items: Iterable[int]):
        self.parent = {int(item): int(item) for item in items}

    def find(self, item: int) -> int:
        parent = self.parent[item]
        while parent != self.parent[parent]:
            parent = self.parent[parent]
        while self.parent[item] != parent:
            nxt = self.parent[item]
            self.parent[item] = parent
            item = nxt
        return parent

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _contract_junctions(
    edges: list[_Edge],
    junctions: dict[int, _Junction],
    tuning: Tuning,
) -> tuple[list[_Edge], dict[int, _Junction]]:
    """Merge junction clusters connected by a very short skeleton branch.

    A pixel-skeleton X crossing often becomes two T junctions joined by a
    handful of pixels.  Without contraction the pairing step would leave a
    tiny spurious stroke in the middle of the crossing.
    """
    if not junctions:
        return edges, junctions
    merge_len = max(5.0, 2.5 * tuning.work_scale)
    uf = _UnionFind(junctions.keys())
    internal: set[int] = set()
    for edge in edges:
        if (
            not edge.closed
            and edge.node_a is not None
            and edge.node_b is not None
            and edge.node_a != edge.node_b
            and edge.length <= merge_len
        ):
            uf.union(edge.node_a, edge.node_b)
            internal.add(edge.id)

    groups: dict[int, list[_Junction]] = {}
    for node_id, junction in junctions.items():
        groups.setdefault(uf.find(node_id), []).append(junction)

    merged: dict[int, _Junction] = {}
    for root, members in groups.items():
        pixels = [m.pixels for m in members if len(m.pixels)]
        if pixels:
            all_pixels = np.vstack(pixels)
            centre = np.mean(all_pixels, axis=0)
        else:
            centre = np.mean([m.center for m in members], axis=0)
        merged[root] = _Junction(
            id=root, center=centre, pixels=np.vstack(pixels) if pixels else np.empty((0, 2))
        )

    active_edges: list[_Edge] = []
    for edge in edges:
        if edge.id in internal:
            continue
        if edge.node_a is not None:
            edge.node_a = uf.find(edge.node_a)
        if edge.node_b is not None:
            edge.node_b = uf.find(edge.node_b)
        active_edges.append(edge)

    # Re-number edges so ids stay compact and match list positions.
    for new_id, edge in enumerate(active_edges):
        edge.id = new_id
    return active_edges, merged


def _build_incidence(
    edges: list[_Edge], junctions: dict[int, _Junction]
) -> dict[int, _Junction]:
    for junction in junctions.values():
        junction.incident = []
    for edge in edges:
        if edge.node_a is not None and edge.node_a in junctions:
            junctions[edge.node_a].incident.append((edge.id, 0))
        if edge.node_b is not None and edge.node_b in junctions:
            junctions[edge.node_b].incident.append((edge.id, 1))
    return {node_id: j for node_id, j in junctions.items() if j.incident}


# ---------------------------------------------------------------------------
# pruning
# ---------------------------------------------------------------------------

def _prune_edges(
    edges: list[_Edge],
    junctions: dict[int, _Junction],
    tuning: Tuning,
    dt: np.ndarray | None = None,
) -> tuple[list[_Edge], dict[int, _Junction], int]:
    active: dict[int, _Edge] = {edge.id: edge for edge in edges}
    junctions = _build_incidence(edges, junctions)
    pruned = 0
    changed = True
    rounds = 0
    while changed and rounds < 200:
        rounds += 1
        changed = False
        remove: set[int] = set()
        for edge in active.values():
            free_a = edge.node_a is None
            free_b = edge.node_b is None
            if edge.closed:
                area = geometry.polygon_area(edge.points)
                if area < tuning.min_area_px:
                    remove.add(edge.id)
                continue
            if free_a and free_b:
                if edge.length < tuning.min_length_px:
                    remove.add(edge.id)
            elif free_a or free_b:
                # Stroke caps in a pixel skeleton frequently split into a
                # short Y-shaped fork whose length scales with the stroke
                # width.  Use the local radius (distance transform) to prune
                # those without eating genuine short branches of thin art.
                spur_limit = tuning.spur_px
                if dt is not None:
                    radius = max(
                        _radius_at(edge, 0, dt), _radius_at(edge, 1, dt)
                    )
                    spur_limit = max(spur_limit, 1.5 * radius)
                if edge.length < spur_limit:
                    remove.add(edge.id)
                    pruned += 1
        if remove:
            changed = True
            for eid in remove:
                active.pop(eid, None)
            current = list(active.values())
            # Re-number for stable incidence ids.
            for new_id, edge in enumerate(current):
                edge.id = new_id
            active = {edge.id: edge for edge in current}
            for junction in junctions.values():
                junction.incident = [
                    (eid, side)
                    for eid, side in junction.incident
                    if eid in active
                ]
    # Drop junctions with no incident edges and update edge references.
    used: set[int] = set()
    for edge in active.values():
        if edge.node_a is not None:
            used.add(edge.node_a)
        if edge.node_b is not None:
            used.add(edge.node_b)
    junctions = {node_id: j for node_id, j in junctions.items() if node_id in used}
    active_edges = sorted(active.values(), key=lambda e: e.id)
    junctions = _build_incidence(active_edges, junctions)

    # A junction that lost all but one branch is simply a stroke tip.  Turning
    # it into a free end lets the cap extension below recover the full length
    # of the line (this happens at the ends of very thick strokes).
    by_id = {edge.id: edge for edge in active_edges}
    changed = True
    while changed:
        changed = False
        for node_id, junction in list(junctions.items()):
            if len(junction.incident) != 1:
                continue
            eid, side = junction.incident[0]
            edge = by_id.get(eid)
            if edge is None:
                continue
            if side == 0:
                edge.node_a = None
            else:
                edge.node_b = None
            del junctions[node_id]
            changed = True
        if changed:
            junctions = _build_incidence(active_edges, junctions)
    return active_edges, junctions, pruned


# ---------------------------------------------------------------------------
# junction branch pairing
# ---------------------------------------------------------------------------

def _pair_branches(
    edges_by_id: dict[int, _Edge],
    junctions: dict[int, _Junction],
) -> dict[tuple[int, int], tuple[int, int]]:
    """Pair branch ends at each junction by tangent continuity."""
    pair_map: dict[tuple[int, int], tuple[int, int]] = {}
    for junction in junctions.values():
        ends = [
            (eid, side)
            for eid, side in junction.incident
            if eid in edges_by_id
        ]
        if len(ends) < 2:
            continue
        directions: dict[tuple[int, int], np.ndarray] = {}
        for eid, side in ends:
            edge = edges_by_id[eid]
            tangent = geometry.endpoint_tangent(edge.points, at_start=(side == 0))
            if float(np.linalg.norm(tangent)) < 1e-9:
                tangent = np.array([1.0, 0.0])
            directions[(eid, side)] = tangent

        if len(ends) == 2:
            a, b = ends
            pair_map[a] = b
            pair_map[b] = a
            continue

        candidates: list[tuple[float, tuple[int, int], tuple[int, int]]] = []
        for i in range(len(ends)):
            for j in range(i + 1, len(ends)):
                a, b = ends[i], ends[j]
                score = -float(np.dot(directions[a], directions[b]))
                if score > 0.10:
                    candidates.append((score, a, b))
        candidates.sort(key=lambda item: item[0], reverse=True)
        used: set[tuple[int, int]] = set()
        for score, a, b in candidates:
            if a in used or b in used:
                continue
            pair_map[a] = b
            pair_map[b] = a
            used.add(a)
            used.add(b)
    return pair_map


# ---------------------------------------------------------------------------
# stroke assembly
# ---------------------------------------------------------------------------

def _radius_at(edge: _Edge, side: int, dt: np.ndarray) -> float:
    h, w = dt.shape
    if side == 0:
        x, y = edge.points[0]
    else:
        x, y = edge.points[-1]
    xi = int(round(float(x)))
    yi = int(round(float(y)))
    if 0 <= xi < w and 0 <= yi < h:
        return max(0.5, float(dt[yi, xi]))
    return 1.0


def _assemble_strokes(
    edges: list[_Edge],
    junctions: dict[int, _Junction],
    pair_map: dict[tuple[int, int], tuple[int, int]],
    dt: np.ndarray,
) -> list[_Stroke]:
    edges_by_id = {edge.id: edge for edge in edges}
    visited: set[int] = set()
    strokes: list[_Stroke] = []

    def node_of(edge: _Edge, side: int) -> int | None:
        return edge.node_a if side == 0 else edge.node_b

    def is_terminal(edge: _Edge, side: int) -> bool:
        """True if this end becomes a stroke tip after spur pruning."""
        node = node_of(edge, side)
        if node is None:
            return True
        junction = junctions.get(node)
        return junction is not None and len(junction.incident) <= 1

    def walk(start_edge_id: int, start_side: int) -> _Stroke | None:
        chunks: list[np.ndarray] = []
        edge_id, side = start_edge_id, start_side
        start_edge = edges_by_id[edge_id]
        start_node = node_of(start_edge, side)
        start_free = is_terminal(start_edge, side)
        start_radius = _radius_at(start_edge, side, dt) if start_free else 1.0
        if start_node is not None and not start_free and (edge_id, side) not in pair_map:
            chunks.append(junctions[start_node].center[None, :])
        closed = False
        end_free = False
        end_radius = 1.0
        steps = 0
        while True:
            steps += 1
            if steps > len(edges_by_id) * 4 + 10:
                break
            edge = edges_by_id.get(edge_id)
            if edge is None or edge.id in visited:
                break
            pts = edge.points if side == 0 else edge.points[::-1]
            chunks.append(pts)
            visited.add(edge.id)
            exit_side = 1 - side
            exit_node = node_of(edge, exit_side)
            if is_terminal(edge, exit_side):
                end_free = True
                end_radius = _radius_at(edge, exit_side, dt)
                break
            pair = pair_map.get((edge.id, exit_side))
            if pair is None:
                chunks.append(junctions[exit_node].center[None, :])
                break
            next_edge_id, next_side = pair
            if (next_edge_id, next_side) == (start_edge_id, start_side):
                closed = True
                break
            if next_edge_id in visited:
                break
            chunks.append(junctions[exit_node].center[None, :])
            edge_id, side = next_edge_id, next_side
        if not chunks:
            return None
        points = geometry.dedupe_points(np.vstack(chunks))
        if closed and len(points) >= 2:
            if np.allclose(points[0], points[-1]):
                points = points[:-1]
        if len(points) < 2:
            return None
        return _Stroke(
            points=points,
            closed=closed,
            start_free=start_free,
            end_free=end_free,
            start_radius=start_radius,
            end_radius=end_radius,
        )

    # Starts at free ends and unpaired junction branches.
    starts: list[tuple[int, int]] = []
    for edge in edges:
        if edge.closed:
            continue
        for side in (0, 1):
            node = node_of(edge, side)
            if node is None or (edge.id, side) not in pair_map:
                starts.append((edge.id, side))
    starts.sort()
    for edge_id, side in starts:
        if edge_id in visited:
            continue
        stroke = walk(edge_id, side)
        if stroke is not None:
            strokes.append(stroke)

    # Remaining edges are isolated loops or cycles through junctions.
    for edge in edges:
        if edge.id in visited:
            continue
        if edge.closed:
            visited.add(edge.id)
            points = geometry.dedupe_points(edge.points)
            if len(points) >= 3:
                strokes.append(
                    _Stroke(
                        points=points,
                        closed=True,
                        start_free=False,
                        end_free=False,
                    )
                )
            continue
        stroke = walk(edge.id, 0)
        if stroke is not None:
            if stroke.closed:
                strokes.append(stroke)
            else:
                strokes.append(stroke)
    return strokes


# ---------------------------------------------------------------------------
# gap bridging and endpoint extension
# ---------------------------------------------------------------------------

@dataclass
class _Endpoint:
    stroke: int
    side: str  # "start" | "end"
    position: np.ndarray
    tangent: np.ndarray
    radius: float


def _endpoints(strokes: list[_Stroke]) -> list[_Endpoint]:
    result: list[_Endpoint] = []
    for idx, stroke in enumerate(strokes):
        if stroke.closed:
            continue
        if stroke.start_free:
            tangent = geometry.endpoint_tangent(stroke.points, at_start=True)
            if float(np.linalg.norm(tangent)) > 1e-9:
                result.append(
                    _Endpoint(
                        idx, "start", stroke.points[0].copy(), tangent, stroke.start_radius
                    )
                )
        if stroke.end_free:
            tangent = geometry.endpoint_tangent(stroke.points, at_start=False)
            if float(np.linalg.norm(tangent)) > 1e-9:
                result.append(
                    _Endpoint(
                        idx, "end", stroke.points[-1].copy(), tangent, stroke.end_radius
                    )
                )
    return result


def _merge_two(
    s1: _Stroke,
    side1: str,
    s2: _Stroke,
    side2: str,
    tangent1: np.ndarray,
    tangent2: np.ndarray,
    bridge_points: np.ndarray,
) -> _Stroke:
    p1 = s1.points[0] if side1 == "start" else s1.points[-1]
    p2 = s2.points[0] if side2 == "start" else s2.points[-1]
    if s1 is s2:
        points = np.vstack([s1.points, bridge_points])
        return _Stroke(
            points=geometry.dedupe_points(points),
            closed=True,
            start_free=False,
            end_free=False,
        )
    if side1 == "end":
        first = s1.points
        first_free = s1.start_free
        first_radius = s1.start_radius
    else:
        first = s1.points[::-1]
        first_free = s1.end_free
        first_radius = s1.end_radius
    if side2 == "start":
        second = s2.points
        second_free = s2.end_free
        second_radius = s2.end_radius
    else:
        second = s2.points[::-1]
        second_free = s2.start_free
        second_radius = s2.start_radius
    points = np.vstack([first, bridge_points, second])
    return _Stroke(
        points=geometry.dedupe_points(points),
        closed=False,
        start_free=first_free,
        end_free=second_free,
        start_radius=first_radius,
        end_radius=second_radius,
    )


def _bridge_gaps(strokes: list[_Stroke], gap_px: float) -> tuple[list[_Stroke], int]:
    """Connect stroke ends that are close and tangent-aligned."""
    if gap_px <= 0.5:
        return strokes, 0
    bridges = 0
    max_rounds = 40
    for _ in range(max_rounds):
        endpoints = _endpoints(strokes)
        if len(endpoints) < 2:
            break
        best = None
        best_score = float("inf")
        for i in range(len(endpoints)):
            for j in range(i + 1, len(endpoints)):
                a, b = endpoints[i], endpoints[j]
                if a.stroke == b.stroke and a.side == b.side:
                    continue
                delta = b.position - a.position
                distance = float(np.linalg.norm(delta))
                if distance < 0.3 or distance > gap_px:
                    continue
                unit = delta / max(distance, 1e-9)
                cos_a = float(np.dot(a.tangent, unit))
                cos_b = float(np.dot(b.tangent, -unit))
                if cos_a < 0.55 or cos_b < 0.55:
                    continue
                # A smooth continuation means the two outward tangents point
                # in opposite directions.  Without this test, two arms of a
                # broken X can be joined sideways into an H shape instead of
                # continuing each diagonal through the gap.
                tangent_alignment = float(np.dot(a.tangent, b.tangent))
                if tangent_alignment > 0.15:
                    continue
                score = (
                    distance
                    + (2.0 - cos_a - cos_b) * 20.0
                    + (1.0 + tangent_alignment) * 15.0
                )
                if score < best_score:
                    best_score = score
                    best = (i, j)
        if best is None:
            break
        ia, ib = best
        a, b = endpoints[ia], endpoints[ib]
        if a.stroke == b.stroke:
            # Close an almost complete loop.
            bridge = geometry.hermite_bridge(
                a.position, a.tangent, b.position, b.tangent
            )
            base = strokes[a.stroke]
            if a.side == "end":
                points = np.vstack([base.points, bridge])
            else:
                points = np.vstack([base.points[::-1], bridge])
            strokes[a.stroke] = _Stroke(
                points=geometry.dedupe_points(points),
                closed=True,
                start_free=False,
                end_free=False,
            )
        else:
            bridge = geometry.hermite_bridge(
                a.position, a.tangent, b.position, b.tangent
            )
            merged = _merge_two(
                strokes[a.stroke],
                a.side,
                strokes[b.stroke],
                b.side,
                a.tangent,
                b.tangent,
                bridge,
            )
            for idx in sorted([a.stroke, b.stroke], reverse=True):
                strokes.pop(idx)
            strokes.append(merged)
        bridges += 1
    return strokes, bridges


def _extend_free_ends(strokes: list[_Stroke], mask: np.ndarray) -> int:
    extended = 0
    for stroke in strokes:
        if stroke.closed:
            continue
        points = stroke.points
        if stroke.start_free:
            new_points = geometry.extend_endpoint(
                points, at_start=True, mask=mask, radius_px=stroke.start_radius
            )
            if len(new_points) > len(points):
                extended += 1
                points = new_points
        if stroke.end_free:
            new_points = geometry.extend_endpoint(
                points, at_start=False, mask=mask, radius_px=stroke.end_radius
            )
            if len(new_points) > len(points):
                extended += 1
                points = new_points
        stroke.points = points
    return extended


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def extract_centerlines(
    mask: np.ndarray,
    tuning: Tuning,
    options=None,
    skeleton: np.ndarray | None = None,
    dt: np.ndarray | None = None,
) -> CenterlineResult:
    """Trace a binary mask into centerline polylines (working coordinates)."""
    mask = np.ascontiguousarray(mask, dtype=bool)
    if not mask.any():
        return CenterlineResult(warnings=["空白图像，没有可转换的内容。"])
    if skeleton is None or dt is None:
        skeleton, dt = compute_skeleton(mask)

    edges, junctions, _ = _extract_edges(skeleton)
    edges, junctions = _contract_junctions(edges, junctions, tuning)
    edges, junctions, pruned = _prune_edges(edges, junctions, tuning, dt)
    if not edges:
        return CenterlineResult(
            spur_prune_count=pruned,
            warnings=["没有提取到中心线；请尝试调整阈值或使用轮廓模式。"],
        )

    edges_by_id = {edge.id: edge for edge in edges}
    pair_map = _pair_branches(edges_by_id, junctions)
    strokes = _assemble_strokes(edges, junctions, pair_map, dt)

    # Recover retracted caps *before* measuring gaps: thinning pulls ends in
    # by roughly the stroke radius, so a 30 px gap in the drawing would
    # otherwise look like a 42 px gap in the skeleton.
    extended = _extend_free_ends(strokes, mask)
    strokes, bridges = _bridge_gaps(strokes, tuning.gap_px)

    # Filter tiny strokes before the more expensive smoothing passes.
    filtered: list[_Stroke] = []
    for stroke in strokes:
        if stroke.closed:
            if len(stroke.points) < 3:
                continue
            if geometry.polygon_area(stroke.points) < tuning.min_area_px:
                continue
        else:
            if geometry.polyline_length(stroke.points) < tuning.min_length_px:
                continue
        filtered.append(stroke)
    strokes = filtered
    if not strokes:
        return CenterlineResult(
            junction_count=len(junctions),
            spur_prune_count=pruned,
            bridge_count=bridges,
            warnings=["提取到的线条都小于最小细节尺寸；请提高精度或降低最小细节。"],
        )

    corner_angle = getattr(options, "corner_angle", 100.0) if options is not None else 100.0
    paths_work: list[VectorPath] = []
    for stroke in strokes:
        smoothed = geometry.smooth_polyline(
            stroke.points,
            closed=stroke.closed,
            epsilon=tuning.simplify_px,
            smoothing_iters=tuning.smoothing_iters,
            corner_angle_deg=corner_angle,
        )
        if len(smoothed) < 3 and stroke.closed:
            continue
        if len(smoothed) < 2:
            continue
        path = VectorPath(smoothed, closed=stroke.closed, kind="centerline")
        if path.closed:
            if geometry.polygon_area(smoothed) < tuning.min_area_px * 0.75:
                continue
        elif path.length < tuning.min_length_px * 0.8:
            continue
        paths_work.append(path)

    dedupe_tolerance = max(1.0, min(3.0, 0.5 * tuning.min_feature_px))
    paths_work, duplicates = geometry.find_duplicate_paths(
        paths_work, tolerance=dedupe_tolerance
    )

    warnings: list[str] = []
    if not paths_work:
        warnings.append("未生成有效中心线，请尝试降低阈值/提高精度。")
    return CenterlineResult(
        paths=paths_work,
        junction_count=len(junctions),
        spur_prune_count=pruned,
        bridge_count=bridges,
        duplicate_removed=duplicates,
        warnings=warnings,
    )
