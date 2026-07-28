# Agent Console

An operator console for a Contact-Center-as-a-Service (CCaaS) platform. It
brings campaign management, a manual dialer, call detail records, WhatsApp
messaging, dashboards, and user administration together in one dark-themed
single-page app.

> Telephony and WhatsApp sending are **simulated** — there is no real carrier or
> WhatsApp Cloud API wired up. Every action is persisted so the console behaves
> like the real thing; swap the simulation hooks for your SIP/CPaaS and the
> WhatsApp Cloud API when you go live.

## Features

| Area              | What it does                                                                 |
| ----------------- | ---------------------------------------------------------------------------- |
| **Dashboard**     | Live KPIs — total calls, answer rate, avg duration, running campaigns, WhatsApp volume, users, calls-by-status, recent calls |
| **Campaigns**     | Create outbound campaigns (CPS, max concurrency, caller-ID strategy, daily window, retries, webhook), upload a contacts CSV, and start/pause/resume the (simulated) dialer |
| **Campaign Agents** | Manage the voice agents (prompt + voice) that power campaigns              |
| **Manual Dial**   | Keypad dialer to place an ad-hoc outbound call                               |
| **CDR**           | Searchable, filterable Call Detail Records with CSV export                   |
| **WhatsApp**      | Connect WhatsApp Business channels and send/receive messages per channel     |
| **Users (Admin)** | Add / edit / disable / delete console users with roles                       |

## Roles (RBAC)

- **admin** — full access, including user administration
- **supervisor** — everything except user administration
- **agent** — everything except user administration

The **Administration** section of the sidebar is only shown to admins, and the
user-management API is admin-only on the server too.

## Architecture

```
console/
  main.py          FastAPI app — all /api routes; serves the SPA
  db.py            SQLite schema + tiny query helpers (stdlib sqlite3, no ORM)
  auth.py          PBKDF2 password hashing, bearer-token sessions, RBAC deps
  seed.py          First-run seed: default admin, sample agents, demo data
  requirements.txt
  static/
    index.html     App shell + login view
    styles.css     Dark theme (warm near-black + orange accent)
    app.js         SPA — routing + all views (vanilla JS, no build step)
```

Data lives in a single SQLite file (`console/console.db` by default, override
with `CONSOLE_DB_PATH`). The database and seed data are created automatically
on first startup.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r console/requirements.txt
uvicorn main:app --app-dir console --reload --port 8000
```

Open <http://localhost:8000> and sign in with the seeded admin
(`admin@example.com` / `admin123` by default — override via
`CONSOLE_ADMIN_EMAIL` / `CONSOLE_ADMIN_PASSWORD`).

Other seeded logins: `agent@example.com` / `agent123`,
`supervisor@example.com` / `super123`.

## Deploy on Render (single web service)

| Field         | Value                                                               |
| ------------- | ------------------------------------------------------------------- |
| Build Command | `pip install -r console/requirements.txt`                           |
| Start Command | `uvicorn main:app --app-dir console --host 0.0.0.0 --port $PORT`    |
| Env vars      | `CONSOLE_ADMIN_EMAIL`, `CONSOLE_ADMIN_PASSWORD`, `CONSOLE_DB_PATH`  |

SQLite on Render's ephemeral disk resets on redeploy — attach a persistent
disk and point `CONSOLE_DB_PATH` at it for durable data.

## Contacts CSV format

The upload must include a `to` column (E.164 numbers). A `name` column is used
if present; any other columns are stored as per-contact variables.

```csv
to,name,city
+919812345670,Amit Kumar,Delhi
+919812345671,Sneha Patel,Mumbai
```

## API overview

All routes are under `/api` and (except `/api/auth/login` and `/api/health`)
require an `Authorization: Bearer <token>` header from login.

| Method | Path                                   | Notes                          |
| ------ | -------------------------------------- | ------------------------------ |
| POST   | `/api/auth/login`                      | → `{token, user}`              |
| POST   | `/api/auth/logout`                     | revokes the token              |
| GET    | `/api/dashboard`                       | KPIs                           |
| GET/POST/PATCH/DELETE | `/api/users[/{id}]`     | **admin only**                 |
| GET/POST/DELETE | `/api/agents[/{id}]`          | campaign agents                |
| GET/POST/DELETE | `/api/campaigns[/{id}]`       | campaigns                      |
| POST   | `/api/campaigns/{id}/contacts`         | multipart CSV upload           |
| POST   | `/api/campaigns/{id}/action?action=`   | start/pause/resume/stop        |
| POST   | `/api/dial`                            | manual call                    |
| PATCH  | `/api/calls/{id}`                      | disposition a call             |
| GET    | `/api/cdr`                             | filter: direction/status/search|
| GET/POST/DELETE | `/api/wa/channels[/{id}]`     | WhatsApp channels              |
| GET/POST | `/api/wa/channels/{id}/messages`     | list / send messages           |

## Going to production

Replace the simulated pieces with real integrations:

- **Dialer** — `_simulate_campaign_dialing()` in `main.py` writes fake CDR rows.
  Point it at your SIP/CPaaS originate API and drive it from a worker that
  honours the campaign's CPS / max-concurrency / calling-window settings.
- **Manual dial** — `POST /api/dial` should originate a real call and stream
  status back (webhook) rather than resolving instantly.
- **WhatsApp** — `POST /api/wa/channels/{id}/messages` should call the WhatsApp
  Cloud API; add an inbound webhook to record received messages.
- **Auth** — swap the bearer-token table for your IdP / OAuth, and move secrets
  out of env defaults.
