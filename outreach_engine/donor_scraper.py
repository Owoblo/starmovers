"""Donor/sponsor list scraper — find local companies on institutional donor pages.

Scrapes donor/sponsor pages from UWindsor, St. Clair College, Windsor Hospital
Foundation, etc. Extracts company names, deduplicates against existing contacts,
classifies new companies into tiers, and creates contacts for email discovery.
"""

import logging
import re
import sqlite3
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

from outreach_engine.config import cfg

logger = logging.getLogger(__name__)

_SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

# ── Configurable donor sources ──

DONOR_SOURCES = [
    {
        "name": "Bright Lights Windsor Sponsors",
        "urls": [
            "https://www.citywindsor.ca/residents/recreation/special-events/bright-lights-windsor",
            "https://citywindsor.ca/newsroom/bright-lights-windsor-returns-the-city-holiday-tradition-shines",
            "https://citywindsor.ca/newsroom/windsor-holiday-tradition-shined-bright-for-thousands-at-bright-lights-windsor-2025",
        ],
        "type": "event_sponsors",
    },
    {
        "name": "City of Windsor Awarded Contracts",
        "urls": [
            "https://www.citywindsor.ca/business/awarded-contracts",
        ],
        "type": "city_vendors",
    },
    {
        "name": "United Way Windsor-Essex",
        "urls": [
            "https://www.weareunited.com/donor-recognition/",
            "https://www.weareunited.com/about-us/",
        ],
        "type": "charity_donors",
    },
    {
        "name": "UWindsor Corporate Giving",
        "urls": [
            "https://www.uwindsor.ca/supportuwindsor/corporate-foundation-giving",
        ],
        "type": "university_donors",
    },
    {
        "name": "Windsor Essex Community Foundation",
        "urls": [
            "https://www.wecf.ca/donors",
            "https://www.wecf.ca/partners",
        ],
        "type": "community_foundation",
    },
]

# Known Windsor-Essex companies from verified sources (Bright Lights 2025 sponsors,
# City contracts, local events). These are added directly since many sponsor pages
# use JavaScript rendering or PDFs that our scraper can't parse.
KNOWN_LOCAL_COMPANIES = [
    # Bright Lights Windsor 2024/2025 sponsors
    {"company_name": "ENWIN Utilities", "website": "enwin.com", "source": "Bright Lights Windsor"},
    {"company_name": "WaveDirect", "website": "wavedirect.net", "source": "Bright Lights Windsor"},
    {"company_name": "Libro Credit Union", "website": "libro.ca", "source": "Bright Lights Windsor"},
    {"company_name": "Ground Effects", "website": "groundeffects.com", "source": "Bright Lights Windsor"},
    {"company_name": "YQG Windsor International Airport", "website": "yqg.ca", "source": "Bright Lights Windsor"},
    {"company_name": "Motor City Community Credit Union", "website": "mcccu.com", "source": "Bright Lights Windsor"},
    {"company_name": "HD Development Group", "website": "hddevelopmentgroup.com", "source": "Bright Lights Windsor"},
    {"company_name": "WindsorEssex Community Foundation", "website": "wecf.ca", "source": "Bright Lights Windsor"},
    {"company_name": "Detroit-Windsor Tunnel", "website": "dwtunnel.com", "source": "Bright Lights Windsor"},
    {"company_name": "Trillium Machine and Tool", "website": "trilliummachine.com", "source": "Bright Lights Windsor"},
    {"company_name": "Paul Davis Restoration Windsor", "website": "pauldavis.ca", "source": "Bright Lights Windsor"},
    {"company_name": "Tucker Electric", "website": "", "source": "Bright Lights Windsor"},
    # City of Windsor awarded contract vendors
    {"company_name": "D'Amore Construction", "website": "", "source": "City of Windsor Contracts"},
    {"company_name": "Coco Paving Inc.", "website": "cocopaving.com", "source": "City of Windsor Contracts"},
    {"company_name": "SLR Contracting Group", "website": "", "source": "City of Windsor Contracts"},
    {"company_name": "Vince Ferro Construction", "website": "", "source": "City of Windsor Contracts"},
    {"company_name": "Amico Infrastructures", "website": "amico.ca", "source": "City of Windsor Contracts"},
    {"company_name": "FACCA Incorporated", "website": "facca.com", "source": "City of Windsor Contracts"},
    {"company_name": "Dillon Consulting", "website": "dillon.ca", "source": "City of Windsor Contracts"},
    {"company_name": "Stantec Consulting", "website": "stantec.com", "source": "City of Windsor Contracts"},
    {"company_name": "WSP Canada", "website": "wsp.com", "source": "City of Windsor Contracts"},
    {"company_name": "Haller Mechanical Contractors", "website": "", "source": "City of Windsor Contracts"},
    {"company_name": "Oscar Construction Company", "website": "", "source": "City of Windsor Contracts"},
    {"company_name": "Goodman Group Insurance", "website": "", "source": "City of Windsor Contracts"},
    {"company_name": "Cintas Canada", "website": "cintas.ca", "source": "City of Windsor Contracts"},
    {"company_name": "GDI Services Canada", "website": "gdi.com", "source": "City of Windsor Contracts"},
    {"company_name": "Reaume Chevrolet Buick GMC", "website": "reaumechev.com", "source": "City of Windsor Contracts"},
    {"company_name": "Pierascenzi Construction", "website": "", "source": "City of Windsor Contracts"},
    {"company_name": "Sterling Ridge Infrastructure", "website": "", "source": "City of Windsor Contracts"},
    {"company_name": "Fuller Construction", "website": "", "source": "City of Windsor Contracts"},
    {"company_name": "Rudak Excavating", "website": "", "source": "City of Windsor Contracts"},
    {"company_name": "Elmara Construction", "website": "", "source": "City of Windsor Contracts"},
    {"company_name": "Capital Sewer Services", "website": "", "source": "City of Windsor Contracts"},
    {"company_name": "Mill-Am Corporation", "website": "", "source": "City of Windsor Contracts"},
    {"company_name": "Joe Johnson Equipment", "website": "jjequipment.com", "source": "City of Windsor Contracts"},
    {"company_name": "SheaRock Construction Group", "website": "", "source": "City of Windsor Contracts"},
]

# Words that indicate this is NOT a company name
_NOISE_WORDS = {
    "donate", "donation", "donor", "giving", "gift", "learn more",
    "click here", "read more", "view all", "see all", "back to top",
    "anonymous", "privacy policy", "terms", "contact us", "home",
    "about us", "subscribe", "newsletter", "copyright", "all rights reserved",
    "facebook pixel", "how to apply", "types of scholarships",
    "about our scholarship program", "an endowment", "an annual",
    "foundation endowments", "application is now closed", "how to",
    "skip to content", "menu", "search", "close", "open", "toggle",
    "submit", "sign up", "log in", "register", "next", "previous",
    "share", "print", "email", "phone", "fax", "address",
}

# Known industry keywords for classification fallback
_INDUSTRY_HINTS = {
    "law": ("A", "DL25", 80),
    "legal": ("A", "DL25", 80),
    "lawyer": ("A", "DL25", 80),
    "attorney": ("A", "DL25", 80),
    "mortgage": ("A", "MB25", 80),
    "real estate": ("A", "MB25", 75),
    "realty": ("A", "MB25", 75),
    "insurance": ("B", "IR25", 60),
    "restoration": ("B", "IR25", 60),
    "construction": ("B", "HB25", 60),
    "building": ("B", "HB25", 60),
    "bank": ("C", "LE25", 55),
    "financial": ("C", "LE25", 55),
    "credit union": ("C", "LE25", 55),
    "manufacturing": ("C", "EM25", 50),
    "engineering": ("C", "EM25", 50),
    "automotive": ("C", "EM25", 50),
    "hospital": ("C", "HO25", 50),
    "medical": ("C", "HO25", 50),
    "hotel": ("C", "HT25", 50),
    "church": ("D", "CH25", 40),
    "foundation": ("D", "NPWE25", 40),
    "charity": ("D", "NPWE25", 40),
}


def scrape_donor_page(url: str) -> list[dict]:
    """Scrape a single donor/sponsor page for company names.

    Returns list of {company_name, website, source_url}.
    Handles multiple HTML patterns: logo grids, lists, tables, headings.
    """
    try:
        resp = requests.get(url, headers=_SCRAPE_HEADERS, timeout=15,
                            allow_redirects=True)
        if resp.status_code != 200:
            logger.warning("  %s returned %d", url, resp.status_code)
            return []
    except Exception as e:
        logger.warning("  Failed to fetch %s: %s", url, e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    found: list[dict] = []
    seen_names: set[str] = set()

    def _add(name: str, website: str = ""):
        name = name.strip()
        # Strip trailing periods, colons
        name = name.rstrip(".:;,")
        if not name or len(name) < 4 or len(name) > 100:
            return
        name_lower = name.lower()
        if name_lower in seen_names:
            return
        # Skip noise words
        if any(noise in name_lower for noise in _NOISE_WORDS):
            return
        # Skip if it's just a number, very generic, or looks like page navigation
        if re.match(r"^\d+$", name) or name_lower in ("inc", "ltd", "corp"):
            return
        # Skip sentences (real company names rarely have 6+ words)
        if len(name.split()) > 7:
            return
        # Skip if it starts with common non-company words
        if name_lower.startswith(("the 20", "how to", "about ", "types of", "our ", "your ", "this ")):
            return
        seen_names.add(name_lower)
        found.append({
            "company_name": name,
            "website": website,
            "source_url": url,
        })

    # Strategy 1: Sponsor logos — img tags with alt text inside links
    for img in soup.find_all("img", alt=True):
        alt = img["alt"].strip()
        if not alt or len(alt) < 3:
            continue
        # Skip generic alts
        if alt.lower() in ("logo", "sponsor", "image", "banner", "photo"):
            continue
        # Clean up common suffixes
        alt = re.sub(r"\s*(logo|sponsor|partner|image)s?$", "", alt, flags=re.I).strip()
        if alt:
            # Try to get website from parent link
            parent_link = img.find_parent("a", href=True)
            website = ""
            if parent_link:
                href = parent_link["href"]
                if href.startswith("http") and urlparse(href).hostname != urlparse(url).hostname:
                    website = href
            _add(alt, website)

    # Strategy 2: Lists — ul/ol with company names
    for section in soup.find_all(["section", "div", "article"]):
        # Look for headers that indicate donor lists
        header = section.find(["h1", "h2", "h3", "h4"], string=re.compile(
            r"(sponsor|donor|partner|supporter|thank|recogni)", re.I
        ))
        if not header:
            continue
        # Get list items after the header
        for li in section.find_all("li"):
            text = li.get_text(strip=True)
            # Remove common prefixes like bullet chars
            text = re.sub(r"^[•\-–—\*]\s*", "", text)
            if text and len(text) > 2:
                _add(text)

    # Strategy 3: Tables with company names
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if cells:
                text = cells[0].get_text(strip=True)
                if text and len(text) > 2:
                    _add(text)

    # Strategy 4: Headings that look like company names in sponsor sections
    sponsor_sections = soup.find_all(string=re.compile(
        r"(sponsor|donor|partner|supporter)", re.I
    ))
    for match in sponsor_sections:
        parent = match.find_parent(["section", "div"])
        if parent:
            for heading in parent.find_all(["h3", "h4", "h5", "strong"]):
                text = heading.get_text(strip=True)
                if text and len(text) > 2 and not re.search(
                    r"(sponsor|donor|partner|level|tier|category)", text, re.I
                ):
                    _add(text)

    logger.info("  Scraped %d companies from %s", len(found), url)
    return found


def scrape_all_donors() -> list[dict]:
    """Scrape all configured donor sources. Deduplicates by company name."""
    all_found: list[dict] = []
    seen: set[str] = set()

    for source in DONOR_SOURCES:
        logger.info("Scraping %s...", source["name"])
        for url in source["urls"]:
            companies = scrape_donor_page(url)
            for co in companies:
                key = co["company_name"].lower().strip()
                if key not in seen:
                    seen.add(key)
                    co["donor_source"] = source["name"]
                    co["donor_type"] = source["type"]
                    all_found.append(co)

    logger.info("Total unique companies from donor pages: %d", len(all_found))
    return all_found


def classify_donor_industry(company_name: str, context: str = "") -> tuple[str, str, int]:
    """Classify a donor company into (tier, industry_code, priority_score).

    Uses keyword hints first, then GPT-4o-mini as fallback.
    """
    name_lower = company_name.lower()

    # Try keyword-based classification first
    for keyword, classification in _INDUSTRY_HINTS.items():
        if keyword in name_lower:
            return classification

    # GPT classification
    if cfg.openai_api_key:
        try:
            client = OpenAI(api_key=cfg.openai_api_key)
            industries = (
                "DL25=Divorce/Family Law, EL25=Estate Lawyers, MB25=Mortgage Brokers, "
                "HB25=Home Builders, IR25=Insurance/Restoration, CC25=Condo/Property Mgmt, "
                "LE25=Large Employers/Corporate, UN25=Universities, HO25=Hospitals/Healthcare, "
                "HT25=Hotels, GV25=Government, EM25=Engineering/Manufacturing, "
                "CH25=Churches, NPWE25=Nonprofits, SC25=Sports Clubs, CU25=Cultural Clubs, "
                "RH25=Retirement/Care Homes, FH25=Funeral Homes"
            )
            resp = client.chat.completions.create(
                model=cfg.llm_model,
                messages=[{"role": "user", "content": (
                    f"Classify this company into one industry code. "
                    f"Company: '{company_name}'. Context: {context or 'local Windsor-Essex business'}. "
                    f"Options: {industries}. "
                    f"Reply with ONLY the code (e.g., LE25). If unsure, reply LE25."
                )}],
                max_tokens=10,
                temperature=0,
            )
            code = resp.choices[0].message.content.strip().upper()
            # Map code to tier+priority
            code_to_tier = {
                "DL25": ("A", 80), "EL25": ("A", 80), "MB25": ("A", 80),
                "HB25": ("B", 60), "IR25": ("B", 60), "CC25": ("B", 60),
                "LE25": ("C", 55), "UN25": ("C", 50), "HO25": ("C", 50),
                "HT25": ("C", 50), "GV25": ("C", 50), "EM25": ("C", 50),
                "CH25": ("D", 40), "NPWE25": ("D", 40), "NPCK25": ("D", 40),
                "SC25": ("D", 40), "CU25": ("D", 40),
                "RH25": ("E", 70), "FH25": ("E", 70),
            }
            if code in code_to_tier:
                tier, prio = code_to_tier[code]
                return tier, code, prio
        except Exception as e:
            logger.warning("GPT classification failed for '%s': %s", company_name, e)

    # Default: large employer
    return "C", "LE25", 55


def _fuzzy_match_company(company_name: str, conn: sqlite3.Connection) -> int | None:
    """Check if a company already exists in contacts. Returns contact ID or None."""
    name_lower = company_name.lower().strip()

    # Exact match
    row = conn.execute(
        "SELECT id FROM contacts WHERE LOWER(company_name) = ?",
        (name_lower,),
    ).fetchone()
    if row:
        return row[0]

    # Substring match (company name contained in existing, or vice versa)
    rows = conn.execute(
        "SELECT id, company_name FROM contacts WHERE company_name != ''"
    ).fetchall()
    for r in rows:
        existing = r["company_name"].lower()
        if (name_lower in existing or existing in name_lower) and len(name_lower) > 5:
            return r["id"]

    return None


def import_donors(dry_run: bool = False) -> dict:
    """Full pipeline: scrape + known list → classify → deduplicate → create contacts.

    Returns {scraped, known, new_companies, new_contacts, existing_matched, skipped}.
    """
    results = {
        "scraped": 0,
        "known_added": 0,
        "new_companies": 0,
        "new_contacts": 0,
        "existing_matched": 0,
        "skipped": 0,
        "details": [],
    }

    # Scrape all sources
    all_companies = scrape_all_donors()
    results["scraped"] = len(all_companies)

    # Add known local companies (these bypass scraping — verified manually)
    for known in KNOWN_LOCAL_COMPANIES:
        # Dedup against scraped
        if not any(c["company_name"].lower() == known["company_name"].lower() for c in all_companies):
            all_companies.append({
                "company_name": known["company_name"],
                "website": known.get("website", ""),
                "source_url": "",
                "donor_source": known.get("source", "Known Local"),
                "donor_type": "known_local",
            })
            results["known_added"] += 1

    if dry_run:
        results["details"] = all_companies
        return results

    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    for co in all_companies:
        company_name = co["company_name"]

        # Check for existing match
        existing_id = _fuzzy_match_company(company_name, conn)

        if existing_id:
            results["existing_matched"] += 1
            results["details"].append({
                "company": company_name,
                "action": "matched_existing",
                "existing_id": existing_id,
            })
            continue

        # Classify industry
        tier, industry_code, priority_score = classify_donor_industry(
            company_name, context=co.get("donor_source", "")
        )

        # Derive domain from website if available
        domain = ""
        website = co.get("website", "")
        if website:
            try:
                parsed = urlparse(website if website.startswith("http") else f"https://{website}")
                host = parsed.hostname or ""
                if host.startswith("www."):
                    host = host[4:]
                domain = host.lower()
            except Exception:
                pass

        # Create contact
        conn.execute("""
            INSERT INTO contacts (
                company_name, website, domain, city, province,
                tier, industry_code, priority_score, csv_source,
                notes, outreach_status, email_status
            ) VALUES (?, ?, ?, 'Windsor', 'ON', ?, ?, ?, 'donor_scrape', ?, 'pending', 'pending')
        """, (
            company_name, website, domain,
            tier, industry_code, priority_score,
            f"Donor source: {co.get('donor_source', '')} | URL: {co.get('source_url', '')}",
        ))
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        results["new_companies"] += 1
        results["new_contacts"] += 1
        results["details"].append({
            "company": company_name,
            "action": "created",
            "contact_id": new_id,
            "tier": tier,
            "industry_code": industry_code,
        })

    conn.commit()
    conn.close()

    logger.info(
        "Donor import: %d scraped, %d new companies, %d existing matched, %d skipped",
        results["scraped"], results["new_companies"],
        results["existing_matched"], results["skipped"],
    )
    return results


def add_donor_source(name: str, url: str, source_type: str = "custom"):
    """Add a new donor source URL to the list (runtime only)."""
    # Check if source with this name exists
    for source in DONOR_SOURCES:
        if source["name"] == name:
            if url not in source["urls"]:
                source["urls"].append(url)
            return
    DONOR_SOURCES.append({
        "name": name,
        "urls": [url],
        "type": source_type,
    })
