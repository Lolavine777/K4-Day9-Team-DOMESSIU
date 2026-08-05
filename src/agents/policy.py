from typing import Dict, Any, List
from src.agents.base import BaseAgent
from src.handoff import AgentHandoff, Fact
from src.models import (
    CaseAssessment,
    RootCauseAnalysis,
    RankedCause,
    ResponsibleParty,
    FinancialResolution,
)


class PolicyAgent(BaseAgent):
    """Agent responsible for applying EC_POLICY_V2 and generating financial resolution."""

    def __init__(self, repository, llm_client):
        super().__init__("PolicyAgent", repository, llm_client)

    def process_handoff(self, incoming: AgentHandoff) -> AgentHandoff:
        claimed_order_id = incoming.ticket_id

        # Consolidate facts from previous agents
        cust_fact = {}
        order_prod_fact = {}
        payment_fact = {}
        delivery_fact = {}

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

        order_status = delivery_fact.get("order_status") or ""
        payment_total_brl = payment_fact.get("payment_total_brl", 0.0)
        freight_total_brl = payment_fact.get("freight_total_brl") or 0.0
        delivery_variance = delivery_fact.get("delivery_variance_hours")
        late_seller_ids = delivery_fact.get("late_handoff_seller_ids") or []
        reconciled = payment_fact.get("reconciled")
        payment_rows_count = payment_fact.get("payment_rows_count", 0)

        # 1. Determine Primary Issue
        primary_issue = ""
        root_cause_code = ""
        responsible_parties: List[ResponsibleParty] = []
        recommended_refund_brl = 0.0

        if order_status == "canceled" and payment_total_brl > 0:
            primary_issue = "canceled_order_paid"
            root_cause_code = "ORDER_CANCELED_AFTER_PAYMENT"
            responsible_parties = [ResponsibleParty(party_type="platform", party_id="OLIST_PLATFORM")]
            recommended_refund_brl = payment_total_brl

        elif order_status == "unavailable" and payment_total_brl > 0:
            primary_issue = "unavailable_order_paid"
            root_cause_code = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
            responsible_parties = [ResponsibleParty(party_type="platform", party_id="OLIST_PLATFORM")]
            recommended_refund_brl = payment_total_brl

        elif delivery_variance is not None and delivery_variance > 0:
            if len(late_seller_ids) > 0:
                primary_issue = "late_delivery_seller"
                root_cause_code = "SELLER_HANDOFF_AFTER_LIMIT"
                responsible_parties = [
                    ResponsibleParty(party_type="seller", party_id=sid) for sid in late_seller_ids
                ]
                recommended_refund_brl = freight_total_brl
            else:
                primary_issue = "late_delivery_logistics"
                root_cause_code = "CARRIER_DELIVERED_AFTER_ESTIMATE"
                responsible_parties = [
                    ResponsibleParty(party_type="logistics_provider", party_id="LOGISTICS_PROVIDER")
                ]
                recommended_refund_brl = freight_total_brl

        elif payment_rows_count >= 2 and reconciled is True:
            primary_issue = "valid_split_payment"
            root_cause_code = "MULTIPLE_PAYMENTS_RECONCILED"
            responsible_parties = []
            recommended_refund_brl = 0.0

        else:
            primary_issue = "unsupported_late_claim"
            root_cause_code = "DELIVERY_WITHIN_ESTIMATE"
            responsible_parties = []
            recommended_refund_brl = 0.0

        # 2. Determine Secondary Issues (strict fixed order)
        secondary_issues = []
        if order_prod_fact.get("multi_item_order"):
            secondary_issues.append("multi_item_order")
        if order_prod_fact.get("multi_seller_order"):
            secondary_issues.append("multi_seller_order")
        if payment_fact.get("split_payment"):
            secondary_issues.append("split_payment")
        if cust_fact.get("is_repeat_customer"):
            secondary_issues.append("repeat_customer")
        if order_prod_fact.get("multiple_categories"):
            secondary_issues.append("multiple_categories")

        # 3. Determine Case Status
        case_status = "action_required" if recommended_refund_brl > 0 else "no_action"

        # 4. Determine Resolution Actions (strict order)
        PRIMARY_ACTIONS = {
            "canceled_order_paid": "issue_full_refund",
            "unavailable_order_paid": "issue_full_refund",
            "late_delivery_seller": "refund_freight",
            "late_delivery_logistics": "refund_freight",
            "valid_split_payment": "explain_valid_split_payment",
            "unsupported_late_claim": "reject_late_refund",
        }
        resolution_actions = [PRIMARY_ACTIONS[primary_issue]]

        if primary_issue == "late_delivery_seller":
            resolution_actions.append("review_seller_handoff")
        elif primary_issue == "late_delivery_logistics":
            resolution_actions.append("review_carrier_delay")

        if primary_issue in (
            "canceled_order_paid",
            "unavailable_order_paid",
            "late_delivery_seller",
            "late_delivery_logistics",
        ):
            resolution_actions.append("verify_refund_completion")

        if order_prod_fact.get("multi_seller_order"):
            resolution_actions.append("coordinate_multi_seller_case")

        if payment_fact.get("split_payment") and primary_issue != "valid_split_payment":
            resolution_actions.append("verify_payment_allocation")

        resolution_actions = resolution_actions[:5]

        # 5. Build Evidence IDs
        evidence_ids = [f"order:{claimed_order_id}"]

        for item_id in order_prod_fact.get("item_ids", []):
            evidence_ids.append(f"item:{item_id}")

        for pid in payment_fact.get("payment_ids", []):
            evidence_ids.append(f"payment:{pid}")

        if primary_issue == "late_delivery_seller":
            for sid in late_seller_ids:
                evidence_ids.append(f"seller:{sid}")

        evidence_ids.append(f"policy:{root_cause_code}")
        evidence_ids = evidence_ids[:20]

        facts = [
            Fact(
                description="Policy evaluation completed",
                source_ids=evidence_ids,
                value={
                    "primary_issue": primary_issue,
                    "secondary_issues": secondary_issues,
                    "case_status": case_status,
                    "confidence": 1.0,
                    "root_cause_code": root_cause_code,
                    "responsible_parties": [rp.to_dict() for rp in responsible_parties],
                    "recommended_refund_brl": round(recommended_refund_brl, 2),
                    "resolution_actions": resolution_actions,
                    "evidence_ids": evidence_ids,
                },
            )
        ]

        prompt = (
            f"Policy evaluation for {claimed_order_id}: "
            f"primary_issue={primary_issue}, refund={recommended_refund_brl} BRL, "
            f"status={case_status}."
        )
        llm_narrative = self.llm_client.generate(
            "You are a Policy Decision Agent applying EC_POLICY_V2.",
            prompt,
        )

        return AgentHandoff(
            ticket_id=incoming.ticket_id,
            sender=self.name,
            recipient="VerifierAgent",
            question="Verify final output structure and evidence grounding.",
            facts_found=incoming.facts_found + facts,
            facts_missing=[],
            next_suggestion=f"Policy applied. LLM note: {llm_narrative[:100]}...",
        )
