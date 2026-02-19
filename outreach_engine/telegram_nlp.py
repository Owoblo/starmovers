"""Telegram NLP — GPT-powered message parsing + message grouping.

Parses natural language field intel into structured data:
  - Extracts company name, location, notes, industry hint
  - Classifies intent: new_idea / addition / status_query / command
  - Detects urgency: normal / urgent
  - Groups multiple messages about the same company (5-min window)
"""

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Optional

from outreach_engine.config import cfg

logger = logging.getLogger(__name__)

# ── In-memory message groups ──
# {group_id: {company, messages: [], last_msg_time, chat_id, idea_id, flushed}}
_message_groups: dict[str, dict] = {}


def parse_message(text: str, chat_id: int,
                  reply_to_notification_type: str = "",
                  reply_to_reference_id: int = 0) -> dict:
    """Parse a natural language message using GPT-4o-mini.

    Returns:
        {
            "intent": "new_idea" | "addition" | "status_query" | "command" | "reply_action",
            "company_name": str,
            "location": str,
            "industry": str,
            "notes": str,
            "urgency": "normal" | "urgent",
            "command": str (if intent=command, e.g. "summary", "status"),
            "command_args": str,
            "confidence": float (0-1),
        }
    """
    # Build context about what the user is replying to
    reply_context = ""
    if reply_to_notification_type:
        reply_context = (
            f"\nCONTEXT: The user is REPLYING to a {reply_to_notification_type} notification "
            f"(reference_id: {reply_to_reference_id}). Interpret their message as a response to that notification."
        )

    prompt = f"""You are the AI parser for Saturn Star Movers' field intel system. The owner texts ideas from his phone in natural language.

Parse this message and return structured JSON.
{reply_context}

MESSAGE: "{text}"

Return ONLY valid JSON with these keys:
{{
  "intent": "new_idea" | "addition" | "status_query" | "command" | "reply_action" | "chat",
  "company_name": "extracted company name or empty string",
  "location": "extracted location/address or empty string",
  "industry": "industry hint (e.g. cold storage, plumbing, food service) or empty string",
  "notes": "everything else worth capturing as notes",
  "urgency": "normal" or "urgent",
  "command": "if intent is command: summary/status/ideas/approve/research/pipeline/queue/stats/help or empty",
  "command_args": "arguments for the command (e.g. company name for status query)",
  "confidence": 0.0 to 1.0
}}

RULES:
- "new_idea": User spotted a new company. Must have a company_name.
- "addition": Adding info to a previously mentioned company. Contains details but references something recent.
- "status_query": Asking about a company or the system ("how's X going", "what happened today")
- "command": Explicit commands like "research X", "approve", "show pipeline", "show me the queue"
- "reply_action": Responding to a notification with an action ("looks good", "send it", "add note about...")
- "chat": General chat, not field intel
- urgency is "urgent" if: "research now", "about to walk in", "ASAP", "right now", "heading there"
- Status queries like "what happened today" or "how's today" → command: "summary"
- "how's [company] going" → intent: "status_query", command: "status", command_args: company name"""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg.openai_api_key)

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )

        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        parsed = json.loads(raw.strip())
        return parsed

    except json.JSONDecodeError as e:
        logger.warning("NLP parse JSON error: %s — raw: %s", e, raw[:200])
        return _fallback_parse(text)
    except Exception as e:
        logger.error("NLP parse failed: %s", e)
        return _fallback_parse(text)


def _fallback_parse(text: str) -> dict:
    """Quick regex/keyword fallback when GPT is unavailable."""
    text_lower = text.lower().strip()

    # Command detection
    if text_lower.startswith("/"):
        parts = text_lower.split(None, 1)
        cmd = parts[0][1:]  # strip /
        args = parts[1] if len(parts) > 1 else ""
        return {
            "intent": "command",
            "company_name": "",
            "location": "",
            "industry": "",
            "notes": text,
            "urgency": "normal",
            "command": cmd,
            "command_args": args,
            "confidence": 0.9,
        }

    # Urgency detection
    urgent_phrases = ["research now", "about to walk in", "asap", "right now",
                      "heading there", "about to go talk"]
    urgency = "urgent" if any(p in text_lower for p in urgent_phrases) else "normal"

    # Status query detection
    status_phrases = ["how's", "how is", "what happened", "what's going on",
                      "status of", "update on"]
    if any(p in text_lower for p in status_phrases):
        return {
            "intent": "status_query",
            "company_name": "",
            "location": "",
            "industry": "",
            "notes": text,
            "urgency": "normal",
            "command": "status",
            "command_args": text,
            "confidence": 0.5,
        }

    # Default: treat as new idea
    return {
        "intent": "new_idea",
        "company_name": text[:100],
        "location": "",
        "industry": "",
        "notes": text,
        "urgency": urgency,
        "command": "",
        "command_args": "",
        "confidence": 0.3,
    }


# ── Message Grouping ──

def get_or_create_group(company_name: str, chat_id: int) -> str:
    """Find an active group for this company or create one.

    Groups expire after telegram_group_timeout seconds (default 300 = 5 min).
    """
    now = time.time()
    timeout = cfg.telegram_group_timeout

    # Check for existing active group
    for gid, group in _message_groups.items():
        if (group["company"].lower() == company_name.lower()
                and group["chat_id"] == chat_id
                and not group["flushed"]
                and (now - group["last_msg_time"]) < timeout):
            return gid

    # Create new group
    gid = str(uuid.uuid4())[:8]
    _message_groups[gid] = {
        "company": company_name,
        "messages": [],
        "last_msg_time": now,
        "chat_id": chat_id,
        "idea_id": None,
        "flushed": False,
        "created_at": datetime.now().isoformat(),
    }
    return gid


def add_to_group(group_id: str, text: str, parsed: dict) -> int:
    """Add a message to an existing group. Returns message count."""
    group = _message_groups.get(group_id)
    if not group:
        return 0

    group["messages"].append({
        "text": text,
        "parsed": parsed,
        "time": time.time(),
    })
    group["last_msg_time"] = time.time()
    return len(group["messages"])


def flush_stale_groups() -> list[dict]:
    """Flush groups that have been idle past the timeout.

    Returns list of flushed groups ready for submission:
    [{company, notes, location, industry, urgency, chat_id, group_id}]
    """
    now = time.time()
    timeout = cfg.telegram_group_timeout
    ready = []

    for gid, group in list(_message_groups.items()):
        if group["flushed"]:
            continue
        if (now - group["last_msg_time"]) < timeout:
            continue

        # Merge all messages into one submission
        merged = _merge_group(group)
        merged["group_id"] = gid
        merged["chat_id"] = group["chat_id"]
        group["flushed"] = True
        ready.append(merged)

    # Clean up old flushed groups (older than 1 hour)
    stale_cutoff = now - 3600
    for gid in list(_message_groups.keys()):
        if _message_groups[gid]["flushed"] and _message_groups[gid]["last_msg_time"] < stale_cutoff:
            del _message_groups[gid]

    return ready


def force_flush_group(group_id: str) -> Optional[dict]:
    """Force-flush a specific group (e.g. for urgent research)."""
    group = _message_groups.get(group_id)
    if not group or group["flushed"]:
        return None

    merged = _merge_group(group)
    merged["group_id"] = group_id
    merged["chat_id"] = group["chat_id"]
    group["flushed"] = True
    return merged


def set_group_idea_id(group_id: str, idea_id: int):
    """Link a group to a submitted idea."""
    if group_id in _message_groups:
        _message_groups[group_id]["idea_id"] = idea_id


def get_group_idea_id(group_id: str) -> Optional[int]:
    """Get the idea_id for a group, if linked."""
    group = _message_groups.get(group_id)
    return group["idea_id"] if group else None


def _merge_group(group: dict) -> dict:
    """Merge all messages in a group into one submission payload."""
    all_notes = []
    location = ""
    industry = ""
    urgency = "normal"

    for msg in group["messages"]:
        p = msg["parsed"]
        all_notes.append(p.get("notes") or msg["text"])
        if p.get("location") and not location:
            location = p["location"]
        if p.get("industry") and not industry:
            industry = p["industry"]
        if p.get("urgency") == "urgent":
            urgency = "urgent"

    return {
        "company": group["company"],
        "notes": "\n".join(all_notes),
        "location": location,
        "industry": industry,
        "urgency": urgency,
        "message_count": len(group["messages"]),
    }


def build_confirmation(company: str, industry: str, location: str,
                       urgency: str, message_count: int = 1,
                       research_mode: str = "batch") -> str:
    """Build a human-readable confirmation message."""
    lines = [f"Got it \u2014 queued *{company}*"]

    if industry:
        lines.append(f"Industry: {industry}")
    if location:
        lines.append(f"Location: {location}")

    if message_count > 1:
        lines.append(f"({message_count} messages grouped)")

    if urgency == "urgent":
        lines.append("\nURGENT \u2014 researching now...")
    elif research_mode == "batch":
        # Figure out next batch time
        import datetime as dt
        now = dt.datetime.now()
        hours = [int(h) for h in cfg.telegram_research_hours.split(",")]
        next_time = None
        for h in sorted(hours):
            if now.hour < h:
                next_time = f"{h}:00"
                break
        if not next_time:
            next_time = f"{sorted(hours)[0]}:00 tomorrow"
        lines.append(f"Research scheduled for {next_time}")

    return "\n".join(lines)
