"""Integration test against a text-rich sample PDF (vector path, no OpenAI)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.jobs import create_job_dir
from app.pipeline.analyze import analyze_pdf_bytes

REPO = Path(__file__).resolve().parents[1]
PODDAR = REPO / "floor-plans-pdf" / "blank-floor-plans-pdf" / "Dr. Poddar First floor.pdf"


@pytest.mark.skipif(not PODDAR.exists(), reason="sample PDF missing")
def test_poddar_extracts_rooms_and_door_keepout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Dr. Poddar has live text labels; skip vision and still recover rooms plus a keepout."""
    monkeypatch.setenv("SKIP_VISION", "true")
    data = PODDAR.read_bytes()
    job_id, job_dir = create_job_dir()
    result = analyze_pdf_bytes(data, job_id, job_dir, skip_vision=True)
    assert result.page.width_pt > 0
    assert result.scale.mm_per_pdf_point > 0
    names = " ".join(r.name_raw.upper() for r in result.rooms)
    assert result.rooms, "expected interior room polygons"
    assert any(
        token in names
        for token in ("KITCHEN", "BEDROOM", "LIVING", "TOILET", "POOJA", "LOBBY")
    ) or any(r.name_normalized for r in result.rooms)
    dumped = result.model_dump_json().upper()
    for token in ("SOFA", "TV UNIT", "FRIDGE", "3 SEATER", "SIDE TABLE"):
        assert token not in dumped
    assert all(r.name_normalized for r in result.rooms)
    assert all(r.adjacent_room_ids is not None for r in result.rooms)
    assert all(hasattr(r, "walls") for r in result.rooms)
    assert result.usage.vision_called is False
    assert result.usage.cost_usd == 0.0
    assert (job_dir / "overlay.png").exists()

    openings = [o for room in result.rooms for wall in room.walls for o in wall.openings]
    keepouts = [
        k
        for room in result.rooms
        for wall in room.walls
        for o in wall.openings
        for k in o.keepouts
    ]
    if openings:
        assert keepouts, "openings should produce keepouts"
        assert any(k.reason in {"door_swing", "window_clearance", "circulation"} for k in keepouts)
        assert all(o.blocks_tall_furniture for o in openings if o.type == "window")
