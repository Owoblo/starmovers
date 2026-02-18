"""Follow-up engine — 3-touch email sequence for non-responders.

Touch 1 (original): Sent by the main pipeline
Touch 2 (7 days):   Shorter, references original, adds urgency
Touch 3 (14 days):  "Closing the loop" — final touch, low pressure

Follow-ups are generated via GPT and sent through the same SMTP pipeline.
"""

import logging
import random
import time
import uuid
from datetime import date, datetime, timedelta

from outreach_engine.config import cfg
from outreach_engine import queue_manager
from outreach_engine.email_sender import send_email

logger = logging.getLogger(__name__)

# Follow-up schedule: (sequence_number, days_after_original, style)
FOLLOWUP_SCHEDULE = [
    (2, 7, "nudge"),
    (3, 14, "closing"),
]

# GPT prompts per follow-up style
FOLLOWUP_PROMPTS = {
    "nudge": """You are writing a SHORT follow-up email for Saturn Star Movers (a Windsor, ON moving company).

CONTEXT:
- We sent the original email {days_ago} days ago to {contact_name} at {company_name}
- Original subject: "{original_subject}"
- They have NOT replied yet
- Their opens: {open_count}

RULES:
- Keep it 3-5 sentences MAX
- Reference the original email briefly ("I reached out last week about...")
- Add one new piece of value (a stat, a testimonial angle, a seasonal offer)
- End with a soft CTA: "Would a quick 5-min call this week work?"
- Tone: friendly, not pushy. You're following up, not begging.
- Do NOT repeat the full original pitch
- Sign as: John Owolabi, Saturn Star Movers, 226-724-1730

Return ONLY the email body text (no subject line).
""",

    "closing": """You are writing a FINAL follow-up email for Saturn Star Movers (a Windsor, ON moving company).

CONTEXT:
- Original email sent {days_ago} days ago to {contact_name} at {company_name}
- Original subject: "{original_subject}"
- This is the LAST touch — we won't email them again after this
- Their opens: {open_count}

RULES:
- Keep it 2-4 sentences MAX
- "Closing the loop" tone — professional, zero pressure
- Acknowledge they're busy: "I know timing isn't always right..."
- Leave the door open: "If anything changes, we're a call away at 226-724-1730"
- Do NOT pitch. This is a graceful exit.
- Sign as: John Owolabi, Saturn Star Movers

Return ONLY the email body text (no subject line).
""",
}

FOLLOWUP_SUBJECTS = {
    "nudge": "Re: {original_subject}",
    "closing": "Re: {original_subject}",
}


def _generate_followup_body(style: str, contact: dict, original_bundle: dict) -> str:
    """Use GPT to generate a follow-up email body."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg.openai_api_key)
    except Exception:
        return _fallback_body(style, contact, original_bundle)

    sent_at = original_bundle.get("sent_at", "")
    days_ago = 7 if style == "nudge" else 14
    if sent_at:
        try:
            sent_date = datetime.fromisoformat(sent_at)
            days_ago = (datetime.now() - sent_date).days
        except Exception:
            pass

    prompt_template = FOLLOWUP_PROMPTS.get(style, FOLLOWUP_PROMPTS["nudge"])
    prompt = prompt_template.format(
        contact_name=contact.get("contact_name", "there"),
        company_name=contact.get("company_name", "your company"),
        original_subject=original_bundle.get("email_subject", ""),
        days_ago=days_ago,
        open_count=original_bundle.get("open_count", 0),
    )

    try:
        resp = client.chat.completions.create(
            model=cfg.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("GPT follow-up generation failed: %s", e)
        return _fallback_body(style, contact, original_bundle)


def _fallback_body(style: str, contact: dict, original_bundle: dict) -> str:
    """Static fallback if GPT is unavailable."""
    name = contact.get("contact_name", "there")
    company = contact.get("company_name", "your company")

    if style == "nudge":
        return f"""Hi {name},

I wanted to follow up on my email last week about how Saturn Star Movers can help {company} with upcoming relocations.

We've completed over 500 moves across Ontario with a 4.9/5 rating, and I'd love to explore how we can support your team.

Would a quick 5-minute call this week work?

John Owolabi
Saturn Star Movers
226-724-1730"""

    return f"""Hi {name},

I wanted to close the loop on my previous email. I know timing isn't always right, and I don't want to clutter your inbox.

If moving or relocation needs come up for {company} down the road, we're always a call away at 226-724-1730.

Wishing you and your team all the best.

John Owolabi
Saturn Star Movers"""


def schedule_followups(limit: int = 30) -> dict:
    """Scan sent bundles and schedule follow-ups where due.
    Returns {scheduled_nudge, scheduled_closing, skipped}."""
    stats = {"scheduled_nudge": 0, "scheduled_closing": 0, "skipped": 0}

    for seq, days_after, style in FOLLOWUP_SCHEDULE:
        candidates = queue_manager.get_followup_candidates(
            days_since_send=days_after, sequence=seq, limit=limit,
        )
        for c in candidates:
            # Don't follow up on bounced contacts
            if c.get("status") == "bounced":
                stats["skipped"] += 1
                continue

            scheduled_date = date.today().isoformat()
            queue_manager.create_followup(
                contact_id=c["contact_id"],
                bundle_id=c["bundle_id"],
                sequence_number=seq,
                scheduled_date=scheduled_date,
            )
            stats[f"scheduled_{style}"] += 1

    logger.info("Follow-ups scheduled: %s", stats)
    return stats


def send_followups(limit: int = 20) -> dict:
    """Send pending follow-ups that are due. Returns {sent, failed, skipped}."""
    stats = {"sent": 0, "failed": 0, "skipped": 0}

    # Check daily send cap first
    can_send, sent_today, max_sends = queue_manager.check_daily_send_cap()
    if not can_send:
        logger.warning("Daily send cap reached (%d/%d) — skipping follow-ups",
                       sent_today, max_sends)
        return stats

    budget = queue_manager.remaining_send_budget()
    pending = queue_manager.get_pending_followups()

    for fu in pending[:min(limit, budget)]:
        email_addr = fu.get("discovered_email", "")
        if not email_addr:
            stats["skipped"] += 1
            continue

        seq = fu["sequence_number"]
        style = "nudge" if seq == 2 else "closing"

        # Generate follow-up content
        body = _generate_followup_body(style, fu, fu)
        subject_template = FOLLOWUP_SUBJECTS.get(style, "Re: {original_subject}")
        subject = subject_template.format(
            original_subject=fu.get("email_subject", "Saturn Star Movers"),
        )

        # Create tracking
        tracking_id = str(uuid.uuid4())

        result = send_email(email_addr, subject, body, tracking_id=tracking_id)

        if result.get("success"):
            queue_manager.mark_followup_sent(fu["id"])
            queue_manager.log_send(
                fu["bundle_id"], email_addr,
                smtp_code=result.get("smtp_code", 0),
            )
            stats["sent"] += 1
            logger.info("Follow-up #%d sent to %s (%s)", seq, email_addr,
                        fu.get("company_name", ""))
        else:
            stats["failed"] += 1
            logger.warning("Follow-up #%d failed for %s: %s", seq, email_addr,
                           result.get("error", ""))

        # Stagger sends
        time.sleep(random.randint(8, 18))

    logger.info("Follow-ups sent: %s", stats)
    return stats


def run_followup_cycle(limit: int = 20) -> dict:
    """Full follow-up cycle: schedule + send. Called by scheduler or API."""
    scheduled = schedule_followups(limit=limit)
    sent = send_followups(limit=limit)
    return {"scheduled": scheduled, "sent": sent}
