import json
from pathlib import Path

from dispute_agents.facts import order_product_handoff, payment_handoff
from dispute_agents.llm import FakeLLM
from dispute_agents.models import CaseInput
from dispute_agents.repository import OlistRepository
from dispute_agents.workflow import DisputeWorkflow


ROOT = Path(__file__).resolve().parents[1]


def load_case(case_id: str) -> CaseInput:
    return CaseInput.model_validate_json(
        (ROOT / "input" / f"{case_id}.json").read_text(encoding="utf-8")
    )


def test_product_categories_are_translated_with_the_supplied_lookup_table():
    repository = OlistRepository(ROOT / "data")

    handoff = order_product_handoff(load_case("EC_001"), repository)

    assert handoff.category_names == ["health_beauty"]


def test_unknown_product_category_keeps_its_source_value():
    repository = OlistRepository(ROOT / "data")

    assert repository.translated_category("category_without_translation") == "category_without_translation"


def test_payment_types_preserve_one_entry_per_source_payment_row():
    repository = OlistRepository(ROOT / "data")
    case = load_case("EC_010")
    order_product = order_product_handoff(case, repository)

    handoff = payment_handoff(case, repository, order_product)

    assert handoff.payment_types == ["credit_card", "credit_card"]


def test_confidence_is_calibrated_instead_of_claiming_absolute_certainty():
    output = DisputeWorkflow(
        repository=OlistRepository(ROOT / "data"),
        llm=FakeLLM(),
    ).run_case(load_case("EC_001"))

    assert output.case_assessment.confidence == 0.92


def test_freight_refund_actions_match_the_readme_reference_output():
    output = DisputeWorkflow(
        repository=OlistRepository(ROOT / "data"),
        llm=FakeLLM(),
    ).run_case(load_case("EC_002"))

    assert output.resolution_actions == [
        "refund_freight",
        "review_seller_handoff",
        "verify_payment_allocation",
    ]
