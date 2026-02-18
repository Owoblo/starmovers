"""Centralized configuration loaded from .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# Render persistent disk mount (or local fallback)
_data_env = os.getenv("DATA_DIR", "")
_DATA_DIR = Path(_data_env) if _data_env else None


class _Config:
    # Paths
    project_root: Path = Path(__file__).resolve().parent.parent

    # On Render: store DB + backups on persistent disk (/data)
    # Locally: use the default outreach_engine/db/ path
    db_path: Path = (
        _DATA_DIR / "outreach.db" if _DATA_DIR and _DATA_DIR.is_dir()
        else project_root / "outreach_engine" / "db" / "outreach.db"
    )
    csv_dir: Path = project_root
    templates_dir: Path = project_root / "direct_mail_templates"
    logo_path: Path = project_root / "assets" / "logo.jpg"

    # SiteGround SMTP
    smtp_host: str = os.getenv("SMTP_HOST", "mail.starmovers.ca")
    smtp_port: int = int(os.getenv("SMTP_PORT", "465"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "business@starmovers.ca")
    smtp_from_name: str = os.getenv("SMTP_FROM_NAME", "John Owolabi")
    smtp_use_ssl: bool = os.getenv("SMTP_USE_SSL", "true").lower() == "true"

    # OpenAI
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # Sidecar
    sidecar_port: int = int(os.getenv("SIDECAR_PORT", "8787"))
    sidecar_public_url: str = os.getenv("SIDECAR_PUBLIC_URL", "http://localhost:8787")

    # Notification
    notification_email: str = os.getenv("NOTIFICATION_EMAIL", "johnowolabi80@gmail.com")

    # Dashboard
    dashboard_url: str = os.getenv("DASHBOARD_URL", "http://localhost:3000")

    # Pipeline
    daily_send_target: int = int(os.getenv("DAILY_SEND_TARGET", "40"))
    discovery_batch_size: int = int(os.getenv("DISCOVERY_BATCH_SIZE", "60"))

    # Hard daily send cap — absolute max emails per day (safety net)
    max_daily_sends: int = int(os.getenv("MAX_DAILY_SENDS", "80"))

    # Auto-approve: automatically approve bundles for well-tested templates
    auto_approve: bool = os.getenv("AUTO_APPROVE", "true").lower() == "true"
    # Industry codes that ALWAYS require manual review
    manual_review_codes: list[str] = (
        os.getenv("MANUAL_REVIEW_CODES", "CR25,HOT25").split(",")
    )

    # Discovery rate limits
    discovery_daily_cap: int = int(os.getenv("DISCOVERY_DAILY_CAP", "200"))
    discovery_per_domain_per_hour: int = int(os.getenv("DISCOVERY_PER_DOMAIN_HOUR", "3"))

    # Scheduler (times in 24h format, timezone)
    scheduler_timezone: str = os.getenv("SCHEDULER_TIMEZONE", "America/Toronto")
    pipeline_schedule_hour: int = int(os.getenv("PIPELINE_HOUR", "9"))
    followup_schedule_hour: int = int(os.getenv("FOLLOWUP_HOUR", "11"))
    backup_schedule_hour: int = int(os.getenv("BACKUP_HOUR", "0"))

    # DB backup
    backup_dir: Path = (
        _DATA_DIR / "backups" if _DATA_DIR and _DATA_DIR.is_dir()
        else project_root / "outreach_engine" / "db" / "backups"
    )
    backup_keep_days: int = int(os.getenv("BACKUP_KEEP_DAYS", "7"))


cfg = _Config()
