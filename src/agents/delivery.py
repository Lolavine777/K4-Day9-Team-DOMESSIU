from datetime import datetime
from typing import Optional, List, Dict, Any
from src.agents.base import BaseAgent
from src.handoff import AgentHandoff, Fact
from src.models import SellerHandoffAnalysis


def parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def calculate_variance_hours(dt1: Optional[datetime], dt2: Optional[datetime]) -> Optional[float]:
    """Calculate dt1 - dt2 in hours. Returns None if either is None."""
    if dt1 is None or dt2 is None:
        return None
    seconds = (dt1 - dt2).total_seconds()
    return round(seconds / 3600.0, 2)


class DeliveryAgent(BaseAgent):
    """Agent responsible for delivery timeline variance and seller handoff analysis."""

    def __init__(self, repository, llm_client):
        super().__init__("DeliveryAgent", repository, llm_client)

    def process_handoff(self, incoming: AgentHandoff) -> AgentHandoff:
        claimed_order_id = incoming.ticket_id
        order = self.repository.get_order(claimed_order_id) or {}
        items = self.repository.get_items(claimed_order_id)

        delivered_at_str = order.get("order_delivered_customer_date") or None
        estimated_at_str = order.get("order_estimated_delivery_date") or None
        carrier_at_str = order.get("order_delivered_carrier_date") or None

        delivered_dt = parse_datetime(delivered_at_str)
        estimated_dt = parse_datetime(estimated_at_str)
        carrier_dt = parse_datetime(carrier_at_str)

        delivery_variance_hours = calculate_variance_hours(delivered_dt, estimated_dt)

        # Seller handoff analysis
        # Per seller, find earliest shipping_limit_date
        seller_limits: Dict[str, str] = {}
        seller_limit_dts: Dict[str, datetime] = {}

        for item in items:
            sid = item["seller_id"]
            limit_str = item["shipping_limit_date"]
            limit_dt = parse_datetime(limit_str)
            if limit_dt:
                if sid not in seller_limit_dts or limit_dt < seller_limit_dts[sid]:
                    seller_limit_dts[sid] = limit_dt
                    seller_limits[sid] = limit_str

        seller_handoff_analysis: List[SellerHandoffAnalysis] = []
        late_handoff_seller_ids: List[str] = []

        for sid, limit_str in seller_limits.items():
            limit_dt = seller_limit_dts[sid]
            variance = calculate_variance_hours(carrier_dt, limit_dt)
            is_late = (variance is not None) and (variance > 0)
            if is_late:
                late_handoff_seller_ids.append(sid)

            seller_handoff_analysis.append(
                SellerHandoffAnalysis(
                    seller_id=sid,
                    shipping_limit_at=limit_str,
                    handoff_variance_hours=variance,
                    late_handoff=is_late,
                )
            )

        facts = [
            Fact(
                description="Delivery analysis completed",
                source_ids=[f"order:{claimed_order_id}"],
                value={
                    "delivered_at": delivered_at_str,
                    "estimated_delivery_at": estimated_at_str,
                    "carrier_handoff_at": carrier_at_str,
                    "delivery_variance_hours": delivery_variance_hours,
                    "seller_handoff_analysis": [sh.to_dict() for sh in seller_handoff_analysis],
                    "late_handoff_seller_ids": late_handoff_seller_ids,
                    "order_status": order.get("order_status"),
                },
            )
        ]

        prompt = (
            f"Delivery analysis for {claimed_order_id}: status={order.get('order_status')}, "
            f"delivery_variance={delivery_variance_hours} hours, "
            f"late_sellers={late_handoff_seller_ids}."
        )
        llm_narrative = self.llm_client.generate(
            "You are a Delivery Investigation Agent.",
            prompt,
        )

        return AgentHandoff(
            ticket_id=incoming.ticket_id,
            sender=self.name,
            recipient="PolicyAgent",
            question="Apply EC_POLICY_V2 policy rules and determine resolution.",
            facts_found=incoming.facts_found + facts,
            facts_missing=[],
            next_suggestion=f"Delivery analyzed. LLM note: {llm_narrative[:100]}...",
        )
