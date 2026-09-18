"""
GeM-Guard — Base Connector & Data Contracts
Strict Specifications:
1. Standard connector outputting: source, status, timestamp, and raw_hash.
2. Status Enum: VERIFIED, MISMATCH, NOT_FOUND, UNAVAILABLE, PENDING.
3. Graceful Degradation: Boolean simulate_timeout toggle returning status PENDING.
"""

import abc
import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ConnectorStatus(str, Enum):
    """Standardized connector verification statuses."""
    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    NOT_FOUND = "NOT_FOUND"
    UNAVAILABLE = "UNAVAILABLE"
    PENDING = "PENDING"


def utcnow_str() -> str:
    """Current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def compute_sha256(data: Any) -> str:
    """Deterministic SHA-256 hash calculation for raw payloads."""
    if isinstance(data, (dict, list)):
        payload = json.dumps(data, sort_keys=True, default=str)
    elif isinstance(data, str):
        payload = data
    else:
        payload = str(data)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ConnectorResult(BaseModel):
    """
    Standardized Government Verification Result.
    Strictly required attributes: source, status, timestamp, raw_hash.
    """
    source: str = Field(..., description="Government Registry / Source Name (e.g. GSTN, PAN, UDYAM)")
    status: ConnectorStatus = Field(..., description="Verification status")
    timestamp: str = Field(default_factory=utcnow_str, description="ISO 8601 UTC timestamp")
    raw_hash: str = Field(..., description="SHA-256 hash of raw upstream response payload")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Structured verified attributes")
    message: str = Field(default="", description="Human-readable verification narrative")
    is_timeout: bool = Field(default=False, description="True if result was triggered by a timeout / simulation")
    simulated: bool = Field(default=True, description="True for simulated sandbox connectors")

    class Config:
        use_enum_values = True


class BaseConnector(abc.ABC):
    """
    Abstract Base Connector for Government Registries.
    Ensures unified interface, deterministic hashing, and timeout handling.
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name.upper()
        self.description = description

    def _create_timeout_result(self, query: Dict[str, Any]) -> ConnectorResult:
        """Standardized response when an external API times out (SIH Graceful Degradation)."""
        timeout_payload = {
            "source": self.name,
            "status": "TIMEOUT",
            "query": query,
            "error": "Connection timed out after 10000ms. External gateway unreachable.",
        }
        raw_hash = compute_sha256(timeout_payload)
        return ConnectorResult(
            source=self.name,
            status=ConnectorStatus.PENDING,
            timestamp=utcnow_str(),
            raw_hash=raw_hash,
            data={"timeout_details": timeout_payload},
            message=f"{self.name} external API service timed out. Graceful degradation active: status held as PENDING (never FAIL).",
            is_timeout=True,
            simulated=True,
        )

    def _create_result(
        self,
        status: ConnectorStatus,
        raw_data: Any,
        data: Optional[Dict[str, Any]] = None,
        message: str = "",
    ) -> ConnectorResult:
        """Create a standard connector result with calculated raw_hash."""
        raw_hash = compute_sha256(raw_data)
        return ConnectorResult(
            source=self.name,
            status=status,
            timestamp=utcnow_str(),
            raw_hash=raw_hash,
            data=data or {},
            message=message or f"{self.name} returned status {status.value}",
            is_timeout=False,
            simulated=True,
        )

    @abc.abstractmethod
    async def verify(
        self,
        query: Dict[str, Any],
        simulate_timeout: bool = False,
    ) -> ConnectorResult:
        """
        Verify bidder records against external registry.
        
        Args:
            query: Dict containing identifiers (e.g. gstin, pan, udyam_number, legal_name)
            simulate_timeout: If True, adapter MUST output status PENDING without failing the bid.
        """
        pass
