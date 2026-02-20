"""Daily pipeline orchestrator — discovers emails, generates bundles, sends approved ones.

Target: ~40 emails/day.

Autonomy features:
  - Pipeline run logging (every run tracked in pipeline_runs table)
  - Auto-approve mode (well-tested templates auto-approved)
  - Hard daily send cap (safety net)
  - Error recovery with retries (exponential backoff)
  - Follow-up engine (3-touch sequence)
  - DB backup on each run

Usage:
    python -m outreach_engine.daily_run                    # Full pipeline
    python -m outreach_engine.daily_run --discover-only    # Only discover emails
    python -m outreach_engine.daily_run --dry-run          # Generate bundles, don't send
    python -m outreach_engine.daily_run --send-only        # Only send approved bundles
"""

import argparse
import logging
import random
import time
import traceback
from datetime import date

from outreach_engine.config import cfg
from outreach_engine import queue_manager
from outreach_engine.email_discovery import discover_batch
from outreach_engine.template_engine import generate_email
from outreach_engine.email_sender import send_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Retry decorator ──

def _retry(func, max_retries: int = 3, base_delay: float = 5.0, step_name: str = ""):
    """Run func with exponential backoff retries. Returns func result or raises."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 2)
                logger.warning("  %s failed (attempt %d/%d): %s — retrying in %.0fs...",
                               step_name, attempt + 1, max_retries, e, delay)
                time.sleep(delay)
            else:
                logger.error("  %s failed after %d attempts: %s",
                             step_name, max_retries, e)
    raise last_error


def step_account_maintenance() -> dict:
    """Step 0c: Run account maintenance — recalculate confidence, enforce revisits."""
    logger.info("Step 0c: Running account maintenance...")
    try:
        from outreach_engine.account_manager import run_account_maintenance
        stats = run_account_maintenance()
        logger.info("  Account maintenance: %d recalced, %d reactivated, %d parked",
                     stats.get("recalculated", 0), stats.get("reactivated", 0),
                     stats.get("parked", 0))
        return stats
    except Exception as e:
        logger.warning("  Account maintenance failed: %s", e)
        return {}


def step_discover(limit: int = 60) -> int:
    """Step 1: Discover emails for pending contacts."""
    logger.info("Step 1: Discovering emails (up to %d contacts)...", limit)

    def _do():
        return discover_batch(limit)

    results = _retry(_do, max_retries=2, step_name="Email discovery")
    found = sum(1 for r in results if r["email"])
    logger.info("  Discovered %d/%d emails", found, len(results))
    queue_manager.update_daily_stats(
        date.today().isoformat(),
        contacts_discovered=len(results),
        emails_found=found,
    )
    return found


def step_verify_likely(limit: int = 50) -> dict:
    """Step 1.5: Batch-verify 'likely' emails via Hunter before bundle generation.

    Promotes likely → verified (or invalid) using available Hunter credits.
    This ensures we have verified contacts for the send queue.
    """
    logger.info("Step 1.5: Batch-verifying 'likely' emails via Hunter (up to %d)...", limit)
    try:
        from outreach_engine.hunter_enrichment import verify_batch_likely
        stats = verify_batch_likely(limit=limit)
        logger.info("  Verified: %d promoted, %d invalidated, %d unchanged (credits used: %d)",
                     stats.get("promoted", 0), stats.get("invalidated", 0),
                     stats.get("unchanged", 0), stats.get("credits_used", 0))
        return stats
    except Exception as e:
        logger.warning("  Batch verify failed: %s", e)
        return {}


def step_generate_bundles(batch_size: int = 40) -> int:
    """Step 2: Select contacts and generate email bundles."""
    logger.info("Step 2: Generating bundles (target: %d)...", batch_size)
    contact_ids = queue_manager.select_next_batch(batch_size)
    if not contact_ids:
        logger.info("  No eligible contacts found for bundle generation.")
        return 0

    today = date.today().isoformat()
    generated = 0

    for cid in contact_ids:
        try:
            def _gen(c=cid):
                return generate_email(c)
            subject, body = _retry(_gen, max_retries=2, step_name=f"Generate contact #{cid}")
            if subject and body:
                queue_manager.create_bundle(cid, today, subject, body)
                generated += 1
            else:
                logger.warning("  Empty email for contact %d, skipping", cid)
        except Exception as e:
            logger.error("  Failed to generate for contact %d: %s", cid, e)

    logger.info("  Generated %d bundles", generated)
    queue_manager.update_daily_stats(
        today, bundles_generated=generated,
    )
    return generated


def step_auto_approve() -> int:
    """Step 2.7: Auto-approve bundles for well-tested templates."""
    if not cfg.auto_approve:
        logger.info("Step 2.7: Auto-approve disabled")
        return 0
    logger.info("Step 2.7: Auto-approving eligible bundles...")
    count = queue_manager.auto_approve_bundles()
    logger.info("  Auto-approved %d bundles (skipping: %s)", count,
                ", ".join(cfg.manual_review_codes))
    return count


TARGET_VERIFIED = 30     # minimum bundles with verified/likely emails
MAX_BACKFILL_ROUNDS = 5  # max discovery+generate rounds
BACKFILL_BUFFER = 5      # discover extra to account for invalid emails


def _count_verified_bundles(batch_date: str) -> int:
    """Count bundles for a date that have verified or likely emails."""
    import sqlite3
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    row = conn.execute("""
        SELECT COUNT(*) as cnt
        FROM outreach_bundles b
        JOIN contacts c ON b.contact_id = c.id
        WHERE b.batch_date = ?
        AND b.status NOT IN ('skipped', 'bounced')
        AND c.email_status IN ('verified', 'likely')
    """, (batch_date,)).fetchone()
    conn.close()
    return row["cnt"]


def step_backfill(target: int = 40, max_rounds: int = MAX_BACKFILL_ROUNDS) -> int:
    """Step 3: Backfill until we have TARGET_VERIFIED bundles with good emails."""
    today = date.today().isoformat()
    existing = len(queue_manager.get_queue(today))
    verified = _count_verified_bundles(today)

    if existing >= target and verified >= TARGET_VERIFIED:
        logger.info("Step 3: Already at %d bundles (%d verified), no backfill needed.",
                     existing, verified)
        return 0

    total_added = 0
    for round_num in range(max_rounds):
        current_total = existing + total_added
        current_verified = _count_verified_bundles(today)

        if current_total >= target and current_verified >= TARGET_VERIFIED:
            break

        gap = max(target - current_total, TARGET_VERIFIED - current_verified)
        if gap <= 0:
            break

        logger.info("  Backfill round %d: need %d more (total=%d, verified=%d)...",
                     round_num + 1, gap, current_total, current_verified)

        # Discover more emails first — extra buffer for invalid ones
        discover_batch((gap + BACKFILL_BUFFER) * 2)

        # Try to generate more bundles
        contact_ids = queue_manager.select_next_batch(gap + BACKFILL_BUFFER)
        for cid in contact_ids:
            try:
                subject, body = generate_email(cid)
                if subject and body:
                    queue_manager.create_bundle(cid, today, subject, body)
                    total_added += 1
            except Exception:
                continue

    final_verified = _count_verified_bundles(today)
    logger.info("  Backfill complete: added %d bundles (now %d verified)",
                total_added, final_verified)
    return total_added


def step_send_approved() -> tuple[int, int]:
    """Step 4: Send approved bundles with staggered timing + daily cap.

    Belt-and-suspenders: even if a bundle was approved, skip it if
    cfg.send_only_verified is True and the email isn't verified.
    Returns (sent_count, failed_count).
    """
    # Check daily send cap
    can_send, sent_today, max_sends = queue_manager.check_daily_send_cap()
    if not can_send:
        logger.warning("Step 4: Daily send cap reached (%d/%d) — skipping sends",
                       sent_today, max_sends)
        return 0, 0

    budget = queue_manager.remaining_send_budget()
    bundle_ids = queue_manager.get_pending_send_bundles()

    if not bundle_ids:
        logger.info("Step 4: No approved bundles to send.")
        return 0, 0

    # Cap to remaining budget
    bundle_ids = bundle_ids[:budget]
    logger.info("Step 4: Sending %d approved bundles (budget: %d/%d)...",
                len(bundle_ids), budget, max_sends)
    sent_count = 0
    failed_count = 0
    skipped_unverified = 0

    for bid in bundle_ids:
        bundle = queue_manager.get_bundle(bid)
        if not bundle:
            continue

        email_addr = bundle.get("discovered_email", "")
        if not email_addr:
            logger.warning("  Bundle %d: no email, skipping", bid)
            continue

        if bundle.get("email_status") == "invalid":
            logger.warning("  Bundle %d: email invalid, skipping", bid)
            continue

        # Belt-and-suspenders: verified-only gate
        if cfg.send_only_verified and bundle.get("email_status") != "verified":
            skipped_unverified += 1
            logger.warning("  Bundle %d: email_status='%s' (not verified), skipping — send_only_verified is ON",
                           bid, bundle.get("email_status"))
            continue

        import uuid
        tracking_id = str(uuid.uuid4())
        queue_manager.create_tracking(bid, tracking_id)

        def _send(addr=email_addr, b=bundle, tid=tracking_id):
            return send_email(addr, b["email_subject"], b["email_body"], tracking_id=tid)

        try:
            result = _retry(_send, max_retries=2, base_delay=3.0,
                            step_name=f"Send bundle #{bid}")
        except Exception as e:
            result = {"success": False, "error": str(e)}

        queue_manager.log_send(
            bid, email_addr,
            smtp_code=result.get("smtp_code", 0),
            error=result.get("error", ""),
        )

        if result.get("success"):
            queue_manager.mark_sent(bid, email_sent=True)
            sent_count += 1
            logger.info("  Sent bundle %d to %s", bid, email_addr)
        else:
            failed_count += 1
            logger.warning("  Failed bundle %d: %s", bid, result.get("error"))

        # Stagger: 10-25s between sends
        delay = random.randint(10, 25)
        logger.info("  Waiting %ds before next send...", delay)
        time.sleep(delay)

    if skipped_unverified:
        logger.info("  Skipped %d bundles (email not verified)", skipped_unverified)
    logger.info("  Sent %d/%d bundles (%d failed)", sent_count, len(bundle_ids), failed_count)
    queue_manager.update_daily_stats(
        date.today().isoformat(), bundles_sent=sent_count,
    )
    return sent_count, failed_count


def step_scan_replies() -> dict:
    """Step 0b: Scan IMAP for replies and classify them."""
    logger.info("Step 0b: Scanning for replies...")
    try:
        from outreach_engine.email_sender import process_replies

        def _do():
            return process_replies(days=7)

        stats = _retry(_do, max_retries=2, step_name="Reply scan")
        logger.info("  Replies: %d found, %d matched (%d positive, %d negative, %d auto, %d redirect)",
                     stats["found"], stats["matched"], stats.get("positive", 0),
                     stats.get("negative", 0), stats.get("auto_reply", 0),
                     stats.get("redirect", 0))
        return stats
    except Exception as e:
        logger.warning("  Reply scan failed: %s", e)
        return {}


def step_scan_bounces() -> int:
    """Step 0a: Scan IMAP for bounces."""
    logger.info("Step 0a: Scanning for bounces...")
    try:
        from outreach_engine.email_sender import scan_imap_bounces
        import sqlite3

        def _do():
            return scan_imap_bounces(days=3)

        bounced_emails = _retry(_do, max_retries=2, step_name="Bounce scan")
        if not bounced_emails:
            logger.info("  No bounces found")
            return 0

        conn = sqlite3.connect(str(cfg.db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        marked = 0
        for email_addr in bounced_emails:
            row = conn.execute("""
                SELECT b.id FROM outreach_bundles b
                JOIN contacts c ON b.contact_id = c.id
                WHERE c.discovered_email = ? AND b.status = 'sent'
                LIMIT 1
            """, (email_addr,)).fetchone()
            if row:
                queue_manager.mark_bounced(row["id"])
                marked += 1
        conn.close()
        logger.info("  Bounces: found %d bounced emails, marked %d bundles",
                     len(bounced_emails), marked)
        return marked

    except Exception as e:
        logger.warning("  Bounce scan failed: %s", e)
        return 0


def step_followups() -> dict:
    """Step 5.5: Schedule and send follow-up emails."""
    logger.info("Step 5.5: Running follow-up cycle...")
    try:
        from outreach_engine.followup_engine import run_followup_cycle
        stats = run_followup_cycle(limit=20)
        scheduled = stats.get("scheduled", {})
        sent = stats.get("sent", {})
        logger.info("  Follow-ups: scheduled %d nudge + %d closing, sent %d",
                     scheduled.get("scheduled_nudge", 0),
                     scheduled.get("scheduled_closing", 0),
                     sent.get("sent", 0))
        return stats
    except Exception as e:
        logger.warning("  Follow-up cycle failed: %s", e)
        return {}


def _build_sent_today_section() -> str:
    """Build detailed list of emails sent today."""
    import sqlite3
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    today = date.today().isoformat()

    rows = conn.execute("""
        SELECT b.id, b.email_subject, b.sent_at, b.open_count,
               c.company_name, c.contact_name, c.discovered_email,
               c.city, c.tier, c.confidence_score
        FROM outreach_bundles b
        JOIN contacts c ON b.contact_id = c.id
        WHERE b.status IN ('sent', 'replied') AND DATE(b.sent_at) = ?
        ORDER BY b.sent_at ASC
    """, (today,)).fetchall()
    conn.close()

    if not rows:
        return "  (none sent today)\n"

    lines = []
    for i, r in enumerate(rows, 1):
        name = r["contact_name"] or "Unknown"
        lines.append(
            f"  {i}. {r['company_name']} — {name}\n"
            f"     Email: {r['discovered_email']}\n"
            f"     Subject: {r['email_subject'][:60]}\n"
            f"     City: {r['city']} | Tier: {r['tier']} | Confidence: {r['confidence_score']}"
        )
    return "\n".join(lines) + "\n"


def _build_tomorrow_queue_section() -> str:
    """Build detailed list of bundles queued/approved for tomorrow."""
    import sqlite3
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT b.id, b.email_subject, b.status,
               c.company_name, c.contact_name, c.discovered_email,
               c.city, c.tier, c.confidence_score, c.email_status
        FROM outreach_bundles b
        JOIN contacts c ON b.contact_id = c.id
        WHERE b.status IN ('queued', 'approved')
        ORDER BY c.confidence_score DESC, c.priority_score DESC
    """).fetchall()
    conn.close()

    if not rows:
        return "  (none queued)\n"

    lines = []
    for i, r in enumerate(rows, 1):
        name = r["contact_name"] or "Unknown"
        status_tag = "AUTO-APPROVED" if r["status"] == "approved" else "QUEUED"
        email_tag = f"({r['email_status']})" if r["email_status"] != "verified" else "(verified)"
        lines.append(
            f"  {i}. [{status_tag}] {r['company_name']} — {name}\n"
            f"     Email: {r['discovered_email']} {email_tag}\n"
            f"     Subject: {r['email_subject'][:60]}\n"
            f"     City: {r['city']} | Tier: {r['tier']} | Confidence: {r['confidence_score']}"
        )
    return "\n".join(lines) + "\n"


def _build_needs_attention_section() -> str:
    """Build list of contacts that need human input.

    Includes: bounced (recovery failed), low confidence high-value,
    no decision maker found, stuck contacts.
    """
    import sqlite3
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row

    sections = []

    # 1. Bounced emails where recovery failed (no new email found)
    bounced = conn.execute("""
        SELECT c.id, c.company_name, c.contact_name, c.city, c.tier,
               c.bounce_count, c.bounced_emails, c.website,
               c.confidence_score
        FROM contacts c
        WHERE c.bounce_count > 0
        AND c.email_status IN ('bounced', 'invalid')
        AND c.account_status NOT IN ('dnc', 'revisit')
        ORDER BY c.tier ASC, c.bounce_count DESC
        LIMIT 15
    """).fetchall()

    if bounced:
        lines = ["  BOUNCED — Recovery Failed (need manual research):"]
        for r in bounced:
            bad_emails = r["bounced_emails"] or "unknown"
            lines.append(
                f"    • {r['company_name']} ({r['city']}) — Tier {r['tier']}\n"
                f"      Contact: {r['contact_name'] or 'Unknown'}\n"
                f"      Bounced {r['bounce_count']}x: {bad_emails}\n"
                f"      Website: {r['website'] or 'none'}\n"
                f"      → Need: correct email or new contact name/title"
            )
        sections.append("\n".join(lines))

    # 2. High-value contacts with low confidence (can't find enough info)
    low_conf = conn.execute("""
        SELECT c.id, c.company_name, c.contact_name, c.city, c.tier,
               c.confidence_score, c.email_status, c.discovered_email,
               c.website, c.phone, c.decision_maker_found
        FROM contacts c
        WHERE c.tier IN ('A', 'HOT')
        AND c.confidence_score < 40
        AND c.account_status NOT IN ('dnc', 'partnered')
        ORDER BY c.confidence_score ASC
        LIMIT 15
    """).fetchall()

    if low_conf:
        lines = ["\n  LOW CONFIDENCE — High-Value Accounts (need intel):"]
        for r in low_conf:
            missing = []
            if not r["discovered_email"]:
                missing.append("email")
            if not r["phone"]:
                missing.append("phone")
            if not r["website"]:
                missing.append("website")
            if not r["decision_maker_found"] and not r["contact_name"]:
                missing.append("decision maker")
            lines.append(
                f"    • {r['company_name']} ({r['city']}) — Tier {r['tier']}, Score: {r['confidence_score']}\n"
                f"      Contact: {r['contact_name'] or 'NONE FOUND'}\n"
                f"      Missing: {', '.join(missing) if missing else 'needs verification'}\n"
                f"      → Need: {', '.join(missing) if missing else 'verify contact info'}"
            )
        sections.append("\n".join(lines))

    # 3. Contacts stuck in contacted with multiple touches but no engagement
    stuck = conn.execute("""
        SELECT c.id, c.company_name, c.contact_name, c.city, c.tier,
               c.discovered_email, c.confidence_score, c.last_touch_date,
               (SELECT COUNT(*) FROM touch_log t
                WHERE t.contact_id = c.id AND t.direction = 'outbound') as touch_count
        FROM contacts c
        WHERE c.account_status = 'contacted'
        AND c.account_status != 'dnc'
        HAVING touch_count >= 2
        ORDER BY touch_count DESC
        LIMIT 10
    """).fetchall()

    if stuck:
        lines = ["\n  STUCK — Multiple Touches, No Engagement:"]
        for r in stuck:
            lines.append(
                f"    • {r['company_name']} ({r['city']}) — {r['touch_count']} touches\n"
                f"      Contact: {r['contact_name'] or 'Unknown'} | {r['discovered_email']}\n"
                f"      Last touch: {r['last_touch_date'] or 'unknown'}\n"
                f"      → Consider: phone call, LinkedIn, or different contact person"
            )
        sections.append("\n".join(lines))

    conn.close()

    if not sections:
        return "  All clear — no contacts need immediate attention.\n"

    return "\n".join(sections) + "\n"


def _build_account_board_summary() -> str:
    """Build account board status breakdown."""
    board_stats = queue_manager.get_account_board_stats()
    by_status = board_stats.get("by_status", {})

    status_order = ["cold", "contacted", "engaged", "qualified",
                    "partnered", "revisit", "dnc"]
    lines = []
    for s in status_order:
        info = by_status.get(s, {})
        count = info.get("count", 0)
        avg = info.get("avg_confidence", 0)
        if count > 0:
            lines.append(f"  {s.upper():12s} {count:>5d} contacts  (avg confidence: {avg})")

    lines.append(f"\n  High Confidence (>70):  {board_stats.get('high_confidence', 0)}")
    lines.append(f"  Needs Review (40-69):  {board_stats.get('needs_review', 0)}")
    lines.append(f"  Low Confidence (<40):  {board_stats.get('low_confidence', 0)}")

    return "\n".join(lines) + "\n"


def step_notify(discovered: int, generated: int, sent: int,
                reply_stats: dict | None = None, failed: int = 0,
                auto_approved: int = 0, followup_stats: dict | None = None,
                news_stats: dict | None = None,
                account_stats: dict | None = None):
    """Step 6: Send detailed notification email with full run summary."""
    if not cfg.smtp_password:
        logger.info("Step 6: Notification skipped (no SMTP config)")
        return

    today = date.today().isoformat()
    stats = queue_manager.get_stats()

    # Build reply section
    reply_section = ""
    if reply_stats and reply_stats.get("found", 0) > 0:
        reply_section = f"""
REPLIES DETECTED:
  {reply_stats.get('matched', 0)} matched to bundles
  {reply_stats.get('positive', 0)} positive (interested!)
  {reply_stats.get('negative', 0)} negative
  {reply_stats.get('auto_reply', 0)} auto-replies
  {reply_stats.get('redirect', 0)} redirects
"""

    # Build follow-up section
    followup_section = ""
    if followup_stats:
        s = followup_stats.get("scheduled", {})
        se = followup_stats.get("sent", {})
        followup_section = f"""
FOLLOW-UPS:
  Scheduled: {s.get('scheduled_nudge', 0)} nudges, {s.get('scheduled_closing', 0)} closings
  Sent: {se.get('sent', 0)}, Failed: {se.get('failed', 0)}
"""

    # Build news signal section
    news_section = ""
    if news_stats and news_stats.get("total_signals", 0) > 0:
        news_section = f"""
NEWS SIGNALS:
  {news_stats.get('total_signals', 0)} signals detected
  {news_stats.get('total_contacts_created', 0)} new contacts created
  {news_stats.get('sources_scanned', 0)} sources scanned
"""

    # Build account maintenance section
    acct_section = ""
    if account_stats:
        acct_section = f"""
ACCOUNT MAINTENANCE:
  {account_stats.get('recalculated', 0)} confidence scores recalculated
  {account_stats.get('reactivated', 0)} revisit contacts reactivated
  {account_stats.get('parked', 0)} contacts parked (no reply)
"""

    can_send, sent_today, max_sends = queue_manager.check_daily_send_cap()

    # Build the detailed sections
    sent_detail = _build_sent_today_section()
    tomorrow_detail = _build_tomorrow_queue_section()
    attention_detail = _build_needs_attention_section()
    board_summary = _build_account_board_summary()

    # Build field intel section
    try:
        from outreach_engine.research_engine import get_research_summary_for_report
        field_intel_detail = get_research_summary_for_report()
    except Exception:
        field_intel_detail = "  (field intel module not available)\n"

    body = f"""Saturn Star Movers — Daily Pipeline Report
{'=' * 55}
Date: {today}

OVERVIEW:
  Sent today: {sent}{f' ({failed} failed)' if failed else ''}
  Auto-approved: {auto_approved} bundles
  Queued for tomorrow: {generated}
  Emails discovered: {discovered}
  Send cap: {sent_today}/{max_sends} used
{reply_section}{followup_section}{news_section}{acct_section}
{'─' * 55}
EMAILS SENT TODAY — Full Detail
{'─' * 55}
{sent_detail}
{'─' * 55}
QUEUED FOR TOMORROW — Ready to Send
{'─' * 55}
{tomorrow_detail}
{'─' * 55}
⚠ NEEDS YOUR ATTENTION
{'─' * 55}
{attention_detail}
{'─' * 55}
ACCOUNT BOARD
{'─' * 55}
{board_summary}
{'─' * 55}
FIELD INTEL — Research Pipeline
{'─' * 55}
{field_intel_detail}
{'─' * 55}
PIPELINE TOTALS (all time)
{'─' * 55}
  Total Contacts: {stats['total_contacts']}
  Emails Found: {stats['emails_found']}
  Total Sent: {stats['total_sent']}
  Open Rate: {stats['open_rate']}%
  Total Replied: {stats['total_replied']}
  Bounced: {stats['total_bounced']}
  Queue: {stats['total_queued']} queued, {stats['total_approved']} approved
  Remaining: {stats['contacts_remaining']} contacts not yet reached

— Saturn Star Outreach Engine (Autonomous Mode)
  Reply to this email or update the dashboard to feed back intel.
  Dashboard: {cfg.dashboard_url}
  API: {cfg.sidecar_public_url}/docs"""

    subject = (
        f"Saturn Star Daily Report — {today}: "
        f"{sent} sent, {generated} queued"
        f"{f', {failed} failed' if failed else ''}"
    )

    # Send to notification email
    notify_targets = [cfg.notification_email]
    # Also send to business email if different
    biz_email = "business@starmovers.ca"
    if biz_email != cfg.notification_email:
        notify_targets.append(biz_email)

    for target in notify_targets:
        if not target:
            continue
        try:
            send_email(target, subject, body)
            logger.info("Step 6: Report sent to %s", target)
        except Exception as e:
            logger.warning("Step 6: Report to %s failed: %s", target, e)


def step_flywheel() -> dict:
    """Step 2.5: Run flywheel batch for recent opens/replies."""
    logger.info("Step 2.5: Running flywheel for contact growth...")
    try:
        from outreach_engine.flywheel import run_flywheel_batch
        stats = run_flywheel_batch(limit=20)
        logger.info("  Flywheel: %d opens, %d replies processed -> %d new contacts",
                     stats.get("opens_processed", 0), stats.get("replies_processed", 0),
                     stats.get("new_contacts", 0))
        return stats
    except Exception as e:
        logger.warning("  Flywheel failed: %s", e)
        return {}


def step_news_scan() -> dict:
    """Step 2.8: Scan local news for moving-service signals."""
    logger.info("Step 2.8: Scanning news for business signals...")
    try:
        from outreach_engine.news_scanner import scan_all_sources
        stats = scan_all_sources(auto_create_contacts=True)
        if stats.get("enabled") is False:
            logger.info("  News scanning disabled")
            return stats
        logger.info("  News scan: %d signals found, %d contacts created",
                     stats.get("total_signals", 0),
                     stats.get("total_contacts_created", 0))
        return stats
    except Exception as e:
        logger.warning("  News scan failed: %s", e)
        return {}


def step_backup() -> str:
    """Step 7: Backup the database."""
    logger.info("Step 7: Backing up database...")
    try:
        path = queue_manager.backup_database()
        logger.info("  Backup saved to %s", path)
        return path
    except Exception as e:
        logger.warning("  Backup failed: %s", e)
        return ""


def run_daily_pipeline():
    """Full daily pipeline with run logging."""
    run_id = queue_manager.log_pipeline_start("interactive")
    logger.info("=" * 60)
    logger.info("Saturn Star Movers — Daily Outreach Pipeline (run #%d)", run_id)
    logger.info("=" * 60)

    try:
        step_scan_bounces()
        reply_stats = step_scan_replies()
        acct_stats = step_account_maintenance()
        discovered = step_discover(cfg.discovery_batch_size)
        step_verify_likely(limit=50)
        generated = step_generate_bundles(cfg.daily_send_target)
        auto_approved = step_auto_approve()
        step_flywheel()
        news_stats = step_news_scan()

        if generated < cfg.daily_send_target:
            backfilled = step_backfill(cfg.daily_send_target)
            generated += backfilled
            # Auto-approve the backfilled bundles too
            if backfilled > 0:
                auto_approved += step_auto_approve()

        sent, failed = step_send_approved()
        followup_stats = step_followups()
        step_backup()
        step_notify(discovered, generated, sent, reply_stats=reply_stats,
                    failed=failed, auto_approved=auto_approved,
                    followup_stats=followup_stats, news_stats=news_stats,
                    account_stats=acct_stats)

        results = {
            "discovered": discovered, "generated": generated,
            "auto_approved": auto_approved,
            "sent": sent, "failed": failed,
            "followups": followup_stats,
            "news_signals": news_stats.get("total_signals", 0),
        }
        queue_manager.log_pipeline_end(run_id, "completed", stats=results)

        logger.info("=" * 60)
        logger.info("Pipeline complete: %d discovered, %d generated, %d sent",
                     discovered, generated, sent)
        logger.info("=" * 60)
    except Exception as e:
        queue_manager.log_pipeline_end(run_id, "failed", error=traceback.format_exc())
        logger.error("Pipeline failed: %s", e)
        raise


def run_daily_pipeline_headless(batch_size: int = 20) -> dict:
    """Headless pipeline for API/cron — runs full cycle, returns stats dict."""
    run_id = queue_manager.log_pipeline_start("headless")
    logger.info("=" * 60)
    logger.info("Saturn Star Movers — Headless Pipeline (run #%d, batch=%d)",
                run_id, batch_size)
    logger.info("=" * 60)

    results = {
        "run_id": run_id,
        "bounces_marked": 0,
        "reply_stats": {},
        "flywheel": {},
        "discovered": 0,
        "verify_likely": {},
        "generated": 0,
        "auto_approved": 0,
        "backfilled": 0,
        "sent": 0,
        "failed": 0,
        "followups": {},
        "news_stats": {},
        "account_maintenance": {},
        "backup": "",
    }

    try:
        # Step 0a: Scan bounces
        results["bounces_marked"] = step_scan_bounces()

        # Step 0b: Scan replies
        results["reply_stats"] = step_scan_replies()

        # Step 0c: Account maintenance (before discovery so scores are fresh)
        results["account_maintenance"] = step_account_maintenance()

        # Step 1: Send approved bundles first (they've been reviewed or auto-approved)
        results["sent"], results["failed"] = step_send_approved()

        # Step 2: Discover emails
        results["discovered"] = step_discover(cfg.discovery_batch_size)

        # Step 2.2: Batch-verify 'likely' emails before bundle generation
        results["verify_likely"] = step_verify_likely(limit=50)

        # Step 2.5: Flywheel — grow contact list from engagement signals
        results["flywheel"] = step_flywheel()

        # Step 2.8: News signal scan
        results["news_stats"] = step_news_scan()

        # Step 3: Generate bundles for next batch
        results["generated"] = step_generate_bundles(batch_size)

        # Step 3.5: Auto-approve eligible bundles
        results["auto_approved"] = step_auto_approve()

        # Step 4: Backfill
        if results["generated"] < batch_size:
            results["backfilled"] = step_backfill(batch_size)
            results["generated"] += results["backfilled"]
            if results["backfilled"] > 0:
                results["auto_approved"] += step_auto_approve()

        # Step 5.5: Follow-ups
        results["followups"] = step_followups()

        # Step 6: Notify
        step_notify(
            results["discovered"], results["generated"], results["sent"],
            reply_stats=results["reply_stats"],
            failed=results["failed"],
            auto_approved=results["auto_approved"],
            followup_stats=results["followups"],
            news_stats=results["news_stats"],
            account_stats=results.get("account_maintenance"),
        )

        # Step 7: Backup
        results["backup"] = step_backup()

        queue_manager.log_pipeline_end(run_id, "completed", stats=results)

        logger.info("=" * 60)
        logger.info("Headless pipeline complete: %s", results)
        logger.info("=" * 60)

    except Exception as e:
        queue_manager.log_pipeline_end(run_id, "failed",
                                       stats=results, error=traceback.format_exc())
        logger.error("Headless pipeline failed: %s", e)
        results["error"] = str(e)

    return results


def main():
    parser = argparse.ArgumentParser(description="Saturn Star daily outreach pipeline")
    parser.add_argument("--discover-only", action="store_true",
                        help="Only run email discovery")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate bundles but don't send")
    parser.add_argument("--send-only", action="store_true",
                        help="Only send approved bundles")
    parser.add_argument("--batch-size", type=int, default=cfg.daily_send_target,
                        help="Number of bundles to generate")
    args = parser.parse_args()

    # Ensure DB exists
    if not cfg.db_path.exists():
        from outreach_engine.db.init_db import init_db
        from outreach_engine.csv_importer import import_all
        init_db(cfg.db_path)
        import_all()

    if args.discover_only:
        step_discover(args.batch_size)
    elif args.send_only:
        step_send_approved()
    elif args.dry_run:
        step_discover(cfg.discovery_batch_size)
        step_generate_bundles(args.batch_size)
        step_auto_approve()
        logger.info("Dry run complete — bundles generated and auto-approved but not sent.")
    else:
        run_daily_pipeline()


if __name__ == "__main__":
    main()
