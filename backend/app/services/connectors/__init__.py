"""
Connectors package — Stage 4.

Exports all demo adapters and the connector registry.
"""

from .base import VerificationConnector, VerificationResponse, VerificationStatus
from .udyam_adapter import udyam_adapter
from .gst_adapter import gst_adapter
from .pan_adapter import pan_adapter
from .epfo_adapter import epfo_adapter

# Registry: source_id → connector instance
CONNECTOR_REGISTRY: dict[str, VerificationConnector] = {
    "UDYAM_MOCK": udyam_adapter,
    "GST_MOCK":   gst_adapter,
    "PAN_MOCK":   pan_adapter,
    "EPFO_MOCK":  epfo_adapter,
}

__all__ = [
    "VerificationConnector",
    "VerificationResponse",
    "VerificationStatus",
    "CONNECTOR_REGISTRY",
    "udyam_adapter",
    "gst_adapter",
    "pan_adapter",
    "epfo_adapter",
]
