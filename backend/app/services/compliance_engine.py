import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app import models

logger = logging.getLogger("gemguard.compliance")

class ComplianceEngine:
    def __init__(self, db: Session):
        self.db = db

    def evaluate_bid(self, bid_package_id: int) -> List[models.RuleResult]:
        """
        Evaluate all applicable rules for a bid package.
        Uses deterministic logic (no AI for compliance decisions).
        """
        bid_package = self.db.query(models.BidPackage).filter_by(id=bid_package_id).first()
        if not bid_package:
            raise ValueError(f"Bid package {bid_package_id} not found")

        # Load rules, evidence, verifications
        rules = self.db.query(models.RequirementRule).filter_by(tender_id=bid_package.tender_id).all()
        evidence_items = self.db.query(models.BidderEvidence).filter_by(bid_package_id=bid_package_id).all()
        verifications = self.db.query(models.VerificationRecord).filter_by(bid_package_id=bid_package_id).all()

        # Group by field/metric for easy lookup
        evidence_by_metric = {}
        for ev in evidence_items:
            evidence_by_metric.setdefault(ev.field, []).append(ev)

        # Group verifications by source
        verification_by_source = {v.source: v for v in verifications}

        results = []
        for rule in rules:
            if rule.applicability == "MSME" and bid_package.bidder.category != "MSME":
                # Create NOT_APPLICABLE result
                results.append(self._create_result(
                    bid_package_id, rule.id, "NOT_APPLICABLE", "Bidder is not MSME.", []
                ))
                continue

            # Check verification dependency first
            pending_source = False
            v_ids = []
            for src in (rule.verification_sources or []):
                v_record = verification_by_source.get(src)
                if v_record:
                    v_ids.append(v_record.id)
                    if v_record.connector_status == "UNAVAILABLE":
                        pending_source = True
                else:
                    # Depending on strictness, if missing verification record, we could wait.
                    # But if we haven't run it yet, maybe just proceed or mark pending.
                    pass
            
            if pending_source:
                results.append(self._create_result(
                    bid_package_id, rule.id, "PENDING", 
                    "Verification source unavailable. Compliance check pending.",
                    [], v_ids
                ))
                continue

            # Evaluate based on rule type
            result_obj = self._evaluate_rule(bid_package_id, rule, evidence_by_metric, v_ids)
            results.append(result_obj)

        # Store results — clean existing first
        self.db.query(models.RuleResult).filter_by(bid_package_id=bid_package_id).delete()
        self.db.add_all(results)
        self.db.commit()

        # Emit audit event (Stage 8 — SHA-256 chained)
        try:
            from app.services.audit_service import append_audit_event
            pass_c = sum(1 for r in results if r.result == "PASS")
            fail_c = sum(1 for r in results if r.result in ("FAIL", "MISSING", "EXPIRED"))
            review_c = sum(1 for r in results if r.result == "REVIEW")
            pending_c = sum(1 for r in results if r.result == "PENDING")
            append_audit_event(
                db=self.db,
                event_type="RULE_EVALUATED",
                actor="compliance_engine",
                details={
                    "rules_evaluated": len(results),
                    "pass": pass_c, "fail": fail_c,
                    "review": review_c, "pending": pending_c,
                    "engine": "deterministic",
                },
                bid_package_id=bid_package_id,
            )
        except Exception as e:
            logger.warning("Failed to emit audit event: %s", e)

        # Update Risk Assessment
        self._compute_risk_assessment(bid_package_id, results)

        return results


    def _create_result(self, bid_package_id: int, rule_id: int, result: str, explanation: str, 
                       evidence_ids: List[int], verification_ids: List[int] = None, confidence: float = 1.0) -> models.RuleResult:
        return models.RuleResult(
            bid_package_id=bid_package_id,
            requirement_rule_id=rule_id,
            result=result,
            explanation=explanation,
            evidence_ids=evidence_ids or [],
            verification_ids=verification_ids or [],
            confidence=confidence,
            evaluated_at=datetime.utcnow()
        )

    def _evaluate_rule(self, bid_package_id: int, rule: models.RequirementRule, 
                       evidence_by_metric: Dict[str, List[models.BidderEvidence]], 
                       verification_ids: List[int]) -> models.RuleResult:
        
        # Cross-document consistency (NAME_MATCH)
        if rule.rule_type == "NAME_MATCH":
            # Use the rule's metric field for evidence lookup
            names = evidence_by_metric.get(rule.metric, [])
            if not names:
                return self._create_result(bid_package_id, rule.id, "MISSING", "No entity names extracted.", [], verification_ids)
            
            e_ids = [e.id for e in names]
            avg_conf = sum(e.confidence or 0 for e in names) / len(names)
            
            # Simple check: do all normalized values match?
            first_name = names[0].normalized_value
            mismatch = False
            for n in names[1:]:
                if n.normalized_value and first_name and n.normalized_value.lower() != first_name.lower():
                    mismatch = True
                    break
            
            if mismatch:
                return self._create_result(bid_package_id, rule.id, "REVIEW", "Entity names are inconsistent across documents.", e_ids, verification_ids, avg_conf)
            return self._create_result(bid_package_id, rule.id, "PASS", "Entity names are consistent.", e_ids, verification_ids, avg_conf)

        # Temporal validity
        if rule.rule_type == "CERT_VALIDITY":
            expiries = evidence_by_metric.get("expiry_date", [])
            if not expiries:
                # If rule is mandatory and no certs found, MISSING? Let's say PASS if no expiry found for now, or NOT_APPLICABLE.
                return self._create_result(bid_package_id, rule.id, "PASS", "No expiry dates found to validate.", [], verification_ids)
            
            e_ids = [e.id for e in expiries]
            for ev in expiries:
                if ev.normalized_value == "EXPIRED": # Assume normalized string for demo
                    return self._create_result(bid_package_id, rule.id, "EXPIRED", f"Certificate expired: {ev.raw_value}", e_ids, verification_ids)
            
            return self._create_result(bid_package_id, rule.id, "PASS", "All certificates are valid.", e_ids, verification_ids)

        # Fetch relevant evidence for metric
        evidences = evidence_by_metric.get(rule.metric, [])
        if not evidences:
            if rule.is_mandatory:
                return self._create_result(bid_package_id, rule.id, "MISSING", f"Missing evidence for {rule.metric}.", [], verification_ids)
            else:
                return self._create_result(bid_package_id, rule.id, "NOT_APPLICABLE", f"No evidence provided for optional rule.", [], verification_ids)

        # Use the first one or combine. Let's use the first one for simplicity.
        primary_ev = evidences[0]
        e_ids = [e.id for e in evidences]
        val = primary_ev.normalized_value
        conf = primary_ev.confidence or 1.0

        if not val:
            return self._create_result(bid_package_id, rule.id, "REVIEW", f"Could not normalize extracted value: {primary_ev.raw_value}", e_ids, verification_ids, conf)

        # Numeric threshold
        if rule.rule_type == "TURNOVER" or rule.operator in ("GTE", "GT", "LTE", "LT"):
            try:
                num_val = float(val)
                thresh = float(rule.threshold_value)
                if rule.operator == "GTE" and num_val >= thresh:
                    res = "PASS"
                    msg = f"Value {num_val} satisfies >= {thresh}"
                elif rule.operator == "GT" and num_val > thresh:
                    res = "PASS"
                    msg = f"Value {num_val} satisfies > {thresh}"
                else:
                    res = "FAIL"
                    msg = f"Value {num_val} does not satisfy {rule.operator} {thresh}"
                return self._create_result(bid_package_id, rule.id, res, msg, e_ids, verification_ids, conf)
            except ValueError:
                return self._create_result(bid_package_id, rule.id, "REVIEW", f"Non-numeric value extracted: {val}", e_ids, verification_ids, conf)

        # Equality
        if rule.operator == "ACTIVE" or rule.operator == "MATCH" or rule.operator == "EQ":
            # E.g. GST_STATUS, UDYAM
            if val.upper() == str(rule.threshold_value).upper():
                return self._create_result(bid_package_id, rule.id, "PASS", f"Status is {val}", e_ids, verification_ids, conf)
            else:
                return self._create_result(bid_package_id, rule.id, "FAIL", f"Status {val} != {rule.threshold_value}", e_ids, verification_ids, conf)

        # Default fallback
        return self._create_result(bid_package_id, rule.id, "REVIEW", "Rule evaluation fallthrough.", e_ids, verification_ids, conf)


    def _compute_risk_assessment(self, bid_package_id: int, results: List[models.RuleResult]):
        fail_c = sum(1 for r in results if r.result in ("FAIL", "EXPIRED", "MISSING"))
        review_c = sum(1 for r in results if r.result == "REVIEW")
        pending_c = sum(1 for r in results if r.result == "PENDING")
        pass_c = sum(1 for r in results if r.result == "PASS")

        if fail_c > 0:
            risk_level = "HIGH"
            summary = f"{fail_c} mandatory requirements failed."
        elif review_c > 0:
            risk_level = "MEDIUM"
            summary = f"{review_c} rules require manual review."
        elif pending_c > 0:
            risk_level = "LOW"
            summary = f"Waiting for {pending_c} pending verification sources."
        else:
            risk_level = "LOW"
            summary = "All requirements passed automatically."

        # Update or create RiskAssessment
        ra = self.db.query(models.RiskAssessment).filter_by(bid_package_id=bid_package_id).first()
        if not ra:
            ra = models.RiskAssessment(bid_package_id=bid_package_id)
            self.db.add(ra)
        
        ra.risk_level = risk_level
        ra.fail_count = fail_c
        ra.review_count = review_c
        ra.pending_count = pending_c
        ra.pass_count = pass_c
        ra.summary = summary
        ra.computed_at = datetime.utcnow()

        # Mirror risk_level onto BidPackage for fast summary queries
        bid = self.db.query(models.BidPackage).filter_by(id=bid_package_id).first()
        if bid:
            bid.risk_level = risk_level
            bid.overall_status = "FAIL" if fail_c > 0 else ("REVIEW" if review_c > 0 else ("PENDING" if pending_c > 0 else "PASS"))

        self.db.commit()

compliance_engine = ComplianceEngine
