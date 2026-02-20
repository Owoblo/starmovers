"""Telegram Notifications — push notifications back to owner's chat.

Every system event pushes to Telegram. Owner replies to take action.

Notification types:
  - research_complete: GPT research finished for a field intel idea
  - positive_reply: Someone replied positively to an outreach email
  - pipeline_complete: Daily pipeline run finished
  - bounce_alert: Email bounced
  - hot_lead: Email opened 3+ times
  - daily_summary: Evening daily digest (8pm)
"""

import json
import logging
import sqlite3
from datetime import date

from outreach_engine.config import cfg

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _log_notification(chat_id: int | str, notification_type: str,
                      reference_id: int | None, message_text: str):
    """Log a sent notification for reply-context tracking."""
    try:
        conn = _get_conn()
        conn.execute("""
            INSERT INTO telegram_notifications
            (chat_id, notification_type, reference_id, message_text)
            VALUES (?, ?, ?, ?)
        """, (int(chat_id), notification_type, reference_id,
              message_text[:1000]))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to log notification: %s", e)


def _send(text: str, reply_markup: dict | None = None,
          notification_type: str = "", reference_id: int | None = None) -> bool:
    """Send a notification to the owner. Uses sync httpx."""
    chat_id = cfg.telegram_chat_id
    if not chat_id or not cfg.telegram_bot_token:
        return False

    from outreach_engine.telegram_bot import send_message_sync_safe
    result = send_message_sync_safe(
        chat_id, text, reply_markup=reply_markup,
    )

    if result and result.get("ok"):
        _log_notification(chat_id, notification_type, reference_id, text)
        return True

    return False


# ── Research Complete ──

def notify_research_complete(idea_id: int, company_name: str,
                             research: dict):
    """Push research results to Telegram after GPT research completes."""
    company_type = research.get("company_type", "unknown")
    strategy = research.get("approach_strategy", "unknown")
    angles = research.get("angles", [])
    target_contacts = research.get("target_contacts", [])

    lines = [
        f"*[RESEARCH DONE]* {company_name}",
        f"Type: {company_type} | Strategy: {strategy}",
    ]

    if target_contacts:
        target = target_contacts[0] if isinstance(target_contacts, list) else {}
        if isinstance(target, dict):
            lines.append(f"Target: {target.get('role', 'unknown')}")

    if angles and isinstance(angles, list):
        lines.append("\nTalking points:")
        for a in angles[:3]:
            lines.append(f"\u2022 {a}")

    risks = research.get("risks", "")
    if risks:
        lines.append(f"\nWatch out: {risks[:150]}")

    buttons = {"inline_keyboard": [[
        {"text": "Advance Stage", "callback_data": f"advance_{idea_id}"},
        {"text": "View Full", "callback_data": f"idea_view_{idea_id}"},
    ]]}

    _send(
        "\n".join(lines),
        reply_markup=buttons,
        notification_type="research_complete",
        reference_id=idea_id,
    )


# ── Positive Reply ──

def notify_positive_reply(bundle_id: int, company_name: str,
                          contact_name: str, email: str,
                          reply_snippet: str = ""):
    """Push urgent notification when someone replies positively."""
    lines = [
        f"*[POSITIVE REPLY]* {company_name} replied:",
        f'"{reply_snippet[:200]}"' if reply_snippet else "(no preview)",
        f"Contact: {contact_name} | {email}",
    ]

    _send(
        "\n".join(lines),
        notification_type="positive_reply",
        reference_id=bundle_id,
    )


# ── Pipeline Complete ──

def notify_pipeline_complete(stats: dict):
    """Push pipeline summary after daily run completes."""
    sent = stats.get("sent", 0)
    generated = stats.get("generated", 0)
    discovered = stats.get("discovered", 0)
    opens = stats.get("opens_today", 0)
    replies = stats.get("replies", 0)

    lines = [
        f"*[PIPELINE COMPLETE]* Daily run finished",
        f"{sent} sent | {generated} generated | {discovered} discovered",
    ]

    if opens:
        lines.append(f"{opens} opened today")
    if replies:
        lines.append(f"{replies} replies")

    queued = stats.get("queued_tomorrow", 0)
    if queued:
        lines.append(f"{queued} queued for tomorrow")

    attention = stats.get("needs_attention", 0)
    if attention:
        lines.append(f"\n{attention} need attention")

    _send(
        "\n".join(lines),
        notification_type="pipeline_complete",
        reference_id=None,
    )


# ── Bounce Alert ──

def notify_bounce(bundle_id: int, company_name: str, email: str):
    """Push alert when an email bounces."""
    _send(
        f"*[BOUNCE]* {company_name}\n"
        f"Email bounced: {email}\n"
        f"Recovery in progress (team scrape + rediscovery)",
        notification_type="bounce_alert",
        reference_id=bundle_id,
    )


# ── Hot Lead ──

def notify_hot_lead(bundle_id: int, company_name: str,
                    contact_name: str, open_count: int):
    """Push alert when someone opens an email 3+ times."""
    _send(
        f"*[HOT LEAD]* {company_name}\n"
        f"{contact_name} opened your email {open_count} times!\n"
        f"Consider a follow-up call.",
        notification_type="hot_lead",
        reference_id=bundle_id,
    )


# ── Daily Summary (8pm push) ──

def send_daily_summary():
    """Build and send the 8pm daily digest.

    Called by APScheduler at configured hour (default 8pm).
    """
    from outreach_engine import queue_manager

    today = date.today().isoformat()
    stats = queue_manager.get_stats()
    ideas = queue_manager.get_ideas(limit=100)

    today_ideas = [i for i in ideas
                   if i.get("created_at", "").startswith(today)]

    sent = stats.get("emails_sent", 0)
    opens = stats.get("unique_opens", 0)
    open_rate = stats.get("open_rate", 0)
    replied = stats.get("total_replied", 0)
    queued = stats.get("total_queued", 0)

    lines = [f"*Saturn Star Daily \u2014 {today}*\n"]

    if today_ideas:
        lines.append(f"{len(today_ideas)} ideas submitted today")
    lines.append(f"{sent} emails sent ({opens} opened, {open_rate}% rate)")
    if replied:
        lines.append(f"{replied} replies received")

    # Ideas needing attention
    needs = []
    for idea in ideas:
        if idea["research_status"] == "researched":
            needs.append(f"\u2022 {idea['company_name']} \u2014 research ready")
        elif idea["research_status"] == "active":
            stages = idea.get("stages_json", [])
            if isinstance(stages, str):
                try:
                    stages = json.loads(stages)
                except (json.JSONDecodeError, TypeError):
                    stages = []
            current = idea.get("current_stage", 0)
            if 0 < current <= len(stages):
                stage = stages[current - 1]
                if stage.get("action") == "find_contacts":
                    needs.append(
                        f"\u2022 {idea['company_name']} \u2014 needs contact info")
                elif stage.get("action") == "outreach":
                    needs.append(
                        f"\u2022 {idea['company_name']} \u2014 outreach ready")

    if needs:
        lines.append("\n*NEEDS YOU:*")
        lines.extend(needs[:5])

    if queued:
        lines.append(f"\n{queued} queued for tomorrow")

    _send(
        "\n".join(lines),
        notification_type="daily_summary",
        reference_id=None,
    )
    logger.info("Daily summary sent to Telegram")


# ── Stuck-Stage Checker ──

def check_stuck_stages():
    """Scan active ideas for stuck stages and ping the owner.

    Called by APScheduler every 4 hours. Checks for:
      - research complete but not reviewed (1+ day)
      - find_contacts stage stuck 2+ days (needs user input)
      - outreach stage ready but not approved (1+ day)
      - any stage stuck 5+ days (general nudge)

    Only pings once per idea per day to avoid spam.
    """
    from outreach_engine import queue_manager
    from datetime import datetime, timedelta

    ideas = queue_manager.get_ideas(limit=200)
    now = datetime.now()
    today = date.today().isoformat()
    nudges = []

    # Check what we already pinged today (avoid duplicate nags)
    conn = _get_conn()
    already_pinged = set()
    rows = conn.execute("""
        SELECT reference_id FROM telegram_notifications
        WHERE notification_type = 'stuck_stage'
        AND DATE(sent_at) = ?
    """, (today,)).fetchall()
    conn.close()
    for r in rows:
        if r["reference_id"]:
            already_pinged.add(r["reference_id"])

    for idea in ideas:
        idea_id = idea["id"]
        if idea_id in already_pinged:
            continue

        status = idea["research_status"]
        updated = idea.get("updated_at", "")
        company = idea["company_name"]

        # Parse updated_at
        try:
            updated_dt = datetime.fromisoformat(updated) if updated else now
        except (ValueError, TypeError):
            updated_dt = now

        days_stuck = (now - updated_dt).days

        stages = idea.get("stages_json", [])
        if isinstance(stages, str):
            try:
                stages = json.loads(stages)
            except (json.JSONDecodeError, TypeError):
                stages = []

        current = idea.get("current_stage", 0)
        current_stage = stages[current - 1] if 0 < current <= len(stages) else {}
        action = current_stage.get("action", "")
        stage_title = current_stage.get("title", "")

        # Rule 1: Research done but not reviewed (1+ day)
        if status == "researched" and days_stuck >= 1:
            nudges.append({
                "id": idea_id,
                "company": company,
                "msg": f"Research ready for *{company}* ({days_stuck}d ago)\nReview and advance to next stage.",
                "action": "advance",
            })

        # Rule 2: find_contacts stage stuck 2+ days
        elif status == "active" and action == "find_contacts" and days_stuck >= 2:
            target = current_stage.get("target_role", "decision maker")
            nudges.append({
                "id": idea_id,
                "company": company,
                "msg": f"*{company}* needs contact info ({days_stuck}d stuck)\nLooking for: {target}",
                "action": "add_contact",
            })

        # Rule 3: outreach ready but not sent (1+ day)
        elif status == "active" and action == "outreach" and days_stuck >= 1:
            nudges.append({
                "id": idea_id,
                "company": company,
                "msg": f"Outreach email ready for *{company}* ({days_stuck}d)\nApprove to send.",
                "action": "advance",
            })

        # Rule 4: any stage stuck 5+ days (general nudge)
        elif status == "active" and days_stuck >= 5:
            nudges.append({
                "id": idea_id,
                "company": company,
                "msg": f"*{company}* stuck at Stage {current}: {stage_title} ({days_stuck}d)\nNeed to move this forward?",
                "action": "advance",
            })

    if not nudges:
        logger.info("Stuck-stage check: nothing stuck")
        return

    # Send grouped notification
    if len(nudges) == 1:
        n = nudges[0]
        buttons = {"inline_keyboard": [[
            {"text": "Advance Stage", "callback_data": f"advance_{n['id']}"},
            {"text": "View", "callback_data": f"idea_view_{n['id']}"},
        ]]}
        _send(
            f"[NEEDS ATTENTION]\n{n['msg']}",
            reply_markup=buttons,
            notification_type="stuck_stage",
            reference_id=n["id"],
        )
    else:
        lines = [f"*[NEEDS ATTENTION]* {len(nudges)} ideas stuck:\n"]
        for n in nudges[:8]:
            lines.append(f"\u2022 {n['msg']}")
        _send(
            "\n".join(lines),
            notification_type="stuck_stage",
            reference_id=nudges[0]["id"],
        )

    logger.info("Stuck-stage check: pinged %d ideas", len(nudges))


# ── Needs Manual ──

def notify_needs_manual(contact_id: int, company_name: str,
                        contact_name: str = "", reason: str = ""):
    """Push notification when automated discovery exhausts all methods.

    Flags the contact for manual email research (LinkedIn, phone call, etc).
    """
    lines = [
        f"*[NEEDS MANUAL]* {company_name}",
        f"Contact: {contact_name or 'Unknown'}",
        f"Automated email discovery exhausted all methods.",
    ]
    if reason:
        lines.append(f"Reason: {reason}")
    lines.append("Action: Find email via LinkedIn, phone call, or website research.")

    _send(
        "\n".join(lines),
        notification_type="needs_manual",
        reference_id=contact_id,
    )
