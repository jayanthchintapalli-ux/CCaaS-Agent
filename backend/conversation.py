"""Fetching conversation transcripts from the external case API."""

from __future__ import annotations

import os
from typing import Any

import httpx


class CaseNotFoundError(Exception):
    """Raised when the requested case does not exist."""


class CaseFetchError(Exception):
    """Raised when the case API call fails for any other reason."""


async def fetch_conversation(case_id: str) -> dict[str, Any]:
    """Fetch the conversation transcript for a given case.

    Returns a dict shaped like:
        {
            "case_id": "...",
            "messages": [
                {"role": "customer" | "agent", "text": "..."},
                ...
            ]
        }

    Raises:
        CaseNotFoundError: the case API responded 404.
        CaseFetchError: any other failure (network, auth, 5xx, bad payload).
    """
    base_url = os.environ.get("CASE_API_BASE_URL")
    token = os.environ.get("CASE_API_TOKEN")

    if not base_url:
        raise CaseFetchError("CASE_API_BASE_URL is not configured.")

    # ------------------------------------------------------------------
    # TODO: Replace this stub with the real HTTP call to our case API.
    #
    # The intended implementation looks like:
    #
    #     url = f"{base_url.rstrip('/')}/cases/{case_id}/conversation"
    #     headers = {"Authorization": f"Bearer {token}"}
    #     try:
    #         async with httpx.AsyncClient(timeout=15.0) as client:
    #             resp = await client.get(url, headers=headers)
    #     except httpx.RequestError as exc:
    #         raise CaseFetchError(f"Could not reach case API: {exc}") from exc
    #
    #     if resp.status_code == 404:
    #         raise CaseNotFoundError(f"Case {case_id!r} not found.")
    #     if resp.status_code >= 400:
    #         raise CaseFetchError(
    #             f"Case API returned {resp.status_code}: {resp.text}"
    #         )
    #
    #     return resp.json()  # expected to match the shape documented above
    #
    # Until the real endpoint is wired up, we return a deterministic sample so
    # the rest of the app (and the frontend) can be exercised end to end.
    # ------------------------------------------------------------------
    _ = (token, httpx)  # referenced so linters don't flag the stubbed imports

    if not case_id or not case_id.strip():
        raise CaseNotFoundError("A non-empty case_id is required.")

    if case_id.strip().lower() in {"missing", "404", "unknown"}:
        # Lets you exercise the not-found path without a live API.
        raise CaseNotFoundError(f"Case {case_id!r} not found.")

    return {
        "case_id": case_id,
        "messages": [
            {
                "role": "customer",
                "text": (
                    "Hi, I was charged twice for my subscription this month "
                    "and I'd like a refund for the duplicate charge."
                ),
            },
            {
                "role": "agent",
                "text": (
                    "I'm sorry about that! I can see two charges of $29.99 on "
                    "the 3rd. Let me confirm your account details."
                ),
            },
            {
                "role": "customer",
                "text": "Sure, the email is jordan@example.com.",
            },
            {
                "role": "agent",
                "text": (
                    "Thanks. I've confirmed the duplicate and issued a refund "
                    "of $29.99. It should appear in 3-5 business days. Is there "
                    "anything else I can help with?"
                ),
            },
            {
                "role": "customer",
                "text": "That's perfect, thank you so much!",
            },
        ],
    }
