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
    Returns (sent_count, failed_count)."""
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


def step_notify(discovered: int, generated: int, sent: int,
                reply_stats: dict | None = None, failed: int = 0,
                auto_approved: int = 0, followup_stats: dict | None = None,
                news_stats: dict | None = None):
    """Step 6: Send notification email with daily summary."""
    if not cfg.notification_email or not cfg.smtp_password:
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

    cap_info = ""
    can_send, sent_today, max_sends = queue_manager.check_daily_send_cap()
    cap_info = f"  Send Cap: {sent_today}/{max_sends}"

    body = f"""Saturn Star Movers — Daily Pipeline Summary (AUTONOMOUS)
{'=' * 50}
Date: {today}

SENT TODAY: {sent} emails sent{f' ({failed} failed)' if failed else ''}
AUTO-APPROVED: {auto_approved} bundles
PREPPED FOR TOMORROW: {generated} bundles queued
EMAILS DISCOVERED: {discovered}
{reply_section}{followup_section}{news_section}
PIPELINE STATS:
  Total Contacts: {stats['total_contacts']}
  Emails Found: {stats['emails_found']}
  Total Sent (all time): {stats['total_sent']}
  Open Rate: {stats['open_rate']}%
  Total Replied: {stats['total_replied']}
  Bounced: {stats['total_bounced']}
  Queue: {stats['total_queued']} queued, {stats['total_approved']} approved
  Remaining: {stats['contacts_remaining']} contacts not yet reached
{cap_info}

— Saturn Star Outreach Engine (Autonomous Mode)"""

    try:
        send_email(
            cfg.notification_email,
            f"Outreach Pipeline — {today}: {sent} sent, {generated} queued",
            body,
        )
        logger.info("Step 6: Notification sent to %s", cfg.notification_email)
    except Exception as e:
        logger.warning("Step 6: Notification failed: %s", e)


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
        discovered = step_discover(cfg.discovery_batch_size)
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
                    followup_stats=followup_stats, news_stats=news_stats)

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
        "generated": 0,
        "auto_approved": 0,
        "backfilled": 0,
        "sent": 0,
        "failed": 0,
        "followups": {},
        "news_stats": {},
        "backup": "",
    }

    try:
        # Step 0a: Scan bounces
        results["bounces_marked"] = step_scan_bounces()

        # Step 0b: Scan replies
        results["reply_stats"] = step_scan_replies()

        # Step 1: Send approved bundles first (they've been reviewed or auto-approved)
        results["sent"], results["failed"] = step_send_approved()

        # Step 2: Discover emails
        results["discovered"] = step_discover(cfg.discovery_batch_size)

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
