import json
from pathlib import Path

from dispute_agents.config import MODEL_BY_AGENT
from dispute_agents.llm import FakeLLM
from dispute_agents.repository import OlistRepository
from dispute_agents.models import CaseInput
from dispute_agents.tracing import TraceLogger
from dispute_agents.workflow import DisputeWorkflow


ROOT = Path(__file__).resolve().parents[1]


def load_case(name: str) -> CaseInput:
    return CaseInput.model_validate(json.loads((ROOT / "input" / name).read_text(encoding="utf-8")))


def test_workflow_runs_all_agents_and_builds_seller_late_output():
    fake = FakeLLM()
    trace = TraceLogger()
    workflow = DisputeWorkflow(repository=OlistRepository(ROOT / "data"), llm=fake, trace=trace)

    output = workflow.run_case(load_case("EC_002.json"))

    assert output.case_assessment.primary_issue == "late_delivery_seller"
    assert output.financial_resolution.recommended_refund_brl > 0
    assert output.root_cause_analysis.ranked_causes[0].cause_code == "SELLER_HANDOFF_AFTER_LIMIT"
    assert output.evidence_ids[-1] == "policy:SELLER_HANDOFF_AFTER_LIMIT"
    assert len(fake.calls) == 8  # Coordinator is called before routing and after verification.
    assert fake.routes == [
        (MODEL_BY_AGENT[agent].provider, MODEL_BY_AGENT[agent].model)
        for agent in ["coordinator", "customer", "order_product", "payment", "delivery", "policy", "verifier", "coordinator"]
    ]
    assert {event["agent"] for event in trace.events} >= {
        "coordinator", "customer", "order_product", "payment", "delivery", "policy", "verifier"
    }


def test_workflow_preserves_no_item_null_reconciliation():
    workflow = DisputeWorkflow(repository=OlistRepository(ROOT / "data"), llm=FakeLLM())

    output = workflow.run_case(load_case("EC_012.json"))

    assert output.case_assessment.primary_issue == "unavailable_order_paid"
    assert output.affected_entities.item_ids == []
    assert output.payment_reconciliation.expected_total_brl is None
    assert output.payment_reconciliation.difference_brl is None
    assert output.payment_reconciliation.reconciled is None
