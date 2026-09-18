"""
Udyam Verification Adapter — Demo / Simulation.

LABEL (always shown in UI): "Simulation / Authorized Adapter"
NOT labelled: "Live Government API"

Simulates the Udyam Registration Portal verification response.
Returns ACTIVE for all known demo bidders except Bidder D (timeout case).
"""

import logging
from typing import Any, Dict

from .base import VerificationConnector, VerificationResponse, VerificationStatus, utcnow

logger = logging.getLogger("gemguard.connectors.udyam")

# Demo data store — mirrors seed.py bidder data
_UDYAM_REGISTRY = {
    "UDYAM-KA-01-0034521": {
        "entity_name": "Technoserve Solutions Private Limited",
        "status": "ACTIVE",
        "enterprise_type": "Small",
        "nic_code": "62090",
        "registered_on": "2021-04-01",
    },
    "UDYAM-DL-03-0067891": {
        "entity_name": "Infralink Technologies Limited",
        "status": "ACTIVE",
        "enterprise_type": "Small",
        "nic_code": "62090",
        "registered_on": "2021-01-01",
    },
    "UDYAM-MH-02-0089234": {
        "entity_name": "DataVault Systems Private Limited",
        "status": "ACTIVE",
        "enterprise_type": "Micro",
        "nic_code": "62020",
        "registered_on": "2020-07-15",
    },
}

# Bidder D simulates a timeout — used to demonstrate UNAVAILABLE → PENDING
_TIMEOUT_IDENTIFIERS = {"UDYAM-TN-04-0012345", "TN33", "33AABNE5678F1ZQ"}


class UdyamAdapter(VerificationConnector):
    """
    Demo Udyam Registration Portal adapter.

    UI Label: Simulation / Authorized Adapter
    Source: UDYAM_MOCK
    """

    SOURCE_ID = "UDYAM_MOCK"
    SOURCE_LABEL = "Simulation / Authorized Adapter"
    FRESHNESS_HOURS = 48

    def _do_verify(self, payload: Dict[str, Any]) -> VerificationResponse:
        udyam_number = payload.get("udyam_number", "").strip().upper()
        gstin = payload.get("gstin", "").strip().upper()

        # Check for timeout simulation (Bidder D)
        if any(t in udyam_number or t in gstin for t in _TIMEOUT_IDENTIFIERS):
            logger.info("Udyam: simulating timeout for %s", udyam_number or gstin)
            return self._unavailable(
                payload,
                message="Udyam portal is temporarily unavailable. Compliance status is PENDING.",
            )

        record = _UDYAM_REGISTRY.get(udyam_number)
        if not record:
            return self._make_response(
                status=VerificationStatus.NOT_VERIFIED,
                fields={"udyam_number": udyam_number, "status": "NOT_FOUND"},
                message=f"Udyam number {udyam_number} not found in registry.",
            )

        status_val = record["status"]
        v_status = (
            VerificationStatus.VERIFIED if status_val == "ACTIVE"
            else VerificationStatus.NOT_VERIFIED
        )

        return self._make_response(
            status=v_status,
            fields={
                "udyam_number": udyam_number,
                "entity_name": record["entity_name"],
                "registration_status": status_val,
                "enterprise_type": record["enterprise_type"],
                "registered_on": record["registered_on"],
            },
            message=f"Udyam registration status: {status_val}",
            freshness_ts=utcnow(),
        )


udyam_adapter = UdyamAdapter()
