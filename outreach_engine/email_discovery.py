"""Email discovery — find email addresses for contacts.

Adapted from challsor/email_validator.py for local business outreach.
Steps: domain extraction → MX check → website scraping → pattern generation → SMTP probing.
"""

import logging
import re
import smtplib
import socket
import sqlite3
from functools import lru_cache
from urllib.parse import urlparse

import dns.resolver
import requests
from bs4 import BeautifulSoup

from outreach_engine.config import cfg

logger = logging.getLogger(__name__)

_SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}
_EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Generic addresses to skip during scraping (we DO want info@ for local businesses)
_IGNORE_PREFIXES = {"noreply@", "no-reply@", "jobs@", "careers@", "privacy@"}


def _extract_domain(website: str) -> str:
    """Extract bare domain from a URL."""
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


def _normalize_url(website: str) -> str:
    """Ensure URL has scheme."""
    url = website.strip()
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    return url


def validate_syntax(email: str) -> bool:
    """Quick regex check for valid email format."""
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email))


@lru_cache(maxsize=512)
def validate_mx(domain: str) -> tuple[bool, str]:
    """Check if domain has MX records. Returns (has_mx, best_mx_host)."""
    try:
        answers = dns.resolver.resolve(domain, "MX")
        best = min(answers, key=lambda r: r.preference)
        host = str(best.exchange).rstrip(".")
        return True, host
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
            dns.resolver.NoNameservers, dns.exception.Timeout, Exception):
        return False, ""


def validate_smtp(email: str, mx_host: str, timeout: int = 5) -> bool | None:
    """Probe SMTP server via RCPT TO. Returns True/False/None (inconclusive).
    Respects per-domain rate limits."""
    # Rate limit check
    domain = email.split("@")[-1] if "@" in email else ""
    if domain:
        try:
            from outreach_engine.queue_manager import check_discovery_rate
            if not check_discovery_rate(domain):
                logger.debug("Rate limit hit for domain %s — skipping SMTP probe", domain)
                return None
        except Exception:
            pass  # Don't block probing if rate check fails

    try:
        with smtplib.SMTP(timeout=timeout) as server:
            server.connect(mx_host, 25)
            server.ehlo("saturnstarmovers.com")
            server.mail("test@saturnstarmovers.com")
            code, _ = server.rcpt(email)

            # Log the probe for rate tracking
            if domain:
                try:
                    conn = sqlite3.connect(str(cfg.db_path), timeout=5)
                    conn.execute("""
                        INSERT INTO email_discovery_log (contact_id, step, result, detail)
                        VALUES (0, 'smtp_probe', ?, ?)
                    """, (str(code == 250), f"{email} @ {mx_host} domain={domain}"))
                    conn.commit()
                    conn.close()
                except Exception:
                    pass

            return code == 250
    except (smtplib.SMTPException, socket.timeout, socket.error, OSError):
        return None


@lru_cache(maxsize=512)
def is_catch_all(domain: str) -> bool:
    """Detect catch-all by probing a gibberish address."""
    has_mx, mx_host = validate_mx(domain)
    if not has_mx:
        return False
    result = validate_smtp(f"zxqj7k9m3wplv@{domain}", mx_host)
    return result is True


def _parse_name(full_name: str) -> tuple[str, str]:
    """Split 'First Last' into (first, last)."""
    parts = full_name.strip().split()
    if not parts:
        return "", ""
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""
    return first, last


def generate_email_variations(first_name: str, last_name: str, domain: str,
                              deep: bool = False) -> list[str]:
    """Generate common email patterns from name + domain.

    When deep=True, generates extra patterns for bounce recovery.
    """
    first = first_name.lower().strip()
    last = last_name.lower().strip()
    if not first or not domain:
        return []

    # Remove non-alpha characters
    first = re.sub(r"[^a-z]", "", first)
    last = re.sub(r"[^a-z]", "", last)

    variations = [
        f"{first}@{domain}",
        f"{first}.{last}@{domain}" if last else None,
        f"{first}{last}@{domain}" if last else None,
        f"{first[0]}{last}@{domain}" if last else None,
        f"{first}{last[0]}@{domain}" if last else None,
        f"{first}_{last}@{domain}" if last else None,
        f"{last}@{domain}" if last else None,
    ]

    if deep and last:
        # Extended patterns for bounce recovery
        variations.extend([
            f"{last}.{first}@{domain}",
            f"{last}{first}@{domain}",
            f"{last}{first[0]}@{domain}",
            f"{first[0]}.{last}@{domain}",
            f"{first}-{last}@{domain}",
            f"{last}-{first}@{domain}",
            f"{first}.{last[0]}@{domain}",
            # Generic fallbacks
            f"info@{domain}",
            f"contact@{domain}",
            f"office@{domain}",
            f"hello@{domain}",
            f"admin@{domain}",
        ])
    seen = set()
    result = []
    for v in variations:
        if v and v not in seen:
            seen.add(v)
            result.append(v)
    return result


def scrape_emails_from_website(website: str, deep: bool = False) -> list[str]:
    """Scrape website pages for email addresses.

    When deep=True, tries many more page paths for bounce recovery.
    """
    base = _normalize_url(website).rstrip("/")
    if not base:
        return []

    pages = [base, f"{base}/about", f"{base}/contact", f"{base}/about-us",
             f"{base}/team", f"{base}/staff", f"{base}/people"]

    if deep:
        # Extra pages for deeper discovery on bounce recovery
        pages.extend([
            f"{base}/our-team", f"{base}/attorneys", f"{base}/lawyers",
            f"{base}/professionals", f"{base}/partners", f"{base}/about-us",
            f"{base}/connect", f"{base}/reach-us", f"{base}/get-in-touch",
            f"{base}/our-firm", f"{base}/leadership", f"{base}/directory",
        ])
    found: list[str] = []
    seen: set[str] = set()

    for url in pages:
        try:
            resp = requests.get(url, headers=_SCRAPE_HEADERS, timeout=8,
                                allow_redirects=True)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # mailto: links first (highest quality)
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("mailto:"):
                    email = href.replace("mailto:", "").split("?")[0].strip().lower()
                    if validate_syntax(email) and email not in seen:
                        if not any(email.startswith(p) for p in _IGNORE_PREFIXES):
                            seen.add(email)
                            found.append(email)

            # Regex scan
            emails = _EMAIL_REGEX.findall(resp.text)
            for email in emails:
                email = email.lower()
                if (validate_syntax(email) and email not in seen
                        and not any(email.startswith(p) for p in _IGNORE_PREFIXES)
                        and not email.endswith((".png", ".jpg", ".svg", ".gif", ".css", ".js"))):
                    seen.add(email)
                    found.append(email)
        except Exception:
            continue

    return found


# ── Known title keywords for extracting team members from pages ──
_TITLE_KEYWORDS = [
    "mortgage agent", "mortgage broker", "mortgage specialist",
    "lawyer", "attorney", "partner", "associate", "counsel",
    "funeral director", "director", "manager", "vp of", "vice president",
    "agent", "broker", "advisor", "consultant", "specialist",
    "property manager", "leasing", "superintendent",
    "president", "owner", "principal", "founder", "ceo", "coo", "cfo",
]

# Words that are NOT person names — filter these out
_NOT_NAMES = {
    "find", "search", "home", "about", "contact", "our", "the", "view",
    "meet", "team", "staff", "all", "more", "read", "click", "apply",
    "learn", "company", "directory", "office", "location", "mortgage",
    "agent", "broker", "rates", "tools", "login", "blog", "news",
}


def _looks_like_name(text: str) -> bool:
    """Check if a string looks like a person's first+last name."""
    parts = text.strip().split()
    if len(parts) < 2 or len(parts) > 4:
        return False
    # Each part should be capitalized and alpha (allow hyphens/apostrophes)
    for p in parts:
        cleaned = p.replace("-", "").replace("'", "").replace(".", "")
        if not cleaned or not cleaned[0].isupper() or not cleaned.isalpha():
            return False
    # First word shouldn't be a known non-name
    if parts[0].lower() in _NOT_NAMES:
        return False
    return True


def scrape_team_members(website: str, city_hint: str = "windsor") -> list[dict]:
    """Deep scrape website for team member names and titles.

    Looks at team pages, location pages, staff directories.
    Returns list of {"name": "Brian Holland", "title": "Mortgage Agent"}.
    """
    base = _normalize_url(website).rstrip("/")
    if not base:
        return []

    domain = _extract_domain(website)
    city = city_hint.lower().replace(" ", "-")

    # URLs to try — team pages + location-specific pages
    pages = [
        f"{base}/team", f"{base}/our-team", f"{base}/staff",
        f"{base}/people", f"{base}/about", f"{base}/about-us",
        f"{base}/attorneys", f"{base}/lawyers", f"{base}/professionals",
        f"{base}/partners", f"{base}/leadership", f"{base}/directory",
        f"{base}/agents", f"{base}/contact",
        # Location-specific
        f"{base}/locations/{city}", f"{base}/locations/{city}-office",
        f"{base}/{city}", f"{base}/{city}-team", f"{base}/{city}-office",
    ]

    found: list[dict] = []
    seen_names: set[str] = set()

    for url in pages:
        try:
            resp = requests.get(url, headers=_SCRAPE_HEADERS, timeout=10,
                                allow_redirects=True)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            logger.info("Team scrape: scanning %s", url)

            # Strategy 1: Find elements containing title keywords,
            # then look at parent/sibling for the person's name
            for tag in soup.find_all(["h2", "h3", "h4", "h5", "p", "span", "div", "strong"]):
                text = tag.get_text(strip=True)
                text_lower = text.lower()

                # Check if this element contains a known title
                matched_title = ""
                for kw in _TITLE_KEYWORDS:
                    if kw in text_lower:
                        matched_title = kw
                        break

                if not matched_title:
                    continue

                # Get the full card text (parent element)
                parent = tag.parent
                if not parent:
                    continue
                card_text = parent.get_text(" ", strip=True)
                if len(card_text) > 150:
                    continue

                # Try to split name from title
                # Pattern: "Brian Holland Mortgage Agent"
                for kw in _TITLE_KEYWORDS:
                    idx = card_text.lower().find(kw)
                    if idx > 0:
                        name_part = card_text[:idx].strip()
                        title_part = card_text[idx:].strip()
                        if _looks_like_name(name_part) and name_part not in seen_names:
                            seen_names.add(name_part)
                            found.append({"name": name_part, "title": title_part})
                        break

            # Strategy 2: Look for mailto links with names nearby
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("mailto:"):
                    email = href.replace("mailto:", "").split("?")[0].strip().lower()
                    # Try to find name from link text or nearby elements
                    link_text = a.get_text(strip=True)
                    if _looks_like_name(link_text) and link_text not in seen_names:
                        seen_names.add(link_text)
                        found.append({"name": link_text, "title": "", "email": email})

            # Strategy 3: Look for links to individual profile pages
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not href or href == "#":
                    continue
                # Profile links often contain /team/name or /agents/name
                if any(seg in href.lower() for seg in ["/team/", "/agents/", "/staff/", "/people/", "/professionals/"]):
                    link_text = a.get_text(" ", strip=True)
                    # Check if the link text contains a name
                    words = link_text.split()
                    if len(words) >= 2:
                        # Try the first two capitalized words as a name
                        potential_name = " ".join(words[:3])
                        if _looks_like_name(potential_name) and potential_name not in seen_names:
                            seen_names.add(potential_name)
                            found.append({"name": potential_name, "title": ""})

        except Exception as e:
            logger.debug("Team scrape failed for %s: %s", url, e)
            continue

    logger.info("Team scrape for %s: found %d people", website, len(found))
    return found


def discover_team_emails(website: str, domain: str, city: str = "windsor",
                         exclude_emails: set[str] | None = None) -> list[dict]:
    """Scrape team members from website and find valid emails for each.

    Returns list of {"name", "title", "email", "email_status"}.
    """
    exclude = exclude_emails or set()
    members = scrape_team_members(website, city_hint=city)
    if not members:
        return []

    # Check MX once
    has_mx, mx_host = validate_mx(domain)
    if not has_mx:
        return []

    catch_all = is_catch_all(domain)
    results = []

    for member in members:
        name = member["name"]
        first, last = _parse_name(name)
        if not first or not last:
            continue

        # If the member already has an email from a mailto link
        if member.get("email") and member["email"] not in exclude:
            results.append({
                "name": name,
                "title": member.get("title", ""),
                "email": member["email"],
                "email_status": "verified" if not catch_all else "likely",
            })
            continue

        # Generate and probe patterns
        patterns = generate_email_variations(first, last, domain)
        patterns = [e for e in patterns if e not in exclude]

        best_email = ""
        best_status = "unknown"

        for email in patterns:
            if not validate_syntax(email):
                continue
            result = validate_smtp(email, mx_host)
            if result is True and not catch_all:
                best_email = email
                best_status = "verified"
                break
            if result is True and catch_all:
                best_email = email
                best_status = "likely"
                break
            if result is None and not best_email:
                best_email = email
                best_status = "likely"

        # Fallback to most common pattern
        if not best_email and patterns:
            scored = sorted(patterns, key=_pattern_score, reverse=True)
            best_email = scored[0]
            best_status = "likely"

        if best_email:
            results.append({
                "name": name,
                "title": member.get("title", ""),
                "email": best_email,
                "email_status": best_status,
            })

    logger.info("Team email discovery for %s: %d/%d with emails",
                website, len(results), len(members))
    return results


def _pattern_score(email: str) -> int:
    """Score email by local-part pattern commonality. Higher = more likely real."""
    local = email.split("@")[0]
    if re.match(r"^[a-z]+$", local) and len(local) <= 15:
        return 100  # firstname@
    if re.match(r"^[a-z]+\.[a-z]+$", local):
        return 80   # first.last@
    if re.match(r"^[a-z][a-z]{3,}$", local) and len(local) > 4:
        return 60   # flast@
    if re.match(r"^[a-z]+_[a-z]+$", local):
        return 50   # first_last@
    if local in ("info", "contact", "office", "hello", "admin", "general"):
        return 30   # generic but useful for local businesses
    return 10


def _log_discovery(conn: sqlite3.Connection, contact_id: int, step: str,
                   result: str, detail: str = ""):
    """Write to email_discovery_log."""
    conn.execute(
        "INSERT INTO email_discovery_log (contact_id, step, result, detail) VALUES (?, ?, ?, ?)",
        (contact_id, step, result, detail),
    )


def _google_search_email(company_name: str, domain: str = "") -> str:
    """Search Google for a company's contact email as a fallback layer.

    Searches for '"company name" email contact' and extracts emails from results.
    Returns the best email found, or empty string.
    """
    try:
        query = f'"{company_name}" email contact'
        if domain:
            query += f" site:{domain} OR @{domain}"

        resp = requests.get(
            "https://www.google.com/search",
            params={"q": query, "num": 5},
            headers=_SCRAPE_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return ""

        # Extract emails from search results page
        found = _EMAIL_REGEX.findall(resp.text)
        for email in found:
            email = email.lower()
            if validate_syntax(email) and not any(email.startswith(p) for p in _IGNORE_PREFIXES):
                # Prefer domain-matching emails
                if domain and email.endswith(f"@{domain}"):
                    return email
        # Return first valid email even if domain doesn't match
        for email in found:
            email = email.lower()
            if validate_syntax(email) and not any(email.startswith(p) for p in _IGNORE_PREFIXES):
                if not email.endswith((".png", ".jpg", ".svg", ".gif", ".css", ".js")):
                    return email
    except Exception as e:
        logger.debug("Google search email failed for %s: %s", company_name, e)

    return ""


def _flag_needs_manual(conn: sqlite3.Connection, contact_id: int,
                       company_name: str, contact_name: str,
                       reason: str = ""):
    """Flag a contact as needs_manual and send Telegram notification."""
    conn.execute("""
        UPDATE contacts SET email_status = 'needs_manual',
               updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (contact_id,))
    _log_discovery(conn, contact_id, "needs_manual", "flagged", reason)

    # Send Telegram notification
    try:
        from outreach_engine.telegram_notifications import notify_needs_manual
        notify_needs_manual(contact_id, company_name, contact_name, reason)
    except Exception as e:
        logger.debug("Telegram notify_needs_manual failed: %s", e)


def discover_email(contact_id: int) -> tuple[str, str]:
    """Run full email discovery pipeline for a single contact.

    Returns (best_email, email_status).

    When all automated methods are exhausted, flags the contact as
    'needs_manual' instead of guessing a pattern email.
    """
    conn = sqlite3.connect(str(cfg.db_path))
    conn.row_factory = sqlite3.Row

    contact = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not contact:
        conn.close()
        return "", "unknown"

    website = contact["website"]
    contact_name = contact["contact_name"]
    company_name = contact["company_name"]
    domain = contact["domain"] or _extract_domain(website)

    # Update domain if missing
    if domain and not contact["domain"]:
        conn.execute("UPDATE contacts SET domain = ? WHERE id = ?", (domain, contact_id))

    # Step 1: Check if we already have an email
    if contact["discovered_email"] and contact["email_status"] in ("verified", "likely"):
        conn.close()
        return contact["discovered_email"], contact["email_status"]

    # Step 2a: Hunter.io lookup (if API key configured + high-priority contact)
    try:
        from outreach_engine.config import cfg as _cfg
        if _cfg.hunter_api_key and domain:
            # Only auto-use Hunter for Tier A or field intel contacts
            tier = contact["tier"] if "tier" in contact.keys() else ""
            source = contact["csv_source"] if "csv_source" in contact.keys() else ""
            if tier == "A" or source == "field_intel":
                from outreach_engine.hunter_enrichment import find_email as hunter_find
                first, last = _parse_name(contact_name)
                if first and last:
                    hunter_result = hunter_find(domain, first, last)
                    if hunter_result.get("found") and hunter_result.get("email"):
                        h_email = hunter_result["email"]
                        h_score = hunter_result.get("score", 0)
                        h_status = "verified" if h_score >= 90 else "likely"
                        _log_discovery(conn, contact_id, "hunter_find", h_status,
                                       f"{h_email} score={h_score}")
                        conn.execute("""
                            UPDATE contacts
                            SET discovered_email = ?, email_status = ?,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (h_email, h_status, contact_id))
                        if hunter_result.get("linkedin"):
                            conn.execute(
                                "UPDATE contacts SET linkedin_url = ? WHERE id = ?",
                                (hunter_result["linkedin"], contact_id))
                        conn.commit()
                        conn.close()
                        logger.info("Hunter.io found %s for #%d (%s)",
                                    h_email, contact_id, company_name)
                        return h_email, h_status
    except Exception as e:
        logger.debug("Hunter.io lookup skipped: %s", e)

    # Step 2: MX check
    if not domain:
        _log_discovery(conn, contact_id, "mx", "skip", "no domain")
        _flag_needs_manual(conn, contact_id, company_name, contact_name,
                           "no domain — no website to extract from")
        conn.commit()
        conn.close()
        return "", "needs_manual"

    has_mx, mx_host = validate_mx(domain)
    _log_discovery(conn, contact_id, "mx", "pass" if has_mx else "fail", mx_host)

    if not has_mx:
        conn.execute(
            "UPDATE contacts SET email_status = 'invalid', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (contact_id,),
        )
        conn.commit()
        conn.close()
        return "", "invalid"

    # Step 3: Scrape website for emails
    scraped = scrape_emails_from_website(website)
    _log_discovery(conn, contact_id, "scrape", f"found:{len(scraped)}",
                   " | ".join(scraped[:5]))

    # Step 3.5: Google search for email (fallback layer)
    if not scraped:
        google_email = _google_search_email(company_name, domain)
        if google_email:
            scraped.append(google_email)
            _log_discovery(conn, contact_id, "google_search", "found", google_email)

    # Step 4: Generate name-based patterns
    first, last = _parse_name(contact_name)
    patterns = generate_email_variations(first, last, domain) if first else []
    _log_discovery(conn, contact_id, "patterns", f"generated:{len(patterns)}",
                   " | ".join(patterns[:5]))

    # Combine: scraped first (higher quality), then patterns
    all_candidates = scraped + [p for p in patterns if p not in scraped]

    if not all_candidates:
        # No candidates at all — flag for manual research instead of guessing
        _flag_needs_manual(conn, contact_id, company_name, contact_name,
                           "no emails found via scrape, Google, or name patterns")
        conn.commit()
        conn.close()
        return "", "needs_manual"

    # Step 5: SMTP probing
    catch_all = is_catch_all(domain)
    _log_discovery(conn, contact_id, "catchall", str(catch_all), "")

    best_email = ""
    best_status = "unknown"

    for email in all_candidates:
        if not validate_syntax(email):
            continue
        result = validate_smtp(email, mx_host)
        if result is True and not catch_all:
            best_email = email
            best_status = "verified"
            _log_discovery(conn, contact_id, "smtp", "verified", email)
            break
        if result is True and catch_all:
            best_email = email
            best_status = "likely"
            _log_discovery(conn, contact_id, "smtp", "likely-catchall", email)
            break
        if result is None and not best_email:
            best_email = email
            best_status = "likely"

    # If SMTP probing found nothing and we only have patterns (no scraped emails),
    # flag as needs_manual instead of guessing
    if not best_email:
        if scraped:
            # We had scraped emails but none confirmed — use best scraped one
            best_email = scraped[0]
            best_status = "likely"
            _log_discovery(conn, contact_id, "scraped_fallback", "likely", best_email)
        else:
            # Only had pattern-guessed emails — don't guess, flag for manual
            _flag_needs_manual(conn, contact_id, company_name, contact_name,
                               "SMTP probing inconclusive, no scraped emails to fall back on")
            conn.commit()
            conn.close()
            return "", "needs_manual"

    # Update contact
    conn.execute("""
        UPDATE contacts
        SET discovered_email = ?, email_status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (best_email, best_status, contact_id))
    conn.commit()
    conn.close()

    return best_email, best_status


def rediscover_email(contact_id: int) -> tuple[str, str]:
    """Deep rediscovery after a bounce — tries harder than initial discovery.

    Excludes previously bounced emails, scrapes more pages, tries more patterns.
    Returns (best_email, email_status).
    """
    conn = sqlite3.connect(str(cfg.db_path))
    conn.row_factory = sqlite3.Row

    contact = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not contact:
        conn.close()
        return "", "unknown"

    website = contact["website"]
    contact_name = contact["contact_name"]
    domain = contact["domain"] or _extract_domain(website)

    # Emails that already bounced — never try these again
    bounced_set = set(
        e.strip() for e in (contact["bounced_emails"] or "").split(",") if e.strip()
    )
    logger.info("Rediscovery for #%d (%s) — excluding bounced: %s",
                contact_id, contact["company_name"], bounced_set)

    if not domain:
        _log_discovery(conn, contact_id, "rediscover", "skip", "no domain")
        conn.execute(
            "UPDATE contacts SET email_status = 'exhausted', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (contact_id,),
        )
        conn.commit()
        conn.close()
        return "", "exhausted"

    # MX check
    has_mx, mx_host = validate_mx(domain)
    if not has_mx:
        _log_discovery(conn, contact_id, "rediscover_mx", "fail", "no MX")
        conn.execute(
            "UPDATE contacts SET email_status = 'exhausted', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (contact_id,),
        )
        conn.commit()
        conn.close()
        return "", "exhausted"

    # Deep scrape — more pages than initial discovery
    scraped = scrape_emails_from_website(website, deep=True)
    _log_discovery(conn, contact_id, "rediscover_scrape", f"found:{len(scraped)}",
                   " | ".join(scraped[:5]))

    # Deep patterns — more variations
    first, last = _parse_name(contact_name)
    patterns = generate_email_variations(first, last, domain, deep=True) if first else []
    _log_discovery(conn, contact_id, "rediscover_patterns", f"generated:{len(patterns)}",
                   " | ".join(patterns[:5]))

    # Combine and exclude bounced emails
    all_candidates = scraped + [p for p in patterns if p not in scraped]
    all_candidates = [e for e in all_candidates if e not in bounced_set]

    if not all_candidates:
        _log_discovery(conn, contact_id, "rediscover", "exhausted", "no new candidates")
        conn.execute(
            "UPDATE contacts SET email_status = 'exhausted', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (contact_id,),
        )
        conn.commit()
        conn.close()
        return "", "exhausted"

    # SMTP probing
    catch_all = is_catch_all(domain)
    best_email = ""
    best_status = "unknown"

    for email in all_candidates:
        if not validate_syntax(email):
            continue
        result = validate_smtp(email, mx_host)
        if result is True and not catch_all:
            best_email = email
            best_status = "verified"
            _log_discovery(conn, contact_id, "rediscover_smtp", "verified", email)
            break
        if result is True and catch_all:
            best_email = email
            best_status = "likely"
            _log_discovery(conn, contact_id, "rediscover_smtp", "likely-catchall", email)
            break
        if result is None and not best_email:
            best_email = email
            best_status = "likely"

    # Fallback: pattern scoring
    if not best_email and all_candidates:
        scored = sorted(all_candidates, key=_pattern_score, reverse=True)
        best_email = scored[0]
        best_status = "likely"
        _log_discovery(conn, contact_id, "rediscover_score", "fallback", best_email)

    if best_email:
        conn.execute("""
            UPDATE contacts
            SET discovered_email = ?, email_status = ?, outreach_status = 'pending',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (best_email, best_status, contact_id))
        _log_discovery(conn, contact_id, "rediscover", "found", best_email)
    else:
        conn.execute(
            "UPDATE contacts SET email_status = 'exhausted', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (contact_id,),
        )
        _log_discovery(conn, contact_id, "rediscover", "exhausted", "no valid email found")

    conn.commit()
    conn.close()
    return best_email, best_status


def discover_batch(limit: int = 60) -> list[dict]:
    """Discover emails for a batch of pending contacts."""
    conn = sqlite3.connect(str(cfg.db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT id FROM contacts
        WHERE email_status = 'pending' AND domain != ''
        ORDER BY priority_score DESC, id ASC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    results = []
    for row in rows:
        email, status = discover_email(row["id"])
        results.append({"contact_id": row["id"], "email": email, "status": status})
        logger.info("Discovered %s → %s (%s)", row["id"], email, status)

    return results


if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    results = discover_batch(limit)
    found = sum(1 for r in results if r["email"])
    print(f"\nDiscovered {found}/{len(results)} emails")
    for r in results:
        print(f"  #{r['contact_id']}: {r['email']} ({r['status']})")
