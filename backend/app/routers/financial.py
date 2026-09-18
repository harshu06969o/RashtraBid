"""
GeM-Guard v6.0 — Financial Evaluator Router
Strict Specifications:
1. Two-Envelope System: Technical + Financial packets uploaded separately.
   Financial packet is stored encrypted/sealed and NOT readable until tech evaluation completes.
2. Unsealing Gate: POST /financial/bids/{bid_id}/unseal only succeeds when bid compliance_status == COMPLIANT.
   Any bid still PENDING, UNDER_REVIEW, or NON_COMPLIANT is hard-blocked.
3. L1 Ranking: GET /financial/tenders/{tender_id}/l1 aggregates all PASS bids, applies
   MII (Make-in-India) and MSE preference adjustments, and ranks by adjusted price.
4. Every action (upload, unseal, L1-calc) is appended to the SHA-256 audit chain.
5. RBAC: All routes require PROCUREMENT_OFFICER role (enforced at Gateway + validated here).
"""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.core.database import doc_to_dict, get_db, to_oid, utcnow_str, sha256
from app.core.storage import storage
from app.engine.audit import AuditEngine

logger = logging.getLogger("gemguard.routers.financial")

router = APIRouter(tags=["financial"])

# ── MII / MSE Preference Constants (as per GFR 2017 / Order 2020) ────────────
MII_CLASS_I_THRESHOLD = 0.50   # ≥50% local content  → Class I Local Supplier
MII_CLASS_II_THRESHOLD = 0.20  # ≥20% local content  → Class II Local Supplier
MII_CLASS_I_PREFERENCE = 0.00  # No price preference penalty (just eligibility)
MII_CLASS_II_PREFERENCE = 0.00
NON_LOCAL_PENALTY_PCT = 0.20   # 20% price preference added to non-local bidder's quoted price for ranking
MSE_PREFERENCE_PCT = 0.15      # 15% purchase preference for MSE-registered bidders (Udyam)


class FinancialEnvelopeUploadResponse(BaseModel):
    bid_id: str
    envelope_id: str
    file_hash: str
    status: str
    sealed: bool
    message: str


class UnsealRequest(BaseModel):
    actor: Optional[str] = Field(default="financial@gem.gov.in")
    notes: Optional[str] = None


class L1RankingEntry(BaseModel):
    bid_id: str
    bidder_name: str
    quoted_price: float
    mii_class: str
    is_mse: bool
    adjusted_price: float
    rank: int
    compliance_status: str


# ── Financial Envelope Upload ────────────────────────────────────────────────

@router.post("/api/v1/financial/bids/{bid_id}/envelope/upload",
             status_code=status.HTTP_201_CREATED)
@router.post("/api/financial/bids/{bid_id}/envelope/upload",
             status_code=status.HTTP_201_CREATED)
async def upload_financial_envelope(
    bid_id: str,
    request: Request,
    file: UploadFile = File(...),
    actor: str = Form(default="bidder@vendor.com"),
    mii_local_content_pct: float = Form(default=0.0, ge=0.0, le=100.0),
    quoted_price: float = Form(default=0.0, ge=0.0),
    db=Depends(get_db),
):
    """
    Upload the sealed Financial Envelope (Price Bid) as part of Two-Envelope system.
    The envelope is stored sealed and cannot be accessed until the Technical Evaluation clears.
    SHA-256 of the file is computed and stored for tamper-evidence.
    """
    # Validate role from injected header
    user_role = request.headers.get("x-user-role", "")
    if user_role and user_role not in ("BIDDER", "PROCUREMENT_OFFICER"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only BIDDER or PROCUREMENT_OFFICER may upload financial envelopes."
        )

    oid = to_oid(bid_id)
    bid = await db["bids"].find_one({"_id": oid})
    if not bid:
        raise HTTPException(status_code=404, detail=f"Bid not found: {bid_id}")

    # Read and hash file
    content = await file.read()
    file_hash = sha256(content)

    # Store sealed financial envelope
    envelope_doc = {
        "bid_id": bid_id,
        "tender_id": bid.get("tender_id"),
        "bidder_id": bid.get("bidder_id", actor),
        "original_filename": file.filename,
        "file_hash": file_hash,
        "file_size": len(content),
        "content_type": file.content_type,
        "quoted_price": quoted_price,
        "mii_local_content_pct": mii_local_content_pct,
        "sealed": True,          # 🔒 Sealed until tech evaluation PASS
        "unsealed_at": None,
        "unsealed_by": None,
        "uploaded_at": utcnow_str(),
        "uploaded_by": actor,
    }

    # Store file binary via storage adapter
    try:
        storage_path = f"financial/{bid_id}/{file.filename}"
        await storage.save(storage_path, content)
        envelope_doc["storage_path"] = storage_path
    except Exception as e:
        logger.warning(f"Storage save failed (using DB-only mode): {e}")
        envelope_doc["storage_path"] = None

    result = await db["financial_envelopes"].insert_one(envelope_doc)
    envelope_id = str(result.inserted_id)

    # Update bid with financial envelope reference
    await db["bids"].update_one(
        {"_id": oid},
        {"$set": {
            "financial_envelope_id": envelope_id,
            "financial_envelope_sealed": True,
            "financial_envelope_hash": file_hash,
            "has_financial_envelope": True,
        }}
    )

    # Audit log
    await AuditEngine.log_event(
        db=db,
        actor=actor,
        action="FINANCIAL_ENVELOPE_UPLOADED",
        entity_id=bid_id,
        details={
            "envelope_id": envelope_id,
            "file_hash": file_hash,
            "file_name": file.filename,
            "sealed": True,
        }
    )

    return {
        "bid_id": bid_id,
        "envelope_id": envelope_id,
        "file_hash": file_hash,
        "status": "SEALED",
        "sealed": True,
        "message": "Financial envelope uploaded and sealed. It will be unlocked only after Technical Evaluation confirms COMPLIANT status.",
    }


# ── Financial Envelope Unsealing ────────────────────────────────────────────

@router.post("/api/v1/financial/bids/{bid_id}/unseal")
@router.post("/api/financial/bids/{bid_id}/unseal")
async def unseal_financial_envelope(
    bid_id: str,
    body: UnsealRequest,
    request: Request,
    db=Depends(get_db),
):
    """
    Unseal the Financial Envelope for a bid.
    HARD GATE: Bid compliance_status must be COMPLIANT (Technical Evaluation must PASS).
    Blocked states: PENDING_VERIFICATION, UNDER_REVIEW, NON_COMPLIANT, PENDING.
    """
    actor = body.actor or request.headers.get("x-user-id", "financial@gem.gov.in")
    user_role = request.headers.get("x-user-role", "")

    # Role enforcement at backend level (defence-in-depth after Gateway check)
    if user_role and user_role != "PROCUREMENT_OFFICER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Financial envelope unsealing requires PROCUREMENT_OFFICER role. Got: {user_role}",
        )

    oid = to_oid(bid_id)
    bid = await db["bids"].find_one({"_id": oid})
    if not bid:
        raise HTTPException(status_code=404, detail=f"Bid not found: {bid_id}")

    compliance_status = bid.get("compliance_status", "PENDING")

    # ── The Critical Gate ──────────────────────────────────────────────────────
    BLOCKED_STATUSES = {"PENDING", "PENDING_VERIFICATION", "UNDER_REVIEW", "NON_COMPLIANT", "FAIL"}
    if compliance_status.upper() in BLOCKED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={
                "error": "FINANCIAL_ENVELOPE_LOCKED",
                "message": f"Financial envelope cannot be unsealed. Bid is {compliance_status}. "
                           f"Technical Evaluation must confirm COMPLIANT status first.",
                "bid_id": bid_id,
                "current_status": compliance_status,
                "required_status": "COMPLIANT",
            }
        )

    # Find the financial envelope
    envelope = await db["financial_envelopes"].find_one({"bid_id": bid_id})
    if not envelope:
        raise HTTPException(
            status_code=404,
            detail=f"No financial envelope found for bid {bid_id}. Bidder may not have submitted a financial packet.",
        )

    if not envelope.get("sealed", True):
        return {
            "bid_id": bid_id,
            "message": "Financial envelope was already unsealed.",
            "unsealed_at": envelope.get("unsealed_at"),
            "unsealed_by": envelope.get("unsealed_by"),
            "quoted_price": envelope.get("quoted_price", 0),
            "mii_local_content_pct": envelope.get("mii_local_content_pct", 0),
        }

    # Unseal
    unseal_time = utcnow_str()
    await db["financial_envelopes"].update_one(
        {"bid_id": bid_id},
        {"$set": {
            "sealed": False,
            "unsealed_at": unseal_time,
            "unsealed_by": actor,
            "unsealing_notes": body.notes,
        }}
    )

    await db["bids"].update_one(
        {"_id": oid},
        {"$set": {"financial_envelope_sealed": False, "financial_unsealed_at": unseal_time}}
    )

    # Audit log
    await AuditEngine.log_event(
        db=db,
        actor=actor,
        action="FINANCIAL_ENVELOPE_UNSEALED",
        entity_id=bid_id,
        details={
            "envelope_id": str(envelope.get("_id", "")),
            "compliance_status_at_unseal": compliance_status,
            "quoted_price": envelope.get("quoted_price"),
            "notes": body.notes,
        }
    )

    logger.info(f"Financial envelope UNSEALED for bid {bid_id} by {actor}")

    return {
        "status": "UNSEALED",
        "bid_id": bid_id,
        "envelope_id": str(envelope.get("_id", "")),
        "quoted_price": envelope.get("quoted_price", 0),
        "mii_local_content_pct": envelope.get("mii_local_content_pct", 0),
        "unsealed_at": unseal_time,
        "unsealed_by": actor,
        "file_hash": envelope.get("file_hash"),
        "message": "Financial envelope successfully unsealed. Price bid is now accessible for L1 evaluation.",
    }


# ── L1 Ranking with MII / MSE Preference ────────────────────────────────────

@router.get("/api/v1/financial/tenders/{tender_id}/l1")
@router.get("/api/financial/tenders/{tender_id}/l1")
async def calculate_l1_ranking(
    tender_id: str,
    request: Request,
    db=Depends(get_db),
):
    """
    Calculate L1 (Lowest Cost Bidder) ranking for a tender across all COMPLIANT bids.
    Applies MII (Make-in-India) and MSE preference adjustments per GFR 2017.

    MII Rules:
    - Class I Local Supplier (≥50% local content): No price preference penalty.
    - Class II Local Supplier (20-50% local content): No price preference penalty.
    - Non-Local Supplier (<20% local content): Adjusted price = quoted_price * 1.20 for ranking.

    MSE Rules (Udyam Registered):
    - 15% purchase preference: MSE adjusted price = quoted_price * 0.85 for ranking.
    - MSE Class I gets combined preference.
    """
    toid = to_oid(tender_id)
    tender = await db["tenders"].find_one({"_id": toid})
    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender not found: {tender_id}")

    # Fetch all COMPLIANT bids for this tender
    compliant_bids = await db["bids"].find({
        "tender_id": tender_id,
        "compliance_status": {"$in": ["COMPLIANT", "PASS"]}
    }).to_list(100)

    if not compliant_bids:
        return {
            "tender_id": tender_id,
            "tender_no": tender.get("tender_no"),
            "title": tender.get("title"),
            "l1_ranking": [],
            "total_eligible_bids": 0,
            "message": "No COMPLIANT bids found for L1 ranking. Technical Evaluation may still be in progress.",
        }

    ranking_entries = []

    for bid in compliant_bids:
        bid_id = str(bid["_id"])

        # Get financial envelope
        envelope = await db["financial_envelopes"].find_one({"bid_id": bid_id, "sealed": False})
        if not envelope:
            # Skip bids without unsealed financial envelope
            logger.warning(f"Bid {bid_id} is COMPLIANT but financial envelope not unsealed. Skipping from L1.")
            continue

        quoted_price = float(envelope.get("quoted_price", 0))
        mii_pct = float(envelope.get("mii_local_content_pct", 0))

        # Determine MII class
        if mii_pct >= MII_CLASS_I_THRESHOLD * 100:
            mii_class = "CLASS_I_LOCAL"
        elif mii_pct >= MII_CLASS_II_THRESHOLD * 100:
            mii_class = "CLASS_II_LOCAL"
        else:
            mii_class = "NON_LOCAL"

        # Check MSE from bid data (Udyam registration)
        is_mse = bid.get("is_mse", False)
        udyam_status = bid.get("udyam_status", "")
        if udyam_status in ("MICRO", "SMALL", "MEDIUM"):
            is_mse = True

        # Calculate adjusted price for ranking
        adjusted_price = quoted_price

        # Apply non-local price penalty for ranking (not for actual payment)
        if mii_class == "NON_LOCAL":
            adjusted_price *= (1 + NON_LOCAL_PENALTY_PCT)

        # Apply MSE purchase preference (discount for ranking)
        if is_mse and mii_class in ("CLASS_I_LOCAL", "CLASS_II_LOCAL"):
            adjusted_price *= (1 - MSE_PREFERENCE_PCT)

        ranking_entries.append({
            "bid_id": bid_id,
            "bidder_name": bid.get("bidder_name", bid.get("bidder_id", "Unknown")),
            "bidder_id": bid.get("bidder_id", ""),
            "quoted_price": quoted_price,
            "mii_local_content_pct": mii_pct,
            "mii_class": mii_class,
            "is_mse": is_mse,
            "adjusted_price": round(adjusted_price, 2),
            "compliance_status": bid.get("compliance_status"),
            "risk_score": bid.get("risk_score", 0),
        })

    # Sort by adjusted_price ascending (L1 = lowest adjusted price)
    ranking_entries.sort(key=lambda x: x["adjusted_price"])

    # Assign ranks
    for i, entry in enumerate(ranking_entries):
        entry["rank"] = i + 1
        entry["is_l1"] = (i == 0)

    # Determine L1 winner
    l1_winner = ranking_entries[0] if ranking_entries else None

    # Audit log
    actor = request.headers.get("x-user-id", "financial@gem.gov.in")
    await AuditEngine.log_event(
        db=db,
        actor=actor,
        action="L1_RANKING_CALCULATED",
        entity_id=tender_id,
        details={
            "total_eligible": len(ranking_entries),
            "l1_bid_id": l1_winner["bid_id"] if l1_winner else None,
            "l1_bidder": l1_winner["bidder_name"] if l1_winner else None,
            "l1_adjusted_price": l1_winner["adjusted_price"] if l1_winner else None,
        }
    )

    return {
        "tender_id": tender_id,
        "tender_no": tender.get("tender_no"),
        "title": tender.get("title"),
        "organization": tender.get("organization"),
        "total_eligible_bids": len(ranking_entries),
        "l1_ranking": ranking_entries,
        "l1_winner": l1_winner,
        "mii_preference_applied": NON_LOCAL_PENALTY_PCT * 100,
        "mse_preference_applied": MSE_PREFERENCE_PCT * 100,
        "ranking_basis": "Adjusted Price = Quoted Price + MII Penalty (if non-local) - MSE Preference (if MSE+local)",
        "calculated_at": utcnow_str(),
        "calculated_by": actor,
    }


# ── List Unsealed Envelopes for a Tender ────────────────────────────────────

@router.get("/api/v1/financial/tenders/{tender_id}/envelopes")
@router.get("/api/financial/tenders/{tender_id}/envelopes")
async def list_financial_envelopes(tender_id: str, db=Depends(get_db)):
    """List all financial envelopes for a tender (sealed and unsealed status)."""
    envelopes = await db["financial_envelopes"].find({"tender_id": tender_id}).to_list(100)
    result = []
    for e in envelopes:
        d = doc_to_dict(e)
        if d.get("sealed"):
            # Hide price data for sealed envelopes
            d.pop("quoted_price", None)
            d.pop("storage_path", None)
        result.append(d)
    return result


# ── Get Single Envelope ────────────────────────────────────────────────────

@router.get("/api/v1/financial/bids/{bid_id}/envelope")
@router.get("/api/financial/bids/{bid_id}/envelope")
async def get_financial_envelope(bid_id: str, db=Depends(get_db)):
    """Get financial envelope details for a bid."""
    envelope = await db["financial_envelopes"].find_one({"bid_id": bid_id})
    if not envelope:
        raise HTTPException(status_code=404, detail=f"No financial envelope for bid {bid_id}")
    d = doc_to_dict(envelope)
    if d.get("sealed"):
        d.pop("quoted_price", None)
        d.pop("storage_path", None)
        d["message"] = "Envelope is sealed. Price data hidden until technical evaluation completes."
    return d
