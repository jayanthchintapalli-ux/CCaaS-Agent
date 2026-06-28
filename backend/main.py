"""FastAPI app exposing POST /summarize for CCaaS case summaries."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Load .env from the project root (one level up from backend/) if present.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from conversation import (  # noqa: E402  (import after load_dotenv)
    CaseFetchError,
    CaseNotFoundError,
    fetch_conversation,
)
from summarizer import SummarizationError, summarize  # noqa: E402

app = FastAPI(title="CCaaS Case Summary Tool")

# Allow the static frontend (and local dev tools) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SummarizeRequest(BaseModel):
    case_id: str = Field(..., min_length=1, description="The case identifier.")


@app.post("/summarize")
async def summarize_case(req: SummarizeRequest) -> dict:
    """Fetch a case conversation and return a structured + readable summary."""
    try:
        conversation = await fetch_conversation(req.case_id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseFetchError as exc:
        # Upstream/integration failure → 502 Bad Gateway.
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        summary = summarize(conversation)
    except SummarizationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"case_id": req.case_id, "summary": summary}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# Serve the static frontend at the root, if the directory exists.
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if _frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
