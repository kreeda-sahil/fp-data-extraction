"""Orchestrate load → scale → geometry → vision → keepouts → nest → overlay."""

from __future__ import annotations

from pathlib import Path

from app.catalog_spaces import is_furniture_caption, normalize_space_name
from app.config import RASTER_DPI, SKIP_VISION
from app.pipeline.cost import empty_usage
from app.pipeline.geometry import (
    assign_adjacency,
    build_rooms_walls_openings,
    recompute_opening_rooms,
)
from app.pipeline.keepouts import build_keepouts
from app.pipeline.nest import nest_rooms
from app.pipeline.overlay import render_overlay
from app.pipeline.pdf_load import load_pdf
from app.pipeline.scale import recover_scale
from app.pipeline.vision import apply_vision
from app.schemas import AnalysisResult, PageInfo, UsageInfo, WarningItem


def analyze_pdf_bytes(
    data: bytes,
    job_id: str,
    job_dir: Path,
    skip_vision: bool | None = None,
) -> AnalysisResult:
    """Run the hybrid extraction pipeline on an uploaded PDF."""
    use_vision = not (SKIP_VISION if skip_vision is None else skip_vision)
    warnings: list[WarningItem] = []
    page = load_pdf(data, dpi=RASTER_DPI)
    scale, scale_warnings, _sizes = recover_scale(page)
    warnings.extend(scale_warnings)
    mm = scale.mm_per_pdf_point

    rooms, walls, openings, candidates = build_rooms_walls_openings(page, mm, warnings)

    vision_used = False
    usage: UsageInfo = empty_usage(vision_called=False)
    if use_vision:
        rooms, openings, vision_used, usage = apply_vision(
            page, rooms, openings, candidates, mm, warnings
        )

    rooms = [
        r
        for r in rooms
        if r.name_normalized and not is_furniture_caption(r.name_raw)
    ]
    for room in rooms:
        if room.name_normalized is None:
            room.name_normalized = normalize_space_name(room.name_raw)
    rooms = [r for r in rooms if r.name_normalized]
    recompute_opening_rooms(rooms, openings)
    assign_adjacency(rooms, openings)

    keepouts = build_keepouts(rooms, openings, mm)
    flat_walls = walls[:250]
    overlay = render_overlay(page, rooms, openings, keepouts, scale)
    overlay.save(job_dir / "overlay.png", "PNG")

    nested_rooms = nest_rooms(rooms, flat_walls, openings, keepouts)
    return AnalysisResult(
        job_id=job_id,
        scale=scale,
        page=PageInfo(
            width_pt=page.width_pt,
            height_pt=page.height_pt,
            width_mm=page.width_pt * mm,
            height_mm=page.height_pt * mm,
            rotation=page.rotation,
        ),
        rooms=nested_rooms,
        warnings=warnings,
        overlay_url=f"/api/jobs/{job_id}/overlay.png",
        vision_used=vision_used,
        usage=usage,
    )
