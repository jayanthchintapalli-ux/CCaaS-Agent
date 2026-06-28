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

    Calls:  GET {CASE_API_BASE_URL}/cases/{case_id}/conversation
            Authorization: Bearer {CASE_API_TOKEN}

    Expects the API to return JSON shaped like:
        {
            "case_id": "...",
            "messages": [
                {"role": "customer" | "agent", "text": "..."},
                ...
            ]
        }

    Raises:
        CaseNotFoundError: the case API responded 404.
        CaseFetchError: any other failure (config, network, auth, 5xx, bad payload).
    """
    if not case_id or not case_id.strip():
        raise CaseNotFoundError("A non-empty case_id is required.")

    base_url = os.environ.get("CASE_API_BASE_URL")
    token = os.environ.get("CASE_API_TOKEN")

    if not base_url:
        raise CaseFetchError("CASE_API_BASE_URL is not configured.")

    url = f"{base_url.rstrip('/')}/cases/{case_id}/conversation"
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        raise CaseFetchError(f"Could not reach case API: {exc}") from exc

    if resp.status_code == 404:
        raise CaseNotFoundError(f"Case {case_id!r} not found.")
    if resp.status_code >= 400:
        raise CaseFetchError(
            f"Case API returned {resp.status_code}: {resp.text}"
        )

    try:
        data = resp.json()
    except ValueError as exc:
        raise CaseFetchError("Case API returned a non-JSON response.") from exc

    if not isinstance(data, dict) or "messages" not in data:
        raise CaseFetchError("Case API response is missing a 'messages' field.")

    return data
