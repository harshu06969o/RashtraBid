"""
GeM-Guard — Connector Manager & Dispatcher
Central registry orchestrating all government verification connectors.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from app.connectors.base import BaseConnector, ConnectorResult, ConnectorStatus
from app.connectors.debarment import DebarmentConnector
from app.connectors.epfo import EPFOConnector
from app.connectors.gstn import GSTNConnector
from app.connectors.pan import PANConnector
from app.connectors.startup_india import StartupIndiaConnector
from app.connectors.udyam import UdyamConnector

logger = logging.getLogger("gemguard.connectors")


class ConnectorManager:
    """
    Manages and orchestrates government connector execution.
    Features:
    - Parallel / sequential execution across all 6 registries.
    - Per-connector or global simulate_timeout toggle.
    - Graceful degradation aggregation ensuring timeouts yield PENDING and never FAIL.
    """

    def __init__(self):
        self._connectors: Dict[str, BaseConnector] = {
            "GSTN": GSTNConnector(),
            "PAN": PANConnector(),
            "UDYAM": UdyamConnector(),
            "EPFO": EPFOConnector(),
            "STARTUP_INDIA": StartupIndiaConnector(),
            "DEBARMENT": DebarmentConnector(),
        }

    def get_connector(self, source: str) -> Optional[BaseConnector]:
        """Retrieve connector by source name."""
        return self._connectors.get(source.upper())

    def list_connectors(self) -> List[Dict[str, str]]:
        """List registered connectors and their descriptions."""
        return [
            {"name": c.name, "description": c.description}
            for c in self._connectors.values()
        ]

    async def verify_single(
        self,
        source: str,
        query: Dict[str, Any],
        simulate_timeout: bool = False,
    ) -> ConnectorResult:
        """Run verification on a single designated connector."""
        connector = self.get_connector(source)
        if not connector:
            raise ValueError(f"Unknown connector source: '{source}'. Available: {list(self._connectors.keys())}")
        return await connector.verify(query=query, simulate_timeout=simulate_timeout)

    async def verify_all(
        self,
        query: Dict[str, Any],
        simulate_timeout: bool = False,
        timeout_connectors: Optional[List[str]] = None,
    ) -> List[ConnectorResult]:
        """
        Run verification across all 6 government registries simultaneously.
        
        Args:
            query: Bidder data (gstin, pan, udyam_number, legal_name, etc.)
            simulate_timeout: If True, all connectors will simulate a timeout.
            timeout_connectors: Specific list of connectors to simulate timeout for (e.g. ['GSTN', 'EPFO']).
        """
        timeout_set = set(tc.upper() for tc in (timeout_connectors or []))

        tasks = []
        for name, connector in self._connectors.items():
            should_timeout = simulate_timeout or (name in timeout_set)
            tasks.append(connector.verify(query=query, simulate_timeout=should_timeout))

        results: List[ConnectorResult] = await asyncio.gather(*tasks)
        return results

    @classmethod
    def evaluate_connector_impact(cls, results: List[ConnectorResult]) -> Dict[str, Any]:
        """
        Analyzes connector results with strict adherence to SIH USP:
        - Timeouts / PENDING status MUST NEVER auto-disqualify a bid.
        - Returns compliance hint, timeout count, verified count, and mismatch count.
        """
        pending_count = sum(1 for r in results if r.status == ConnectorStatus.PENDING)
        verified_count = sum(1 for r in results if r.status == ConnectorStatus.VERIFIED)
        mismatch_count = sum(1 for r in results if r.status == ConnectorStatus.MISMATCH)
        not_found_count = sum(1 for r in results if r.status == ConnectorStatus.NOT_FOUND)

        # Check for active debarment (which is a true disqualifying risk)
        debarred_flag = any(
            r.source == "DEBARMENT" and r.status == ConnectorStatus.MISMATCH
            for r in results
        )

        if debarred_flag:
            overall_recommendation = "DISQUALIFY_DEBARRED"
        elif mismatch_count > 0:
            overall_recommendation = "SEEK_CLARIFICATION"
        elif pending_count > 0:
            overall_recommendation = "HOLD_PENDING"
        else:
            overall_recommendation = "VERIFIED_ALL_CLEAR"

        return {
            "overall_recommendation": overall_recommendation,
            "total_connectors": len(results),
            "verified_count": verified_count,
            "pending_count": pending_count,
            "mismatch_count": mismatch_count,
            "not_found_count": not_found_count,
            "has_timeouts": pending_count > 0,
            "auto_disqualified": False if not debarred_flag else True,
            "graceful_degradation_active": pending_count > 0,
        }


# Singleton manager instance
connector_manager = ConnectorManager()
