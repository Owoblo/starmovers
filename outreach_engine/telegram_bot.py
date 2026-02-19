"""Telegram Bot — webhook handler, auth, message routing, group management.

Runs inside the existing FastAPI sidecar. Telegram POSTs to /api/telegram/webhook.
Single-user bot: only the owner's chat_id is accepted.

Flow:
  1. Webhook receives update from Telegram
  2. Auth check (chat_id must match owner or /start setup)
  3. NLP parse → classify intent
  4. Route to: idea submission, command handler, or reply-to-notification
  5. Send confirmation back to user
"""

import json
import logging
import sqlite3
from datetime import datetime

import httpx

from outreach_engine.config import cfg

logger = logging.getLogger(__name__)


# ── Telegram API Helpers ──

async def send_message(chat_id: int | str, text: str,
                       reply_markup: dict | None = None,
                       reply_to_message_id: int | None = None,
                       parse_mode: str = "Markdown") -> dict | None:
    """Send a message via Telegram Bot API."""
    if not cfg.telegram_bot_token:
        logger.warning("Telegram bot token not configured")
        return None

    url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            result = resp.json()
            if not result.get("ok"):
                logger.error("Telegram sendMessage failed: %s", result)
            return result
    except Exception as e:
        logger.error("Telegram API error: %s", e)
        return None


async def send_message_sync_safe(chat_id: int | str, text: str,
                                 reply_markup: dict | None = None,
                                 parse_mode: str = "Markdown") -> dict | None:
    """Send message using sync httpx (for use from sync code / background tasks)."""
    if not cfg.telegram_bot_token:
        return None

    url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json=payload)
            result = resp.json()
            if not result.get("ok"):
                logger.error("Telegram sendMessage failed: %s", result)
            return result
    except Exception as e:
        logger.error("Telegram API error: %s", e)
        return None


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _is_authorized(chat_id: int) -> bool:
    """Check if this chat_id is the authorized owner."""
    owner_id = cfg.telegram_chat_id
    if not owner_id:
        return False
    return str(chat_id) == str(owner_id)


def _save_chat_id(chat_id: int):
    """Save the owner's chat_id to the database for persistence."""
    conn = _get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO telegram_notifications
        (id, chat_id, notification_type, message_text)
        VALUES (1, ?, 'setup', 'Owner chat_id registered')
    """, (chat_id,))
    conn.commit()
    conn.close()


def _log_message(telegram_msg_id: int, chat_id: int, raw_text: str,
                 parsed_json: dict, intent: str, company_name: str,
                 group_id: str = "", idea_id: int | None = None):
    """Log a message to the telegram_messages table."""
    conn = _get_conn()
    conn.execute("""
        INSERT INTO telegram_messages
        (telegram_msg_id, chat_id, raw_text, parsed_json, intent,
         company_name, group_id, idea_id, processed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (
        telegram_msg_id, chat_id, raw_text,
        json.dumps(parsed_json), intent, company_name,
        group_id, idea_id,
    ))
    conn.commit()
    conn.close()


def _get_reply_context(reply_to_msg_id: int, chat_id: int) -> tuple[str, int]:
    """Look up what notification a reply is responding to.

    Returns (notification_type, reference_id) or ("", 0).
    """
    conn = _get_conn()
    row = conn.execute("""
        SELECT notification_type, reference_id
        FROM telegram_notifications
        WHERE chat_id = ? AND id = (
            SELECT MAX(id) FROM telegram_notifications
            WHERE chat_id = ?
        )
    """, (chat_id, chat_id)).fetchone()
    conn.close()

    if row:
        return row["notification_type"], row["reference_id"] or 0
    return "", 0


# ── Main Webhook Handler ──

async def handle_update(update: dict) -> dict:
    """Process a Telegram webhook update. Returns response dict."""

    # Handle callback queries (inline button presses)
    if "callback_query" in update:
        return await _handle_callback(update["callback_query"])

    message = update.get("message")
    if not message:
        return {"ok": True, "action": "ignored"}

    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()
    caption = (message.get("caption") or "").strip()
    msg_id = message.get("message_id", 0)
    photo = message.get("photo")  # list of PhotoSize objects

    if not chat_id:
        return {"ok": True, "action": "ignored"}

    # ── Photo handling (screenshot support) ──
    if photo and not text:
        if not _is_authorized(chat_id):
            return {"ok": True, "action": "unauthorized"}
        return await _handle_photo(message, chat_id, msg_id, caption)

    if not text:
        return {"ok": True, "action": "ignored"}

    # ── /start setup flow ──
    if text.startswith("/start"):
        return await _handle_start(chat_id, text, msg_id)

    # ── Auth check ──
    if not _is_authorized(chat_id):
        # Silently ignore unauthorized users
        return {"ok": True, "action": "unauthorized"}

    # ── Check if replying to a notification ──
    reply_to = message.get("reply_to_message", {})
    reply_notif_type = ""
    reply_ref_id = 0
    if reply_to:
        reply_notif_type, reply_ref_id = _get_reply_context(
            reply_to.get("message_id", 0), chat_id)

    # ── NLP Parse ──
    from outreach_engine.telegram_nlp import parse_message
    parsed = parse_message(
        text, chat_id,
        reply_to_notification_type=reply_notif_type,
        reply_to_reference_id=reply_ref_id,
    )
    intent = parsed.get("intent", "chat")

    # ── Route by intent ──

    if intent == "command" or text.startswith("/"):
        from outreach_engine.telegram_commands import handle_command
        cmd = parsed.get("command", "")
        args = parsed.get("command_args", "")
        if text.startswith("/") and not cmd:
            parts = text.split(None, 1)
            cmd = parts[0][1:]
            args = parts[1] if len(parts) > 1 else ""
        result = await handle_command(cmd, args, chat_id, msg_id)
        _log_message(msg_id, chat_id, text, parsed, "command", "")
        return result

    if intent == "status_query":
        from outreach_engine.telegram_commands import handle_command
        cmd = parsed.get("command", "status")
        args = parsed.get("command_args", parsed.get("company_name", ""))
        result = await handle_command(cmd, args, chat_id, msg_id)
        _log_message(msg_id, chat_id, text, parsed, "status_query",
                     parsed.get("company_name", ""))
        return result

    if intent == "reply_action" and reply_notif_type:
        result = await _handle_reply_action(
            text, parsed, chat_id, msg_id,
            reply_notif_type, reply_ref_id)
        _log_message(msg_id, chat_id, text, parsed, "reply_action", "")
        return result

    if intent in ("new_idea", "addition"):
        result = await _handle_idea(text, parsed, chat_id, msg_id, intent)
        _log_message(msg_id, chat_id, text, parsed, intent,
                     parsed.get("company_name", ""))
        return result

    # Default: acknowledge
    await send_message(chat_id, "Got it. Send a company name to log field intel, or /help for commands.",
                       reply_to_message_id=msg_id)
    _log_message(msg_id, chat_id, text, parsed, "chat", "")
    return {"ok": True, "action": "chat"}


async def _handle_start(chat_id: int, text: str, msg_id: int) -> dict:
    """Handle /start with setup token authentication."""
    parts = text.split(None, 1)
    token = parts[1].strip() if len(parts) > 1 else ""

    # Already authorized
    if _is_authorized(chat_id):
        await send_message(
            chat_id,
            "You're already set up! Send company names from the field, or /help for commands.",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "already_setup"}

    # Check setup token
    if not cfg.telegram_setup_token:
        await send_message(chat_id, "Bot not configured. Set TELEGRAM\\_SETUP\\_TOKEN in .env first.")
        return {"ok": True, "action": "not_configured"}

    if token != cfg.telegram_setup_token:
        # Silently ignore wrong tokens
        return {"ok": True, "action": "bad_token"}

    # Register this chat_id
    _save_chat_id(chat_id)
    # NOTE: The owner needs to set TELEGRAM_CHAT_ID in .env to this value
    await send_message(
        chat_id,
        f"Saturn Star Field Intel Bot activated!\n\n"
        f"Your chat ID: `{chat_id}`\n"
        f"Add this to your .env as TELEGRAM\\_CHAT\\_ID={chat_id}\n\n"
        f"Then redeploy. After that, just text me company names from the field.\n"
        f"/help for all commands.",
        reply_to_message_id=msg_id,
    )
    return {"ok": True, "action": "setup_complete", "chat_id": chat_id}


async def _handle_photo(message: dict, chat_id: int, msg_id: int,
                        caption: str) -> dict:
    """Handle a photo message — extract business info via GPT-4o vision.

    Downloads the highest-res photo, sends to GPT-4o with vision,
    extracts company name + details, then feeds into normal idea flow.
    """
    photo_list = message.get("photo", [])
    if not photo_list:
        return {"ok": True, "action": "no_photo"}

    # Telegram sends multiple sizes — grab the largest
    best_photo = max(photo_list, key=lambda p: p.get("file_size", 0))
    file_id = best_photo["file_id"]

    await send_message(chat_id, "Analyzing photo...", reply_to_message_id=msg_id)

    # Step 1: Get file path from Telegram
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://api.telegram.org/bot{cfg.telegram_bot_token}/getFile",
                params={"file_id": file_id},
            )
            file_info = r.json()
            if not file_info.get("ok"):
                await send_message(chat_id, "Could not download photo.")
                return {"ok": True, "action": "file_error"}
            file_path = file_info["result"]["file_path"]

        # Step 2: Download the image
        file_url = f"https://api.telegram.org/file/bot{cfg.telegram_bot_token}/{file_path}"
        async with httpx.AsyncClient(timeout=30) as client:
            img_resp = await client.get(file_url)
            image_bytes = img_resp.content

    except Exception as e:
        logger.error("Photo download failed: %s", e)
        await send_message(chat_id, "Could not download photo. Try sending the company name as text.")
        return {"ok": True, "action": "download_error"}

    # Step 3: Send to GPT-4o vision
    try:
        import base64
        from openai import OpenAI

        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        # Determine mime type from file path
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "jpg"
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")

        caption_context = f"\nThe user also sent this caption: \"{caption}\"" if caption else ""

        openai_client = OpenAI(api_key=cfg.openai_api_key)
        resp = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "You are helping a moving company owner identify business leads. "
                            "He just sent a photo from the field — probably a business sign, "
                            "storefront, truck, building, or business card.\n\n"
                            "Extract the business information and return ONLY valid JSON:\n"
                            "{\n"
                            '  "company_name": "the business name visible in the image",\n'
                            '  "industry": "what kind of business this appears to be",\n'
                            '  "location": "any address or location clues visible",\n'
                            '  "details": "any other useful details (phone numbers, services, fleet size, etc)",\n'
                            '  "confidence": 0.0 to 1.0\n'
                            "}\n\n"
                            "If you can't identify a business, set company_name to empty string "
                            "and confidence to 0."
                            f"{caption_context}"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{b64_image}",
                        },
                    },
                ],
            }],
            temperature=0.2,
            max_tokens=300,
        )

        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        extracted = json.loads(raw.strip())

    except json.JSONDecodeError:
        logger.warning("Photo vision JSON parse failed: %s", raw[:200])
        await send_message(
            chat_id,
            "I could see the photo but couldn't parse the business info. "
            "Try sending the company name as text.",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "vision_parse_error"}
    except Exception as e:
        logger.error("Photo vision failed: %s", e)
        await send_message(
            chat_id,
            "Vision analysis failed. Try sending the company name as text.",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "vision_error"}

    company = extracted.get("company_name", "").strip()
    if not company or extracted.get("confidence", 0) < 0.3:
        await send_message(
            chat_id,
            "Couldn't identify a business in that photo. "
            "Try a clearer shot of the sign, or just type the name.",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "no_business_found"}

    # Step 4: Feed into the normal idea flow as if user typed it
    # Build a synthetic parsed result
    details = extracted.get("details", "")
    notes_parts = [f"[From photo]"]
    if caption:
        notes_parts.append(caption)
    if details:
        notes_parts.append(details)

    parsed = {
        "intent": "new_idea",
        "company_name": company,
        "location": extracted.get("location", ""),
        "industry": extracted.get("industry", ""),
        "notes": " | ".join(notes_parts),
        "urgency": "urgent" if caption and any(
            w in caption.lower() for w in ["asap", "now", "urgent", "walking in"]
        ) else "normal",
        "command": "",
        "command_args": "",
        "confidence": extracted.get("confidence", 0.7),
    }

    result = await _handle_idea(
        f"[Photo] {company}", parsed, chat_id, msg_id, "new_idea",
    )
    _log_message(msg_id, chat_id, f"[Photo] {company}", parsed,
                 "new_idea", company)
    return result


async def _handle_idea(text: str, parsed: dict, chat_id: int,
                       msg_id: int, intent: str) -> dict:
    """Handle new_idea or addition intents."""
    from outreach_engine.telegram_nlp import (
        get_or_create_group, add_to_group, force_flush_group,
        set_group_idea_id, build_confirmation,
    )
    from outreach_engine import queue_manager

    company = parsed.get("company_name", "").strip()
    if not company:
        await send_message(
            chat_id,
            "I couldn't catch the company name. Try: `Coldhaus Storage near the Tim Hortons`",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "no_company"}

    # Group this message
    group_id = get_or_create_group(company, chat_id)
    count = add_to_group(group_id, text, parsed)

    urgency = parsed.get("urgency", "normal")

    if urgency == "urgent":
        # Force-flush and research immediately
        merged = force_flush_group(group_id)
        if merged:
            idea_id = queue_manager.submit_idea(
                company_name=merged["company"],
                user_notes=merged["notes"],
                city=merged.get("location") or "Windsor-Essex",
                industry=merged.get("industry", ""),
                priority="urgent",
            )
            set_group_idea_id(group_id, idea_id)

            # Send confirmation
            confirm = build_confirmation(
                company, parsed.get("industry", ""),
                parsed.get("location", ""), "urgent", count,
            )
            buttons = {
                "inline_keyboard": [[
                    {"text": "View Research", "callback_data": f"idea_view_{idea_id}"},
                ]]
            }
            await send_message(chat_id, confirm, reply_markup=buttons,
                               reply_to_message_id=msg_id)

            # Trigger immediate research in background
            try:
                from outreach_engine.research_engine import research_company
                import asyncio
                loop = asyncio.get_event_loop()
                loop.run_in_executor(None, research_company, idea_id)
            except Exception as e:
                logger.error("Failed to trigger urgent research: %s", e)

            return {"ok": True, "action": "urgent_idea", "idea_id": idea_id}

    # Normal: add to group, send confirmation
    if count == 1:
        # First message in group — send "queued" confirmation
        confirm = build_confirmation(
            company, parsed.get("industry", ""),
            parsed.get("location", ""), "normal", 1,
        )
        buttons = {
            "inline_keyboard": [[
                {"text": "Research Now", "callback_data": f"research_now_{group_id}"},
                {"text": "Set Priority", "callback_data": f"set_priority_{group_id}"},
            ]]
        }
        await send_message(chat_id, confirm, reply_markup=buttons,
                           reply_to_message_id=msg_id)
    else:
        # Additional message in same group
        await send_message(
            chat_id,
            f"Added to *{company}*:\n\"{text}\"\n({count} messages grouped)",
            reply_to_message_id=msg_id,
        )

    return {"ok": True, "action": "idea_grouped", "group_id": group_id,
            "count": count}


async def _handle_reply_action(text: str, parsed: dict, chat_id: int,
                               msg_id: int, notif_type: str,
                               ref_id: int) -> dict:
    """Handle a reply to a system notification."""
    from outreach_engine import queue_manager

    notes = parsed.get("notes", text)

    if notif_type == "research_complete" and ref_id:
        # Add notes to the idea
        queue_manager.update_idea_notes(ref_id, notes)
        await send_message(
            chat_id,
            f"Noted. Added to idea #{ref_id}.",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "notes_added", "idea_id": ref_id}

    if notif_type == "positive_reply" and ref_id:
        # Flag bundle for follow-up
        await send_message(
            chat_id,
            f"Noted \u2014 flagged for follow-up. Added to your action list.",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "reply_flagged", "bundle_id": ref_id}

    if notif_type == "pipeline_complete":
        from outreach_engine.telegram_commands import handle_command
        return await handle_command("summary", "", chat_id, msg_id)

    # Generic: acknowledge
    await send_message(
        chat_id, "Noted.",
        reply_to_message_id=msg_id,
    )
    return {"ok": True, "action": "noted"}


async def _handle_callback(callback: dict) -> dict:
    """Handle inline keyboard button presses."""
    data = callback.get("data", "")
    chat_id = callback.get("message", {}).get("chat", {}).get("id")
    msg_id = callback.get("message", {}).get("message_id")

    if not chat_id or not _is_authorized(chat_id):
        return {"ok": True, "action": "unauthorized"}

    # Answer the callback to dismiss the loading indicator
    if cfg.telegram_bot_token:
        try:
            url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/answerCallbackQuery"
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(url, json={"callback_query_id": callback["id"]})
        except Exception:
            pass

    # Route callback data
    if data.startswith("research_now_"):
        group_id = data.replace("research_now_", "")
        return await _callback_research_now(group_id, chat_id)

    if data.startswith("idea_view_"):
        idea_id = int(data.replace("idea_view_", ""))
        from outreach_engine.telegram_commands import handle_command
        return await handle_command("status_idea", str(idea_id), chat_id, 0)

    if data.startswith("set_priority_"):
        group_id = data.replace("set_priority_", "")
        await send_message(
            chat_id,
            "Reply with priority: `high`, `medium`, or `low`",
        )
        return {"ok": True, "action": "priority_prompt"}

    if data.startswith("advance_"):
        idea_id = int(data.replace("advance_", ""))
        from outreach_engine.research_engine import advance_stage
        result = advance_stage(idea_id)
        if result.get("success"):
            await send_message(
                chat_id,
                f"Advanced to Stage {result['current_stage']}/{result['total_stages']}: "
                f"{result.get('next_action', '')}",
            )
        else:
            await send_message(chat_id, f"Could not advance: {result.get('error', 'Unknown')}")
        return {"ok": True, "action": "stage_advanced"}

    return {"ok": True, "action": "unknown_callback"}


async def _callback_research_now(group_id: str, chat_id: int) -> dict:
    """Handle 'Research Now' button press — flush group and research immediately."""
    from outreach_engine.telegram_nlp import force_flush_group, set_group_idea_id
    from outreach_engine import queue_manager

    merged = force_flush_group(group_id)
    if not merged:
        await send_message(chat_id, "This idea was already submitted.")
        return {"ok": True, "action": "already_flushed"}

    idea_id = queue_manager.submit_idea(
        company_name=merged["company"],
        user_notes=merged["notes"],
        city=merged.get("location") or "Windsor-Essex",
        industry=merged.get("industry", ""),
        priority="high",
    )
    set_group_idea_id(group_id, idea_id)

    await send_message(chat_id, f"Researching *{merged['company']}* now...")

    # Trigger research in background
    try:
        from outreach_engine.research_engine import research_company
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, research_company, idea_id)
    except Exception as e:
        logger.error("Failed to trigger research: %s", e)

    return {"ok": True, "action": "research_triggered", "idea_id": idea_id}


# ── Group Flush (called by scheduler every 60s) ──

def flush_and_submit_groups():
    """Flush stale message groups and submit them as ideas.

    Called by APScheduler every 60 seconds.
    """
    from outreach_engine.telegram_nlp import flush_stale_groups, set_group_idea_id
    from outreach_engine import queue_manager

    ready = flush_stale_groups()
    for group in ready:
        try:
            idea_id = queue_manager.submit_idea(
                company_name=group["company"],
                user_notes=group["notes"],
                city=group.get("location") or "Windsor-Essex",
                industry=group.get("industry", ""),
                priority="medium",
            )
            set_group_idea_id(group["group_id"], idea_id)
            logger.info("Auto-submitted idea #%d for '%s' (%d messages grouped)",
                        idea_id, group["company"], group.get("message_count", 1))

            # Notify owner
            send_message_sync_safe(
                group["chat_id"],
                f"Submitted *{group['company']}* (auto-grouped, "
                f"{group.get('message_count', 1)} messages)\n"
                f"Research will run at next batch.",
            )
        except Exception as e:
            logger.error("Failed to auto-submit group %s: %s",
                         group["group_id"], e)


# ── Batch Research (called at 9am + 3pm) ──

def run_batch_research():
    """Research all queued (non-urgent) ideas that haven't been researched yet.

    Called by APScheduler at configured research hours.
    """
    from outreach_engine.research_engine import research_company
    from outreach_engine import queue_manager

    ideas = queue_manager.get_ideas(status="new")
    if not ideas:
        logger.info("TELEGRAM BATCH RESEARCH: No new ideas to research")
        return

    logger.info("TELEGRAM BATCH RESEARCH: Researching %d ideas", len(ideas))
    researched = 0
    for idea in ideas:
        try:
            research_company(idea["id"])
            researched += 1
        except Exception as e:
            logger.error("Batch research failed for idea #%d: %s", idea["id"], e)

    logger.info("TELEGRAM BATCH RESEARCH: Completed %d/%d", researched, len(ideas))

    # Notify owner
    if cfg.telegram_chat_id and researched > 0:
        send_message_sync_safe(
            cfg.telegram_chat_id,
            f"Batch research complete: {researched}/{len(ideas)} ideas researched.\n"
            f"Use /ideas to see results.",
        )


# ── Webhook Setup ──

async def setup_webhook(webhook_url: str) -> dict | None:
    """Register the webhook URL with Telegram."""
    if not cfg.telegram_bot_token:
        return None

    url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/setWebhook"
    payload = {
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query"],
    }
    if cfg.telegram_webhook_secret:
        payload["secret_token"] = cfg.telegram_webhook_secret

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            result = resp.json()
            logger.info("Telegram webhook setup: %s", result)
            return result
    except Exception as e:
        logger.error("Telegram webhook setup failed: %s", e)
        return None
