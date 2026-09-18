"""
GeM-Guard — Udyam Connector (Ministry of Micro, Small & Medium Enterprises)
Simulates verification against the Udyam / MSME Registration Portal.
"""

import re
from typing import Any, Dict
from app.connectors.base import BaseConnector, ConnectorResult, ConnectorStatus

UDYAM_REGEX = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")


class UdyamConnector(BaseConnector):
    """
    Udyam Adapter:
    Verifies MSME Udyam Registration Number, enterprise classification
    (Micro, Small, Medium), and major activity (Manufacturing/Services).
    """

    def __init__(self):
        super().__init__(name="UDYAM", description="Ministry of MSME Udyam Registration Portal")

    async def verify(self, query: Dict[str, Any], simulate_timeout: bool = False) -> ConnectorResult:
        if simulate_timeout:
            return self._create_timeout_result(query)

        udyam_number = (query.get("udyam_number") or query.get("udyam") or "").strip().upper()
        bidder_category = (query.get("category") or query.get("enterprise_type") or "").strip().upper()
        bidder_name = (query.get("legal_name") or query.get("bidder_name") or "").strip()

        if not udyam_number:
            # If the enterprise is explicitly declared as Large, MSME registration is not required
            if bidder_category in ("LARGE", "NON_MSME"):
                data = {
                    "udyam_number": None,
                    "enterprise_type": "LARGE",
                    "exemption_status": "EXEMPT",
                }
                return self._create_result(
                    status=ConnectorStatus.VERIFIED,
                    raw_data={"status_code": 200, "data": data},
                    data=data,
                    message="Bidder categorized as Large Enterprise; Udyam registration exempt.",
                )

            return self._create_result(
                status=ConnectorStatus.NOT_FOUND,
                raw_data={"error": "NO_UDYAM_PROVIDED", "query": query},
                data={"udyam_number": None, "registration_status": "NOT_PROVIDED"},
                message="No Udyam Registration Number provided for MSME verification.",
            )

        if not UDYAM_REGEX.match(udyam_number):
            return self._create_result(
                status=ConnectorStatus.MISMATCH,
                raw_data={"error": "INVALID_UDYAM_FORMAT", "udyam_number": udyam_number},
                data={"udyam_number": udyam_number, "registration_status": "INVALID_FORMAT"},
                message=f"Udyam number '{udyam_number}' does not conform to format UDYAM-XX-00-0000000.",
            )

        state_code = udyam_number[6:8]
        derived_name = bidder_name or "Bharat Engineering Ltd"
        verified_data = {
            "udyam_number": udyam_number,
            "enterprise_name": derived_name,
            "enterprise_type": "SMALL",
            "major_activity": "MANUFACTURING",
            "social_category": "GENERAL",
            "state": state_code,
            "registration_status": "ACTIVE",
            "date_of_incorporation": "2018-05-15",
            "validity": "PERPETUAL",
        }

        return self._create_result(
            status=ConnectorStatus.VERIFIED,
            raw_data={"status_code": 200, "data": verified_data},
            data=verified_data,
            message=f"Udyam registration '{udyam_number}' verified ACTIVE (Small Enterprise - Manufacturing).",
        )
