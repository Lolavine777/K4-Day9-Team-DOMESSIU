from src.agents.base import BaseAgent
from src.handoff import AgentHandoff, Fact


class PaymentAgent(BaseAgent):
    """Agent responsible for payment rows analysis and financial reconciliation."""

    def __init__(self, repository, llm_client):
        super().__init__("PaymentAgent", repository, llm_client)

    def process_handoff(self, incoming: AgentHandoff) -> AgentHandoff:
        claimed_order_id = incoming.ticket_id
        payments = self.repository.get_payments(claimed_order_id)

        # Extract expected_total_brl and item_total / freight_total from incoming facts
        expected_total_brl = None
        item_total_brl = None
        freight_total_brl = None
        for fact in incoming.facts_found:
            if isinstance(fact.value, dict) and "expected_total_brl" in fact.value:
                expected_total_brl = fact.value.get("expected_total_brl")
                item_total_brl = fact.value.get("item_total_brl")
                freight_total_brl = fact.value.get("freight_total_brl")
                break

        payment_ids = []
        payment_evidence = []
        payment_types = []
        seen_types = set()
        payment_sum = 0.0

        for p in payments:
            seq = p["payment_sequential"]
            ptype = p["payment_type"]
            pval = float(p["payment_value"])
            payment_sum += pval

            pid_str = f"{claimed_order_id}:{seq}"
            payment_ids.append(pid_str)
            payment_evidence.append(f"payment:{pid_str}")

            if ptype not in seen_types:
                seen_types.add(ptype)
                payment_types.append(ptype)

        payment_total_brl = round(payment_sum, 2)

        if expected_total_brl is not None:
            difference_brl = round(payment_total_brl - expected_total_brl, 2)
            reconciled = abs(difference_brl) <= 0.10
        else:
            difference_brl = None
            reconciled = None

        split_payment = len(payments) >= 2

        facts = [
            Fact(
                description="Payment reconciliation completed",
                source_ids=payment_evidence,
                value={
                    "payment_ids": payment_ids,
                    "payment_types": payment_types,
                    "payment_total_brl": payment_total_brl,
                    "item_total_brl": item_total_brl,
                    "freight_total_brl": freight_total_brl,
                    "expected_total_brl": expected_total_brl,
                    "difference_brl": difference_brl,
                    "reconciled": reconciled,
                    "split_payment": split_payment,
                    "payment_rows_count": len(payments),
                },
            )
        ]

        prompt = (
            f"Payment reconciliation for {claimed_order_id}: "
            f"payment_total={payment_total_brl}, expected={expected_total_brl}, "
            f"difference={difference_brl}, reconciled={reconciled}."
        )
        llm_narrative = self.llm_client.generate(
            "You are a Payment Reconciliation Agent.",
            prompt,
        )

        return AgentHandoff(
            ticket_id=incoming.ticket_id,
            sender=self.name,
            recipient="DeliveryAgent",
            question="Analyze delivery timeline and seller handoffs.",
            facts_found=incoming.facts_found + facts,
            facts_missing=[],
            next_suggestion=f"Payment reconciled. LLM note: {llm_narrative[:100]}...",
        )
