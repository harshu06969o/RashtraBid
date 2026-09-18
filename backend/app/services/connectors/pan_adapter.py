"""
PAN Verification Adapter — Demo / Simulation.
UI Label: "Simulation / Authorized Adapter"
Source: PAN_MOCK
"""

import logging
from typing import Any, Dict

from .base import VerificationConnector, VerificationResponse, VerificationStatus, utcnow

logger = logging.getLogger("gemguard.connectors.pan")

_PAN_REGISTRY = {
    "AABCT1332L": {
        "name": "TECHNOSERVE SOLUTIONS PRIVATE LIMITED",
        "status": "VALID",
        "pan_type": "Company",
    },
    "AACCI4520M": {
        "name": "INFRALINK TECHNOLOGIES LIMITED",
        "status": "VALID",
        "pan_type": "Company",
    },
    "AABCD1234E": {
        "name": "DATAVAULT SYSTEMS PRIVATE LIMITED",
        "status": "VALID",
        "pan_type": "Company",
    },
}

_TIMEOUT_PANS = {"AABNE5678F"}


class PANAdapter(VerificationConnector):
    SOURCE_ID = "PAN_MOCK"
    SOURCE_LABEL = "Simulation / Authorized Adapter"
    FRESHNESS_HOURS = 168  # 7 days

    def _do_verify(self, payload: Dict[str, Any]) -> VerificationResponse:
        pan = payload.get("pan", "").strip().upper()[:10]
        submitted_name = payload.get("name", "").strip().upper()

        if pan in _TIMEOUT_PANS:
            return self._unavailable(
                payload,
                message="Income Tax PAN portal is temporarily unavailable. Compliance status is PENDING.",
            )

        record = _PAN_REGISTRY.get(pan)
        if not record:
            return self._make_response(
                status=VerificationStatus.NOT_VERIFIED,
                fields={"pan": pan, "status": "NOT_FOUND"},
                message=f"PAN {pan} not found.",
            )

        name_match = (not submitted_name) or (submitted_name in record["name"] or record["name"] in submitted_name)
        v_status = VerificationStatus.VERIFIED if (record["status"] == "VALID" and name_match) else VerificationStatus.NOT_VERIFIED

        return self._make_response(
            status=v_status,
            fields={
                "pan": pan,
                "registered_name": record["name"],
                "pan_status": record["status"],
                "pan_type": record["pan_type"],
                "name_match": name_match,
            },
            message=f"PAN status: {record['status']}, name match: {name_match}",
            freshness_ts=utcnow(),
        )


pan_adapter = PANAdapter()
