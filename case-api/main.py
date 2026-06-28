"""A minimal, free sample Case API.

Serves canned support conversations so the CCaaS summary tool has a real
backend to call. Deploy this as its own service; point the summary tool's
CASE_API_BASE_URL at this service's URL and CASE_API_TOKEN at API_TOKEN below.

Contract:
    GET /cases/{case_id}/conversation
    Authorization: Bearer {API_TOKEN}   (only enforced if API_TOKEN is set)

    200 -> {"case_id": "...", "messages": [{"role": "...", "text": "..."}]}
    401 -> invalid/missing token
    404 -> unknown case
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI(title="Sample Case API")

# The token clients must present. Set this in the environment; if left empty,
# auth is disabled (handy for quick local testing).
API_TOKEN = os.environ.get("CASE_API_TOKEN", "")

# A tiny in-memory "database" of sample conversations.
SAMPLE_CASES: dict[str, list[dict[str, str]]] = {
    "CASE-12345": [
        {
            "role": "customer",
            "text": (
                "Hi, I was charged twice for my subscription this month and "
                "I'd like a refund for the duplicate charge."
            ),
        },
        {
            "role": "agent",
            "text": (
                "I'm sorry about that! I can see two charges of $29.99 on the "
                "3rd. Let me confirm your account details."
            ),
        },
        {"role": "customer", "text": "Sure, the email is jordan@example.com."},
        {
            "role": "agent",
            "text": (
                "Thanks. I've confirmed the duplicate and issued a refund of "
                "$29.99. It should appear in 3-5 business days. Anything else?"
            ),
        },
        {"role": "customer", "text": "That's perfect, thank you so much!"},
    ],
    "CASE-67890": [
        {
            "role": "customer",
            "text": "My internet has been down since this morning and I work from home.",
        },
        {
            "role": "agent",
            "text": (
                "I'm really sorry. I ran a line test and see an outage in your "
                "area. Our team is working on it; ETA is 4 hours."
            ),
        },
        {"role": "customer", "text": "That's frustrating, but okay. Can you notify me when it's fixed?"},
        {
            "role": "agent",
            "text": (
                "Absolutely — I've enabled SMS alerts to your number and opened "
                "ticket #4471 to track it."
            ),
        },
    ],
}


def _check_auth(authorization: str | None) -> None:
    if not API_TOKEN:
        return  # auth disabled
    if authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid or missing token.")


@app.get("/cases/{case_id}/conversation")
def get_conversation(
    case_id: str, authorization: str | None = Header(default=None)
) -> dict:
    _check_auth(authorization)
    messages = SAMPLE_CASES.get(case_id)
    if messages is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id!r} not found.")
    return {"case_id": case_id, "messages": messages}


@app.get("/cases")
def list_cases(authorization: str | None = Header(default=None)) -> dict:
    """Convenience endpoint: list the available sample case IDs."""
    _check_auth(authorization)
    return {"cases": list(SAMPLE_CASES.keys())}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
