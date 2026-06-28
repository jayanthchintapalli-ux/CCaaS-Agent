# CCaaS Case Summary Tool

A small Contact-Center-as-a-Service tool that fetches a support case
conversation and produces a structured summary using the **Google Gemini API**
(model: `gemini-2.0-flash`, free tier).

The summary includes:

- **Issue** — what the customer needed
- **Actions taken** — what the agent did
- **Resolution status** — `resolved` / `pending` / `escalated` / `unresolved`
- **Sentiment** — `positive` / `neutral` / `negative` / `mixed`
- **Follow-ups** — outstanding items

Results are returned as structured JSON **plus** a readable text rendering.

## Project layout

```
backend/             The summary tool (calls Gemini + the case API)
  main.py            FastAPI app — POST /summarize {case_id}; serves frontend
  conversation.py    fetch_conversation(case_id) — calls the case API over HTTP
  summarizer.py      summarize(conversation) — calls the Gemini API
frontend/
  index.html         Case-id input, "Summarize" button, result panel
  app.js             Calls POST /summarize and renders the summary
case-api/            A standalone, free sample Case API (its own service)
  main.py            GET /cases/{case_id}/conversation with bearer auth
  requirements.txt
.env.example         Environment variable template
requirements.txt     Dependencies for the summary tool
```

This repo contains **two deployable services**:

1. **The summary tool** (`backend/` + `frontend/`) — what users interact with.
2. **The sample case API** (`case-api/`) — serves canned conversations so the
   tool has a real backend to call. Replace it later with your real case system.

## Configuration

All secrets are read from environment variables — nothing is hardcoded.

```bash
cp .env.example .env
```

| Variable            | Used by      | Purpose                                                |
| ------------------- | ------------ | ------------------------------------------------------ |
| `GEMINI_API_KEY`    | summary tool | Gemini key from <https://aistudio.google.com/app/apikey> |
| `CASE_API_BASE_URL` | summary tool | URL of the case API service (no trailing `/`)          |
| `CASE_API_TOKEN`    | both         | Shared bearer secret — **same value in both services** |

`CASE_API_TOKEN` is a secret **you invent**. Set the same string for the case
API (which checks it) and the summary tool (which sends it).

## Run locally

### 1. Start the case API (terminal A)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r case-api/requirements.txt
CASE_API_TOKEN=mysecret uvicorn main:app --app-dir case-api --port 8001
```

### 2. Start the summary tool (terminal B)

```bash
source .venv/bin/activate
pip install -r requirements.txt
GEMINI_API_KEY=your_key \
CASE_API_BASE_URL=http://localhost:8001 \
CASE_API_TOKEN=mysecret \
uvicorn main:app --app-dir backend --reload --port 8000
```

Open <http://localhost:8000>, enter `CASE-12345` (or `CASE-67890`), and click
**Summarize**. Enter an unknown ID to see the 404 path.

## Deploy on Render (two web services, same repo)

### Service 1 — Case API

| Field | Value |
|-------|-------|
| Build Command | `pip install -r case-api/requirements.txt` |
| Start Command | `uvicorn main:app --app-dir case-api --host 0.0.0.0 --port $PORT` |
| Env var | `CASE_API_TOKEN` = your chosen secret |

Note its URL, e.g. `https://my-case-api.onrender.com`.

### Service 2 — Summary tool

| Field | Value |
|-------|-------|
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
| Env vars | `GEMINI_API_KEY` = your Gemini key |
|          | `CASE_API_BASE_URL` = the case API URL from Service 1 |
|          | `CASE_API_TOKEN` = the **same** secret as Service 1 |

## API

```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"case_id": "CASE-12345"}'
```

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

| Situation                       | Response                          |
| ------------------------------- | --------------------------------- |
| Case not found                  | `404` with a descriptive `detail` |
| Case API fetch failure          | `502` with a descriptive `detail` |
| Missing API key / summary error | `500` with a descriptive `detail` |
| Empty / invalid `case_id`       | `422` (request validation)        |

## Using your real case system later

When you have a real case backend, just point `CASE_API_BASE_URL` /
`CASE_API_TOKEN` at it instead of the sample `case-api/` service. As long as it
exposes `GET /cases/{case_id}/conversation` returning
`{"case_id": ..., "messages": [{"role", "text"}, ...]}`, no code changes are
needed.
