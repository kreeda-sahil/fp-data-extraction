"""Parse dimension labels and recover millimetres per PDF point."""

from __future__ import annotations

import math
import re
from statistics import median

from app.config import SCALE_RESIDUAL_FLAG
from app.pipeline.pdf_load import LoadedPage, Stroke, TextSpan
from app.schemas import ScaleInfo, WarningItem

# 13'6", 13'-6", 13' 6", 4'-7", 18', 5'0"
_IMPERIAL = re.compile(
    r"""
    (?P<ft>\d+)\s*['’]
    (?:
        \s*[-–]?\s*(?P<inch>\d+(?:\.\d+)?)\s*(?:["”]|'')
    )?
    """,
    re.VERBOSE,
)
_METRIC_M = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:x|X|×)\s*(\d+(?:\.\d+)?)\b")
_METRIC_SINGLE = re.compile(r"\b(\d+\.\d{2,3})\b")
_FEET_PAIR = re.compile(
    r"(\d+\s*['’](?:\s*[-–]?\s*\d+(?:\.\d+)?\s*(?:[\"”]|'')?)?)"
    r"\s*(?:x|X|×)\s*"
    r"(\d+\s*['’](?:\s*[-–]?\s*\d+(?:\.\d+)?\s*(?:[\"”]|'')?)?)",
)


def imperial_to_mm(feet: float, inches: float = 0.0) -> float:
    """Convert feet and inches to millimetres."""
    return feet * 304.8 + inches * 25.4


def parse_imperial_length(text: str) -> float | None:
    """Parse a single imperial length in a string to millimetres."""
    match = _IMPERIAL.search(text.replace("�", "-"))
    if not match:
        return None
    feet = float(match.group("ft"))
    inches = float(match.group("inch") or 0)
    return imperial_to_mm(feet, inches)


ROOM_CALL_MIN_SIDE_MM = 1800.0
ROOM_CALL_BOTH_SIDES_MM = 2100.0
ROOM_CALL_LONG_SIDE_MM = 2700.0


def is_room_callout(width_mm: float, depth_mm: float) -> bool:
    """Return True if a WxD pair is a room overall size, not a furniture piece."""
    a, b = sorted((abs(width_mm), abs(depth_mm)))
    if a >= ROOM_CALL_BOTH_SIDES_MM and b >= ROOM_CALL_BOTH_SIDES_MM:
        return True
    return a >= ROOM_CALL_MIN_SIDE_MM and b >= ROOM_CALL_LONG_SIDE_MM


def is_furniture_size(width_mm: float, depth_mm: float) -> bool:
    """Return True if a WxD pair is a furniture-piece size."""
    return not is_room_callout(width_mm, depth_mm)


def parse_size_pair(text: str) -> tuple[float, float] | None:
    """Parse a W x D label into millimetres, imperial or metric."""
    cleaned = text.replace("�", "-")
    pair = _FEET_PAIR.search(cleaned)
    if pair:
        a = parse_imperial_length(pair.group(1))
        b = parse_imperial_length(pair.group(2))
        if a and b:
            return a, b
    metric = _METRIC_M.search(cleaned)
    if metric:
        w, d = float(metric.group(1)), float(metric.group(2))
        # Values like 4.350 x 4.000 are metres on these sheets.
        if w < 50 and d < 50:
            return w * 1000.0, d * 1000.0
        return w, d
    return None


def _is_axis_aligned(stroke: Stroke, tol: float = 8.0) -> str | None:
    """Return 'h' or 'v' if the stroke is roughly axis-aligned."""
    dx = abs(stroke.x1 - stroke.x0)
    dy = abs(stroke.y1 - stroke.y0)
    if dx <= tol and dy > dx:
        return "v"
    if dy <= tol and dx > dy:
        return "h"
    return None


def recover_scale(page: LoadedPage) -> tuple[ScaleInfo, list[WarningItem], list[tuple[str, float, float]]]:
    """Estimate mm per PDF point from dimension labels near dimension-like lines.

    Returns scale info, warnings, and (label, width_mm, depth_mm) size annotations.
    """
    warnings: list[WarningItem] = []
    size_labels: list[tuple[str, float, float]] = []
    lengths_mm: list[tuple[TextSpan, float]] = []

    for span in page.texts:
        pair = parse_size_pair(span.text)
        if pair:
            size_labels.append((span.text, pair[0], pair[1]))
            lengths_mm.append((span, pair[0]))
            lengths_mm.append((span, pair[1]))
            continue
        single = parse_imperial_length(span.text)
        if single and single > 200:
            lengths_mm.append((span, single))
        else:
            metric = _METRIC_SINGLE.search(span.text)
            if metric and "SCALE" not in span.text.upper():
                value = float(metric.group(1))
                if 1.5 <= value <= 30:
                    lengths_mm.append((span, value * 1000.0))

    dim_strokes = [
        s
        for s in page.strokes
        if s.length > 15
        and _is_axis_aligned(s)
        and (
            "dim" in s.layer.lower()
            or "dimension" in s.layer.lower()
            or not s.layer
            or s.layer.lower() in {"0", "defpoints"}
        )
    ]
    if len(dim_strokes) < 8:
        dim_strokes = [s for s in page.strokes if s.length > 20 and _is_axis_aligned(s)]

    ratios: list[float] = []
    for span, length_mm in lengths_mm:
        best: tuple[float, float] | None = None
        for stroke in dim_strokes:
            mid_x = (stroke.x0 + stroke.x1) / 2
            mid_y = (stroke.y0 + stroke.y1) / 2
            dist = math.hypot(mid_x - span.cx, mid_y - span.cy)
            if dist > 80:
                continue
            if stroke.length < 8:
                continue
            ratio = length_mm / stroke.length
            # CAD plots at ~1:50 to 1:100 on A3: roughly 2–20 mm per point is plausible.
            if not 0.3 <= ratio <= 40:
                continue
            if best is None or dist < best[0]:
                best = (dist, ratio)
        if best:
            ratios.append(best[1])

    if not ratios and lengths_mm:
        # Fallback: match each length to the closest stroke of similar relative size.
        long_strokes = sorted(
            [s for s in page.strokes if s.length > 40 and _is_axis_aligned(s)],
            key=lambda s: -s.length,
        )
        for _, length_mm in lengths_mm[:12]:
            for stroke in long_strokes[:80]:
                ratio = length_mm / stroke.length
                if 0.5 <= ratio <= 25:
                    ratios.append(ratio)
                    break

    if not ratios:
        # Last resort: assume the page is plotted near true paper size (1 pt = 0.3528 mm)
        # and flag it — NTS drawings must not be trusted this way.
        warnings.append(
            WarningItem(
                code="scale_fallback_paper",
                message="Could not recover scale from dimensions; using PDF point = 0.352777 mm (paper).",
            )
        )
        return (
            ScaleInfo(
                mm_per_pdf_point=25.4 / 72.0,
                method="paper_point",
                sample_count=0,
                flagged=True,
            ),
            warnings,
            size_labels,
        )

    med = float(median(ratios))
    if med == 0:
        med = 25.4 / 72.0
    deviations = [abs(r - med) / med for r in ratios if med]
    residual = float(median(deviations)) if deviations else None
    flagged = bool(residual is not None and residual > SCALE_RESIDUAL_FLAG)
    if flagged:
        warnings.append(
            WarningItem(
                code="scale_disagreement",
                message=f"Dimension samples disagree (residual={residual:.2%}); using median scale.",
            )
        )
    return (
        ScaleInfo(
            mm_per_pdf_point=med,
            method="dimension_labels",
            sample_count=len(ratios),
            residual_ratio=residual,
            flagged=flagged,
        ),
        warnings,
        size_labels,
    )
