from src.agents.base import BaseAgent
from src.handoff import AgentHandoff, Fact


class CustomerAgent(BaseAgent):
    """Agent responsible for customer identity & purchase history investigation."""

    def __init__(self, repository, llm_client):
        super().__init__("CustomerAgent", repository, llm_client)

    def process_handoff(self, incoming: AgentHandoff) -> AgentHandoff:
        claimed_order_id = incoming.ticket_id  # order_id passed in
        order = self.repository.get_order(claimed_order_id)

        customer_unique_id = ""
        related_order_ids = []
        is_repeat_customer = False

        if order:
            customer_id = order.get("customer_id")
            if customer_id:
                cuid = self.repository.get_customer_unique_id(customer_id)
                if cuid:
                    customer_unique_id = cuid
                    related_order_ids = self.repository.get_related_order_ids(cuid, claimed_order_id)
                    # Check repeat customer: total orders under this customer_unique_id > 1
                    all_cids = self.repository.customer_ids_by_unique_id.get(cuid, [])
                    all_orders = []
                    for cid in all_cids:
                        for o in self.repository.orders_by_customer_id.get(cid, []):
                            all_orders.append(o["order_id"])
                    if len(set(all_orders)) > 1:
                        is_repeat_customer = True

        facts = [
            Fact(
                description="Customer identity retrieved",
                source_ids=[f"order:{claimed_order_id}"],
                value={
                    "customer_unique_id": customer_unique_id,
                    "related_order_ids": related_order_ids,
                    "is_repeat_customer": is_repeat_customer,
                },
            )
        ]

        # LLM narrative synthesis
        prompt = (
            f"Customer Analysis for order {claimed_order_id}: "
            f"customer_unique_id={customer_unique_id}, "
            f"related_orders_count={len(related_order_ids)}, "
            f"is_repeat={is_repeat_customer}."
        )
        llm_narrative = self.llm_client.generate(
            "You are a Customer Investigation Agent analyzing customer identity and order history.",
            prompt,
        )

        return AgentHandoff(
            ticket_id=incoming.ticket_id,
            sender=self.name,
            recipient="CoordinatorAgent",
            question="Customer investigation completed.",
            facts_found=facts,
            facts_missing=[],
            next_suggestion=f"Customer identity verified. LLM note: {llm_narrative[:100]}...",
        )
