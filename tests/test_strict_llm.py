import json
from pathlib import Path

import pytest

from dispute_agents.config import MODEL_BY_AGENT, PROVIDER_BY_NAME
from dispute_agents.models import CaseInput
from dispute_agents.llm import MultiProviderLLM, build_user_content, max_tokens_for_model
from dispute_agents.repository import OlistRepository
from dispute_agents.workflow import DisputeWorkflow


ROOT = Path(__file__).resolve().parents[1]


class EmptyLLM:
    def complete(self, *, provider: str, model: str, system: str, payload: dict) -> str:
        return ""


def test_workflow_rejects_empty_model_reply_in_strict_mode():
    case = CaseInput.model_validate(json.loads((ROOT / "input" / "EC_001.json").read_text(encoding="utf-8")))
    workflow = DisputeWorkflow(repository=OlistRepository(ROOT / "data"), llm=EmptyLLM())

    with pytest.raises(RuntimeError, match="coordinator model failed after 2 attempts"):
        workflow.run_case(case)


def test_model_configuration_uses_three_free_models_within_lab_limit():
    assert set(config.provider for config in MODEL_BY_AGENT.values()) == {"ollama", "openrouter", "nvidia"}
    assert all(config.parameters_billion <= 10 for config in MODEL_BY_AGENT.values())
    assert PROVIDER_BY_NAME["ollama"].credential_env is None
    assert PROVIDER_BY_NAME["openrouter"].credential_env == "OPENROUTER_API_KEY"
    assert PROVIDER_BY_NAME["nvidia"].credential_env == "NVIDIA_API_KEY"


def test_provider_client_uses_its_own_base_url_and_credential(monkeypatch):
    created: list[tuple[str, str]] = []

    class RecordingClient:
        def __init__(self, *, base_url: str, api_key: str, timeout: float):
            created.append((base_url, api_key, timeout))

    llm = MultiProviderLLM(
        secrets={"OPENROUTER_API_KEY": "openrouter-token", "NVIDIA_API_KEY": "nvidia-token"},
        client_factory=RecordingClient,
    )

    assert llm.client_for("ollama") is llm.client_for("ollama")
    assert llm.client_for("openrouter") is llm.client_for("openrouter")
    assert llm.client_for("nvidia") is llm.client_for("nvidia")
    assert created == [
        ("http://localhost:11434/v1/", "ollama", 60.0),
        ("https://openrouter.ai/api/v1/", "openrouter-token", 60.0),
        ("https://integrate.api.nvidia.com/v1/", "nvidia-token", 60.0),
    ]


def test_model_payload_is_plain_json_and_models_get_enough_output_tokens():
    assert build_user_content("qwen3:8b", {"candidate": {}}) == '{"candidate": {}}'
    assert max_tokens_for_model("qwen3:8b") == 500
