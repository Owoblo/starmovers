"""Telegram Commands — slash commands + natural language command handling.

All commands work both as /command and natural language:
  "what happened today" → /summary
  "how's Tim Hortons going" → /status Tim Hortons
"""

import json
import logging
from datetime import date

from outreach_engine.config import cfg
from outreach_engine.telegram_bot import send_message

logger = logging.getLogger(__name__)


async def handle_command(cmd: str, args: str, chat_id: int,
                         msg_id: int) -> dict:
    """Route a command to the appropriate handler."""
    cmd = cmd.lower().strip()

    handlers = {
        "help": cmd_help,
        "status": cmd_status,
        "ideas": cmd_ideas,
        "approve": cmd_approve,
        "research": cmd_research,
        "summary": cmd_summary,
        "stats": cmd_stats,
        "pipeline": cmd_pipeline,
        "queue": cmd_queue,
        "status_idea": cmd_status_idea,
    }

    handler = handlers.get(cmd)
    if handler:
        return await handler(args, chat_id, msg_id)

    await send_message(
        chat_id,
        f"Unknown command: /{cmd}\nUse /help for available commands.",
        reply_to_message_id=msg_id,
    )
    return {"ok": True, "action": "unknown_command"}


async def cmd_help(args: str, chat_id: int, msg_id: int) -> dict:
    """Show available commands."""
    text = """*Saturn Star Field Intel Bot*

*Commands:*
/status `[company]` \u2014 Check idea or pipeline status
/ideas \u2014 List all active field intel ideas
/approve `[company]` \u2014 Advance current stage
/research `[company]` \u2014 Force immediate research
/summary \u2014 Today's activity digest
/stats \u2014 Overall outreach numbers
/pipeline \u2014 Last pipeline run details
/queue \u2014 Tomorrow's send queue
/help \u2014 This message

*Natural language also works:*
\u2022 "just saw Coldhaus Storage near Tim Hortons"
\u2022 "research Shell station on Tecumseh now"
\u2022 "how's Tim Hortons going"
\u2022 "what happened today"

*Tips:*
\u2022 Send multiple texts about same company \u2014 they auto-group
\u2022 Say "research now" or "ASAP" for urgent research
\u2022 Reply to any notification to take action"""
    await send_message(chat_id, text, reply_to_message_id=msg_id)
    return {"ok": True, "action": "help"}


async def cmd_status(args: str, chat_id: int, msg_id: int) -> dict:
    """Check status of a specific company."""
    from outreach_engine import queue_manager

    if not args:
        await send_message(
            chat_id,
            "Which company? Try: /status `Coldhaus Storage`",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "status_no_args"}

    # Search ideas
    ideas = queue_manager.get_ideas(limit=100)
    company = args.strip().lower()
    matches = [i for i in ideas
               if company in i["company_name"].lower()]

    if not matches:
        await send_message(
            chat_id,
            f"No ideas found matching \"{args}\".\n"
            f"Use /ideas to see all active ideas.",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "status_not_found"}

    idea = matches[0]
    stages = idea.get("stages_json", [])
    if isinstance(stages, str):
        try:
            stages = json.loads(stages)
        except (json.JSONDecodeError, TypeError):
            stages = []

    total = len(stages)
    current = idea.get("current_stage", 0)
    current_stage = stages[current - 1] if 0 < current <= total else {}

    status_label = idea["research_status"].upper()
    lines = [f"*{idea['company_name']}* \u2014 {status_label}"]

    if idea.get("approach_strategy"):
        lines.append(f"Strategy: {idea['approach_strategy']}")
    if current_stage:
        lines.append(f"Stage {current}/{total}: {current_stage.get('title', '?')}")
        if current_stage.get("action") == "find_contacts":
            target = current_stage.get("target_role", "decision maker")
            lines.append(f"Need: {target} email")
        elif current_stage.get("action") == "outreach":
            lines.append("Outreach email ready")

    buttons = {"inline_keyboard": []}
    row = []
    if idea["research_status"] in ("researched", "active"):
        row.append({"text": "Advance Stage",
                     "callback_data": f"advance_{idea['id']}"})
    row.append({"text": "View Full",
                 "callback_data": f"idea_view_{idea['id']}"})
    if row:
        buttons["inline_keyboard"].append(row)

    await send_message(chat_id, "\n".join(lines),
                       reply_markup=buttons if buttons["inline_keyboard"] else None,
                       reply_to_message_id=msg_id)
    return {"ok": True, "action": "status", "idea_id": idea["id"]}


async def cmd_status_idea(args: str, chat_id: int, msg_id: int) -> dict:
    """Show detailed status for a specific idea by ID."""
    from outreach_engine import queue_manager

    try:
        idea_id = int(args.strip())
    except (ValueError, AttributeError):
        await send_message(chat_id, "Invalid idea ID.")
        return {"ok": True, "action": "invalid_id"}

    idea = queue_manager.get_idea(idea_id)
    if not idea:
        await send_message(chat_id, f"Idea #{idea_id} not found.")
        return {"ok": True, "action": "not_found"}

    lines = [f"*{idea['company_name']}* (#{idea_id})"]
    lines.append(f"Status: {idea['research_status'].upper()}")

    if idea.get("company_type"):
        lines.append(f"Type: {idea['company_type']}")
    if idea.get("approach_strategy"):
        lines.append(f"Strategy: {idea['approach_strategy']}")
    if idea.get("company_brief"):
        brief = idea["company_brief"][:300]
        if len(idea["company_brief"]) > 300:
            brief += "..."
        lines.append(f"\n{brief}")

    stages = idea.get("stages_json", [])
    if isinstance(stages, str):
        try:
            stages = json.loads(stages)
        except (json.JSONDecodeError, TypeError):
            stages = []

    if stages:
        lines.append("\n*Stages:*")
        for s in stages:
            icon = "\u2705" if s.get("status") == "complete" else (
                "\u25b6\ufe0f" if s.get("status") == "in_progress" else "\u23f3")
            lines.append(f"{icon} {s.get('stage', '?')}. {s.get('title', '?')}")

    if idea.get("angles"):
        angles = idea["angles"]
        if isinstance(angles, str):
            try:
                angles = json.loads(angles)
            except (json.JSONDecodeError, TypeError):
                angles = []
        if angles:
            lines.append("\n*Angles:*")
            for a in angles[:3]:
                lines.append(f"\u2022 {a}")

    await send_message(chat_id, "\n".join(lines),
                       reply_to_message_id=msg_id if msg_id else None)
    return {"ok": True, "action": "status_idea", "idea_id": idea_id}


async def cmd_ideas(args: str, chat_id: int, msg_id: int) -> dict:
    """List all active field intel ideas."""
    from outreach_engine import queue_manager

    ideas = queue_manager.get_ideas(limit=20)
    if not ideas:
        await send_message(
            chat_id,
            "No field intel ideas yet.\nSend a company name to get started!",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "no_ideas"}

    lines = ["*Field Intel Ideas:*\n"]
    for idea in ideas:
        status = idea["research_status"]
        icon = {
            "new": "\U0001f195",
            "researching": "\U0001f50d",
            "researched": "\u2705",
            "active": "\u25b6\ufe0f",
            "completed": "\u2714\ufe0f",
            "failed": "\u274c",
        }.get(status, "\u2753")

        stage_info = ""
        if idea.get("current_stage"):
            stage_info = f" (Stage {idea['current_stage']})"

        lines.append(
            f"{icon} *{idea['company_name']}* \u2014 {status}{stage_info}"
        )

    await send_message(chat_id, "\n".join(lines),
                       reply_to_message_id=msg_id)
    return {"ok": True, "action": "ideas_list"}


async def cmd_approve(args: str, chat_id: int, msg_id: int) -> dict:
    """Advance the current stage of an idea."""
    from outreach_engine import queue_manager
    from outreach_engine.research_engine import advance_stage

    if not args:
        await send_message(
            chat_id,
            "Which company? Try: /approve `Tim Hortons`",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "approve_no_args"}

    # Find the idea
    ideas = queue_manager.get_ideas(limit=100)
    company = args.strip().lower()
    matches = [i for i in ideas if company in i["company_name"].lower()]

    if not matches:
        await send_message(chat_id, f"No idea found matching \"{args}\".")
        return {"ok": True, "action": "approve_not_found"}

    idea = matches[0]
    result = advance_stage(idea["id"])

    if result.get("success"):
        await send_message(
            chat_id,
            f"*{idea['company_name']}* \u2014 Advanced to Stage "
            f"{result['current_stage']}/{result['total_stages']}\n"
            f"Next: {result.get('next_action', 'Complete')}",
            reply_to_message_id=msg_id,
        )
    else:
        await send_message(
            chat_id,
            f"Could not advance: {result.get('error', 'Unknown')}",
            reply_to_message_id=msg_id,
        )
    return {"ok": True, "action": "approve", "result": result}


async def cmd_research(args: str, chat_id: int, msg_id: int) -> dict:
    """Force immediate research for a company."""
    from outreach_engine import queue_manager
    from outreach_engine.research_engine import research_company
    import asyncio

    if not args:
        await send_message(
            chat_id,
            "Which company? Try: /research `Coldhaus Storage`",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "research_no_args"}

    company = args.strip()

    # Check if idea already exists
    ideas = queue_manager.get_ideas(limit=100)
    matches = [i for i in ideas if company.lower() in i["company_name"].lower()]

    if matches:
        idea = matches[0]
        if idea["research_status"] == "researched":
            await send_message(
                chat_id,
                f"*{idea['company_name']}* already researched. Use /status to view.",
                reply_to_message_id=msg_id,
            )
            return {"ok": True, "action": "already_researched"}
        idea_id = idea["id"]
    else:
        # Create new idea
        idea_id = queue_manager.submit_idea(
            company_name=company, priority="high",
        )

    await send_message(
        chat_id,
        f"Researching *{company}* now...",
        reply_to_message_id=msg_id,
    )

    # Run research in background
    try:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, research_company, idea_id)
    except Exception as e:
        logger.error("Research trigger failed: %s", e)

    return {"ok": True, "action": "research_triggered", "idea_id": idea_id}


async def cmd_summary(args: str, chat_id: int, msg_id: int) -> dict:
    """Today's activity digest."""
    from outreach_engine import queue_manager

    today = date.today().isoformat()
    stats = queue_manager.get_stats()
    ideas = queue_manager.get_ideas(limit=100)

    today_ideas = [i for i in ideas
                   if i.get("created_at", "").startswith(today)]

    # Get today's sends
    sent_today = stats.get("by_status", {}).get("sent", 0)
    queued = stats.get("total_queued", 0)
    opens = stats.get("unique_opens", 0)
    replied = stats.get("total_replied", 0)

    lines = [f"*Saturn Star Daily \u2014 {today}*\n"]

    if today_ideas:
        lines.append(f"{len(today_ideas)} ideas submitted today")
    lines.append(f"{stats.get('emails_sent', 0)} total emails sent")
    if opens:
        lines.append(f"{opens} opened ({stats.get('open_rate', 0)}% rate)")
    if replied:
        lines.append(f"{replied} replies received")
    if queued:
        lines.append(f"{queued} queued for sending")

    # Ideas needing attention
    needs_attention = []
    for idea in ideas:
        if idea["research_status"] == "researched":
            needs_attention.append(
                f"\u2022 {idea['company_name']} \u2014 research ready, needs review")
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
                    needs_attention.append(
                        f"\u2022 {idea['company_name']} \u2014 needs contact info")

    if needs_attention:
        lines.append("\n*NEEDS YOU:*")
        lines.extend(needs_attention[:5])

    await send_message(chat_id, "\n".join(lines),
                       reply_to_message_id=msg_id if msg_id else None)
    return {"ok": True, "action": "summary"}


async def cmd_stats(args: str, chat_id: int, msg_id: int) -> dict:
    """Overall outreach numbers."""
    from outreach_engine import queue_manager

    stats = queue_manager.get_stats()
    board_stats = queue_manager.get_account_board_stats()

    lines = [
        "*Saturn Star Outreach Stats*\n",
        f"Contacts: {stats['total_contacts']}",
        f"Emails found: {stats['emails_found']}",
        f"Emails sent: {stats['emails_sent']}",
        f"Open rate: {stats.get('open_rate', 0)}%",
        f"Replies: {stats['total_replied']}",
        f"Bounced: {stats['total_bounced']}",
        f"\nHigh confidence: {board_stats.get('high_confidence', 0)}",
        f"Needs review: {board_stats.get('needs_review', 0)}",
    ]

    await send_message(chat_id, "\n".join(lines),
                       reply_to_message_id=msg_id)
    return {"ok": True, "action": "stats"}


async def cmd_pipeline(args: str, chat_id: int, msg_id: int) -> dict:
    """Last pipeline run details."""
    from outreach_engine import queue_manager

    last_run = queue_manager.get_last_pipeline_run()
    if not last_run:
        await send_message(
            chat_id,
            "No pipeline runs yet.",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "no_pipeline"}

    stats_json = last_run.get("stats_json", "{}")
    try:
        run_stats = json.loads(stats_json) if isinstance(stats_json, str) else stats_json
    except (json.JSONDecodeError, TypeError):
        run_stats = {}

    lines = [
        "*Last Pipeline Run*\n",
        f"Status: {last_run['status']}",
        f"Started: {last_run['started_at']}",
        f"Ended: {last_run.get('ended_at', 'running...')}",
    ]

    if run_stats:
        if run_stats.get("sent"):
            lines.append(f"Sent: {run_stats['sent']}")
        if run_stats.get("generated"):
            lines.append(f"Generated: {run_stats['generated']}")
        if run_stats.get("discovered"):
            lines.append(f"Discovered: {run_stats['discovered']}")

    if last_run.get("error"):
        lines.append(f"\nError: {last_run['error'][:200]}")

    await send_message(chat_id, "\n".join(lines),
                       reply_to_message_id=msg_id)
    return {"ok": True, "action": "pipeline"}


async def cmd_queue(args: str, chat_id: int, msg_id: int) -> dict:
    """Show tomorrow's send queue."""
    from outreach_engine import queue_manager

    bundles = queue_manager.get_queue(None)
    if not bundles:
        await send_message(
            chat_id,
            "Send queue is empty.",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "queue_empty"}

    # Filter to queued/approved only
    pending = [b for b in bundles if b["status"] in ("queued", "approved")]
    if not pending:
        await send_message(
            chat_id,
            f"All {len(bundles)} bundles already sent or processed.",
            reply_to_message_id=msg_id,
        )
        return {"ok": True, "action": "queue_done"}

    lines = [f"*Send Queue* ({len(pending)} ready)\n"]
    for b in pending[:15]:
        status_icon = "\u2705" if b["status"] == "approved" else "\u23f3"
        lines.append(
            f"{status_icon} {b.get('company_name', '?')} "
            f"({b.get('email_status', '?')})"
        )

    if len(pending) > 15:
        lines.append(f"\n... and {len(pending) - 15} more")

    await send_message(chat_id, "\n".join(lines),
                       reply_to_message_id=msg_id)
    return {"ok": True, "action": "queue"}
