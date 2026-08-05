from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from .models import CaseOutput
from .models import CustomerHandoff, DeliveryHandoff, OrderProductHandoff, PaymentHandoff, PolicyDecision

EVIDENCE_RE = re.compile(r"^(order:[0-9a-f]+|item:[0-9a-f]+:[0-9]+|payment:[0-9a-f]+:[0-9]+|seller:[0-9a-f]+|policy:[A-Z_]+)$")


def expected_case_names() -> list[str]:
    return [f"EC_{index:03d}.json" for index in range(1, 51)]


def validate_case_payload(payload: dict) -> CaseOutput:
    output = CaseOutput.model_validate(payload)
    invalid = [evidence for evidence in output.evidence_ids if not EVIDENCE_RE.match(evidence)]
    if invalid:
        raise ValueError(f"Invalid evidence IDs: {invalid}")
    if output.case_assessment.case_status == "no_action" and output.financial_resolution.recommended_refund_brl != 0:
        raise ValueError("no_action cases must not recommend a refund")
    if output.case_assessment.case_status == "action_required" and output.financial_resolution.recommended_refund_brl <= 0:
        raise ValueError("action_required cases need a positive refund")
    return output


def validate_output_against_handoffs(
    *,
    output: CaseOutput,
    customer: CustomerHandoff,
    order_product: OrderProductHandoff,
    payment: PaymentHandoff,
    delivery: DeliveryHandoff,
    policy: PolicyDecision,
) -> None:
    """Verify the output remains a faithful projection of validated agent handoffs."""
    validate_case_payload(output.model_dump(mode="python"))
    if output.affected_entities.order_ids != [order_product.order_id]:
        raise ValueError("Output order IDs differ from order handoff")
    if output.affected_entities.item_ids != order_product.item_ids or output.affected_entities.seller_ids != order_product.seller_ids:
        raise ValueError("Output affected entities differ from order/product handoff")
    if output.affected_entities.payment_ids != payment.payment_ids:
        raise ValueError("Output payment IDs differ from payment handoff")
    if output.customer_context.customer_unique_id != customer.customer_unique_id or output.customer_context.related_order_ids != customer.related_order_ids:
        raise ValueError("Output customer context differs from customer handoff")
    reconciliation = output.payment_reconciliation
    if (
        reconciliation.item_total_brl != order_product.item_total_brl
        or reconciliation.freight_total_brl != order_product.freight_total_brl
        or reconciliation.expected_total_brl != payment.expected_total_brl
        or reconciliation.payment_total_brl != payment.payment_total_brl
        or reconciliation.difference_brl != payment.difference_brl
        or reconciliation.reconciled != payment.reconciled
    ):
        raise ValueError("Output reconciliation differs from source-backed handoffs")
    if (
        output.delivery_analysis.delivered_at != delivery.delivered_at
        or output.delivery_analysis.estimated_delivery_at != delivery.estimated_delivery_at
        or output.delivery_analysis.carrier_handoff_at != delivery.carrier_handoff_at
        or output.delivery_analysis.delivery_variance_hours != delivery.delivery_variance_hours
        or output.delivery_analysis.seller_handoff_analysis != delivery.seller_handoff_analysis
        or output.delivery_analysis.late_handoff_seller_ids != delivery.late_handoff_seller_ids
    ):
        raise ValueError("Output delivery analysis differs from delivery handoff")
    if output.case_assessment.primary_issue != policy.primary_issue or output.case_assessment.secondary_issues != policy.secondary_issues:
        raise ValueError("Output issue assessment differs from policy handoff")
    if output.financial_resolution.recommended_refund_brl != policy.recommended_refund_brl or output.resolution_actions != policy.resolution_actions:
        raise ValueError("Output financial resolution differs from policy handoff")
    if output.root_cause_analysis.ranked_causes[0].cause_code != policy.root_cause_code:
        raise ValueError("Output root cause differs from policy handoff")
    expected_evidence = [f"order:{order_product.order_id}"]
    expected_evidence.extend(f"item:{item_id}" for item_id in order_product.item_ids)
    expected_evidence.extend(f"payment:{payment_id}" for payment_id in payment.payment_ids)
    expected_evidence.extend(f"seller:{party.party_id}" for party in policy.responsible_parties if party.party_type == "seller")
    expected_evidence.append(f"policy:{policy.root_cause_code}")
    if output.evidence_ids != expected_evidence:
        raise ValueError("Output evidence IDs differ from validated source-backed evidence")


def validate_directory(output_dir: Path, *, require_full_set: bool = True) -> list[CaseOutput]:
    names = sorted(path.name for path in output_dir.glob("EC_*.json"))
    if require_full_set and names != expected_case_names():
        raise ValueError(f"Expected exactly {len(expected_case_names())} output files, found {len(names)}")
    outputs: list[CaseOutput] = []
    for name in names:
        payload = json.loads((output_dir / name).read_text(encoding="utf-8"))
        output = validate_case_payload(payload)
        if output.case_id + ".json" != name:
            raise ValueError(f"Filename/case_id mismatch: {name}")
        outputs.append(output)
    return outputs
