# CCaaS Case Summary Tool

A small Contact-Center-as-a-Service tool that fetches a support case
conversation and produces a structured summary using the Anthropic Messages
API (model: `claude-sonnet-4-6`).

The summary includes:

- **Issue** — what the customer needed
- **Actions taken** — what the agent did
- **Resolution status** — `resolved` / `pending` / `escalated` / `unresolved`
- **Sentiment** — `positive` / `neutral` / `negative` / `mixed`
- **Follow-ups** — outstanding items

Results are returned as structured JSON **plus** a readable text rendering.

## Project layout

```
backend/
  main.py            FastAPI app — POST /summarize {case_id}
  conversation.py    fetch_conversation(case_id) — calls the external case API
                     (the HTTP call is a clearly-marked TODO stub for now)
  summarizer.py      summarize(conversation) — calls the Anthropic Messages API
frontend/
  index.html         Case-id input, "Summarize" button, result panel
  app.js             Calls POST /summarize and renders the summary
.env.example         Environment variable template
requirements.txt
```

## Configuration

All secrets are read from environment variables — nothing is hardcoded.

Copy the template and fill in your values:

```bash
cp .env.example .env
```

| Variable            | Purpose                                              |
| ------------------- | ---------------------------------------------------- |
| `ANTHROPIC_API_KEY` | Anthropic API key for the summarizer                 |
| `CASE_API_BASE_URL` | Base URL of your external case API (no trailing `/`) |
| `CASE_API_TOKEN`    | Bearer token for the case API                        |

> The case API HTTP call in `backend/conversation.py` is currently a **stub**
> that returns a sample conversation, so you can run the app end to end before
> the real endpoint is wired up. Set `case_id` to `missing` (or `404`) to
> exercise the not-found path.

## Run it

From the project root:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn main:app --reload --app-dir backend
```

Then open <http://localhost:8000> — the FastAPI app serves the frontend at the
root and the API at `/summarize`.

### Try the API directly

```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"case_id": "CASE-12345"}'
```

Example response:

```json
{
  "case_id": "CASE-12345",
  "summary": {
    "issue": "Customer was charged twice for their subscription...",
    "actions_taken": ["Confirmed the duplicate charge", "Issued a $29.99 refund"],
    "resolution_status": "resolved",
    "sentiment": "positive",
    "follow_ups": [],
    "text": "Issue:\n  ..."
  }
}
```

## Error handling

| Situation                       | Response                              |
| ------------------------------- | ------------------------------------- |
| Case not found                  | `404` with a descriptive `detail`     |
| Case API fetch failure          | `502` with a descriptive `detail`     |
| Missing API key / summary error | `500` with a descriptive `detail`     |
| Empty / invalid `case_id`       | `422` (request validation)            |

The frontend surfaces these messages in the status panel.

## Wiring up the real case API

Open `backend/conversation.py` and replace the `TODO` stub in
`fetch_conversation()` with the real `httpx` call (a ready-to-use
implementation is included as a comment). It must return:

```json
{
  "case_id": "...",
  "messages": [
    { "role": "customer", "text": "..." },
    { "role": "agent", "text": "..." }
  ]
}
```
