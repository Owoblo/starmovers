"""News Signal Scanner — scrapes local news, permits, and public records
to detect moving-service opportunities before competitors.

Signals: new plants, business closures, zoning changes, major hiring events,
relocations, construction permits, commercial real estate transactions.

Cost control:
  - Keyword pre-filter eliminates ~70% of articles before GPT
  - Daily cap on GPT classification calls (default 50 ≈ $0.15/day with gpt-4o-mini)
  - Dedup via UNIQUE index on source_url
"""

import logging
import re
import sqlite3
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from outreach_engine.config import cfg

logger = logging.getLogger(__name__)

# ── Signal type → tier/priority mapping ──

SIGNAL_TYPE_MAP = {
    "relocation":     {"tier": "A", "priority": 95, "industry_code": "NEWS25"},
    "expansion":      {"tier": "A", "priority": 90, "industry_code": "NEWS25"},
    "new_business":   {"tier": "A", "priority": 85, "industry_code": "NEWS25"},
    "construction":   {"tier": "A", "priority": 85, "industry_code": "NEWS25"},
    "real_estate":    {"tier": "B", "priority": 80, "industry_code": "NEWS25"},
    "zoning":         {"tier": "B", "priority": 80, "industry_code": "NEWS25"},
    "closure":        {"tier": "B", "priority": 75, "industry_code": "NEWS25"},
    "retail":         {"tier": "B", "priority": 75, "industry_code": "NEWS25"},
    "hiring":         {"tier": "B", "priority": 70, "industry_code": "NEWS25"},
    "infrastructure": {"tier": "B", "priority": 70, "industry_code": "NEWS25"},
    "lawsuit":        {"tier": "C", "priority": 60, "industry_code": "NEWS25"},
}

# ── News sources ──

NEWS_SOURCES = [
    {
        "name": "windsorstar",
        "label": "Windsor Star",
        "type": "rss",
        "urls": [
            "https://windsorstar.com/category/news/local-news/feed",
            "https://windsorstar.com/category/business/feed",
        ],
        "region": "Windsor-Essex",
    },
    {
        "name": "cbc_windsor",
        "label": "CBC Windsor",
        "type": "rss",
        "urls": [
            "https://www.cbc.ca/cmlink/rss-canada-windsor",
        ],
        "region": "Windsor-Essex",
    },
    {
        "name": "blackburn_windsor",
        "label": "Blackburn News Windsor",
        "type": "rss",
        "urls": [
            "https://blackburnnews.com/windsor/feed/",
        ],
        "region": "Windsor-Essex",
    },
    {
        "name": "ctv_windsor",
        "label": "CTV Windsor",
        "type": "html",
        "urls": [
            "https://windsor.ctvnews.ca/local-news",
        ],
        "region": "Windsor-Essex",
    },
    {
        "name": "windsor_permits",
        "label": "City of Windsor Permits",
        "type": "html",
        "urls": [
            "https://www.citywindsor.ca/residents/planning/land-development/development-applications",
        ],
        "region": "Windsor",
    },
    {
        "name": "weedc",
        "label": "Invest WindsorEssex (WEEDC)",
        "type": "html",
        "urls": [
            "https://www.investwindsoressex.com/en/news.aspx",
        ],
        "region": "Windsor-Essex",
    },
    {
        "name": "chatham_kent",
        "label": "Chatham-Kent Municipal News",
        "type": "html",
        "urls": [
            "https://www.chatham-kent.ca/newsroom",
        ],
        "region": "Chatham-Kent",
    },
]

# ── Keyword pre-filter ──

# Positive keywords — if an article matches any of these, it passes to GPT
_POSITIVE_KEYWORDS = [
    r"\breloc\w*",          # relocate, relocation, relocating
    r"\bexpand\w*",         # expand, expansion, expanding
    r"\bnew\s+facil\w*",    # new facility
    r"\bnew\s+plant\b",
    r"\bnew\s+office\b",
    r"\bnew\s+warehouse\b",
    r"\bnew\s+store\b",
    r"\bnew\s+location\b",
    r"\bopening\b",
    r"\bgrand\s+opening\b",
    r"\bground\s*breaking\b",
    r"\bconstruction\b",
    r"\bbuild\w*\s+permit\b",
    r"\bdevelopment\s+permit\b",
    r"\bdemolition\b",
    r"\bzoning\b",
    r"\brezoning\b",
    r"\bclosing\b",
    r"\bclosure\b",
    r"\bbankrupt\w*",
    r"\bshutting\s+down\b",
    r"\bcommercial\s+(real\s+estate|property|sale)\b",
    r"\boffice\s+space\b",
    r"\bwarehouse\s+space\b",
    r"\bhiring\b",
    r"\b\d{2,}\s+(?:new\s+)?jobs?\b",  # "50 jobs", "100 new jobs"
    r"\bjobs?\b.*\b\d{2,}\b",        # "jobs for 50 people"
    r"\bnew\s+business\b",
    r"\bmerger\b",
    r"\bacquisition\b",
    r"\bmov(e|ing)\s+(to|into|from)\b",
    r"\bnew\s+headquarters\b",
    r"\bhospital\b.*\b(project|expansion|new)\b",
    r"\bschool\b.*\b(project|new|construction)\b",
    r"\blawsuit\b",
    r"\bsettlement\b",
]
_POSITIVE_PATTERN = re.compile("|".join(_POSITIVE_KEYWORDS), re.IGNORECASE)

# Negative keywords — skip sports, weather, entertainment, obituaries
_NEGATIVE_KEYWORDS = [
    r"\b(hockey|nhl|spitfires|lancers|football|soccer|basketball|baseball)\b",
    r"\b(weather|forecast|temperature|snow\s+warning)\b",
    r"\b(obituar|funeral|death\s+notice)\b",
    r"\b(concert|festival|movie|entertainment)\b",
    r"\b(recipe|cooking|restaurant\s+review)\b",
    r"\b(election|poll|vote|candidate)\b",
    r"\b(crime|murder|robbery|assault|arrest)\b",
]
_NEGATIVE_PATTERN = re.compile("|".join(_NEGATIVE_KEYWORDS), re.IGNORECASE)

# ── Helpers ──

_SESSION = None


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; SaturnStarBot/1.0; +https://starmovers.ca)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
    return _SESSION


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(cfg.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _signal_exists(source_url: str) -> bool:
    """Check if we've already scraped this URL."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id FROM news_signals WHERE source_url = ?", (source_url,)
    ).fetchone()
    conn.close()
    return row is not None


def _article_is_relevant(headline: str, snippet: str) -> bool:
    """Keyword pre-filter: returns True if article likely has a moving signal."""
    text = f"{headline} {snippet}"
    if _NEGATIVE_PATTERN.search(text):
        return False
    return bool(_POSITIVE_PATTERN.search(text))


def _get_today_gpt_calls() -> int:
    """Count GPT classification calls made today."""
    conn = _get_conn()
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM news_signals WHERE DATE(scraped_at) = ?",
        (today,),
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


# ── RSS scraping ──

def _scrape_rss(url: str) -> list[dict]:
    """Scrape articles from an RSS feed. Returns list of {url, headline, snippet, published}."""
    articles = []
    try:
        resp = _get_session().get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "xml")
        items = soup.find_all("item")

        for item in items[:30]:  # cap per feed
            link = item.find("link")
            title = item.find("title")
            desc = item.find("description")
            pub_date = item.find("pubDate")

            article_url = link.get_text(strip=True) if link else ""
            if not article_url:
                continue

            articles.append({
                "url": article_url,
                "headline": title.get_text(strip=True) if title else "",
                "snippet": _clean_html(desc.get_text(strip=True) if desc else ""),
                "published": pub_date.get_text(strip=True) if pub_date else "",
            })
    except Exception as e:
        logger.warning("RSS scrape failed for %s: %s", url, e)

    return articles


def _clean_html(text: str) -> str:
    """Strip HTML tags from text."""
    return BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)


# ── HTML scraping ──

def _scrape_news_html(url: str) -> list[dict]:
    """Scrape articles from an HTML news page. Returns list of {url, headline, snippet}."""
    articles = []
    try:
        resp = _get_session().get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Try common news article patterns
        for selector in [
            "article a[href]",
            ".news-item a[href]",
            ".post-title a[href]",
            "h2 a[href]", "h3 a[href]",
            ".card a[href]",
            ".listing-item a[href]",
            ".news-listing a[href]",
            ".media-body a[href]",
        ]:
            links = soup.select(selector)
            if links:
                for a_tag in links[:20]:
                    href = a_tag.get("href", "")
                    if not href or href.startswith("#") or href.startswith("javascript"):
                        continue

                    # Make absolute URL
                    if href.startswith("/"):
                        parsed = urlparse(url)
                        href = f"{parsed.scheme}://{parsed.netloc}{href}"

                    headline = a_tag.get_text(strip=True)
                    # Try to get snippet from surrounding context
                    snippet = ""
                    parent = a_tag.find_parent(["article", "div", "li"])
                    if parent:
                        p_tag = parent.find("p")
                        if p_tag:
                            snippet = p_tag.get_text(strip=True)[:300]

                    if headline and len(headline) > 10:
                        articles.append({
                            "url": href,
                            "headline": headline,
                            "snippet": snippet,
                            "published": "",
                        })
                break  # use first matching selector

    except Exception as e:
        logger.warning("HTML scrape failed for %s: %s", url, e)

    return articles


# ── GPT classification ──

_CLASSIFY_PROMPT = """You are analyzing a local news article for moving-service business signals.

Article headline: {headline}
Article snippet: {snippet}
Source: {source}

Determine if this article indicates a MOVING OPPORTUNITY for a commercial moving company
in the Windsor-Essex / Chatham-Kent area. Look for:
- Company relocations or office moves
- New facility openings, plant expansions
- New businesses opening or moving in
- Construction/development permits
- Commercial real estate transactions
- Business closures (they need to move equipment out)
- Zoning changes (signals upcoming construction/moves)
- Major hiring events (50+ jobs = likely new facility)
- Retail/restaurant openings
- Infrastructure projects (hospitals, schools)
- Companies in legal transitions (mergers, lawsuits, settlements)

If this IS a moving signal, respond in EXACTLY this format:
SIGNAL
type: <one of: relocation, expansion, new_business, construction, real_estate, zoning, closure, retail, hiring, infrastructure, lawsuit>
company: <company name if mentioned, or "Unknown">
city: <city name, default "Windsor">
urgency: <high, medium, or low>
opportunity: <1-2 sentence description of the moving opportunity>
action: <recommended next step for the moving company>

If this is NOT a moving signal, respond with exactly:
NO_SIGNAL"""


def classify_article(headline: str, snippet: str, source: str) -> Optional[dict]:
    """Use GPT to classify whether an article contains a moving signal.
    Returns signal dict or None."""
    if not cfg.openai_api_key:
        logger.warning("No OpenAI API key — skipping GPT classification")
        return None

    prompt = _CLASSIFY_PROMPT.format(
        headline=headline, snippet=snippet[:500], source=source,
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg.openai_api_key)
        resp = client.chat.completions.create(
            model=cfg.llm_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1,
        )
        text = resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("GPT classification failed: %s", e)
        return None

    if text.startswith("NO_SIGNAL"):
        return None

    if not text.startswith("SIGNAL"):
        return None

    # Parse structured response
    signal = {}
    for line in text.split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("SIGNAL"):
            key, _, val = line.partition(":")
            key = key.strip().lower()
            val = val.strip()
            if key == "type":
                signal["signal_type"] = val if val in SIGNAL_TYPE_MAP else "expansion"
            elif key == "company":
                signal["company_name"] = val
            elif key == "city":
                signal["city"] = val
            elif key == "urgency":
                signal["urgency"] = val if val in ("high", "medium", "low") else "medium"
            elif key == "opportunity":
                signal["opportunity"] = val
            elif key == "action":
                signal["recommended_action"] = val

    if "signal_type" not in signal:
        return None

    return signal


# ── Contact creation from signal ──

def _fuzzy_match_company(company_name: str) -> Optional[int]:
    """Check if a contact already exists for this company. Returns contact_id or None."""
    if not company_name or company_name.lower() in ("unknown", "n/a", ""):
        return None

    conn = _get_conn()
    # Exact match first
    row = conn.execute(
        "SELECT id FROM contacts WHERE LOWER(company_name) = LOWER(?)",
        (company_name,),
    ).fetchone()
    if row:
        conn.close()
        return row["id"]

    # Partial match — company name contains or is contained
    rows = conn.execute(
        "SELECT id, company_name FROM contacts WHERE LOWER(company_name) LIKE LOWER(?)",
        (f"%{company_name}%",),
    ).fetchall()
    if rows:
        conn.close()
        return rows[0]["id"]

    conn.close()
    return None


def create_contact_from_signal(signal_id: int) -> Optional[int]:
    """Create a contact from a news signal. Returns contact_id or None."""
    conn = _get_conn()
    signal = conn.execute(
        "SELECT * FROM news_signals WHERE id = ?", (signal_id,)
    ).fetchone()
    if not signal:
        conn.close()
        return None

    signal = dict(signal)
    company_name = signal.get("company_name", "")
    if not company_name or company_name.lower() in ("unknown", "n/a"):
        conn.close()
        return None

    # Check if contact already exists
    existing_id = _fuzzy_match_company(company_name)
    if existing_id:
        # Link the signal to existing contact
        conn.execute(
            "UPDATE news_signals SET contact_id = ?, status = 'reviewed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (existing_id, signal_id),
        )
        conn.commit()
        conn.close()
        return existing_id

    # Get tier/priority from signal type
    type_info = SIGNAL_TYPE_MAP.get(signal["signal_type"], {"tier": "B", "priority": 70, "industry_code": "NEWS25"})

    notes = f"News signal: {signal.get('opportunity', '')} | Source: {signal.get('source_url', '')}"

    conn.execute("""
        INSERT INTO contacts (
            company_name, city, province,
            tier, industry_code, priority_score, csv_source,
            notes, outreach_status, email_status
        ) VALUES (?, ?, 'ON', ?, ?, ?, 'news_signal', ?, 'pending', 'pending')
    """, (
        company_name,
        signal.get("city", "Windsor"),
        type_info["tier"],
        type_info["industry_code"],
        type_info["priority"],
        notes,
    ))
    contact_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Link signal to new contact
    conn.execute(
        "UPDATE news_signals SET contact_id = ?, status = 'reviewed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (contact_id, signal_id),
    )
    conn.commit()
    conn.close()
    return contact_id


# ── Main scan orchestrator ──

def scan_source(source: dict, auto_create_contacts: bool = True) -> dict:
    """Scan a single news source. Returns stats dict."""
    stats = {"source": source["name"], "articles_found": 0, "relevant": 0,
             "signals": 0, "contacts_created": 0, "skipped_existing": 0}

    all_articles = []
    for url in source["urls"]:
        if source["type"] == "rss":
            all_articles.extend(_scrape_rss(url))
        else:
            all_articles.extend(_scrape_news_html(url))

    stats["articles_found"] = len(all_articles)
    logger.info("  %s: found %d articles", source["label"], len(all_articles))

    for article in all_articles:
        # Dedup check
        if _signal_exists(article["url"]):
            stats["skipped_existing"] += 1
            continue

        # Keyword pre-filter
        if not _article_is_relevant(article["headline"], article["snippet"]):
            continue

        stats["relevant"] += 1

        # Check daily GPT cap
        if _get_today_gpt_calls() >= cfg.news_scan_max_daily:
            logger.info("  Daily GPT cap reached (%d), stopping", cfg.news_scan_max_daily)
            break

        # GPT classification
        signal = classify_article(
            article["headline"], article["snippet"], source["label"],
        )

        if not signal:
            # Still insert as a "no signal" to avoid re-processing
            # We use a lightweight record with just the URL for dedup
            conn = _get_conn()
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO news_signals
                    (source_name, source_url, headline, content_snippet,
                     signal_type, status, published_date)
                    VALUES (?, ?, ?, ?, 'none', 'dismissed', ?)
                """, (
                    source["name"], article["url"],
                    article["headline"][:500], article["snippet"][:500],
                    article.get("published", ""),
                ))
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()
            continue

        # Insert signal
        conn = _get_conn()
        try:
            conn.execute("""
                INSERT OR IGNORE INTO news_signals
                (source_name, source_url, headline, content_snippet,
                 signal_type, company_name, opportunity, city, urgency,
                 recommended_action, status, published_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
            """, (
                source["name"], article["url"],
                article["headline"][:500], article["snippet"][:500],
                signal["signal_type"],
                signal.get("company_name", ""),
                signal.get("opportunity", ""),
                signal.get("city", "Windsor"),
                signal.get("urgency", "medium"),
                signal.get("recommended_action", ""),
                article.get("published", ""),
            ))
            conn.commit()

            # Get the signal ID
            row = conn.execute(
                "SELECT id FROM news_signals WHERE source_url = ?",
                (article["url"],),
            ).fetchone()
            signal_id = row["id"] if row else None
        except sqlite3.IntegrityError:
            # URL already exists (race condition or duplicate)
            stats["skipped_existing"] += 1
            conn.close()
            continue
        finally:
            conn.close()

        stats["signals"] += 1
        logger.info("    SIGNAL: [%s] %s — %s",
                     signal["signal_type"], signal.get("company_name", "?"),
                     article["headline"][:80])

        # Auto-create contact
        if auto_create_contacts and signal_id:
            contact_id = create_contact_from_signal(signal_id)
            if contact_id:
                stats["contacts_created"] += 1

    return stats


def scan_all_sources(auto_create_contacts: bool = True) -> dict:
    """Scan all configured news sources. Returns aggregate stats."""
    if not cfg.news_scan_enabled:
        logger.info("News scanning disabled (NEWS_SCAN_ENABLED=false)")
        return {"enabled": False}

    logger.info("News Signal Scanner — scanning %d sources...", len(NEWS_SOURCES))

    results = {
        "sources_scanned": 0,
        "total_articles": 0,
        "total_relevant": 0,
        "total_signals": 0,
        "total_contacts_created": 0,
        "source_details": [],
    }

    for source in NEWS_SOURCES:
        try:
            stats = scan_source(source, auto_create_contacts=auto_create_contacts)
            results["sources_scanned"] += 1
            results["total_articles"] += stats["articles_found"]
            results["total_relevant"] += stats["relevant"]
            results["total_signals"] += stats["signals"]
            results["total_contacts_created"] += stats["contacts_created"]
            results["source_details"].append(stats)
        except Exception as e:
            logger.error("  Failed to scan %s: %s", source["name"], e)
            results["source_details"].append({
                "source": source["name"], "error": str(e),
            })

    logger.info("News scan complete: %d sources, %d articles, %d signals, %d contacts",
                results["sources_scanned"], results["total_articles"],
                results["total_signals"], results["total_contacts_created"])

    return results


def get_signal_stats() -> dict:
    """Get news signal statistics."""
    conn = _get_conn()

    total = conn.execute(
        "SELECT COUNT(*) FROM news_signals WHERE signal_type != 'none'"
    ).fetchone()[0]

    by_type = conn.execute(
        "SELECT signal_type, COUNT(*) as cnt FROM news_signals WHERE signal_type != 'none' GROUP BY signal_type"
    ).fetchall()

    by_status = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM news_signals GROUP BY status"
    ).fetchall()

    by_source = conn.execute(
        "SELECT source_name, COUNT(*) as cnt FROM news_signals WHERE signal_type != 'none' GROUP BY source_name"
    ).fetchall()

    recent = conn.execute("""
        SELECT id, source_name, headline, signal_type, company_name,
               urgency, status, scraped_at
        FROM news_signals
        WHERE signal_type != 'none'
        ORDER BY scraped_at DESC LIMIT 20
    """).fetchall()

    with_contacts = conn.execute(
        "SELECT COUNT(*) FROM news_signals WHERE contact_id IS NOT NULL AND signal_type != 'none'"
    ).fetchone()[0]

    conn.close()

    return {
        "total_signals": total,
        "with_contacts": with_contacts,
        "by_type": {r["signal_type"]: r["cnt"] for r in by_type},
        "by_status": {r["status"]: r["cnt"] for r in by_status},
        "by_source": {r["source_name"]: r["cnt"] for r in by_source},
        "recent": [dict(r) for r in recent],
    }
