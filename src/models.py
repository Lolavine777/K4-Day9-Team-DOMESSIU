from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


def round_or_none(val: Optional[float], decimals: int = 2) -> Optional[float]:
    if val is None:
        return None
    return round(float(val), decimals)


@dataclass
class CaseAssessment:
    primary_issue: str
    secondary_issues: List[str]
    case_status: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_issue": self.primary_issue,
            "secondary_issues": self.secondary_issues,
            "case_status": self.case_status,
            "confidence": round_or_none(self.confidence, 2),
        }


@dataclass
class AffectedEntities:
    order_ids: List[str]
    item_ids: List[str]
    seller_ids: List[str]
    payment_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_ids": self.order_ids[:5],
            "item_ids": self.item_ids[:5],
            "seller_ids": self.seller_ids[:3],
            "payment_ids": self.payment_ids[:5],
        }


@dataclass
class CustomerContext:
    customer_unique_id: str
    related_order_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "customer_unique_id": self.customer_unique_id or "",
            "related_order_ids": self.related_order_ids[:5],
        }


@dataclass
class ProductContext:
    product_ids: List[str]
    category_names: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_ids": self.product_ids[:5],
            "category_names": self.category_names[:5],
        }


@dataclass
class SellerHandoffAnalysis:
    seller_id: str
    shipping_limit_at: str
    handoff_variance_hours: Optional[float]
    late_handoff: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seller_id": self.seller_id,
            "shipping_limit_at": self.shipping_limit_at,
            "handoff_variance_hours": round_or_none(self.handoff_variance_hours, 2),
            "late_handoff": self.late_handoff,
        }


@dataclass
class DeliveryAnalysis:
    delivered_at: Optional[str]
    estimated_delivery_at: Optional[str]
    carrier_handoff_at: Optional[str]
    delivery_variance_hours: Optional[float]
    seller_handoff_analysis: List[SellerHandoffAnalysis]
    late_handoff_seller_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "delivered_at": self.delivered_at,
            "estimated_delivery_at": self.estimated_delivery_at,
            "carrier_handoff_at": self.carrier_handoff_at,
            "delivery_variance_hours": round_or_none(self.delivery_variance_hours, 2),
            "seller_handoff_analysis": [
                sh.to_dict() if hasattr(sh, "to_dict") else sh for sh in self.seller_handoff_analysis
            ],
            "late_handoff_seller_ids": self.late_handoff_seller_ids,
        }


@dataclass
class PaymentReconciliation:
    currency: str = "BRL"
    item_total_brl: Optional[float] = None
    freight_total_brl: Optional[float] = None
    expected_total_brl: Optional[float] = None
    payment_total_brl: float = 0.0
    difference_brl: Optional[float] = None
    reconciled: Optional[bool] = None
    payment_types: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "item_total_brl": round_or_none(self.item_total_brl, 2),
            "freight_total_brl": round_or_none(self.freight_total_brl, 2),
            "expected_total_brl": round_or_none(self.expected_total_brl, 2),
            "payment_total_brl": round_or_none(self.payment_total_brl, 2),
            "difference_brl": round_or_none(self.difference_brl, 2),
            "reconciled": self.reconciled,
            "payment_types": self.payment_types,
        }


@dataclass
class RankedCause:
    cause_code: str
    rank: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cause_code": self.cause_code,
            "rank": self.rank,
        }


@dataclass
class ResponsibleParty:
    party_type: str
    party_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "party_type": self.party_type,
            "party_id": self.party_id,
        }


@dataclass
class RootCauseAnalysis:
    ranked_causes: List[RankedCause]
    responsible_parties: List[ResponsibleParty]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ranked_causes": [rc.to_dict() for rc in self.ranked_causes[:3]],
            "responsible_parties": [rp.to_dict() for rp in self.responsible_parties[:3]],
        }


@dataclass
class FinancialResolution:
    currency: str = "BRL"
    recommended_refund_brl: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "recommended_refund_brl": round_or_none(self.recommended_refund_brl, 2),
        }


@dataclass
class CaseOutput:
    case_id: str
    case_assessment: CaseAssessment
    affected_entities: AffectedEntities
    customer_context: CustomerContext
    product_context: ProductContext
    delivery_analysis: DeliveryAnalysis
    payment_reconciliation: PaymentReconciliation
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: List[str]
    financial_resolution: FinancialResolution
    resolution_actions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_assessment": self.case_assessment.to_dict(),
            "affected_entities": self.affected_entities.to_dict(),
            "customer_context": self.customer_context.to_dict(),
            "product_context": self.product_context.to_dict(),
            "delivery_analysis": self.delivery_analysis.to_dict(),
            "payment_reconciliation": self.payment_reconciliation.to_dict(),
            "root_cause_analysis": self.root_cause_analysis.to_dict(),
            "evidence_ids": self.evidence_ids[:20],
            "financial_resolution": self.financial_resolution.to_dict(),
            "resolution_actions": self.resolution_actions[:5],
        }
