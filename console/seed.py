"""Seed the console with a default admin, sample agents, and demo data.

Runs once on startup (guarded on an empty ``users`` table). The default admin
credentials are read from env so they are not hardcoded secrets in the repo:

    CONSOLE_ADMIN_EMAIL   (default: admin@example.com)
    CONSOLE_ADMIN_PASSWORD (default: admin123)

Change the password immediately in a real deployment.
"""

from __future__ import annotations

import json
import os
import random

import db
from auth import hash_password, now_iso


def ensure_seed() -> None:
    if db.query_one("SELECT id FROM users LIMIT 1"):
        return  # already seeded

    admin_email = os.environ.get("CONSOLE_ADMIN_EMAIL", "admin@example.com")
    admin_password = os.environ.get("CONSOLE_ADMIN_PASSWORD", "admin123")

    # --- Users ---
    admin_id = db.execute(
        "INSERT INTO users (email, name, password, role, status, created_at) "
        "VALUES (?, ?, ?, 'admin', 'active', ?)",
        (admin_email, "Console Admin", hash_password(admin_password), now_iso()),
    )
    agent_id = db.execute(
        "INSERT INTO users (email, name, password, role, status, created_at) "
        "VALUES (?, ?, ?, 'agent', 'active', ?)",
        ("agent@example.com", "Priya Sharma", hash_password("agent123"), now_iso()),
    )
    db.execute(
        "INSERT INTO users (email, name, password, role, status, created_at) "
        "VALUES (?, ?, ?, 'supervisor', 'active', ?)",
        ("supervisor@example.com", "Rahul Verma", hash_password("super123"), now_iso()),
    )

    # --- Campaign agents ---
    voice_agent_id = db.execute(
        "INSERT INTO campaign_agents (name, description, prompt, voice, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "Appointment Reminder Bot",
            "Confirms upcoming appointments and offers rescheduling.",
            "You are a friendly assistant reminding customers about their appointment.",
            "en-IN-neural",
            now_iso(),
        ),
    )
    db.execute(
        "INSERT INTO campaign_agents (name, description, prompt, voice, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "Payment Follow-up Bot",
            "Reminds customers about pending invoices.",
            "You are a polite assistant reminding customers about a pending payment.",
            "en-IN-neural",
            now_iso(),
        ),
    )

    # --- Sample campaign with contacts ---
    campaign_id = db.execute(
        """
        INSERT INTO campaigns
          (name, agent_id, cps, max_concurrent, timezone, caller_id_strategy,
           caller_id, window_enabled, window_start, window_end, retry_attempts,
           webhook_url, status, created_by, created_at)
        VALUES (?, ?, 1, 3, 'Asia/Kolkata', 'fixed', '+911171366938', 0,
                '09:00', '18:00', 2, '', 'draft', ?, ?)
        """,
        ("Q1 Appointment Reminders", voice_agent_id, admin_id, now_iso()),
    )
    demo_contacts = [
        ("+919812345670", "Amit Kumar"),
        ("+919812345671", "Sneha Patel"),
        ("+919812345672", "Vikram Singh"),
        ("+919812345673", "Deepa Nair"),
        ("+919812345674", "Arjun Mehta"),
    ]
    db.executemany(
        "INSERT INTO contacts (campaign_id, to_number, name, vars, status, attempts, created_at) "
        "VALUES (?, ?, ?, ?, 'pending', 0, ?)",
        [(campaign_id, n, name, json.dumps({}), now_iso()) for n, name in demo_contacts],
    )

    # --- A few CDR rows so the dashboard isn't empty ---
    for to_number, name in demo_contacts[:3]:
        status = random.choice(["completed", "completed", "no-answer"])
        db.execute(
            "INSERT INTO calls (direction, from_number, to_number, agent_id, campaign_id, "
            "status, disposition, duration_sec, started_at) "
            "VALUES ('manual', ?, ?, ?, NULL, ?, ?, ?, ?)",
            ("+911171366938", to_number, agent_id, status,
             "interested" if status == "completed" else status,
             random.randint(30, 200) if status == "completed" else 0, now_iso()),
        )
