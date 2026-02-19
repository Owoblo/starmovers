"""FastAPI sidecar — serves outreach data to the dashboard.

Includes: APScheduler for autonomous operation, health checks,
follow-up engine, DB backups, pipeline run logging.
"""

import asyncio
import logging
import os
import random
import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from outreach_engine import queue_manager
from outreach_engine.email_sender import send_email
from outreach_engine.email_discovery import (
    discover_email, discover_batch, rediscover_email,
    discover_team_emails, scrape_team_members,
)
from outreach_engine.config import cfg

logger = logging.getLogger(__name__)

app = FastAPI(title="Saturn Star Outreach Sidecar", version="2.0.0")

_cors_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
]
if cfg.dashboard_url:
    _cors_origins.append(cfg.dashboard_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1x1 transparent GIF
TRACKING_PIXEL = bytes([
    0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00,
    0x80, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x21,
    0xF9, 0x04, 0x01, 0x00, 0x00, 0x00, 0x00, 0x2C, 0x00, 0x00,
    0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x02, 0x02, 0x44,
    0x01, 0x00, 0x3B,
])

_pipeline_running = False
_batch_sending = False
_batch_progress = {"sent": 0, "failed": 0, "total": 0, "done": False}


# ── DB auto-init on startup ──

@app.on_event("startup")
def ensure_db():
    # Ensure parent dir exists (Render persistent disk)
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)

    if not cfg.db_path.exists():
        logger.info("Database not found — initializing...")
        from outreach_engine.db.init_db import init_db
        from outreach_engine.csv_importer import import_all
        init_db(cfg.db_path)
        import_all()

    # Run migrations — add columns if they don't exist yet
    import sqlite3
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    for col, typedef in [
        ("reply_type", "TEXT DEFAULT ''"),
        ("reply_snippet", "TEXT DEFAULT ''"),
        ("redirect_email", "TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE outreach_bundles ADD COLUMN {col} {typedef}")
        except Exception:
            pass  # column already exists

    # contacts table migrations
    for col, typedef in [
        ("source_contact_id", "INTEGER DEFAULT NULL"),
        ("company_size", "TEXT DEFAULT ''"),
        ("company_type", "TEXT DEFAULT ''"),
        ("confidence_score", "INTEGER DEFAULT 0"),
        ("account_status", "TEXT DEFAULT 'cold'"),
        ("last_touch_date", "TEXT DEFAULT ''"),
        ("next_action_date", "TEXT DEFAULT ''"),
        ("next_action", "TEXT DEFAULT ''"),
        ("decision_maker_found", "INTEGER DEFAULT 0"),
        ("procurement_required", "INTEGER DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE contacts ADD COLUMN {col} {typedef}")
        except Exception:
            pass

    # pipeline_runs table
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_type TEXT DEFAULT 'headless',
            status TEXT DEFAULT 'running',
            started_at TEXT NOT NULL,
            ended_at TEXT,
            stats_json TEXT DEFAULT '{}',
            error TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);
    """)

    # news_signals table
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS news_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            headline TEXT DEFAULT '',
            content_snippet TEXT DEFAULT '',
            signal_type TEXT NOT NULL,
            company_name TEXT DEFAULT '',
            opportunity TEXT DEFAULT '',
            city TEXT DEFAULT '',
            urgency TEXT DEFAULT 'medium',
            recommended_action TEXT DEFAULT '',
            contact_id INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'new',
            published_date TEXT DEFAULT '',
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_url ON news_signals(source_url);
        CREATE INDEX IF NOT EXISTS idx_signals_status ON news_signals(status);
        CREATE INDEX IF NOT EXISTS idx_signals_type ON news_signals(signal_type);
    """)

    # CRM tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS touch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            direction TEXT DEFAULT 'outbound',
            subject TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            outcome TEXT DEFAULT '',
            logged_by TEXT DEFAULT 'system',
            touch_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id) REFERENCES contacts(id)
        );
        CREATE INDEX IF NOT EXISTS idx_touch_log_contact ON touch_log(contact_id);
        CREATE INDEX IF NOT EXISTS idx_touch_log_channel ON touch_log(channel);

        CREATE TABLE IF NOT EXISTS ecosystem_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            role TEXT NOT NULL,
            company TEXT DEFAULT '',
            source_contact_id INTEGER DEFAULT NULL,
            notes TEXT DEFAULT '',
            promoted_contact_id INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_contact_id) REFERENCES contacts(id)
        );
        CREATE INDEX IF NOT EXISTS idx_ecosystem_role ON ecosystem_contacts(role);

        CREATE TABLE IF NOT EXISTS partner_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_name TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE,
            discount_percent REAL DEFAULT 0,
            bonus_per_referral REAL DEFAULT 0,
            total_referrals INTEGER DEFAULT 0,
            total_revenue REAL DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER DEFAULT NULL,
            partner_code TEXT DEFAULT '',
            job_type TEXT DEFAULT 'commercial',
            status TEXT DEFAULT 'quoted',
            quote_amount REAL DEFAULT 0,
            final_amount REAL DEFAULT 0,
            move_date TEXT DEFAULT '',
            origin_address TEXT DEFAULT '',
            destination_address TEXT DEFAULT '',
            crew_size INTEGER DEFAULT 0,
            truck_count INTEGER DEFAULT 0,
            labor_hours REAL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contact_id) REFERENCES contacts(id)
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_contact ON jobs(contact_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_partner ON jobs(partner_code);
        CREATE INDEX IF NOT EXISTS idx_contacts_account_status ON contacts(account_status);

        CREATE TABLE IF NOT EXISTS account_research (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            user_notes TEXT DEFAULT '',
            research_status TEXT DEFAULT 'new',
            company_brief TEXT DEFAULT '',
            company_type TEXT DEFAULT '',
            approach_strategy TEXT DEFAULT '',
            angles TEXT DEFAULT '[]',
            procurement_notes TEXT DEFAULT '',
            target_contacts TEXT DEFAULT '[]',
            recommended_first_message TEXT DEFAULT '',
            stages_json TEXT DEFAULT '[]',
            current_stage INTEGER DEFAULT 0,
            contact_id INTEGER DEFAULT NULL,
            city TEXT DEFAULT '',
            industry TEXT DEFAULT '',
            priority TEXT DEFAULT 'medium',
            next_action_date TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_research_status ON account_research(research_status);
        CREATE INDEX IF NOT EXISTS idx_research_priority ON account_research(priority);
    """)

    # Telegram tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS telegram_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_msg_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            raw_text TEXT NOT NULL,
            parsed_json TEXT DEFAULT '{}',
            intent TEXT DEFAULT '',
            company_name TEXT DEFAULT '',
            group_id TEXT DEFAULT '',
            idea_id INTEGER DEFAULT NULL,
            processed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS telegram_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            notification_type TEXT NOT NULL,
            reference_id INTEGER DEFAULT NULL,
            message_text TEXT DEFAULT '',
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_tg_notif_chat ON telegram_notifications(chat_id);
        CREATE INDEX IF NOT EXISTS idx_tg_notif_type ON telegram_notifications(notification_type);
    """)

    conn.commit()
    conn.close()
    logger.info("Database ready at %s", cfg.db_path)


# ── Request models ──

class EditRequest(BaseModel):
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    notes: Optional[str] = None


class BatchSendRequest(BaseModel):
    bundle_ids: list[int]


class DiscoverRequest(BaseModel):
    contact_ids: list[int] = []
    limit: int = 10


class SnoozeRequest(BaseModel):
    until: str = ""


class AccountStatusRequest(BaseModel):
    status: str
    notes: str = ""


class TouchLogRequest(BaseModel):
    contact_id: int
    channel: str
    direction: str = "outbound"
    subject: str = ""
    notes: str = ""
    outcome: str = ""


class EcosystemCreateRequest(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    role: str
    company: str = ""
    source_contact_id: Optional[int] = None
    notes: str = ""


class PartnerCreateRequest(BaseModel):
    partner_name: str
    code: str
    discount_percent: float = 0
    bonus_per_referral: float = 0


class JobCreateRequest(BaseModel):
    contact_id: Optional[int] = None
    partner_code: str = ""
    job_type: str = "commercial"
    quote_amount: float = 0
    move_date: str = ""
    origin_address: str = ""
    destination_address: str = ""
    crew_size: int = 0
    truck_count: int = 0
    notes: str = ""


class JobUpdateRequest(BaseModel):
    status: Optional[str] = None
    final_amount: Optional[float] = None
    move_date: Optional[str] = None
    crew_size: Optional[int] = None
    truck_count: Optional[int] = None
    labor_hours: Optional[float] = None
    notes: Optional[str] = None


class IdeaSubmitRequest(BaseModel):
    company_name: str
    user_notes: str = ""
    city: str = "Windsor-Essex"
    industry: str = ""
    priority: str = "medium"
    auto_research: bool = True


class IdeaNotesRequest(BaseModel):
    notes: str


class IdeaContactRequest(BaseModel):
    contact_name: str = ""
    title_role: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""


# ── Pipeline endpoints ──

_pipeline_results: dict = {}


def _run_pipeline_task(batch_size: int = 40):
    global _pipeline_running, _pipeline_results
    _pipeline_running = True
    try:
        from outreach_engine.daily_run import run_daily_pipeline_headless
        _pipeline_results = run_daily_pipeline_headless(batch_size=batch_size)
    except Exception:
        logger.exception("Pipeline failed")
        _pipeline_results = {"error": "Pipeline failed — check logs"}
    finally:
        _pipeline_running = False


@app.post("/api/pipeline/run", status_code=202)
def trigger_pipeline(background_tasks: BackgroundTasks, batch_size: int = 40):
    if _pipeline_running:
        raise HTTPException(status_code=409, detail="Pipeline already running")
    background_tasks.add_task(_run_pipeline_task, batch_size)
    return {"status": "started", "batch_size": batch_size}


@app.get("/api/pipeline/status")
def pipeline_status():
    return {"running": _pipeline_running, "results": _pipeline_results if not _pipeline_running else {}}


# ── Queue endpoints ──

@app.get("/api/queue")
def get_queue(date: Optional[str] = None):
    if date == "latest":
        bundles = queue_manager.get_queue(None)
        dates = {b["batch_date"] for b in bundles if b.get("batch_date")}
        latest = max(dates) if dates else None
        if latest:
            bundles = [b for b in bundles if b["batch_date"] == latest]
        return {"bundles": bundles, "batch_date": latest}
    return {"bundles": queue_manager.get_queue(date)}


@app.get("/api/queue/{bundle_id}")
def get_bundle(bundle_id: int):
    bundle = queue_manager.get_bundle(bundle_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    return bundle


@app.post("/api/queue/{bundle_id}/approve")
def approve_bundle(bundle_id: int):
    queue_manager.approve_bundle(bundle_id)
    return {"status": "approved"}


@app.post("/api/queue/{bundle_id}/edit")
def edit_bundle(bundle_id: int, req: EditRequest):
    queue_manager.edit_bundle(
        bundle_id,
        email_subject=req.email_subject,
        email_body=req.email_body,
        notes=req.notes,
    )
    return {"status": "updated"}


@app.post("/api/queue/{bundle_id}/skip")
def skip_bundle(bundle_id: int):
    queue_manager.skip_bundle(bundle_id)
    return {"status": "skipped"}


@app.post("/api/queue/{bundle_id}/snooze")
def snooze_bundle(bundle_id: int, req: SnoozeRequest):
    queue_manager.snooze_bundle(bundle_id, req.until)
    return {"status": "snoozed"}


def _send_single_bundle(bundle_id: int) -> dict:
    """Send email for a single bundle."""
    # Check daily send cap
    can_send, sent_today, max_sends = queue_manager.check_daily_send_cap()
    if not can_send:
        return {"bundle_id": bundle_id, "status": "error",
                "error": f"Daily send cap reached ({sent_today}/{max_sends})"}

    bundle = queue_manager.get_bundle(bundle_id)
    if not bundle:
        return {"bundle_id": bundle_id, "status": "error", "error": "Bundle not found"}

    # Auto-approve if queued
    if bundle["status"] == "queued":
        queue_manager.approve_bundle(bundle_id)
    elif bundle["status"] not in ("approved",):
        return {"bundle_id": bundle_id, "status": "error",
                "error": f"Status is '{bundle['status']}', must be 'queued' or 'approved'"}

    email_status = bundle.get("email_status", "unknown")
    if email_status == "invalid":
        return {"bundle_id": bundle_id, "status": "email_invalid",
                "error": "Email status is invalid"}

    # Pre-send enrichment: re-validate unknown emails before sending
    if email_status == "unknown" and bundle.get("discovered_email"):
        try:
            new_email, new_status = discover_email(bundle["contact_id"])
            if new_status == "invalid":
                return {"bundle_id": bundle_id, "status": "email_invalid",
                        "error": "Pre-send validation failed: email is invalid"}
            logger.info("Pre-send enrichment for bundle %d: %s → %s",
                        bundle_id, email_status, new_status)
        except Exception as e:
            logger.warning("Pre-send enrichment failed for bundle %d: %s", bundle_id, e)

    email_addr = bundle.get("discovered_email", "")
    if not email_addr or not bundle.get("email_body"):
        return {"bundle_id": bundle_id, "status": "error", "error": "No email or body"}

    tracking_id = str(uuid.uuid4())
    queue_manager.create_tracking(bundle_id, tracking_id)

    result = send_email(
        email_addr, bundle["email_subject"], bundle["email_body"],
        tracking_id=tracking_id,
    )

    email_sent = result.get("success", False)

    # Log the send attempt
    queue_manager.log_send(
        bundle_id, email_addr,
        smtp_code=result.get("smtp_code", 0),
        error=result.get("error", ""),
    )

    if email_sent:
        queue_manager.mark_sent(bundle_id, email_sent=True)
        # Hook: account status transition on send
        try:
            from outreach_engine.account_manager import on_email_sent
            on_email_sent(bundle.get("contact_id", 0), bundle_id)
        except Exception:
            pass

    return {
        "bundle_id": bundle_id,
        "status": "sent" if email_sent else "send_failed",
        "result": result,
    }


@app.post("/api/queue/{bundle_id}/send")
def send_bundle(bundle_id: int):
    result = _send_single_bundle(bundle_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


def _batch_send_task(bundle_ids: list[int]):
    """Background task: send emails with short stagger."""
    import time
    global _batch_sending, _batch_progress
    _batch_sending = True
    _batch_progress = {"sent": 0, "failed": 0, "total": len(bundle_ids), "done": False}
    for bid in bundle_ids:
        result = _send_single_bundle(bid)
        if result.get("status") == "sent":
            _batch_progress["sent"] += 1
        else:
            _batch_progress["failed"] += 1
        # 3-8 second stagger — fast enough to not waste time,
        # slow enough that SiteGround doesn't throttle us
        time.sleep(random.randint(3, 8))
    _batch_progress["done"] = True
    _batch_sending = False


@app.post("/api/queue/send-batch")
def send_batch(req: BatchSendRequest, background_tasks: BackgroundTasks):
    """Kick off batch send in background — poll /api/queue/send-batch/progress."""
    global _batch_sending, _batch_progress
    if _batch_sending:
        raise HTTPException(status_code=409, detail="Batch send already in progress")
    _batch_progress = {"sent": 0, "failed": 0, "total": len(req.bundle_ids), "done": False}
    background_tasks.add_task(_batch_send_task, req.bundle_ids)
    return {"status": "started", "total": len(req.bundle_ids)}


@app.get("/api/queue/send-batch/progress")
def send_batch_progress():
    """Poll this to see how the batch send is going."""
    return _batch_progress


@app.post("/api/queue/{bundle_id}/bounced")
def handle_bounced(bundle_id: int, background_tasks: BackgroundTasks):
    """Mark as bounced → record bad email → trigger deep rediscovery in background."""
    bundle = queue_manager.get_bundle(bundle_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    result = queue_manager.mark_bounced(bundle_id)
    contact_id = result.get("contact_id")
    if contact_id:
        background_tasks.add_task(_bounce_recovery_task, contact_id)
    return {
        "bundle_id": bundle_id,
        "status": "bounced",
        "contact_id": contact_id,
        "bounced_email": result.get("bounced_email", ""),
        "recovery": "started" if contact_id else "skipped",
    }


def _bounce_recovery_task(contact_id: int):
    """Background: deep rediscovery + team scrape + auto-queue new contacts."""
    from datetime import date
    from outreach_engine.template_engine import generate_email
    import sqlite3

    logger.info("Bounce recovery starting for contact #%d", contact_id)

    # Step 1: Try rediscovery on the original contact
    new_email, status = rediscover_email(contact_id)
    if new_email and status in ("verified", "likely"):
        subject, body = generate_email(contact_id)
        if subject and body:
            queue_manager.create_bundle(
                contact_id, date.today().isoformat(), subject, body,
            )
            logger.info("Bounce recovery: re-queued contact #%d with %s (%s)",
                        contact_id, new_email, status)
        return

    # Step 2: Deep team scrape — find individual people on the website
    conn = sqlite3.connect(str(cfg.db_path))
    conn.row_factory = sqlite3.Row
    contact = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not contact:
        conn.close()
        return

    website = contact["website"]
    domain = contact["domain"]
    city = contact["city"] or "windsor"
    company = contact["company_name"]
    tier = contact["tier"]
    industry_code = contact["industry_code"]
    bounced_set = set(
        e.strip() for e in (contact["bounced_emails"] or "").split(",") if e.strip()
    )

    if not website or not domain:
        conn.close()
        logger.info("Bounce recovery: no website for contact #%d — cannot team scrape", contact_id)
        return

    logger.info("Bounce recovery: team scraping %s for contact #%d", website, contact_id)
    team_results = discover_team_emails(website, domain, city, exclude_emails=bounced_set)

    if not team_results:
        logger.info("Bounce recovery: no team members found for %s", company)
        conn.close()
        return

    created = 0
    for person in team_results:
        # Check if this person already exists as a contact
        existing = conn.execute(
            "SELECT id FROM contacts WHERE company_name = ? AND contact_name = ?",
            (company, person["name"]),
        ).fetchone()
        if existing:
            continue

        # Create new contact for this team member
        conn.execute("""
            INSERT INTO contacts
            (company_name, website, domain, city, contact_name, title_role,
             tier, industry_code, priority_score, discovered_email, email_status,
             outreach_status, notes, csv_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, 'team_scrape')
        """, (
            company, website, domain, city,
            person["name"], person.get("title", ""),
            tier, industry_code, contact["priority_score"],
            person["email"], person["email_status"],
            f"Discovered via team scrape from bounced contact #{contact_id}",
        ))
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Generate and queue email for this person
        conn.commit()  # commit so generate_email can read the contact
        subject, body = generate_email(new_id)
        if subject and body:
            queue_manager.create_bundle(new_id, date.today().isoformat(), subject, body)
            created += 1

    conn.commit()
    conn.close()
    logger.info("Bounce recovery: created %d new contacts from team scrape of %s",
                created, company)


@app.post("/api/queue/{bundle_id}/replied")
def mark_replied(bundle_id: int):
    queue_manager.mark_replied(bundle_id)
    return {"status": "replied"}


@app.post("/api/replies/scan")
def scan_replies():
    """Scan IMAP inbox for replies and classify them."""
    from outreach_engine.email_sender import process_replies
    try:
        stats = process_replies(days=7)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reply scan failed: {e}")


# ── Deep research endpoint ──

class DeepResearchRequest(BaseModel):
    contact_ids: list[int] = []

_deep_research_progress: dict = {"running": False, "contact_id": 0, "found": 0, "done": False}


@app.post("/api/discovery/deep-research/{contact_id}")
def deep_research_single(contact_id: int, background_tasks: BackgroundTasks):
    """Trigger deep team research for a single contact (e.g. after bounce)."""
    global _deep_research_progress
    if _deep_research_progress.get("running"):
        raise HTTPException(status_code=409, detail="Deep research already running")
    _deep_research_progress = {"running": True, "contact_id": contact_id, "found": 0, "done": False}
    background_tasks.add_task(_deep_research_task, contact_id)
    return {"status": "started", "contact_id": contact_id}


@app.get("/api/discovery/deep-research/progress")
def deep_research_progress():
    return _deep_research_progress


def _deep_research_task(contact_id: int):
    """Background: full deep research — rediscovery + team scrape + auto-queue."""
    global _deep_research_progress
    try:
        _bounce_recovery_task(contact_id)
        # Count how many new bundles were created for this company
        import sqlite3
        conn = sqlite3.connect(str(cfg.db_path))
        conn.row_factory = sqlite3.Row
        contact = conn.execute("SELECT company_name FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if contact:
            new_count = conn.execute("""
                SELECT COUNT(*) FROM contacts
                WHERE company_name = ? AND csv_source = 'team_scrape'
            """, (contact["company_name"],)).fetchone()[0]
            _deep_research_progress["found"] = new_count
        conn.close()
    except Exception:
        logger.exception("Deep research failed for contact #%d", contact_id)
    finally:
        _deep_research_progress["done"] = True
        _deep_research_progress["running"] = False


# ── Discovery endpoints ──

@app.post("/api/discovery/run")
def run_discovery(req: DiscoverRequest, background_tasks: BackgroundTasks):
    """Run email discovery for specific contacts or a batch."""
    if req.contact_ids:
        results = []
        for cid in req.contact_ids:
            email, status = discover_email(cid)
            results.append({"contact_id": cid, "email": email, "status": status})
        return {"results": results}
    else:
        results = discover_batch(req.limit)
        return {"results": results}


@app.get("/api/discovery/stats")
def discovery_stats():
    return queue_manager.get_discovery_stats()


@app.get("/api/contacts")
def browse_contacts(tier: Optional[str] = None, email_status: Optional[str] = None,
                    limit: int = 50, offset: int = 0):
    contacts = queue_manager.get_contacts(tier, email_status, limit, offset)
    return {"contacts": contacts}


# ── Up-next endpoint ──

@app.get("/api/up-next")
def get_up_next(limit: int = 20):
    contacts = queue_manager.get_up_next(limit)
    total = queue_manager.get_up_next_total()
    return {"contacts": contacts, "total": total}


# ── Tracking pixel ──

@app.get("/api/track/{tracking_id}")
def track_open(tracking_id: str, request: Request, background_tasks: BackgroundTasks):
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    result = queue_manager.record_email_open(tracking_id, ip_address=ip, user_agent=ua)
    # Trigger flywheel + account status on first open
    if result and result.get("first_open"):
        from outreach_engine.flywheel import on_email_opened
        background_tasks.add_task(on_email_opened, result["bundle_id"])
        # Hook: account status transition on open
        try:
            from outreach_engine.account_manager import on_email_opened as _acct_opened
            bid = result["bundle_id"]
            b = queue_manager.get_bundle(bid)
            if b:
                background_tasks.add_task(_acct_opened, b["contact_id"], bid)
        except Exception:
            pass
    return Response(
        content=TRACKING_PIXEL,
        media_type="image/gif",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


# ── History + Stats ──

@app.get("/api/history")
def get_history(limit: int = 100, offset: int = 0):
    return {"history": queue_manager.get_history(limit, offset)}


@app.get("/api/stats")
def get_stats():
    return queue_manager.get_stats()


# ── Donor Scraping ──

_donor_scrape_progress: dict = {"running": False, "done": False, "results": {}}


class DonorSourceRequest(BaseModel):
    name: str
    url: str
    source_type: str = "custom"


@app.post("/api/donors/scrape", status_code=202)
def trigger_donor_scrape(background_tasks: BackgroundTasks, dry_run: bool = False):
    """Trigger full donor scrape pipeline."""
    global _donor_scrape_progress
    if _donor_scrape_progress.get("running"):
        raise HTTPException(status_code=409, detail="Donor scrape already running")
    _donor_scrape_progress = {"running": True, "done": False, "results": {}}
    background_tasks.add_task(_donor_scrape_task, dry_run)
    return {"status": "started"}


def _donor_scrape_task(dry_run: bool = False):
    global _donor_scrape_progress
    try:
        from outreach_engine.donor_scraper import import_donors
        _donor_scrape_progress["results"] = import_donors(dry_run=dry_run)
    except Exception:
        logger.exception("Donor scrape failed")
        _donor_scrape_progress["results"] = {"error": "Donor scrape failed"}
    finally:
        _donor_scrape_progress["done"] = True
        _donor_scrape_progress["running"] = False


@app.get("/api/donors/scrape/status")
def donor_scrape_status():
    return _donor_scrape_progress


@app.post("/api/donors/add-source")
def add_donor_source(req: DonorSourceRequest):
    from outreach_engine.donor_scraper import add_donor_source as _add
    _add(req.name, req.url, req.source_type)
    return {"status": "added", "name": req.name, "url": req.url}


# ── News Signal Scanner ──

_news_scan_progress: dict = {"running": False, "done": False, "results": {}}


@app.post("/api/news/scan", status_code=202)
def trigger_news_scan(background_tasks: BackgroundTasks, dry_run: bool = False):
    """Trigger a news signal scan."""
    global _news_scan_progress
    if _news_scan_progress.get("running"):
        raise HTTPException(status_code=409, detail="News scan already running")
    _news_scan_progress = {"running": True, "done": False, "results": {}}
    background_tasks.add_task(_news_scan_task, not dry_run)
    return {"status": "started", "auto_create_contacts": not dry_run}


def _news_scan_task(auto_create: bool = True):
    global _news_scan_progress
    try:
        from outreach_engine.news_scanner import scan_all_sources
        _news_scan_progress["results"] = scan_all_sources(
            auto_create_contacts=auto_create,
        )
    except Exception:
        logger.exception("News scan failed")
        _news_scan_progress["results"] = {"error": "News scan failed"}
    finally:
        _news_scan_progress["done"] = True
        _news_scan_progress["running"] = False


@app.get("/api/news/scan/status")
def news_scan_status():
    return _news_scan_progress


@app.get("/api/news/signals")
def list_news_signals(status: Optional[str] = None, signal_type: Optional[str] = None,
                      limit: int = 50, offset: int = 0):
    """List news signals with optional filters."""
    signals = queue_manager.get_news_signals(status, signal_type, limit, offset)
    return {"signals": signals, "count": len(signals)}


@app.get("/api/news/signals/{signal_id}")
def get_news_signal(signal_id: int):
    """Get a single news signal."""
    signal = queue_manager.get_news_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal


@app.post("/api/news/signals/{signal_id}/create-contact")
def create_contact_from_signal(signal_id: int):
    """Create a contact from a news signal and kick off discovery."""
    from outreach_engine.news_scanner import create_contact_from_signal as _create
    contact_id = _create(signal_id)
    if not contact_id:
        raise HTTPException(status_code=400,
                            detail="Could not create contact (no company name or already exists)")

    # Trigger email discovery for the new contact
    email_found = ""
    try:
        email_found, _ = discover_email(contact_id)
    except Exception as e:
        logger.warning("Discovery failed for news signal contact #%d: %s", contact_id, e)

    return {
        "contact_id": contact_id,
        "signal_id": signal_id,
        "email_found": email_found,
        "status": "created",
    }


@app.post("/api/news/signals/{signal_id}/dismiss")
def dismiss_signal(signal_id: int):
    """Dismiss a news signal."""
    queue_manager.update_news_signal_status(signal_id, "dismissed")
    return {"status": "dismissed", "signal_id": signal_id}


@app.get("/api/news/stats")
def news_signal_stats():
    """Get news signal statistics."""
    from outreach_engine.news_scanner import get_signal_stats
    return get_signal_stats()


# ── Corporate Relocation ──

class RelocationRequest(BaseModel):
    company_name: str
    origin_city: str = "Windsor"
    destination_city: str = ""
    contact_name: str = ""
    title_role: str = ""
    website: str = ""
    notes: str = ""


@app.post("/api/relocation/create")
def create_relocation(req: RelocationRequest, background_tasks: BackgroundTasks):
    """Create a corporate relocation contact, discover email, generate bundle."""
    from outreach_engine.template_engine import generate_email

    # Create the contact
    contact_id = queue_manager.create_relocation_contact(
        company_name=req.company_name,
        origin_city=req.origin_city,
        destination_city=req.destination_city,
        contact_name=req.contact_name,
        title_role=req.title_role,
        website=req.website,
        notes=req.notes,
    )

    # Discover email
    email_found = ""
    email_status = "pending"
    try:
        email_found, email_status = discover_email(contact_id)
    except Exception as e:
        logger.warning("Relocation email discovery failed for %s: %s", req.company_name, e)

    # Generate bundle
    bundle_id = None
    try:
        subject, body = generate_email(contact_id)
        if subject and body:
            from datetime import date
            bundle_id = queue_manager.create_bundle(
                contact_id, date.today().isoformat(), subject, body,
            )
    except Exception as e:
        logger.warning("Relocation bundle generation failed: %s", e)

    return {
        "contact_id": contact_id,
        "bundle_id": bundle_id,
        "email_found": email_found,
        "email_status": email_status,
        "status": "queued" if bundle_id else "contact_created",
        "note": "Bundle requires manual approval before sending",
    }


@app.get("/api/relocation/list")
def list_relocations():
    """List all corporate relocation contacts and their bundle status."""
    import sqlite3
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT c.*, b.id as bundle_id, b.status as bundle_status,
               b.email_subject, b.sent_at
        FROM contacts c
        LEFT JOIN outreach_bundles b ON b.contact_id = c.id
        WHERE c.industry_code = 'CR25'
        ORDER BY c.created_at DESC
    """).fetchall()
    conn.close()
    return {"relocations": [dict(r) for r in rows]}


# ── Account Board ──

@app.get("/api/accounts/board")
def get_account_board(status: Optional[str] = None, limit: int = 100,
                      offset: int = 0):
    """Get account board — contacts grouped by account status."""
    accounts = queue_manager.get_account_board(status, limit, offset)
    return {"accounts": accounts, "count": len(accounts)}


@app.get("/api/accounts/board/stats")
def get_account_board_stats():
    """Get account board summary statistics."""
    return queue_manager.get_account_board_stats()


@app.get("/api/accounts/{contact_id}")
def get_account_detail(contact_id: int):
    """Get full account detail including touches, bundles, jobs."""
    detail = queue_manager.get_account_detail(contact_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Contact not found")
    return detail


@app.post("/api/accounts/{contact_id}/status")
def update_account_status(contact_id: int, req: AccountStatusRequest):
    """Update account status with transition validation."""
    from outreach_engine.account_manager import transition_account_status
    result = transition_account_status(contact_id, req.status, notes=req.notes)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Transition failed"))
    return result


@app.post("/api/accounts/{contact_id}/dnc")
def mark_account_dnc(contact_id: int, req: AccountStatusRequest):
    """Mark account as DNC (permanent)."""
    from outreach_engine.account_manager import mark_dnc
    result = mark_dnc(contact_id, reason=req.notes)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "DNC failed"))
    return result


@app.post("/api/accounts/{contact_id}/confidence/recalculate")
def recalculate_confidence(contact_id: int):
    """Recalculate confidence score for a single contact."""
    from outreach_engine.account_manager import compute_confidence_score
    score = compute_confidence_score(contact_id)
    return {"contact_id": contact_id, "confidence_score": score}


# ── Touch Log ──

@app.post("/api/touches/log")
def log_touch(req: TouchLogRequest):
    """Log a multi-channel touch (email, phone, in_person, etc)."""
    tid = queue_manager.log_touch(
        contact_id=req.contact_id, channel=req.channel,
        direction=req.direction, subject=req.subject,
        notes=req.notes, outcome=req.outcome,
    )
    return {"id": tid, "status": "logged"}


@app.get("/api/touches/stats")
def get_touch_stats():
    """Get touch statistics across all contacts."""
    return queue_manager.get_touch_stats()


@app.get("/api/touches/{contact_id}")
def get_touches(contact_id: int, limit: int = 50):
    """Get touch log for a contact."""
    touches = queue_manager.get_touches(contact_id, limit)
    return {"touches": touches, "count": len(touches)}


# ── Ecosystem Contacts ──

@app.post("/api/ecosystem/create")
def create_ecosystem_contact(req: EcosystemCreateRequest):
    """Create an ecosystem contact (realtor, lawyer, broker, etc)."""
    eid = queue_manager.create_ecosystem_contact(
        name=req.name, role=req.role, email=req.email,
        phone=req.phone, company=req.company,
        source_contact_id=req.source_contact_id, notes=req.notes,
    )
    return {"id": eid, "status": "created"}


@app.get("/api/ecosystem/list")
def list_ecosystem_contacts(role: Optional[str] = None,
                            limit: int = 50, offset: int = 0):
    """List ecosystem contacts with optional role filter."""
    contacts = queue_manager.get_ecosystem_contacts(role, limit, offset)
    return {"contacts": contacts, "count": len(contacts)}


@app.post("/api/ecosystem/{ecosystem_id}/promote")
def promote_ecosystem(ecosystem_id: int):
    """Promote ecosystem contact to full CRM contact."""
    new_id = queue_manager.promote_ecosystem_contact(ecosystem_id)
    if not new_id:
        raise HTTPException(status_code=404, detail="Ecosystem contact not found")
    return {"ecosystem_id": ecosystem_id, "new_contact_id": new_id, "status": "promoted"}


# ── Partner Codes ──

@app.post("/api/partners/create")
def create_partner(req: PartnerCreateRequest):
    """Create a partner code."""
    pid = queue_manager.create_partner_code(
        partner_name=req.partner_name, code=req.code,
        discount_percent=req.discount_percent,
        bonus_per_referral=req.bonus_per_referral,
    )
    return {"id": pid, "code": req.code.upper(), "status": "created"}


@app.get("/api/partners/list")
def list_partners(status: str = "active", limit: int = 50):
    """List partner codes."""
    partners = queue_manager.get_partner_codes(status, limit)
    return {"partners": partners, "count": len(partners)}


@app.get("/api/partners/lookup/{code}")
def lookup_partner(code: str):
    """Look up a partner code."""
    partner = queue_manager.lookup_partner_code(code)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner code not found")
    return partner


# ── Jobs ──

@app.post("/api/jobs/create")
def create_job(req: JobCreateRequest):
    """Create a job (quote → book → complete pipeline)."""
    jid = queue_manager.create_job(
        contact_id=req.contact_id, partner_code=req.partner_code,
        job_type=req.job_type, quote_amount=req.quote_amount,
        move_date=req.move_date, origin_address=req.origin_address,
        destination_address=req.destination_address,
        crew_size=req.crew_size, truck_count=req.truck_count,
        notes=req.notes,
    )
    return {"id": jid, "status": "quoted"}


@app.get("/api/jobs/list")
def list_jobs(status: Optional[str] = None, limit: int = 50, offset: int = 0):
    """List jobs with optional status filter."""
    jobs = queue_manager.get_jobs(status, limit, offset)
    return {"jobs": jobs, "count": len(jobs)}


@app.get("/api/jobs/stats")
def get_job_stats():
    """Get job pipeline statistics."""
    return queue_manager.get_job_stats()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int):
    """Get a single job with contact info."""
    job = queue_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/jobs/{job_id}/update")
def update_job(job_id: int, req: JobUpdateRequest):
    """Update a job (status, amounts, crew, etc)."""
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    if not kwargs:
        raise HTTPException(status_code=400, detail="No fields to update")
    success = queue_manager.update_job(job_id, **kwargs)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "status": "updated", "fields": list(kwargs.keys())}


# ── Field Intel ──

@app.post("/api/ideas/submit")
def submit_idea(req: IdeaSubmitRequest, background_tasks: BackgroundTasks):
    """Submit a field intel idea. Optionally auto-triggers GPT research."""
    idea_id = queue_manager.submit_idea(
        company_name=req.company_name, user_notes=req.user_notes,
        city=req.city, industry=req.industry, priority=req.priority,
    )
    result = {"id": idea_id, "status": "submitted", "company": req.company_name}

    if req.auto_research:
        from outreach_engine.research_engine import research_company
        background_tasks.add_task(research_company, idea_id)
        result["research"] = "started"

    return result


@app.get("/api/ideas/list")
def list_ideas(status: Optional[str] = None, limit: int = 50, offset: int = 0):
    """List field intel ideas."""
    ideas = queue_manager.get_ideas(status, limit, offset)
    return {"ideas": ideas, "count": len(ideas)}


@app.get("/api/ideas/{idea_id}")
def get_idea(idea_id: int):
    """Get full detail for a field intel idea including research + stages."""
    idea = queue_manager.get_idea(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    return idea


@app.post("/api/ideas/{idea_id}/research")
def trigger_research(idea_id: int, background_tasks: BackgroundTasks):
    """Trigger or re-trigger GPT research for an idea."""
    idea = queue_manager.get_idea(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    from outreach_engine.research_engine import research_company
    background_tasks.add_task(research_company, idea_id)
    return {"id": idea_id, "status": "research_started"}


@app.post("/api/ideas/{idea_id}/add-notes")
def add_idea_notes(idea_id: int, req: IdeaNotesRequest):
    """Add additional field intel notes to an idea."""
    success = queue_manager.update_idea_notes(idea_id, req.notes)
    if not success:
        raise HTTPException(status_code=404, detail="Idea not found")
    return {"id": idea_id, "status": "notes_added"}


@app.post("/api/ideas/{idea_id}/approve-stage")
def approve_stage(idea_id: int, req: IdeaNotesRequest):
    """Approve/advance the current stage of a field intel idea."""
    from outreach_engine.research_engine import advance_stage
    result = advance_stage(idea_id, notes=req.notes)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    return result


@app.post("/api/ideas/{idea_id}/generate-outreach")
def generate_idea_outreach(idea_id: int):
    """Generate custom outreach email for the current stage."""
    from outreach_engine.research_engine import generate_stage_outreach
    result = generate_stage_outreach(idea_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/ideas/{idea_id}/create-contact")
def create_contact_from_idea(idea_id: int, req: IdeaContactRequest):
    """Create a CRM contact from a researched idea."""
    from outreach_engine.research_engine import create_contact_from_research
    contact_id = create_contact_from_research(
        idea_id, contact_name=req.contact_name, title_role=req.title_role,
        email=req.email, phone=req.phone, website=req.website,
    )
    if not contact_id:
        raise HTTPException(status_code=400, detail="Could not create contact")
    return {"idea_id": idea_id, "contact_id": contact_id, "status": "contact_created"}


# ── Telegram Bot Webhook ──

@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request):
    """Receive webhook updates from Telegram Bot API."""
    # Verify secret token if configured
    if cfg.telegram_webhook_secret:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_secret != cfg.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid secret token")

    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    from outreach_engine.telegram_bot import handle_update
    result = await handle_update(update)
    return result


@app.post("/api/telegram/setup-webhook")
async def setup_telegram_webhook():
    """Register webhook URL with Telegram (call once after deploy)."""
    if not cfg.telegram_bot_token:
        raise HTTPException(status_code=400, detail="TELEGRAM_BOT_TOKEN not configured")

    webhook_url = f"{cfg.sidecar_public_url}/api/telegram/webhook"
    from outreach_engine.telegram_bot import setup_webhook
    result = await setup_webhook(webhook_url)
    return {"webhook_url": webhook_url, "telegram_response": result}


# ── Flywheel ──

@app.post("/api/flywheel/run")
def run_flywheel(limit: int = 20):
    """Run flywheel batch for recent opens/replies."""
    from outreach_engine.flywheel import run_flywheel_batch
    try:
        return run_flywheel_batch(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Flywheel failed: {e}")


@app.get("/api/flywheel/stats")
def flywheel_stats():
    from outreach_engine.flywheel import get_flywheel_stats
    return get_flywheel_stats()


@app.post("/api/flywheel/similar/{contact_id}")
def find_similar(contact_id: int, limit: int = 10):
    """Find similar companies for a specific contact."""
    from outreach_engine.flywheel import find_similar_companies
    suggestions = find_similar_companies(contact_id, limit=limit)
    return {"suggestions": suggestions, "count": len(suggestions)}


# ── One-Pager Generator ──

@app.post("/api/onepager/generate/{contact_id}")
def generate_onepager(contact_id: int):
    """Generate a customized partnership one-pager for a contact."""
    from outreach_engine.onepager_generator import generate_onepager as _gen
    result = _gen(contact_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/onepager/list")
def list_onepagers():
    """List all generated one-pagers."""
    from outreach_engine.onepager_generator import list_onepagers as _list
    return {"onepagers": _list()}


@app.get("/api/onepager/view/{filename}")
def view_onepager(filename: str):
    """Serve a generated one-pager HTML file."""
    from outreach_engine.onepager_generator import OUTPUT_DIR
    filepath = OUTPUT_DIR / filename
    if not filepath.exists() or not filepath.name.startswith("OnePager_"):
        raise HTTPException(status_code=404, detail="File not found")
    return Response(
        content=filepath.read_text(encoding="utf-8"),
        media_type="text/html",
    )


@app.get("/api/onepager/download/{filename}")
def download_onepager(filename: str):
    """Download a generated one-pager PDF."""
    from outreach_engine.onepager_generator import OUTPUT_DIR
    filepath = OUTPUT_DIR / filename
    if not filepath.exists() or not filepath.name.startswith("OnePager_"):
        raise HTTPException(status_code=404, detail="File not found")
    media = "application/pdf" if filename.endswith(".pdf") else "text/html"
    return Response(
        content=filepath.read_bytes(),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── IMAP Bounce Scanner ──

def _scan_imap_bounces() -> list[str]:
    """Delegate to email_sender's shared bounce scanner."""
    from outreach_engine.email_sender import scan_imap_bounces
    return scan_imap_bounces(days=3)


@app.post("/api/bounces/scan")
def scan_bounces():
    """Scan IMAP inbox for bounced emails and mark matching bundles."""
    import sqlite3

    try:
        bounced_emails = _scan_imap_bounces()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"IMAP scan failed: {e}")

    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    marked = []
    already = []
    no_match = []

    for email in bounced_emails:
        # Find sent bundle with this email
        row = conn.execute("""
            SELECT b.id as bundle_id, b.status, c.company_name
            FROM outreach_bundles b
            JOIN contacts c ON b.contact_id = c.id
            WHERE c.discovered_email = ? AND b.status = 'sent'
            LIMIT 1
        """, (email,)).fetchone()

        if row:
            marked.append({"email": email, "bundle_id": row["bundle_id"],
                           "company": row["company_name"]})
        else:
            # Check if already bounced
            row2 = conn.execute("""
                SELECT b.id, b.status FROM outreach_bundles b
                JOIN contacts c ON b.contact_id = c.id
                WHERE c.discovered_email = ?
                LIMIT 1
            """, (email,)).fetchone()
            if row2 and row2["status"] == "bounced":
                already.append(email)
            else:
                no_match.append(email)

    conn.close()

    # Mark the bundles as bounced via the existing API logic
    for item in marked:
        try:
            queue_manager.mark_bounced(item["bundle_id"])
        except Exception:
            pass

    return {
        "scanned": len(bounced_emails),
        "newly_marked": len(marked),
        "already_bounced": len(already),
        "no_match": len(no_match),
        "marked_details": marked,
    }


# ── SMTP test ──

@app.get("/api/smtp/test")
def smtp_test():
    import smtplib
    import ssl
    if not cfg.smtp_user or not cfg.smtp_password:
        return {"success": False, "error": "SMTP not configured"}
    try:
        if cfg.smtp_use_ssl:
            context = ssl.create_default_context()
            try:
                with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=context, timeout=10) as server:
                    server.login(cfg.smtp_user, cfg.smtp_password)
            except ssl.SSLCertVerificationError:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=ctx, timeout=10) as server:
                    server.login(cfg.smtp_user, cfg.smtp_password)
        else:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(cfg.smtp_user, cfg.smtp_password)
        return {"success": True, "email": cfg.smtp_from_email}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Health Check ──

@app.get("/api/health")
def health_check():
    """Comprehensive health check — DB, SMTP, OpenAI, disk, last pipeline run."""
    import sqlite3
    import shutil

    health = {
        "status": "healthy",
        "checks": {},
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }

    # 1. Database check
    try:
        conn = sqlite3.connect(str(cfg.db_path), timeout=5)
        count = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        conn.close()
        health["checks"]["database"] = {"ok": True, "contacts": count}
    except Exception as e:
        health["checks"]["database"] = {"ok": False, "error": str(e)}
        health["status"] = "degraded"

    # 2. SMTP check
    try:
        import smtplib
        import ssl
        if cfg.smtp_user and cfg.smtp_password:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=ctx, timeout=5) as s:
                s.login(cfg.smtp_user, cfg.smtp_password)
            health["checks"]["smtp"] = {"ok": True, "host": cfg.smtp_host}
        else:
            health["checks"]["smtp"] = {"ok": False, "error": "Not configured"}
            health["status"] = "degraded"
    except Exception as e:
        health["checks"]["smtp"] = {"ok": False, "error": str(e)}
        health["status"] = "degraded"

    # 3. OpenAI check
    try:
        if cfg.openai_api_key:
            from openai import OpenAI
            client = OpenAI(api_key=cfg.openai_api_key)
            client.models.list()
            health["checks"]["openai"] = {"ok": True}
        else:
            health["checks"]["openai"] = {"ok": False, "error": "No API key"}
            health["status"] = "degraded"
    except Exception as e:
        health["checks"]["openai"] = {"ok": False, "error": str(e)}
        health["status"] = "degraded"

    # 4. Disk space
    try:
        usage = shutil.disk_usage(str(cfg.project_root))
        free_gb = usage.free / (1024 ** 3)
        health["checks"]["disk"] = {
            "ok": free_gb > 1.0,
            "free_gb": round(free_gb, 2),
        }
        if free_gb < 1.0:
            health["status"] = "degraded"
    except Exception as e:
        health["checks"]["disk"] = {"ok": False, "error": str(e)}

    # 5. Last pipeline run
    try:
        last_run = queue_manager.get_last_pipeline_run()
        if last_run:
            health["checks"]["last_pipeline"] = {
                "ok": last_run["status"] == "completed",
                "status": last_run["status"],
                "started_at": last_run["started_at"],
                "ended_at": last_run.get("ended_at", ""),
            }
            if last_run["status"] == "failed":
                health["status"] = "degraded"
        else:
            health["checks"]["last_pipeline"] = {"ok": True, "note": "No runs yet"}
    except Exception:
        health["checks"]["last_pipeline"] = {"ok": True, "note": "No runs table yet"}

    # 6. Daily send cap
    try:
        can_send, sent_today, max_sends = queue_manager.check_daily_send_cap()
        health["checks"]["send_cap"] = {
            "ok": can_send,
            "sent_today": sent_today,
            "max_daily": max_sends,
            "remaining": max_sends - sent_today,
        }
    except Exception:
        health["checks"]["send_cap"] = {"ok": True, "note": "Could not check"}

    # 7. Scheduler status
    health["checks"]["scheduler"] = {
        "ok": _scheduler_running,
        "running": _scheduler_running,
    }

    return health


# ── Pipeline Run History ──

@app.get("/api/pipeline/runs")
def get_pipeline_runs(limit: int = 20):
    """Get recent pipeline run history."""
    runs = queue_manager.get_pipeline_runs(limit)
    return {"runs": runs}


# ── Follow-Up Engine ──

@app.post("/api/followups/run")
def run_followups(background_tasks: BackgroundTasks, limit: int = 20):
    """Trigger follow-up cycle (schedule + send)."""
    from outreach_engine.followup_engine import run_followup_cycle
    try:
        return run_followup_cycle(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Follow-up cycle failed: {e}")


@app.get("/api/followups/stats")
def followup_stats():
    return queue_manager.get_followup_stats()


@app.get("/api/followups/pending")
def pending_followups():
    pending = queue_manager.get_pending_followups()
    return {"pending": pending, "count": len(pending)}


# ── DB Backup ──

@app.post("/api/backup/create")
def create_backup():
    """Create a database backup."""
    try:
        path = queue_manager.backup_database()
        return {"status": "created", "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {e}")


@app.get("/api/backup/list")
def list_backups():
    return {"backups": queue_manager.list_backups()}


# ── Rate Limiting Stats ──

@app.get("/api/discovery/rate-limits")
def discovery_rate_limits():
    return queue_manager.get_discovery_rate_stats()


# ── Send Cap ──

@app.get("/api/send-cap")
def send_cap_status():
    can_send, sent_today, max_sends = queue_manager.check_daily_send_cap()
    return {
        "can_send": can_send,
        "sent_today": sent_today,
        "max_daily": max_sends,
        "remaining": queue_manager.remaining_send_budget(),
    }


# ── APScheduler — Autonomous Operation ──

_scheduler_running = False
_scheduler = None


def _scheduled_pipeline():
    """Scheduled task: run the full headless pipeline."""
    logger.info("SCHEDULER: Starting daily pipeline...")
    try:
        from outreach_engine.daily_run import run_daily_pipeline_headless
        batch_size = cfg.daily_send_target
        results = run_daily_pipeline_headless(batch_size=batch_size)
        logger.info("SCHEDULER: Pipeline complete — %d sent, %d generated",
                     results.get("sent", 0), results.get("generated", 0))
    except Exception:
        logger.exception("SCHEDULER: Pipeline failed")


def _scheduled_followups():
    """Scheduled task: run follow-up cycle."""
    logger.info("SCHEDULER: Starting follow-up cycle...")
    try:
        from outreach_engine.followup_engine import run_followup_cycle
        stats = run_followup_cycle(limit=20)
        logger.info("SCHEDULER: Follow-ups complete — %s", stats)
    except Exception:
        logger.exception("SCHEDULER: Follow-ups failed")


def _scheduled_backup():
    """Scheduled task: backup the database."""
    logger.info("SCHEDULER: Starting DB backup...")
    try:
        path = queue_manager.backup_database()
        logger.info("SCHEDULER: Backup saved to %s", path)
    except Exception:
        logger.exception("SCHEDULER: Backup failed")


def _scheduled_news_scan():
    """Scheduled task: scan local news for business signals."""
    logger.info("SCHEDULER: Starting news signal scan...")
    try:
        from outreach_engine.news_scanner import scan_all_sources
        stats = scan_all_sources(auto_create_contacts=True)
        logger.info("SCHEDULER: News scan complete — %d signals, %d contacts",
                     stats.get("total_signals", 0), stats.get("total_contacts_created", 0))
    except Exception:
        logger.exception("SCHEDULER: News scan failed")


def _scheduled_flywheel():
    """Scheduled task: run flywheel for contact growth."""
    logger.info("SCHEDULER: Starting flywheel...")
    try:
        from outreach_engine.flywheel import run_flywheel_batch
        stats = run_flywheel_batch(limit=20)
        logger.info("SCHEDULER: Flywheel complete — %s", stats)
    except Exception:
        logger.exception("SCHEDULER: Flywheel failed")


def _scheduled_account_maintenance():
    """Scheduled task: recalculate confidence, enforce revisits."""
    logger.info("SCHEDULER: Starting account maintenance...")
    try:
        from outreach_engine.account_manager import run_account_maintenance
        stats = run_account_maintenance()
        logger.info("SCHEDULER: Account maintenance complete — %s", stats)
    except Exception:
        logger.exception("SCHEDULER: Account maintenance failed")


def _scheduled_telegram_group_flush():
    """Scheduled task: flush stale Telegram message groups (every 60s)."""
    try:
        from outreach_engine.telegram_bot import flush_and_submit_groups
        flush_and_submit_groups()
    except Exception:
        logger.exception("SCHEDULER: Telegram group flush failed")


def _scheduled_telegram_batch_research():
    """Scheduled task: research all queued (non-urgent) Telegram ideas."""
    logger.info("SCHEDULER: Starting Telegram batch research...")
    try:
        from outreach_engine.telegram_bot import run_batch_research
        run_batch_research()
    except Exception:
        logger.exception("SCHEDULER: Telegram batch research failed")


def _scheduled_telegram_daily_summary():
    """Scheduled task: send daily summary to Telegram (8pm)."""
    logger.info("SCHEDULER: Sending Telegram daily summary...")
    try:
        from outreach_engine.telegram_notifications import send_daily_summary
        send_daily_summary()
    except Exception:
        logger.exception("SCHEDULER: Telegram daily summary failed")


def _scheduled_telegram_stuck_stages():
    """Scheduled task: check for stuck ideas and ping owner."""
    logger.info("SCHEDULER: Checking for stuck stages...")
    try:
        from outreach_engine.telegram_notifications import check_stuck_stages
        check_stuck_stages()
    except Exception:
        logger.exception("SCHEDULER: Stuck-stage check failed")


def _init_scheduler():
    """Initialize APScheduler with all scheduled tasks."""
    global _scheduler, _scheduler_running
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        _scheduler = BackgroundScheduler(timezone=cfg.scheduler_timezone)

        # Daily pipeline — runs every day at configured hour (default 9am)
        _scheduler.add_job(
            _scheduled_pipeline,
            CronTrigger(hour=cfg.pipeline_schedule_hour, minute=0),
            id="daily_pipeline",
            name="Daily Outreach Pipeline",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Follow-ups — runs daily at configured hour (default 11am)
        _scheduler.add_job(
            _scheduled_followups,
            CronTrigger(hour=cfg.followup_schedule_hour, minute=0),
            id="followup_cycle",
            name="Follow-Up Cycle",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # DB backup — runs daily at midnight
        _scheduler.add_job(
            _scheduled_backup,
            CronTrigger(hour=cfg.backup_schedule_hour, minute=0),
            id="db_backup",
            name="Database Backup",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Flywheel — runs every 6 hours
        _scheduler.add_job(
            _scheduled_flywheel,
            CronTrigger(hour="*/6", minute=30),
            id="flywheel",
            name="Flywheel Contact Growth",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # News scanner — runs 2x/day (7am and 2pm)
        _scheduler.add_job(
            _scheduled_news_scan,
            CronTrigger(hour="7,14", minute=0),
            id="news_scanner",
            name="News Signal Scanner",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Account maintenance — runs daily at configured hour (default 8am)
        _scheduler.add_job(
            _scheduled_account_maintenance,
            CronTrigger(hour=cfg.account_maintenance_hour, minute=0),
            id="account_maintenance",
            name="Account Maintenance",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Telegram: flush stale message groups every 60 seconds
        if cfg.telegram_bot_token:
            from apscheduler.triggers.interval import IntervalTrigger

            _scheduler.add_job(
                _scheduled_telegram_group_flush,
                IntervalTrigger(seconds=60),
                id="telegram_group_flush",
                name="Telegram Group Flush",
                replace_existing=True,
            )

            # Telegram: batch research at configured hours (default 9am + 3pm)
            research_hours = cfg.telegram_research_hours  # e.g. "9,15"
            _scheduler.add_job(
                _scheduled_telegram_batch_research,
                CronTrigger(hour=research_hours, minute=0),
                id="telegram_batch_research",
                name="Telegram Batch Research",
                replace_existing=True,
                misfire_grace_time=3600,
            )

            # Telegram: daily summary push (default 8pm)
            _scheduler.add_job(
                _scheduled_telegram_daily_summary,
                CronTrigger(hour=cfg.telegram_daily_summary_hour, minute=0),
                id="telegram_daily_summary",
                name="Telegram Daily Summary",
                replace_existing=True,
                misfire_grace_time=3600,
            )

            # Telegram: stuck-stage checker every 4 hours (10am, 2pm, 6pm)
            _scheduler.add_job(
                _scheduled_telegram_stuck_stages,
                CronTrigger(hour="10,14,18", minute=0),
                id="telegram_stuck_stages",
                name="Telegram Stuck Stage Checker",
                replace_existing=True,
                misfire_grace_time=3600,
            )
            logger.info("SCHEDULER: Telegram jobs added — group flush @60s, "
                         "batch research @%sh, daily summary @%dh, "
                         "stuck-stage check @10h+14h+18h",
                         research_hours, cfg.telegram_daily_summary_hour)

        _scheduler.start()
        _scheduler_running = True
        logger.info("SCHEDULER: Started with %d jobs — acct maint @%dh, pipeline @%dh, "
                     "followups @%dh, backup @%dh, flywheel every 6h, news scan @7h+14h",
                     len(_scheduler.get_jobs()),
                     cfg.account_maintenance_hour, cfg.pipeline_schedule_hour,
                     cfg.followup_schedule_hour, cfg.backup_schedule_hour)
    except Exception:
        logger.exception("SCHEDULER: Failed to initialize — running without scheduler")
        _scheduler_running = False


@app.on_event("startup")
def start_scheduler():
    """Start the scheduler on sidecar startup."""
    auto_schedule = os.getenv("AUTO_SCHEDULE", "true").lower() == "true"
    if auto_schedule:
        _init_scheduler()
    else:
        logger.info("SCHEDULER: Disabled (AUTO_SCHEDULE=false)")


@app.on_event("shutdown")
def stop_scheduler():
    global _scheduler, _scheduler_running
    if _scheduler and _scheduler_running:
        _scheduler.shutdown(wait=False)
        _scheduler_running = False
        logger.info("SCHEDULER: Stopped")


# ── Scheduler Control API ──

@app.get("/api/scheduler/status")
def scheduler_status():
    """Get scheduler status and next run times."""
    if not _scheduler or not _scheduler_running:
        return {"running": False, "jobs": []}

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "pending": job.pending,
        })
    return {"running": True, "jobs": jobs, "timezone": cfg.scheduler_timezone}


@app.post("/api/scheduler/pause")
def pause_scheduler():
    """Pause the scheduler (all jobs stop firing)."""
    global _scheduler_running
    if _scheduler:
        _scheduler.pause()
        _scheduler_running = False
        return {"status": "paused"}
    raise HTTPException(status_code=400, detail="Scheduler not initialized")


@app.post("/api/scheduler/resume")
def resume_scheduler():
    """Resume a paused scheduler."""
    global _scheduler_running
    if _scheduler:
        _scheduler.resume()
        _scheduler_running = True
        return {"status": "resumed"}
    raise HTTPException(status_code=400, detail="Scheduler not initialized")


@app.post("/api/scheduler/trigger/{job_id}")
def trigger_job(job_id: str, background_tasks: BackgroundTasks):
    """Manually trigger a scheduled job immediately."""
    job_map = {
        "daily_pipeline": _scheduled_pipeline,
        "followup_cycle": _scheduled_followups,
        "db_backup": _scheduled_backup,
        "flywheel": _scheduled_flywheel,
        "news_scanner": _scheduled_news_scan,
        "account_maintenance": _scheduled_account_maintenance,
        "telegram_group_flush": _scheduled_telegram_group_flush,
        "telegram_batch_research": _scheduled_telegram_batch_research,
        "telegram_daily_summary": _scheduled_telegram_daily_summary,
        "telegram_stuck_stages": _scheduled_telegram_stuck_stages,
    }
    if job_id not in job_map:
        raise HTTPException(status_code=404,
                            detail=f"Job '{job_id}' not found. Available: {list(job_map.keys())}")
    background_tasks.add_task(job_map[job_id])
    return {"status": "triggered", "job_id": job_id}


def start_sidecar():
    import uvicorn
    # Render sets PORT env var; fall back to configured sidecar_port
    port = int(os.getenv("PORT", str(cfg.sidecar_port)))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    start_sidecar()
