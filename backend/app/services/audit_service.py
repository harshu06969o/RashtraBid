"""
Stage 8 — Audit Service
SHA-256 chained audit log. Every event is immutably linked to its predecessor.
Tamper-evidence: changing any event breaks all subsequent hashes.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app import models

logger = logging.getLogger("gemguard.audit")

ALLOWED_OFFICER_ACTIONS = {
    "ACCEPT",
    "REJECT",
    "SEEK_CLARIFICATION",
    "MARK_PENDING",
    "OVERRIDE",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _event_payload(event_type: str, actor: str, details: Dict, ts: str, prev_hash: str) -> str:
    """Canonical deterministic string for hashing."""
    return json.dumps({
        "event_type": event_type,
        "actor": actor or "",
        "details": details or {},
        "ts": ts,
        "prev_hash": prev_hash or "",
    }, sort_keys=True, ensure_ascii=False)


def get_last_hash(db: Session, bid_package_id: Optional[int]) -> Optional[str]:
    """Return the event_hash of the most recent audit event for this bid (or globally)."""
    q = db.query(models.AuditEvent.event_hash).order_by(models.AuditEvent.id.desc())
    if bid_package_id is not None:
        q = q.filter(models.AuditEvent.bid_package_id == bid_package_id)
    row = q.first()
    return row[0] if row else None


def append_audit_event(
    db: Session,
    event_type: str,
    actor: Optional[str],
    details: Optional[Dict[str, Any]],
    bid_package_id: Optional[int] = None,
    commit: bool = True,
) -> models.AuditEvent:
    """
    Append a new audit event with SHA-256 chain linkage.
    NEVER call this from frontend-only code — events must be server-side only.
    """
    prev_hash = get_last_hash(db, bid_package_id)
    ts = _utcnow()
    ts_str = ts.isoformat()

    payload = _event_payload(event_type, actor or "", details or {}, ts_str, prev_hash or "")
    event_hash = _sha256(payload)

    event = models.AuditEvent(
        bid_package_id=bid_package_id,
        event_type=event_type,
        actor=actor,
        details=details or {},
        created_at=ts,
        prev_hash=prev_hash,
        event_hash=event_hash,
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    logger.info("AuditEvent[%s] actor=%s bid=%s hash=%s…", event_type, actor, bid_package_id, event_hash[:12])
    return event


def verify_chain(db: Session, bid_package_id: Optional[int]) -> Dict[str, Any]:
    """
    Replay every audit event and verify hash integrity.
    Events without event_hash (seeded before Stage 8) are skipped.
    Returns: { valid: bool, events_checked: int, broken_at: int|None }
    """
    events = (
        db.query(models.AuditEvent)
        .filter(models.AuditEvent.bid_package_id == bid_package_id)
        .order_by(models.AuditEvent.id.asc())
        .all()
    )
    prev_hash_seen: Optional[str] = None
    checked = 0
    for ev in events:
        # Skip legacy events that predate Stage 8 hashing
        if ev.event_hash is None:
            prev_hash_seen = None  # reset chain at each unhashed event
            continue
        ts_str = ev.created_at.isoformat() if ev.created_at else ""
        payload = _event_payload(ev.event_type, ev.actor or "", ev.details or {}, ts_str, prev_hash_seen or "")
        expected = _sha256(payload)
        if expected != ev.event_hash:
            return {"valid": False, "events_checked": checked + 1, "broken_at": ev.id}
        checked += 1
        prev_hash_seen = ev.event_hash

    return {"valid": True, "events_checked": checked, "broken_at": None}
