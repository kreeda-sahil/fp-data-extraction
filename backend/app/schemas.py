"""Pydantic models for the floor-plan placement JSON contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OpeningType = Literal["door", "sliding_door", "window", "opening"]
KeepoutReason = Literal["door_swing", "window_clearance", "circulation"]
HingeSide = Literal["left", "right", "none"]
SwingDirection = Literal["in", "out", "unknown"]


class Point(BaseModel):
    """A 2D point. Origin is the top-left of the PDF page; +x right, +y down."""

    x: float
    y: float


class Polygon(BaseModel):
    """Closed polygon. The first point is repeated as the last when exported."""

    points_mm: list[Point]
    points_pdf: list[Point]


class ScaleInfo(BaseModel):
    """Scale recovered from dimension labels, not from the title-block NTS field."""

    mm_per_pdf_point: float
    method: str
    sample_count: int = 0
    residual_ratio: float | None = None
    flagged: bool = False


class PageInfo(BaseModel):
    """Page size in PDF points and millimetres."""

    width_pt: float
    height_pt: float
    width_mm: float
    height_mm: float
    rotation: int = 0


class Room(BaseModel):
    """A labeled occupiable space (flat, used during extraction)."""

    id: str
    name_raw: str
    name_normalized: str | None = None
    tags: list[str] = Field(default_factory=list)
    adjacent_room_ids: list[str] = Field(default_factory=list)
    polygon: Polygon
    width_mm: float | None = None
    depth_mm: float | None = None
    labeled_size: str | None = None
    confidence: float = 0.5


class Wall(BaseModel):
    """Wall segment used for context; thickness is approximate."""

    id: str
    polygon: Polygon
    room_ids: list[str] = Field(default_factory=list)


class Opening(BaseModel):
    """Door, sliding door, window, or generic wall opening."""

    id: str
    type: OpeningType
    width_mm: float | None = None
    connected_room_ids: list[str] = Field(default_factory=list)
    hinge: HingeSide | None = None
    swing_direction: SwingDirection | None = None
    leaf_polygon: Polygon | None = None
    wall_id: str | None = None
    blocks_tall_furniture: bool = False
    height_mm: float | None = None
    confidence: float = 0.5


class Keepout(BaseModel):
    """Region the furniture-placement POC must not occupy."""

    id: str
    reason: KeepoutReason
    polygon: Polygon
    room_ids: list[str] = Field(default_factory=list)
    opening_id: str | None = None


class OpeningWithKeepouts(Opening):
    """Opening with its keepouts nested underneath."""

    keepouts: list[Keepout] = Field(default_factory=list)


class WallWithOpenings(BaseModel):
    """Wall segment with openings that sit on it."""

    id: str
    polygon: Polygon
    room_ids: list[str] = Field(default_factory=list)
    openings: list[OpeningWithKeepouts] = Field(default_factory=list)


class RoomNested(BaseModel):
    """Room-by-room export: coordinates, then walls → openings → keepouts."""

    id: str
    name_raw: str
    name_normalized: str | None = None
    tags: list[str] = Field(default_factory=list)
    adjacent_room_ids: list[str] = Field(default_factory=list)
    polygon: Polygon
    width_mm: float | None = None
    depth_mm: float | None = None
    labeled_size: str | None = None
    confidence: float = 0.5
    walls: list[WallWithOpenings] = Field(default_factory=list)


class WarningItem(BaseModel):
    """Non-fatal extraction issue."""

    code: str
    message: str


class UsageInfo(BaseModel):
    """OpenAI token usage and estimated cost for the vision call."""

    model: str = "gpt-4o"
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    cost_inr: float = 0.0
    fx_usd_to_inr: float = 96.78
    vision_called: bool = False


class AnalysisResult(BaseModel):
    """Placement-ready floor-plan extraction (room-nested)."""

    job_id: str
    units: Literal["mm"] = "mm"
    coordinate_system: str = "page_top_left_y_down"
    scale: ScaleInfo
    page: PageInfo
    rooms: list[RoomNested] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)
    overlay_url: str | None = None
    vision_used: bool = False
    usage: UsageInfo = Field(default_factory=UsageInfo)
