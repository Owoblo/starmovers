"""Hybrid template engine: tier-based templates + GPT personalization.

Converts direct mail letter templates to email format, then uses GPT to
personalize the opening/closing per contact while keeping core offers exact.

Industry-specific GPT prompts ensure tone matches what actually moves
each type of professional. The universal structure:
  1. Open with THEIR client's situation, not yours
  2. Position yourself as something that makes THEM look better
  3. Make the next step absurdly easy (reply yes, QR code, text a number)
"""

import logging
import sqlite3

from openai import OpenAI

from outreach_engine.config import cfg

logger = logging.getLogger(__name__)

# ── Industry-specific GPT instructions ──
# These tell GPT the *psychology* of each industry so personalization
# hits the right emotional register.

INDUSTRY_GPT_VOICE: dict[str, str] = {
    "FH25": """TONE: 70% empathy and service, 20% professionalism/reliability, 10% logistics.
Their clients are grieving families who need to clear out a loved one's home quickly. The funeral
director wants to be seen as CARING, not selling. They want to be the person who made that process
easier. Your message needs to position Saturn Star as an extension of the care they already provide.
You're NOT selling moving services — you're offering them a way to say "we've got someone who handles
this with dignity." The first thing they should feel is "this person understands my world."
Do NOT use sales language. Do NOT mention revenue, commissions, or partnership bonuses. Think of it
as a tasteful, quiet offering — the way you'd hand someone a tissue, not a business card.
No flashy language. Warm but restrained. Professional but human.""",

    "DL25": """TONE: 60% competence and speed, 25% discretion, 15% ease of referral.
Their clients are in chaos — going through divorce, splitting households, sometimes fleeing.
The lawyer wants to look competent by having resources ready. They do NOT care about your
brand story or partnership revenue. They care that referring you reflects well on them and
doesn't create more problems. Your message should say: "when your client needs to move fast,
here's one less thing you need to figure out." Emphasize: we're quiet, fast, insured, and
the referral takes zero effort on their part. No flashy language. No emojis. Direct and calm.""",

    "MB25": """TONE: 50% value-add for their client experience, 30% partnership/mutual referral energy,
20% professionalism. Mortgage brokers are transactional — they think in terms of "what makes me look
good and brings me more business." Their clients just bought a home and need to move in by closing.
Happy clients remember who made it easy — and send referrals back to the broker. Your angle is:
"we make your clients' experience seamless, and happy clients remember who made it easy."
A co-branded referral card or a "congratulations on your new home" package that includes your info
alongside theirs would hit perfectly. This is the one industry where mutual referral language WORKS.
Be upbeat but professional. Partnership energy, not charity.""",

    "CC25": """TONE: 65% professionalism and process, 25% insurance/damage protection, 10% volume relationship.
Condo boards and property managers deal with move-ins and move-outs constantly. Their nightmare is
damaged hallways, elevator holds not being respected, and complaints from residents. Your message
should lead with "we know the rules" — elevator booking, floor protection, time windows. Offer a
condo-specific move checklist they can hand to residents. That positions you as the ONLY mover who
actually respects their building. They want ONE number they can call and forget about it.
Straightforward and dependable. Like a contractor who just shows up and does the job right.""",

    "EL25": """TONE: 60% efficiency and speed, 25% sensitivity to the situation, 15% reliability.
Estate lawyers deal with families settling a deceased person's affairs. The lawyer's concern is
logistical — they need the estate cleared so the property can be sold or transferred. Your message:
"When your client needs an estate cleared for probate or sale, we handle it respectfully and on
your timeline." Give them a one-pager they can include in their client intake packet. Emphasize:
documented handling, multi-location delivery, estate cleanout to broom-swept. The lawyer wants
to hand off this problem completely.""",

    "RH25": """TONE: 75% empathy and patience, 15% reliability, 10% downsizing expertise.
Seniors moving into care homes are often emotional, overwhelmed, and physically limited. The care
home staff wants movers who won't rush, who'll be kind to the resident, and who'll handle belongings
with respect. Your message should emphasize that your crew understands this is more than a move —
it's a life transition. Offer a senior-specific service tier. Not about speed — about care.
A dresser isn't just furniture, it's 40 years of marriage.""",

    "CH25": """TONE: 75% service to their community, 15% trust/values alignment, 10% practicality.
Pastors and church administrators have congregation members going through life transitions — new
marriages, job relocations, downsizing seniors, families in crisis. They want to be the shepherd
who has answers. Your angle: "When someone in your congregation needs help moving, we want to be
the name you give them." John's family background is in ministry — this is DEEPLY authentic.
A personal letter referencing your upbringing in the church would hit differently than a generic
mailer. This should feel like a fellow believer offering to serve, not a business soliciting.
Warm, community-minded, faithful. Not corporate.""",

    "CU25": """TONE: 80% relationship and community, 15% reliability, 5% pricing.
Cultural and ethnic clubs serve tight-knit communities where word-of-mouth is everything. They
won't respond to corporate outreach — they respond to relationships. Your outreach should feel
like a handshake, not a pitch. Less about mail and more about showing up — sponsoring an event,
posting on their community board, offering a member discount. Write like you're introducing
yourself to a neighbor, not selling to a prospect.""",

    "HB25": """TONE: 50% enhancing their client experience, 30% partnership/co-marketing, 20% reliability.
Home builders want their buyers to have a seamless move-in. A bad moving experience taints the
excitement of a new build. Your angle: "You built their dream home — let us make sure moving day
matches that feeling." A co-branded welcome package for new homeowners would be powerful. They
care about their brand — show them you'll enhance it, not diminish it. Professional, polished,
partnership-oriented.""",

    "IR25": """TONE: 65% process and documentation, 20% speed, 15% care with damaged/sensitive items.
After a fire, flood, or disaster, adjusters need contents moved out for restoration and moved back
in after. They want a mover who understands the claims process and can document everything. Your
message should reference pack-outs, content inventory, and working within insurance timelines.
This is a HIGH-VALUE niche — could be very lucrative recurring partnership. Be precise, process-
oriented, and professional. Show you understand the insurance workflow.""",

    "LE25": """TONE: 55% turnkey relocation solution, 25% corporate billing/invoicing, 20% employee experience.
When companies recruit talent from outside Windsor, a smooth relocation experience matters for
retention. HR doesn't want to deal with logistics — they want to hand it off. Position yourself
as their relocation partner, not just a mover. Offer corporate rates and a dedicated contact.
Professional, corporate tone. They think in terms of employee satisfaction scores and retention.""",

    "UN25": """TONE: 50% affordability and student-friendly pricing, 30% reliability during peak periods,
20% partnership with the institution. Thousands of students move in and out every semester.
University housing offices and international student services need reliable movers they can
recommend. Offer a student rate and get on the university's recommended vendor list. Friendly,
approachable, and institutional at the same time.""",

    "HO25": """TONE: 60% sensitivity and care, 25% reliability, 15% specialized handling.
Hospitals discharge patients who sometimes can't return to their previous living situation.
Healthcare systems also relocate departments and offices. Two angles: patient discharge
coordinators who need to help people move to assisted living, and facilities managers handling
internal moves. Be sensitive about the patient angle, professional about the facilities angle.""",

    "HT25": """TONE: 55% logistics capability, 30% discretion and professionalism, 15% flexible scheduling.
Hotels renovate rooms, relocate furniture between properties, and sometimes help long-term guests
transition. Your angle is about being available on their timeline, handling bulk furniture moves,
and not disrupting guest experience. They care about operational smoothness above all.""",

    "GV25": """TONE: 60% compliance and process, 25% competitive pricing, 15% reliability.
Government procurement is slow and bureaucratic, but once you're in, you're in for a long time.
They need vendors who can handle paperwork, provide quotes that fit budget cycles, and meet
accessibility requirements. This is a longer play. Your outreach should be formal, referencing
any relevant certifications (WSIB, insurance). They need to justify the vendor choice to someone.""",

    "EM25": """TONE: 70% capability and logistics, 20% insurance/liability coverage, 10% project management.
Engineering and manufacturing companies occasionally relocate offices, equipment, or warehouses.
Every hour of downtime costs money. Lead with commercial moving credentials — can you handle heavy
equipment, do you have the right insurance, can you work overnight or weekends to minimize disruption?
A more formal proposal-style outreach works here. Professional, capability-focused.""",

    "NPWE25": """TONE: 60% community partnership, 25% affordability, 15% reliability.
Nonprofits move offices, distribute donated goods, and set up events. They need affordable,
reliable help and they appreciate community-minded businesses. Offering a nonprofit discount or
volunteering for a local charity move would build massive goodwill and word-of-mouth. They
stretch every dollar. Be genuine about community, not performative.""",

    "NPCK25": """TONE: 60% community partnership, 25% affordability, 15% reliability.
Nonprofits move offices, distribute donated goods, and set up events. They need affordable,
reliable help and they appreciate community-minded businesses. Offering a nonprofit discount or
volunteering for a local charity move would build massive goodwill and word-of-mouth. They
stretch every dollar. Be genuine about community, not performative.""",

    "SC25": """TONE: 70% community presence, 20% fun/approachable brand, 10% reliability.
Sports clubs are less about direct referrals and more about brand presence. Sponsoring a local
team, having your logo on jerseys, setting up at tournaments. This is a marketing play more
than a direct referral play. Be casual, community-oriented, and enthusiastic about local sports.
Less formal than other industries.""",

    "HOT25": """TONE: 80% direct and action-oriented, 15% professionalism, 5% relationship.
These are already warm leads with active signals. They need the fastest, most direct outreach.
No fancy packaging needed, just speed and a clear call to action. Get to the point immediately.
What can you do, when can you do it, here's the number to call. Zero fluff.""",

    "CR25": """TONE: 60% proof/social proof, 25% logistics capability, 15% partnership value.
You're reaching out to HR or a relocation coordinator BECAUSE one of their employees just
used our services. This is warm outreach — you have proof you already serve their people.
Lead with the specific move (without naming the employee): "We recently helped one of your
team members relocate from [City A] to [City B]." Then pivot to the partnership offer:
corporate rates, dedicated account manager, simplified billing. This should feel like a
natural escalation — "we're already doing this, let's make it official." Professional,
corporate, confident. Not salesy — you have social proof on your side.""",

    "GH25": """TONE: 60% local pride and project awareness, 25% logistics capability, 15% corporate partnership.
These are companies working on the Gordie Howe International Bridge — the biggest infrastructure
project in Windsor's history. They have workers relocating to Windsor, offices being set up,
furniture and equipment moving between sites. You KNOW about the bridge project. Lead with
congratulations on the project, then pivot to practical moving needs: employee relocations into
Windsor, office/workspace setup, furniture moves within facilities, storage for teams in transition.
Do NOT mention grief, estates, families, or emotional transitions. This is purely commercial and
logistical. Professional, confident, locally aware. You're the local moving company that understands
the project and can handle their people's needs.""",

    "LC25": """TONE: 55% practical and no-nonsense, 30% local reliability, 15% flexibility.
These are local construction, excavating, paving, and infrastructure companies. They build
roads, bridges, buildings, sewers. They do NOT have 'clients' or 'families' or 'tenants.'
IMPORTANT: Do NOT mention grief, families, tenants, emotional transitions, or life changes.
These are CONSTRUCTION COMPANIES. The opening should reference their WORK — their projects,
their crews, their busy schedule, the construction boom in Windsor-Essex. Be direct and
practical: we move stuff, we're local, we're available, we're insured. They value speed,
flexibility (evenings/weekends), and not having to explain things twice. Think like a
contractor talking to another contractor — no fluff, no feelings.""",

    "MT25": """TONE: 50% mutual benefit and partnership, 30% approachability, 20% local community.
These are media outlets (radio stations, newspapers, websites), tourism boards, and airports.
Two angles: (1) practical moving services for their staff/office, and (2) sponsorship and
content partnership — they have audiences, you have a service. Keep it casual and short.
IMPORTANT: Do NOT mention grief, families, emotional weight, transitions, or navigating life
changes. These are BUSINESSES, not counseling services. The opening should reference their
BUSINESS — their audience reach, their role in the community, their content. For a radio
station: mention their listeners. For a newspaper: mention their readers. For tourism: mention
visitors relocating. Be the friendly local business proposing a win-win, not a therapist.""",
}

# ── Base email templates ──
# Industries with deep psychology profiles (FH25, DL25, MB25, CC25) get
# their own templates. Others fall through to tier-based templates.

TIER_TEMPLATES: dict[str, dict] = {
    "FH25": {
        "subject": "A resource for families you serve — {company_name}",
        "body": """Hi {contact_name},

{personalized_opening}

When a family comes to you, they're carrying more than grief — they're often facing the overwhelming task of clearing out a loved one's home. Sorting belongings, coordinating pickups, deciding what goes where. It's a burden that can extend their pain for weeks.

We quietly handle that part.

**What families receive:**
- Gentle, respectful estate cleanout — we treat every item like it matters, because it does
- Distribution to multiple family members across different locations
- Donation coordination with local charities for items families want to give, not discard
- Secure storage when families need time to decide
- Rush service available (48-72 hours) when timing is urgent
- Full insurance ($2M liability) — nothing is at risk

**What this means for {company_name}:**
- A simple card or folder you can hand to a grieving family — "these people will take care of it"
- We deal directly with the family from there — nothing comes back to your desk
- Dedicated line: 226-724-1730 — families can call when they're ready, no pressure
- It becomes one more way your funeral home is remembered for going above and beyond

**Track record:** 500+ moves completed, 4.9/5 rating. Families consistently mention our care in reviews.

{personalized_closing}

John Owolabi
Saturn Star Movers
226-724-1730 | business@starmovers.ca

P.S. — I'd love to drop off a small packet of cards your team can keep at the front desk — something tasteful that families can take when they're ready. Just reply "yes" and I'll bring them by.""",
    },
    "DL25": {
        "subject": "Moving resource for your family law clients — {company_name}",
        "body": """Hi {contact_name},

{personalized_opening}

When a client walks into your office, they're already overwhelmed. If they need to move — whether it's splitting a household, relocating after a settlement, or getting out quickly — the last thing you need is to scramble for a recommendation that might fall through.

We handle that.

**What your clients get:**
- 48-hour priority scheduling for urgent moves
- Discreet, unmarked crews available on request
- Full packing and unpacking — they don't have to think about it
- Secure storage if the new place isn't ready yet
- $2M liability coverage on every move

**What this means for you:**
- One referral card to hand your client — that's it
- We deal directly with the client from there — zero follow-up on your end
- Dedicated line for your office: 226-724-1730 (ask for the family law team)
- Your clients stay taken care of, and it reflects well on your practice

**Track record:** 500+ moves completed, 4.9/5 rating, 98% on-time.

{personalized_closing}

John Owolabi
Saturn Star Movers
226-724-1730 | business@starmovers.ca

P.S. — I'll drop off a stack of referral cards to your office anytime. Just reply "yes" and I'll swing by this week.""",
    },
    "MB25": {
        "subject": "Make your closings unforgettable — {company_name} x Saturn Star Movers",
        "body": """Hi {contact_name},

{personalized_opening}

Your client just got the keys. They're excited, maybe a little overwhelmed — and the last thing they want is a stressful move souring the high of closing day. When you hand them a resource that makes the move seamless, you become the person who thought of everything.

That's what we do.

**What your clients get:**
- Priority scheduling coordinated with their closing date — we move when the keys turn
- 15% Partner Discount (exclusive to your referrals, not available to the public)
- Full-service packing, unpacking, and furniture assembly — they walk into a ready home
- $2M liability coverage on every move
- 30 days free storage if closing dates shift

**What this means for you:**
- A co-branded "Congratulations on Your New Home" card with your info alongside ours — your client sees YOU as the full-service advisor
- $75 referral bonus for every client who books through you
- Happy clients remember who made it easy — and send their friends back to you
- Dedicated broker line: 226-724-1730 — one call, we handle the rest

**The numbers:** 500+ moves completed, 4.9/5 rating, 98% on-time rate.

Your Partner Code: REF-MB25

{personalized_closing}

John Owolabi
Saturn Star Movers
226-724-1730 | business@starmovers.ca

P.S. — I can have co-branded referral cards ready for your closing packages within a week. Just reply with your logo or say "yes" and I'll reach out to set it up.""",
    },
    "CC25": {
        "subject": "One number for every tenant move — {company_name}",
        "body": """Hi {contact_name},

{personalized_opening}

Every turnover is the same headache — find a mover, hope they show up, pray they don't scratch the walls or block the elevator for three hours. Then do it again next month.

We can be the one number you stop thinking about.

**What your tenants get:**
- Professional, insured crews who know building protocols
- Elevator booking coordination — we work with your schedule, not against it
- Loading dock and hallway protection included on every move
- Full packing and unpacking available
- $2M liability coverage — if something gets damaged, we cover it, no arguments

**What this means for {company_name}:**
- One vendor, one number, every turnover handled: 226-724-1730
- Building-specific rules on file — we learn your property once and follow it every time
- 15% preferred pricing on all moves (volume discounts available)
- Net-30 billing, certificate of insurance always on file
- Zero complaints from other tenants — our crews are quiet, fast, and clean

**Track record:** 500+ moves completed, 4.9/5 rating, 98% on-time. Zero damage claims in the last 12 months.

{personalized_closing}

John Owolabi
Saturn Star Movers
226-724-1730 | business@starmovers.ca

P.S. — I'd like to stop by your office for 5 minutes, drop off a card, and learn your building's specific rules so we're ready when you need us. Just reply "yes" or text 226-724-1730.""",
    },
    "A": {
        "subject": "Partnership Opportunity — Saturn Star Movers x {company_name}",
        "body": """Hi {contact_name},

{personalized_opening}

I'm reaching out because {company_name} is in a unique position to recommend trusted moving services to your {industry_context}.

We'd like to make that easy — and rewarding — for you.

**What your clients get:**
- 15% Partner Discount (exclusive, not available to the public)
- Priority scheduling within 48 hours for urgent moves
- Senior move specialists trained for downsizing and estate moves
- Full insurance coverage ($2M liability)
- White-glove service: packing, unpacking, furniture assembly

**What YOU get:**
- $75 referral bonus for every client who books
- Referral cards and a one-pager for your office — hand it off, we handle the rest
- Dedicated account manager — one call, we handle everything
- Monthly statements for easy tracking

**The numbers:** 500+ moves completed, 4.9/5 rating, 98% on-time rate.

Your Partner Code: REF-{industry_code}

{personalized_closing}

John Owolabi
Founder & CEO, Saturn Star Movers
226-724-1730 | business@starmovers.ca

P.S. — Reply "yes" and I'll have referral cards at your office this week.""",
        "industry_context": {
            "EL25": "estate clients managing property and belongings",
            "MB25": "new homeowners closing on their properties",
        },
    },
    "B": {
        "subject": "Preferred Vendor Partnership — Saturn Star Movers + {company_name}",
        "body": """Hi {contact_name},

{personalized_opening}

I'd like to propose a preferred vendor arrangement between Saturn Star Movers and {company_name}.

**Vendor Program Benefits:**
- 15% below retail pricing for all moves
- Priority scheduling
- Net-30 billing (no deposits required)
- Dedicated account representative
- Certificate of insurance always on file

**Why this works for {company_name}:**
{industry_specific}

**Free Trial:** We'll handle your first referral move free (up to $500 value) — no commitment, no risk.

Your Vendor Code: B2B-{industry_code}

{personalized_closing}

John Owolabi
Founder & CEO, Saturn Star Movers
226-724-1730 | business@starmovers.ca""",
        "industry_specific": {
            "HB25": "We coordinate with your closing dates and handle new homeowner move-ins seamlessly. Your buyers get white-glove service that reflects well on your brand.",
            "IR25": "We offer 4-hour emergency response for restoration moves. When a claim requires contents removal, we're there fast with documented handling.",
            "CC25": "We handle elevator booking, loading dock protocols, and building-specific rules. Your residents get professional moves without disrupting other tenants.",
        },
    },
    "C": {
        "subject": "Employee Relocation Program — Saturn Star Movers for {company_name}",
        "body": """Hi {contact_name},

{personalized_opening}

I'm reaching out about a corporate relocation program designed specifically for organizations like {company_name}.

**Employee Benefits:**
- 15-25% discount (Bronze/Silver/Gold tiers based on volume)
- Full-service moves with packing and unpacking
- 30 days free storage
- Real-time move tracking

**HR Benefits:**
- Zero admin burden — we handle everything
- Dedicated account manager
- Online booking portal for employees
- Direct billing options

**Pilot Offer:** 3 FREE employee moves (up to $750 each) so you can evaluate the service risk-free.

Your Corporate Code: CORP-{industry_code}

{personalized_closing}

John Owolabi
Founder & CEO, Saturn Star Movers
226-724-1730 | business@starmovers.ca""",
        "industry_specific": {
            "LE25": "With your growing workforce, we can handle everything from executive relocations to new-hire moves.",
            "UN25": "We specialize in international student arrivals, faculty sabbatical moves, and residence turnovers.",
            "HO25": "We understand shift schedules and can move staff without disrupting patient care operations.",
            "HT25": "We get your new hires settled quickly so they're ready for their first shift — not exhausted from moving.",
            "GV25": "Fully WSIB compliant with all documentation available for public sector requirements.",
            "EM25": "With the manufacturing growth in Windsor-Essex, we help incoming workers settle in quickly.",
        },
    },
    "D": {
        "subject": "Community Partnership — Saturn Star Movers + {company_name}",
        "body": """Hi {contact_name},

{personalized_opening}

Saturn Star Movers would love to partner with {company_name} to support your members and community.

**Member Benefits:**
- 15% discount on all moving services
- Free moving supplies (up to $100 value — boxes, tape, paper)
- Senior-friendly service with patient, trained crews
- Flexible scheduling including evenings and weekends

**Organization Benefits:**
- $50 donation to {company_name} for every completed member move
- Sponsorship opportunities for your events
- Free supplies for fundraisers and community drives
- Discounted facility moving when you need it

Your Community Code: COMM-{industry_code}

{personalized_closing}

John Owolabi
Founder & CEO, Saturn Star Movers
226-724-1730 | business@starmovers.ca""",
    },
    "E": {
        "subject": "Senior Moving & Estate Services — Saturn Star Movers for {company_name}",
        "body": """Hi {contact_name},

{personalized_opening}

I'm reaching out because {company_name} works with families going through significant life transitions — and moving is often part of that journey.

**Senior Move Solutions:**
- Downsizing assistance and packing
- Crews trained for mobility-sensitive environments
- Patient, gentle handling of treasured belongings
- Full unpacking and "move-in ready" room setup
- Family coordination across multiple locations

**Estate Cleanout Services:**
- Full removal to broom-swept condition
- Donation coordination with local charities
- Item distribution to multiple family members
- Rush service available (48-72 hours)

**Preferred Facility Program:**
- 15% preferred pricing for resident/family referrals
- Priority scheduling
- $100 per-move donation to your resident activities fund
- Marketing materials (flyers, brochures) for families

Your Facility Code: CARE-{industry_code}

{personalized_closing}

John Owolabi
Founder & CEO, Saturn Star Movers
226-724-1730 | business@starmovers.ca""",
        "industry_specific": {
            "RH25": "We understand the emotional weight of transitioning from a family home. Our crews set up rooms exactly how residents want them — pictures hung, furniture placed, familiar items where they belong.",
            "FH25": "When families come to you during their most difficult days, estate cleanout is one burden we can lift. We handle everything with discretion and care.",
        },
    },
    "CH25": {
        "subject": "Serving your congregation together — {company_name}",
        "body": """Hi {contact_name},

{personalized_opening}

I grew up in a ministry family — I know what it means when someone in the congregation is going through a transition and the pastor wants to help but can't do everything. New marriages, job relocations, downsizing seniors, families in crisis — they all involve moving, and it's often the part nobody thinks about until it's urgent.

I'd love for Saturn Star Movers to be the name you give when someone in your church needs help.

**What your congregation members receive:**
- 15% church family discount on all moves
- Patient, respectful crews — especially for seniors downsizing
- Flexible scheduling including Saturdays and evenings
- Full packing and unpacking for families who need it
- Estate cleanout when a family loses someone — handled with dignity
- $2M full insurance coverage on every move

**What this means for {company_name}:**
- A resource card for your welcome desk or bulletin board — families can take one when they need it
- We deal directly with the family — nothing comes back to your office
- $50 donation to your church for every completed move from your congregation
- We can help with church facility moves too — offices, storage, event setups

**About us:** 500+ moves completed, 4.9/5 rating. Faith-driven, community-rooted.

{personalized_closing}

John Owolabi
Saturn Star Movers
226-724-1730 | business@starmovers.ca

P.S. — I'd love to drop off a small stack of cards for your welcome desk or community board. Just reply "yes" and I'll bring them by after service this Sunday.""",
    },
    "IR25": {
        "subject": "Contents moving partner for restoration claims — {company_name}",
        "body": """Hi {contact_name},

{personalized_opening}

After a fire, flood, or disaster, the contents need to come out before restoration can begin — and they need to go back in when it's done. That's where we come in.

Saturn Star Movers specializes in insurance pack-outs and contents relocation for restoration companies and adjusters in the Windsor-Essex region.

**What we handle:**
- Emergency pack-outs within 4 hours of dispatch
- Full content inventory with photo documentation for claims
- Climate-controlled storage during the restoration period
- Careful pack-back and placement to pre-loss layout
- Specialty item handling — electronics, antiques, fragile collections
- $2M liability coverage with certificate of insurance on file

**What this means for {company_name}:**
- One call, we're there — 226-724-1730 (24/7 for emergencies)
- Documentation formatted for insurance claims — saves your adjusters hours
- Direct billing options — invoice per job or monthly statement
- Consistent crews who learn your process and follow your protocols
- We work within your timeline, not ours

**The numbers:** 500+ moves completed, 4.9/5 rating, 98% on-time. Zero damage claims in the last 12 months.

Your Vendor Code: RESTORE-{industry_code}

{personalized_closing}

John Owolabi
Saturn Star Movers
226-724-1730 | business@starmovers.ca

P.S. — I'd like to set up a quick 10-minute walkthrough of our pack-out process so you can see exactly how we handle contents. Just reply "yes" and I'll send over some times.""",
    },
    "HB25": {
        "subject": "Move-in experience for your buyers — {company_name} x Saturn Star Movers",
        "body": """Hi {contact_name},

{personalized_opening}

You spend months building someone's dream home. The last thing anyone wants is for moving day to leave a bad taste — damaged floors, stressed families, a crew that doesn't respect the new build.

We'd love to be the moving company you recommend to your buyers.

**What your buyers receive:**
- Priority scheduling coordinated with their possession date
- Floor, wall, and doorframe protection on every move — we treat new builds like they deserve
- Full-service packing, unpacking, and furniture placement
- 30 days free storage if closing dates shift
- $2M liability coverage — if anything gets damaged, we cover it

**What this means for {company_name}:**
- A co-branded "Welcome to Your New Home" card with your logo alongside ours — your buyer sees you as the full-service builder
- Happy buyers remember who made it easy — and they tell their friends
- $75 referral bonus for every buyer who books through you
- Dedicated builder line: 226-724-1730 — one call, we handle the rest

**The numbers:** 500+ moves completed, 4.9/5 rating, 98% on-time rate.

Your Builder Code: BUILD-{industry_code}

{personalized_closing}

John Owolabi
Saturn Star Movers
226-724-1730 | business@starmovers.ca

P.S. — I can have co-branded welcome cards ready for your next buyer closing. Just reply with your logo or say "yes" and I'll reach out to set it up.""",
    },
    "CR25": {
        "subject": "Employee Relocation Partnership — Saturn Star Movers for {company_name}",
        "body": """Hi {contact_name},

{personalized_opening}

We recently helped one of your team members with a move from {origin_city} to {destination_city}, and the experience went so well that it got us thinking — {company_name} likely has employees relocating regularly, and we'd love to make that process seamless for your entire team.

**Corporate Relocation Program:**
- Dedicated account manager for {company_name}
- 20-30% corporate discount (tiered by volume)
- Full-service: packing, transport, unpacking, storage
- Real-time tracking dashboard for HR visibility
- Direct corporate billing — no employee reimbursement hassle
- 30 days free storage for timing flexibility

**What HR Gets:**
- One vendor, one number, every employee move handled: 226-724-1730
- Monthly utilization reports for budgeting
- Employee satisfaction surveys after each move
- Priority scheduling for urgent transfers

**Pilot Offer:** We'll handle the next 3 employee relocations at our corporate rate — no contract, no commitment. If your team loves it, we formalize the partnership.

**The numbers:** 500+ moves completed, 4.9/5 rating, 98% on-time rate across Ontario.

Your Corporate Code: CORP-{company_name_short}

{personalized_closing}

John Owolabi
Founder & CEO, Saturn Star Movers
226-724-1730 | business@starmovers.ca

P.S. — I'm happy to put together a one-page proposal tailored to {company_name}'s relocation needs. Just reply "yes" or call 226-724-1730.""",
    },
    "HOT": {
        "subject": "Moving Services Partnership — Saturn Star Movers for {company_name}",
        "body": """Hi {contact_name},

{personalized_opening}

With the exciting growth happening at {company_name}, I wanted to reach out about how Saturn Star Movers can support your moving and relocation needs.

**What We Offer:**
- Corporate relocation packages (15-25% below retail)
- Priority scheduling and dedicated account management
- Full insurance ($2M liability), WSIB compliant
- Real-time move tracking and professional crews

**Special Offer:** We'd love to do a complimentary consultation to understand your specific needs and put together a custom proposal.

{personalized_closing}

John Owolabi
Founder & CEO, Saturn Star Movers
226-724-1730 | business@starmovers.ca""",
    },
    "GH25": {
        "subject": "Moving & Logistics Partner for Gordie Howe Bridge Teams — Saturn Star Movers",
        "body": """Hi {contact_name},

{personalized_opening}

I'm John Owolabi, founder of Saturn Star Movers here in Windsor. I'm reaching out because as the bridge moves toward completion and the operations phase begins, there's going to be a lot of people relocating to Windsor — from CBSA officers to O&M staff to project teams transitioning roles.

We'd like to be the moving company your team recommends.

**What we handle:**
- Employee relocations into Windsor (full-service: packing, transport, unpacking, storage)
- Office and workspace setup — furniture, desks, filing, equipment
- Warehouse and facility moves between project sites
- Temporary storage for teams in transition (30 days free)

**Why us:**
- Based right here in Windsor — 226-724-1730
- Fully insured ($2M liability, WSIB compliant)
- 500+ moves completed, 4.9/5 rating
- Corporate billing available — no individual employee hassle
- Available 7 days a week, flexible scheduling

**Corporate Offer:** 20% discount for all {company_name}-referred moves. No contract needed — just have your people call and mention {company_name}.

{personalized_closing}

John Owolabi
Founder & CEO, Saturn Star Movers
226-724-1730 | business@starmovers.ca

P.S. — We're also available for any furniture or equipment moves within the Port of Entry buildings. Just say the word.""",
    },
    "LC25": {
        "subject": "Local Moving Partner for {company_name} — Saturn Star Movers",
        "body": """Hi {contact_name},

{personalized_opening}

I'm John Owolabi from Saturn Star Movers, right here in Windsor.

I know {company_name} keeps crews and equipment moving across projects — and when your people need to relocate for a new contract or your office needs rearranging, the last thing you want is to pull your team off the job to handle it.

That's where we come in.

**What we do for construction & trades companies:**
- Employee relocations when staff transfer to new project sites
- Office and trailer moves between job sites
- Furniture delivery and setup for new offices or site trailers
- Equipment and supply transport (non-heavy machinery)
- Storage solutions between projects

**Why local matters:**
- We're in Windsor — same day availability
- Fully insured ($2M liability, WSIB compliant)
- 500+ moves completed, 4.9/5 rating
- We work around YOUR schedule — evenings, weekends, whatever works
- One call: 226-724-1730

**Contractor Rate:** 15% off for local construction companies. No contracts, no minimums — just call when you need us.

{personalized_closing}

John Owolabi
Founder & CEO, Saturn Star Movers
226-724-1730 | business@starmovers.ca""",
    },
    "MT25": {
        "subject": "Moving & Event Logistics — Saturn Star Movers for {company_name}",
        "body": """Hi {contact_name},

{personalized_opening}

I'm John from Saturn Star Movers in Windsor.

Quick pitch — we're a local moving company and I think there's a simple way we can help each other.

**For your team:**
- Staff relocations when you hire from out of town
- Office moves, studio rearrangements, equipment transport
- Event setup and teardown logistics

**For your audience/clients:**
- We'd love to sponsor segments, events, or promotions
- "Moving to Windsor?" content partnership
- Exclusive discount code for your listeners/readers/visitors

**The basics:**
- Local Windsor company — 226-724-1730
- Fully insured, 500+ moves, 4.9/5 rating
- Available 7 days a week

{personalized_closing}

John Owolabi
Founder & CEO, Saturn Star Movers
226-724-1730 | business@starmovers.ca""",
    },
}


def _get_client() -> OpenAI | None:
    """Get OpenAI client, or None if not configured."""
    if not cfg.openai_api_key:
        return None
    return OpenAI(api_key=cfg.openai_api_key)


def _personalize_with_gpt(contact: dict, tier_template: dict) -> tuple[str, str]:
    """Use GPT to generate personalized opening and closing lines.

    Uses industry-specific voice instructions when available so the tone
    matches what actually moves each type of professional.

    Universal structure:
      OPENING → reference THEIR client's situation, not yours
      CLOSING → make the next step absurdly easy (reply yes, text, QR code)

    Returns (opening, closing). Falls back to generic if GPT unavailable.
    """
    client = _get_client()
    if not client:
        return _generic_personalization(contact)

    industry_code = contact["industry_code"]
    voice_instructions = INDUSTRY_GPT_VOICE.get(industry_code, "")

    # Build the prompt
    base_prompt = f"""You are writing a cold business email for Saturn Star Movers (a professional moving company in Windsor-Essex-Chatham, Ontario).

Contact info:
- Name: {contact['contact_name']}
- Title: {contact['title_role']}
- Company: {contact['company_name']}
- Industry code: {industry_code}
- City: {contact['city']}
- Notes: {contact['notes'][:200] if contact['notes'] else 'None'}"""

    if voice_instructions:
        base_prompt += f"""

IMPORTANT — Industry-specific voice direction:
{voice_instructions}"""

    base_prompt += """

UNIVERSAL RULE — the structure that works across ALL industries:
The FIRST thing they should feel is "this person understands my world." NOT "this is a moving company trying to get my business."

Write TWO things. Keep each to 1-2 sentences. No emojis. Match the tone above.

1. OPENING: Reference THEIR client's situation — the people who walk into their office, the families they serve, the tenants they manage. Show you understand the emotional weight of what they deal with daily. Don't mention Saturn Star or moving services yet. Don't be generic. Don't be salesy.

2. CLOSING: Make the next step absurdly easy. Don't ask for a meeting or a call. Offer something they can say "yes" to in one word — dropping off cards, sending a one-pager, texting them a link. The bar to respond should be as low as possible.

Format your response exactly as:
OPENING: [your opening]
CLOSING: [your closing]"""

    try:
        response = client.chat.completions.create(
            model=cfg.llm_model,
            messages=[{"role": "user", "content": base_prompt}],
            max_tokens=250,
            temperature=0.7,
        )
        text = response.choices[0].message.content or ""
        opening = ""
        closing = ""
        for line in text.strip().split("\n"):
            if line.startswith("OPENING:"):
                opening = line.replace("OPENING:", "").strip()
            elif line.startswith("CLOSING:"):
                closing = line.replace("CLOSING:", "").strip()
        if opening and closing:
            return opening, closing
    except Exception as e:
        logger.warning("GPT personalization failed: %s", e)

    return _generic_personalization(contact)


def _generic_personalization(contact: dict) -> tuple[str, str]:
    """Fallback personalization without GPT — industry-aware."""
    city = contact["city"] or "the Windsor-Essex area"
    industry_code = contact["industry_code"]

    # Industry-specific fallbacks — each follows the universal structure:
    # OPENING = their client's world, CLOSING = absurdly easy next step

    if industry_code == "FH25":
        opening = (
            f"The families who come to {contact['company_name']} are carrying more than grief — "
            f"they're often facing the overwhelming task of clearing out a loved one's home."
        )
        closing = (
            f"I'd love to drop off a small packet of cards your team can keep at the front desk — "
            f"something tasteful that families can take when they're ready. Just reply \"yes\" and I'll bring them by."
        )
    elif industry_code == "DL25":
        opening = (
            f"I know family law keeps you busy, and your clients at {contact['company_name']} "
            f"are dealing with enough already."
        )
        closing = (
            f"I'd be happy to drop off a stack of referral cards at your {city} office — "
            f"no meeting needed, just something your team can hand to clients who need to move. Reply \"yes\" and I'll swing by."
        )
    elif industry_code == "MB25":
        opening = (
            f"Your clients at {contact['company_name']} just got the keys to a new home — "
            f"and the last thing they want is a stressful move souring closing day."
        )
        closing = (
            f"I can have co-branded referral cards ready for your closing packages within a week. "
            f"Just reply \"yes\" or text 226-724-1730 and I'll set it up."
        )
    elif industry_code == "CC25":
        opening = (
            f"Every tenant turnover at {contact['company_name']} means finding a mover, hoping they show up, "
            f"and praying they don't scratch the walls or block the elevator for three hours."
        )
        closing = (
            f"I'd like to stop by for 5 minutes, drop off a card, and learn your building's rules "
            f"so we're ready when you need us. Just reply \"yes\" or text 226-724-1730."
        )
    elif industry_code == "EL25":
        opening = (
            f"Estate work means coordinating a lot of moving parts — literally. "
            f"I wanted to put Saturn Star Movers on your radar at {contact['company_name']}."
        )
        closing = (
            f"Can I send you a one-pager you can keep on file for when a client's estate "
            f"needs moving or cleanout handled? Just reply \"yes.\""
        )
    elif industry_code == "RH25":
        opening = (
            f"The residents transitioning into {contact['company_name']} are leaving behind decades of memories — "
            f"and that move needs to feel like care, not logistics."
        )
        closing = (
            f"I'd love to drop off a brochure your team can share with incoming families. "
            f"Just reply \"yes\" and I'll bring it by this week."
        )
    elif industry_code == "CH25":
        opening = (
            f"I grew up in a ministry family, so I know what it means when someone in the congregation "
            f"is going through a transition and the church wants to help."
        )
        closing = (
            f"I'd love to drop off a small stack of cards for your welcome desk or community board. "
            f"Just reply \"yes\" and I'll bring them by after service."
        )
    elif industry_code == "CU25":
        opening = (
            f"Community is everything at {contact['company_name']} — and when your members "
            f"are moving, it helps to have someone local they can trust."
        )
        closing = (
            f"Would you be open to us posting a member discount on your community board? "
            f"Just reply \"yes\" and I'll drop one off."
        )
    elif industry_code == "HB25":
        opening = (
            f"You spend months building someone's dream home — the last thing anyone wants is "
            f"a moving crew that doesn't respect the new build."
        )
        closing = (
            f"I can have co-branded welcome cards ready for your next buyer closing. "
            f"Just reply \"yes\" and I'll reach out to set it up."
        )
    elif industry_code == "IR25":
        opening = (
            f"After a disaster, contents need to come out fast before restoration can begin — "
            f"and the documentation needs to be right for the claim."
        )
        closing = (
            f"Can I send you a one-pager on our pack-out process and pricing? "
            f"Just reply \"yes\" and I'll email it over."
        )
    elif industry_code == "LE25":
        opening = (
            f"When {contact['company_name']} brings in talent from outside the region, "
            f"a smooth relocation experience matters for retention."
        )
        closing = (
            f"Can I send over our corporate relocation package? "
            f"Just reply \"yes\" — no meeting needed."
        )
    elif industry_code == "UN25":
        opening = (
            f"Thousands of students move in and out of {contact['company_name']} every semester — "
            f"and they all need affordable, reliable help."
        )
        closing = (
            f"Would it make sense to get on your recommended vendor list? "
            f"Just reply \"yes\" and I'll send the details."
        )
    elif industry_code == "HO25":
        opening = (
            f"Between patient transitions and facility moves, {contact['company_name']} "
            f"handles more relocations than most people realize."
        )
        closing = (
            f"Can I send you a brochure for your discharge coordination team? "
            f"Just reply \"yes\" and I'll email it over."
        )
    elif industry_code == "HT25":
        opening = (
            f"Between renovations, property transfers, and long-term guest transitions, "
            f"{contact['company_name']} has moving needs that most people don't think about."
        )
        closing = (
            f"Would it help to have a vendor on file for furniture moves and guest relocations? "
            f"Just reply \"yes\" and I'll send our rates."
        )
    elif industry_code == "GV25":
        opening = (
            f"Government office relocations require a vendor who understands procurement, "
            f"documentation, and compliance — we do."
        )
        closing = (
            f"Can I send you our vendor profile with insurance certificates and WSIB documentation? "
            f"Just reply \"yes\" and I'll email it."
        )
    elif industry_code == "EM25":
        opening = (
            f"When {contact['company_name']} needs to relocate equipment or offices, "
            f"every hour of downtime costs money."
        )
        closing = (
            f"Can I send you our commercial moving capabilities sheet? "
            f"Just reply \"yes\" — takes 2 minutes to review."
        )
    elif industry_code in ("NPWE25", "NPCK25"):
        opening = (
            f"As a community-focused organization, {contact['company_name']} stretches every dollar — "
            f"and we want to help with that."
        )
        closing = (
            f"We offer nonprofit discounts and would love to support your next move or event setup. "
            f"Just reply \"yes\" and I'll send the details."
        )
    elif industry_code == "SC25":
        opening = (
            f"Local sports are the heartbeat of our community — and {contact['company_name']} "
            f"is a big part of that."
        )
        closing = (
            f"Would you be open to a sponsorship conversation? "
            f"Just reply \"yes\" and I'll reach out with some options."
        )
    elif industry_code == "CR25":
        opening = (
            f"We recently had the pleasure of helping one of your team members with a relocation, "
            f"and the experience went so smoothly that we wanted to reach out to {contact['company_name']} directly."
        )
        closing = (
            f"I'd love to send over a one-page proposal tailored to {contact['company_name']}'s relocation needs. "
            f"Just reply \"yes\" or call 226-724-1730."
        )
    elif industry_code == "GH25":
        opening = (
            f"Congratulations on the incredible work on the Gordie Howe International Bridge — "
            f"Windsor is watching this project with pride."
        )
        closing = (
            f"Would it make sense to set up a quick call? I'm happy to put together a rate sheet "
            f"tailored to {contact['company_name']}'s needs. Just reply or call 226-724-1730."
        )
    elif industry_code == "LC25":
        opening = (
            f"I know {contact['company_name']} keeps crews and equipment moving across projects — "
            f"and when your people need to relocate, the last thing you want is to pull your team off the job."
        )
        closing = (
            f"Worth a quick chat? Even if it's just keeping our number on file for next time. "
            f"Reply here or call 226-724-1730."
        )
    elif industry_code == "MT25":
        opening = (
            f"I think there's a simple way {contact['company_name']} and Saturn Star Movers "
            f"can help each other out."
        )
        closing = (
            f"Would any of this make sense for {contact['company_name']}? Happy to chat — "
            f"even just 5 minutes. Reply here or call 226-724-1730."
        )
    elif industry_code == "HOT25":
        opening = (
            f"I'll keep this short — {contact['company_name']} is growing and you need "
            f"a reliable moving partner."
        )
        closing = (
            f"Call 226-724-1730 or reply \"yes\" and I'll send a custom quote within 24 hours."
        )
    elif contact["title_role"]:
        opening = (
            f"As a {contact['title_role']} at {contact['company_name']} in {city}, "
            f"you likely see people going through transitions where moving is part of the equation."
        )
        closing = (
            f"Can I send you a one-pager you can keep on hand? "
            f"Just reply \"yes\" — no meeting needed."
        )
    else:
        opening = f"I wanted to reach out to {contact['company_name']} about something that might make life easier for the people you serve."
        closing = (
            f"Would it make sense for me to drop off some info? "
            f"Just reply \"yes\" or text 226-724-1730."
        )

    return opening, closing


def generate_email(contact_id: int) -> tuple[str, str]:
    """Generate a personalized email for a contact.

    Returns (subject, body).
    """
    conn = sqlite3.connect(str(cfg.db_path))
    conn.row_factory = sqlite3.Row
    contact = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    conn.close()

    if not contact:
        return "", ""

    contact_dict = dict(contact)
    tier = contact_dict["tier"]
    industry_code = contact_dict["industry_code"]

    # Industry-specific templates first (FH25, DL25, MB25, CC25),
    # then fall through to tier-based templates
    if industry_code in TIER_TEMPLATES:
        template = TIER_TEMPLATES[industry_code]
    else:
        template = TIER_TEMPLATES.get(tier, TIER_TEMPLATES["D"])

    # Get personalization
    opening, closing = _personalize_with_gpt(contact_dict, template)

    # Build industry context
    industry_context = ""
    if "industry_context" in template:
        industry_context = template["industry_context"].get(industry_code, "clients")

    industry_specific = ""
    if "industry_specific" in template:
        industry_specific = template["industry_specific"].get(industry_code, "")

    # Determine contact name for greeting
    contact_name = contact_dict["contact_name"]
    if contact_name:
        # Use first name only, skip titles/roles used as names
        first = contact_name.split()[0]
        # If it looks like a role rather than a name, use "there"
        if "/" in first or first.lower() in ("hr", "admin", "staff", "team", "manager", "department"):
            contact_name = "there"
        else:
            contact_name = first
    else:
        contact_name = "there"

    # Build extra template variables for CR25 (Corporate Relocation)
    origin_city = ""
    destination_city = ""
    company_name_short = contact_dict["company_name"].split()[0] if contact_dict["company_name"] else ""
    if industry_code == "CR25":
        notes = contact_dict.get("notes", "") or ""
        # Parse "origin_city:X" and "destination_city:Y" from notes
        import re as _re
        m = _re.search(r"origin_city:\s*([^|]+)", notes)
        if m:
            origin_city = m.group(1).strip()
        m = _re.search(r"destination_city:\s*([^|]+)", notes)
        if m:
            destination_city = m.group(1).strip()
        if not origin_city:
            origin_city = "Windsor"
        if not destination_city:
            destination_city = "Toronto"

    # Format the template
    subject = template["subject"].format(
        company_name=contact_dict["company_name"],
        contact_name=contact_name,
    )

    body = template["body"].format(
        contact_name=contact_name,
        company_name=contact_dict["company_name"],
        personalized_opening=opening,
        personalized_closing=closing,
        industry_code=industry_code,
        industry_context=industry_context,
        industry_specific=industry_specific,
        origin_city=origin_city,
        destination_city=destination_city,
        company_name_short=company_name_short,
    )

    return subject, body


if __name__ == "__main__":
    import sys
    cid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    subject, body = generate_email(cid)
    print(f"Subject: {subject}")
    print(f"\n{body}")
