"""
GeM-Guard — Domain Schemas (Pydantic v2)
Strict Domain Models:
- Tender: ID, Tender No, Title, Organization (CPCL), Closing Date, File Hash.
- RequirementRule: Clause ID, Metric, Operator, Threshold, Unit, Severity.
- Evidence: Document ID, Page Number, precise Bounding Box array [x1, y1, x2, y2], Field Name, Normalized Value, Confidence.
- RuleResult: Status (PASS/FAIL/REVIEW/PENDING), Evidence IDs, Explanation.
- AuditEvent: Timestamp, Actor, Action, Prev Hash, Event Hash (SHA-256).
"""

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utcnow() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class RuleStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    PENDING = "PENDING"


class RuleSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tender
# ─────────────────────────────────────────────────────────────────────────────
class Tender(BaseModel):
    """
    Tender Domain Model
    Specification: ID, Tender No, Title, Organization (CPCL), Closing Date, File Hash.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )

    id: Optional[str] = Field(default=None, alias="_id", description="Unique Tender identifier")
    tender_no: str = Field(..., description="Official Tender Reference (e.g. GEM/2026/B/1001)")
    title: str = Field(..., description="Title or description of the procurement")
    organization: str = Field(default="CPCL", description="Issuing Organization (CPCL)")
    closing_date: Optional[datetime] = Field(default=None, description="Tender closing deadline (UTC)")
    file_hash: Optional[str] = Field(default=None, description="SHA-256 hash of original tender document")

    # Additional contextual fields for end-to-end integration
    buyer: Optional[str] = Field(default=None, description="Buyer name/department (defaults to organization)")
    status: str = Field(default="ACTIVE", description="Tender status (ACTIVE, CLOSED, EVALUATING)")
    version: int = Field(default=1, description="Version number")
    description: Optional[str] = Field(default=None, description="Detailed scope of work")
    turnover_threshold_cr: Optional[float] = Field(default=None, description="Minimum turnover threshold in Crores")
    created_at: datetime = Field(default_factory=utcnow, description="Creation timestamp")

    @model_validator(mode="before")
    @classmethod
    def sync_buyer_and_org(cls, values: Any) -> Any:
        if isinstance(values, dict):
            # If buyer is provided but organization is not, map buyer -> organization
            if values.get("buyer") and not values.get("organization"):
                values["organization"] = values["buyer"]
            elif values.get("organization") and not values.get("buyer"):
                values["buyer"] = values["organization"]
            # Handle hash alias if passed as 'hash'
            if "hash" in values and "file_hash" not in values:
                values["file_hash"] = values["hash"]
            # Convert string ID to id
            if "_id" in values and not values.get("id"):
                values["id"] = str(values["_id"])
        return values


# ─────────────────────────────────────────────────────────────────────────────
# 2. RequirementRule
# ─────────────────────────────────────────────────────────────────────────────
class RequirementRule(BaseModel):
    """
    RequirementRule Domain Model
    Specification: Clause ID, Metric, Operator, Threshold, Unit, Severity.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    id: Optional[str] = Field(default=None, alias="_id", description="Rule unique identifier")
    clause_id: Optional[str] = Field(default=None, description="Associated Clause ID")
    metric: str = Field(..., description="Target metric (e.g. annual_turnover_cr, mii_percentage)")
    operator: str = Field(..., description="Operator (>=, >, <=, <, ==, !=, contains)")
    threshold: Any = Field(..., description="Threshold value for compliance")
    unit: str = Field(default="", description="Unit of measurement (INR_CR, %, YEARS, COUNT)")
    severity: str = Field(default="CRITICAL", description="Severity (CRITICAL, HIGH, MEDIUM, LOW)")

    # Contextual fields
    tender_id: Optional[str] = Field(default=None, description="Associated Tender ID")
    conditions: Optional[Dict[str, Any]] = Field(default=None, description="Additional conditional criteria")
    evidence_type: Optional[str] = Field(default=None, description="Expected document type (e.g. CA_CERTIFICATE)")
    verification_source: Optional[str] = Field(default=None, description="External verification connector (e.g. GSTN, UDYAM)")

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, v: Any) -> str:
        if isinstance(v, str):
            val = v.upper().strip()
            if val in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
                return val
        return "CRITICAL"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Evidence
# ─────────────────────────────────────────────────────────────────────────────
class Evidence(BaseModel):
    """
    Evidence Domain Model
    Specification: Document ID, Page Number, precise Bounding Box array [x1, y1, x2, y2], Field Name, Normalized Value, Confidence.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    id: Optional[str] = Field(default=None, alias="_id", description="Evidence unique identifier")
    document_id: str = Field(..., description="Source Document ID")
    page_number: int = Field(..., ge=1, description="1-indexed page number where evidence appears")
    bounding_box: List[float] = Field(..., min_length=4, max_length=4, description="Precise Bounding Box [x1, y1, x2, y2]")
    field_name: str = Field(..., description="Extracted field name (e.g. turnover_2023_24, gstin)")
    normalized_value: Any = Field(..., description="Normalized parsed value for deterministic checking")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score (0.0 to 1.0)")

    # Contextual integration fields
    package_id: Optional[str] = Field(default=None, description="Bid package ID")
    bidder_id: Optional[str] = Field(default=None, description="Bidder ID")
    doc_type: Optional[str] = Field(default=None, description="Classified document type (e.g. CA_CERTIFICATE, PAN_CARD, GST_CERTIFICATE)")
    raw_value: Optional[str] = Field(default=None, description="Raw OCR/extracted text")
    verification_status: str = Field(default="PENDING", description="Status (VERIFIED, MISMATCH, PENDING)")

    @model_validator(mode="before")
    @classmethod
    def map_aliases(cls, values: Any) -> Any:
        if isinstance(values, dict):
            # Support bbox -> bounding_box
            if "bbox" in values and "bounding_box" not in values:
                values["bounding_box"] = values["bbox"]
            # Support page -> page_number
            if "page" in values and "page_number" not in values:
                values["page_number"] = values["page"]
            # Support field -> field_name
            if "field" in values and "field_name" not in values:
                values["field_name"] = values["field"]
            # Support value -> raw_value / normalized_value
            if "value" in values and "raw_value" not in values:
                values["raw_value"] = str(values["value"])
            if "value" in values and "normalized_value" not in values:
                values["normalized_value"] = values["value"]
            if "_id" in values and not values.get("id"):
                values["id"] = str(values["_id"])
        return values

    @field_validator("bounding_box")
    @classmethod
    def validate_bounding_box(cls, v: List[float]) -> List[float]:
        if len(v) != 4:
            raise ValueError("bounding_box must contain exactly 4 coordinates: [x1, y1, x2, y2]")
        return [float(c) for c in v]


# ─────────────────────────────────────────────────────────────────────────────
# 4. RuleResult
# ─────────────────────────────────────────────────────────────────────────────
class RuleResult(BaseModel):
    """
    RuleResult Domain Model
    Specification: Status (PASS/FAIL/REVIEW/PENDING), Evidence IDs, Explanation.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    id: Optional[str] = Field(default=None, alias="_id", description="Result identifier")
    status: RuleStatus = Field(..., description="Evaluation status (PASS, FAIL, REVIEW, PENDING)")
    evidence_ids: List[str] = Field(default_factory=list, description="Associated Evidence IDs supporting outcome")
    explanation: str = Field(..., description="Deterministic human-readable explanation of the rule evaluation")

    # Contextual fields
    rule_id: Optional[str] = Field(default=None, description="Evaluated RequirementRule ID")
    bidder_id: Optional[str] = Field(default=None, description="Bidder ID")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Verification confidence")
    evaluated_at: datetime = Field(default_factory=utcnow, description="Evaluation timestamp")

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> RuleStatus:
        if isinstance(v, RuleStatus):
            return v
        if isinstance(v, str):
            clean = v.upper().strip()
            # Map legacy states
            mapping = {
                "COMPLIANT": "PASS",
                "NON_COMPLIANT": "FAIL",
                "PARTIAL": "REVIEW",
                "MANUAL_REVIEW": "REVIEW",
            }
            clean = mapping.get(clean, clean)
            try:
                return RuleStatus(clean)
            except ValueError:
                return RuleStatus.REVIEW
        return RuleStatus.REVIEW


# ─────────────────────────────────────────────────────────────────────────────
# 5. AuditEvent
# ─────────────────────────────────────────────────────────────────────────────
class AuditEvent(BaseModel):
    """
    AuditEvent Domain Model
    Specification: Timestamp, Actor, Action, Prev Hash, Event Hash (SHA-256).
    """
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )

    id: Optional[str] = Field(default=None, alias="_id", description="Audit event identifier")
    timestamp: datetime = Field(default_factory=utcnow, description="Timestamp of the event (UTC)")
    actor: str = Field(..., description="User ID, email, or system process performing action")
    action: str = Field(..., description="Action description (e.g. TENDER_CREATED, BID_APPROVED, OFFICER_OVERRIDE)")
    prev_hash: Optional[str] = Field(default=None, description="Previous event hash for tamper-evident blockchain chain")
    event_hash: str = Field(..., description="SHA-256 hash of this audit record")

    # Contextual fields
    entity_id: Optional[str] = Field(default=None, description="Target entity ID (Tender, Bid, Document)")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Event payload or metadata")

    @classmethod
    def generate_hash(
        cls,
        timestamp: Union[datetime, str],
        actor: str,
        action: str,
        prev_hash: Optional[str] = None,
        entity_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Compute SHA-256 hash for audit chaining."""
        ts_str = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
        payload = {
            "timestamp": ts_str,
            "actor": actor,
            "action": action,
            "prev_hash": prev_hash or "GENESIS",
            "entity_id": str(entity_id or ""),
            "details": details or {},
        }
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @model_validator(mode="before")
    @classmethod
    def auto_compute_hash(cls, values: Any) -> Any:
        if isinstance(values, dict):
            # If event_hash is not provided, compute it automatically
            if not values.get("event_hash"):
                ts = values.get("timestamp") or utcnow()
                actor = values.get("actor", "system")
                action = values.get("action", "UNKNOWN_ACTION")
                prev = values.get("prev_hash")
                ent = values.get("entity_id")
                det = values.get("details")
                values["event_hash"] = cls.generate_hash(ts, actor, action, prev, ent, det)
            if "_id" in values and not values.get("id"):
                values["id"] = str(values["_id"])
        return values
