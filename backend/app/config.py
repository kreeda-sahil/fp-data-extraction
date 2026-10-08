"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
JOBS_DIR = BACKEND_DIR / "data" / "jobs"

load_dotenv(ROOT_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_INPUT_USD_PER_1M = float(os.getenv("OPENAI_INPUT_USD_PER_1M", "2.50"))
OPENAI_OUTPUT_USD_PER_1M = float(os.getenv("OPENAI_OUTPUT_USD_PER_1M", "10.00"))
FX_USD_TO_INR = float(os.getenv("FX_USD_TO_INR", "96.78"))
WINDOW_CLEARANCE_MM = float(os.getenv("WINDOW_CLEARANCE_MM", "600"))
CIRCULATION_MM = float(os.getenv("CIRCULATION_MM", "900"))
RASTER_DPI = float(os.getenv("RASTER_DPI", "150"))
VISION_MAX_EDGE = int(os.getenv("VISION_MAX_EDGE", "2048"))
SKIP_VISION = os.getenv("SKIP_VISION", "").lower() in {"1", "true", "yes"}
SCALE_RESIDUAL_FLAG = 0.08
MAX_WALLS_PER_ROOM = int(os.getenv("MAX_WALLS_PER_ROOM", "40"))
OPENING_WALL_MAX_DIST_PT = float(os.getenv("OPENING_WALL_MAX_DIST_PT", "80"))
