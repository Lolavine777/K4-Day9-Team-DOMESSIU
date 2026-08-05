import json
from collections import Counter
from pathlib import Path

from dispute_agents.llm import FakeLLM
from dispute_agents.models import CaseInput
from dispute_agents.repository import OlistRepository
from dispute_agents.validation import validate_case_payload
from dispute_agents.workflow import DisputeWorkflow


ROOT = Path(__file__).resolve().parents[1]


def test_all_lab_cases_match_expected_policy_distribution_with_mocked_models():
    cases = [
        CaseInput.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((ROOT / "input").glob("EC_*.json"))
    ]
    workflow = DisputeWorkflow(repository=OlistRepository(ROOT / "data"), llm=FakeLLM())

    outputs = [workflow.run_case(case) for case in cases]

    assert len(outputs) == 50
    assert Counter(output.case_assessment.primary_issue for output in outputs) == {
        "late_delivery_seller": 10,
        "late_delivery_logistics": 10,
        "unsupported_late_claim": 8,
        "canceled_order_paid": 8,
        "valid_split_payment": 8,
        "unavailable_order_paid": 6,
    }
    for output in outputs:
        validate_case_payload(output.model_dump(mode="python"))
