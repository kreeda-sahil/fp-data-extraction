"""Geometry helpers shared across the extraction pipeline."""

from __future__ import annotations

from app.schemas import Point, Polygon


def pdf_to_mm(x: float, y: float, mm_per_pt: float) -> tuple[float, float]:
    """Convert PDF points to millimetres."""
    return x * mm_per_pt, y * mm_per_pt


def polygon_from_rect_pt(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    mm_per_pt: float,
) -> Polygon:
    """Build a closed rectangle polygon from PDF-point bounds."""
    corners_pt = [
        (x0, y0),
        (x1, y0),
        (x1, y1),
        (x0, y1),
        (x0, y0),
    ]
    return Polygon(
        points_pdf=[Point(x=x, y=y) for x, y in corners_pt],
        points_mm=[
            Point(x=x * mm_per_pt, y=y * mm_per_pt) for x, y in corners_pt
        ],
    )


def polygon_from_points_pt(
    points: list[tuple[float, float]],
    mm_per_pt: float,
) -> Polygon:
    """Build a closed polygon from PDF-point vertices."""
    pts = list(points)
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return Polygon(
        points_pdf=[Point(x=x, y=y) for x, y in pts],
        points_mm=[Point(x=x * mm_per_pt, y=y * mm_per_pt) for x, y in pts],
    )


def rects_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    """Return True if two axis-aligned rectangles overlap."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0


def point_in_rect(x: float, y: float, rect: tuple[float, float, float, float]) -> bool:
    """Return True if (x, y) lies inside the rectangle."""
    x0, y0, x1, y1 = rect
    return x0 <= x <= x1 and y0 <= y <= y1
