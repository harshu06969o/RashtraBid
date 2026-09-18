from pydantic import Field
from typing import List, Optional, Any
from datetime import datetime, timezone
from app.db.mongodb import MongoBaseModel, PyObjectId

def utcnow():
    return datetime.now(timezone.utc)

# ─────────────────────────────────────────────
# Core Entities (Section 4.3 of Blueprint)
# ─────────────────────────────────────────────

class Tender(MongoBaseModel):
    tender_no: str
    title: str
    buyer: str
    version: int = 1
    issue_date: datetime = Field(default_factory=utcnow)
    closing_date: Optional[datetime] = None
    hash: Optional[str] = None
    status: str = "ACTIVE"
    description: Optional[str] = None
    turnover_threshold_cr: Optional[float] = None

class TenderClause(MongoBaseModel):
    tender_id: PyObjectId
    source_page: Optional[int] = None
    text: str
    clause_type: str
    mandatory: bool = True
    applicability: str = "ALL"

class RequirementRule(MongoBaseModel):
    clause_id: Optional[PyObjectId] = None
    tender_id: PyObjectId
    metric: str
    operator: str
    threshold: Any
    unit: str
    severity: str = "CRITICAL" # CRITICAL, HIGH, MEDIUM, LOW
    conditions: Optional[dict] = None
    evidence_type: str
    verification_source: str

class Bidder(MongoBaseModel):
    legal_name: str
    identifiers: dict = {} # e.g. {"PAN": "ABCDE1234F", "GSTIN": "..."}
    source: str
    status: str = "ACTIVE"

class BidPackage(MongoBaseModel):
    bidder_id: PyObjectId
    tender_id: PyObjectId
    version: int = 1
    upload_time: datetime = Field(default_factory=utcnow)
    package_hash: Optional[str] = None

class Document(MongoBaseModel):
    package_id: PyObjectId
    type: str # e.g. "CA_CERTIFICATE", "PAN_CARD"
    filename: str
    hash: str
    page_count: int

class Evidence(MongoBaseModel):
    document_id: PyObjectId
    package_id: PyObjectId
    bidder_id: PyObjectId
    page: int
    bbox: Optional[List[float]] = None
    field: str
    value: str
    normalized_value: Any
    confidence: float
    verification_status: str = "PENDING"

class Verification(MongoBaseModel):
    evidence_id: PyObjectId
    source: str
    request_id: str
    response_time: datetime = Field(default_factory=utcnow)
    status: str # VERIFIED, MISMATCH, NOT_FOUND, PENDING, UNAVAILABLE, UNAUTHORIZED
    raw_hash: str
    normalized_fields: dict = {}

class RuleResult(MongoBaseModel):
    rule_id: PyObjectId
    bidder_id: PyObjectId
    result: str # PASS, FAIL, REVIEW, PENDING, NOT_APPLICABLE, WAIVED
    explanation: str
    confidence: float

class RiskAssessment(MongoBaseModel):
    bidder_id: PyObjectId
    score: float
    band: str # Low, Medium, High, Critical
    factors: List[str]
    generated_at: datetime = Field(default_factory=utcnow)

class OfficerAction(MongoBaseModel):
    bidder_id: PyObjectId
    action: str # ACCEPT, REVIEW, OVERRIDE, CLARIFY
    actor: str
    reason: str
    timestamp: datetime = Field(default_factory=utcnow)

class AuditEvent(MongoBaseModel):
    entity_id: PyObjectId
    event_type: str
    actor: str
    timestamp: datetime = Field(default_factory=utcnow)
    prev_hash: Optional[str] = None
    event_hash: str
