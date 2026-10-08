# Floor Plan Analyser POC

Hybrid extractor: CAD vectors for geometry, dimension labels for scale, **OpenAI `gpt-4o`** for room names and opening semantics.

This service does **not** place furniture. It returns **room-by-room** JSON for the furniture-placement POC:

`rooms[] → walls[] → openings[] → keepouts[]`

plus scale/page metadata and OpenAI `usage` (input/output tokens, cost USD and INR at `FX_USD_TO_INR`, default 96.78). Existing furniture on furnished PDFs is ignored.

## Setup

Use the existing interpreter `C:\Users\Sahil\.venv` (do not create a new venv).

```powershell
C:\Users\Sahil\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Set `OPENAI_API_KEY` in `.env`. Optional: `OPENAI_MODEL=gpt-4o`.

## Run

```powershell
cd backend
C:\Users\Sahil\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 — upload a PDF from `floor-plans-pdf/`.

- `POST /api/analyze` multipart field `file`
- `GET /api/jobs/{id}/overlay.png`
- `GET /api/schema` OpenAPI document

## Tests

```powershell
$env:SKIP_VISION="true"
C:\Users\Sahil\.venv\Scripts\python.exe -m pytest tests -q
```

Sample plans: `floor-plans-pdf/blank-floor-plans-pdf/` and `floor-plans-pdf/furnished-floor-plan-pdf/`.
