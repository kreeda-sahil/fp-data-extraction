"""Tests for imperial/metric dimension parsing and scale recovery."""

from __future__ import annotations

from app.pipeline.scale import (
    imperial_to_mm,
    is_furniture_size,
    is_room_callout,
    parse_imperial_length,
    parse_size_pair,
)


def test_imperial_feet_and_inches() -> None:
    """Parse mixed feet-inch strings into millimetres."""
    assert parse_imperial_length("18'") == imperial_to_mm(18)
    assert parse_imperial_length("4'-7\"") == imperial_to_mm(4, 7)
    assert parse_imperial_length("13'6\"") == imperial_to_mm(13, 6)


def test_size_pair_imperial() -> None:
    """Parse a room W x D label in feet and inches."""
    pair = parse_size_pair("13'6\"X15'6\"")
    assert pair is not None
    assert pair[0] == imperial_to_mm(13, 6)
    assert pair[1] == imperial_to_mm(15, 6)


def test_size_pair_metric_metres() -> None:
    """Treat small decimal pairs as metres, matching Avinash-style sheets."""
    pair = parse_size_pair("4.350 x 4.000")
    assert pair == (4350.0, 4000.0)


def test_living_room_label() -> None:
    """Parse labels that include a room size in a single string."""
    pair = parse_size_pair("LIVING ROOM 10' X 17'")
    assert pair is not None
    assert pair[0] == imperial_to_mm(10)
    assert pair[1] == imperial_to_mm(17)


def test_room_callout_vs_furniture_size() -> None:
    """Large WxD pairs are rooms; bed/table sizes are not."""
    room = parse_size_pair("10' X 12'")
    bed = parse_size_pair("5'0\"x6'6\"")
    assert room is not None and is_room_callout(*room)
    assert bed is not None and is_furniture_size(*bed)
    assert not is_room_callout(*bed)

