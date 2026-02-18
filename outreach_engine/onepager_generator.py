"""One-pager generator — creates customized HTML/PDF partnership proposals.

Takes a contact from the DB, selects the right industry content variant,
generates a branded Saturn Star HTML one-pager, and converts to PDF.

Usage:
    from outreach_engine.onepager_generator import generate_onepager
    result = generate_onepager(contact_id)
    # result = {"html_path": "...", "pdf_path": "...", "company_name": "..."}
"""

import base64
import logging
import sqlite3
from datetime import date
from io import BytesIO
from pathlib import Path

from outreach_engine.config import cfg

logger = logging.getLogger(__name__)

LOGO_PATH = cfg.logo_path
OUTPUT_DIR = Path(cfg.db_path).parent.parent / "onepagers"


# ── Industry content variants ──
# Each variant defines the text content for the one-pager sections.
# The HTML structure and branding stay identical — only text changes.

CONTENT_VARIANTS = {
    "construction": {
        "codes": ["GH25", "LC25"],
        "doc_badge": "Construction Partnership",
        "hero_headline": "Your Builds. <span>Our Moves.</span> One Seamless Experience.",
        "hero_subtitle": "Saturn Star Moving Company is seeking a strategic partnership with {company_name} to deliver turnkey relocation solutions — before, during, and after your projects.",
        "problem": "Construction projects frequently require furniture removal, temporary relocations, and post-build move-ins. Coordinating these logistics in-house is costly, time-consuming, and pulls focus from the actual build.",
        "solution": "Partner with Saturn Star as your <strong>dedicated moving &amp; logistics arm</strong>. We handle all relocation needs for your job sites and teams — on schedule, fully insured, and with zero disruption to your timelines.",
        "services": [
            ("&#8635;", "Pre-Construction Clearouts", "Remove existing furniture, appliances &amp; contents before demolition or renovation begins"),
            ("&#9878;", "Temporary Relocations", "Move occupants to temporary locations during construction, then move them back"),
            ("&#9745;", "Post-Build Move-Ins", "Final furniture delivery and placement once construction is complete — ready for occupancy"),
            ("&#9881;", "Debris &amp; Disposal Support", "Removal of old furniture, fixtures, and non-hazardous materials to keep sites clean"),
            ("&#9998;", "Office &amp; Commercial Moves", "Relocate entire offices, retail spaces, or commercial tenants tied to your projects"),
            ("&#9041;", "On-Site Logistics", "Coordinate deliveries, stage furniture, and manage move-day scheduling around your crews"),
        ],
        "benefits_col1_title": "For Your Business",
        "benefits_col1": [
            ("<strong>New revenue stream</strong> — earn referral commissions on every job we complete for your clients",),
            ("<strong>Enhanced service offering</strong> — provide end-to-end project solutions without additional overhead",),
            ("<strong>On-time project delivery</strong> — no delays waiting on third-party movers or clearout crews",),
            ("<strong>Priority scheduling</strong> — your projects jump to the front of the line, every time",),
        ],
        "benefits_col2_title": "For Your Clients",
        "benefits_col2": [
            ("<strong>One point of contact</strong> — clients deal with your company, we work behind the scenes",),
            ("<strong>Stress-free experience</strong> — professional movers handle all the heavy lifting before and after the build",),
            ("<strong>Fully insured</strong> — comprehensive liability and WSIB coverage protects everyone on-site",),
            ("<strong>Preferred partner rates</strong> — your clients get exclusive pricing not available to the public",),
        ],
        "steps": [
            ("Refer or Notify", "Let us know about an upcoming project that needs moving/logistics support"),
            ("We Quote &amp; Plan", "We provide a fast, competitive quote and coordinate directly with your project timeline"),
            ("We Execute", "Our crew handles everything — clearouts, moves, placements — on your schedule"),
            ("You Get Paid", "Receive your referral commission once the job is completed successfully"),
        ],
        "models": [
            ("Referral Partner", "Send us clients and earn a commission on every completed job. Zero effort, consistent payouts."),
            ("Preferred Vendor", "We become your go-to moving partner. Bundled pricing, priority scheduling, and dedicated support."),
            ("White-Label", "We operate under your brand. Your clients see one company delivering everything seamlessly."),
        ],
        "cta_headline": "Let's Build Something Together",
        "cta_subtitle": "We'd love to explore how Saturn Star can support your construction projects. Let's set up a quick call to discuss how this partnership can work for your team.",
    },
    "corporate": {
        "codes": ["CR25", "LE25", "EM25"],
        "doc_badge": "Corporate Relocation",
        "hero_headline": "Your People. <span>Our Moves.</span> Zero Disruption.",
        "hero_subtitle": "Saturn Star Moving Company offers {company_name} a dedicated employee relocation program — making every transfer, new hire, and office move seamless for your team.",
        "problem": "Employee relocations are stressful, time-consuming, and expensive when managed ad-hoc. HR teams spend hours coordinating logistics instead of focusing on onboarding and retention.",
        "solution": "Partner with Saturn Star as your <strong>dedicated relocation partner</strong>. One call, one vendor, every employee move handled — with corporate billing, real-time tracking, and zero admin burden on your team.",
        "services": [
            ("&#8635;", "Full Employee Relocations", "Door-to-door moves for new hires, transfers, and relocating executives — packing, transport, unpacking"),
            ("&#9878;", "Onboarding Support", "Get new team members settled fast so they're focused on work, not unpacking boxes"),
            ("&#9745;", "Office &amp; Workspace Setup", "Desks, chairs, filing cabinets, equipment — delivered and arranged to your specifications"),
            ("&#9881;", "Secure Storage", "30 days free storage for employees between housing — climate-controlled and insured"),
            ("&#9998;", "Real-Time Tracking", "HR dashboard visibility on every move — status updates, ETAs, completion confirmations"),
            ("&#9041;", "Corporate Billing", "Monthly invoicing, department cost codes, and utilization reports — no employee reimbursement hassle"),
        ],
        "benefits_col1_title": "For HR &amp; Management",
        "benefits_col1": [
            ("<strong>Zero admin burden</strong> — one call, one vendor, every employee move handled end-to-end",),
            ("<strong>Budget predictability</strong> — fixed corporate rates with monthly utilization reports",),
            ("<strong>Vendor consolidation</strong> — replace ad-hoc bookings with a single reliable partner",),
            ("<strong>Employee satisfaction</strong> — smooth relocations improve retention and first impressions",),
        ],
        "benefits_col2_title": "For Your Employees",
        "benefits_col2": [
            ("<strong>Full-service moves</strong> — packing, transport, unpacking — they don't lift a finger",),
            ("<strong>Flexible scheduling</strong> — moves on their timeline, including evenings and weekends",),
            ("<strong>30 days free storage</strong> — no rush if housing timing doesn't align perfectly",),
            ("<strong>Dedicated coordinator</strong> — one person manages their entire move from start to finish",),
        ],
        "steps": [
            ("HR Notifies Us", "A quick call or email with the employee's details and timeline"),
            ("We Coordinate", "We contact the employee directly and plan every detail around their schedule"),
            ("We Execute", "Professional crew handles the move — packing, transport, unpacking, setup"),
            ("HR Gets a Report", "Completion confirmation, satisfaction survey, and invoice — all clean and documented"),
        ],
        "models": [
            ("Per-Move", "Pay per relocation with corporate rates. No commitment, no minimums — just call when you need us."),
            ("Volume Contract", "Tiered pricing based on annual volume. The more moves, the deeper the discount."),
            ("Dedicated Account", "Assigned account manager, custom SLA, priority scheduling, and quarterly business reviews."),
        ],
        "cta_headline": "Let's Make Relocations Effortless",
        "cta_subtitle": "We'd love to put together a relocation program tailored to {company_name}'s needs. Let's set up a quick call to discuss how this partnership can work for your team.",
    },
    "referral": {
        "codes": ["FH25", "DL25", "MB25", "HB25", "EL25", "RH25", "CH25", "IR25"],
        "doc_badge": "Referral Partnership",
        "hero_headline": "Your Clients. <span>Our Care.</span> A Seamless Referral.",
        "hero_subtitle": "Saturn Star Moving Company wants to be the name {company_name} trusts when your clients need professional, insured moving services — with zero effort on your part.",
        "problem": "Your clients often need to move — whether it's a life transition, a new home, or an emergency situation. Finding a reliable mover to recommend can be hit-or-miss, and a bad referral reflects on you.",
        "solution": "Partner with Saturn Star as your <strong>trusted referral partner</strong>. Hand your client a card, we handle everything from there — professionally, on time, fully insured. You look great, they're taken care of.",
        "services": [
            ("&#8635;", "Full-Service Moves", "Packing, transport, unpacking, furniture assembly — your clients don't lift a finger"),
            ("&#9878;", "Emergency &amp; Rush Moves", "48-hour priority scheduling for urgent situations — we move fast when it matters"),
            ("&#9745;", "Estate Cleanouts", "Full property clearout to broom-swept condition — distribution, donation coordination, disposal"),
            ("&#9881;", "Secure Storage", "Climate-controlled storage for any duration — 30 days free for referred clients"),
            ("&#9998;", "Senior &amp; Sensitive Moves", "Patient, trained crews for downsizing, assisted living transitions, and delicate situations"),
            ("&#9041;", "Documentation &amp; Insurance", "$2M liability coverage, itemized handling records, certificates of insurance on file"),
        ],
        "benefits_col1_title": "For Your Practice",
        "benefits_col1": [
            ("<strong>Referral revenue</strong> — earn a commission on every completed move from your referrals",),
            ("<strong>Zero effort</strong> — hand your client a card, we handle everything from there",),
            ("<strong>Enhanced reputation</strong> — recommending a reliable partner makes you look thorough and caring",),
            ("<strong>One number</strong> — 226-724-1730 — your staff never has to research movers again",),
        ],
        "benefits_col2_title": "For Your Clients",
        "benefits_col2": [
            ("<strong>Trusted recommendation</strong> — they're hiring a mover YOU vouch for, not a random Google result",),
            ("<strong>Preferred pricing</strong> — 15% partner discount not available to the public",),
            ("<strong>Fully insured</strong> — $2M liability coverage protects their belongings completely",),
            ("<strong>White-glove service</strong> — professional crews who treat their home with respect",),
        ],
        "steps": [
            ("Hand Off a Card", "Keep referral cards at your front desk — clients take one when they're ready"),
            ("Client Calls Us", "They call 226-724-1730 and mention your firm — we take it from there"),
            ("We Handle Everything", "Quote, scheduling, packing, moving, unpacking — seamless and professional"),
            ("You Earn a Commission", "We send you a referral payout once the move is completed successfully"),
        ],
        "models": [
            ("Referral Partner", "Hand out cards, earn a commission on every completed job. Zero effort, consistent payouts."),
            ("Preferred Vendor", "We become your recommended mover. Priority scheduling, dedicated support, and co-branded materials."),
            ("Co-Branded", "Your logo alongside ours on referral materials. Your clients see a unified, professional service."),
        ],
        "cta_headline": "Let's Take Care of Your Clients Together",
        "cta_subtitle": "We'd love to set up a simple referral arrangement with {company_name}. No contracts, no minimums — just a trusted partner your clients can count on.",
    },
    "restoration": {
        "codes": ["IR25"],
        "doc_badge": "Restoration Partnership",
        "hero_headline": "Your Claims. <span>Our Pack-Outs.</span> Faster Restoration.",
        "hero_subtitle": "Saturn Star Moving Company provides {company_name} with professional contents moving and storage for insurance claims — documented, insured, and on your timeline.",
        "problem": "After a fire, flood, or disaster, contents need to come out before restoration can begin — and they need to go back in when it's done. Coordinating this with unreliable movers delays the entire claim.",
        "solution": "Partner with Saturn Star as your <strong>dedicated contents moving partner</strong>. Emergency pack-outs within 4 hours, photo-documented inventory for claims, and careful pack-back to pre-loss layout.",
        "services": [
            ("&#8635;", "Emergency Pack-Outs", "Contents removed within 4 hours of dispatch — available 24/7 for urgent claims"),
            ("&#9878;", "Photo Documentation", "Every item inventoried and photographed for insurance claims — saves adjusters hours"),
            ("&#9745;", "Climate-Controlled Storage", "Secure, insured storage during the entire restoration period — no time pressure"),
            ("&#9881;", "Pack-Back &amp; Placement", "Careful return of all contents to pre-loss layout once restoration is complete"),
            ("&#9998;", "Specialty Item Handling", "Electronics, antiques, fragile collections — trained crews with appropriate materials"),
            ("&#9041;", "Claims-Ready Reporting", "Documentation formatted for insurance submission — inventory lists, condition reports, photos"),
        ],
        "benefits_col1_title": "For Your Company",
        "benefits_col1": [
            ("<strong>Faster claim resolution</strong> — contents out quickly means restoration starts sooner",),
            ("<strong>Reduced liability</strong> — fully insured handling with $2M coverage and WSIB",),
            ("<strong>One vendor</strong> — consistent crews who learn your process and follow your protocols",),
            ("<strong>Direct billing</strong> — invoice per job or monthly statement, formatted for insurance",),
        ],
        "benefits_col2_title": "For Your Clients",
        "benefits_col2": [
            ("<strong>Peace of mind</strong> — their belongings are professionally handled and documented",),
            ("<strong>Careful handling</strong> — trained crews who understand the emotional weight of disaster recovery",),
            ("<strong>Transparent process</strong> — they can see the inventory and know exactly where everything is",),
            ("<strong>Pre-loss restoration</strong> — everything goes back exactly where it was before the loss",),
        ],
        "steps": [
            ("You Dispatch Us", "One call — 226-724-1730 — and we're mobilizing within the hour"),
            ("We Pack &amp; Document", "Contents removed, inventoried, photographed — documentation ready for the adjuster"),
            ("We Store Securely", "Climate-controlled, insured storage until restoration is complete"),
            ("We Pack Back", "Everything returned to pre-loss layout — your client's home is whole again"),
        ],
        "models": [
            ("Per-Claim", "Pay per job with preferred vendor pricing. No contract needed — just call when a claim comes in."),
            ("Preferred Vendor", "Priority dispatch, dedicated account manager, and volume pricing for consistent referrals."),
            ("Emergency Retainer", "Guaranteed 2-hour response time with a small monthly retainer. First call, every time."),
        ],
        "cta_headline": "Let's Speed Up Your Restorations",
        "cta_subtitle": "We'd love to set up a vendor relationship with {company_name}. Let's talk about how we can make contents handling one less thing your team worries about.",
    },
    "default": {
        "codes": [],
        "doc_badge": "Partnership Proposal",
        "hero_headline": "Your Business. <span>Our Support.</span> A Partnership That Works.",
        "hero_subtitle": "Saturn Star Moving Company is proposing a partnership with {company_name} — professional, insured moving services for your team, your clients, and your operations.",
        "problem": "Moving logistics — whether for employees, clients, or office operations — can be time-consuming and unreliable. Finding a trustworthy vendor shouldn't be another thing on your plate.",
        "solution": "Partner with Saturn Star as your <strong>go-to moving partner</strong>. One call, one vendor — we handle everything from employee relocations to office moves, fully insured and on your timeline.",
        "services": [
            ("&#8635;", "Employee Relocations", "Full-service moves for staff — packing, transport, unpacking, storage"),
            ("&#9878;", "Office &amp; Commercial Moves", "Desks, equipment, files — relocated with minimal disruption to operations"),
            ("&#9745;", "Client Referral Program", "Professional moving services your clients can trust — reflects well on your brand"),
            ("&#9881;", "Storage Solutions", "Climate-controlled, insured storage for any duration — 30 days free for partners"),
            ("&#9998;", "Event &amp; Setup Logistics", "Furniture delivery, event setup, teardown — we handle the heavy lifting"),
            ("&#9041;", "Full Insurance Coverage", "$2M liability, WSIB compliant — certificates of insurance always on file"),
        ],
        "benefits_col1_title": "For Your Organization",
        "benefits_col1": [
            ("<strong>One reliable vendor</strong> — stop searching for movers every time you need one",),
            ("<strong>Corporate pricing</strong> — 15-25% below retail rates for all moves",),
            ("<strong>Priority scheduling</strong> — your projects jump to the front of the line",),
            ("<strong>Zero hassle billing</strong> — monthly invoicing, department codes, utilization reports",),
        ],
        "benefits_col2_title": "For Your People",
        "benefits_col2": [
            ("<strong>Full-service experience</strong> — packing, moving, unpacking — they don't lift a finger",),
            ("<strong>Flexible scheduling</strong> — evenings, weekends, whatever works for their timeline",),
            ("<strong>Fully insured</strong> — $2M liability coverage protects every move",),
            ("<strong>Dedicated support</strong> — one coordinator manages their entire move start to finish",),
        ],
        "steps": [
            ("Reach Out", "Call 226-724-1730 or email — tell us what you need"),
            ("We Quote &amp; Plan", "Fast, competitive quote tailored to your specific situation"),
            ("We Execute", "Professional crew handles everything — on your schedule, on budget"),
            ("You're Covered", "Completion confirmation, invoice, and satisfaction follow-up"),
        ],
        "models": [
            ("Referral Partner", "Send us clients and earn a commission on every completed job. Zero effort, consistent payouts."),
            ("Preferred Vendor", "We become your go-to mover. Bundled pricing, priority scheduling, and dedicated support."),
            ("Custom Program", "Tailored to your specific needs — volume contracts, SLAs, co-branding, whatever works."),
        ],
        "cta_headline": "Let's Start a Conversation",
        "cta_subtitle": "We'd love to explore how Saturn Star can support {company_name}. No commitment — just a quick call to see if there's a fit.",
    },
}


def _get_variant(industry_code: str) -> dict:
    """Get the content variant for an industry code."""
    # Check specific overrides first (IR25 gets restoration, not referral)
    if industry_code == "IR25":
        return CONTENT_VARIANTS["restoration"]
    for key, variant in CONTENT_VARIANTS.items():
        if industry_code in variant.get("codes", []):
            return variant
    return CONTENT_VARIANTS["default"]


def _load_logo_base64() -> str:
    """Load the Saturn Star logo as a base64 data URI."""
    if not LOGO_PATH.exists():
        return ""
    data = LOGO_PATH.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _render_services(services: list[tuple]) -> str:
    """Render the 6 service items as HTML."""
    items = []
    for icon, title, desc in services:
        items.append(f"""                <div class="service-item">
                    <div class="service-icon">{icon}</div>
                    <div>
                        <strong>{title}</strong>
                        <span>{desc}</span>
                    </div>
                </div>""")
    return "\n".join(items)


def _render_benefits(benefits: list[tuple]) -> str:
    """Render benefit items as HTML."""
    items = []
    for (text,) in benefits:
        items.append(f"""                    <div class="benefit-item">
                        <div class="benefit-check">&#10003;</div>
                        <p>{text}</p>
                    </div>""")
    return "\n".join(items)


def _render_steps(steps: list[tuple]) -> str:
    """Render the 4 how-it-works steps."""
    items = []
    for i, (title, desc) in enumerate(steps, 1):
        items.append(f"""                <div class="step">
                    <div class="step-number">{i}</div>
                    <strong>{title}</strong>
                    <span>{desc}</span>
                </div>""")
    return "\n".join(items)


def _render_models(models: list[tuple]) -> str:
    """Render partnership model cards."""
    items = []
    for title, desc in models:
        items.append(f"""                <div class="model-item">
                    <strong>{title}</strong>
                    <span>{desc}</span>
                </div>""")
    return "\n".join(items)


def _build_html(company_name: str, contact_name: str, variant: dict) -> str:
    """Build the full HTML one-pager from a content variant."""
    logo_src = _load_logo_base64()
    today = date.today().strftime("%B %Y")

    # Substitute {company_name} in variant text
    hero_headline = variant["hero_headline"]
    hero_subtitle = variant["hero_subtitle"].format(company_name=company_name)
    cta_subtitle = variant["cta_subtitle"].format(company_name=company_name)

    services_html = _render_services(variant["services"])
    benefits1_html = _render_benefits(variant["benefits_col1"])
    benefits2_html = _render_benefits(variant["benefits_col2"])
    steps_html = _render_steps(variant["steps"])
    models_html = _render_models(variant["models"])

    # Prepared for line
    prepared_for = f"Confidential — Prepared for {company_name}"
    if contact_name and contact_name.lower() != "there":
        prepared_for = f"Confidential — Prepared for {contact_name} at {company_name}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Partnership Proposal - Saturn Star Moving Company x {company_name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #1a2744; line-height: 1.6; background: #fff; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 40px; }}
        .header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 35px; padding-bottom: 25px; border-bottom: 3px solid #f5a623; }}
        .logo-section {{ display: flex; align-items: center; gap: 15px; }}
        .logo-img {{ width: 130px; height: auto; }}
        .company-info p {{ color: #666; font-size: 13px; margin-top: 4px; }}
        .doc-info {{ text-align: right; }}
        .doc-info h2 {{ color: #1a2744; font-size: 22px; font-weight: 700; margin-bottom: 5px; line-height: 1.2; }}
        .doc-info p {{ color: #666; font-size: 13px; }}
        .doc-badge {{ background: #f5a623; color: #1a2744; padding: 4px 14px; border-radius: 5px; font-weight: 700; font-size: 11px; display: inline-block; margin-top: 8px; text-transform: uppercase; letter-spacing: 0.5px; }}
        .hero {{ background: linear-gradient(135deg, #1a2744 0%, #2d3a52 100%); border-radius: 15px; padding: 35px; color: white; margin-bottom: 30px; text-align: center; }}
        .hero h1 {{ font-size: 26px; font-weight: 800; margin-bottom: 10px; letter-spacing: -0.5px; }}
        .hero h1 span {{ color: #f5a623; }}
        .hero p {{ font-size: 15px; opacity: 0.9; max-width: 600px; margin: 0 auto; line-height: 1.5; }}
        .opportunity {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }}
        .opp-card {{ background: #f8f9fa; padding: 22px; border-radius: 10px; border-left: 4px solid #f5a623; }}
        .opp-card h3 {{ color: #1a2744; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; font-weight: 700; }}
        .opp-card p {{ color: #444; font-size: 14px; }}
        .section {{ margin-bottom: 30px; }}
        .section h3 {{ color: #1a2744; font-size: 17px; font-weight: 700; margin-bottom: 18px; padding-bottom: 8px; border-bottom: 2px solid #eee; }}
        .services-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
        .service-item {{ display: flex; align-items: flex-start; gap: 12px; padding: 14px; background: #f8f9fa; border-radius: 8px; }}
        .service-icon {{ width: 36px; height: 36px; background: #f5a623; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 16px; flex-shrink: 0; }}
        .service-item strong {{ display: block; font-size: 13px; color: #1a2744; margin-bottom: 2px; }}
        .service-item span {{ font-size: 12px; color: #666; line-height: 1.4; }}
        .benefits-section {{ background: linear-gradient(135deg, #1a2744 0%, #2d3a52 100%); border-radius: 15px; padding: 30px; color: white; margin-bottom: 30px; }}
        .benefits-section h3 {{ color: #f5a623; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 20px; border-bottom: none; padding-bottom: 0; }}
        .benefits-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .benefit-col h4 {{ color: #f5a623; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; font-weight: 700; }}
        .benefit-item {{ display: flex; align-items: flex-start; gap: 10px; margin-bottom: 12px; }}
        .benefit-check {{ width: 20px; height: 20px; background: rgba(245,166,35,0.3); border: 1.5px solid #f5a623; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #f5a623; font-size: 11px; font-weight: bold; flex-shrink: 0; margin-top: 1px; }}
        .benefit-item p {{ font-size: 13px; line-height: 1.4; opacity: 0.95; }}
        .how-it-works {{ background: linear-gradient(135deg, #f5a623 0%, #e8941f 100%); padding: 25px; border-radius: 10px; color: #1a2744; margin-bottom: 30px; }}
        .how-it-works h3 {{ font-size: 14px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 18px; border-bottom: none; padding-bottom: 0; }}
        .steps-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; }}
        .step {{ text-align: center; }}
        .step-number {{ width: 40px; height: 40px; background: #1a2744; color: #f5a623; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 800; margin: 0 auto 10px; }}
        .step strong {{ display: block; font-size: 12px; margin-bottom: 3px; }}
        .step span {{ font-size: 11px; opacity: 0.8; line-height: 1.3; }}
        .credentials {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-bottom: 30px; }}
        .credential-card {{ background: #e8f5e9; border: 2px solid #4caf50; border-radius: 10px; padding: 18px; text-align: center; }}
        .credential-card .icon {{ font-size: 28px; margin-bottom: 8px; }}
        .credential-card h5 {{ color: #2e7d32; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }}
        .credential-card p {{ color: #555; font-size: 11px; line-height: 1.4; }}
        .partnership-models {{ background: #e3f2fd; border: 2px solid #1a2744; border-radius: 10px; padding: 22px; margin-bottom: 30px; }}
        .partnership-models h4 {{ color: #1a2744; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 15px; font-weight: 700; }}
        .model-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }}
        .model-item {{ background: white; border-radius: 8px; padding: 15px; text-align: center; border: 1px solid #ddd; }}
        .model-item strong {{ display: block; font-size: 13px; color: #1a2744; margin-bottom: 5px; }}
        .model-item span {{ font-size: 11px; color: #666; line-height: 1.4; }}
        .cta {{ background: #f8f9fa; border: 2px solid #f5a623; border-radius: 15px; padding: 30px; text-align: center; margin-bottom: 30px; }}
        .cta h3 {{ color: #1a2744; font-size: 20px; font-weight: 700; margin-bottom: 8px; border-bottom: none; padding-bottom: 0; }}
        .cta p {{ color: #555; font-size: 14px; margin-bottom: 20px; }}
        .contact-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; }}
        .contact-item {{ background: #1a2744; color: white; padding: 15px; border-radius: 8px; }}
        .contact-item .label {{ color: #f5a623; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; font-weight: 600; }}
        .contact-item .value {{ font-size: 13px; font-weight: 600; }}
        .footer {{ text-align: center; padding-top: 20px; border-top: 3px solid #f5a623; }}
        .footer p {{ color: #888; font-size: 12px; margin-bottom: 3px; }}
        .footer .tagline {{ color: #f5a623; font-weight: 700; font-size: 13px; margin-top: 10px; }}
        @media print {{
            body {{ print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
            .container {{ padding: 20px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo-section">
                <img src="{logo_src}" alt="Saturn Star Moving Company" class="logo-img">
                <div class="company-info">
                    <p>Professional Commercial &amp; Residential Moving</p>
                    <p>Windsor, Ontario</p>
                    <p>business@starmovers.ca</p>
                </div>
            </div>
            <div class="doc-info">
                <h2>PARTNERSHIP<br>PROPOSAL</h2>
                <p>{today}</p>
                <div class="doc-badge">{variant["doc_badge"]}</div>
            </div>
        </div>

        <div class="hero">
            <h1>{hero_headline}</h1>
            <p>{hero_subtitle}</p>
        </div>

        <div class="opportunity">
            <div class="opp-card">
                <h3>The Problem</h3>
                <p>{variant["problem"]}</p>
            </div>
            <div class="opp-card">
                <h3>The Solution</h3>
                <p>{variant["solution"]}</p>
            </div>
        </div>

        <div class="section">
            <h3>Services We Bring to {company_name}</h3>
            <div class="services-grid">
{services_html}
            </div>
        </div>

        <div class="benefits-section">
            <h3>Why Partner with Saturn Star?</h3>
            <div class="benefits-grid">
                <div class="benefit-col">
                    <h4>{variant["benefits_col1_title"]}</h4>
{benefits1_html}
                </div>
                <div class="benefit-col">
                    <h4>{variant["benefits_col2_title"]}</h4>
{benefits2_html}
                </div>
            </div>
        </div>

        <div class="how-it-works">
            <h3>How the Partnership Works</h3>
            <div class="steps-grid">
{steps_html}
            </div>
        </div>

        <div class="credentials">
            <div class="credential-card">
                <div class="icon">&#128274;</div>
                <h5>Fully Insured</h5>
                <p>Commercial general liability insurance. COI available on request.</p>
            </div>
            <div class="credential-card">
                <div class="icon">&#9989;</div>
                <h5>WSIB Covered</h5>
                <p>Full Workplace Safety coverage for all crew members on your sites.</p>
            </div>
            <div class="credential-card">
                <div class="icon">&#11088;</div>
                <h5>Proven Track Record</h5>
                <p>500+ moves completed. 4.9/5 rating. Trusted by institutions like St. Clair College.</p>
            </div>
        </div>

        <div class="partnership-models">
            <h4>Flexible Partnership Models</h4>
            <div class="model-grid">
{models_html}
            </div>
        </div>

        <div class="cta">
            <h3>{variant["cta_headline"]}</h3>
            <p>{cta_subtitle}</p>
            <div class="contact-grid">
                <div class="contact-item">
                    <div class="label">Email</div>
                    <div class="value">business@starmovers.ca</div>
                </div>
                <div class="contact-item">
                    <div class="label">Phone</div>
                    <div class="value">(226) 724-1730</div>
                </div>
                <div class="contact-item">
                    <div class="label">Location</div>
                    <div class="value">Windsor, Ontario</div>
                </div>
            </div>
        </div>

        <div class="footer">
            <p><strong>Saturn Star Moving Company</strong></p>
            <p>Windsor, Ontario | business@starmovers.ca</p>
            <p class="tagline">Professional Moving Services You Can Trust</p>
            <p style="margin-top: 10px; font-size: 11px; color: #aaa;">{prepared_for}</p>
        </div>
    </div>
</body>
</html>"""


def _html_to_pdf(html_content: str, pdf_path: Path) -> bool:
    """Convert HTML string to PDF using xhtml2pdf. Returns True on success."""
    try:
        from xhtml2pdf import pisa
        with open(pdf_path, "wb") as f:
            result = pisa.CreatePDF(BytesIO(html_content.encode("utf-8")), dest=f)
        if result.err:
            logger.warning("PDF conversion had %d errors", result.err)
            return False
        return True
    except ImportError:
        logger.warning("xhtml2pdf not installed — skipping PDF generation")
        return False
    except Exception as e:
        logger.warning("PDF conversion failed: %s", e)
        return False


def generate_onepager(contact_id: int) -> dict:
    """Generate a customized one-pager for a contact.

    Returns {html_path, pdf_path, company_name, industry_code, variant_used}.
    """
    conn = sqlite3.connect(str(cfg.db_path))
    conn.row_factory = sqlite3.Row
    contact = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    conn.close()

    if not contact:
        return {"error": f"Contact #{contact_id} not found"}

    company_name = contact["company_name"]
    contact_name = contact["contact_name"] or ""
    industry_code = contact["industry_code"] or ""

    variant = _get_variant(industry_code)

    # Generate HTML
    html = _build_html(company_name, contact_name, variant)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Clean filename
    safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in company_name).strip()
    safe_name = safe_name.replace(" ", "_")[:50]

    html_filename = f"OnePager_{safe_name}_{contact_id}.html"
    pdf_filename = f"OnePager_{safe_name}_{contact_id}.pdf"

    html_path = OUTPUT_DIR / html_filename
    pdf_path = OUTPUT_DIR / pdf_filename

    # Save HTML
    html_path.write_text(html, encoding="utf-8")
    logger.info("One-pager HTML saved: %s", html_path)

    # Convert to PDF
    pdf_ok = _html_to_pdf(html, pdf_path)
    if pdf_ok:
        logger.info("One-pager PDF saved: %s", pdf_path)

    return {
        "html_path": str(html_path),
        "html_filename": html_filename,
        "pdf_path": str(pdf_path) if pdf_ok else None,
        "pdf_filename": pdf_filename if pdf_ok else None,
        "company_name": company_name,
        "contact_name": contact_name,
        "industry_code": industry_code,
        "variant_used": [k for k, v in CONTENT_VARIANTS.items()
                         if v is variant][0],
    }


def list_onepagers() -> list[dict]:
    """List all generated one-pagers."""
    if not OUTPUT_DIR.exists():
        return []
    results = []
    for f in sorted(OUTPUT_DIR.glob("OnePager_*.html")):
        pdf = f.with_suffix(".pdf")
        results.append({
            "html_filename": f.name,
            "pdf_filename": pdf.name if pdf.exists() else None,
            "created": f.stat().st_mtime,
        })
    return results


if __name__ == "__main__":
    import sys
    cid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    result = generate_onepager(cid)
    print(result)
