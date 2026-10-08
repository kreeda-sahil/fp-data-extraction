"""Room-by-room nesting: walls → openings → keepouts."""

from __future__ import annotations

from app.pipeline.geom_util import polygon_from_rect_pt
from app.pipeline.nest import nest_rooms
from app.schemas import Keepout, Opening, Room, Wall


def _room(rid: str, x0: float, y0: float, x1: float, y1: float) -> Room:
    """Build a simple room rectangle in PDF points."""
    mm = 2.0
    return Room(
        id=rid,
        name_raw=rid.upper(),
        name_normalized="Living Room",
        polygon=polygon_from_rect_pt(x0, y0, x1, y1, mm),
        width_mm=(x1 - x0) * mm,
        depth_mm=(y1 - y0) * mm,
    )


def test_opening_nests_under_nearest_wall_with_keepouts() -> None:
    """A door near wall A must land under wall A with its keepouts."""
    mm = 2.0
    room = _room("room_1", 0, 0, 200, 200)
    wall_a = Wall(
        id="wall_a",
        polygon=polygon_from_rect_pt(90, 0, 110, 8, mm),
        room_ids=["room_1"],
    )
    wall_b = Wall(
        id="wall_b",
        polygon=polygon_from_rect_pt(0, 90, 8, 110, mm),
        room_ids=["room_1"],
    )
    opening = Opening(
        id="opening_1",
        type="door",
        width_mm=900,
        connected_room_ids=["room_1"],
        leaf_polygon=polygon_from_rect_pt(95, 0, 105, 40, mm),
    )
    keepouts = [
        Keepout(
            id="keepout_1",
            reason="door_swing",
            polygon=polygon_from_rect_pt(95, 0, 105, 40, mm),
            room_ids=["room_1"],
            opening_id="opening_1",
        ),
        Keepout(
            id="keepout_2",
            reason="circulation",
            polygon=polygon_from_rect_pt(90, 40, 110, 70, mm),
            room_ids=["room_1"],
            opening_id="opening_1",
        ),
    ]
    nested = nest_rooms([room], [wall_a, wall_b], [opening], keepouts)
    assert len(nested) == 1
    by_id = {w.id: w for w in nested[0].walls}
    assert "wall_a" in by_id
    assert len(by_id["wall_a"].openings) == 1
    assert by_id["wall_a"].openings[0].id == "opening_1"
    assert {k.reason for k in by_id["wall_a"].openings[0].keepouts} == {
        "door_swing",
        "circulation",
    }
    assert by_id["wall_b"].openings == []


def test_shared_door_appears_in_both_rooms() -> None:
    """A door connecting two rooms is duplicated under each room tree."""
    mm = 2.0
    room_a = _room("room_1", 0, 0, 100, 100)
    room_b = _room("room_2", 100, 0, 200, 100)
    wall_a = Wall(
        id="wall_shared",
        polygon=polygon_from_rect_pt(95, 40, 105, 60, mm),
        room_ids=["room_1", "room_2"],
    )
    opening = Opening(
        id="opening_shared",
        type="door",
        width_mm=900,
        connected_room_ids=["room_1", "room_2"],
        leaf_polygon=polygon_from_rect_pt(96, 42, 104, 58, mm),
    )
    keepouts = [
        Keepout(
            id="keepout_1",
            reason="door_swing",
            polygon=polygon_from_rect_pt(96, 42, 104, 58, mm),
            opening_id="opening_shared",
        )
    ]
    nested = nest_rooms([room_a, room_b], [wall_a], [opening], keepouts)
    assert len(nested) == 2
    for room in nested:
        openings = [o for w in room.walls for o in w.openings]
        assert any(o.id == "opening_shared" for o in openings)


def test_unassigned_opening_uses_synthetic_wall() -> None:
    """Openings with no nearby wall land under wall_unassigned for that room."""
    mm = 2.0
    room = _room("room_1", 0, 0, 200, 200)
    wall = Wall(
        id="wall_far",
        polygon=polygon_from_rect_pt(0, 0, 10, 10, mm),
        room_ids=["room_1"],
    )
    opening = Opening(
        id="opening_orphan",
        type="window",
        width_mm=1200,
        connected_room_ids=["room_1"],
        blocks_tall_furniture=True,
        leaf_polygon=polygon_from_rect_pt(180, 180, 200, 190, mm),
    )
    nested = nest_rooms(
        [room],
        [wall],
        [opening],
        [],
        max_walls_per_room=40,
    )
    walls = nested[0].walls
    unassigned = next(w for w in walls if w.id.startswith("wall_unassigned"))
    assert len(unassigned.openings) == 1
    assert unassigned.openings[0].id == "opening_orphan"
