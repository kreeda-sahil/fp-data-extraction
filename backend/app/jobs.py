"""On-disk job artifacts (PDF copy, overlay, JSON)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.config import JOBS_DIR
from app.schemas import AnalysisResult


def create_job_dir() -> tuple[str, Path]:
    """Create a unique job folder and return (job_id, path)."""
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    path = JOBS_DIR / job_id
    path.mkdir(parents=True, exist_ok=True)
    return job_id, path


def save_result(job_dir: Path, result: AnalysisResult) -> Path:
    """Write analysis JSON next to other job files."""
    out = job_dir / "result.json"
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return out


def load_result(job_id: str) -> AnalysisResult | None:
    """Load a previously saved analysis, if present."""
    path = JOBS_DIR / job_id / "result.json"
    if not path.exists():
        return None
    return AnalysisResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
