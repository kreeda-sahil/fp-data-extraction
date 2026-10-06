"""Load CAD plot PDFs: drawings, text, and rasters."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

import pymupdf as fitz
from PIL import Image


@dataclass
class TextSpan:
    """Extractable PDF text with a page-space bounding box."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    layer: str | None = None

    @property
    def cx(self) -> float:
        """Return the box centre x in PDF points."""
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        """Return the box centre y in PDF points."""
        return (self.y0 + self.y1) / 2


@dataclass
class Stroke:
    """A straight segment from a CAD drawing."""

    x0: float
    y0: float
    x1: float
    y1: float
    layer: str
    color: tuple[float, ...] | None = None
    width: float = 0.0

    @property
    def length(self) -> float:
        """Return segment length in PDF points."""
        return ((self.x1 - self.x0) ** 2 + (self.y1 - self.y0) ** 2) ** 0.5


@dataclass
class DrawingBBox:
    """Axis-aligned bounds of one drawing object."""

    x0: float
    y0: float
    x1: float
    y1: float
    layer: str
    has_curve: bool
    item_count: int

    @property
    def width(self) -> float:
        """Return box width in PDF points."""
        return abs(self.x1 - self.x0)

    @property
    def height(self) -> float:
        """Return box height in PDF points."""
        return abs(self.y1 - self.y0)

    @property
    def cx(self) -> float:
        """Return centre x."""
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        """Return centre y."""
        return (self.y0 + self.y1) / 2


@dataclass
class LoadedPage:
    """In-memory representation of the first PDF page."""

    width_pt: float
    height_pt: float
    rotation: int
    texts: list[TextSpan] = field(default_factory=list)
    strokes: list[Stroke] = field(default_factory=list)
    drawings: list[DrawingBBox] = field(default_factory=list)
    layers: dict[str, int] = field(default_factory=dict)
    raster: Image.Image | None = None
    dpi: float = 150.0
    drawing_count: int = 0
    image_count: int = 0


def _xy(point) -> tuple[float, float]:
    """Read x/y from a PyMuPDF point or sequence."""
    if hasattr(point, "x"):
        return float(point.x), float(point.y)
    return float(point[0]), float(point[1])


def _layer_name(drawing: dict) -> str:
    """Return a drawing's CAD layer name if present."""
    layer = drawing.get("layer") or drawing.get("Layer") or ""
    return str(layer)


def load_pdf(data: bytes, dpi: float = 150.0) -> LoadedPage:
    """Parse the first page of a floor-plan PDF into vectors, text, and a raster."""
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        page = doc[0]
        rect = page.rect
        loaded = LoadedPage(
            width_pt=rect.width,
            height_pt=rect.height,
            rotation=page.rotation,
            dpi=dpi,
            image_count=len(page.get_images()),
        )
        loaded.texts = _extract_text(page)
        drawings = page.get_drawings()
        loaded.drawing_count = len(drawings)
        loaded.strokes, loaded.drawings, loaded.layers = _extract_drawings(drawings)
        loaded.raster = _rasterize(page, dpi)
        return loaded
    finally:
        doc.close()


def _extract_text(page: fitz.Page) -> list[TextSpan]:
    """Collect text spans from the page dict."""
    spans: list[TextSpan] = []
    raw = page.get_text("dict")
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = (span.get("text") or "").strip()
                if not text:
                    continue
                x0, y0, x1, y1 = span["bbox"]
                spans.append(
                    TextSpan(
                        text=text,
                        x0=float(x0),
                        y0=float(y0),
                        x1=float(x1),
                        y1=float(y1),
                    )
                )
    return spans


def _extract_drawings(
    drawings: list[dict],
) -> tuple[list[Stroke], list[DrawingBBox], dict[str, int]]:
    """Flatten drawing items into strokes, bboxes, and layer histograms."""
    strokes: list[Stroke] = []
    bboxes: list[DrawingBBox] = []
    layers: dict[str, int] = {}
    for drawing in drawings:
        layer = _layer_name(drawing)
        layers[layer] = layers.get(layer, 0) + 1
        rect = drawing.get("rect")
        items = drawing.get("items") or []
        has_curve = False
        color = drawing.get("color")
        width = float(drawing.get("width") or 0)
        for item in items:
            kind = item[0]
            if kind == "l" and len(item) >= 3:
                x0, y0 = _xy(item[1])
                x1, y1 = _xy(item[2])
                strokes.append(
                    Stroke(
                        x0=x0,
                        y0=y0,
                        x1=x1,
                        y1=y1,
                        layer=layer,
                        color=tuple(color) if color else None,
                        width=width,
                    )
                )
            elif kind in {"c", "curve", "qu"}:
                has_curve = True
        if rect is not None:
            bboxes.append(
                DrawingBBox(
                    x0=float(rect.x0),
                    y0=float(rect.y0),
                    x1=float(rect.x1),
                    y1=float(rect.y1),
                    layer=layer,
                    has_curve=has_curve,
                    item_count=len(items),
                )
            )
    return strokes, bboxes, layers


def _rasterize(page: fitz.Page, dpi: float) -> Image.Image:
    """Render the page to an RGB PIL image."""
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    return Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
