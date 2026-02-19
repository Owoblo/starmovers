"""Field Intel Research Engine — GPT-powered company research + staged approach planning.

Flow:
  1. User submits field intel (company name + notes from the field)
  2. GPT researches the company: structure, procurement, decision makers, angles
  3. System classifies approach type and builds a multi-stage plan
  4. Stages auto-advance when ready, big decisions wait for user approval
  5. Daily report shows research updates and what needs user input

Company types (from strategy):
  - type1_owner: Owner-operated, decision maker is the owner
  - type2_manager: Managed by hired managers, facilities/ops manager decides
  - type3_tender: Procurement/tender process, vendor registration required

Approach strategies:
  - direct_pitch: Small company, email the owner directly
  - vendor_registration: Large company, request to get on approved vendor list
  - employee_program: Franchise/chain, propose employee relocation discount
  - partnership: Mid-size, propose ongoing partnership
  - event_based: Company with upcoming move/expansion (from news signals)
"""

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta

from outreach_engine.config import cfg

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def research_company(idea_id: int) -> dict:
    """Run GPT research on a submitted field intel idea.

    Updates the account_research record with:
      - company_brief: detailed research output
      - company_type: classified type
      - approach_strategy: recommended approach
      - angles: JSON array of approach angles
      - stages_json: multi-stage plan
      - research_status: 'researched'

    Returns the research results dict.
    """
    conn = _get_conn()
    row = conn.execute("SELECT * FROM account_research WHERE id = ?",
                       (idea_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": "Idea not found"}

    company = row["company_name"]
    user_notes = row["user_notes"] or ""
    city = row["city"] or "Windsor-Essex"

    conn.execute(
        "UPDATE account_research SET research_status = 'researching', "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?", (idea_id,))
    conn.commit()
    conn.close()

    # GPT research prompt
    prompt = f"""You are a commercial moving company business development researcher for Saturn Star Movers in Windsor-Essex / Chatham-Kent, Ontario, Canada.

A team member spotted this company in the field and submitted it as a potential client. Research it thoroughly.

COMPANY: {company}
LOCATION FOCUS: {city}
FIELD NOTES FROM OUR TEAM: {user_notes if user_notes else 'No additional notes.'}

Research and provide a JSON response with these exact keys:

{{
  "company_brief": "2-3 paragraph research brief. What does this company do? How big are they? How many locations in Windsor-Essex area? Parent company? Franchise or corporate-owned? What's their organizational structure?",

  "company_type": "one of: type1_owner, type2_manager, type3_tender",

  "type_reasoning": "Why this classification? What's their decision-making structure?",

  "approach_strategy": "one of: direct_pitch, vendor_registration, employee_program, partnership, event_based",

  "strategy_reasoning": "Why this approach? What makes it the best entry point?",

  "angles": [
    "Angle 1: describe a specific way Saturn Star can provide value",
    "Angle 2: another approach angle",
    "Angle 3: if applicable"
  ],

  "target_contacts": [
    {{
      "role": "the job title to target",
      "why": "why this person is the right entry point",
      "search_tips": "how to find this person (LinkedIn, company website, etc.)"
    }}
  ],

  "procurement_notes": "Does this company have a vendor registration process? Tender system? Approved vendor list? What do we need to know?",

  "employee_angle": "Could we offer employee relocation discounts? Do they transfer staff between locations? Is this relevant?",

  "risks": "What could go wrong? Why might they say no? What should we avoid?",

  "recommended_first_message_theme": "In one sentence, what should the FIRST outreach message focus on? Not the full email, just the strategic angle.",

  "stages": [
    {{
      "stage": 1,
      "action": "research",
      "title": "short title",
      "description": "what to do in this stage",
      "target_role": "who to find/contact",
      "delay_days": 0
    }},
    {{
      "stage": 2,
      "action": "find_contacts",
      "title": "short title",
      "description": "what to do",
      "target_role": "specific role to find",
      "delay_days": 1
    }},
    {{
      "stage": 3,
      "action": "outreach",
      "title": "short title",
      "description": "what the email/outreach should focus on",
      "target_role": "who receives it",
      "delay_days": 2
    }},
    {{
      "stage": 4,
      "action": "follow_up",
      "title": "short title",
      "description": "follow-up approach",
      "target_role": "",
      "delay_days": 14
    }}
  ]
}}

IMPORTANT:
- Be specific to the Windsor-Essex/Chatham-Kent market
- Saturn Star Movers does commercial AND residential moving
- For franchises/chains: the employee relocation discount angle is very strong
- For tender companies: always lead with vendor registration, NOT a sales pitch
- We position as "reputation protection partner" — their stuff arrives safe, on time, no damage
- Return ONLY valid JSON, no markdown formatting"""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg.openai_api_key)

        resp = client.chat.completions.create(
            model=cfg.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )

        raw = resp.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        research = json.loads(raw)

    except json.JSONDecodeError as e:
        logger.error("Research JSON parse failed for '%s': %s", company, e)
        research = {"error": f"JSON parse failed: {e}", "raw": raw[:500]}
    except Exception as e:
        logger.error("Research GPT call failed for '%s': %s", company, e)
        research = {"error": str(e)}

    if "error" in research:
        conn = _get_conn()
        conn.execute(
            "UPDATE account_research SET research_status = 'failed', "
            "company_brief = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(research), idea_id))
        conn.commit()
        conn.close()
        return research

    # Build stages with status tracking
    stages = research.get("stages", [])
    for s in stages:
        s["status"] = "complete" if s.get("action") == "research" else "pending"
        s["output"] = ""
        s["completed_at"] = date.today().isoformat() if s["status"] == "complete" else ""

    # Save research results
    conn = _get_conn()
    conn.execute("""
        UPDATE account_research SET
            research_status = 'researched',
            company_brief = ?,
            company_type = ?,
            approach_strategy = ?,
            angles = ?,
            procurement_notes = ?,
            target_contacts = ?,
            recommended_first_message = ?,
            stages_json = ?,
            current_stage = 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (
        research.get("company_brief", ""),
        research.get("company_type", ""),
        research.get("approach_strategy", ""),
        json.dumps(research.get("angles", [])),
        research.get("procurement_notes", ""),
        json.dumps(research.get("target_contacts", [])),
        research.get("recommended_first_message_theme", ""),
        json.dumps(stages),
        idea_id,
    ))
    conn.commit()
    conn.close()

    logger.info("Research complete for '%s': type=%s, strategy=%s, %d stages",
                company, research.get("company_type"),
                research.get("approach_strategy"), len(stages))

    return research


def advance_stage(idea_id: int, notes: str = "") -> dict:
    """Advance the current stage to complete and move to the next stage.

    Returns {success, current_stage, next_action}.
    """
    conn = _get_conn()
    row = conn.execute("SELECT * FROM account_research WHERE id = ?",
                       (idea_id,)).fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "Idea not found"}

    stages = json.loads(row["stages_json"] or "[]")
    current = row["current_stage"] or 0

    if current < 1 or current > len(stages):
        conn.close()
        return {"success": False, "error": "No valid stage to advance"}

    # Mark current stage complete
    stage_idx = current - 1
    stages[stage_idx]["status"] = "complete"
    stages[stage_idx]["completed_at"] = date.today().isoformat()
    if notes:
        stages[stage_idx]["output"] = notes

    # Advance to next stage
    next_stage = current + 1
    new_status = row["research_status"]

    if next_stage > len(stages):
        # All stages complete
        new_status = "completed"
        next_stage = current  # stay on last
    else:
        stages[next_stage - 1]["status"] = "in_progress"
        new_status = "active"

        # Set next_action_date based on delay
        delay = stages[next_stage - 1].get("delay_days", 0)
        next_date = (date.today() + timedelta(days=delay)).isoformat()
        conn.execute(
            "UPDATE account_research SET next_action_date = ? WHERE id = ?",
            (next_date, idea_id))

    conn.execute("""
        UPDATE account_research SET
            current_stage = ?, stages_json = ?, research_status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (next_stage, json.dumps(stages), new_status, idea_id))
    conn.commit()
    conn.close()

    next_info = stages[next_stage - 1] if next_stage <= len(stages) else {}
    return {
        "success": True,
        "current_stage": next_stage,
        "total_stages": len(stages),
        "next_action": next_info.get("title", "Complete"),
        "status": new_status,
    }


def generate_stage_outreach(idea_id: int) -> dict:
    """Generate custom outreach email for the current outreach stage.

    Uses the research brief + approach strategy to craft a targeted email.
    Returns {subject, body, target_role} or {error}.
    """
    conn = _get_conn()
    row = conn.execute("SELECT * FROM account_research WHERE id = ?",
                       (idea_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": "Idea not found"}

    stages = json.loads(row["stages_json"] or "[]")
    current = row["current_stage"] or 0
    if current < 1 or current > len(stages):
        conn.close()
        return {"error": "No active stage"}

    stage = stages[current - 1]
    if stage.get("action") not in ("outreach", "follow_up"):
        conn.close()
        return {"error": f"Stage {current} is '{stage.get('action')}', not an outreach stage"}

    company = row["company_name"]
    brief = row["company_brief"] or ""
    strategy = row["approach_strategy"] or ""
    angles = json.loads(row["angles"] or "[]")
    first_msg = row["recommended_first_message"] or ""
    procurement = row["procurement_notes"] or ""
    target_contacts = json.loads(row["target_contacts"] or "[]")

    target_role = stage.get("target_role", "")
    stage_desc = stage.get("description", "")
    is_followup = stage.get("action") == "follow_up"

    prompt = f"""You are writing a {'follow-up' if is_followup else 'first outreach'} email for Saturn Star Movers (commercial/residential moving company in Windsor, ON).

COMPANY: {company}
RESEARCH BRIEF: {brief}

APPROACH STRATEGY: {strategy}
RECOMMENDED ANGLE: {first_msg}
{'PROCUREMENT NOTES: ' + procurement if procurement else ''}
TARGET CONTACT ROLE: {target_role}
STAGE DESCRIPTION: {stage_desc}

AVAILABLE ANGLES:
{chr(10).join(f'- {a}' for a in angles)}

RULES:
- {'This is a FOLLOW-UP — reference the previous outreach, keep it short (3-5 sentences)' if is_followup else 'This is the FIRST outreach — make it count but keep it professional and concise'}
- Match the approach strategy:
  - vendor_registration: Ask about their vendor registration/approved vendor process. Do NOT sell.
  - employee_program: Propose a staff relocation discount program. Frame it as a perk for their employees.
  - partnership: Position as a strategic moving partner, not a vendor.
  - direct_pitch: Direct but professional value proposition.
- Sign as: John Owolabi, Saturn Star Movers, 226-724-1730
- Keep the email 4-8 sentences for first outreach, 3-5 for follow-up
- Do NOT use generic phrases like "I hope this email finds you well"
- Be specific to their business — show we researched them

Return a JSON with:
{{
  "subject": "email subject line",
  "body": "full email body text"
}}

Return ONLY valid JSON."""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg.openai_api_key)

        resp = client.chat.completions.create(
            model=cfg.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=600,
        )

        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        result = json.loads(raw.strip())
        result["target_role"] = target_role
        result["stage"] = current

        conn.close()
        return result

    except Exception as e:
        conn.close()
        logger.error("Stage outreach generation failed for '%s': %s", company, e)
        return {"error": str(e)}


def create_contact_from_research(idea_id: int, contact_name: str = "",
                                 title_role: str = "", email: str = "",
                                 phone: str = "", website: str = "") -> int | None:
    """Create a CRM contact from a researched idea and link them.

    Returns the new contact_id.
    """
    conn = _get_conn()
    row = conn.execute("SELECT * FROM account_research WHERE id = ?",
                       (idea_id,)).fetchone()
    if not row:
        conn.close()
        return None

    company = row["company_name"]
    company_type = row["company_type"] or ""
    city = row["city"] or "Windsor"

    # Determine tier based on approach
    strategy = row["approach_strategy"] or ""
    if strategy in ("vendor_registration", "employee_program"):
        tier = "A"
        priority = 80
    elif strategy == "partnership":
        tier = "A"
        priority = 75
    else:
        tier = "B"
        priority = 65

    from urllib.parse import urlparse
    domain = ""
    if website:
        url = website if website.startswith("http") else f"https://{website}"
        try:
            host = urlparse(url).hostname or ""
            if host.startswith("www."):
                host = host[4:]
            domain = host.lower()
        except Exception:
            pass

    cur = conn.execute("""
        INSERT INTO contacts (
            company_name, contact_name, title_role, phone, website, domain,
            city, province, tier, industry_code, priority_score,
            discovered_email, email_status, outreach_status,
            company_type, account_status, notes, csv_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ON', ?, 'FIELD', ?, ?, ?, 'pending',
                  ?, 'cold', ?, 'field_intel')
    """, (
        company, contact_name, title_role, phone, website, domain,
        city, tier, priority,
        email, "likely" if email else "pending",
        company_type,
        f"Field intel #{idea_id}. Strategy: {strategy}",
    ))
    contact_id = cur.lastrowid

    # Link to research
    conn.execute(
        "UPDATE account_research SET contact_id = ?, research_status = 'active', "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (contact_id, idea_id))

    conn.commit()
    conn.close()

    logger.info("Created contact #%d from field intel #%d (%s)",
                contact_id, idea_id, company)
    return contact_id


def get_research_summary_for_report() -> str:
    """Build the Field Intel section for the daily report email."""
    conn = _get_conn()

    # Active/researched ideas
    active = conn.execute("""
        SELECT ar.*, c.discovered_email, c.contact_name as linked_contact
        FROM account_research ar
        LEFT JOIN contacts c ON ar.contact_id = c.id
        WHERE ar.research_status IN ('new', 'researching', 'researched', 'staged', 'active')
        ORDER BY
            CASE ar.research_status
                WHEN 'active' THEN 1
                WHEN 'staged' THEN 2
                WHEN 'researched' THEN 3
                WHEN 'researching' THEN 4
                WHEN 'new' THEN 5
            END,
            ar.priority DESC
        LIMIT 15
    """).fetchall()

    # Recently completed
    completed = conn.execute("""
        SELECT company_name, approach_strategy, updated_at
        FROM account_research
        WHERE research_status = 'completed'
        ORDER BY updated_at DESC LIMIT 5
    """).fetchall()

    conn.close()

    if not active and not completed:
        return "  No field intel submitted yet.\n  Submit ideas: POST /api/ideas/submit\n"

    lines = []

    for r in active:
        stages = json.loads(r["stages_json"] or "[]")
        total = len(stages)
        current = r["current_stage"] or 0
        current_stage = stages[current - 1] if 0 < current <= total else {}

        status_label = r["research_status"].upper()
        if r["research_status"] == "new":
            status_label = "AWAITING RESEARCH"
        elif r["research_status"] == "researching":
            status_label = "RESEARCHING..."
        elif r["research_status"] == "researched":
            status_label = "RESEARCH READY — Review needed"

        stage_info = ""
        if current_stage:
            stage_info = (
                f"    Stage {current}/{total}: {current_stage.get('title', '?')} "
                f"({current_stage.get('status', '?')})"
            )

        # What does the system need from the user?
        needs = ""
        if r["research_status"] == "researched":
            needs = "    → ACTION: Review research brief and approve next stage"
        elif r["research_status"] == "active" and current_stage:
            action = current_stage.get("action", "")
            if action == "find_contacts":
                needs = "    → NEED: Contact name/email for " + current_stage.get("target_role", "decision maker")
            elif action == "outreach":
                needs = "    → READY: Outreach email drafted, awaiting approval"

        strategy = r["approach_strategy"] or "pending research"
        lines.append(
            f"  {r['company_name']} — [{status_label}]\n"
            f"    Strategy: {strategy}\n"
            f"{stage_info}\n"
            f"{needs}" if needs else
            f"  {r['company_name']} — [{status_label}]\n"
            f"    Strategy: {strategy}\n"
            f"{stage_info}"
        )

    if completed:
        lines.append("\n  Recently Completed:")
        for c in completed:
            lines.append(f"    ✓ {c['company_name']} ({c['approach_strategy']})")

    return "\n".join(lines) + "\n"
