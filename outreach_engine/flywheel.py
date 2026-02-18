"""Auto-growing contact list — triggers on engagement signals.

The flywheel: more sends → more opens/replies → more team members discovered →
more contacts → more sends. Growth is capped per trigger to prevent runaway.

Triggers:
  - Email opened (first open only) → scrape company for teammates
  - Positive/neutral reply → deeper scrape + extract names from reply text
  - Periodic batch → process unprocessed opens/replies

Safety:
  - Max contacts per trigger event (5 for opens, 8 for replies)
  - Company cap: skip if company already has 5+ contacts
  - Daily cap: max 50 new flywheel contacts per day
  - Lower priority score (40-50) so they don't flood the queue
  - No auto-queue: contacts appear in Up-Next for normal pipeline inclusion
"""

import logging
import re
import sqlite3
from datetime import date

from outreach_engine.config import cfg
from outreach_engine.email_discovery import discover_team_emails, scrape_team_members

logger = logging.getLogger(__name__)

MAX_PER_OPEN = 5
MAX_PER_REPLY = 8
MAX_PER_SIMILAR = 10
COMPANY_CAP = 5
DAILY_CAP = 50


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _count_company_contacts(conn: sqlite3.Connection, company_name: str) -> int:
    """Count existing contacts for a company."""
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM contacts WHERE company_name = ?",
        (company_name,),
    ).fetchone()
    return row["cnt"]


def _count_daily_flywheel(conn: sqlite3.Connection) -> int:
    """Count flywheel contacts created today."""
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM contacts WHERE csv_source LIKE 'flywheel_%' AND DATE(created_at) = ?",
        (today,),
    ).fetchone()
    return row["cnt"]


def _contact_exists(conn: sqlite3.Connection, company_name: str, email: str) -> bool:
    """Check if a contact with this company + email already exists."""
    if email:
        row = conn.execute(
            "SELECT id FROM contacts WHERE discovered_email = ?", (email,)
        ).fetchone()
        if row:
            return True
    return False


def _create_flywheel_contact(
    conn: sqlite3.Connection,
    company_name: str, website: str, domain: str, city: str,
    contact_name: str, title: str, email: str, email_status: str,
    source_type: str, source_contact_id: int | None = None,
    tier: str = "", industry_code: str = "", priority_score: int = 45,
) -> int | None:
    """Create a flywheel-sourced contact. Returns new ID or None if duplicate."""
    # Dedup check
    if _contact_exists(conn, company_name, email):
        return None

    # Check same name at same company
    existing = conn.execute(
        "SELECT id FROM contacts WHERE company_name = ? AND contact_name = ?",
        (company_name, contact_name),
    ).fetchone()
    if existing:
        return None

    conn.execute("""
        INSERT INTO contacts (
            company_name, website, domain, city, province,
            contact_name, title_role, discovered_email, email_status,
            tier, industry_code, priority_score,
            csv_source, source_contact_id, outreach_status, notes
        ) VALUES (?, ?, ?, ?, 'ON', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (
        company_name, website, domain, city,
        contact_name, title, email, email_status,
        tier, industry_code, priority_score,
        f"flywheel_{source_type}", source_contact_id,
        f"Auto-discovered via {source_type} on {date.today().isoformat()}",
    ))
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return new_id


def on_email_opened(bundle_id: int) -> int:
    """Triggered on first email open. Scrapes company for teammates.

    Returns count of new contacts created.
    """
    conn = _get_conn()

    # Check daily cap
    if _count_daily_flywheel(conn) >= DAILY_CAP:
        conn.close()
        return 0

    # Get bundle + contact info
    row = conn.execute("""
        SELECT b.contact_id, c.company_name, c.website, c.domain, c.city,
               c.tier, c.industry_code, c.priority_score
        FROM outreach_bundles b
        JOIN contacts c ON b.contact_id = c.id
        WHERE b.id = ?
    """, (bundle_id,)).fetchone()

    if not row:
        conn.close()
        return 0

    company = row["company_name"]
    website = row["website"]
    domain = row["domain"]
    city = row["city"] or "Windsor"
    contact_id = row["contact_id"]

    # Company cap
    if _count_company_contacts(conn, company) >= COMPANY_CAP:
        logger.info("Flywheel: %s already has %d+ contacts, skipping", company, COMPANY_CAP)
        conn.close()
        return 0

    if not website or not domain:
        conn.close()
        return 0

    # Scrape team members
    logger.info("Flywheel (open): scraping %s for team members", company)
    try:
        team = discover_team_emails(website, domain, city)
    except Exception as e:
        logger.warning("Flywheel: team scrape failed for %s: %s", company, e)
        conn.close()
        return 0

    created = 0
    for person in team[:MAX_PER_OPEN]:
        new_id = _create_flywheel_contact(
            conn,
            company_name=company,
            website=website, domain=domain, city=city,
            contact_name=person.get("name", ""),
            title=person.get("title", ""),
            email=person.get("email", ""),
            email_status=person.get("email_status", "pending"),
            source_type="open",
            source_contact_id=contact_id,
            tier=row["tier"], industry_code=row["industry_code"],
            priority_score=45,
        )
        if new_id:
            created += 1

    conn.commit()
    conn.close()
    logger.info("Flywheel (open): created %d contacts from %s", created, company)
    return created


def _extract_mentioned_contacts(reply_body: str) -> list[dict]:
    """Parse reply text for mentioned names and emails.

    Returns [{name, email, context}].
    """
    results = []

    # Extract email addresses
    email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    emails = email_pattern.findall(reply_body)
    for email in emails:
        results.append({"name": "", "email": email.lower(), "context": "mentioned in reply"})

    # Extract names from redirect patterns
    name_patterns = [
        r"(?:please\s+)?(?:contact|reach out to|talk to|speak with|email|ask for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:handles|manages|is in charge of|deals with|takes care of)",
        r"(?:forward|forwarding|redirect|redirecting)\s+(?:this\s+)?to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"([A-Z][a-z]+)\s+(?:is|would be)\s+(?:the\s+)?(?:right|better|best)\s+(?:person|contact)",
    ]

    for pattern in name_patterns:
        matches = re.findall(pattern, reply_body)
        for name in matches:
            name = name.strip()
            if len(name) > 2 and name.lower() not in ("the", "our", "your", "this", "that"):
                results.append({"name": name, "email": "", "context": "mentioned in reply"})

    return results


def on_reply_received(bundle_id: int, reply_body: str = "") -> int:
    """Triggered on positive/neutral reply. Scrapes + extracts names.

    Returns count of new contacts created.
    """
    conn = _get_conn()

    if _count_daily_flywheel(conn) >= DAILY_CAP:
        conn.close()
        return 0

    row = conn.execute("""
        SELECT b.contact_id, c.company_name, c.website, c.domain, c.city,
               c.tier, c.industry_code, c.priority_score
        FROM outreach_bundles b
        JOIN contacts c ON b.contact_id = c.id
        WHERE b.id = ?
    """, (bundle_id,)).fetchone()

    if not row:
        conn.close()
        return 0

    company = row["company_name"]
    website = row["website"]
    domain = row["domain"]
    city = row["city"] or "Windsor"
    contact_id = row["contact_id"]

    if _count_company_contacts(conn, company) >= COMPANY_CAP:
        conn.close()
        return 0

    created = 0

    # 1. Extract mentioned contacts from reply text
    if reply_body:
        mentioned = _extract_mentioned_contacts(reply_body)
        for person in mentioned[:3]:  # Max 3 from reply text
            if person["email"] or person["name"]:
                new_id = _create_flywheel_contact(
                    conn,
                    company_name=company,
                    website=website, domain=domain, city=city,
                    contact_name=person.get("name", ""),
                    title="",
                    email=person.get("email", ""),
                    email_status="likely" if person.get("email") else "pending",
                    source_type="reply",
                    source_contact_id=contact_id,
                    tier=row["tier"], industry_code=row["industry_code"],
                    priority_score=50,
                )
                if new_id:
                    created += 1

    # 2. Team scrape (deeper than open trigger)
    if website and domain and created < MAX_PER_REPLY:
        logger.info("Flywheel (reply): scraping %s for team members", company)
        try:
            team = discover_team_emails(website, domain, city)
            remaining = MAX_PER_REPLY - created
            for person in team[:remaining]:
                new_id = _create_flywheel_contact(
                    conn,
                    company_name=company,
                    website=website, domain=domain, city=city,
                    contact_name=person.get("name", ""),
                    title=person.get("title", ""),
                    email=person.get("email", ""),
                    email_status=person.get("email_status", "pending"),
                    source_type="reply",
                    source_contact_id=contact_id,
                    tier=row["tier"], industry_code=row["industry_code"],
                    priority_score=50,
                )
                if new_id:
                    created += 1
        except Exception as e:
            logger.warning("Flywheel: team scrape failed for %s: %s", company, e)

    conn.commit()
    conn.close()
    logger.info("Flywheel (reply): created %d contacts from %s", created, company)
    return created


def find_similar_companies(contact_id: int, limit: int = 10) -> list[dict]:
    """For a successful contact, find similar companies not yet in DB.

    Uses GPT to suggest similar local businesses.
    Returns [{company_name, industry_code, tier, city}].
    """
    if not cfg.openai_api_key:
        return []

    conn = _get_conn()
    contact = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not contact:
        conn.close()
        return []

    industry_code = contact["industry_code"]
    city = contact["city"] or "Windsor"

    # Get existing company names for this industry to avoid duplicates
    existing = conn.execute(
        "SELECT company_name FROM contacts WHERE industry_code = ? AND city = ?",
        (industry_code, city),
    ).fetchall()
    existing_names = [r["company_name"] for r in existing]
    conn.close()

    industry_labels = {
        "DL25": "divorce/family law firms", "EL25": "estate lawyers",
        "MB25": "mortgage brokers", "HB25": "home builders",
        "IR25": "insurance/restoration companies", "CC25": "condo/property management",
        "LE25": "large employers", "UN25": "universities/colleges",
        "HO25": "hospitals/healthcare facilities", "HT25": "hotels",
        "GV25": "government offices", "EM25": "engineering/manufacturing companies",
        "CH25": "churches", "NPWE25": "nonprofits", "NPCK25": "nonprofits",
        "SC25": "sports clubs", "CU25": "cultural clubs",
        "RH25": "retirement/care homes", "FH25": "funeral homes",
    }
    industry_label = industry_labels.get(industry_code, "businesses")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg.openai_api_key)
        resp = client.chat.completions.create(
            model=cfg.llm_model,
            messages=[{"role": "user", "content": (
                f"List {limit} {industry_label} in {city}, Ontario, Canada "
                f"that are NOT in this list: {existing_names[:30]}. "
                f"Return ONLY company names, one per line. No numbering, no explanations."
            )}],
            max_tokens=500,
            temperature=0.8,
        )
        text = resp.choices[0].message.content or ""
        suggestions = []
        for line in text.strip().split("\n"):
            name = line.strip().strip("- •*0123456789.")
            if name and len(name) > 2 and name.lower() not in {n.lower() for n in existing_names}:
                suggestions.append({
                    "company_name": name,
                    "industry_code": industry_code,
                    "tier": contact["tier"],
                    "city": city,
                })
        return suggestions[:limit]
    except Exception as e:
        logger.warning("Similar company search failed: %s", e)
        return []


def run_flywheel_batch(limit: int = 20) -> dict:
    """Process unprocessed opens/replies for flywheel growth.

    Returns {opens_processed, replies_processed, new_contacts, daily_total}.
    """
    conn = _get_conn()
    results = {"opens_processed": 0, "replies_processed": 0, "new_contacts": 0}

    daily = _count_daily_flywheel(conn)
    if daily >= DAILY_CAP:
        logger.info("Flywheel: daily cap reached (%d/%d)", daily, DAILY_CAP)
        conn.close()
        results["daily_total"] = daily
        return results

    # Process opens — bundles with first open that haven't been flywheel-processed
    open_bundles = conn.execute("""
        SELECT b.id, b.notes FROM outreach_bundles b
        WHERE b.open_count > 0
        AND b.status IN ('sent', 'replied')
        AND (b.notes IS NULL OR b.notes NOT LIKE '%flywheel_processed%')
        ORDER BY b.first_opened_at DESC
        LIMIT ?
    """, (limit,)).fetchall()

    conn.close()  # Close before calling on_email_opened (it opens its own conn)

    for bundle in open_bundles:
        created = on_email_opened(bundle["id"])
        results["new_contacts"] += created
        results["opens_processed"] += 1

        # Mark as processed
        mark_conn = _get_conn()
        existing_notes = bundle["notes"] or ""
        new_notes = f"{existing_notes} | flywheel_processed:{date.today().isoformat()}"
        mark_conn.execute(
            "UPDATE outreach_bundles SET notes = ? WHERE id = ?",
            (new_notes.strip(" |"), bundle["id"]),
        )
        mark_conn.commit()
        mark_conn.close()

    # Process replies
    conn2 = _get_conn()
    reply_bundles = conn2.execute("""
        SELECT b.id, b.notes, b.reply_snippet FROM outreach_bundles b
        WHERE b.status = 'replied'
        AND (b.notes IS NULL OR b.notes NOT LIKE '%flywheel_processed%')
        ORDER BY b.updated_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn2.close()

    for bundle in reply_bundles:
        reply_body = bundle["reply_snippet"] or ""
        created = on_reply_received(bundle["id"], reply_body=reply_body)
        results["new_contacts"] += created
        results["replies_processed"] += 1

        mark_conn = _get_conn()
        existing_notes = bundle["notes"] or ""
        new_notes = f"{existing_notes} | flywheel_processed:{date.today().isoformat()}"
        mark_conn.execute(
            "UPDATE outreach_bundles SET notes = ? WHERE id = ?",
            (new_notes.strip(" |"), bundle["id"]),
        )
        mark_conn.commit()
        mark_conn.close()

    results["daily_total"] = _count_daily_flywheel(_get_conn())
    logger.info(
        "Flywheel batch: %d opens, %d replies processed → %d new contacts",
        results["opens_processed"], results["replies_processed"], results["new_contacts"],
    )
    return results


def get_flywheel_stats() -> dict:
    """Count contacts by flywheel source type."""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT csv_source, COUNT(*) as cnt
        FROM contacts
        WHERE csv_source LIKE 'flywheel_%' OR csv_source = 'donor_scrape'
        GROUP BY csv_source
    """).fetchall()
    conn.close()

    by_source = {r["csv_source"]: r["cnt"] for r in rows}
    total = sum(by_source.values())
    return {
        "total_generated": total,
        "by_source": by_source,
    }
