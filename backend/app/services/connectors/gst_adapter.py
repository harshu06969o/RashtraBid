"""
GST Verification Adapter — Demo / Simulation.

UI Label: "Simulation / Authorized Adapter"
Source: GST_MOCK

Simulates GSTN portal verification.
Returns ACTIVE for known demo GSTINs. Timeout for Bidder D.
"""

import logging
from typing import Any, Dict

from .base import VerificationConnector, VerificationResponse, VerificationStatus, utcnow

logger = logging.getLogger("gemguard.connectors.gst")

_GST_REGISTRY = {
    "29AABCT1332L1ZX": {
        "trade_name": "Technoserve Solutions Private Limited",
        "legal_name": "TECHNOSERVE SOLUTIONS PRIVATE LIMITED",
        "registration_status": "ACTIVE",
        "state": "Karnataka",
        "state_code": "29",
        "taxpayer_type": "Regular",
        "registration_date": "2017-07-01",
    },
    "07AACCI4520M1ZP": {
        "trade_name": "Infralink Technologies",
        "legal_name": "INFRALINK TECHNOLOGIES LIMITED",
        "registration_status": "ACTIVE",
        "state": "Delhi",
        "state_code": "07",
        "taxpayer_type": "Regular",
        "registration_date": "2017-07-01",
    },
    "27AABCD1234E1ZY": {
        "trade_name": "DataVault Systems",
        "legal_name": "DATAVAULT SYSTEMS PRIVATE LIMITED",
        "registration_status": "ACTIVE",
        "state": "Maharashtra",
        "state_code": "27",
        "taxpayer_type": "Regular",
        "registration_date": "2018-04-01",
    },
}

# Bidder D — simulates timeout (GST portal unreachable)
_TIMEOUT_GSTINS = {"33AABNE5678F1ZQ"}


class GSTAdapter(VerificationConnector):
    SOURCE_ID = "GST_MOCK"
    SOURCE_LABEL = "Simulation / Authorized Adapter"
    FRESHNESS_HOURS = 24

    def _do_verify(self, payload: Dict[str, Any]) -> VerificationResponse:
        gstin = payload.get("gstin", "").strip().upper()

        if gstin in _TIMEOUT_GSTINS:
            logger.info("GST: simulating timeout for %s", gstin)
            return self._unavailable(
                payload,
                message="GSTN portal is temporarily unavailable. Compliance status is PENDING.",
            )

        record = _GST_REGISTRY.get(gstin)
        if not record:
            return self._make_response(
                status=VerificationStatus.NOT_VERIFIED,
                fields={"gstin": gstin, "registration_status": "NOT_FOUND"},
                message=f"GSTIN {gstin} not found in registry.",
            )

        reg_status = record["registration_status"]
        v_status = (
            VerificationStatus.VERIFIED if reg_status == "ACTIVE"
            else VerificationStatus.NOT_VERIFIED
        )

        return self._make_response(
            status=v_status,
            fields={
                "gstin": gstin,
                "legal_name": record["legal_name"],
                "trade_name": record["trade_name"],
                "registration_status": reg_status,
                "taxpayer_type": record["taxpayer_type"],
                "state": record["state"],
                "registration_date": record["registration_date"],
            },
            message=f"GST registration status: {reg_status}",
            freshness_ts=utcnow(),
        )


gst_adapter = GSTAdapter()
