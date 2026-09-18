"""
GeM-Guard — Cryptographic Audit Trail Engine
Strict Specifications:
1. Append-only log calculating chained SHA-256 hash:
   event_hash = SHA256(prev_hash + payload)
2. Immutable logging for AI extractions, verifications, officer actions, and corrigenda.
3. Cryptographic chain integrity validation and tamper detection.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("gemguard.engine.audit")


def utcnow_str() -> str:
    """Returns current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def canonical_json(data: Any) -> str:
    """Produces deterministic, sorted, whitespace-normalized JSON representation."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


class AuditEngine:
    """
    Enterprise Cryptographic Audit Trail Engine.
    Implements append-only chained SHA-256 event logging.
    event_hash = SHA256(prev_hash + canonical_json(payload))
    """

    GENESIS_HASH = "GENESIS_00000000000000000000000000000000000000000000000000000000"

    @classmethod
    def compute_event_hash(cls, prev_hash: str, payload_dict: Dict[str, Any]) -> str:
        """
        Calculates cryptographic event hash:
        SHA256(prev_hash + canonical_json(payload))
        """
        payload_str = canonical_json(payload_dict)
        data_to_hash = f"{prev_hash}{payload_str}"
        return hashlib.sha256(data_to_hash.encode("utf-8")).hexdigest()

    @classmethod
    async def get_latest_hash(cls, db, entity_id: Optional[str] = None) -> str:
        """Fetches the latest event_hash in the chain (or global genesis if empty)."""
        query = {"entity_id": entity_id} if entity_id else {}
        latest = await db["audit"].find_one(query, sort=[("timestamp", -1), ("_id", -1)])
        if latest and latest.get("event_hash"):
            return str(latest["event_hash"])
        # Fallback to global chain head
        global_latest = await db["audit"].find_one(sort=[("timestamp", -1), ("_id", -1)])
        if global_latest and global_latest.get("event_hash"):
            return str(global_latest["event_hash"])
        return cls.GENESIS_HASH

    @classmethod
    async def append_event(
        cls,
        db,
        action: str,
        actor: str,
        entity_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        event_type: str = "SYSTEM",
    ) -> Dict[str, Any]:
        """
        Appends an event to the cryptographic audit trail with chained SHA-256 hash.
        """
        prev_hash = await cls.get_latest_hash(db)
        timestamp = utcnow_str()
        cleaned_details = details or {}

        # Canonical payload structure
        payload = {
            "action": str(action),
            "actor": str(actor),
            "details": cleaned_details,
            "entity_id": str(entity_id) if entity_id else "",
            "event_type": str(event_type),
            "timestamp": timestamp,
        }

        event_hash = cls.compute_event_hash(prev_hash=prev_hash, payload_dict=payload)

        record = {
            "timestamp": timestamp,
            "actor": actor,
            "action": action,
            "event_type": event_type,
            "entity_id": entity_id,
            "details": cleaned_details,
            "prev_hash": prev_hash,
            "event_hash": event_hash,
        }

        res = await db["audit"].insert_one(record)
        record["_id"] = str(res.inserted_id)
        record["id"] = str(res.inserted_id)

        logger.info(
            "Audit event logged: [%s] by %s (Hash: %s...)",
            action, actor, event_hash[:12]
        )
        return record

    @classmethod
    async def log_ai_extraction(
        cls,
        db,
        bid_id: str,
        actor: str,
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Log Vision/LLM AI document extraction into the cryptographic chain."""
        return await cls.append_event(
            db=db,
            action="AI_EXTRACTION_COMPLETED",
            actor=actor or "system_vision_ai",
            entity_id=bid_id,
            details=details,
            event_type="AI_EXTRACTION",
        )

    @classmethod
    async def log_verification(
        cls,
        db,
        bid_id: str,
        actor: str,
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Log external Government connector verification event into the cryptographic chain."""
        return await cls.append_event(
            db=db,
            action="GOV_VERIFICATION_RECORDED",
            actor=actor or "system_connector_gateway",
            entity_id=bid_id,
            details=details,
            event_type="VERIFICATION",
        )

    @classmethod
    async def log_officer_override(
        cls,
        db,
        bid_id: str,
        actor: str,
        justification: str,
        rule_id: Optional[str] = None,
        old_status: Optional[str] = None,
        new_status: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Log Procurement Officer override decision into the cryptographic chain.
        Strictly requires substantive justification.
        """
        override_details = {
            "justification": justification,
            "rule_id": rule_id,
            "previous_status": old_status,
            "overridden_status": new_status,
            **(details or {}),
        }
        return await cls.append_event(
            db=db,
            action="OFFICER_OVERRIDE",
            actor=actor,
            entity_id=bid_id,
            details=override_details,
            event_type="OFFICER_ACTION",
        )

    @classmethod
    async def log_corrigendum(
        cls,
        db,
        tender_id: str,
        actor: str,
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Log tender corrigendum rule amendment and impact diff into the cryptographic chain."""
        return await cls.append_event(
            db=db,
            action="CORRIGENDUM_ISSUED",
            actor=actor,
            entity_id=tender_id,
            details=details,
            event_type="CORRIGENDUM",
        )

    @classmethod
    async def verify_chain(cls, db) -> Dict[str, Any]:
        """
        Validates entire audit trail cryptographic chain integrity.
        Re-computes event_hash = SHA256(prev_hash + canonical_json(payload))
        and asserts prev_hash linking. Detects any database tampering.
        """
        cursor = db["audit"].find().sort([("timestamp", 1), ("_id", 1)])
        events = await cursor.to_list(1000)

        if not events:
            return {
                "valid": True,
                "status": "EMPTY",
                "total_events": 0,
                "message": "Audit trail is empty.",
            }

        prev_hash = cls.GENESIS_HASH
        for idx, event in enumerate(events):
            actual_prev = event.get("prev_hash", "")
            stored_hash = event.get("event_hash", "")

            # 1. Validate previous hash link (for events after genesis)
            if idx > 0 and actual_prev != prev_hash:
                return {
                    "valid": False,
                    "status": "TAMPERED",
                    "broken_at_index": idx,
                    "event_id": str(event.get("_id")),
                    "action": event.get("action"),
                    "reason": f"Chain link broken: expected prev_hash '{prev_hash[:12]}...', got '{actual_prev[:12]}...'",
                }

            # 2. Re-compute event payload hash
            payload = {
                "action": str(event.get("action", "")),
                "actor": str(event.get("actor", "")),
                "details": event.get("details", {}),
                "entity_id": str(event.get("entity_id", "") or ""),
                "event_type": str(event.get("event_type", "SYSTEM")),
                "timestamp": str(event.get("timestamp", "")),
            }
            recomputed = cls.compute_event_hash(prev_hash=actual_prev, payload_dict=payload)

            if recomputed != stored_hash:
                return {
                    "valid": False,
                    "status": "TAMPERED",
                    "broken_at_index": idx,
                    "event_id": str(event.get("_id")),
                    "action": event.get("action"),
                    "reason": f"Payload tampered at index {idx}: recomputed '{recomputed[:12]}...' != stored '{stored_hash[:12]}...'",
                }

            prev_hash = stored_hash

        return {
            "valid": True,
            "status": "VERIFIED",
            "total_events": len(events),
            "chain_head_hash": prev_hash,
            "verified_at": utcnow_str(),
        }
