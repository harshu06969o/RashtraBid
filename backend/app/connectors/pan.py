"""
GeM-Guard — PAN Connector (Income Tax Department / NSDL / UTIITSL)
Simulates verification against the Income Tax PAN Verification Gateway.
"""

import re
from typing import Any, Dict
from app.connectors.base import BaseConnector, ConnectorResult, ConnectorStatus

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")


class PANConnector(BaseConnector):
    """
    PAN Adapter:
    Verifies 10-character Permanent Account Number, entity type code (4th character),
    and active status with the Income Tax Department.
    """

    def __init__(self):
        super().__init__(name="PAN", description="Income Tax Department PAN Verification Gateway")

    async def verify(self, query: Dict[str, Any], simulate_timeout: bool = False) -> ConnectorResult:
        if simulate_timeout:
            return self._create_timeout_result(query)

        pan = (query.get("pan") or "").strip().upper()
        # Fallback: Derive PAN from GSTIN if PAN not explicitly given
        gstin = (query.get("gstin") or "").strip().upper()
        if not pan and len(gstin) == 15:
            pan = gstin[2:12]

        bidder_name = (query.get("legal_name") or query.get("bidder_name") or "").strip()

        if not pan:
            return self._create_result(
                status=ConnectorStatus.NOT_FOUND,
                raw_data={"error": "NO_PAN_PROVIDED", "query": query},
                data={"pan": None, "pan_status": "NOT_PROVIDED"},
                message="No PAN provided for verification.",
            )

        if not PAN_REGEX.match(pan):
            return self._create_result(
                status=ConnectorStatus.MISMATCH,
                raw_data={"error": "INVALID_PAN_FORMAT", "pan": pan},
                data={"pan": pan, "pan_status": "INVALID_FORMAT"},
                message=f"PAN '{pan}' does not conform to the 10-character statutory format.",
            )

        # 4th character denotes entity type: C = Company, P = Person, H = HUF, F = Firm, A = AOP, T = Trust
        entity_char = pan[3]
        entity_types = {
            "C": "Company",
            "P": "Individual",
            "H": "Hindu Undivided Family",
            "F": "Partnership Firm / LLP",
            "A": "Association of Persons",
            "T": "Trust",
            "G": "Government Agency",
        }
        entity_type_desc = entity_types.get(entity_char, "Corporate Entity")

        known_bad_pans = {
            "XXXXX0000X": {"status": "DEACTIVATED", "reason": "Non-compliant with Aadhaar linkage"},
            "DEFPG1234F": {"status": "INACTIVE", "reason": "Surrendered / Duplicate PAN"},
        }

        if pan in known_bad_pans:
            rec = known_bad_pans[pan]
            return self._create_result(
                status=ConnectorStatus.MISMATCH,
                raw_data={"pan": pan, "response": rec},
                data={"pan": pan, "pan_status": rec["status"], "entity_type": entity_type_desc},
                message=f"PAN '{pan}' is {rec['status']}: {rec['reason']}.",
            )

        derived_name = bidder_name or "Bharat Engineering Ltd"
        verified_data = {
            "pan": pan,
            "pan_status": "ACTIVE",
            "entity_type": entity_type_desc,
            "registered_name": derived_name,
            "aadhaar_seeding_status": "LINKED_OR_EXEMPT",
            "last_updated": "2024-04-01",
        }

        return self._create_result(
            status=ConnectorStatus.VERIFIED,
            raw_data={"status_code": 200, "data": verified_data},
            data=verified_data,
            message=f"PAN '{pan}' verified ACTIVE ({entity_type_desc}) for '{derived_name}'.",
        )
