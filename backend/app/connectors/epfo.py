"""
GeM-Guard — EPFO Connector (Employees' Provident Fund Organisation)
Simulates verification against the EPFO Unified Portal API.
"""

import re
from typing import Any, Dict
from app.connectors.base import BaseConnector, ConnectorResult, ConnectorStatus


class EPFOConnector(BaseConnector):
    """
    EPFO Adapter:
    Verifies Establishment Code, active member employee count,
    and recent Electronic Challan cum Return (ECR) compliance.
    """

    def __init__(self):
        super().__init__(name="EPFO", description="Employees' Provident Fund Organisation Portal")

    async def verify(self, query: Dict[str, Any], simulate_timeout: bool = False) -> ConnectorResult:
        if simulate_timeout:
            return self._create_timeout_result(query)

        est_code = (
            query.get("epfo_establishment_code")
            or query.get("establishment_code")
            or query.get("epfo_code")
            or ""
        ).strip().upper()

        bidder_name = (query.get("legal_name") or query.get("bidder_name") or "").strip()

        # If no establishment code provided, generate a standard formatted code based on entity
        if not est_code:
            # Check if employee count requires EPFO (mandatory if >= 20 employees)
            emp_count = query.get("employee_count", 25)
            if emp_count and int(emp_count) < 20:
                data = {
                    "establishment_code": None,
                    "exemption_reason": "LESS_THAN_20_EMPLOYEES",
                    "status": "EXEMPT",
                }
                return self._create_result(
                    status=ConnectorStatus.VERIFIED,
                    raw_data={"status_code": 200, "data": data},
                    data=data,
                    message="Employee count < 20; statutory EPFO registration is exempt.",
                )
            est_code = "TN/MAS/0098765/000"

        derived_name = bidder_name or "Bharat Engineering Ltd"
        verified_data = {
            "establishment_code": est_code,
            "establishment_name": derived_name,
            "office_name": "Chennai Regional Office",
            "active_members_count": 48,
            "last_ecr_month": "2024-08",
            "compliance_status": "COMPLIANT",
            "coverage_date": "2019-01-01",
        }

        return self._create_result(
            status=ConnectorStatus.VERIFIED,
            raw_data={"status_code": 200, "data": verified_data},
            data=verified_data,
            message=f"EPFO establishment '{est_code}' verified COMPLIANT (48 active contributing members).",
        )
