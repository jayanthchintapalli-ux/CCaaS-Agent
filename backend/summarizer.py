"""Summarize a support conversation with the Google Gemini API (free tier)."""

from __future__ import annotations

import json
import os
from typing import Any

from google import genai
from google.genai import types

# gemini-2.0-flash is available on Google AI Studio's free tier.
MODEL = "gemini-2.0-flash"

_ALLOWED_STATUS = ["resolved", "pending", "escalated", "unresolved"]
_ALLOWED_SENTIMENT = ["positive", "neutral", "negative", "mixed"]


class SummarizationError(Exception):
    """Raised when the summary could not be produced."""


def _transcript(conversation: dict[str, Any]) -> str:
    """Render the conversation messages into a plain-text transcript."""
    lines = []
    for msg in conversation.get("messages", []):
        role = str(msg.get("role", "unknown")).capitalize()
        text = str(msg.get("text", "")).strip()
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def _readable(summary: dict[str, Any]) -> str:
    """Build a human-readable text version of the structured summary."""
    actions = summary.get("actions_taken") or []
    follow_ups = summary.get("follow_ups") or []

    actions_text = (
        "\n".join(f"  - {a}" for a in actions) if actions else "  - None recorded"
    )
    follow_ups_text = (
        "\n".join(f"  - {f}" for f in follow_ups) if follow_ups else "  - None"
    )

    return (
        f"Issue:\n  {summary.get('issue', 'N/A')}\n\n"
        f"Actions taken:\n{actions_text}\n\n"
        f"Resolution status: {summary.get('resolution_status', 'N/A')}\n"
        f"Customer sentiment: {summary.get('sentiment', 'N/A')}\n\n"
        f"Follow-ups:\n{follow_ups_text}"
    )


def _build_prompt(transcript: str) -> str:
    return (
        "You are a contact-center analyst. Summarize the customer support "
        "conversation below.\n\n"
        "Return ONLY a JSON object with exactly these keys:\n"
        '  - "issue": string — what the customer needed.\n'
        '  - "actions_taken": array of strings — actions the agent took.\n'
        '  - "resolution_status": one of '
        f"{_ALLOWED_STATUS}.\n"
        '  - "sentiment": one of '
        f"{_ALLOWED_SENTIMENT}.\n"
        '  - "follow_ups": array of strings — outstanding items (empty array if none).\n\n'
        "Do not include any text outside the JSON object.\n\n"
        f"Conversation transcript:\n{transcript}"
    )


def summarize(conversation: dict[str, Any]) -> dict[str, Any]:
    """Summarize a conversation, returning structured fields plus readable text.

    Returns:
        {
            "issue": str,
            "actions_taken": [str, ...],
            "resolution_status": str,
            "sentiment": str,
            "follow_ups": [str, ...],
            "text": str,   # human-readable rendering
        }

    Raises:
        SummarizationError: missing API key, empty transcript, or API failure.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SummarizationError("GEMINI_API_KEY is not configured.")

    transcript = _transcript(conversation)
    if not transcript:
        raise SummarizationError("Conversation has no messages to summarize.")

    client = genai.Client(api_key=api_key)

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=_build_prompt(transcript),
            config=types.GenerateContentConfig(
                # Ask Gemini to emit pure JSON so it parses cleanly.
                response_mime_type="application/json",
                temperature=0,
            ),
        )
    except Exception as exc:  # google-genai raises various exception types
        raise SummarizationError(f"Gemini API error: {exc}") from exc

    raw = (response.text or "").strip()
    if not raw:
        raise SummarizationError("Model returned no content.")

    try:
        summary = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SummarizationError(f"Could not parse model output: {exc}") from exc

    # Normalize: guarantee the expected keys/shapes the frontend renders.
    summary.setdefault("issue", "")
    summary.setdefault("actions_taken", [])
    summary.setdefault("resolution_status", "unresolved")
    summary.setdefault("sentiment", "neutral")
    summary.setdefault("follow_ups", [])

    summary["text"] = _readable(summary)
    return summary
