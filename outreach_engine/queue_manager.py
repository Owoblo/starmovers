"""SQLite CRUD for outreach queue management."""

import json
import sqlite3
from datetime import date, datetime
from typing import Optional

from outreach_engine.config import cfg


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Queue CRUD ──


def get_queue(batch_date: Optional[str] = None) -> list[dict]:
    """Get all bundles for a given date with contact info."""
    conn = _get_conn()
    d = batch_date or date.today().isoformat()

    rows = conn.execute("""
        SELECT
            b.id, b.contact_id, b.batch_date, b.email_subject, b.email_body,
            b.status, b.approved_at, b.sent_at, b.email_sent,
            b.open_count, b.first_opened_at, b.notes,
            c.company_name, c.website, c.domain, c.city,
            c.contact_name, c.title_role, c.tier, c.industry_code,
            c.priority_score, c.discovered_email, c.email_status,
            c.phone
        FROM outreach_bundles b
        JOIN contacts c ON b.contact_id = c.id
        WHERE b.batch_date = ?
        ORDER BY c.priority_score DESC, c.company_name ASC
    """, (d,)).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def get_bundle(bundle_id: int) -> Optional[dict]:
    """Get a single bundle with full context."""
    conn = _get_conn()
    row = conn.execute("""
        SELECT
            b.*, c.company_name, c.website, c.domain, c.city,
            c.contact_name, c.title_role, c.tier, c.industry_code,
            c.priority_score, c.discovered_email, c.email_status,
            c.phone, c.street_address, c.postal_code, c.notes as contact_notes
        FROM outreach_bundles b
        JOIN contacts c ON b.contact_id = c.id
        WHERE b.id = ?
    """, (bundle_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_bundle(contact_id: int, batch_date: str, email_subject: str,
                  email_body: str) -> int:
    """Create a new outreach bundle. Returns the new bundle ID."""
    conn = _get_conn()
    cur = conn.execute("""
        INSERT INTO outreach_bundles (contact_id, batch_date, email_subject, email_body)
        VALUES (?, ?, ?, ?)
    """, (contact_id, batch_date, email_subject, email_body))
    bundle_id = cur.lastrowid
    conn.commit()
    conn.close()
    return bundle_id


def approve_bundle(bundle_id: int) -> bool:
    conn = _get_conn()
    conn.execute(
        "UPDATE outreach_bundles SET status = 'approved', approved_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (datetime.now().isoformat(), bundle_id),
    )
    conn.commit()
    conn.close()
    return True


def edit_bundle(bundle_id: int, email_subject: Optional[str] = None,
                email_body: Optional[str] = None, notes: Optional[str] = None) -> bool:
    conn = _get_conn()
    updates = []
    params = []
    if email_subject is not None:
        updates.append("email_subject = ?")
        params.append(email_subject)
    if email_body is not None:
        updates.append("email_body = ?")
        params.append(email_body)
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)

    if not updates:
        conn.close()
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(bundle_id)

    conn.execute(
        f"UPDATE outreach_bundles SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    conn.close()
    return True


def skip_bundle(bundle_id: int) -> bool:
    conn = _get_conn()
    conn.execute(
        "UPDATE outreach_bundles SET status = 'skipped', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (bundle_id,),
    )
    row = conn.execute("SELECT contact_id FROM outreach_bundles WHERE id = ?", (bundle_id,)).fetchone()
    if row:
        conn.execute(
            "UPDATE contacts SET outreach_status = 'skipped' WHERE id = ?",
            (row["contact_id"],),
        )
    conn.commit()
    conn.close()
    return True


def mark_sent(bundle_id: int, email_sent: bool = False) -> bool:
    conn = _get_conn()
    conn.execute("""
        UPDATE outreach_bundles
        SET status = 'sent', sent_at = ?, email_sent = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (datetime.now().isoformat(), email_sent, bundle_id))

    row = conn.execute("SELECT contact_id FROM outreach_bundles WHERE id = ?", (bundle_id,)).fetchone()
    if row:
        conn.execute(
            "UPDATE contacts SET outreach_status = 'sent' WHERE id = ?",
            (row["contact_id"],),
        )
    conn.commit()
    conn.close()
    return True


def mark_bounced(bundle_id: int) -> dict:
    """Mark bundle as bounced and record the bad email on the contact.

    Returns dict with contact_id and the bounced email for recovery flow.
    """
    conn = _get_conn()
    conn.execute(
        "UPDATE outreach_bundles SET status = 'bounced', notes = 'email bounced', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (bundle_id,),
    )

    # Get contact info
    row = conn.execute("""
        SELECT b.contact_id, c.discovered_email, c.bounced_emails, c.bounce_count
        FROM outreach_bundles b
        JOIN contacts c ON b.contact_id = c.id
        WHERE b.id = ?
    """, (bundle_id,)).fetchone()

    contact_id = 0
    bounced_email = ""
    if row:
        contact_id = row["contact_id"]
        bounced_email = row["discovered_email"] or ""
        # Append to bounced_emails list (comma-separated)
        existing = row["bounced_emails"] or ""
        bounced_list = [e.strip() for e in existing.split(",") if e.strip()]
        if bounced_email and bounced_email not in bounced_list:
            bounced_list.append(bounced_email)
        new_bounced = ",".join(bounced_list)
        new_count = (row["bounce_count"] or 0) + 1

        # Update contact: mark email invalid, record bounce history
        conn.execute("""
            UPDATE contacts
            SET email_status = 'bounced',
                bounce_count = ?,
                bounced_emails = ?,
                outreach_status = 'pending',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_count, new_bounced, contact_id))

    conn.commit()
    conn.close()
    return {"contact_id": contact_id, "bounced_email": bounced_email}


def mark_replied(bundle_id: int) -> bool:
    conn = _get_conn()
    conn.execute(
        "UPDATE outreach_bundles SET status = 'replied', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (bundle_id,),
    )
    conn.commit()
    conn.close()
    return True


def snooze_bundle(bundle_id: int, snooze_until: str = "") -> bool:
    conn = _get_conn()
    conn.execute(
        "UPDATE outreach_bundles SET status = 'snoozed', notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (f"snoozed_until:{snooze_until}", bundle_id),
    )
    conn.commit()
    conn.close()
    return True


def mark_rejected(bundle_id: int) -> bool:
    conn = _get_conn()
    conn.execute(
        "UPDATE outreach_bundles SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (bundle_id,),
    )
    row = conn.execute("SELECT contact_id FROM outreach_bundles WHERE id = ?", (bundle_id,)).fetchone()
    if row:
        conn.execute(
            "UPDATE contacts SET outreach_status = 'rejected' WHERE id = ?",
            (row["contact_id"],),
        )
    conn.commit()
    conn.close()
    return True


# ── Tracking ──


def create_tracking(bundle_id: int, tracking_id: str) -> bool:
    conn = _get_conn()
    conn.execute(
        "INSERT INTO email_tracking (bundle_id, tracking_id, sent_at) VALUES (?, ?, ?)",
        (bundle_id, tracking_id, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return True


def record_email_open(tracking_id: str, ip_address: str = "", user_agent: str = "") -> dict | None:
    """Record an email open event. Returns {bundle_id, first_open} or None."""
    conn = _get_conn()
    tracking = conn.execute(
        "SELECT bundle_id FROM email_tracking WHERE tracking_id = ?", (tracking_id,)
    ).fetchone()
    if not tracking:
        conn.close()
        return None

    bundle_id = tracking["bundle_id"]

    # Check if this is the first open
    bundle = conn.execute(
        "SELECT open_count FROM outreach_bundles WHERE id = ?", (bundle_id,)
    ).fetchone()
    first_open = bundle["open_count"] == 0 if bundle else False

    conn.execute(
        "INSERT INTO email_opens (tracking_id, bundle_id, ip_address, user_agent) VALUES (?, ?, ?, ?)",
        (tracking_id, bundle_id, ip_address, user_agent),
    )
    conn.execute("""
        UPDATE outreach_bundles
        SET open_count = open_count + 1,
            first_opened_at = COALESCE(first_opened_at, CURRENT_TIMESTAMP),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (bundle_id,))

    conn.commit()
    conn.close()
    return {"bundle_id": bundle_id, "first_open": first_open}


# ── Batch selection ──


def select_next_batch(batch_size: int = 40) -> list[int]:
    """Select next contacts to process, one per domain, ordered by priority."""
    conn = _get_conn()

    # Get contacts with discovered emails that haven't been sent yet
    rows = conn.execute("""
        SELECT c.id, c.domain FROM contacts c
        WHERE c.outreach_status = 'pending'
        AND c.email_status IN ('verified', 'likely')
        AND c.discovered_email != ''
        AND c.account_status != 'dnc'
        AND c.id NOT IN (
            SELECT contact_id FROM outreach_bundles WHERE status NOT IN ('skipped', 'bounced')
        )
        ORDER BY c.priority_score DESC, c.id ASC
    """).fetchall()
    conn.close()

    # One per domain
    seen_domains: set[str] = set()
    selected: list[int] = []
    for row in rows:
        domain = row["domain"]
        if domain and domain in seen_domains:
            continue
        if domain:
            seen_domains.add(domain)
        selected.append(row["id"])
        if len(selected) >= batch_size:
            break

    return selected


def get_pending_send_bundles() -> list[int]:
    """Get bundle IDs ready to send (approved with batch_date <= today)."""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT id FROM outreach_bundles
        WHERE status IN ('approved') AND batch_date <= ?
    """, (date.today().isoformat(),)).fetchall()
    conn.close()
    return [r["id"] for r in rows]


# ── History + Stats ──


def get_history(limit: int = 100, offset: int = 0) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("""
        SELECT b.*, c.company_name, c.tier, c.industry_code,
               c.discovered_email, c.contact_name
        FROM outreach_bundles b
        JOIN contacts c ON b.contact_id = c.id
        WHERE b.status IN ('sent', 'replied', 'opened')
        ORDER BY b.sent_at DESC
        LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    conn = _get_conn()

    total_contacts = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    by_tier = conn.execute(
        "SELECT tier, COUNT(*) as cnt FROM contacts GROUP BY tier"
    ).fetchall()
    tier_map = {r["tier"]: r["cnt"] for r in by_tier}

    emails_found = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE discovered_email != ''"
    ).fetchone()[0]
    emails_verified = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE email_status = 'verified'"
    ).fetchone()[0]
    emails_likely = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE email_status = 'likely'"
    ).fetchone()[0]

    total_bundles = conn.execute("SELECT COUNT(*) FROM outreach_bundles").fetchone()[0]
    by_status = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM outreach_bundles GROUP BY status"
    ).fetchall()
    status_map = {r["status"]: r["cnt"] for r in by_status}

    emails_sent_count = conn.execute(
        "SELECT COUNT(*) FROM outreach_bundles WHERE email_sent = 1"
    ).fetchone()[0]
    unique_opens = conn.execute(
        "SELECT COUNT(*) FROM outreach_bundles WHERE email_sent = 1 AND open_count > 0"
    ).fetchone()[0]

    daily = conn.execute("""
        SELECT batch_date, COUNT(*) as cnt,
               SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
               SUM(CASE WHEN status = 'replied' THEN 1 ELSE 0 END) as replied
        FROM outreach_bundles
        GROUP BY batch_date
        ORDER BY batch_date DESC
        LIMIT 30
    """).fetchall()

    contacts_reached = conn.execute(
        "SELECT COUNT(DISTINCT contact_id) FROM outreach_bundles WHERE status IN ('sent', 'replied')"
    ).fetchone()[0]

    conn.close()

    return {
        "total_contacts": total_contacts,
        "by_tier": tier_map,
        "emails_found": emails_found,
        "emails_verified": emails_verified,
        "emails_likely": emails_likely,
        "emails_pending": total_contacts - emails_found,
        "total_bundles": total_bundles,
        "by_status": status_map,
        "contacts_reached": contacts_reached,
        "contacts_remaining": total_contacts - contacts_reached,
        "total_sent": status_map.get("sent", 0) + status_map.get("replied", 0),
        "total_replied": status_map.get("replied", 0),
        "total_queued": status_map.get("queued", 0),
        "total_approved": status_map.get("approved", 0),
        "total_skipped": status_map.get("skipped", 0),
        "total_bounced": status_map.get("bounced", 0),
        "total_snoozed": status_map.get("snoozed", 0),
        "total_rejected": status_map.get("rejected", 0),
        "emails_sent": emails_sent_count,
        "unique_opens": unique_opens,
        "open_rate": round(unique_opens / emails_sent_count * 100, 1) if emails_sent_count else 0,
        "daily": [dict(d) for d in daily],
    }


# ── Discovery browsing ──


def get_contacts(tier: Optional[str] = None, email_status: Optional[str] = None,
                 limit: int = 50, offset: int = 0) -> list[dict]:
    """Browse contacts with optional filters."""
    conn = _get_conn()
    where_parts = []
    params: list = []
    if tier:
        where_parts.append("tier = ?")
        params.append(tier)
    if email_status:
        where_parts.append("email_status = ?")
        params.append(email_status)

    where_clause = " AND ".join(where_parts) if where_parts else "1=1"

    rows = conn.execute(f"""
        SELECT * FROM contacts
        WHERE {where_clause}
        ORDER BY priority_score DESC, company_name ASC
        LIMIT ? OFFSET ?
    """, (*params, limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_discovery_stats() -> dict:
    """Stats for the discovery page."""
    conn = _get_conn()
    total = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    by_status = conn.execute(
        "SELECT email_status, COUNT(*) as cnt FROM contacts GROUP BY email_status"
    ).fetchall()
    by_tier = conn.execute("""
        SELECT tier, email_status, COUNT(*) as cnt
        FROM contacts GROUP BY tier, email_status
    """).fetchall()

    conn.close()
    return {
        "total": total,
        "by_status": {r["email_status"]: r["cnt"] for r in by_status},
        "by_tier": [dict(r) for r in by_tier],
    }


def get_up_next(limit: int = 20) -> list[dict]:
    """Get pending contacts not yet in bundles — the next batch candidates."""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT
            c.id, c.company_name, c.contact_name, c.title_role,
            c.tier, c.industry_code, c.priority_score,
            c.discovered_email, c.email_status, c.city, c.website
        FROM contacts c
        WHERE c.outreach_status = 'pending'
        AND c.email_status IN ('verified', 'likely')
        AND c.discovered_email != ''
        AND c.account_status != 'dnc'
        AND c.id NOT IN (
            SELECT contact_id FROM outreach_bundles WHERE status NOT IN ('skipped', 'bounced')
        )
        ORDER BY c.priority_score DESC, c.id ASC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_up_next_total() -> int:
    """Count of pending contacts not yet in bundles."""
    conn = _get_conn()
    row = conn.execute("""
        SELECT COUNT(*) as cnt FROM contacts c
        WHERE c.outreach_status = 'pending'
        AND c.email_status IN ('verified', 'likely')
        AND c.discovered_email != ''
        AND c.account_status != 'dnc'
        AND c.id NOT IN (
            SELECT contact_id FROM outreach_bundles WHERE status NOT IN ('skipped', 'bounced')
        )
    """).fetchone()
    conn.close()
    return row["cnt"]


def log_send(bundle_id: int, recipient_email: str, smtp_code: int = 0,
             smtp_response: str = "", error: str = ""):
    """Log SMTP send attempt."""
    conn = _get_conn()
    conn.execute("""
        INSERT INTO send_log (bundle_id, recipient_email, smtp_response_code, smtp_response_text, error)
        VALUES (?, ?, ?, ?, ?)
    """, (bundle_id, recipient_email, smtp_code, smtp_response, error))
    conn.commit()
    conn.close()


def update_daily_stats(stat_date: str, **kwargs):
    """Upsert daily stats."""
    conn = _get_conn()
    existing = conn.execute("SELECT id FROM daily_stats WHERE stat_date = ?", (stat_date,)).fetchone()
    if existing:
        sets = ", ".join(f"{k} = {k} + ?" for k in kwargs)
        conn.execute(
            f"UPDATE daily_stats SET {sets} WHERE stat_date = ?",
            (*kwargs.values(), stat_date),
        )
    else:
        cols = ", ".join(["stat_date"] + list(kwargs.keys()))
        placeholders = ", ".join(["?"] * (1 + len(kwargs)))
        conn.execute(
            f"INSERT INTO daily_stats ({cols}) VALUES ({placeholders})",
            (stat_date, *kwargs.values()),
        )
    conn.commit()
    conn.close()


# ── Corporate Relocation ──


def create_relocation_contact(
    company_name: str, origin_city: str = "Windsor", destination_city: str = "",
    contact_name: str = "", title_role: str = "", website: str = "",
    notes: str = "",
) -> int:
    """Create a corporate relocation contact. Returns contact_id.

    Sets tier='A', industry_code='CR25', priority_score=85.
    Stores origin/destination in notes for template engine.
    """
    from urllib.parse import urlparse

    domain = ""
    if website:
        url = website if website.startswith("http") else f"https://{website}"
        try:
            host = urlparse(url).hostname or ""
            if host.startswith("www."):
                host = host[4:]
            domain = host.lower()
        except Exception:
            pass

    reloc_notes = f"origin_city: {origin_city} | destination_city: {destination_city}"
    if notes:
        reloc_notes += f" | {notes}"

    conn = _get_conn()
    conn.execute("""
        INSERT INTO contacts (
            company_name, website, domain, city, province,
            contact_name, title_role,
            tier, industry_code, priority_score, csv_source,
            notes, outreach_status, email_status
        ) VALUES (?, ?, ?, ?, 'ON', ?, ?, 'A', 'CR25', 85, 'corporate_relocation', ?, 'pending', 'pending')
    """, (
        company_name, website, domain, origin_city,
        contact_name, title_role or "HR / Relocation Coordinator",
        reloc_notes,
    ))
    contact_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return contact_id


# ── Pipeline Run Logging ──


def log_pipeline_start(run_type: str = "headless") -> int:
    """Log a pipeline run start. Returns the run_id."""
    conn = _get_conn()
    cur = conn.execute("""
        INSERT INTO pipeline_runs (run_type, status, started_at)
        VALUES (?, 'running', ?)
    """, (run_type, datetime.now().isoformat()))
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def log_pipeline_end(run_id: int, status: str = "completed",
                     stats: dict | None = None, error: str = ""):
    """Log pipeline run completion."""
    conn = _get_conn()
    conn.execute("""
        UPDATE pipeline_runs
        SET status = ?, ended_at = ?, stats_json = ?, error = ?
        WHERE id = ?
    """, (status, datetime.now().isoformat(),
          json.dumps(stats or {}), error, run_id))
    conn.commit()
    conn.close()


def get_pipeline_runs(limit: int = 20) -> list[dict]:
    """Get recent pipeline runs."""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT * FROM pipeline_runs
        ORDER BY started_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_last_pipeline_run() -> dict | None:
    """Get the most recent pipeline run."""
    conn = _get_conn()
    row = conn.execute("""
        SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 1
    """).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Hard Daily Send Cap ──


def get_today_send_count() -> int:
    """Count emails sent today (from send_log)."""
    conn = _get_conn()
    today = date.today().isoformat()
    row = conn.execute("""
        SELECT COUNT(*) as cnt FROM send_log
        WHERE DATE(sent_at) = ?
    """, (today,)).fetchone()
    conn.close()
    return row["cnt"]


def check_daily_send_cap() -> tuple[bool, int, int]:
    """Check if we're under the daily send cap.
    Returns (can_send, sent_today, max_allowed)."""
    sent = get_today_send_count()
    max_sends = cfg.max_daily_sends
    return (sent < max_sends, sent, max_sends)


def remaining_send_budget() -> int:
    """How many more emails we can send today."""
    sent = get_today_send_count()
    return max(0, cfg.max_daily_sends - sent)


# ── Auto-Approve ──


def auto_approve_bundles(batch_date: str | None = None) -> int:
    """Auto-approve queued bundles for well-tested industry templates.
    Skips manual_review_codes (CR25, HOT25, etc). Returns count approved."""
    if not cfg.auto_approve:
        return 0

    conn = _get_conn()
    d = batch_date or date.today().isoformat()
    skip_codes = cfg.manual_review_codes

    placeholders = ",".join("?" * len(skip_codes))
    rows = conn.execute(f"""
        SELECT b.id, c.industry_code
        FROM outreach_bundles b
        JOIN contacts c ON b.contact_id = c.id
        WHERE b.status = 'queued'
        AND b.batch_date = ?
        AND c.industry_code NOT IN ({placeholders})
    """, (d, *skip_codes)).fetchall()

    count = 0
    now = datetime.now().isoformat()
    for row in rows:
        conn.execute("""
            UPDATE outreach_bundles
            SET status = 'approved', approved_at = ?,
                notes = COALESCE(notes, '') || ' [auto-approved]',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (now, row["id"]))
        count += 1

    conn.commit()
    conn.close()
    return count


# ── Discovery Rate Limiting ──


def check_discovery_rate(domain: str) -> bool:
    """Check if we can probe this domain (per-domain hourly + daily global cap).
    Returns True if allowed."""
    conn = _get_conn()

    # Global daily cap
    today = date.today().isoformat()
    daily = conn.execute("""
        SELECT COUNT(*) as cnt FROM email_discovery_log
        WHERE DATE(created_at) = ? AND step = 'smtp_probe'
    """, (today,)).fetchone()["cnt"]
    if daily >= cfg.discovery_daily_cap:
        conn.close()
        return False

    # Per-domain hourly cap
    hourly = conn.execute("""
        SELECT COUNT(*) as cnt FROM email_discovery_log
        WHERE detail LIKE ? AND step = 'smtp_probe'
        AND created_at > datetime('now', '-1 hour')
    """, (f"%{domain}%",)).fetchone()["cnt"]
    conn.close()
    return hourly < cfg.discovery_per_domain_per_hour


def get_discovery_rate_stats() -> dict:
    """Current rate limit usage."""
    conn = _get_conn()
    today = date.today().isoformat()
    daily = conn.execute("""
        SELECT COUNT(*) as cnt FROM email_discovery_log
        WHERE DATE(created_at) = ? AND step = 'smtp_probe'
    """, (today,)).fetchone()["cnt"]
    conn.close()
    return {
        "probes_today": daily,
        "daily_cap": cfg.discovery_daily_cap,
        "remaining": max(0, cfg.discovery_daily_cap - daily),
    }


# ── Follow-Up Tracking ──


def get_followup_candidates(days_since_send: int = 7, sequence: int = 1,
                            limit: int = 20) -> list[dict]:
    """Find sent bundles with no reply that are due for follow-up.
    Returns contacts/bundles eligible for follow-up #sequence."""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT
            b.id as bundle_id, b.contact_id, b.email_subject, b.email_body,
            b.sent_at, b.open_count, b.status,
            c.company_name, c.contact_name, c.discovered_email,
            c.industry_code, c.tier, c.city
        FROM outreach_bundles b
        JOIN contacts c ON b.contact_id = c.id
        WHERE b.status = 'sent'
        AND b.email_sent = 1
        AND b.reply_type = ''
        AND DATE(b.sent_at) <= DATE('now', ? || ' days')
        AND b.id NOT IN (
            SELECT DISTINCT bundle_id FROM follow_ups
            WHERE sequence_number >= ? AND status IN ('sent', 'pending')
        )
        ORDER BY b.open_count DESC, b.sent_at ASC
        LIMIT ?
    """, (f"-{days_since_send}", sequence, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_followup(contact_id: int, bundle_id: int, sequence_number: int,
                    scheduled_date: str) -> int:
    """Create a follow-up record. Returns follow_up id."""
    conn = _get_conn()
    cur = conn.execute("""
        INSERT INTO follow_ups (contact_id, bundle_id, sequence_number,
                                scheduled_date, status)
        VALUES (?, ?, ?, ?, 'pending')
    """, (contact_id, bundle_id, sequence_number, scheduled_date))
    fid = cur.lastrowid
    conn.commit()
    conn.close()
    return fid


def get_pending_followups(scheduled_date: str | None = None) -> list[dict]:
    """Get follow-ups ready to send."""
    conn = _get_conn()
    d = scheduled_date or date.today().isoformat()
    rows = conn.execute("""
        SELECT f.*, c.company_name, c.contact_name, c.discovered_email,
               c.industry_code, b.email_subject, b.email_body
        FROM follow_ups f
        JOIN contacts c ON f.contact_id = c.id
        JOIN outreach_bundles b ON f.bundle_id = b.id
        WHERE f.status = 'pending'
        AND f.scheduled_date <= ?
        ORDER BY f.scheduled_date ASC
    """, (d,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_followup_sent(followup_id: int):
    conn = _get_conn()
    conn.execute("""
        UPDATE follow_ups SET status = 'sent', sent_at = ?
        WHERE id = ?
    """, (datetime.now().isoformat(), followup_id))
    conn.commit()
    conn.close()


def get_followup_stats() -> dict:
    """Follow-up statistics."""
    conn = _get_conn()
    total = conn.execute("SELECT COUNT(*) FROM follow_ups").fetchone()[0]
    by_status = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM follow_ups GROUP BY status"
    ).fetchall()
    by_seq = conn.execute(
        "SELECT sequence_number, COUNT(*) as cnt FROM follow_ups GROUP BY sequence_number"
    ).fetchall()
    conn.close()
    return {
        "total": total,
        "by_status": {r["status"]: r["cnt"] for r in by_status},
        "by_sequence": {r["sequence_number"]: r["cnt"] for r in by_seq},
    }


# ── DB Backup ──


# ── News Signals ──


def get_news_signals(status: Optional[str] = None, signal_type: Optional[str] = None,
                     limit: int = 50, offset: int = 0) -> list[dict]:
    """Browse news signals with optional filters."""
    conn = _get_conn()
    where_parts = ["signal_type != 'none'"]
    params: list = []
    if status:
        where_parts.append("status = ?")
        params.append(status)
    if signal_type:
        where_parts.append("signal_type = ?")
        params.append(signal_type)

    where_clause = " AND ".join(where_parts)
    rows = conn.execute(f"""
        SELECT * FROM news_signals
        WHERE {where_clause}
        ORDER BY scraped_at DESC
        LIMIT ? OFFSET ?
    """, (*params, limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_news_signal(signal_id: int) -> Optional[dict]:
    """Get a single news signal by ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM news_signals WHERE id = ?", (signal_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_news_signal_status(signal_id: int, status: str) -> bool:
    """Update a news signal's status (new → reviewed, contacted, dismissed)."""
    conn = _get_conn()
    conn.execute(
        "UPDATE news_signals SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, signal_id),
    )
    conn.commit()
    conn.close()
    return True


def backup_database() -> str:
    """Create a timestamped SQLite backup. Returns backup file path."""
    import shutil

    cfg.backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = cfg.backup_dir / f"outreach_{timestamp}.db"

    # Use SQLite backup API for consistency
    src = sqlite3.connect(str(cfg.db_path), timeout=30)
    dst = sqlite3.connect(str(backup_path))
    src.backup(dst)
    dst.close()
    src.close()

    # Cleanup old backups
    backups = sorted(cfg.backup_dir.glob("outreach_*.db"))
    while len(backups) > cfg.backup_keep_days:
        oldest = backups.pop(0)
        oldest.unlink()

    return str(backup_path)


def list_backups() -> list[dict]:
    """List available backups."""
    if not cfg.backup_dir.exists():
        return []
    backups = sorted(cfg.backup_dir.glob("outreach_*.db"), reverse=True)
    return [
        {"filename": b.name, "size_mb": round(b.stat().st_size / 1024 / 1024, 2),
         "created": datetime.fromtimestamp(b.stat().st_mtime).isoformat()}
        for b in backups
    ]


# ── Account Board ──


def get_account_board(status: Optional[str] = None, limit: int = 100,
                      offset: int = 0) -> list[dict]:
    """Get contacts grouped by account_status for the board view."""
    conn = _get_conn()
    where = "WHERE c.account_status != 'dnc'" if not status else "WHERE c.account_status = ?"
    params: list = [] if not status else [status]

    rows = conn.execute(f"""
        SELECT c.id, c.company_name, c.contact_name, c.title_role,
               c.tier, c.industry_code, c.city, c.website, c.phone,
               c.discovered_email, c.email_status,
               c.company_size, c.company_type, c.confidence_score,
               c.account_status, c.last_touch_date, c.next_action_date,
               c.next_action, c.decision_maker_found, c.procurement_required,
               (SELECT COUNT(*) FROM touch_log t WHERE t.contact_id = c.id) as touch_count,
               (SELECT COUNT(*) FROM outreach_bundles ob
                WHERE ob.contact_id = c.id AND ob.open_count > 0) as opens
        FROM contacts c
        {where}
        ORDER BY c.confidence_score DESC, c.priority_score DESC
        LIMIT ? OFFSET ?
    """, (*params, limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_account_board_stats() -> dict:
    """Get account board summary statistics."""
    conn = _get_conn()
    by_status = conn.execute("""
        SELECT account_status, COUNT(*) as cnt,
               AVG(confidence_score) as avg_confidence
        FROM contacts
        GROUP BY account_status
    """).fetchall()

    total = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    high_confidence = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE confidence_score >= 70"
    ).fetchone()[0]
    needs_review = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE confidence_score BETWEEN 40 AND 69"
    ).fetchone()[0]
    low_confidence = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE confidence_score < 40 AND account_status != 'dnc'"
    ).fetchone()[0]

    conn.close()
    return {
        "total": total,
        "by_status": {r["account_status"]: {"count": r["cnt"],
                      "avg_confidence": round(r["avg_confidence"] or 0, 1)}
                      for r in by_status},
        "high_confidence": high_confidence,
        "needs_review": needs_review,
        "low_confidence": low_confidence,
    }


def get_account_detail(contact_id: int) -> Optional[dict]:
    """Get full account detail including touches and bundles."""
    conn = _get_conn()
    contact = conn.execute("SELECT * FROM contacts WHERE id = ?",
                           (contact_id,)).fetchone()
    if not contact:
        conn.close()
        return None

    touches = conn.execute("""
        SELECT * FROM touch_log WHERE contact_id = ?
        ORDER BY touch_date DESC LIMIT 50
    """, (contact_id,)).fetchall()

    bundles = conn.execute("""
        SELECT id, batch_date, status, email_subject, sent_at, open_count,
               reply_type, reply_snippet
        FROM outreach_bundles WHERE contact_id = ?
        ORDER BY created_at DESC
    """, (contact_id,)).fetchall()

    jobs = conn.execute("""
        SELECT * FROM jobs WHERE contact_id = ?
        ORDER BY created_at DESC
    """, (contact_id,)).fetchall()

    conn.close()
    return {
        "contact": dict(contact),
        "touches": [dict(t) for t in touches],
        "bundles": [dict(b) for b in bundles],
        "jobs": [dict(j) for j in jobs],
    }


# ── Touch Log CRUD ──


def log_touch(contact_id: int, channel: str, direction: str = "outbound",
              subject: str = "", notes: str = "", outcome: str = "",
              logged_by: str = "system") -> int:
    """Log a multi-channel touch. Returns touch_log id."""
    conn = _get_conn()
    cur = conn.execute("""
        INSERT INTO touch_log (contact_id, channel, direction, subject,
                               notes, outcome, logged_by, touch_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, channel, direction, subject, notes, outcome,
          logged_by, date.today().isoformat()))
    tid = cur.lastrowid
    # Update last_touch_date
    conn.execute(
        "UPDATE contacts SET last_touch_date = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (date.today().isoformat(), contact_id),
    )
    conn.commit()
    conn.close()
    return tid


def get_touches(contact_id: int, limit: int = 50) -> list[dict]:
    """Get touch log for a contact."""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT * FROM touch_log WHERE contact_id = ?
        ORDER BY touch_date DESC, created_at DESC LIMIT ?
    """, (contact_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_touch_stats() -> dict:
    """Get touch statistics across all contacts."""
    conn = _get_conn()
    by_channel = conn.execute("""
        SELECT channel, COUNT(*) as cnt FROM touch_log GROUP BY channel
    """).fetchall()
    by_direction = conn.execute("""
        SELECT direction, COUNT(*) as cnt FROM touch_log GROUP BY direction
    """).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM touch_log").fetchone()[0]
    conn.close()
    return {
        "total": total,
        "by_channel": {r["channel"]: r["cnt"] for r in by_channel},
        "by_direction": {r["direction"]: r["cnt"] for r in by_direction},
    }


# ── Ecosystem Contacts CRUD ──


def create_ecosystem_contact(name: str, role: str, email: str = "",
                             phone: str = "", company: str = "",
                             source_contact_id: Optional[int] = None,
                             notes: str = "") -> int:
    """Create an ecosystem contact (realtor, lawyer, broker, etc). Returns id."""
    conn = _get_conn()
    cur = conn.execute("""
        INSERT INTO ecosystem_contacts (name, email, phone, role, company,
                                        source_contact_id, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, email, phone, role, company, source_contact_id, notes))
    eid = cur.lastrowid
    conn.commit()
    conn.close()
    return eid


def get_ecosystem_contacts(role: Optional[str] = None,
                           limit: int = 50, offset: int = 0) -> list[dict]:
    """List ecosystem contacts with optional role filter."""
    conn = _get_conn()
    if role:
        rows = conn.execute("""
            SELECT * FROM ecosystem_contacts WHERE role = ?
            ORDER BY created_at DESC LIMIT ? OFFSET ?
        """, (role, limit, offset)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM ecosystem_contacts
            ORDER BY created_at DESC LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def promote_ecosystem_contact(ecosystem_id: int) -> Optional[int]:
    """Promote an ecosystem contact to a full CRM contact.

    Returns the new contact_id, or None if failed.
    """
    conn = _get_conn()
    eco = conn.execute(
        "SELECT * FROM ecosystem_contacts WHERE id = ?", (ecosystem_id,)
    ).fetchone()
    if not eco:
        conn.close()
        return None

    # Create a new contact
    cur = conn.execute("""
        INSERT INTO contacts (company_name, contact_name, phone, discovered_email,
                              email_status, tier, priority_score, notes,
                              csv_source, outreach_status, account_status)
        VALUES (?, ?, ?, ?, ?, 'B', 60, ?, 'ecosystem_promote', 'pending', 'cold')
    """, (
        eco["company"] or eco["name"],
        eco["name"],
        eco["phone"] or "",
        eco["email"] or "",
        "likely" if eco["email"] else "pending",
        f"Promoted from ecosystem ({eco['role']}). {eco['notes'] or ''}",
    ))
    new_id = cur.lastrowid

    # Mark the ecosystem contact as promoted
    conn.execute(
        "UPDATE ecosystem_contacts SET promoted_contact_id = ? WHERE id = ?",
        (new_id, ecosystem_id),
    )
    conn.commit()
    conn.close()
    return new_id


# ── Partner Codes CRUD ──


def create_partner_code(partner_name: str, code: str,
                        discount_percent: float = 0,
                        bonus_per_referral: float = 0) -> int:
    """Create a partner code. Returns id."""
    conn = _get_conn()
    cur = conn.execute("""
        INSERT INTO partner_codes (partner_name, code, discount_percent,
                                   bonus_per_referral)
        VALUES (?, ?, ?, ?)
    """, (partner_name, code.upper(), discount_percent, bonus_per_referral))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def get_partner_codes(status: str = "active",
                      limit: int = 50) -> list[dict]:
    """List partner codes."""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT * FROM partner_codes
        WHERE status = ?
        ORDER BY total_revenue DESC
        LIMIT ?
    """, (status, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def lookup_partner_code(code: str) -> Optional[dict]:
    """Look up a partner code."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM partner_codes WHERE code = ?", (code.upper(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Jobs CRUD ──


def create_job(contact_id: Optional[int] = None, partner_code: str = "",
               job_type: str = "commercial", quote_amount: float = 0,
               move_date: str = "", origin_address: str = "",
               destination_address: str = "", crew_size: int = 0,
               truck_count: int = 0, notes: str = "") -> int:
    """Create a job. Returns job id."""
    conn = _get_conn()
    cur = conn.execute("""
        INSERT INTO jobs (contact_id, partner_code, job_type, status,
                          quote_amount, move_date, origin_address,
                          destination_address, crew_size, truck_count, notes)
        VALUES (?, ?, ?, 'quoted', ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, partner_code.upper() if partner_code else "",
          job_type, quote_amount, move_date, origin_address,
          destination_address, crew_size, truck_count, notes))
    jid = cur.lastrowid
    conn.commit()
    conn.close()
    return jid


def get_jobs(status: Optional[str] = None, limit: int = 50,
             offset: int = 0) -> list[dict]:
    """List jobs with optional status filter."""
    conn = _get_conn()
    if status:
        rows = conn.execute("""
            SELECT j.*, c.company_name, c.contact_name
            FROM jobs j
            LEFT JOIN contacts c ON j.contact_id = c.id
            WHERE j.status = ?
            ORDER BY j.created_at DESC LIMIT ? OFFSET ?
        """, (status, limit, offset)).fetchall()
    else:
        rows = conn.execute("""
            SELECT j.*, c.company_name, c.contact_name
            FROM jobs j
            LEFT JOIN contacts c ON j.contact_id = c.id
            ORDER BY j.created_at DESC LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job(job_id: int) -> Optional[dict]:
    """Get a single job with contact info."""
    conn = _get_conn()
    row = conn.execute("""
        SELECT j.*, c.company_name, c.contact_name
        FROM jobs j
        LEFT JOIN contacts c ON j.contact_id = c.id
        WHERE j.id = ?
    """, (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_job(job_id: int, **kwargs) -> bool:
    """Update a job. Handles partner revenue attribution on completion."""
    conn = _get_conn()
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        conn.close()
        return False

    updates = []
    params = []
    for k, v in kwargs.items():
        if v is not None and k in ("status", "final_amount", "move_date",
                                    "crew_size", "truck_count", "labor_hours",
                                    "notes"):
            updates.append(f"{k} = ?")
            params.append(v)

    if not updates:
        conn.close()
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(job_id)
    conn.execute(f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?", params)

    # Partner revenue attribution on completion
    new_status = kwargs.get("status")
    if new_status == "completed" and job["partner_code"]:
        final = kwargs.get("final_amount", job["final_amount"]) or job["quote_amount"]
        conn.execute("""
            UPDATE partner_codes
            SET total_referrals = total_referrals + 1,
                total_revenue = total_revenue + ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE code = ?
        """, (final, job["partner_code"]))

    conn.commit()
    conn.close()
    return True


def get_job_stats() -> dict:
    """Get job pipeline statistics."""
    conn = _get_conn()
    by_status = conn.execute("""
        SELECT status, COUNT(*) as cnt,
               SUM(quote_amount) as total_quoted,
               SUM(final_amount) as total_final
        FROM jobs GROUP BY status
    """).fetchall()

    total_revenue = conn.execute(
        "SELECT SUM(final_amount) FROM jobs WHERE status = 'completed'"
    ).fetchone()[0] or 0

    total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    conn.close()
    return {
        "total_jobs": total_jobs,
        "total_revenue": total_revenue,
        "by_status": {r["status"]: {
            "count": r["cnt"],
            "quoted": r["total_quoted"] or 0,
            "final": r["total_final"] or 0,
        } for r in by_status},
    }


# ── Field Intel / Account Research CRUD ──


def submit_idea(company_name: str, user_notes: str = "",
                city: str = "Windsor-Essex", industry: str = "",
                priority: str = "medium") -> int:
    """Submit a field intel idea. Returns idea id."""
    conn = _get_conn()
    cur = conn.execute("""
        INSERT INTO account_research (company_name, user_notes, city,
                                      industry, priority, research_status)
        VALUES (?, ?, ?, ?, ?, 'new')
    """, (company_name, user_notes, city, industry, priority))
    idea_id = cur.lastrowid
    conn.commit()
    conn.close()
    return idea_id


def get_ideas(status: Optional[str] = None, limit: int = 50,
              offset: int = 0) -> list[dict]:
    """List field intel ideas with optional status filter."""
    conn = _get_conn()
    if status:
        rows = conn.execute("""
            SELECT * FROM account_research WHERE research_status = ?
            ORDER BY
                CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2
                     WHEN 'medium' THEN 3 ELSE 4 END,
                created_at DESC
            LIMIT ? OFFSET ?
        """, (status, limit, offset)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM account_research
            ORDER BY
                CASE research_status
                    WHEN 'active' THEN 1 WHEN 'staged' THEN 2
                    WHEN 'researched' THEN 3 WHEN 'researching' THEN 4
                    WHEN 'new' THEN 5 WHEN 'completed' THEN 6
                    ELSE 7 END,
                CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2
                     WHEN 'medium' THEN 3 ELSE 4 END,
                created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_idea(idea_id: int) -> Optional[dict]:
    """Get a single field intel idea with full detail."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM account_research WHERE id = ?", (idea_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    # Parse JSON fields for convenience
    import json
    for field in ("angles", "target_contacts", "stages_json"):
        try:
            result[field] = json.loads(result.get(field) or "[]")
        except (json.JSONDecodeError, TypeError):
            pass
    return result


def update_idea_notes(idea_id: int, notes: str) -> bool:
    """Append additional notes to an idea (field intel updates)."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT user_notes FROM account_research WHERE id = ?", (idea_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False

    existing = row["user_notes"] or ""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    updated = f"{existing}\n[{ts}] {notes}" if existing else f"[{ts}] {notes}"

    conn.execute(
        "UPDATE account_research SET user_notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (updated, idea_id))
    conn.commit()
    conn.close()
    return True
