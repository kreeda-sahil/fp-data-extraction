"""Door-swing, window-clearance, and circulation keepout polygons."""

from __future__ import annotations

from shapely.geometry import Point as SPoint
from shapely.geometry import Polygon as SPolygon
from shapely.geometry import box

from app.config import CIRCULATION_MM, WINDOW_CLEARANCE_MM
from app.pipeline.geom_util import polygon_from_points_pt
from app.schemas import Keepout, Opening, Room


def _poly_from_shapely(shape, mm_per_pt: float):
    """Convert a Shapely polygon to the API Polygon model."""
    if shape.is_empty:
        return None
    geom = shape
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    coords = list(geom.exterior.coords)
    return polygon_from_points_pt([(float(x), float(y)) for x, y in coords], mm_per_pt)


def _room_centroid_pt(room: Room) -> tuple[float, float]:
    """Return the centroid of a room in PDF points."""
    pts = room.polygon.points_pdf
    return (
        sum(p.x for p in pts) / len(pts),
        sum(p.y for p in pts) / len(pts),
    )


def _opening_box_pt(opening: Opening) -> tuple[float, float, float, float] | None:
    """Axis-aligned PDF-point box of an opening leaf."""
    if not opening.leaf_polygon:
        return None
    pts = opening.leaf_polygon.points_pdf
    return (
        min(p.x for p in pts),
        min(p.y for p in pts),
        max(p.x for p in pts),
        max(p.y for p in pts),
    )


def build_keepouts(
    rooms: list[Room],
    openings: list[Opening],
    mm_per_pt: float,
    window_clearance_mm: float = WINDOW_CLEARANCE_MM,
    circulation_mm: float = CIRCULATION_MM,
) -> list[Keepout]:
    """Create keepout polygons furniture must not occupy."""
    keepouts: list[Keepout] = []
    room_by_id = {r.id: r for r in rooms}
    n = 0

    for opening in openings:
        bbox = _opening_box_pt(opening)
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        leaf = box(x0, y0, x1, y1)
        connected = [room_by_id[i] for i in opening.connected_room_ids if i in room_by_id]
        inward = None
        if connected:
            cx, cy = _room_centroid_pt(connected[0])
            inward = SPoint(cx, cy)

        if opening.type in {"door"}:
            n += 1
            swing_shape = leaf
            poly = _poly_from_shapely(swing_shape, mm_per_pt)
            if poly:
                keepouts.append(
                    Keepout(
                        id=f"keepout_{n}",
                        reason="door_swing",
                        polygon=poly,
                        room_ids=opening.connected_room_ids,
                        opening_id=opening.id,
                    )
                )
            circ_pt = circulation_mm / mm_per_pt
            approach = _approach_box(leaf, inward, circ_pt)
            n += 1
            poly = _poly_from_shapely(approach, mm_per_pt)
            if poly:
                keepouts.append(
                    Keepout(
                        id=f"keepout_{n}",
                        reason="circulation",
                        polygon=poly,
                        room_ids=opening.connected_room_ids,
                        opening_id=opening.id,
                    )
                )
        elif opening.type == "sliding_door":
            circ_pt = circulation_mm / mm_per_pt
            approach = _approach_box(leaf, inward, circ_pt)
            n += 1
            poly = _poly_from_shapely(approach, mm_per_pt)
            if poly:
                keepouts.append(
                    Keepout(
                        id=f"keepout_{n}",
                        reason="circulation",
                        polygon=poly,
                        room_ids=opening.connected_room_ids,
                        opening_id=opening.id,
                    )
                )
        elif opening.type == "window":
            clear_pt = window_clearance_mm / mm_per_pt
            strip = _window_strip(leaf, inward, clear_pt)
            n += 1
            poly = _poly_from_shapely(strip, mm_per_pt)
            if poly:
                keepouts.append(
                    Keepout(
                        id=f"keepout_{n}",
                        reason="window_clearance",
                        polygon=poly,
                        room_ids=opening.connected_room_ids,
                        opening_id=opening.id,
                    )
                )
    return keepouts


def _approach_box(leaf: SPolygon, inward: SPoint | None, depth_pt: float) -> SPolygon:
    """Buffer a door approach on the interior side, or a symmetric buffer."""
    if inward is None:
        return leaf.buffer(depth_pt)
    minx, miny, maxx, maxy = leaf.bounds
    w, h = maxx - minx, maxy - miny
    cx, cy = inward.x, inward.y
    if w >= h:
        # Door in a horizontal wall: approach toward the room in Y
        if cy > (miny + maxy) / 2:
            return box(minx, maxy, maxx, maxy + depth_pt).union(leaf)
        return box(minx, miny - depth_pt, maxx, miny).union(leaf)
    if cx > (minx + maxx) / 2:
        return box(maxx, miny, maxx + depth_pt, maxy).union(leaf)
    return box(minx - depth_pt, miny, minx, maxy).union(leaf)


def _window_strip(leaf: SPolygon, inward: SPoint | None, depth_pt: float) -> SPolygon:
    """Interior clearance strip along a window."""
    return _approach_box(leaf, inward, depth_pt)
