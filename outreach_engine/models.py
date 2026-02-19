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


class AccountStatus(str, Enum):
    COLD = "cold"
    CONTACTED = "contacted"
    ENGAGED = "engaged"
    QUALIFIED = "qualified"
    PARTNERED = "partnered"
    REVISIT = "revisit"
    DNC = "dnc"


class CompanySize(str, Enum):
    SMALL = "small"
    MID = "mid"
    LARGE = "large"


class CompanyType(str, Enum):
    TYPE1_OWNER = "type1_owner"
    TYPE2_MANAGER = "type2_manager"
    TYPE3_TENDER = "type3_tender"


class TouchChannel(str, Enum):
    EMAIL = "email"
    DIRECT_MAIL = "direct_mail"
    PHONE = "phone"
    IN_PERSON = "in_person"
    LINKEDIN = "linkedin"


class TouchDirection(str, Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class EcosystemRole(str, Enum):
    REALTOR = "realtor"
    LAWYER = "lawyer"
    BROKER = "broker"
    PROPERTY_MANAGER = "property_manager"
    INSURANCE = "insurance"
    OTHER = "other"


class JobStatus(str, Enum):
    QUOTED = "quoted"
    BOOKED = "booked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


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


class AccountStatusRequest(BaseModel):
    status: str
    notes: str = ""


class TouchLogRequest(BaseModel):
    contact_id: int
    channel: str
    direction: str = "outbound"
    subject: str = ""
    notes: str = ""
    outcome: str = ""


class EcosystemCreateRequest(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    role: str
    company: str = ""
    source_contact_id: Optional[int] = None
    notes: str = ""


class PartnerCreateRequest(BaseModel):
    partner_name: str
    code: str
    discount_percent: float = 0
    bonus_per_referral: float = 0


class JobCreateRequest(BaseModel):
    contact_id: Optional[int] = None
    partner_code: str = ""
    job_type: str = "commercial"
    quote_amount: float = 0
    move_date: str = ""
    origin_address: str = ""
    destination_address: str = ""
    crew_size: int = 0
    truck_count: int = 0
    notes: str = ""


class JobUpdateRequest(BaseModel):
    status: Optional[str] = None
    final_amount: Optional[float] = None
    move_date: Optional[str] = None
    crew_size: Optional[int] = None
    truck_count: Optional[int] = None
    labor_hours: Optional[float] = None
    notes: Optional[str] = None
