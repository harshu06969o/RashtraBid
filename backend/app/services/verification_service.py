"""
Verification Service — Stage 4.

Orchestrates verification for a bid package:
  1. Reads bidder evidence (from Stage 3 BidderEvidence rows)
  2. Selects appropriate connectors for each field
  3. Calls connectors (with retry)
  4. Maps UNAVAILABLE → PENDING (NEVER → FAIL)
  5. Stores VerificationRecord rows for every connector call
  6. Returns summary

CRITICAL RULE (NON-NEGOTIABLE):
  connector_response.status == UNAVAILABLE
  → compliance_status = PENDING
  → never FAIL

  Only deterministic rule evaluation (Stage 5+) can produce PASS or FAIL.
  Connector results are EVIDENCE INPUTS to the rules engine, not compliance verdicts.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app import models
from app.services.connectors import CONNECTOR_REGISTRY, VerificationStatus

logger = logging.getLogger("gemguard.services.verification")


# ── Field → connector routing table ────────────────────────────────────────────

# Maps evidence field name → (connector_source_id, payload_builder_fn)
def _build_udyam_payload(bidder: models.Bidder, ev: Optional[models.BidderEvidence]) -> dict:
    number = (ev.normalized_value if ev else None) or bidder.udyam_number or ""
    return {"udyam_number": number, "gstin": bidder.gstin or ""}


def _build_gst_payload(bidder: models.Bidder, ev: Optional[models.BidderEvidence]) -> dict:
    gstin = (ev.normalized_value if ev else None) or bidder.gstin or ""
    return {"gstin": gstin}


def _build_pan_payload(bidder: models.Bidder, ev: Optional[models.BidderEvidence]) -> dict:
    pan = bidder.pan or ""
    name = bidder.legal_name or bidder.name or ""
    return {"pan": pan, "name": name}


def _build_epfo_payload(bidder: models.Bidder, ev: Optional[models.BidderEvidence]) -> dict:
    pan = bidder.pan or ""
    return {"pan": pan}


_FIELD_TO_CONNECTOR = {
    "udyam_registration_status": ("UDYAM_MOCK", _build_udyam_payload),
    "udyam_number":              ("UDYAM_MOCK", _build_udyam_payload),
    "gst_registration_status":  ("GST_MOCK",   _build_gst_payload),
    "gstin":                     ("GST_MOCK",   _build_gst_payload),
}

# Always-run connectors (regardless of extracted evidence)
_DEFAULT_CONNECTORS = [
    ("GST_MOCK",   lambda b, _: {"gstin": b.gstin or ""}),
    ("UDYAM_MOCK", lambda b, _: {"udyam_number": b.udyam_number or "", "gstin": b.gstin or ""}),
    ("PAN_MOCK",   lambda b, _: {"pan": b.pan or "", "name": b.legal_name or b.name or ""}),
    ("EPFO_MOCK",  lambda b, _: {"pan": b.pan or ""}),
]


class VerificationService:
    """
    Runs the full verification pipeline for a bid package.

    Returns list of VerificationRecord ORM objects (already committed).
    """

    def run(self, db: Session, bid_package_id: int) -> List[models.VerificationRecord]:
        bid = (
            db.query(models.BidPackage)
            .filter(models.BidPackage.id == bid_package_id)
            .first()
        )
        if not bid:
            raise ValueError(f"BidPackage {bid_package_id} not found")

        bidder = bid.bidder
        if not bidder:
            raise ValueError(f"No bidder for BidPackage {bid_package_id}")

        # Gather existing evidence for this bid
        evidence_rows = (
            db.query(models.BidderEvidence)
            .filter(models.BidderEvidence.bid_package_id == bid_package_id)
            .all()
        )
        evidence_by_field = {ev.field: ev for ev in evidence_rows}

        # Delete any prior verification records for this bid (re-run)
        db.query(models.VerificationRecord).filter(
            models.VerificationRecord.bid_package_id == bid_package_id
        ).delete(synchronize_session=False)

        records: List[models.VerificationRecord] = []

        # Run each default connector (covers all required sources)
        seen_sources = set()
        for source_id, payload_fn in _DEFAULT_CONNECTORS:
            if source_id in seen_sources:
                continue
            seen_sources.add(source_id)

            connector = CONNECTOR_REGISTRY.get(source_id)
            if not connector:
                logger.warning("No connector registered for %s", source_id)
                continue

            ev = evidence_by_field.get(source_id.lower().replace("_mock", ""))
            payload = payload_fn(bidder, ev)

            logger.info("Running %s for bid=%d", source_id, bid_package_id)
            response = connector.verify(payload, retry=1)

            record = self._store_record(db, bid_package_id, source_id, response)
            records.append(record)

        db.commit()
        logger.info(
            "Verification complete: bid=%d, sources=%d, unavailable=%d",
            bid_package_id,
            len(records),
            sum(1 for r in records if r.connector_status == VerificationStatus.UNAVAILABLE),
        )
        return records

    def _store_record(
        self,
        db: Session,
        bid_package_id: int,
        source_id: str,
        response,
    ) -> models.VerificationRecord:
        """
        Store a VerificationRecord and determine compliance_hint.

        UNAVAILABLE → compliance_hint = PENDING (NEVER FAIL)
        VERIFIED    → compliance_hint = PASS_CANDIDATE (engine decides final)
        NOT_VERIFIED → compliance_hint = REVIEW
        Others      → compliance_hint = PENDING
        """
        compliance_hint = {
            VerificationStatus.VERIFIED:        "PASS_CANDIDATE",
            VerificationStatus.NOT_VERIFIED:    "REVIEW",
            VerificationStatus.UNAVAILABLE:     "PENDING",
            VerificationStatus.STALE:           "REVIEW",
            VerificationStatus.UNAUTHORIZED:    "PENDING",
            VerificationStatus.MANUAL_REQUIRED: "PENDING",
        }.get(response.status, "PENDING")

        record = models.VerificationRecord(
            bid_package_id=bid_package_id,
            source=source_id,
            source_label=response.source_label,
            connector_status=response.status,
            compliance_hint=compliance_hint,
            request_id=response.request_id,
            checked_at=response.checked_at,
            fields_verified=response.fields,
            raw_hash=response.raw_hash,
            message=response.message,
            is_fresh=response.is_fresh,
            freshness_ts=response.freshness_ts,
            retry_count=response.retry_count,
            simulated=response.simulated,
        )
        db.add(record)
        db.flush()
        return record


# Singleton
verification_service = VerificationService()
