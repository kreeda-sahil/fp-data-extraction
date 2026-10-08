"""Debug overlay of rooms, keepouts, and openings on the rasterized plan."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from app.pipeline.pdf_load import LoadedPage
from app.schemas import Keepout, Opening, Room, ScaleInfo


_KEEP_COLORS = {
    "door_swing": (220, 40, 40, 90),
    "window_clearance": (40, 90, 220, 90),
    "circulation": (230, 160, 40, 70),
}


def render_overlay(
    page: LoadedPage,
    rooms: list[Room],
    openings: list[Opening],
    keepouts: list[Keepout],
    scale: ScaleInfo,
) -> Image.Image:
    """Draw extraction QA graphics on a copy of the page raster."""
    base = page.raster.copy().convert("RGBA") if page.raster is not None else Image.new(
        "RGBA", (int(page.width_pt), int(page.height_pt)), (255, 255, 255, 255)
    )
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    sx = base.width / page.width_pt
    sy = base.height / page.height_pt
    font = ImageFont.load_default()

    palette = [
        (80, 170, 120, 70),
        (150, 120, 200, 70),
        (120, 180, 200, 70),
        (200, 180, 90, 70),
        (180, 110, 140, 70),
    ]
    for i, room in enumerate(rooms):
        color = palette[i % len(palette)]
        pts = _to_px(room, sx, sy)
        if len(pts) >= 3:
            draw.polygon(pts, fill=color, outline=(20, 90, 50, 220))
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            label = room.name_normalized or room.name_raw
            draw.text((cx - 20, cy - 6), label[:40], fill=(10, 10, 10, 255), font=font)

    for keepout in keepouts:
        color = _KEEP_COLORS.get(keepout.reason, (80, 80, 80, 80))
        pts = _keepout_px(keepout, sx, sy)
        if len(pts) >= 3:
            draw.polygon(pts, fill=color, outline=color[:3] + (230,))

    for opening in openings:
        if not opening.leaf_polygon:
            continue
        pts = [
            (p.x * sx, p.y * sy) for p in opening.leaf_polygon.points_pdf[:-1]
        ]
        outline = (
            (180, 20, 20, 255)
            if opening.type in {"door", "sliding_door"}
            else (20, 60, 180, 255)
        )
        if len(pts) >= 2:
            draw.line(pts + [pts[0]], fill=outline, width=2)

    scale_badge = (
        f"scale {scale.mm_per_pdf_point:.4f} mm/pt"
        f" samples={scale.sample_count}"
        f"{' FLAGGED' if scale.flagged else ''}"
    )
    draw.rectangle((8, 8, 8 + 7 * len(scale_badge), 24), fill=(255, 255, 255, 200))
    draw.text((12, 10), scale_badge, fill=(0, 0, 0, 255), font=font)

    return Image.alpha_composite(base, overlay).convert("RGB")


def _to_px(room: Room, sx: float, sy: float) -> list[tuple[float, float]]:
    """Convert a room polygon to pixel coordinates."""
    return [(p.x * sx, p.y * sy) for p in room.polygon.points_pdf[:-1]]


def _keepout_px(keepout: Keepout, sx: float, sy: float) -> list[tuple[float, float]]:
    """Convert a keepout polygon to pixel coordinates."""
    return [(p.x * sx, p.y * sy) for p in keepout.polygon.points_pdf[:-1]]
