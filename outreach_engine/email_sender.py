"""SiteGround SMTP email sender with tracking pixel injection.

Saves a copy to the IMAP Sent folder so emails appear in your mailbox.
"""

import imaplib
import logging
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

from outreach_engine.config import cfg

logger = logging.getLogger(__name__)

# IMAP config (same host as SMTP for SiteGround)
_IMAP_PORT = 993
_SENT_FOLDER_NAMES = ["Sent", "INBOX.Sent", "Sent Messages", "Sent Items"]


def _text_to_html(text: str, tracking_id: str = "") -> str:
    """Convert plain text email body to HTML with optional tracking pixel."""
    # Convert markdown-style bold
    import re
    html = text
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)

    # Wrap <li> groups in <ul>
    html = re.sub(
        r"((?:<li>.*?</li>\n?)+)",
        r"<ul style='margin:8px 0;padding-left:20px;'>\1</ul>",
        html,
    )

    # Paragraphs
    paragraphs = html.split("\n\n")
    html_parts = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if p.startswith("<ul") or p.startswith("<li"):
            html_parts.append(p)
        else:
            html_parts.append(f"<p style='margin:12px 0;line-height:1.6;'>{p}</p>")

    body_html = "\n".join(html_parts)

    # Tracking pixel
    pixel_html = ""
    if tracking_id:
        pixel_url = f"{cfg.sidecar_public_url}/api/track/{tracking_id}"
        pixel_html = f'<img src="{pixel_url}" width="1" height="1" style="display:none;" alt="" />'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; font-size: 14px; color: #333; max-width: 600px;">
{body_html}
{pixel_html}
</body>
</html>"""


def _get_ssl_context(strict: bool = True) -> ssl.SSLContext:
    """Get an SSL context, optionally relaxed for shared hosting."""
    ctx = ssl.create_default_context()
    if not strict:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _save_to_sent_folder(msg: MIMEMultipart) -> None:
    """Append the sent message to the IMAP Sent folder so it shows in webmail."""
    try:
        # Try strict SSL first, fallback to relaxed
        imap = None
        for strict in [True, False]:
            try:
                ctx = _get_ssl_context(strict)
                imap = imaplib.IMAP4_SSL(cfg.smtp_host, _IMAP_PORT, ssl_context=ctx)
                imap.login(cfg.smtp_user, cfg.smtp_password)
                break
            except ssl.SSLCertVerificationError:
                if strict:
                    continue
                raise

        if not imap:
            return

        # Find the Sent folder — different servers name it differently
        sent_folder = None
        status, folders = imap.list()
        if status == "OK" and folders:
            folder_names = []
            for f in folders:
                if f:
                    decoded = f.decode() if isinstance(f, bytes) else str(f)
                    # Extract folder name from IMAP LIST response like '(\\Sent) "/" "Sent"'
                    parts = decoded.rsplit('"', 2)
                    if len(parts) >= 2:
                        folder_names.append(parts[-2])

            # Check for known sent folder names
            for candidate in _SENT_FOLDER_NAMES:
                for name in folder_names:
                    if name.lower() == candidate.lower():
                        sent_folder = name
                        break
                if sent_folder:
                    break

            # Also check for folders with \Sent flag
            if not sent_folder:
                for f in folders:
                    decoded = f.decode() if isinstance(f, bytes) else str(f)
                    if "\\Sent" in decoded:
                        parts = decoded.rsplit('"', 2)
                        if len(parts) >= 2:
                            sent_folder = parts[-2]
                            break

        if not sent_folder:
            sent_folder = "Sent"  # default guess

        # Append the message
        msg_bytes = msg.as_bytes()
        now = datetime.now(timezone.utc)
        imap.append(sent_folder, "\\Seen", imaplib.Time2Internaldate(now), msg_bytes)
        logger.info("Saved to IMAP Sent folder: %s", sent_folder)

        imap.logout()

    except Exception as e:
        # Non-fatal — email was already sent, just couldn't save to Sent
        logger.warning("Failed to save to Sent folder: %s", e)


def send_email(
    to_email: str,
    subject: str,
    body: str,
    tracking_id: str = "",
) -> dict:
    """Send an email via SiteGround SMTP.

    Returns dict with success, message_id, smtp_code, error.
    """
    if not cfg.smtp_user or not cfg.smtp_password:
        return {"success": False, "error": "SMTP not configured. Set SMTP_USER and SMTP_PASSWORD in .env"}

    if not to_email:
        return {"success": False, "error": "No recipient email"}

    # Build message
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{cfg.smtp_from_name} <{cfg.smtp_from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)

    # Generate tracking ID if not provided
    if not tracking_id:
        tracking_id = str(uuid.uuid4())

    # Plain text version
    msg.attach(MIMEText(body, "plain"))

    # HTML version with tracking pixel
    html_body = _text_to_html(body, tracking_id)
    msg.attach(MIMEText(html_body, "html"))

    try:
        if cfg.smtp_use_ssl:
            # SSL on port 465 — try strict cert first, fallback for shared hosting
            context = _get_ssl_context(strict=True)
            try:
                with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=context,
                                      timeout=15) as server:
                    server.login(cfg.smtp_user, cfg.smtp_password)
                    server.send_message(msg)
                    logger.info("Email sent to %s via SSL", to_email)
            except ssl.SSLCertVerificationError:
                logger.info("SSL cert verify failed, retrying without strict verification")
                ctx = _get_ssl_context(strict=False)
                with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=ctx,
                                      timeout=15) as server:
                    server.login(cfg.smtp_user, cfg.smtp_password)
                    server.send_message(msg)
                    logger.info("Email sent to %s via SSL (relaxed)", to_email)
        else:
            # STARTTLS on port 587
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as server:
                server.starttls()
                server.login(cfg.smtp_user, cfg.smtp_password)
                server.send_message(msg)
                logger.info("Email sent to %s via STARTTLS", to_email)

        # Save a copy to the Sent folder so it shows in webmail
        _save_to_sent_folder(msg)

        return {
            "success": True,
            "tracking_id": tracking_id,
            "smtp_code": 250,
        }

    except smtplib.SMTPRecipientsRefused as e:
        error_msg = str(e)
        logger.warning("Recipient refused: %s → %s", to_email, error_msg)
        return {"success": False, "error": error_msg, "smtp_code": 550}

    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"Authentication failed: {e}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg, "smtp_code": 535}

    except Exception as e:
        error_msg = str(e)
        logger.error("Send failed to %s: %s", to_email, error_msg)
        return {"success": False, "error": error_msg}


# ── Reply detection + classification via IMAP ─────────────────────

import re as _re

_EMAIL_RE = _re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Patterns for auto-replies (out-of-office, vacation, etc.)
_AUTO_REPLY_PATTERNS = [
    r"out of (?:the )?office",
    r"on (?:vacation|leave|holiday|pto)",
    r"auto[- ]?reply",
    r"automatic reply",
    r"i(?:'m| am) (?:currently )?(?:away|unavailable|out)",
    r"thank you for (?:your |)(?:email|message|reaching out).*(?:get back|respond|reply)",
    r"will (?:get back|respond|return|reply).*(?:soon|shortly|when i return)",
    r"limited access to email",
    r"delayed response",
]
_AUTO_REPLY_RE = _re.compile("|".join(_AUTO_REPLY_PATTERNS), _re.IGNORECASE)

# Patterns for "email someone else instead"
_REDIRECT_PATTERNS = [
    r"(?:please |)(?:contact|reach out to|email|write to|send .* to)\s+(\S+@\S+\.\S+)",
    r"(?:best|better|right) (?:person|contact|email) (?:is|would be)\s+(\S+@\S+\.\S+)",
    r"(?:forward|redirect|cc|copy)\s+(?:this |your (?:email|message) )?to\s+(\S+@\S+\.\S+)",
    r"(\S+@\S+\.\S+)\s+(?:is|would be) (?:the |a )?(?:best|better|right|correct) (?:person|contact|email)",
    r"no longer (?:at|with|active|using|monitoring)\s+(?:this|that)",
]
_REDIRECT_RE = _re.compile("|".join(_REDIRECT_PATTERNS), _re.IGNORECASE)


def _imap_date(days_ago: int) -> str:
    """Format a date N days ago for IMAP SINCE filter."""
    from datetime import timedelta
    d = datetime.now() - timedelta(days=days_ago)
    return d.strftime("%d-%b-%Y")


def _get_reply_body(msg) -> str:
    """Extract the plain text body from a reply, stripping quoted original."""
    import email as email_lib
    body = ""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            try:
                body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                break
            except Exception:
                continue
    if not body:
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                    body = _re.sub(r"<[^>]+>", " ", body)
                    break
                except Exception:
                    continue

    # Strip quoted text
    lines = body.split("\n")
    clean_lines = []
    for line in lines:
        if _re.match(r"^On .* wrote:", line.strip()):
            break
        if line.strip().startswith(">"):
            break
        if _re.match(r"^-{3,}.*Original Message", line.strip(), _re.IGNORECASE):
            break
        if _re.match(r"^From:\s", line.strip()):
            break
        clean_lines.append(line)

    return "\n".join(clean_lines).strip()


def _classify_reply_local(body: str) -> tuple[str, str | None]:
    """Fast local classification. Returns (reply_type, redirect_email).

    reply_type: 'auto_reply' | 'redirect' | 'human_reply'
    """
    # Check for auto-reply
    if _AUTO_REPLY_RE.search(body):
        redirect_match = _REDIRECT_RE.search(body)
        if redirect_match:
            redirect_email = next((g for g in redirect_match.groups() if g), None)
            if redirect_email:
                return "redirect", redirect_email.strip().rstrip(".,;")
        return "auto_reply", None

    # Check for redirect
    redirect_match = _REDIRECT_RE.search(body)
    if redirect_match:
        redirect_email = next((g for g in redirect_match.groups() if g), None)
        if redirect_email:
            return "redirect", redirect_email.strip().rstrip(".,;")

    # Check for "no longer at this email" without a redirect
    if _re.search(r"no longer (?:at|with|active|using|monitoring)", body, _re.IGNORECASE):
        return "auto_reply", None

    return "human_reply", None


def _classify_reply_sentiment(body: str) -> str:
    """Classify a human reply as positive/negative/neutral using GPT-4o-mini."""
    from openai import OpenAI
    client = OpenAI(api_key=cfg.openai_api_key)

    try:
        resp = client.chat.completions.create(
            model=cfg.llm_model,
            temperature=0,
            messages=[
                {"role": "system", "content": (
                    "You classify email replies to cold outreach from a moving company (Saturn Star Movers). "
                    "Respond with ONLY one word:\n"
                    "- positive: interested in services, wants a quote, asks for more info, "
                    "refers to someone who needs moving, wants to set up a partnership\n"
                    "- negative: not interested, no need for movers, asks to be removed, "
                    "unsubscribe, do not contact again\n"
                    "- neutral: unclear intent, just acknowledging, asking a question "
                    "that's neither positive nor negative"
                )},
                {"role": "user", "content": f"Classify this reply:\n\n{body[:1000]}"},
            ],
            max_tokens=10,
        )
        sentiment = resp.choices[0].message.content.strip().lower()
        if sentiment in ("positive", "negative", "neutral"):
            return sentiment
        return "neutral"
    except Exception as e:
        logger.warning("Sentiment classification failed: %s", e)
        return "neutral"


def _get_sent_recipient_emails() -> set[str]:
    """Get all email addresses we've sent outreach to."""
    import sqlite3
    conn = sqlite3.connect(str(cfg.db_path))
    rows = conn.execute("""
        SELECT DISTINCT LOWER(c.discovered_email)
        FROM outreach_bundles b
        JOIN contacts c ON b.contact_id = c.id
        WHERE b.status IN ('sent', 'replied', 'rejected')
        AND c.discovered_email != ''
    """).fetchall()
    conn.close()
    emails = set()
    for row in rows:
        for addr in _EMAIL_RE.findall(row[0] or ""):
            emails.add(addr.lower())
    return emails


def scan_replies(days: int = 7) -> list[dict]:
    """Scan SiteGround IMAP inbox for replies to our outreach emails.

    Returns list of dicts with keys:
        from_email, subject, body, reply_type, sentiment, redirect_email
    """
    import email as email_lib

    if not cfg.smtp_user or not cfg.smtp_password:
        logger.error("SMTP not configured for IMAP")
        return []

    sent_emails = _get_sent_recipient_emails()
    if not sent_emails:
        logger.info("No sent outreach emails to match against")
        return []

    try:
        ctx = _get_ssl_context(strict=True)
        try:
            imap = imaplib.IMAP4_SSL(cfg.smtp_host, _IMAP_PORT, ssl_context=ctx)
        except ssl.SSLCertVerificationError:
            ctx2 = _get_ssl_context(strict=False)
            imap = imaplib.IMAP4_SSL(cfg.smtp_host, _IMAP_PORT, ssl_context=ctx2)

        imap.login(cfg.smtp_user, cfg.smtp_password)
        imap.select("INBOX")

        all_msg_ids = set()
        for criteria in [
            f'(SUBJECT "Re:" SINCE "{_imap_date(days)}" NOT FROM "mailer-daemon")',
            f'(SUBJECT "Automatic reply" SINCE "{_imap_date(days)}")',
            f'(SUBJECT "Out of Office" SINCE "{_imap_date(days)}")',
            f'(SUBJECT "Auto:" SINCE "{_imap_date(days)}")',
        ]:
            try:
                _, data = imap.search(None, criteria)
                all_msg_ids.update(data[0].split())
            except Exception:
                pass

        replies = []
        seen_from: set[str] = set()
        our_email = cfg.smtp_from_email.lower()

        for mid in all_msg_ids:
            if not mid:
                continue
            _, msg_data = imap.fetch(mid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw)

            from_header = msg.get("From", "")
            from_match = _EMAIL_RE.search(from_header)
            if not from_match:
                continue
            from_email = from_match.group(0).lower()

            # Skip system emails and our own
            if from_email == our_email:
                continue
            if any(skip in from_email for skip in ("mailer-daemon", "postmaster", "noreply", "no-reply")):
                continue

            # Only process if sender matches a sent outreach recipient
            if from_email not in sent_emails:
                continue

            # Skip duplicates
            if from_email in seen_from:
                continue
            seen_from.add(from_email)

            subject = msg.get("Subject", "")
            body = _get_reply_body(msg)
            if not body:
                continue

            reply_type, redirect_email = _classify_reply_local(body)

            sentiment = ""
            if reply_type == "human_reply":
                sentiment = _classify_reply_sentiment(body)

            replies.append({
                "from_email": from_email,
                "subject": subject,
                "body": body[:500],
                "reply_type": reply_type,
                "sentiment": sentiment,
                "redirect_email": redirect_email,
            })

        imap.logout()
        logger.info("Found %d replies (%d human, %d auto, %d redirect)",
                     len(replies),
                     sum(1 for r in replies if r["reply_type"] == "human_reply"),
                     sum(1 for r in replies if r["reply_type"] == "auto_reply"),
                     sum(1 for r in replies if r["reply_type"] == "redirect"))
        return replies

    except Exception as e:
        logger.exception("IMAP reply scan failed: %s", e)
        return []


def process_replies(days: int = 7) -> dict:
    """Scan for replies, match to bundles, classify, and update DB.

    Returns stats dict with counts.
    """
    import sqlite3
    from datetime import timedelta

    replies = scan_replies(days=days)
    if not replies:
        return {"found": 0, "matched": 0, "positive": 0, "negative": 0,
                "auto_reply": 0, "redirect": 0}

    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    stats = {"found": len(replies), "matched": 0, "positive": 0,
             "negative": 0, "neutral": 0, "auto_reply": 0, "redirect": 0}

    for reply in replies:
        from_email = reply["from_email"]

        # Match reply to a sent bundle by contact email
        row = conn.execute("""
            SELECT b.id, b.status, b.reply_type as existing_reply_type,
                   c.discovered_email, c.company_name, b.contact_id
            FROM outreach_bundles b
            JOIN contacts c ON b.contact_id = c.id
            WHERE b.status IN ('sent', 'replied', 'rejected')
            AND LOWER(c.discovered_email) = ?
        """, (from_email,)).fetchone()

        if not row:
            continue

        bid = row["id"]
        stats["matched"] += 1

        # Skip if already classified
        if row["existing_reply_type"]:
            continue

        reply_type = reply["reply_type"]
        sentiment = reply.get("sentiment", "")
        snippet = reply["body"][:500]
        redirect_email = reply.get("redirect_email", "")

        if reply_type == "auto_reply":
            stats["auto_reply"] += 1
            conn.execute("""
                UPDATE outreach_bundles
                SET reply_type = 'auto_reply', reply_snippet = ?,
                    notes = COALESCE(notes, '') || ' | auto-reply detected',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (snippet, bid))
            logger.info("Bundle %d (%s): auto-reply detected", bid, row["company_name"])

        elif reply_type == "redirect":
            stats["redirect"] += 1
            if redirect_email:
                # Update contact email to redirect address
                conn.execute("""
                    UPDATE contacts
                    SET discovered_email = ?, email_status = 'likely', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (redirect_email, row["contact_id"]))

                # Requeue bundle for next day
                from datetime import date
                next_batch = (date.today() + timedelta(days=1)).isoformat()
                conn.execute("""
                    UPDATE outreach_bundles
                    SET status = 'queued', batch_date = ?,
                        reply_type = 'redirect', reply_snippet = ?,
                        redirect_email = ?,
                        sent_at = NULL, email_sent = 0,
                        notes = COALESCE(notes, '') || ' | redirect to: ' || ? || ' | requeued',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (next_batch, snippet, redirect_email, redirect_email, bid))
                logger.info("Bundle %d (%s): redirect to %s — requeued for %s",
                           bid, row["company_name"], redirect_email, next_batch)
            else:
                conn.execute("""
                    UPDATE outreach_bundles
                    SET reply_type = 'redirect', reply_snippet = ?,
                        notes = COALESCE(notes, '') || ' | redirect detected (no email found)',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (snippet, bid))

        elif reply_type == "human_reply":
            if sentiment == "positive":
                stats["positive"] += 1
            elif sentiment == "negative":
                stats["negative"] += 1
            else:
                stats["neutral"] += 1

            new_status = "rejected" if sentiment == "negative" else "replied"
            new_outreach = "rejected" if sentiment == "negative" else "replied"

            conn.execute("""
                UPDATE outreach_bundles
                SET status = ?, reply_type = ?, reply_snippet = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (new_status, sentiment, snippet, bid))

            conn.execute("""
                UPDATE contacts SET outreach_status = ?
                WHERE id = ?
            """, (new_outreach, row["contact_id"]))

            logger.info("Bundle %d (%s): human reply (%s) → status=%s",
                        bid, row["company_name"], sentiment, new_status)

            # Trigger flywheel for positive/neutral replies
            if sentiment in ("positive", "neutral"):
                try:
                    from outreach_engine.flywheel import on_reply_received
                    on_reply_received(bid, reply_body=snippet)
                except Exception as fw_err:
                    logger.warning("Flywheel trigger failed for bundle %d: %s", bid, fw_err)

        conn.commit()

    conn.close()
    return stats


def scan_imap_bounces(days: int = 3) -> list[str]:
    """Scan IMAP inbox for bounce-back messages. Returns list of bounced emails."""
    import email as email_lib

    if not cfg.smtp_user or not cfg.smtp_password:
        return []

    ctx = _get_ssl_context(strict=True)
    try:
        imap = imaplib.IMAP4_SSL(cfg.smtp_host, _IMAP_PORT, ssl_context=ctx)
    except ssl.SSLCertVerificationError:
        ctx2 = _get_ssl_context(strict=False)
        imap = imaplib.IMAP4_SSL(cfg.smtp_host, _IMAP_PORT, ssl_context=ctx2)

    imap.login(cfg.smtp_user, cfg.smtp_password)
    imap.select("INBOX")

    bounced_emails = set()
    our_email = cfg.smtp_from_email.lower()
    ignore = {our_email, "postmaster@saturnstarmovers.com", "business@starmovers.ca"}
    since = _imap_date(days)

    for search in [
        f'(SUBJECT "delivery" SINCE "{since}")',
        f'(SUBJECT "undeliverable" SINCE "{since}")',
        f'(FROM "mailer-daemon" SINCE "{since}")',
        f'(FROM "postmaster" SINCE "{since}")',
    ]:
        try:
            status, data = imap.search(None, search)
            ids = data[0].split() if data[0] else []
            for mid in ids:
                _, msg_data = imap.fetch(mid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        if ct in ("text/plain", "message/delivery-status"):
                            payload = part.get_payload(decode=True)
                            if payload:
                                body += payload.decode("utf-8", errors="replace")
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")

                found = _re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', body)
                for e in found:
                    e = e.lower()
                    if e not in ignore and "mailer-daemon" not in e and "postmaster" not in e:
                        bounced_emails.add(e)
        except Exception:
            continue

    imap.logout()
    logger.info("Bounce scan: found %d bounced emails", len(bounced_emails))
    return list(bounced_emails)


def send_test_email(to_email: str | None = None) -> dict:
    """Send a test email to verify SMTP config."""
    target = to_email or cfg.notification_email
    return send_email(
        to_email=target,
        subject="Saturn Star Movers — SMTP Test",
        body="This is a test email from the Saturn Star Movers outreach engine.\n\nIf you received this, SMTP is configured correctly.",
    )


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else None
    result = send_test_email(target)
    print(result)
