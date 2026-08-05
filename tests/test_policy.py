from decimal import Decimal

from dispute_agents.models import DeliveryHandoff, OrderProductHandoff, PaymentHandoff
from dispute_agents.policy import PolicyEngine


def order_product(*, items=1, sellers=("seller-1",), freight="12.50"):
    return OrderProductHandoff(
        order_id="order-1",
        order_status="delivered",
        item_ids=[f"order-1:{index}" for index in range(1, items + 1)],
        seller_ids=list(sellers),
        product_ids=[f"product-{index}" for index in range(1, items + 1)],
        category_names=["category"],
        item_total_brl=Decimal("100.00"),
        freight_total_brl=Decimal(freight),
        seller_shipping_limits={seller: "2018-01-10 00:00:00" for seller in sellers},
        item_count=items,
        seller_count=len(sellers),
        category_count=1,
    )


def payment(*, rows=1, total="112.50", expected="112.50", reconciled=True):
    return PaymentHandoff(
        payment_ids=[f"order-1:{index}" for index in range(1, rows + 1)],
        payment_types=["credit_card"],
        payment_total_brl=Decimal(total),
        expected_total_brl=Decimal(expected) if expected is not None else None,
        difference_brl=Decimal(total) - Decimal(expected) if expected is not None else None,
        reconciled=reconciled,
        payment_count=rows,
    )


def delivery(*, late=False, late_sellers=()):
    return DeliveryHandoff(
        delivered_at="2018-01-12 00:00:00" if late else "2018-01-09 00:00:00",
        estimated_delivery_at="2018-01-10 00:00:00",
        carrier_handoff_at="2018-01-11 00:00:00" if late else "2018-01-09 00:00:00",
        delivery_variance_hours=Decimal("48.00") if late else Decimal("-24.00"),
        seller_handoff_analysis=[],
        late_handoff_seller_ids=list(late_sellers),
        all_late_handoff_seller_ids=list(late_sellers),
    )


def test_canceled_paid_has_priority_over_late_delivery():
    facts = order_product(items=2)
    facts.order_status = "canceled"

    decision = PolicyEngine().decide(
        order_product=facts,
        payment=payment(rows=2),
        delivery=delivery(late=True, late_sellers=("seller-1",)),
        is_repeat_customer=True,
    )

    assert decision.primary_issue == "canceled_order_paid"
    assert decision.root_cause_code == "ORDER_CANCELED_AFTER_PAYMENT"
    assert decision.recommended_refund_brl == Decimal("112.50")
    assert decision.resolution_actions == [
        "issue_full_refund",
        "verify_refund_completion",
        "verify_payment_allocation",
    ]


def test_unavailable_order_without_items_keeps_item_reconciliation_null():
    facts = OrderProductHandoff(
        order_id="order-1",
        order_status="unavailable",
        item_ids=[],
        seller_ids=[],
        product_ids=[],
        category_names=[],
        item_total_brl=Decimal("0.00"),
        freight_total_brl=Decimal("0.00"),
        seller_shipping_limits={},
        item_count=0,
        seller_count=0,
        category_count=0,
    )
    decision = PolicyEngine().decide(
        order_product=facts,
        payment=payment(total="54.40", expected=None, reconciled=None),
        delivery=DeliveryHandoff.empty(),
        is_repeat_customer=True,
    )

    assert decision.primary_issue == "unavailable_order_paid"
    assert decision.recommended_refund_brl == Decimal("54.40")
    assert decision.case_status == "action_required"


def test_late_fourth_seller_is_used_for_policy_even_when_output_sellers_are_capped():
    facts = order_product(items=4, sellers=("seller-1", "seller-2", "seller-3"))
    facts.seller_count = 4
    facts.seller_shipping_limits["seller-4"] = "2018-01-10 00:00:00"
    late_delivery = delivery(late=True)
    late_delivery.all_late_handoff_seller_ids = ["seller-4"]

    decision = PolicyEngine().decide(
        order_product=facts,
        payment=payment(),
        delivery=late_delivery,
        is_repeat_customer=False,
    )

    assert decision.primary_issue == "late_delivery_seller"
    assert decision.responsible_parties[0].party_id == "seller-4"
