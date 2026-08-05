import pytest
from src.repository import DataRepository
from src.llm_client import GroqLLMClient
from src.agents.policy import PolicyAgent
from src.handoff import AgentHandoff, Fact


@pytest.fixture(scope="module")
def policy_agent():
    repo = DataRepository(data_dir="data")
    llm = GroqLLMClient()
    return PolicyAgent(repo, llm)


def test_canceled_order_paid(policy_agent):
    incoming = AgentHandoff(
        ticket_id="test_canceled",
        sender="DeliveryAgent",
        recipient="PolicyAgent",
        question="Apply policy",
        facts_found=[
            Fact(description="delivery", source_ids=[], value={"order_status": "canceled", "delivery_variance_hours": None}),
            Fact(description="payment", source_ids=[], value={"payment_total_brl": 100.0, "freight_total_brl": 10.0}),
        ],
    )
    res = policy_agent.process_handoff(incoming)
    policy_fact = res.facts_found[-1].value
    assert policy_fact["primary_issue"] == "canceled_order_paid"
    assert policy_fact["recommended_refund_brl"] == 100.0
    assert policy_fact["resolution_actions"][0] == "issue_full_refund"


def test_late_delivery_seller(policy_agent):
    incoming = AgentHandoff(
        ticket_id="test_late_seller",
        sender="DeliveryAgent",
        recipient="PolicyAgent",
        question="Apply policy",
        facts_found=[
            Fact(
                description="delivery",
                source_ids=[],
                value={"order_status": "delivered", "delivery_variance_hours": 15.0, "late_handoff_seller_ids": ["seller_1"]},
            ),
            Fact(description="payment", source_ids=[], value={"payment_total_brl": 100.0, "freight_total_brl": 15.0}),
        ],
    )
    res = policy_agent.process_handoff(incoming)
    policy_fact = res.facts_found[-1].value
    assert policy_fact["primary_issue"] == "late_delivery_seller"
    assert policy_fact["recommended_refund_brl"] == 15.0
    assert policy_fact["resolution_actions"][0] == "refund_freight"
    assert "review_seller_handoff" in policy_fact["resolution_actions"]
