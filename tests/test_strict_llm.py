import json
from pathlib import Path

import pytest

from dispute_agents.models import CaseInput
from dispute_agents.llm import build_user_content, max_tokens_for_model
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


def test_qwen3_prompt_disables_thinking_so_json_reaches_content():
    assert build_user_content("Qwen/Qwen3-8B:nscale", {"candidate": {}}).endswith("/no_think")
    assert not build_user_content("Qwen/Qwen2.5-7B-Instruct:together", {"candidate": {}}).endswith("/no_think")


def test_deepseek_gets_room_for_reasoning_and_final_json():
    assert max_tokens_for_model("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B:nscale") == 1000
    assert max_tokens_for_model("Qwen/Qwen3-8B:nscale") == 250
