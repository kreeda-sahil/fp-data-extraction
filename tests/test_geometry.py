"""Layer classification tests."""

from __future__ import annotations

from app.pipeline.geometry import classify_layer


def test_window_layers_include_short_cad_names() -> None:
    """A-WIN style layers must count as windows, not miss the 'window' substring."""
    assert classify_layer("A-WIN") == "window"
    assert classify_layer("WIN - A") == "window"
    assert classify_layer("PL - WINDOWS") == "window"


def test_door_swing_not_window() -> None:
    """Door swing layers contain 'win' inside 'swing' and must stay doors."""
    assert classify_layer("A - DOOR SWING") == "door"
    assert classify_layer("A-DOOR") == "door"
