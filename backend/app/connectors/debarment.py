"""
GeM-Guard — Debarment & Blacklist Registry Connector
Simulates verification against CVC, CPPP, and GeM Incident Management Registries.
"""

from typing import Any, Dict
from app.connectors.base import BaseConnector, ConnectorResult, ConnectorStatus


class DebarmentConnector(BaseConnector):
    """
    Debarment Adapter:
    Checks if bidder PAN, GSTIN, CIN, or legal entity name is listed on:
    - GeM Incident Management (Debarred / Suspended Bidders)
    - Central Public Procurement Portal (CPPP) Banned Sellers
    - Central Vigilance Commission (CVC) Sanctions List
    - Ministry of Finance Debarment Orders (Rule 151 of GFR 2017)
    """

    def __init__(self):
        super().__init__(name="DEBARMENT", description="CVC / CPPP / GeM Debarment & Sanctions Registry")

    async def verify(self, query: Dict[str, Any], simulate_timeout: bool = False) -> ConnectorResult:
        if simulate_timeout:
            return self._create_timeout_result(query)

        pan = (query.get("pan") or "").strip().upper()
        gstin = (query.get("gstin") or "").strip().upper()
        legal_name = (query.get("legal_name") or query.get("bidder_name") or "").strip().upper()

        # Database of simulated debarred entities
        blacklisted_records = [
            {
                "name_fragment": "FRAUDULENT",
                "pan": "BADDD1234F",
                "reason": "Submission of forged CA turnover certificate in CPCL tender",
                "period": "2023-10-01 to 2026-09-30",
                "authority": "GeM Incident Management Cell",
            },
            {
                "name_fragment": "BLACKSTONE INFRA CORRUPT",
                "pan": "DEBAR9999P",
                "reason": "Cartelization and collusive bidding in IOCL procurement",
                "period": "2024-01-15 to 2027-01-14",
                "authority": "Ministry of Petroleum & Natural Gas",
            },
        ]

        # Check for blacklist match
        is_debarred = False
        matched_rec = None
        for b in blacklisted_records:
            if (pan and pan == b["pan"]) or (b["name_fragment"] in legal_name):
                is_debarred = True
                matched_rec = b
                break

        if is_debarred and matched_rec:
            debarred_data = {
                "debarred": True,
                "sanction_reason": matched_rec["reason"],
                "debarment_period": matched_rec["period"],
                "issuing_authority": matched_rec["authority"],
                "pan_checked": pan,
                "name_checked": legal_name,
            }
            return self._create_result(
                status=ConnectorStatus.MISMATCH,
                raw_data={"alert": "ENTITY_DEBARRED", "record": matched_rec},
                data=debarred_data,
                message=f"CRITICAL: Bidder is DEBARRED by {matched_rec['authority']} until {matched_rec['period']}. Reason: {matched_rec['reason']}.",
            )

        # Bidder is clean
        clean_data = {
            "debarred": False,
            "pan_checked": pan or "N/A",
            "gstin_checked": gstin or "N/A",
            "registry_checked": ["GeM Incident Management", "CPPP Blacklist", "CVC Orders"],
            "status": "CLEAR",
            "active_sanctions_count": 0,
        }

        return self._create_result(
            status=ConnectorStatus.VERIFIED,
            raw_data={"status_code": 200, "data": clean_data},
            data=clean_data,
            message="No adverse debarment or sanction records found across CVC, CPPP, and GeM registries.",
        )
