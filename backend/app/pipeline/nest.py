"""Build room-by-room nested JSON: room → walls → openings → keepouts."""

from __future__ import annotations

from app.config import MAX_WALLS_PER_ROOM, OPENING_WALL_MAX_DIST_PT
from app.schemas import (
    Keepout,
    Opening,
    OpeningWithKeepouts,
    Room,
    RoomNested,
    Wall,
    WallWithOpenings,
)


def _polygon_bbox(polygon) -> tuple[float, float, float, float]:
    """Return axis-aligned PDF-point bounds of a polygon."""
    pts = polygon.points_pdf
    return (
        min(p.x for p in pts),
        min(p.y for p in pts),
        max(p.x for p in pts),
        max(p.y for p in pts),
    )


def _bbox_centroid(box: tuple[float, float, float, float]) -> tuple[float, float]:
    """Return the centre of an axis-aligned box."""
    return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0


def _bbox_area(box: tuple[float, float, float, float]) -> float:
    """Return box area in PDF points squared."""
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _centroid_distance(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    """Euclidean distance between two box centres."""
    ax, ay = _bbox_centroid(a)
    bx, by = _bbox_centroid(b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _nearest_wall(
    opening: Opening,
    walls: list[Wall],
    max_dist_pt: float = OPENING_WALL_MAX_DIST_PT,
) -> Wall | None:
    """Pick the closest wall polygon to an opening leaf, or None if too far."""
    if opening.leaf_polygon is None or not walls:
        return None
    o_box = _polygon_bbox(opening.leaf_polygon)
    best: Wall | None = None
    best_dist = float("inf")
    for wall in walls:
        dist = _centroid_distance(o_box, _polygon_bbox(wall.polygon))
        if dist < best_dist:
            best_dist = dist
            best = wall
    if best is None or best_dist > max_dist_pt:
        return None
    return best


def nest_rooms(
    rooms: list[Room],
    walls: list[Wall],
    openings: list[Opening],
    keepouts: list[Keepout],
    *,
    max_walls_per_room: int = MAX_WALLS_PER_ROOM,
) -> list[RoomNested]:
    """Nest walls, openings, and keepouts under each room for POC 2."""
    keepouts_by_opening: dict[str, list[Keepout]] = {}
    for keepout in keepouts:
        if not keepout.opening_id:
            continue
        keepouts_by_opening.setdefault(keepout.opening_id, []).append(keepout)

    nested: list[RoomNested] = []
    for room in rooms:
        room_walls = [w for w in walls if room.id in w.room_ids]
        room_walls.sort(key=lambda w: -_bbox_area(_polygon_bbox(w.polygon)))
        room_walls = room_walls[:max_walls_per_room]

        wall_openings: dict[str, list[OpeningWithKeepouts]] = {w.id: [] for w in room_walls}
        unassigned: list[OpeningWithKeepouts] = []

        for opening in openings:
            if room.id not in opening.connected_room_ids:
                continue
            opening_copy = opening.model_copy(deep=True)
            nested_opening = OpeningWithKeepouts(
                **opening_copy.model_dump(),
                keepouts=list(keepouts_by_opening.get(opening.id, [])),
            )
            wall = _nearest_wall(opening, room_walls)
            if wall is None:
                unassigned.append(nested_opening)
            else:
                nested_opening.wall_id = wall.id
                wall_openings[wall.id].append(nested_opening)

        walls_out: list[WallWithOpenings] = [
            WallWithOpenings(
                id=wall.id,
                polygon=wall.polygon,
                room_ids=list(wall.room_ids),
                openings=wall_openings.get(wall.id, []),
            )
            for wall in room_walls
        ]
        if unassigned:
            walls_out.append(
                WallWithOpenings(
                    id=f"wall_unassigned_{room.id}",
                    polygon=room.polygon,
                    room_ids=[room.id],
                    openings=unassigned,
                )
            )

        nested.append(
            RoomNested(
                id=room.id,
                name_raw=room.name_raw,
                name_normalized=room.name_normalized,
                tags=list(room.tags),
                adjacent_room_ids=list(room.adjacent_room_ids),
                polygon=room.polygon,
                width_mm=room.width_mm,
                depth_mm=room.depth_mm,
                labeled_size=room.labeled_size,
                confidence=room.confidence,
                walls=walls_out,
            )
        )
    return nested
