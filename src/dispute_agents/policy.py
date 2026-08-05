from __future__ import annotations

from decimal import Decimal

from .models import DeliveryHandoff, OrderProductHandoff, PaymentHandoff, PolicyDecision, ResponsibleParty


class PolicyEngine:
    """The deterministic EC_POLICY_V2 reference implementation."""

    def decide(
        self,
        *,
        order_product: OrderProductHandoff,
        payment: PaymentHandoff,
        delivery: DeliveryHandoff,
        is_repeat_customer: bool,
    ) -> PolicyDecision:
        secondary = self._secondary_issues(order_product, payment, is_repeat_customer)
        payment_count = payment.payment_count
        payment_paid = payment.payment_total_brl > Decimal("0")
        delivered_late = (delivery.delivery_variance_hours or Decimal("0")) > Decimal("0")

        if order_product.order_status == "canceled" and payment_paid:
            return self._decision(
                "canceled_order_paid", secondary, "ORDER_CANCELED_AFTER_PAYMENT",
                [ResponsibleParty(party_type="platform", party_id="OLIST_PLATFORM")],
                payment.payment_total_brl, "issue_full_refund",
            )
        if order_product.order_status == "unavailable" and payment_paid:
            return self._decision(
                "unavailable_order_paid", secondary, "ORDER_UNAVAILABLE_AFTER_PAYMENT",
                [ResponsibleParty(party_type="platform", party_id="OLIST_PLATFORM")],
                payment.payment_total_brl, "issue_full_refund",
            )
        if delivered_late and delivery.all_late_handoff_seller_ids:
            parties = [ResponsibleParty(party_type="seller", party_id=seller) for seller in delivery.all_late_handoff_seller_ids[:3]]
            return self._decision(
                "late_delivery_seller", secondary, "SELLER_HANDOFF_AFTER_LIMIT", parties,
                order_product.freight_total_brl, "refund_freight",
            )
        if delivered_late:
            return self._decision(
                "late_delivery_logistics", secondary, "CARRIER_DELIVERED_AFTER_ESTIMATE",
                [ResponsibleParty(party_type="logistics_provider", party_id="LOGISTICS_PROVIDER")],
                order_product.freight_total_brl, "refund_freight",
            )
        if payment_count >= 2 and payment.reconciled:
            return self._decision(
                "valid_split_payment", secondary, "MULTIPLE_PAYMENTS_RECONCILED", [],
                Decimal("0.00"), "explain_valid_split_payment",
            )
        if delivery.delivery_variance_hours is not None and delivery.delivery_variance_hours <= 0 and payment.reconciled:
            return self._decision(
                "unsupported_late_claim", secondary, "DELIVERY_WITHIN_ESTIMATE", [],
                Decimal("0.00"), "reject_late_refund",
            )
        raise ValueError("EC_POLICY_V2 could not classify the order")

    @staticmethod
    def _secondary_issues(order_product: OrderProductHandoff, payment: PaymentHandoff, is_repeat_customer: bool) -> list[str]:
        issues: list[str] = []
        if order_product.item_count >= 2:
            issues.append("multi_item_order")
        if order_product.seller_count >= 2:
            issues.append("multi_seller_order")
        if payment.payment_count >= 2:
            issues.append("split_payment")
        if is_repeat_customer:
            issues.append("repeat_customer")
        if order_product.category_count >= 2:
            issues.append("multiple_categories")
        return issues

    @staticmethod
    def _decision(
        primary: str,
        secondary: list[str],
        root_cause: str,
        parties: list[ResponsibleParty],
        refund: Decimal,
        action: str,
    ) -> PolicyDecision:
        actions = [action]
        if primary == "late_delivery_seller":
            actions.append("review_seller_handoff")
        elif primary == "late_delivery_logistics":
            actions.append("review_carrier_delay")
        if primary in {"canceled_order_paid", "unavailable_order_paid"}:
            actions.append("verify_refund_completion")
        if "multi_seller_order" in secondary:
            actions.append("coordinate_multi_seller_case")
        if "split_payment" in secondary and primary != "valid_split_payment":
            actions.append("verify_payment_allocation")
        return PolicyDecision(
            primary_issue=primary,
            secondary_issues=secondary,
            root_cause_code=root_cause,
            responsible_parties=parties,
            case_status="action_required" if refund > 0 else "no_action",
            recommended_refund_brl=refund.quantize(Decimal("0.01")),
            resolution_actions=actions,
        )
