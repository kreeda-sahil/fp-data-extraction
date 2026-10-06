"""Wall clustering, opening candidates, and room polygons from CAD vectors."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from app.catalog_spaces import is_furniture_caption, normalize_space_name
from app.pipeline.geom_util import polygon_from_rect_pt
from app.pipeline.pdf_load import DrawingBBox, LoadedPage, Stroke, TextSpan
from app.pipeline.scale import is_room_callout, parse_size_pair
from app.schemas import Opening, Room, Wall, WarningItem

_FURNITURE_HINTS = (
    "furn",
    "sofa",
    "bed",
    "chair",
    "table",
    "wardrobe",
    "fixture",
    "sanitary",
    "hatch",
    "hatching",
    "text",
    "dimen",
    "title",
    "logo",
    "tree",
    "plant",
    "car",
    "vehicle",
    "grid",
    "hatch",
)
_DOOR_HINTS = ("door", "swing")
_WINDOW_HINTS = ("window", "wind", "a-win", "a- win", "win -", "pl - window", "pl-window")
_WALL_HINTS = ("wall", "partition", "a-wall", "a - wall")


@dataclass
class OpeningCandidate:
    """Vector opening before VLM classification."""

    bbox: tuple[float, float, float, float]
    layer: str
    guessed_type: str
    has_curve: bool
    width_pt: float


def _layer_matches(layer: str, hints: tuple[str, ...]) -> bool:
    """Return True if any hint is a substring of the layer name."""
    low = layer.lower()
    return any(h in low for h in hints)


def classify_layer(layer: str) -> str:
    """Classify a CAD layer as door, window, wall, skip, or other."""
    low = layer.lower()
    if _layer_matches(layer, _DOOR_HINTS):
        return "door"
    if "win" in low and "swing" not in low:
        return "window"
    if _layer_matches(layer, _WINDOW_HINTS):
        return "window"
    if _layer_matches(layer, _WALL_HINTS):
        return "wall"
    if _layer_matches(layer, _FURNITURE_HINTS):
        return "skip"
    return "other"


def wall_strokes(page: LoadedPage) -> list[Stroke]:
    """Select strokes that are likely walls rather than furniture."""
    classified = [(s, classify_layer(s.layer)) for s in page.strokes]
    walls = [s for s, kind in classified if kind == "wall" and s.length > 8]
    if len(walls) >= 20:
        return walls
    return [
        s
        for s, kind in classified
        if kind in {"wall", "other", "door", "window"} and s.length > 12
    ]


def _merge_bboxes(
    boxes: list[DrawingBBox], gap: float = 12.0
) -> list[tuple[float, float, float, float, DrawingBBox]]:
    """Greedily merge nearby drawing boxes of the same layer family."""
    remaining = list(boxes)
    merged: list[tuple[float, float, float, float, DrawingBBox]] = []
    while remaining:
        cur = remaining.pop(0)
        x0, y0, x1, y1 = cur.x0, cur.y0, cur.x1, cur.y1
        changed = True
        while changed:
            changed = False
            nxt = []
            for other in remaining:
                ox0, oy0, ox1, oy1 = other.x0, other.y0, other.x1, other.y1
                if (
                    x0 - gap <= ox1
                    and ox0 <= x1 + gap
                    and y0 - gap <= oy1
                    and oy0 <= y1 + gap
                ):
                    x0, y0 = min(x0, ox0), min(y0, oy0)
                    x1, y1 = max(x1, ox1), max(y1, oy1)
                    changed = True
                else:
                    nxt.append(other)
            remaining = nxt
        merged.append((x0, y0, x1, y1, cur))
    return merged


def opening_candidates(page: LoadedPage) -> list[OpeningCandidate]:
    """Build door/window candidates from layer names and swing-like boxes."""
    door_boxes = [d for d in page.drawings if classify_layer(d.layer) == "door"]
    window_boxes = [d for d in page.drawings if classify_layer(d.layer) == "window"]
    candidates: list[OpeningCandidate] = []

    def add_group(boxes: list[DrawingBBox], guessed: str) -> None:
        """Append merged candidates for one opening family."""
        if not boxes:
            return
        for x0, y0, x1, y1, sample in _merge_bboxes(boxes):
            w, h = abs(x1 - x0), abs(y1 - y0)
            if w < 4 or h < 4:
                continue
            if w > page.width_pt * 0.45 or h > page.height_pt * 0.45:
                continue
            width_pt = min(w, h) if guessed == "door" else max(w, h)
            if guessed == "window" and min(w, h) > 80:
                continue
            candidates.append(
                OpeningCandidate(
                    bbox=(x0, y0, x1, y1),
                    layer=sample.layer,
                    guessed_type=guessed,
                    has_curve=sample.has_curve or (0.6 <= (min(w, h) / max(w, h)) <= 1.0),
                    width_pt=width_pt,
                )
            )

    add_group(door_boxes, "door")
    add_group(window_boxes, "window")
    return candidates


def _title_block_rect(page: LoadedPage) -> tuple[float, float, float, float]:
    """Approximate title-block band along the bottom-right of the sheet."""
    return (
        page.width_pt * 0.62,
        page.height_pt * 0.72,
        page.width_pt,
        page.height_pt,
    )


def room_rects_from_labels(
    page: LoadedPage, mm_per_pt: float
) -> list[tuple[tuple[float, float, float, float], str, str | None]]:
    """Build room rectangles from catalog space names plus room-scale WxD callouts."""
    deny = {
        "LAYOUT",
        "PLAN",
        "NOTES",
        "SCALE",
        "NTS",
        "REVISION",
        "NORTH",
        "UP",
        "DN",
        "DOWN",
        "GLASS",
        "SLAB",
        "DOUBLE",
        "HT",
        "WOODEN",
        "PANEL",
        "DRAWING",
        "PROJECT",
        "LIFT",
        "CLIENT",
        "DATE",
        "PASSAGE",
    }
    names: list[TextSpan] = []
    room_sizes: list[tuple[TextSpan, tuple[float, float]]] = []
    furniture_sizes: list[TextSpan] = []
    for span in page.texts:
        pair = parse_size_pair(span.text)
        if pair:
            if is_room_callout(pair[0], pair[1]):
                room_sizes.append((span, pair))
            else:
                furniture_sizes.append(span)
            continue
        raw = span.text.strip()
        if len(raw) < 3:
            continue
        if is_furniture_caption(raw):
            continue
        token = raw.upper().replace(".", "")
        if token in deny or token.startswith("UP") or token.startswith("DN"):
            continue
        if "DOUBLE HT" in token:
            continue
        if normalize_space_name(raw) is None:
            continue
        names.append(span)

    rooms: list[tuple[tuple[float, float, float, float], str, str | None]] = []
    used_sizes: set[int] = set()
    for span in names:
        best_i = None
        best_d = 120.0
        for i, (size_span, _pair) in enumerate(room_sizes):
            if i in used_sizes:
                continue
            dist = ((size_span.cx - span.cx) ** 2 + (size_span.cy - span.cy) ** 2) ** 0.5
            if dist < best_d:
                best_d = dist
                best_i = i
        if best_i is None:
            pad = 40
            rect = _expand_with_furniture(
                (span.x0 - pad, span.y0 - pad, span.x1 + pad, span.y1 + pad),
                furniture_sizes,
            )
            rooms.append((rect, span.text, None))
            continue
        used_sizes.add(best_i)
        size_span, pair = room_sizes[best_i]
        w_pt = pair[0] / mm_per_pt
        d_pt = pair[1] / mm_per_pt
        cx, cy = span.cx, (span.cy + size_span.cy) / 2
        rect = (cx - w_pt / 2, cy - d_pt / 2, cx + w_pt / 2, cy + d_pt / 2)
        rect = _expand_with_furniture(rect, furniture_sizes)
        rooms.append((rect, span.text, size_span.text))
    return rooms


def _expand_with_furniture(
    rect: tuple[float, float, float, float],
    furniture_sizes: list[TextSpan],
    pad: float = 36.0,
) -> tuple[float, float, float, float]:
    """Grow a space box slightly if nearby furniture-size labels sit just outside it."""
    x0, y0, x1, y1 = rect
    for span in furniture_sizes:
        if x0 - pad <= span.cx <= x1 + pad and y0 - pad <= span.cy <= y1 + pad:
            x0 = min(x0, span.x0)
            y0 = min(y0, span.y0)
            x1 = max(x1, span.x1)
            y1 = max(y1, span.y1)
    return (x0, y0, x1, y1)


def room_rects_from_raster(page: LoadedPage) -> list[tuple[float, float, float, float]]:
    """Find occupiable blanks by rasterizing walls and labeling interiors."""
    if page.raster is None:
        return []
    src = page.raster
    max_edge = 560
    scale = min(1.0, max_edge / max(src.size))
    w_i = max(1, int(src.width * scale))
    h_i = max(1, int(src.height * scale))
    canvas = Image.new("L", (w_i, h_i), 255)
    draw = ImageDraw.Draw(canvas)
    sx = w_i / page.width_pt
    sy = h_i / page.height_pt
    for stroke in wall_strokes(page):
        draw.line(
            (stroke.x0 * sx, stroke.y0 * sy, stroke.x1 * sx, stroke.y1 * sy),
            fill=0,
            width=3,
        )
    arr = np.array(canvas)
    # Exterior flood from corners
    mask = arr > 128
    h, w = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    stack = [(0, 0), (0, h - 1), (w - 1, 0), (w - 1, h - 1)]
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        if visited[y, x] or not mask[y, x]:
            continue
        visited[y, x] = True
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    interior = mask & ~visited
    labels, count = _connected_components(interior)
    rects: list[tuple[float, float, float, float]] = []
    min_area = (w * h) * 0.004
    tb = _title_block_rect(page)
    for idx in range(1, count + 1):
        ys, xs = np.where(labels == idx)
        if xs.size == 0:
            continue
        if xs.size < min_area:
            continue
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        # Convert pixel box back to PDF points
        px0, py0 = x0 / sx, y0 / sy
        px1, py1 = x1 / sx, y1 / sy
        cx, cy = (px0 + px1) / 2, (py0 + py1) / 2
        if tb[0] <= cx <= tb[2] and tb[1] <= cy <= tb[3]:
            continue
        if (px1 - px0) > page.width_pt * 0.92:
            continue
        rects.append((px0, py0, px1, py1))
    rects.sort(key=lambda r: -(r[2] - r[0]) * (r[3] - r[1]))
    return rects[:24]


def _connected_components(binary: np.ndarray) -> tuple[np.ndarray, int]:
    """Label 4-connected True pixels. Returns (labels, count)."""
    h, w = binary.shape
    labels = np.zeros((h, w), dtype=np.int32)
    current = 0
    for y in range(h):
        for x in range(w):
            if not binary[y, x] or labels[y, x]:
                continue
            current += 1
            stack = [(x, y)]
            labels[y, x] = current
            while stack:
                cx, cy = stack.pop()
                for nx, ny in (
                    (cx + 1, cy),
                    (cx - 1, cy),
                    (cx, cy + 1),
                    (cx, cy - 1),
                ):
                    if nx < 0 or ny < 0 or nx >= w or ny >= h:
                        continue
                    if binary[ny, nx] and labels[ny, nx] == 0:
                        labels[ny, nx] = current
                        stack.append((nx, ny))
    return labels, current


def label_rooms_from_text(
    rects: list[tuple[float, float, float, float]],
    texts: list[TextSpan],
) -> list[tuple[tuple[float, float, float, float], str, str | None]]:
    """Assign extractable text labels that look like room names to rects."""
    labeled: list[tuple[tuple[float, float, float, float], str, str | None]] = []
    used_text: set[int] = set()
    for rect in rects:
        best: tuple[int, str] | None = None
        for i, span in enumerate(texts):
            if i in used_text:
                continue
            if not (rect[0] <= span.cx <= rect[2] and rect[1] <= span.cy <= rect[3]):
                continue
            name = span.text.strip()
            if is_furniture_caption(name):
                continue
            if len(name) < 3 or parse_size_pair(name):
                continue
            if any(ch.isdigit() for ch in name) and len(name) < 8:
                continue
            if name.upper() in {"LAYOUT PLAN", "NOTES", "SCALE", "NTS", "REVISION"}:
                continue
            norm = normalize_space_name(name)
            if norm is None:
                continue
            score = 2
            if best is None or score > 0:
                if best is None or (norm and not normalize_space_name(best[1])):
                    best = (i, name)
        if best:
            used_text.add(best[0])
            labeled.append((rect, best[1], parse_nearby_room_size(texts, rect)))
    return labeled


def parse_nearby_room_size(
    texts: list[TextSpan], rect: tuple[float, float, float, float]
) -> str | None:
    """Find a room-scale W x D label inside a room rectangle."""
    for span in texts:
        if rect[0] <= span.cx <= rect[2] and rect[1] <= span.cy <= rect[3]:
            pair = parse_size_pair(span.text)
            if pair and is_room_callout(pair[0], pair[1]):
                return span.text
    return None


def build_rooms_walls_openings(
    page: LoadedPage,
    mm_per_pt: float,
    warnings: list[WarningItem],
) -> tuple[list[Room], list[Wall], list[Opening], list[OpeningCandidate]]:
    """Construct rooms, simplified walls, and opening objects from vectors."""
    if len(page.texts) == 0:
        warnings.append(
            WarningItem(
                code="exploded_text",
                message="No extractable text; room names need vision or exploded-path OCR.",
            )
        )

    labeled = room_rects_from_labels(page, mm_per_pt)
    if not labeled:
        rects = room_rects_from_raster(page)
        labeled = label_rooms_from_text(rects, page.texts)
    if not labeled:
        warnings.append(
            WarningItem(
                code="no_room_polygons",
                message="Could not form rooms from space labels or wall rasterization.",
            )
        )
    rooms: list[Room] = []
    for i, (rect, raw, size_text) in enumerate(labeled, start=1):
        norm = normalize_space_name(raw)
        if norm is None:
            continue
        pair = parse_size_pair(size_text) if size_text else None
        if pair and not is_room_callout(pair[0], pair[1]):
            pair = None
            size_text = None
        width_mm = pair[0] if pair else (rect[2] - rect[0]) * mm_per_pt
        depth_mm = pair[1] if pair else (rect[3] - rect[1]) * mm_per_pt
        rooms.append(
            Room(
                id=f"room_{len(rooms) + 1}",
                name_raw=raw,
                name_normalized=norm,
                polygon=polygon_from_rect_pt(*rect, mm_per_pt),
                width_mm=width_mm,
                depth_mm=depth_mm,
                labeled_size=size_text,
                confidence=0.7,
            )
        )
    rooms = dedupe_rooms(rooms)

    walls: list[Wall] = []
    for i, stroke in enumerate(wall_strokes(page)[:400], start=1):
        pad = max(stroke.width, 1.5)
        x0, x1 = min(stroke.x0, stroke.x1), max(stroke.x0, stroke.x1)
        y0, y1 = min(stroke.y0, stroke.y1), max(stroke.y0, stroke.y1)
        walls.append(
            Wall(
                id=f"wall_{i}",
                polygon=polygon_from_rect_pt(
                    x0 - pad, y0 - pad, x1 + pad, y1 + pad, mm_per_pt
                ),
                room_ids=_rooms_touching(rooms, (x0, y0, x1, y1), mm_per_pt),
            )
        )

    candidates = opening_candidates(page)
    openings: list[Opening] = []
    for i, cand in enumerate(candidates, start=1):
        guessed = cand.guessed_type
        opening_type = "door" if guessed == "door" else "window"
        if guessed == "door" and not cand.has_curve:
            # Elongated door-layer boxes without a swing are often sliding leaves.
            x0, y0, x1, y1 = cand.bbox
            aspect = max(x1 - x0, y1 - y0) / max(min(x1 - x0, y1 - y0), 1e-3)
            if aspect > 3.5:
                opening_type = "sliding_door"
        openings.append(
            Opening(
                id=f"opening_{i}",
                type=opening_type,  # type: ignore[arg-type]
                width_mm=cand.width_pt * mm_per_pt,
                connected_room_ids=_rooms_touching(rooms, cand.bbox, mm_per_pt),
                hinge="none" if opening_type == "sliding_door" else None,
                leaf_polygon=polygon_from_rect_pt(*cand.bbox, mm_per_pt),
                blocks_tall_furniture=opening_type == "window",
                confidence=0.55,
            )
        )
    if not openings:
        warnings.append(
            WarningItem(
                code="no_openings",
                message="No door/window layers found; vision should classify openings.",
            )
        )
    recompute_opening_rooms(rooms, openings)
    assign_adjacency(rooms, openings)
    return rooms, walls, openings, candidates


def _rooms_touching(
    rooms: list[Room], bbox_pt: tuple[float, float, float, float], _mm_per_pt: float
) -> list[str]:
    """Return room ids whose polygons overlap a PDF-point bbox."""
    x0, y0, x1, y1 = bbox_pt
    ids: list[str] = []
    pad = 8
    for room in rooms:
        pts = room.polygon.points_pdf
        rx0 = min(p.x for p in pts) - pad
        ry0 = min(p.y for p in pts) - pad
        rx1 = max(p.x for p in pts) + pad
        ry1 = max(p.y for p in pts) + pad
        if x0 < rx1 and x1 > rx0 and y0 < ry1 and y1 > ry0:
            ids.append(room.id)
    return ids


def _room_bbox_pdf(room: Room) -> tuple[float, float, float, float]:
    """Return axis-aligned PDF-point bounds of a room polygon."""
    pts = room.polygon.points_pdf
    return (
        min(p.x for p in pts),
        min(p.y for p in pts),
        max(p.x for p in pts),
        max(p.y for p in pts),
    )


def _bbox_iou(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    """Intersection-over-union of two axis-aligned boxes."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    denom = area_a + area_b - inter
    return inter / denom if denom else 0.0


def _bbox_area(box: tuple[float, float, float, float]) -> float:
    """Return box area in PDF points squared."""
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def dedupe_rooms(rooms: list[Room], iou_threshold: float = 0.3) -> list[Room]:
    """Keep one room per overlapping same catalog name; prefer labeled sizes."""
    kept: list[Room] = []
    for room in sorted(rooms, key=lambda r: (-(1 if r.labeled_size else 0), -_bbox_area(_room_bbox_pdf(r)))):
        box = _room_bbox_pdf(room)
        duplicate = False
        for other in kept:
            if room.name_normalized != other.name_normalized:
                continue
            if _bbox_iou(box, _room_bbox_pdf(other)) > iou_threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(room)
    for i, room in enumerate(kept, start=1):
        room.id = f"room_{i}"
    return kept


def assign_adjacency(rooms: list[Room], openings: list[Opening], pad_pt: float = 14.0) -> None:
    """Fill adjacent_room_ids from shared doors and touching polygons."""
    neighbors: dict[str, set[str]] = {r.id: set() for r in rooms}
    for opening in openings:
        if opening.type not in {"door", "sliding_door", "opening"}:
            continue
        ids = [i for i in opening.connected_room_ids if i in neighbors]
        for a in ids:
            for b in ids:
                if a != b:
                    neighbors[a].add(b)
    for i, room_a in enumerate(rooms):
        box_a = _room_bbox_pdf(room_a)
        for room_b in rooms[i + 1 :]:
            box_b = _room_bbox_pdf(room_b)
            ax0, ay0, ax1, ay1 = box_a
            bx0, by0, bx1, by1 = box_b
            touch_x = ax0 - pad_pt <= bx1 and bx0 <= ax1 + pad_pt
            touch_y = ay0 - pad_pt <= by1 and by0 <= ay1 + pad_pt
            overlap_x = min(ax1, bx1) - max(ax0, bx0)
            overlap_y = min(ay1, by1) - max(ay0, by0)
            if touch_x and touch_y and (overlap_x > 8 or overlap_y > 8):
                neighbors[room_a.id].add(room_b.id)
                neighbors[room_b.id].add(room_a.id)
    for room in rooms:
        room.adjacent_room_ids = sorted(neighbors.get(room.id, set()))


def recompute_opening_rooms(rooms: list[Room], openings: list[Opening]) -> None:
    """Refresh connected_room_ids and tall-furniture flags after room filtering."""
    for opening in openings:
        if opening.leaf_polygon is None:
            opening.connected_room_ids = []
            continue
        pts = opening.leaf_polygon.points_pdf
        bbox = (
            min(p.x for p in pts),
            min(p.y for p in pts),
            max(p.x for p in pts),
            max(p.y for p in pts),
        )
        opening.connected_room_ids = _rooms_touching(rooms, bbox, 0)
        opening.blocks_tall_furniture = opening.type == "window"

