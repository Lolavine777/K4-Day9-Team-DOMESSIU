from typing import Tuple, Dict, Any, List
from src.agents.base import BaseAgent
from src.agents.customer import CustomerAgent
from src.agents.order_product import OrderProductAgent
from src.agents.payment import PaymentAgent
from src.agents.delivery import DeliveryAgent
from src.agents.policy import PolicyAgent
from src.agents.verifier import VerifierAgent
from src.handoff import AgentHandoff, Fact


class CoordinatorAgent(BaseAgent):
    """Coordinator Agent managing workflow dispatch, handoffs, and final synthesis."""

    def __init__(self, repository, llm_client):
        super().__init__("CoordinatorAgent", repository, llm_client)
        self.customer_agent = CustomerAgent(repository, llm_client)
        self.order_product_agent = OrderProductAgent(repository, llm_client)
        self.payment_agent = PaymentAgent(repository, llm_client)
        self.delivery_agent = DeliveryAgent(repository, llm_client)
        self.policy_agent = PolicyAgent(repository, llm_client)
        self.verifier_agent = VerifierAgent(repository, llm_client)

    def process_case(self, case_input: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        case_id = case_input.get("case_id", "")
        claimed_order_id = case_input["customer_request"]["claimed_order_id"]

        trace_entries: List[Dict[str, Any]] = []

        # Initial handoff from Coordinator to CustomerAgent
        initial_handoff = AgentHandoff(
            ticket_id=claimed_order_id,
            sender=self.name,
            recipient="CustomerAgent",
            question=f"Investigate ticket {case_id} for order {claimed_order_id}",
            facts_found=[],
            facts_missing=[],
            next_suggestion="Start customer identity lookup",
        )
        trace_entries.append(initial_handoff.to_dict())

        # Step 1: CustomerAgent
        h1 = self.customer_agent.process_handoff(initial_handoff)
        trace_entries.append(h1.to_dict())

        # Step 2: OrderProductAgent
        h1.recipient = "OrderProductAgent"
        h2 = self.order_product_agent.process_handoff(h1)
        trace_entries.append(h2.to_dict())

        # Step 3: PaymentAgent
        h2.recipient = "PaymentAgent"
        h3 = self.payment_agent.process_handoff(h2)
        trace_entries.append(h3.to_dict())

        # Step 4: DeliveryAgent
        h3.recipient = "DeliveryAgent"
        h4 = self.delivery_agent.process_handoff(h3)
        trace_entries.append(h4.to_dict())

        # Step 5: PolicyAgent
        h4.recipient = "PolicyAgent"
        h5 = self.policy_agent.process_handoff(h4)
        trace_entries.append(h5.to_dict())

        # Step 6: VerifierAgent
        h5.recipient = "VerifierAgent"
        h6 = self.verifier_agent.process_handoff(h5)
        trace_entries.append(h6.to_dict())

        # Extract final output JSON from VerifierAgent's last fact
        final_output = {}
        for fact in h6.facts_found:
            if fact.description == "Output verification and evidence grounding verified":
                final_output = fact.value
                break

        # Ensure case_id matches input case_id (e.g. "EC_001")
        if isinstance(final_output, dict):
            final_output["case_id"] = case_id

        return final_output, trace_entries

    def process_handoff(self, handoff: AgentHandoff) -> AgentHandoff:
        # Not directly used as coordinator entrypoint is process_case
        return handoff
