"""Hunter.io enrichment — find decision-maker emails + LinkedIn for commercial targets.

Free plan: 50 searches + 100 verifications per month.
Strategy: use only for high-value targets (Tier A, field intel, manual requests).

Endpoints used:
  - Domain Search: all emails at a domain (1 search credit)
  - Email Finder:  specific person's email by name + domain (1 search credit)
  - Email Verifier: deliverability check (1 verification credit)
"""

import logging
import sqlite3
from datetime import date, datetime

import requests

from outreach_engine.config import cfg

logger = logging.getLogger(__name__)

_BASE = "https://api.hunter.io/v2"
_TIMEOUT = 12


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Usage tracking ──


def _log_usage(endpoint: str, domain: str, credits_used: int, detail: str = ""):
    """Log Hunter API call for usage tracking."""
    try:
        conn = _get_conn()
        conn.execute("""
            INSERT INTO hunter_usage_log (endpoint, domain, credits_used, detail)
            VALUES (?, ?, ?, ?)
        """, (endpoint, domain, credits_used, detail))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("Hunter usage log failed: %s", e)


def get_usage_today() -> dict:
    """Get today's Hunter API usage."""
    conn = _get_conn()
    today = date.today().isoformat()
    rows = conn.execute("""
        SELECT endpoint, SUM(credits_used) as used
        FROM hunter_usage_log
        WHERE DATE(created_at) = ?
        GROUP BY endpoint
    """, (today,)).fetchall()
    conn.close()
    return {r["endpoint"]: r["used"] for r in rows}


def get_usage_month() -> dict:
    """Get this month's Hunter API usage."""
    conn = _get_conn()
    month_start = date.today().replace(day=1).isoformat()
    rows = conn.execute("""
        SELECT endpoint, SUM(credits_used) as used, COUNT(*) as calls
        FROM hunter_usage_log
        WHERE DATE(created_at) >= ?
        GROUP BY endpoint
    """, (month_start,)).fetchall()
    conn.close()
    return {r["endpoint"]: {"credits": r["used"], "calls": r["calls"]} for r in rows}


def check_budget() -> dict:
    """Check remaining Hunter credits for the month."""
    if not cfg.hunter_api_key:
        return {"available": False, "reason": "No API key configured"}

    try:
        r = requests.get(f"{_BASE}/account",
                         params={"api_key": cfg.hunter_api_key}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return {"available": False, "reason": f"API error {r.status_code}"}

        data = r.json()["data"]
        searches = data["requests"]["searches"]
        verifications = data["requests"]["verifications"]
        return {
            "available": True,
            "searches_used": searches["used"],
            "searches_available": searches["available"],
            "searches_remaining": searches["available"] - searches["used"],
            "verifications_used": verifications["used"],
            "verifications_available": verifications["available"],
            "verifications_remaining": verifications["available"] - verifications["used"],
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}


# ── Domain Search ──


def domain_search(domain: str, limit: int = 10) -> dict:
    """Find all emails associated with a domain.

    Returns {
        organization, domain, emails: [{email, first_name, last_name,
            position, department, linkedin, confidence, sources}],
        total_results, credits_used
    }
    """
    if not cfg.hunter_api_key:
        return {"error": "No Hunter API key configured"}

    try:
        r = requests.get(f"{_BASE}/domain-search", params={
            "api_key": cfg.hunter_api_key,
            "domain": domain,
            "limit": limit,
        }, timeout=_TIMEOUT)

        if r.status_code == 401:
            return {"error": "Invalid API key"}
        if r.status_code == 429:
            return {"error": "Rate limited — try again later"}
        if r.status_code != 200:
            return {"error": f"API error {r.status_code}: {r.text[:200]}"}

        data = r.json()["data"]
        emails = []
        for em in data.get("emails", []):
            emails.append({
                "email": em["value"],
                "first_name": em.get("first_name", ""),
                "last_name": em.get("last_name", ""),
                "position": em.get("position", ""),
                "department": em.get("department", ""),
                "linkedin": em.get("linkedin_url") or em.get("linkedin", ""),
                "confidence": em.get("confidence", 0),
                "sources": len(em.get("sources", [])),
            })

        _log_usage("domain_search", domain, 1,
                    f"{len(emails)} emails found")

        return {
            "organization": data.get("organization", ""),
            "domain": domain,
            "emails": emails,
            "total_results": data.get("meta", {}).get("results", len(emails)),
            "credits_used": 1,
        }

    except requests.Timeout:
        return {"error": "Request timed out"}
    except Exception as e:
        logger.error("Hunter domain search failed for %s: %s", domain, e)
        return {"error": str(e)}


# ── Email Finder ──


def find_email(domain: str, first_name: str, last_name: str) -> dict:
    """Find a specific person's email at a domain.

    Returns {
        email, score, position, department, linkedin,
        company, sources, credits_used
    }
    """
    if not cfg.hunter_api_key:
        return {"error": "No Hunter API key configured"}

    try:
        r = requests.get(f"{_BASE}/email-finder", params={
            "api_key": cfg.hunter_api_key,
            "domain": domain,
            "first_name": first_name,
            "last_name": last_name,
        }, timeout=_TIMEOUT)

        if r.status_code != 200:
            return {"error": f"API error {r.status_code}: {r.text[:200]}"}

        data = r.json()["data"]
        email = data.get("email", "")
        if not email:
            _log_usage("email_finder", domain, 1,
                        f"no result for {first_name} {last_name}")
            return {"email": "", "found": False}

        _log_usage("email_finder", domain, 1,
                    f"{email} ({data.get('score', 0)})")

        return {
            "email": email,
            "found": True,
            "score": data.get("score", 0),
            "position": data.get("position", ""),
            "department": data.get("department", ""),
            "linkedin": data.get("linkedin_url", ""),
            "company": data.get("company", ""),
            "sources": len(data.get("sources", [])),
            "credits_used": 1,
        }

    except Exception as e:
        logger.error("Hunter email finder failed: %s", e)
        return {"error": str(e)}


# ── Email Verifier ──


def verify_email(email: str) -> dict:
    """Verify if an email is deliverable.

    Returns {
        email, result (deliverable/undeliverable/risky/unknown),
        score, smtp_check, mx_records, credits_used
    }
    """
    if not cfg.hunter_api_key:
        return {"error": "No Hunter API key configured"}

    try:
        r = requests.get(f"{_BASE}/email-verifier", params={
            "api_key": cfg.hunter_api_key,
            "email": email,
        }, timeout=_TIMEOUT)

        if r.status_code != 200:
            return {"error": f"API error {r.status_code}: {r.text[:200]}"}

        data = r.json()["data"]

        domain = email.split("@")[-1] if "@" in email else ""
        _log_usage("email_verifier", domain, 1,
                    f"{email} → {data.get('result', '?')} ({data.get('score', 0)})")

        return {
            "email": data.get("email", email),
            "result": data.get("result", "unknown"),
            "score": data.get("score", 0),
            "smtp_check": data.get("smtp_check", False),
            "mx_records": data.get("mx_records", False),
            "disposable": data.get("disposable", False),
            "webmail": data.get("webmail", False),
            "credits_used": 1,
        }

    except Exception as e:
        logger.error("Hunter verify failed for %s: %s", email, e)
        return {"error": str(e)}


# ── High-level: Enrich a commercial account ──


def enrich_account(contact_id: int) -> dict:
    """Full Hunter enrichment for a commercial account.

    Steps:
    1. Domain search — find all people at the company
    2. Match/store decision makers with titles, emails, LinkedIn
    3. Verify the best email
    4. Update contact record with enriched data

    Returns summary of what was found.
    """
    conn = _get_conn()
    contact = conn.execute("SELECT * FROM contacts WHERE id = ?",
                           (contact_id,)).fetchone()
    if not contact:
        conn.close()
        return {"error": "Contact not found"}

    domain = contact["domain"]
    if not domain:
        conn.close()
        return {"error": "No domain on contact — add a website first"}

    company = contact["company_name"]
    contact_name = contact["contact_name"]

    # Step 1: Domain search
    search_result = domain_search(domain, limit=10)
    if "error" in search_result:
        conn.close()
        return search_result

    hunter_emails = search_result.get("emails", [])
    if not hunter_emails:
        conn.close()
        return {
            "contact_id": contact_id,
            "company": company,
            "domain": domain,
            "found": 0,
            "message": "No emails found on Hunter for this domain",
        }

    # Step 2: Find the best decision-maker email
    # Priority: people with titles matching decision-maker roles
    _DM_KEYWORDS = [
        "owner", "president", "ceo", "founder", "director",
        "manager", "vp", "vice president", "partner", "principal",
        "operations", "facilities", "office manager", "general manager",
        "procurement", "purchasing", "hr", "human resources",
    ]

    decision_makers = []
    generic_emails = []

    for em in hunter_emails:
        position = (em.get("position") or "").lower()
        has_name = bool(em.get("first_name") and em.get("last_name"))

        if has_name and any(kw in position for kw in _DM_KEYWORDS):
            decision_makers.append(em)
        elif has_name:
            decision_makers.append(em)  # Named person, even without matching title
        else:
            generic_emails.append(em)

    # Sort: titled decision makers first, then by confidence
    decision_makers.sort(
        key=lambda e: (
            any(kw in (e.get("position") or "").lower() for kw in _DM_KEYWORDS),
            e.get("confidence", 0),
        ),
        reverse=True,
    )

    # Pick the best candidate
    best = decision_makers[0] if decision_makers else (
        generic_emails[0] if generic_emails else None
    )

    if not best:
        conn.close()
        return {
            "contact_id": contact_id,
            "company": company,
            "domain": domain,
            "found": len(hunter_emails),
            "message": "Emails found but no decision makers identified",
        }

    best_email = best["email"]
    best_name = f"{best.get('first_name', '')} {best.get('last_name', '')}".strip()
    best_position = best.get("position", "")
    best_linkedin = best.get("linkedin", "")

    # Step 3: Verify the best email
    verification = verify_email(best_email)
    hunter_status = verification.get("result", "unknown")

    # Map Hunter result to our email_status
    status_map = {
        "deliverable": "verified",
        "risky": "likely",
        "unknown": "likely",
        "undeliverable": "invalid",
    }
    our_status = status_map.get(hunter_status, "likely")

    # Step 4: Update contact record
    updates = {
        "discovered_email": best_email,
        "email_status": our_status,
    }
    if best_name and not contact["contact_name"]:
        updates["contact_name"] = best_name
    if best_position and not contact["title_role"]:
        updates["title_role"] = best_position
    if best_linkedin:
        updates["linkedin_url"] = best_linkedin

    # Build notes about all people found
    people_notes = []
    for em in decision_makers[:5]:
        name = f"{em.get('first_name', '')} {em.get('last_name', '')}".strip()
        pos = em.get("position", "")
        li = em.get("linkedin", "")
        line = f"{name} — {em['email']}"
        if pos:
            line += f" ({pos})"
        if li:
            line += f" [LinkedIn: {li}]"
        people_notes.append(line)

    hunter_notes = f"[Hunter.io {date.today().isoformat()}] Found {len(hunter_emails)} emails.\n"
    if people_notes:
        hunter_notes += "Decision makers:\n" + "\n".join(f"  - {p}" for p in people_notes)

    # Append to existing notes
    existing_notes = contact["notes"] or ""
    if existing_notes:
        updates["notes"] = existing_notes + "\n\n" + hunter_notes
    else:
        updates["notes"] = hunter_notes

    updates["decision_maker_found"] = 1 if decision_makers else 0
    updates["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE contacts SET {set_clause} WHERE id = ?",
        (*updates.values(), contact_id),
    )

    # Log touch
    conn.execute("""
        INSERT INTO touch_log (contact_id, channel, direction, subject, notes,
                               outcome, logged_by, touch_date)
        VALUES (?, 'research', 'internal', 'Hunter.io enrichment', ?, 'enriched',
                'hunter_api', ?)
    """, (contact_id, hunter_notes, date.today().isoformat()))

    conn.commit()
    conn.close()

    logger.info("Hunter enrichment for #%d (%s): found %d emails, best=%s (%s)",
                contact_id, company, len(hunter_emails), best_email, our_status)

    return {
        "contact_id": contact_id,
        "company": company,
        "domain": domain,
        "found": len(hunter_emails),
        "decision_makers": len(decision_makers),
        "best_email": best_email,
        "best_name": best_name,
        "best_position": best_position,
        "best_linkedin": best_linkedin,
        "email_verified": our_status,
        "hunter_score": verification.get("score", 0),
        "all_people": [
            {
                "name": f"{em.get('first_name', '')} {em.get('last_name', '')}".strip(),
                "email": em["email"],
                "position": em.get("position", ""),
                "linkedin": em.get("linkedin", ""),
                "confidence": em.get("confidence", 0),
            }
            for em in decision_makers[:10]
        ],
        "credits_used": {"searches": 1, "verifications": 1},
    }


# ── Batch: enrich top priority accounts ──


def enrich_batch(limit: int = 5, min_tier: str = "A") -> list[dict]:
    """Enrich a batch of high-priority accounts that lack decision-maker emails.

    Only targets contacts with:
    - domain set
    - no verified email yet
    - tier A (or specified)
    - not already enriched via Hunter
    """
    conn = _get_conn()
    tiers = ["A"] if min_tier == "A" else ["A", "B"]
    placeholders = ",".join("?" * len(tiers))

    rows = conn.execute(f"""
        SELECT id, company_name, domain FROM contacts
        WHERE domain != ''
        AND email_status IN ('pending', 'unknown', 'likely')
        AND tier IN ({placeholders})
        AND account_status NOT IN ('dnc', 'explicit-no')
        AND notes NOT LIKE '%Hunter.io%'
        ORDER BY priority_score DESC, confidence_score DESC
        LIMIT ?
    """, (*tiers, limit)).fetchall()
    conn.close()

    results = []
    for row in rows:
        result = enrich_account(row["id"])
        results.append(result)
        logger.info("Batch enriched #%d (%s): %s",
                     row["id"], row["company_name"],
                     result.get("best_email", "no result"))

    return results
