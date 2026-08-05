from __future__ import annotations

from .models import (
    AffectedEntities,
    CaseAssessment,
    CaseInput,
    CaseOutput,
    CustomerContext,
    CustomerHandoff,
    DeliveryAnalysis,
    DeliveryHandoff,
    FinancialResolution,
    OrderProductHandoff,
    PaymentHandoff,
    PaymentReconciliation,
    PolicyDecision,
    ProductContext,
    RankedCause,
    RootCauseAnalysis,
)

REFERENCE_CONFIDENCE = 0.92


def build_output(
    *,
    case: CaseInput,
    customer: CustomerHandoff,
    order_product: OrderProductHandoff,
    payment: PaymentHandoff,
    delivery: DeliveryHandoff,
    policy: PolicyDecision,
) -> CaseOutput:
    evidence = [f"order:{order_product.order_id}"]
    evidence.extend(f"item:{item_id}" for item_id in order_product.item_ids)
    evidence.extend(f"payment:{payment_id}" for payment_id in payment.payment_ids)
    evidence.extend(f"seller:{party.party_id}" for party in policy.responsible_parties if party.party_type == "seller")
    evidence.append(f"policy:{policy.root_cause_code}")
    return CaseOutput(
        case_id=case.case_id,
        case_assessment=CaseAssessment(
            primary_issue=policy.primary_issue,
            secondary_issues=policy.secondary_issues,
            case_status=policy.case_status,
            confidence=REFERENCE_CONFIDENCE,
        ),
        affected_entities=AffectedEntities(
            order_ids=[order_product.order_id],
            item_ids=order_product.item_ids,
            seller_ids=order_product.seller_ids,
            payment_ids=payment.payment_ids,
        ),
        customer_context=CustomerContext(
            customer_unique_id=customer.customer_unique_id,
            related_order_ids=customer.related_order_ids,
        ),
        product_context=ProductContext(product_ids=order_product.product_ids, category_names=order_product.category_names),
        delivery_analysis=DeliveryAnalysis(
            delivered_at=delivery.delivered_at,
            estimated_delivery_at=delivery.estimated_delivery_at,
            carrier_handoff_at=delivery.carrier_handoff_at,
            delivery_variance_hours=delivery.delivery_variance_hours,
            seller_handoff_analysis=delivery.seller_handoff_analysis,
            late_handoff_seller_ids=delivery.late_handoff_seller_ids,
        ),
        payment_reconciliation=PaymentReconciliation(
            item_total_brl=order_product.item_total_brl,
            freight_total_brl=order_product.freight_total_brl,
            expected_total_brl=payment.expected_total_brl,
            payment_total_brl=payment.payment_total_brl,
            difference_brl=payment.difference_brl,
            reconciled=payment.reconciled,
            payment_types=payment.payment_types,
        ),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause(cause_code=policy.root_cause_code, rank=1)],
            responsible_parties=policy.responsible_parties,
        ),
        evidence_ids=evidence,
        financial_resolution=FinancialResolution(recommended_refund_brl=policy.recommended_refund_brl),
        resolution_actions=policy.resolution_actions,
    )
