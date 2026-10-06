"""OpenAI gpt-4o vision labeling for rooms and openings."""

from __future__ import annotations

import base64
import json
from io import BytesIO

from openai import OpenAI
from PIL import Image

from app.catalog_spaces import CANONICAL_SPACES, is_furniture_caption, normalize_space_name
from app.config import OPENAI_API_KEY, OPENAI_MODEL, VISION_MAX_EDGE
from app.pipeline.geom_util import polygon_from_rect_pt
from app.pipeline.geometry import (
    OpeningCandidate,
    _bbox_iou,
    _room_bbox_pdf,
    dedupe_rooms,
)
from app.pipeline.pdf_load import LoadedPage
from app.pipeline.scale import is_room_callout, parse_size_pair
from app.schemas import Opening, Room, WarningItem


def _resize_for_vision(image: Image.Image, max_edge: int = VISION_MAX_EDGE) -> Image.Image:
    """Shrink the raster so the longest edge fits the vision limit."""
    w, h = image.size
    longest = max(w, h)
    if longest <= max_edge:
        return image
    scale = max_edge / longest
    return image.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)


def _png_data_url(image: Image.Image) -> str:
    """Encode a PIL image as a PNG data URL."""
    buf = BytesIO()
    image.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _norm_box_to_pdf(
    box: list[float], page: LoadedPage
) -> tuple[float, float, float, float]:
    """Convert a 0-1000 normalized box to PDF points."""
    x0, y0, x1, y1 = [float(v) for v in box]
    return (
        x0 / 1000.0 * page.width_pt,
        y0 / 1000.0 * page.height_pt,
        x1 / 1000.0 * page.width_pt,
        y1 / 1000.0 * page.height_pt,
    )


def _space_text_for_vision(page: LoadedPage) -> list[dict]:
    """Send only space names and room-scale callouts to the model."""
    items: list[dict] = []
    for span in page.texts:
        if is_furniture_caption(span.text):
            continue
        pair = parse_size_pair(span.text)
        if pair:
            if is_room_callout(pair[0], pair[1]):
                items.append(
                    {"text": span.text, "cx": round(span.cx, 1), "cy": round(span.cy, 1)}
                )
            continue
        if normalize_space_name(span.text):
            items.append(
                {"text": span.text, "cx": round(span.cx, 1), "cy": round(span.cy, 1)}
            )
        if len(items) >= 60:
            break
    return items


def apply_vision(
    page: LoadedPage,
    rooms: list[Room],
    openings: list[Opening],
    candidates: list[OpeningCandidate],
    mm_per_pt: float,
    warnings: list[WarningItem],
) -> tuple[list[Room], list[Opening], bool]:
    """Call gpt-4o to label catalog spaces and classify openings."""
    if page.raster is None:
        warnings.append(WarningItem(code="vision_skipped", message="No raster for vision."))
        return rooms, openings, False
    if not OPENAI_API_KEY:
        warnings.append(
            WarningItem(
                code="vision_skipped",
                message="OPENAI_API_KEY is not set; returning vector-only labels.",
            )
        )
        return rooms, openings, False

    summary = {
        "canonical_spaces": list(CANONICAL_SPACES),
        "page_width_pt": page.width_pt,
        "page_height_pt": page.height_pt,
        "space_labels": _space_text_for_vision(page),
        "candidate_spaces": [
            {
                "id": r.id,
                "name_normalized": r.name_normalized,
            }
            for r in rooms
        ],
        "openings": [
            {
                "id": o.id,
                "guessed_type": o.type,
                "layer": candidates[i].layer if i < len(candidates) else "",
            }
            for i, o in enumerate(openings)
        ],
    }
    prompt = (
        "You are analysing an architectural floor-plan drawing. "
        "Coordinates use a 0-1000 normalized page box [x0,y0,x1,y1], origin top-left.\n"
        "Return ONLY occupiable catalog spaces. Ignore existing furniture completely. "
        "Do not name sofas, beds, tables, TV units, appliances, or other furniture.\n"
        "approx_box must cover the whole room, not a furniture piece.\n"
        "Do not invent millimetre sizes.\n"
        "Return JSON keys rooms, openings, notes.\n"
        "rooms: [{id (existing candidate id or null), name, approx_box, is_title_block}]\n"
        "openings: [{id, type (door|sliding_door|window|opening), "
        "hinge (left|right|none), swing (in|out|unknown)}]\n"
        "Map names to these catalog spaces when possible: "
        + ", ".join(CANONICAL_SPACES)
        + "\nVector summary:\n"
        + json.dumps(summary, ensure_ascii=False)[:12000]
    )

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        vision_image = _resize_for_vision(page.raster)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": _png_data_url(vision_image), "detail": "high"},
                        },
                    ],
                }
            ],
        )
        content = response.choices[0].message.content or "{}"
        payload = json.loads(content)
    except Exception as exc:  # noqa: BLE001 — POC must not 500 on LLM errors
        warnings.append(
            WarningItem(code="vision_failed", message=f"gpt-4o call failed: {exc}")
        )
        return rooms, openings, False

    rooms = _replace_rooms_from_vision(page, rooms, payload.get("rooms") or [], mm_per_pt)
    openings = _merge_opening_labels(openings, payload.get("openings") or [])
    for opening in openings:
        opening.blocks_tall_furniture = opening.type == "window"
    for note in payload.get("notes") or []:
        text = str(note)
        if is_furniture_caption(text):
            continue
        warnings.append(WarningItem(code="vision_note", message=text))
    return rooms, openings, True


def _replace_rooms_from_vision(
    page: LoadedPage,
    vector_rooms: list[Room],
    vision_rooms: list[dict],
    mm_per_pt: float,
) -> list[Room]:
    """Build a catalog-only room list from vision, snapping onto vector boxes."""
    replaced: list[Room] = []
    for item in vision_rooms:
        if item.get("is_title_block"):
            continue
        name = str(item.get("name") or "").strip()
        if is_furniture_caption(name):
            continue
        norm = normalize_space_name(name)
        if norm is None:
            continue
        rid = item.get("id")
        snapped: Room | None = None
        if isinstance(rid, str):
            snapped = next((r for r in vector_rooms if r.id == rid), None)
        box = item.get("approx_box")
        pdf_box = _norm_box_to_pdf(box, page) if box and len(box) == 4 else None
        if snapped is None and pdf_box is not None:
            best = None
            best_iou = 0.0
            for room in vector_rooms:
                iou = _bbox_iou(pdf_box, _room_bbox_pdf(room))
                if iou > best_iou:
                    best_iou = iou
                    best = room
            if best and best_iou > 0.15:
                snapped = best
        if snapped is not None:
            snapped.name_raw = name
            snapped.name_normalized = norm
            snapped.confidence = 0.85
            if "living" in name.lower() and "dining" in name.lower():
                snapped.tags = ["Living Room", "Dining Room"]
            replaced.append(snapped)
            continue
        if pdf_box is None:
            continue
        x0, y0, x1, y1 = pdf_box
        replaced.append(
            Room(
                id=f"room_{len(replaced) + 1}",
                name_raw=name,
                name_normalized=norm,
                polygon=polygon_from_rect_pt(x0, y0, x1, y1, mm_per_pt),
                width_mm=(x1 - x0) * mm_per_pt,
                depth_mm=(y1 - y0) * mm_per_pt,
                confidence=0.75,
                tags=["Living Room", "Dining Room"]
                if "living" in name.lower() and "dining" in name.lower()
                else [],
            )
        )
    cleaned = [r for r in replaced if r.name_normalized]
    if not cleaned:
        return [r for r in vector_rooms if r.name_normalized]
    return dedupe_rooms(cleaned)


def _merge_opening_labels(openings: list[Opening], vision_openings: list[dict]) -> list[Opening]:
    """Overwrite opening type/hinge from the VLM when ids match."""
    by_id = {o.id: o for o in openings}
    allowed = {"door", "sliding_door", "window", "opening"}
    for item in vision_openings:
        oid = item.get("id")
        if oid not in by_id:
            continue
        opening = by_id[oid]
        otype = item.get("type")
        if otype in allowed:
            opening.type = otype
        hinge = item.get("hinge")
        if hinge in {"left", "right", "none"}:
            opening.hinge = hinge
        swing = item.get("swing")
        if swing in {"in", "out", "unknown"}:
            opening.swing_direction = swing
        if opening.type == "sliding_door":
            opening.hinge = "none"
        opening.confidence = 0.8
        opening.blocks_tall_furniture = opening.type == "window"
    return openings
