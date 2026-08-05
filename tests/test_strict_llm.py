import json
from pathlib import Path

import pytest

from dispute_agents.models import CaseInput
from dispute_agents.repository import OlistRepository
from dispute_agents.workflow import DisputeWorkflow


ROOT = Path(__file__).resolve().parents[1]


class EmptyLLM:
    def complete(self, *, model: str, system: str, payload: dict) -> str:
        return ""


def test_workflow_rejects_empty_model_reply_in_strict_mode():
    case = CaseInput.model_validate(json.loads((ROOT / "input" / "EC_001.json").read_text(encoding="utf-8")))
    workflow = DisputeWorkflow(repository=OlistRepository(ROOT / "data"), llm=EmptyLLM())

    with pytest.raises(RuntimeError, match="coordinator model failed after 2 attempts"):
        workflow.run_case(case)
