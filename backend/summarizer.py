"""Summarize a support conversation with the Anthropic Messages API."""

from __future__ import annotations

import os
from typing import Any

import anthropic

MODEL = "claude-sonnet-4-6"

# JSON schema for the structured summary. Structured outputs guarantee the
# response parses cleanly into the fields the frontend renders.
SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "issue": {
            "type": "string",
            "description": "What the customer's problem or request was.",
        },
        "actions_taken": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concrete actions the agent took during the conversation.",
        },
        "resolution_status": {
            "type": "string",
            "enum": ["resolved", "pending", "escalated", "unresolved"],
            "description": "Current state of the case.",
        },
        "sentiment": {
            "type": "string",
            "enum": ["positive", "neutral", "negative", "mixed"],
            "description": "Overall customer sentiment by the end of the conversation.",
        },
        "follow_ups": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Outstanding follow-up items, if any.",
        },
    },
    "required": [
        "issue",
        "actions_taken",
        "resolution_status",
        "sentiment",
        "follow_ups",
    ],
    "additionalProperties": False,
}


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
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SummarizationError("ANTHROPIC_API_KEY is not configured.")

    transcript = _transcript(conversation)
    if not transcript:
        raise SummarizationError("Conversation has no messages to summarize.")

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    prompt = (
        "You are a contact-center analyst. Summarize the following customer "
        "support conversation. Identify the customer's issue, the actions the "
        "agent took, the resolution status, the customer's overall sentiment, "
        "and any outstanding follow-ups.\n\n"
        f"Conversation transcript:\n{transcript}"
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {"type": "json_schema", "schema": SUMMARY_SCHEMA}
            },
        )
    except anthropic.APIError as exc:
        raise SummarizationError(f"Anthropic API error: {exc}") from exc

    # With output_config.format, the first text block is guaranteed valid JSON.
    import json

    text_block = next((b for b in response.content if b.type == "text"), None)
    if text_block is None:
        raise SummarizationError("Model returned no text content.")

    try:
        summary = json.loads(text_block.text)
    except json.JSONDecodeError as exc:
        raise SummarizationError(f"Could not parse model output: {exc}") from exc

    summary["text"] = _readable(summary)
    return summary
