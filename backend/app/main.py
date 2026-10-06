"""HTTP API for floor-plan analysis."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import JOBS_DIR
from app.jobs import create_job_dir, load_result, save_result
from app.pipeline.analyze import analyze_pdf_bytes
from app.schemas import AnalysisResult

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

app = FastAPI(
    title="Floor Plan Analyser",
    description="Extract rooms, scale, openings, and keepouts from a CAD floor-plan PDF.",
    version="0.1.0",
)


@app.post("/api/analyze", response_model=AnalysisResult)
async def analyze(file: UploadFile = File(...)) -> AnalysisResult:
    """Accept a floor-plan PDF and return placement-ready JSON."""
    name = (file.filename or "").lower()
    if not name.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Upload a PDF file.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    job_id, job_dir = create_job_dir()
    (job_dir / "input.pdf").write_bytes(data)
    try:
        result = analyze_pdf_bytes(data, job_id, job_dir)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    save_result(job_dir, result)
    return result


@app.get("/api/jobs/{job_id}/overlay.png")
async def overlay_png(job_id: str) -> FileResponse:
    """Return the debug overlay for a job."""
    path = JOBS_DIR / job_id / "overlay.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Overlay not found.")
    return FileResponse(path, media_type="image/png")


@app.get("/api/jobs/{job_id}", response_model=AnalysisResult)
async def get_job(job_id: str) -> AnalysisResult:
    """Reload a saved analysis JSON."""
    result = load_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return result


@app.get("/api/schema")
async def schema() -> dict:
    """Expose the OpenAPI document for the furniture-placement POC."""
    return app.openapi()


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
