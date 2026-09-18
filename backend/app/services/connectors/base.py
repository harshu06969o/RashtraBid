"""
Verification Connector Layer — Stage 4 Base.

ARCHITECTURE PRINCIPLES
-----------------------
1. All government data sources are simulated through controlled demo adapters.
   They are clearly labelled "Simulation / Authorized Adapter" — NOT "Live Government API".

2. Each connector returns a VerificationResponse with a normalized schema.

3. UNAVAILABLE status never causes FAIL.
   UNAVAILABLE → compliance status becomes PENDING.
   The officer decides. The system never auto-rejects because a source is down.

4. No government credentials are stored, transmitted, or exposed to the frontend.

5. Request IDs and timestamps are recorded for audit.

CONNECTOR STATUS VALUES
-----------------------
VERIFIED         → adapter returned a valid response matching expected values
NOT_VERIFIED     → adapter returned a response but values don't match
UNAVAILABLE      → adapter timed out or source is down
STALE            → response is cached but older than freshness threshold
UNAUTHORIZED     → adapter received auth error (simulation: never happens in demo)
MANUAL_REQUIRED  → adapter cannot determine result; officer must verify manually
"""

import abc
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ── Status constants ───────────────────────────────────────────────────────────

class VerificationStatus:
    VERIFIED         = "VERIFIED"
    NOT_VERIFIED     = "NOT_VERIFIED"
    UNAVAILABLE      = "UNAVAILABLE"
    STALE            = "STALE"
    UNAUTHORIZED     = "UNAUTHORIZED"
    MANUAL_REQUIRED  = "MANUAL_REQUIRED"

    ALL = {VERIFIED, NOT_VERIFIED, UNAVAILABLE, STALE, UNAUTHORIZED, MANUAL_REQUIRED}


# ── Normalized response ────────────────────────────────────────────────────────

@dataclass
class VerificationResponse:
    """
    Normalized response from any verification connector.

    All connectors MUST return this schema.

    Fields
    ------
    source          : connector identifier (e.g. "UDYAM_MOCK")
    source_label    : human-readable label shown in UI
                      ALWAYS "Simulation / Authorized Adapter" for demo connectors
    status          : one of VerificationStatus.*
    request_id      : UUID for this verification attempt (for audit)
    checked_at      : UTC datetime of the check
    fields          : dict of field → verified_value pairs (what the adapter returned)
    raw_hash        : SHA-256 of the raw response (for tamper evidence in audit)
    message         : human-readable explanation (shown in UI)
    is_fresh        : whether the response is within freshness window
    freshness_ts    : when the source data was last updated (simulated)
    retry_count     : number of retries made before returning this response
    simulated       : always True for demo connectors — shown in UI
    """
    source: str
    source_label: str
    status: str
    request_id: str
    checked_at: datetime
    fields: Dict[str, Any]
    raw_hash: str
    message: str
    is_fresh: bool = True
    freshness_ts: Optional[datetime] = None
    retry_count: int = 0
    simulated: bool = True          # always True for this prototype

    def __post_init__(self):
        if self.status not in VerificationStatus.ALL:
            raise ValueError(f"Invalid status '{self.status}'. Must be one of {VerificationStatus.ALL}")

    @classmethod
    def make_id(cls) -> str:
        return str(uuid.uuid4())

    @classmethod
    def hash_response(cls, raw: dict) -> str:
        import json
        raw_bytes = json.dumps(raw, sort_keys=True, default=str).encode()
        return hashlib.sha256(raw_bytes).hexdigest()[:16]


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Abstract connector ─────────────────────────────────────────────────────────

class VerificationConnector(abc.ABC):
    """
    Abstract base for all verification connectors.

    Subclasses implement the specific adapter logic.
    All must return VerificationResponse with the correct schema.

    CRITICAL:
    - Connectors NEVER determine compliance status.
    - They return a verification result.
    - The compliance engine uses the result as one input.
    - UNAVAILABLE must never propagate as FAIL.
    """

    SOURCE_ID: str = "UNKNOWN"          # e.g. "UDYAM_MOCK"
    SOURCE_LABEL: str = "Simulation / Authorized Adapter"
    FRESHNESS_HOURS: int = 24           # how old is "stale"

    def verify(self, payload: Dict[str, Any], retry: int = 2) -> VerificationResponse:
        """
        Run verification with automatic retry on UNAVAILABLE.

        retry: maximum number of additional attempts on UNAVAILABLE (0 = no retry).
        """
        last_response = None
        for attempt in range(retry + 1):
            resp = self._do_verify(payload)
            resp.retry_count = attempt
            if resp.status != VerificationStatus.UNAVAILABLE:
                return resp
            last_response = resp

        # All retries exhausted — return the last UNAVAILABLE response
        if last_response:
            last_response.message = (
                f"Source unavailable after {retry + 1} attempt(s). "
                "Compliance status will be PENDING until source is restored."
            )
            return last_response

        return self._unavailable(payload, message="No response after retries")

    @abc.abstractmethod
    def _do_verify(self, payload: Dict[str, Any]) -> VerificationResponse:
        """Implement the actual adapter call. Must return VerificationResponse."""

    def _make_response(
        self,
        status: str,
        fields: Dict[str, Any],
        message: str,
        raw: Optional[dict] = None,
        is_fresh: bool = True,
        freshness_ts: Optional[datetime] = None,
    ) -> VerificationResponse:
        raw = raw or fields
        return VerificationResponse(
            source=self.SOURCE_ID,
            source_label=self.SOURCE_LABEL,
            status=status,
            request_id=VerificationResponse.make_id(),
            checked_at=utcnow(),
            fields=fields,
            raw_hash=VerificationResponse.hash_response(raw),
            message=message,
            is_fresh=is_fresh,
            freshness_ts=freshness_ts or utcnow(),
            simulated=True,
        )

    def _unavailable(
        self, payload: dict, message: str = "Source temporarily unavailable"
    ) -> VerificationResponse:
        return self._make_response(
            status=VerificationStatus.UNAVAILABLE,
            fields={},
            message=message,
            raw={"payload": payload, "error": "TIMEOUT"},
            is_fresh=False,
        )

    # ── Convenience method signatures (optional) ───────────────────────────────

    def verify_udyam(self, udyam_number: str) -> VerificationResponse:
        return self.verify({"udyam_number": udyam_number})

    def verify_gst(self, gstin: str) -> VerificationResponse:
        return self.verify({"gstin": gstin})

    def verify_pan(self, pan: str, name: str) -> VerificationResponse:
        return self.verify({"pan": pan, "name": name})

    def verify_epfo(self, pan: str) -> VerificationResponse:
        return self.verify({"pan": pan})

    def verify_generic(self, payload: Dict[str, Any]) -> VerificationResponse:
        return self.verify(payload)
