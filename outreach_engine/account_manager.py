"""Account manager — confidence scoring, status lifecycle, automated enforcement.

Handles:
  - Dynamic 0-100 confidence scoring based on 10 weighted factors
  - Account status transitions (cold → contacted → engaged → qualified → partnered)
  - Revisit/DNC enforcement
  - Integration hooks for email_sender and followup_engine
"""

import logging
import sqlite3
from datetime import date, datetime, timedelta

from outreach_engine.config import cfg

logger = logging.getLogger(__name__)

# Valid account status transitions
VALID_TRANSITIONS = {
    "cold": {"contacted", "revisit", "dnc"},
    "contacted": {"engaged", "revisit", "dnc"},
    "engaged": {"qualified", "revisit", "dnc"},
    "qualified": {"partnered", "revisit", "dnc"},
    "partnered": {"revisit", "dnc"},
    "revisit": {"cold", "dnc"},
}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def compute_confidence_score(contact_id: int) -> int:
    """Compute dynamic 0-100 confidence score for a contact.

    Returns the score and updates it in the DB.
    """
    conn = _get_conn()
    row = conn.execute("""
        SELECT c.*,
            (SELECT COUNT(*) FROM news_signals ns
             WHERE ns.contact_id = c.id AND ns.status != 'dismissed') as signal_count,
            (SELECT COUNT(*) FROM outreach_bundles ob
             WHERE ob.contact_id = c.id AND ob.open_count > 0) as has_opens,
            (SELECT MAX(ob.sent_at) FROM outreach_bundles ob
             WHERE ob.contact_id = c.id AND ob.status = 'sent') as last_sent
        FROM contacts c WHERE c.id = ?
    """, (contact_id,)).fetchone()

    if not row:
        conn.close()
        return 0

    w = cfg.confidence_weights
    score = 0

    # Email verified (+20) or likely (+10)
    email_status = row["email_status"] or ""
    if email_status == "verified":
        score += w["email_verified"]
    elif email_status == "likely":
        score += w["email_likely"]

    # Decision maker found (+15)
    if row["decision_maker_found"] or (row["contact_name"] and row["title_role"]):
        score += w["decision_maker_found"]

    # Website exists (+10)
    if row["website"]:
        score += w["website_exists"]

    # Phone exists (+10)
    if row["phone"]:
        score += w["phone_exists"]

    # High-value tier (+10)
    tier = row["tier"] or ""
    if tier in ("A", "HOT"):
        score += w["high_value_tier"]

    # Has news signal (+10)
    if row["signal_count"] and row["signal_count"] > 0:
        score += w["has_news_signal"]

    # Account engaged or better (+10)
    account_status = row["account_status"] or "cold"
    if account_status in ("engaged", "qualified", "partnered"):
        score += w["account_engaged"]

    # Previously had opens (+5)
    if row["has_opens"] and row["has_opens"] > 0:
        score += w["has_opens"]

    # Recent activity within 30 days (+10)
    last_sent = row["last_sent"]
    if last_sent:
        try:
            sent_date = datetime.fromisoformat(last_sent)
            if (datetime.now() - sent_date).days <= 30:
                score += w["recent_activity"]
        except (ValueError, TypeError):
            pass

    # Clamp to 0-100
    score = max(0, min(100, score))

    # Update in DB
    conn.execute(
        "UPDATE contacts SET confidence_score = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (score, contact_id),
    )
    conn.commit()
    conn.close()
    return score


def batch_recalculate_confidence() -> int:
    """Recalculate confidence scores for all non-DNC contacts.

    Returns count of contacts updated.
    """
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id FROM contacts WHERE account_status != 'dnc'"
    ).fetchall()
    conn.close()

    count = 0
    for row in rows:
        compute_confidence_score(row["id"])
        count += 1

    logger.info("Recalculated confidence for %d contacts", count)
    return count


def transition_account_status(contact_id: int, new_status: str,
                              notes: str = "") -> dict:
    """Transition a contact's account status with validation.

    Returns {success, old_status, new_status, error}.
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT account_status FROM contacts WHERE id = ?", (contact_id,)
    ).fetchone()

    if not row:
        conn.close()
        return {"success": False, "error": "Contact not found"}

    old_status = row["account_status"] or "cold"

    # DNC is permanent
    if old_status == "dnc":
        conn.close()
        return {"success": False, "error": "Contact is DNC — permanent, cannot transition",
                "old_status": old_status, "new_status": new_status}

    # Validate transition
    allowed = VALID_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        conn.close()
        return {"success": False,
                "error": f"Invalid transition: {old_status} → {new_status}. "
                         f"Allowed: {', '.join(sorted(allowed))}",
                "old_status": old_status, "new_status": new_status}

    updates = {
        "account_status": new_status,
        "last_touch_date": date.today().isoformat(),
    }

    # Set next_action_date for revisit
    if new_status == "revisit":
        days = cfg.revisit_no_reply_days
        updates["next_action_date"] = (
            date.today() + timedelta(days=days)
        ).isoformat()
        updates["next_action"] = "revisit_expiry"

    if new_status == "dnc":
        updates["next_action_date"] = ""
        updates["next_action"] = "permanent_dnc"

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [contact_id]
    conn.execute(
        f"UPDATE contacts SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        params,
    )

    # Log the touch
    conn.execute("""
        INSERT INTO touch_log (contact_id, channel, direction, subject, notes, touch_date)
        VALUES (?, 'email', 'outbound', ?, ?, ?)
    """, (contact_id, f"Status: {old_status} → {new_status}",
          notes, date.today().isoformat()))

    conn.commit()
    conn.close()

    # Recalculate confidence after status change
    compute_confidence_score(contact_id)

    return {"success": True, "old_status": old_status, "new_status": new_status}


def mark_dnc(contact_id: int, reason: str = "") -> dict:
    """Mark a contact as DNC (permanent)."""
    return transition_account_status(contact_id, "dnc", notes=reason)


def enforce_revisit_expiry() -> int:
    """Move expired revisit contacts back to cold.

    Returns count of contacts reactivated.
    """
    conn = _get_conn()
    today = date.today().isoformat()
    rows = conn.execute("""
        SELECT id FROM contacts
        WHERE account_status = 'revisit'
        AND next_action_date != ''
        AND next_action_date <= ?
    """, (today,)).fetchall()
    conn.close()

    count = 0
    for row in rows:
        result = transition_account_status(row["id"], "cold",
                                           notes="Revisit expired — reactivated")
        if result.get("success"):
            count += 1

    if count:
        logger.info("Reactivated %d expired revisit contacts", count)
    return count


def enforce_no_reply_revisit() -> int:
    """Park contacts with 3+ unanswered email touches into revisit.

    Returns count of contacts parked.
    """
    conn = _get_conn()
    # Find contacts in contacted status with 3+ outbound email touches
    # and no inbound touches
    rows = conn.execute("""
        SELECT c.id, c.account_status,
            (SELECT COUNT(*) FROM touch_log t
             WHERE t.contact_id = c.id AND t.channel = 'email'
             AND t.direction = 'outbound') as outbound_count,
            (SELECT COUNT(*) FROM touch_log t
             WHERE t.contact_id = c.id
             AND t.direction = 'inbound') as inbound_count
        FROM contacts c
        WHERE c.account_status IN ('cold', 'contacted')
        AND c.account_status != 'dnc'
    """).fetchall()
    conn.close()

    count = 0
    for row in rows:
        if row["outbound_count"] >= 3 and row["inbound_count"] == 0:
            old = row["account_status"]
            # Need valid transition path
            if old == "cold":
                # cold → contacted → revisit (need intermediate)
                # Actually, just set it directly via DB since enforcement
                _conn = _get_conn()
                next_date = (date.today() + timedelta(days=cfg.revisit_no_reply_days)).isoformat()
                _conn.execute("""
                    UPDATE contacts
                    SET account_status = 'revisit',
                        next_action_date = ?,
                        next_action = 'no_reply_revisit',
                        last_touch_date = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (next_date, date.today().isoformat(), row["id"]))
                _conn.commit()
                _conn.close()
                count += 1
            elif old == "contacted":
                result = transition_account_status(
                    row["id"], "revisit",
                    notes="3 email touches with no reply — parked",
                )
                if result.get("success"):
                    # Override the next_action_date with no-reply timer
                    _conn = _get_conn()
                    next_date = (date.today() + timedelta(days=cfg.revisit_no_reply_days)).isoformat()
                    _conn.execute("""
                        UPDATE contacts
                        SET next_action_date = ?, next_action = 'no_reply_revisit'
                        WHERE id = ?
                    """, (next_date, row["id"]))
                    _conn.commit()
                    _conn.close()
                    count += 1

    if count:
        logger.info("Parked %d contacts to revisit (no reply after 3 touches)", count)
    return count


# ── Integration hooks (called from email_sender/followup_engine/sidecar) ──


def on_email_sent(contact_id: int, bundle_id: int = 0):
    """Hook: called after an email is sent. Transitions cold → contacted."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT account_status FROM contacts WHERE id = ?", (contact_id,)
    ).fetchone()
    conn.close()

    if not row:
        return

    current = row["account_status"] or "cold"
    if current == "cold":
        transition_account_status(contact_id, "contacted",
                                  notes=f"First email sent (bundle #{bundle_id})")

    # Log touch
    conn = _get_conn()
    conn.execute("""
        INSERT INTO touch_log (contact_id, channel, direction, subject, notes, touch_date)
        VALUES (?, 'email', 'outbound', 'Email sent', ?, ?)
    """, (contact_id, f"bundle_id={bundle_id}", date.today().isoformat()))
    conn.execute(
        "UPDATE contacts SET last_touch_date = ? WHERE id = ?",
        (date.today().isoformat(), contact_id),
    )
    conn.commit()
    conn.close()


def on_email_opened(contact_id: int, bundle_id: int = 0):
    """Hook: called on first email open. Transitions contacted → engaged."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT account_status FROM contacts WHERE id = ?", (contact_id,)
    ).fetchone()
    conn.close()

    if not row:
        return

    current = row["account_status"] or "cold"
    if current == "contacted":
        transition_account_status(contact_id, "engaged",
                                  notes=f"Email opened (bundle #{bundle_id})")


def on_reply_received(contact_id: int, sentiment: str = "",
                      bundle_id: int = 0):
    """Hook: called after reply is classified.

    Positive/neutral → engaged (or stays if already higher).
    Negative → revisit with 180-day timer.
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT account_status FROM contacts WHERE id = ?", (contact_id,)
    ).fetchone()
    conn.close()

    if not row:
        return

    current = row["account_status"] or "cold"

    if sentiment == "negative":
        # Move to revisit with longer timer
        if current != "dnc":
            _conn = _get_conn()
            next_date = (date.today() + timedelta(days=cfg.revisit_negative_days)).isoformat()
            _conn.execute("""
                UPDATE contacts
                SET account_status = 'revisit',
                    next_action_date = ?,
                    next_action = 'negative_reply_revisit',
                    last_touch_date = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (next_date, date.today().isoformat(), contact_id))
            _conn.commit()
            _conn.close()
    else:
        # Positive or neutral — engage
        if current in ("cold", "contacted"):
            new = "engaged" if current == "contacted" else "contacted"
            transition_account_status(contact_id, new,
                                      notes=f"Reply received ({sentiment})")
        elif current == "engaged":
            # Already engaged, just log
            pass

    # Log inbound touch
    conn = _get_conn()
    conn.execute("""
        INSERT INTO touch_log (contact_id, channel, direction, subject, notes, touch_date)
        VALUES (?, 'email', 'inbound', 'Reply received', ?, ?)
    """, (contact_id, f"sentiment={sentiment} bundle_id={bundle_id}",
          date.today().isoformat()))
    conn.commit()
    conn.close()


def on_followup_exhausted(contact_id: int):
    """Hook: called after 3rd follow-up sent. Parks contact to revisit."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT account_status FROM contacts WHERE id = ?", (contact_id,)
    ).fetchone()
    conn.close()

    if not row:
        return

    current = row["account_status"] or "cold"
    if current in ("cold", "contacted", "engaged") and current != "dnc":
        _conn = _get_conn()
        next_date = (date.today() + timedelta(days=cfg.revisit_no_reply_days)).isoformat()
        _conn.execute("""
            UPDATE contacts
            SET account_status = 'revisit',
                next_action_date = ?,
                next_action = 'followup_exhausted',
                last_touch_date = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (next_date, date.today().isoformat(), contact_id))
        _conn.commit()
        _conn.close()
        logger.info("Contact #%d parked to revisit (followup exhausted)", contact_id)


def run_account_maintenance():
    """Daily maintenance: recalculate scores, enforce revisits.

    Called by scheduler and daily pipeline.
    """
    logger.info("Account maintenance starting...")
    recalced = batch_recalculate_confidence()
    reactivated = enforce_revisit_expiry()
    parked = enforce_no_reply_revisit()
    logger.info("Account maintenance complete: %d recalced, %d reactivated, %d parked",
                recalced, reactivated, parked)
    return {
        "recalculated": recalced,
        "reactivated": reactivated,
        "parked": parked,
    }
