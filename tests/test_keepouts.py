"""Keepout polygon tests using synthetic openings."""

from __future__ import annotations

from app.pipeline.geom_util import polygon_from_rect_pt
from app.pipeline.keepouts import build_keepouts
from app.schemas import Opening, Room


def test_door_creates_swing_and_circulation() -> None:
    """A hinged door must emit door_swing and circulation keepouts."""
    mm = 2.0
    room = Room(
        id="room_1",
        name_raw="Living",
        name_normalized="Living Room",
        polygon=polygon_from_rect_pt(0, 0, 200, 200, mm),
    )
    opening = Opening(
        id="opening_1",
        type="door",
        width_mm=900,
        connected_room_ids=["room_1"],
        leaf_polygon=polygon_from_rect_pt(90, 0, 110, 40, mm),
    )
    keepouts = build_keepouts([room], [opening], mm, window_clearance_mm=600, circulation_mm=900)
    reasons = {k.reason for k in keepouts}
    assert "door_swing" in reasons
    assert "circulation" in reasons
    swing = next(k for k in keepouts if k.reason == "door_swing")
    assert len(swing.polygon.points_mm) >= 4
    xs = [p.x for p in swing.polygon.points_mm]
    ys = [p.y for p in swing.polygon.points_mm]
    assert max(xs) - min(xs) > 0
    assert max(ys) - min(ys) > 0


def test_sliding_door_has_no_swing() -> None:
    """Sliding doors must not create a door_swing keepout."""
    mm = 2.0
    room = Room(
        id="room_1",
        name_raw="Kitchen",
        name_normalized="Kitchen",
        polygon=polygon_from_rect_pt(0, 0, 200, 200, mm),
    )
    opening = Opening(
        id="opening_1",
        type="sliding_door",
        width_mm=1800,
        connected_room_ids=["room_1"],
        hinge="none",
        leaf_polygon=polygon_from_rect_pt(20, 0, 80, 8, mm),
    )
    keepouts = build_keepouts([room], [opening], mm)
    reasons = {k.reason for k in keepouts}
    assert "door_swing" not in reasons
    assert "circulation" in reasons


def test_window_clearance_strip() -> None:
    """Windows emit an interior clearance keepout."""
    mm = 2.0
    room = Room(
        id="room_1",
        name_raw="Bedroom",
        name_normalized="Master Bedroom",
        polygon=polygon_from_rect_pt(0, 0, 300, 300, mm),
    )
    opening = Opening(
        id="opening_1",
        type="window",
        width_mm=1200,
        connected_room_ids=["room_1"],
        leaf_polygon=polygon_from_rect_pt(100, 0, 160, 6, mm),
    )
    keepouts = build_keepouts([room], [opening], mm, window_clearance_mm=600)
    assert any(k.reason == "window_clearance" for k in keepouts)
