from __future__ import annotations

from decimal import Decimal
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


PrimaryIssue: TypeAlias = Literal[
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
]
SecondaryIssue: TypeAlias = Literal[
    "multi_item_order",
    "multi_seller_order",
    "split_payment",
    "repeat_customer",
    "multiple_categories",
]
RootCauseCode: TypeAlias = Literal[
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
]
ResolutionAction: TypeAlias = Literal[
    "issue_full_refund",
    "refund_freight",
    "explain_valid_split_payment",
    "reject_late_refund",
    "review_seller_handoff",
    "review_carrier_delay",
    "verify_refund_completion",
    "coordinate_multi_seller_case",
    "verify_payment_allocation",
]


class CustomerRequest(StrictModel):
    language: str
    message: str
    claimed_order_id: str


class InvestigationScope(StrictModel):
    include_customer_history: bool
    include_product_context: bool


class CaseInput(StrictModel):
    case_id: str = Field(pattern=r"^EC_[0-9]{3}$")
    customer_request: CustomerRequest
    investigation_scope: InvestigationScope
    policy_version: Literal["EC_POLICY_V2"]


class CustomerHandoff(StrictModel):
    customer_unique_id: str
    related_order_ids: list[str] = Field(max_length=5)


class OrderProductHandoff(StrictModel):
    order_id: str
    order_status: str
    item_ids: list[str] = Field(max_length=5)
    seller_ids: list[str] = Field(max_length=3)
    product_ids: list[str] = Field(max_length=5)
    category_names: list[str] = Field(max_length=5)
    item_total_brl: Decimal
    freight_total_brl: Decimal
    seller_shipping_limits: dict[str, str]
    item_count: int = Field(ge=0)
    seller_count: int = Field(ge=0)
    category_count: int = Field(ge=0)


class PaymentHandoff(StrictModel):
    payment_ids: list[str] = Field(max_length=5)
    payment_types: list[str]
    payment_total_brl: Decimal
    expected_total_brl: Decimal | None
    difference_brl: Decimal | None
    reconciled: bool | None
    payment_count: int = Field(ge=0)


class SellerHandoffAnalysis(StrictModel):
    seller_id: str
    shipping_limit_at: str | None
    handoff_variance_hours: Decimal | None
    late_handoff: bool


class DeliveryHandoff(StrictModel):
    delivered_at: str | None
    estimated_delivery_at: str | None
    carrier_handoff_at: str | None
    delivery_variance_hours: Decimal | None
    seller_handoff_analysis: list[SellerHandoffAnalysis] = Field(max_length=3)
    late_handoff_seller_ids: list[str] = Field(max_length=3)
    all_late_handoff_seller_ids: list[str]

    @classmethod
    def empty(cls) -> "DeliveryHandoff":
        return cls(
            delivered_at=None,
            estimated_delivery_at=None,
            carrier_handoff_at=None,
            delivery_variance_hours=None,
            seller_handoff_analysis=[],
            late_handoff_seller_ids=[],
            all_late_handoff_seller_ids=[],
        )


class CoordinatorResult(StrictModel):
    case_id: str
    status: Literal["ready", "complete"]


class AgentAssessment(StrictModel):
    consistent: bool
    summary: str


class VerifierReview(StrictModel):
    approved: bool
    corrections: list[str] = Field(default_factory=list)


class ResponsibleParty(StrictModel):
    party_type: Literal["seller", "platform", "logistics_provider"]
    party_id: str


class RankedCause(StrictModel):
    cause_code: RootCauseCode
    rank: int = Field(ge=1, le=3)


class PolicyDecision(StrictModel):
    primary_issue: PrimaryIssue
    secondary_issues: list[SecondaryIssue] = Field(max_length=5)
    root_cause_code: RootCauseCode
    responsible_parties: list[ResponsibleParty] = Field(max_length=3)
    case_status: Literal["action_required", "no_action"]
    recommended_refund_brl: Decimal = Field(ge=0)
    resolution_actions: list[ResolutionAction] = Field(min_length=1, max_length=5)


class CaseAssessment(StrictModel):
    primary_issue: PrimaryIssue
    secondary_issues: list[SecondaryIssue] = Field(max_length=5)
    case_status: Literal["action_required", "no_action"]
    confidence: float = Field(ge=0, le=1)


class AffectedEntities(StrictModel):
    order_ids: list[str] = Field(min_length=1, max_length=5)
    item_ids: list[str] = Field(max_length=5)
    seller_ids: list[str] = Field(max_length=3)
    payment_ids: list[str] = Field(max_length=5)


class CustomerContext(StrictModel):
    customer_unique_id: str
    related_order_ids: list[str] = Field(max_length=5)


class ProductContext(StrictModel):
    product_ids: list[str] = Field(max_length=5)
    category_names: list[str] = Field(max_length=5)


class DeliveryAnalysis(StrictModel):
    delivered_at: str | None
    estimated_delivery_at: str | None
    carrier_handoff_at: str | None
    delivery_variance_hours: Decimal | None
    seller_handoff_analysis: list[SellerHandoffAnalysis] = Field(max_length=3)
    late_handoff_seller_ids: list[str] = Field(max_length=3)


class PaymentReconciliation(StrictModel):
    currency: Literal["BRL"] = "BRL"
    item_total_brl: Decimal
    freight_total_brl: Decimal
    expected_total_brl: Decimal | None
    payment_total_brl: Decimal
    difference_brl: Decimal | None
    reconciled: bool | None
    payment_types: list[str]


class RootCauseAnalysis(StrictModel):
    ranked_causes: list[RankedCause] = Field(min_length=1, max_length=3)
    responsible_parties: list[ResponsibleParty] = Field(max_length=3)


class FinancialResolution(StrictModel):
    currency: Literal["BRL"] = "BRL"
    recommended_refund_brl: Decimal = Field(ge=0)


class CaseOutput(StrictModel):
    case_id: str
    case_assessment: CaseAssessment
    affected_entities: AffectedEntities
    customer_context: CustomerContext
    product_context: ProductContext
    delivery_analysis: DeliveryAnalysis
    payment_reconciliation: PaymentReconciliation
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    financial_resolution: FinancialResolution
    resolution_actions: list[ResolutionAction] = Field(min_length=1, max_length=5)
