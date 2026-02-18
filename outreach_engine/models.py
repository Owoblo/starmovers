"""Pydantic models and enums for the outreach engine."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Tier(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    HOT = "HOT"


class EmailStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    LIKELY = "likely"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class BundleStatus(str, Enum):
    QUEUED = "queued"
    APPROVED = "approved"
    SENT = "sent"
    OPENED = "opened"
    REPLIED = "replied"
    SKIPPED = "skipped"
    BOUNCED = "bounced"


class Contact(BaseModel):
    city: str = ""
    company_name: str = ""
    street_address: str = ""
    province: str = "ON"
    postal_code: str = ""
    phone: str = ""
    website: str = ""
    contact_name: str = ""
    title_role: str = ""
    notes: str = ""
    tier: Tier = Tier.D
    industry_code: str = ""
    priority_score: int = 50


class OutreachBundle(BaseModel):
    contact_id: int
    batch_date: str
    email_subject: str = ""
    email_body: str = ""
    status: BundleStatus = BundleStatus.QUEUED
    notes: str = ""


class EditRequest(BaseModel):
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    notes: Optional[str] = None


class BatchSendRequest(BaseModel):
    bundle_ids: list[int]


class DiscoverRequest(BaseModel):
    contact_ids: list[int] = []
    limit: int = 10
