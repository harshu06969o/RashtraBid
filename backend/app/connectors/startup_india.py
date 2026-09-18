"""
GeM-Guard — Startup India Connector (DPIIT / Ministry of Commerce & Industry)
Simulates verification against the Startup India Recognition Portal.
"""

from typing import Any, Dict
from app.connectors.base import BaseConnector, ConnectorResult, ConnectorStatus


class StartupIndiaConnector(BaseConnector):
    """
    Startup India Adapter:
    Verifies DPIIT Certificate of Recognition (DIPP number), incorporation date (<10 years),
    annual turnover (<100 Cr), and eligibility for public procurement waivers
    (Relaxation of Prior Turnover & Prior Experience under GFR 173(i)).
    """

    def __init__(self):
        super().__init__(name="STARTUP_INDIA", description="DPIIT Startup India Recognition Portal")

    async def verify(self, query: Dict[str, Any], simulate_timeout: bool = False) -> ConnectorResult:
        if simulate_timeout:
            return self._create_timeout_result(query)

        dipp_number = (
            query.get("dipp_number")
            or query.get("startup_id")
            or query.get("startup_certificate_number")
            or ""
        ).strip().upper()

        is_startup_claimed = (
            query.get("is_startup")
            or query.get("startup_declared")
            or bool(dipp_number)
        )

        bidder_name = (query.get("legal_name") or query.get("bidder_name") or "").strip()

        if not is_startup_claimed and not dipp_number:
            # Entity is not claiming startup relaxation
            data = {
                "is_recognized_startup": False,
                "exemption_claimed": False,
                "status": "NOT_APPLICABLE",
            }
            return self._create_result(
                status=ConnectorStatus.VERIFIED,
                raw_data={"status_code": 200, "data": data},
                data=data,
                message="Bidder has not claimed Startup India status; general eligibility criteria apply.",
            )

        # If DIPP number is given or startup status is claimed
        if not dipp_number:
            dipp_number = "DIPP102345"

        derived_name = bidder_name or "Bharat Engineering Ltd"
        verified_data = {
            "dipp_number": dipp_number,
            "entity_name": derived_name,
            "recognition_status": "RECOGNIZED",
            "date_of_recognition": "2021-03-10",
            "incorporation_date": "2020-11-04",
            "sector": "Industrial Goods & Green Tech",
            "turnover_relaxation_eligible": True,
            "prior_experience_relaxation_eligible": True,
            "tax_exemption_80iac": True,
        }

        return self._create_result(
            status=ConnectorStatus.VERIFIED,
            raw_data={"status_code": 200, "data": verified_data},
            data=verified_data,
            message=f"Startup recognized by DPIIT ({dipp_number}). Eligible for GFR 173(i) prior experience/turnover waiver.",
        )
