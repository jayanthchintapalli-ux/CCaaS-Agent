"""Agent Console — FastAPI backend.

A single-tenant Contact-Center-as-a-Service operator console:

* Auth + RBAC (admin / supervisor / agent)
* User administration
* Campaign agents + outbound campaigns with CSV contact upload
* Manual dialer
* CDR (Call Detail Records)
* WhatsApp channels + messaging
* Dashboard KPIs

Telephony and WhatsApp sends are *simulated* — there is no real carrier wired
up — but every action is persisted so the console behaves like the real thing.
Point the simulation hooks at your SIP/CPaaS + WhatsApp Cloud API later.
"""

from __future__ import annotations

import csv
import io
import json
import random
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

import db
from auth import (
    create_token,
    current_user,
    hash_password,
    now_iso,
    require_admin,
    revoke_token,
    verify_password,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI(title="Agent Console")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    import seed

    seed.ensure_seed()


# --------------------------------------------------------------------------- #
# Pydantic request models
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)
    role: str = Field(default="agent", pattern="^(admin|supervisor|agent)$")


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = Field(default=None, pattern="^(admin|supervisor|agent)$")
    status: str | None = Field(default=None, pattern="^(active|disabled)$")
    password: str | None = Field(default=None, min_length=6)


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    prompt: str = ""
    voice: str = "default"


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1)
    agent_id: int | None = None
    cps: int = Field(default=1, ge=1)
    max_concurrent: int = Field(default=1, ge=1)
    timezone: str = "Asia/Kolkata"
    caller_id_strategy: str = Field(default="fixed", pattern="^(fixed|round_robin)$")
    caller_id: str = ""
    window_enabled: bool = False
    window_start: str = "09:00"
    window_end: str = "18:00"
    retry_attempts: int = Field(default=0, ge=0, le=5)
    webhook_url: str = ""


class ManualCallRequest(BaseModel):
    to_number: str = Field(..., min_length=3)
    from_number: str = ""
    notes: str = ""


class CallDisposition(BaseModel):
    status: str = Field(..., pattern="^(completed|failed|no-answer|busy|voicemail)$")
    disposition: str = ""
    notes: str = ""


class ChannelCreate(BaseModel):
    display_name: str = Field(..., min_length=1)
    phone_number: str = Field(..., min_length=3)
    phone_number_id: str = ""
    waba_id: str = ""
    provider: str = Field(default="meta", pattern="^(meta|twilio|360dialog)$")


class WaSendRequest(BaseModel):
    to_number: str = Field(..., min_length=3)
    body: str = Field(..., min_length=1)


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@app.post("/api/auth/login")
def login(req: LoginRequest) -> dict:
    user = db.query_one("SELECT * FROM users WHERE email = ?", (req.email,))
    if not user or not verify_password(req.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if user["status"] != "active":
        raise HTTPException(status_code=403, detail="Account is disabled.")
    token = create_token(user["id"])
    return {"token": token, "user": _public_user(user)}


@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.lower().startswith("bearer "):
        revoke_token(authorization.split(" ", 1)[1].strip())
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)) -> dict:
    return {"user": user}


def _public_user(u: dict) -> dict:
    return {k: u[k] for k in ("id", "email", "name", "role", "status")}


# --------------------------------------------------------------------------- #
# Users (admin only)
# --------------------------------------------------------------------------- #
@app.get("/api/users")
def list_users(user: dict = Depends(require_admin)) -> dict:
    rows = db.query(
        "SELECT id, email, name, role, status, created_at FROM users ORDER BY id"
    )
    return {"users": rows}


@app.post("/api/users")
def create_user(req: UserCreate, user: dict = Depends(require_admin)) -> dict:
    if db.query_one("SELECT id FROM users WHERE email = ?", (req.email,)):
        raise HTTPException(status_code=409, detail="A user with that email already exists.")
    uid = db.execute(
        "INSERT INTO users (email, name, password, role, status, created_at) "
        "VALUES (?, ?, ?, ?, 'active', ?)",
        (req.email, req.name, hash_password(req.password), req.role, now_iso()),
    )
    return {"user": db.query_one(
        "SELECT id, email, name, role, status, created_at FROM users WHERE id = ?", (uid,)
    )}


@app.patch("/api/users/{user_id}")
def update_user(user_id: int, req: UserUpdate, user: dict = Depends(require_admin)) -> dict:
    target = db.query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    fields, params = [], []
    if req.name is not None:
        fields.append("name = ?"); params.append(req.name)
    if req.role is not None:
        fields.append("role = ?"); params.append(req.role)
    if req.status is not None:
        fields.append("status = ?"); params.append(req.status)
    if req.password is not None:
        fields.append("password = ?"); params.append(hash_password(req.password))
    if not fields:
        raise HTTPException(status_code=422, detail="No fields to update.")
    params.append(user_id)
    db.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)
    return {"user": db.query_one(
        "SELECT id, email, name, role, status, created_at FROM users WHERE id = ?", (user_id,)
    )}


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, user: dict = Depends(require_admin)) -> dict:
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    if not db.query_one("SELECT id FROM users WHERE id = ?", (user_id,)):
        raise HTTPException(status_code=404, detail="User not found.")
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Campaign agents
# --------------------------------------------------------------------------- #
@app.get("/api/agents")
def list_agents(user: dict = Depends(current_user)) -> dict:
    return {"agents": db.query("SELECT * FROM campaign_agents ORDER BY id DESC")}


@app.post("/api/agents")
def create_agent(req: AgentCreate, user: dict = Depends(current_user)) -> dict:
    aid = db.execute(
        "INSERT INTO campaign_agents (name, description, prompt, voice, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (req.name, req.description, req.prompt, req.voice, now_iso()),
    )
    return {"agent": db.query_one("SELECT * FROM campaign_agents WHERE id = ?", (aid,))}


@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: int, user: dict = Depends(current_user)) -> dict:
    if not db.query_one("SELECT id FROM campaign_agents WHERE id = ?", (agent_id,)):
        raise HTTPException(status_code=404, detail="Agent not found.")
    db.execute("DELETE FROM campaign_agents WHERE id = ?", (agent_id,))
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Campaigns
# --------------------------------------------------------------------------- #
def _campaign_with_stats(row: dict) -> dict:
    stats = db.query_one(
        "SELECT COUNT(*) total, "
        "SUM(status='pending') pending, "
        "SUM(status='called') called, "
        "SUM(status='failed') failed "
        "FROM contacts WHERE campaign_id = ?",
        (row["id"],),
    ) or {}
    row = dict(row)
    row["contacts"] = {
        "total": stats.get("total") or 0,
        "pending": stats.get("pending") or 0,
        "called": stats.get("called") or 0,
        "failed": stats.get("failed") or 0,
    }
    if row.get("agent_id"):
        agent = db.query_one(
            "SELECT name FROM campaign_agents WHERE id = ?", (row["agent_id"],)
        )
        row["agent_name"] = agent["name"] if agent else None
    else:
        row["agent_name"] = None
    return row


@app.get("/api/campaigns")
def list_campaigns(user: dict = Depends(current_user)) -> dict:
    rows = db.query("SELECT * FROM campaigns ORDER BY id DESC")
    return {"campaigns": [_campaign_with_stats(r) for r in rows]}


@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, user: dict = Depends(current_user)) -> dict:
    row = db.query_one("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    contacts = db.query(
        "SELECT * FROM contacts WHERE campaign_id = ? ORDER BY id LIMIT 500", (campaign_id,)
    )
    return {"campaign": _campaign_with_stats(row), "contacts": contacts}


@app.post("/api/campaigns")
def create_campaign(req: CampaignCreate, user: dict = Depends(current_user)) -> dict:
    if req.agent_id is not None and not db.query_one(
        "SELECT id FROM campaign_agents WHERE id = ?", (req.agent_id,)
    ):
        raise HTTPException(status_code=422, detail="Selected campaign agent does not exist.")
    cid = db.execute(
        """
        INSERT INTO campaigns
          (name, agent_id, cps, max_concurrent, timezone, caller_id_strategy,
           caller_id, window_enabled, window_start, window_end, retry_attempts,
           webhook_url, status, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)
        """,
        (
            req.name, req.agent_id, req.cps, req.max_concurrent, req.timezone,
            req.caller_id_strategy, req.caller_id, int(req.window_enabled),
            req.window_start, req.window_end, req.retry_attempts, req.webhook_url,
            user["id"], now_iso(),
        ),
    )
    return {"campaign": _campaign_with_stats(
        db.query_one("SELECT * FROM campaigns WHERE id = ?", (cid,))
    )}


@app.post("/api/campaigns/{campaign_id}/contacts")
async def upload_contacts(
    campaign_id: int, file: UploadFile = File(...), user: dict = Depends(current_user)
) -> dict:
    """Upload a contacts CSV. Must contain a ``to`` column (E.164 numbers)."""
    if not db.query_one("SELECT id FROM campaigns WHERE id = ?", (campaign_id,)):
        raise HTTPException(status_code=404, detail="Campaign not found.")
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="CSV must be UTF-8 encoded.")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "to" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(status_code=422, detail="CSV must include a 'to' column.")
    # Map header names case-insensitively.
    header_map = {f.strip().lower(): f for f in reader.fieldnames}
    to_key = header_map["to"]
    name_key = header_map.get("name")

    rows, imported, skipped = [], 0, 0
    for r in reader:
        number = (r.get(to_key) or "").strip()
        if not number:
            skipped += 1
            continue
        name = (r.get(name_key) or "").strip() if name_key else ""
        extra = {
            k: v for k, v in r.items()
            if k not in (to_key, name_key) and v not in (None, "")
        }
        rows.append((campaign_id, number, name, json.dumps(extra), "pending", 0, now_iso()))
        imported += 1

    if rows:
        db.executemany(
            "INSERT INTO contacts (campaign_id, to_number, name, vars, status, attempts, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    return {"imported": imported, "skipped": skipped}


@app.post("/api/campaigns/{campaign_id}/action")
def campaign_action(campaign_id: int, action: str, user: dict = Depends(current_user)) -> dict:
    """Start / pause / resume / stop a campaign (simulated dialer)."""
    campaign = db.query_one("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    transitions = {
        "start": "running", "resume": "running", "pause": "paused", "stop": "completed",
    }
    if action not in transitions:
        raise HTTPException(status_code=422, detail="Unknown action.")
    new_status = transitions[action]
    db.execute("UPDATE campaigns SET status = ? WHERE id = ?", (new_status, campaign_id))

    dialed = 0
    if action in ("start", "resume"):
        dialed = _simulate_campaign_dialing(campaign)
    return {"status": new_status, "dialed": dialed}


def _simulate_campaign_dialing(campaign: dict) -> int:
    """Dial up to `max_concurrent` pending contacts, writing CDR rows.

    Stand-in for the real dialer loop that would honour CPS / concurrency and
    call your carrier. Here we synchronously resolve a batch so the demo has
    live-looking CDR + progress.
    """
    batch = db.query(
        "SELECT * FROM contacts WHERE campaign_id = ? AND status = 'pending' "
        "ORDER BY id LIMIT ?",
        (campaign["id"], max(campaign["max_concurrent"], 1)),
    )
    outcomes = ["completed", "completed", "completed", "no-answer", "busy", "voicemail", "failed"]
    for c in batch:
        status = random.choice(outcomes)
        duration = random.randint(20, 240) if status == "completed" else 0
        db.execute(
            "INSERT INTO calls (direction, from_number, to_number, agent_id, campaign_id, "
            "status, disposition, duration_sec, started_at) "
            "VALUES ('outbound', ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                campaign["caller_id"], c["to_number"], campaign["agent_id"], campaign["id"],
                status, "auto" if status == "completed" else status, duration, now_iso(),
            ),
        )
        contact_status = "called" if status in ("completed", "voicemail") else "failed"
        db.execute(
            "UPDATE contacts SET status = ?, attempts = attempts + 1 WHERE id = ?",
            (contact_status, c["id"]),
        )
    return len(batch)


@app.delete("/api/campaigns/{campaign_id}")
def delete_campaign(campaign_id: int, user: dict = Depends(current_user)) -> dict:
    if not db.query_one("SELECT id FROM campaigns WHERE id = ?", (campaign_id,)):
        raise HTTPException(status_code=404, detail="Campaign not found.")
    db.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Manual dialer + CDR
# --------------------------------------------------------------------------- #
@app.post("/api/dial")
def manual_dial(req: ManualCallRequest, user: dict = Depends(current_user)) -> dict:
    """Place a manual outbound call and open a CDR record (simulated connect)."""
    call_id = db.execute(
        "INSERT INTO calls (direction, from_number, to_number, agent_id, status, notes, "
        "duration_sec, started_at) VALUES ('manual', ?, ?, ?, 'completed', ?, ?, ?)",
        (
            req.from_number, req.to_number, user["id"], req.notes,
            random.randint(15, 300), now_iso(),
        ),
    )
    return {"call": db.query_one("SELECT * FROM calls WHERE id = ?", (call_id,))}


@app.patch("/api/calls/{call_id}")
def disposition_call(
    call_id: int, req: CallDisposition, user: dict = Depends(current_user)
) -> dict:
    if not db.query_one("SELECT id FROM calls WHERE id = ?", (call_id,)):
        raise HTTPException(status_code=404, detail="Call not found.")
    db.execute(
        "UPDATE calls SET status = ?, disposition = ?, notes = ? WHERE id = ?",
        (req.status, req.disposition, req.notes, call_id),
    )
    return {"call": db.query_one("SELECT * FROM calls WHERE id = ?", (call_id,))}


@app.get("/api/cdr")
def list_cdr(
    user: dict = Depends(current_user),
    direction: str | None = None,
    status: str | None = None,
    campaign_id: int | None = None,
    search: str | None = None,
    limit: int = 200,
) -> dict:
    where, params = [], []
    if direction:
        where.append("c.direction = ?"); params.append(direction)
    if status:
        where.append("c.status = ?"); params.append(status)
    if campaign_id:
        where.append("c.campaign_id = ?"); params.append(campaign_id)
    if search:
        where.append("(c.to_number LIKE ? OR c.from_number LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(min(max(limit, 1), 1000))
    rows = db.query(
        f"""
        SELECT c.*, u.name AS agent_name, cp.name AS campaign_name
        FROM calls c
        LEFT JOIN users u ON u.id = c.agent_id
        LEFT JOIN campaigns cp ON cp.id = c.campaign_id
        {clause}
        ORDER BY c.id DESC LIMIT ?
        """,
        params,
    )
    return {"calls": rows}


# --------------------------------------------------------------------------- #
# WhatsApp channels + messaging
# --------------------------------------------------------------------------- #
@app.get("/api/wa/channels")
def list_channels(user: dict = Depends(current_user)) -> dict:
    rows = db.query("SELECT * FROM wa_channels ORDER BY id DESC")
    for r in rows:
        counts = db.query_one(
            "SELECT COUNT(*) total, SUM(direction='inbound') inbound "
            "FROM wa_messages WHERE channel_id = ?",
            (r["id"],),
        ) or {}
        r["message_count"] = counts.get("total") or 0
    return {"channels": rows}


@app.post("/api/wa/channels")
def create_channel(req: ChannelCreate, user: dict = Depends(current_user)) -> dict:
    cid = db.execute(
        "INSERT INTO wa_channels (display_name, phone_number, phone_number_id, waba_id, "
        "provider, status, created_at) VALUES (?, ?, ?, ?, ?, 'connected', ?)",
        (req.display_name, req.phone_number, req.phone_number_id, req.waba_id,
         req.provider, now_iso()),
    )
    return {"channel": db.query_one("SELECT * FROM wa_channels WHERE id = ?", (cid,))}


@app.delete("/api/wa/channels/{channel_id}")
def delete_channel(channel_id: int, user: dict = Depends(current_user)) -> dict:
    if not db.query_one("SELECT id FROM wa_channels WHERE id = ?", (channel_id,)):
        raise HTTPException(status_code=404, detail="Channel not found.")
    db.execute("DELETE FROM wa_channels WHERE id = ?", (channel_id,))
    return {"ok": True}


@app.get("/api/wa/channels/{channel_id}/messages")
def list_messages(channel_id: int, user: dict = Depends(current_user)) -> dict:
    if not db.query_one("SELECT id FROM wa_channels WHERE id = ?", (channel_id,)):
        raise HTTPException(status_code=404, detail="Channel not found.")
    rows = db.query(
        "SELECT * FROM wa_messages WHERE channel_id = ? ORDER BY id", (channel_id,)
    )
    return {"messages": rows}


@app.post("/api/wa/channels/{channel_id}/messages")
def send_message(
    channel_id: int, req: WaSendRequest, user: dict = Depends(current_user)
) -> dict:
    channel = db.query_one("SELECT * FROM wa_channels WHERE id = ?", (channel_id,))
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found.")
    mid = db.execute(
        "INSERT INTO wa_messages (channel_id, direction, peer, body, status, created_at) "
        "VALUES (?, 'outbound', ?, ?, 'delivered', ?)",
        (channel_id, req.to_number, req.body, now_iso()),
    )
    # Simulate an auto-reply so the conversation view has two-way traffic.
    if random.random() < 0.6:
        db.execute(
            "INSERT INTO wa_messages (channel_id, direction, peer, body, status, created_at) "
            "VALUES (?, 'inbound', ?, ?, 'received', ?)",
            (channel_id, req.to_number,
             random.choice(["Thanks!", "Got it 👍", "Please call me back.", "Okay"]),
             now_iso()),
        )
    return {"message": db.query_one("SELECT * FROM wa_messages WHERE id = ?", (mid,))}


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@app.get("/api/dashboard")
def dashboard(user: dict = Depends(current_user)) -> dict:
    calls_total = db.query_one("SELECT COUNT(*) n FROM calls")["n"]
    calls_completed = db.query_one("SELECT COUNT(*) n FROM calls WHERE status='completed'")["n"]
    calls_failed = db.query_one(
        "SELECT COUNT(*) n FROM calls WHERE status IN ('failed','no-answer','busy')"
    )["n"]
    avg = db.query_one(
        "SELECT AVG(duration_sec) a FROM calls WHERE status='completed'"
    )["a"] or 0
    by_status = db.query(
        "SELECT status, COUNT(*) n FROM calls GROUP BY status ORDER BY n DESC"
    )
    by_direction = db.query(
        "SELECT direction, COUNT(*) n FROM calls GROUP BY direction"
    )
    return {
        "calls_total": calls_total,
        "calls_completed": calls_completed,
        "calls_failed": calls_failed,
        "avg_duration_sec": round(avg, 1),
        "answer_rate": round(100 * calls_completed / calls_total, 1) if calls_total else 0,
        "campaigns_total": db.query_one("SELECT COUNT(*) n FROM campaigns")["n"],
        "campaigns_running": db.query_one(
            "SELECT COUNT(*) n FROM campaigns WHERE status='running'"
        )["n"],
        "agents_total": db.query_one("SELECT COUNT(*) n FROM campaign_agents")["n"],
        "users_total": db.query_one("SELECT COUNT(*) n FROM users")["n"],
        "wa_channels": db.query_one("SELECT COUNT(*) n FROM wa_channels")["n"],
        "wa_messages": db.query_one("SELECT COUNT(*) n FROM wa_messages")["n"],
        "by_status": by_status,
        "by_direction": by_direction,
        "recent_calls": db.query(
            """
            SELECT c.*, cp.name AS campaign_name FROM calls c
            LEFT JOIN campaigns cp ON cp.id = c.campaign_id
            ORDER BY c.id DESC LIMIT 8
            """
        ),
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Static SPA
# --------------------------------------------------------------------------- #
_static = Path(__file__).resolve().parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="console")
