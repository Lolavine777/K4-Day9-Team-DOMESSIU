from typing import Dict, Any, List
from src.agents.base import BaseAgent
from src.handoff import AgentHandoff, Fact
from src.models import (
    CaseOutput,
    CaseAssessment,
    AffectedEntities,
    CustomerContext,
    ProductContext,
    DeliveryAnalysis,
    SellerHandoffAnalysis,
    PaymentReconciliation,
    RootCauseAnalysis,
    RankedCause,
    ResponsibleParty,
    FinancialResolution,
)

VALID_ROOT_CAUSES = {
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
}


class VerifierAgent(BaseAgent):
    """Agent responsible for strict evidence grounding verification and schema validation."""

    def __init__(self, repository, llm_client):
        super().__init__("VerifierAgent", repository, llm_client)

    def process_handoff(self, incoming: AgentHandoff) -> AgentHandoff:
        claimed_order_id = incoming.ticket_id

        # Consolidate all facts
        cust_fact = {}
        order_prod_fact = {}
        payment_fact = {}
        delivery_fact = {}
        policy_fact = {}

        for fact in incoming.facts_found:
            val = fact.value
            if isinstance(val, dict):
                if "customer_unique_id" in val:
                    cust_fact = val
                elif "has_items" in val:
                    order_prod_fact = val
                elif "payment_total_brl" in val:
                    payment_fact = val
                elif "delivery_variance_hours" in val:
                    delivery_fact = val
                elif "primary_issue" in val:
                    policy_fact = val

        # Assemble CaseAssessment
        assessment = CaseAssessment(
            primary_issue=policy_fact.get("primary_issue", "unsupported_late_claim"),
            secondary_issues=policy_fact.get("secondary_issues", []),
            case_status=policy_fact.get("case_status", "no_action"),
            confidence=policy_fact.get("confidence", 1.0),
        )

        # Assemble AffectedEntities
        affected = AffectedEntities(
            order_ids=[claimed_order_id],
            item_ids=order_prod_fact.get("item_ids", []),
            seller_ids=order_prod_fact.get("seller_ids", []),
            payment_ids=payment_fact.get("payment_ids", []),
        )

        # Assemble CustomerContext
        customer_ctx = CustomerContext(
            customer_unique_id=cust_fact.get("customer_unique_id", ""),
            related_order_ids=cust_fact.get("related_order_ids", []),
        )

        # Assemble ProductContext
        product_ctx = ProductContext(
            product_ids=order_prod_fact.get("product_ids", []),
            category_names=order_prod_fact.get("category_names", []),
        )

        # Assemble DeliveryAnalysis
        delivery_analysis = DeliveryAnalysis(
            delivered_at=delivery_fact.get("delivered_at"),
            estimated_delivery_at=delivery_fact.get("estimated_delivery_at"),
            carrier_handoff_at=delivery_fact.get("carrier_handoff_at"),
            delivery_variance_hours=delivery_fact.get("delivery_variance_hours"),
            seller_handoff_analysis=delivery_fact.get("seller_handoff_analysis", []),
            late_handoff_seller_ids=delivery_fact.get("late_handoff_seller_ids", []),
        )

        # Assemble PaymentReconciliation
        payment_reconcil = PaymentReconciliation(
            currency="BRL",
            item_total_brl=payment_fact.get("item_total_brl"),
            freight_total_brl=payment_fact.get("freight_total_brl"),
            expected_total_brl=payment_fact.get("expected_total_brl"),
            payment_total_brl=payment_fact.get("payment_total_brl", 0.0),
            difference_brl=payment_fact.get("difference_brl"),
            reconciled=payment_fact.get("reconciled"),
            payment_types=payment_fact.get("payment_types", []),
        )

        # Assemble RootCauseAnalysis
        root_cause_code = policy_fact.get("root_cause_code", "DELIVERY_WITHIN_ESTIMATE")
        resp_parties_raw = policy_fact.get("responsible_parties", [])
        resp_parties = [
            ResponsibleParty(party_type=p["party_type"], party_id=p["party_id"]) for p in resp_parties_raw
        ]

        root_cause_analysis = RootCauseAnalysis(
            ranked_causes=[RankedCause(cause_code=root_cause_code, rank=1)],
            responsible_parties=resp_parties,
        )

        # Grounding check for evidence_ids
        raw_evidence_ids = policy_fact.get("evidence_ids", [])
        verified_evidence_ids = []

        for eid in raw_evidence_ids:
            if self._verify_evidence_id(eid):
                verified_evidence_ids.append(eid)
            else:
                print(f"[Verifier Warning] Evidence ID ground check failed: {eid}")

        # Financial Resolution
        financial_resolution = FinancialResolution(
            currency="BRL",
            recommended_refund_brl=policy_fact.get("recommended_refund_brl", 0.0),
        )

        resolution_actions = policy_fact.get("resolution_actions", [])

        # Construct final CaseOutput
        final_output = CaseOutput(
            case_id=claimed_order_id,
            case_assessment=assessment,
            affected_entities=affected,
            customer_context=customer_ctx,
            product_context=product_ctx,
            delivery_analysis=delivery_analysis,
            payment_reconciliation=payment_reconcil,
            root_cause_analysis=root_cause_analysis,
            evidence_ids=verified_evidence_ids,
            financial_resolution=financial_resolution,
            resolution_actions=resolution_actions,
        )

        facts = [
            Fact(
                description="Output verification and evidence grounding verified",
                source_ids=verified_evidence_ids,
                value=final_output.to_dict(),
            )
        ]

        prompt = (
            f"Verifier check for {claimed_order_id}: "
            f"{len(verified_evidence_ids)} verified evidence IDs, schema valid."
        )
        llm_narrative = self.llm_client.generate(
            "You are a Quality Verification Agent.",
            prompt,
        )

        return AgentHandoff(
            ticket_id=incoming.ticket_id,
            sender=self.name,
            recipient="CoordinatorAgent",
            question="Verification complete. Final output generated.",
            facts_found=incoming.facts_found + facts,
            facts_missing=[],
            next_suggestion=f"Verification complete. LLM note: {llm_narrative[:100]}...",
        )

    def _verify_evidence_id(self, eid: str) -> bool:
        """Verify that an evidence ID exists in the underlying CSV dataset."""
        try:
            if eid.startswith("order:"):
                oid = eid.split(":", 1)[1]
                return self.repository.order_exists(oid)
            elif eid.startswith("item:"):
                parts = eid.split(":")
                oid = parts[1]
                item_seq = int(parts[2])
                return self.repository.item_exists(oid, item_seq)
            elif eid.startswith("payment:"):
                parts = eid.split(":")
                oid = parts[1]
                pay_seq = int(parts[2])
                return self.repository.payment_exists(oid, pay_seq)
            elif eid.startswith("seller:"):
                sid = eid.split(":", 1)[1]
                return self.repository.seller_exists(sid)
            elif eid.startswith("policy:"):
                code = eid.split(":", 1)[1]
                return code in VALID_ROOT_CAUSES
            return False
        except Exception:
            return False
