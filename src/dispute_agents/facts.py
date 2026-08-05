from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from .models import (
    CaseInput,
    CustomerHandoff,
    DeliveryHandoff,
    OrderProductHandoff,
    PaymentHandoff,
    SellerHandoffAnalysis,
)
from .repository import OlistRepository

TWO_DECIMALS = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)


def parse_brl_decimal(value: str) -> Decimal:
    return Decimal(value or "0")


def stable_unique(values: list[str], limit: int | None = None) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
            if limit is not None and len(result) >= limit:
                break
    return result


def parse_timestamp(value: str) -> datetime | None:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S") if value else None


def hours_between(later: str | None, earlier: str | None) -> Decimal | None:
    if not later or not earlier:
        return None
    seconds = Decimal(str((parse_timestamp(later) - parse_timestamp(earlier)).total_seconds()))
    return (seconds / Decimal("3600")).quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)


def customer_handoff(case: CaseInput, repo: OlistRepository) -> CustomerHandoff:
    order = repo.order(case.customer_request.claimed_order_id)
    customer = repo.customer_for_order(order)
    related = repo.related_orders(customer["customer_unique_id"], case.customer_request.claimed_order_id)
    return CustomerHandoff(customer_unique_id=customer["customer_unique_id"], related_order_ids=related[:5])


def order_product_handoff(case: CaseInput, repo: OlistRepository) -> OrderProductHandoff:
    order_id = case.customer_request.claimed_order_id
    order = repo.order(order_id)
    items = repo.order_items(order_id)
    item_total = money(sum((parse_brl_decimal(row["price"]) for row in items), Decimal("0")))
    freight_total = money(sum((parse_brl_decimal(row["freight_value"]) for row in items), Decimal("0")))
    all_product_ids = stable_unique([row["product_id"] for row in items])
    all_categories = stable_unique(
        [product["product_category_name"] for product_id in all_product_ids if (product := repo.product(product_id))]
    )
    all_seller_ids = stable_unique([row["seller_id"] for row in items])
    product_ids = all_product_ids[:5]
    categories = all_categories[:5]
    seller_ids = all_seller_ids[:3]
    seller_limits: dict[str, str] = {}
    for seller_id in all_seller_ids:
        limits = [row["shipping_limit_date"] for row in items if row["seller_id"] == seller_id and row["shipping_limit_date"]]
        if limits:
            seller_limits[seller_id] = min(limits)
    return OrderProductHandoff(
        order_id=order_id,
        order_status=order["order_status"],
        item_ids=[f"{order_id}:{row['order_item_id']}" for row in items[:5]],
        seller_ids=seller_ids,
        product_ids=product_ids,
        category_names=categories,
        item_total_brl=item_total,
        freight_total_brl=freight_total,
        seller_shipping_limits=seller_limits,
        item_count=len(items),
        seller_count=len(all_seller_ids),
        category_count=len(all_categories),
    )


def payment_handoff(case: CaseInput, repo: OlistRepository, order_product: OrderProductHandoff) -> PaymentHandoff:
    order_id = case.customer_request.claimed_order_id
    payments = repo.order_payments(order_id)
    payment_total = money(sum((parse_brl_decimal(row["payment_value"]) for row in payments), Decimal("0")))
    expected = None
    difference = None
    reconciled = None
    if repo.order_items(order_id):
        expected = money(order_product.item_total_brl + order_product.freight_total_brl)
        difference = money(payment_total - expected)
        reconciled = abs(difference) <= Decimal("0.10")
    return PaymentHandoff(
        payment_ids=[f"{order_id}:{row['payment_sequential']}" for row in payments[:5]],
        payment_types=stable_unique([row["payment_type"] for row in payments]),
        payment_total_brl=payment_total,
        expected_total_brl=expected,
        difference_brl=difference,
        reconciled=reconciled,
        payment_count=len(payments),
    )


def delivery_handoff(case: CaseInput, repo: OlistRepository, order_product: OrderProductHandoff) -> DeliveryHandoff:
    order = repo.order(case.customer_request.claimed_order_id)
    carrier = order["order_delivered_carrier_date"] or None
    analysis: list[SellerHandoffAnalysis] = []
    late_sellers: list[str] = []
    for seller_id, limit in order_product.seller_shipping_limits.items():
        variance = hours_between(carrier, limit)
        late = variance is not None and variance > Decimal("0")
        if len(analysis) < 3:
            analysis.append(SellerHandoffAnalysis(
                seller_id=seller_id,
                shipping_limit_at=limit,
                handoff_variance_hours=variance,
                late_handoff=late,
            ))
        if late:
            late_sellers.append(seller_id)
    return DeliveryHandoff(
        delivered_at=order["order_delivered_customer_date"] or None,
        estimated_delivery_at=order["order_estimated_delivery_date"] or None,
        carrier_handoff_at=carrier,
        delivery_variance_hours=hours_between(
            order["order_delivered_customer_date"] or None,
            order["order_estimated_delivery_date"] or None,
        ),
        seller_handoff_analysis=analysis,
        late_handoff_seller_ids=late_sellers[:3],
        all_late_handoff_seller_ids=late_sellers,
    )
