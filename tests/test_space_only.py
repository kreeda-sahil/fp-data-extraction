"""Space-only room construction from mixed furniture and space labels."""

from __future__ import annotations

from app.pipeline.geometry import room_rects_from_labels
from app.pipeline.pdf_load import LoadedPage, TextSpan
from app.schemas import AnalysisResult, Opening, PageInfo, Room, ScaleInfo
from app.pipeline.geom_util import polygon_from_rect_pt


def _span(text: str, x: float, y: float) -> TextSpan:
    """Build a short text span at a point."""
    return TextSpan(text=text, x0=x, y0=y, x1=x + 24, y1=y + 10)


def test_choure_like_labels_drop_furniture() -> None:
    """Sofa and table captions must not become rooms; kitchen/living keep callouts."""
    page = LoadedPage(
        width_pt=600,
        height_pt=800,
        rotation=0,
        texts=[
            _span("KITCHEN", 100, 100),
            _span("10'9\" X 8'", 110, 118),
            _span("APPLIANCES", 90, 130),
            _span("LIVING", 300, 300),
            _span("13'9 X 11'", 310, 318),
            _span("3 SEATER", 305, 340),
            _span("SOFA", 320, 360),
            _span("SIDE TABLE +", 400, 200),
            _span("10' X 12'", 200, 80),
            _span("MASTER BEDROOM", 200, 60),
            _span("TV UNIT", 280, 400),
            _span("WARDROBE", 210, 90),
        ],
    )
    rooms = room_rects_from_labels(page, mm_per_pt=10.0)
    names = [name.upper() for _rect, name, _size in rooms]
    blob = " ".join(names)
    assert "SOFA" not in blob
    assert "SEATER" not in blob
    assert "APPLIANCES" not in blob
    assert "TV UNIT" not in blob
    assert "WARDROBE" not in blob
    assert "SIDE TABLE" not in blob
    assert any("KITCHEN" in n for n in names)
    assert any("LIVING" in n for n in names)
    assert any("MASTER" in n or "BEDROOM" in n for n in names)
    kitchen = next(item for item in rooms if "KITCHEN" in item[1].upper())
    assert kitchen[2] is not None


def test_serialized_result_has_no_furniture_tokens() -> None:
    """POC-2 JSON must not mention existing furniture names."""
    mm = 2.0
    result = AnalysisResult(
        job_id="test",
        scale=ScaleInfo(mm_per_pdf_point=mm, method="test", sample_count=1),
        page=PageInfo(width_pt=100, height_pt=100, width_mm=200, height_mm=200),
        rooms=[
            Room(
                id="room_1",
                name_raw="KITCHEN",
                name_normalized="Kitchen",
                polygon=polygon_from_rect_pt(0, 0, 40, 30, mm),
                adjacent_room_ids=["room_2"],
            )
        ],
        openings=[
            Opening(
                id="opening_1",
                type="window",
                blocks_tall_furniture=True,
                leaf_polygon=polygon_from_rect_pt(0, 0, 10, 2, mm),
            )
        ],
    )
    dumped = result.model_dump_json().upper()
    for token in ("SOFA", "TV UNIT", "WARDROBE", "FRIDGE", "3 SEATER"):
        assert token not in dumped
    assert result.openings[0].blocks_tall_furniture is True
