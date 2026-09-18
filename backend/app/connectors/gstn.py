"""
GeM-Guard — GSTN Connector (Goods & Services Tax Network)
Simulates verification against the GST Common Portal API.
"""

import re
from typing import Any, Dict
from app.connectors.base import BaseConnector, ConnectorResult, ConnectorStatus

GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")


class GSTNConnector(BaseConnector):
    """
    GSTN Adapter:
    Verifies GSTIN validity, registration status (ACTIVE/CANCELLED/SUSPENDED),
    business legal name, and return filing compliance.
    """

    def __init__(self):
        super().__init__(name="GSTN", description="GST Common Portal / Goods and Services Tax Network")

    async def verify(self, query: Dict[str, Any], simulate_timeout: bool = False) -> ConnectorResult:
        if simulate_timeout:
            return self._create_timeout_result(query)

        gstin = (query.get("gstin") or "").strip().upper()
        bidder_name = (query.get("legal_name") or query.get("bidder_name") or "").strip()

        if not gstin:
            return self._create_result(
                status=ConnectorStatus.NOT_FOUND,
                raw_data={"error": "NO_GSTIN_PROVIDED", "query": query},
                data={"gstin": None, "registration_status": "NOT_PROVIDED"},
                message="No GSTIN provided for verification.",
            )

        if not GSTIN_REGEX.match(gstin):
            return self._create_result(
                status=ConnectorStatus.MISMATCH,
                raw_data={"error": "INVALID_GSTIN_FORMAT", "gstin": gstin},
                data={"gstin": gstin, "registration_status": "INVALID_FORMAT"},
                message=f"GSTIN '{gstin}' does not conform to the 15-character statutory format.",
            )

        # Mock database of specific GSTIN statuses for realistic evaluation
        known_bad_gstins = {
            "29ABCDE1234F1Z5": {"status": "CANCELLED", "legal_name": "Defunct Enterprise Ltd"},
            "07AABCS9999K1ZZ": {"status": "SUSPENDED", "legal_name": "Suspended Supplier LLP"},
        }

        if gstin in known_bad_gstins:
            rec = known_bad_gstins[gstin]
            return self._create_result(
                status=ConnectorStatus.MISMATCH,
                raw_data={"gstin": gstin, "response": rec},
                data={
                    "gstin": gstin,
                    "legal_name": rec["legal_name"],
                    "registration_status": rec["status"],
                    "state_code": gstin[:2],
                    "taxpayer_type": "Regular",
                },
                message=f"GSTIN '{gstin}' is {rec['status']} in GSTN database.",
            )

        # Successful verification
        derived_legal_name = bidder_name or "Bharat Engineering Ltd"
        verified_data = {
            "gstin": gstin,
            "legal_name": derived_legal_name,
            "trade_name": derived_legal_name,
            "registration_status": "ACTIVE",
            "state_code": gstin[:2],
            "taxpayer_type": "Regular",
            "date_of_registration": "2017-07-01",
            "annual_return_filed": True,
            "einvoice_enabled": True,
        }

        return self._create_result(
            status=ConnectorStatus.VERIFIED,
            raw_data={"status_code": 200, "data": verified_data},
            data=verified_data,
            message=f"GSTIN '{gstin}' verified ACTIVE. Registered under '{derived_legal_name}'.",
        )
