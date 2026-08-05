from src.agents.base import BaseAgent
from src.handoff import AgentHandoff, Fact


class OrderProductAgent(BaseAgent):
    """Agent responsible for Order items, Sellers, Products, and Category investigation."""

    def __init__(self, repository, llm_client):
        super().__init__("OrderProductAgent", repository, llm_client)

    def process_handoff(self, incoming: AgentHandoff) -> AgentHandoff:
        claimed_order_id = incoming.ticket_id
        items = self.repository.get_items(claimed_order_id)

        has_items = len(items) > 0
        item_ids = []
        product_ids = []
        seller_ids = []
        categories = []
        item_evidence = []
        seller_evidence = []

        item_total_brl = None
        freight_total_brl = None
        expected_total_brl = None

        if has_items:
            item_sum = 0.0
            freight_sum = 0.0
            seen_products = set()
            seen_sellers = set()
            seen_categories = set()

            for it in items:
                order_item_id = it["order_item_id"]
                pid = it["product_id"]
                sid = it["seller_id"]
                price = float(it["price"])
                freight = float(it["freight_value"])

                item_sum += price
                freight_sum += freight

                item_formatted_id = f"{claimed_order_id}:{order_item_id}"
                if item_formatted_id not in item_ids:
                    item_ids.append(item_formatted_id)
                    item_evidence.append(f"item:{item_formatted_id}")

                if pid not in seen_products:
                    seen_products.add(pid)
                    product_ids.append(pid)

                if sid not in seen_sellers:
                    seen_sellers.add(sid)
                    seller_ids.append(sid)
                    seller_evidence.append(f"seller:{sid}")

                prod = self.repository.get_product(pid)
                if prod and prod.get("product_category_name"):
                    raw_cat = prod["product_category_name"]
                    trans_cat = self.repository.get_translated_category(raw_cat)
                    if trans_cat and trans_cat not in seen_categories:
                        seen_categories.add(trans_cat)
                        categories.append(trans_cat)

            item_total_brl = round(item_sum, 2)
            freight_total_brl = round(freight_sum, 2)
            expected_total_brl = round(item_sum + freight_sum, 2)

        multi_item = len(items) >= 2
        multi_seller = len(set(seller_ids)) >= 2
        multi_category = len(categories) >= 2

        facts = [
            Fact(
                description="Order items and product context analyzed",
                source_ids=item_evidence + seller_evidence,
                value={
                    "has_items": has_items,
                    "item_ids": item_ids,
                    "product_ids": product_ids,
                    "seller_ids": seller_ids,
                    "category_names": categories,
                    "item_total_brl": item_total_brl,
                    "freight_total_brl": freight_total_brl,
                    "expected_total_brl": expected_total_brl,
                    "multi_item_order": multi_item,
                    "multi_seller_order": multi_seller,
                    "multiple_categories": multi_category,
                    "raw_items": items,
                },
            )
        ]

        prompt = (
            f"Order {claimed_order_id} has {len(items)} items, "
            f"{len(seller_ids)} sellers, expected_total={expected_total_brl} BRL."
        )
        llm_narrative = self.llm_client.generate(
            "You are an Order and Product Investigation Agent.",
            prompt,
        )

        return AgentHandoff(
            ticket_id=incoming.ticket_id,
            sender=self.name,
            recipient="PaymentAgent",
            question="Analyze payment reconciliation with expected total.",
            facts_found=incoming.facts_found + facts,
            facts_missing=[],
            next_suggestion=f"Order composition analyzed. LLM note: {llm_narrative[:100]}...",
        )
