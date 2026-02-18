"""Import all 22 CSVs into the contacts table with tier/industry tags."""

import csv
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from outreach_engine.config import cfg

# ── CSV registry: filename pattern → (tier, industry_code, priority_score) ──

CSV_REGISTRY: dict[str, tuple[str, str, int]] = {
    "Divorce_Law_Firms": ("A", "DL25", 80),
    "estate_lawyers": ("A", "EL25", 80),
    "mortgage_brokers": ("A", "MB25", 80),
    "home_builders": ("B", "HB25", 60),
    "insurance_adjusters_restoration": ("B", "IR25", 60),
    "condo_corporations_property_mgmt": ("B", "CC25", 60),
    "large_employers_hr": ("C", "LE25", 50),
    "universities_colleges_housing": ("C", "UN25", 50),
    "hospitals_healthcare": ("C", "HO25", 50),
    "hotels_hospitality": ("C", "HT25", 50),
    "government_offices": ("C", "GV25", 50),
    "engineering_manufacturing": ("C", "EM25", 50),
    "churches_places_of_worship": ("D", "CH25", 40),
    "nonprofits_comprehensive_windsor_essex": ("D", "NPWE25", 40),
    "nonprofits_comprehensive_chatham_kent": ("D", "NPCK25", 40),
    "nonprofits_charities": ("D", "NPWE25", 40),
    "sports_clubs": ("D", "SC25", 40),
    "cultural_ethnic_clubs": ("D", "CU25", 40),
    "retirement_care_homes": ("E", "RH25", 70),
    "funeral_homes": ("E", "FH25", 70),
    "HOT_LEADS_SIGNALS": ("HOT", "HOT25", 100),
}

# ── Column name normalization ──
# Maps variant column names to our canonical fields.

COMPANY_NAME_COLS = [
    "Company Name", "Law Firm Name", "Law Firm", "Funeral Home",
    "Church/Organization Name", "Organization Name", "Name",
    "Hotel/Property Name", "Hospital/Healthcare Facility Name",
    "Club/Association Name", "Institution Name", "Office/Department Name",
    "Facility Name", "Company/Brokerage Name", "Company/Organization",
]

CONTACT_NAME_COLS = [
    "Decision Maker Name", "Staff Name", "HR Contact Name", "Contact/Source",
]

TITLE_COLS = [
    "Title/Role", "Title / Role", "Staff Title/Role",
]

PHONE_COLS = ["Phone Number", "Phone"]

_EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def _find_col(headers: list[str], candidates: list[str]) -> str | None:
    """Find the first matching column name from candidates."""
    header_lower = {h.strip().lower(): h.strip() for h in headers}
    for c in candidates:
        if c.lower() in header_lower:
            return header_lower[c.lower()]
    return None


def _extract_domain(website: str) -> str:
    """Extract bare domain from a website URL."""
    if not website:
        return ""
    url = website.strip()
    if not url.startswith("http"):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if host.startswith("www."):
            host = host[4:]
        return host.lower()
    except Exception:
        return ""


def _extract_emails_from_notes(notes: str) -> str:
    """Pull email addresses from notes field."""
    if not notes:
        return ""
    found = _EMAIL_REGEX.findall(notes)
    return found[0] if found else ""


def _match_registry(filename: str) -> tuple[str, str, int] | None:
    """Match a CSV filename to its registry entry."""
    stem = Path(filename).stem
    # Try exact stem match first
    for key, value in CSV_REGISTRY.items():
        if stem.startswith(key) or key in stem:
            return value
    return None


def import_csv(csv_path: Path, conn: sqlite3.Connection) -> int:
    """Import a single CSV file into the contacts table. Returns row count."""
    reg = _match_registry(csv_path.name)
    if reg is None:
        print(f"  SKIP (no registry match): {csv_path.name}")
        return 0

    tier, industry_code, priority_score = reg

    with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return 0

        headers = [h.strip() for h in reader.fieldnames]

        # Resolve column mappings
        company_col = _find_col(headers, COMPANY_NAME_COLS)
        contact_col = _find_col(headers, CONTACT_NAME_COLS)
        title_col = _find_col(headers, TITLE_COLS)
        phone_col = _find_col(headers, PHONE_COLS)

        count = 0
        for row in reader:
            # Normalize: strip all values, skip None keys
            row = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k is not None}

            company_name = row.get(company_col, "") if company_col else ""
            contact_name = row.get(contact_col, "") if contact_col else ""
            title_role = row.get(title_col, "") if title_col else ""
            phone = row.get(phone_col, "") if phone_col else ""

            # Skip rows with no company name AND no contact name
            if not company_name and not contact_name:
                continue

            city = row.get("City", "")
            street_address = row.get("Street Address", "")
            province = row.get("Province", "ON")
            postal_code = row.get("Postal Code", "")
            website = row.get("Website", "")
            notes = row.get("Notes", "")

            # HOT_LEADS has different columns
            if industry_code == "HOT25":
                company_name = company_name or row.get("Company/Organization", "")
                notes = row.get("Opportunity Description", "")
                if row.get("Action Required"):
                    notes += f" | Action: {row['Action Required']}"
                if row.get("Time Sensitivity"):
                    notes += f" | Timing: {row['Time Sensitivity']}"

            domain = _extract_domain(website)

            # Check notes for embedded emails
            discovered_email = _extract_emails_from_notes(notes)
            email_status = "likely" if discovered_email else "pending"

            conn.execute("""
                INSERT INTO contacts (
                    city, company_name, street_address, province, postal_code,
                    phone, website, domain, contact_name, title_role, notes,
                    tier, industry_code, csv_source, priority_score,
                    discovered_email, email_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                city, company_name, street_address, province, postal_code,
                phone, website, domain, contact_name, title_role, notes,
                tier, industry_code, csv_path.name, priority_score,
                discovered_email, email_status,
            ))
            count += 1

    return count


def import_all():
    """Import all CSVs from the project directory."""
    from outreach_engine.db.init_db import init_db

    # Initialize DB if needed
    if not cfg.db_path.exists():
        init_db(cfg.db_path)

    conn = sqlite3.connect(str(cfg.db_path))

    # Check if already imported
    existing = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    if existing > 0:
        print(f"Database already has {existing} contacts. Skipping import.")
        print("To re-import, delete the database file first.")
        conn.close()
        return

    csv_files = sorted(cfg.csv_dir.glob("*.csv"))
    total = 0

    for csv_path in csv_files:
        # Skip temp files
        if csv_path.name.startswith("~$"):
            continue
        count = import_csv(csv_path, conn)
        if count > 0:
            print(f"  {csv_path.name}: {count} contacts")
            total += count

    conn.commit()

    # Print summary by tier
    print(f"\n{'='*50}")
    print(f"Total imported: {total} contacts")
    print(f"{'='*50}")

    for tier_label, tier_code in [("HOT", "HOT"), ("A", "A"), ("B", "B"),
                                   ("C", "C"), ("D", "D"), ("E", "E")]:
        row = conn.execute(
            "SELECT COUNT(*) FROM contacts WHERE tier = ?", (tier_code,)
        ).fetchone()
        print(f"  Tier {tier_label}: {row[0]}")

    # Unique domains
    domains = conn.execute(
        "SELECT COUNT(DISTINCT domain) FROM contacts WHERE domain != ''"
    ).fetchone()[0]
    print(f"  Unique domains: {domains}")

    # Pre-populated emails
    emails = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE discovered_email != ''"
    ).fetchone()[0]
    print(f"  Pre-populated emails: {emails}")

    conn.close()


if __name__ == "__main__":
    import_all()
