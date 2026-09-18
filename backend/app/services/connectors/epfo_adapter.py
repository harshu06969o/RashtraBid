"""
EPFO Verification Adapter — Demo / Simulation.
UI Label: "Simulation / Authorized Adapter"
Source: EPFO_MOCK

Bidder D deliberately times out to demonstrate UNAVAILABLE → PENDING behavior.
CRITICAL: UNAVAILABLE must NEVER produce FAIL compliance status.
"""

import logging
from typing import Any, Dict

from .base import VerificationConnector, VerificationResponse, VerificationStatus, utcnow

logger = logging.getLogger("gemguard.connectors.epfo")

_EPFO_REGISTRY = {
    "AABCT1332L": {"status": "ACTIVE", "establishment_code": "KA/BAN/012345", "employees": ">20"},
    "AACCI4520M": {"status": "ACTIVE", "establishment_code": "DL/DEL/067890", "employees": ">20"},
    "AABCD1234E": {"status": "ACTIVE", "establishment_code": "MH/MUM/089234", "employees": "10-20"},
}

# Bidder D (PAN: AABNE5678F) → simulates EPFO portal timeout
_TIMEOUT_PANS = {"AABNE5678F"}


class EPFOAdapter(VerificationConnector):
    SOURCE_ID = "EPFO_MOCK"
    SOURCE_LABEL = "Simulation / Authorized Adapter"
    FRESHNESS_HOURS = 48

    def _do_verify(self, payload: Dict[str, Any]) -> VerificationResponse:
        pan = payload.get("pan", "").strip().upper()[:10]

        if pan in _TIMEOUT_PANS:
            logger.info("EPFO: simulating timeout for PAN=%s (Bidder D demo)", pan)
            return self._unavailable(
                payload,
                message=(
                    "EPFO portal is temporarily unavailable. "
                    "Compliance status is PENDING — system does not mark this as FAIL. "
                    "Officer should verify manually or retry when source is restored."
                ),
            )

        record = _EPFO_REGISTRY.get(pan)
        if not record:
            return self._make_response(
                status=VerificationStatus.MANUAL_REQUIRED,
                fields={"pan": pan, "epfo_status": "NOT_FOUND"},
                message="EPFO record not found. Officer must verify employment compliance manually.",
            )

        v_status = VerificationStatus.VERIFIED if record["status"] == "ACTIVE" else VerificationStatus.NOT_VERIFIED
        return self._make_response(
            status=v_status,
            fields={
                "pan": pan,
                "epfo_status": record["status"],
                "establishment_code": record["establishment_code"],
                "employee_count_band": record["employees"],
            },
            message=f"EPFO compliance status: {record['status']}",
            freshness_ts=utcnow(),
        )


epfo_adapter = EPFOAdapter()
