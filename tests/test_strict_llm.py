import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dispute_agents.config import MODEL_BY_AGENT, PROVIDER_BY_NAME, configured_model_configs, model_for_agent
from dispute_agents.models import CaseInput
from dispute_agents.llm import AgentInvoker, MultiProviderLLM, build_user_content, max_tokens_for_model
from dispute_agents.models import AgentAssessment
from dispute_agents.repository import OlistRepository
from dispute_agents.workflow import DisputeWorkflow
from dispute_agents.tracing import TraceLogger


ROOT = Path(__file__).resolve().parents[1]


class EmptyLLM:
    def complete(self, *, provider: str, model: str, system: str, payload: dict) -> str:
        return ""


def test_workflow_rejects_empty_model_reply_in_strict_mode():
    case = CaseInput.model_validate(json.loads((ROOT / "input" / "EC_001.json").read_text(encoding="utf-8")))
    workflow = DisputeWorkflow(repository=OlistRepository(ROOT / "data"), llm=EmptyLLM())

    with pytest.raises(RuntimeError, match="coordinator model failed after 2 attempts"):
        workflow.run_case(case)


def test_model_configuration_uses_only_two_free_cloud_providers_within_lab_limit():
    assert set(config.provider for config in configured_model_configs()) == {"openrouter", "nvidia"}
    assert all(config.parameters_billion <= 10 for config in configured_model_configs())
    assert "ollama" not in PROVIDER_BY_NAME
    assert PROVIDER_BY_NAME["openrouter"].credential_env == "OPENROUTER_API_KEY"
    assert PROVIDER_BY_NAME["nvidia"].credential_env == "NVIDIA_API_KEY"


def test_openrouter_is_scoped_to_one_canary_case_to_fit_the_free_request_budget():
    assert model_for_agent("customer", "EC_001").provider == "openrouter"
    assert model_for_agent("customer", "EC_002").provider == "nvidia"


def test_provider_client_uses_its_own_base_url_and_credential(monkeypatch):
    created: list[tuple[str, str]] = []

    class RecordingClient:
        def __init__(self, *, base_url: str, api_key: str, timeout: float):
            created.append((base_url, api_key, timeout))

    llm = MultiProviderLLM(
        secrets={"OPENROUTER_API_KEY": "openrouter-token", "NVIDIA_API_KEY": "nvidia-token"},
        client_factory=RecordingClient,
    )

    assert llm.client_for("openrouter") is llm.client_for("openrouter")
    assert llm.client_for("nvidia") is llm.client_for("nvidia")
    assert created == [
        ("https://openrouter.ai/api/v1/", "openrouter-token", 60.0),
        ("https://integrate.api.nvidia.com/v1/", "nvidia-token", 60.0),
    ]


def test_model_payload_is_plain_json_and_models_get_enough_output_tokens():
    assert build_user_content("meta/llama-3.1-8b-instruct", {"candidate": {}}) == '{"candidate": {}}'
    assert max_tokens_for_model("meta/llama-3.1-8b-instruct") == 500


def test_openrouter_excludes_reasoning_so_final_json_reaches_content():
    request: dict = {}

    class CompletionEndpoint:
        def create(self, **kwargs):
            request.update(kwargs)
            message = SimpleNamespace(content='{"status":"ok"}')
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class RecordingClient:
        def __init__(self, **_):
            self.chat = SimpleNamespace(completions=CompletionEndpoint())

    llm = MultiProviderLLM(
        secrets={"OPENROUTER_API_KEY": "openrouter-token"},
        client_factory=RecordingClient,
    )

    assert llm.complete(provider="openrouter", model="free-model", system="JSON only", payload={}) == '{"status":"ok"}'
    assert request["extra_body"] == {"reasoning": {"effort": "low", "exclude": True}}


def test_rate_limit_waits_before_retrying():
    sleeps: list[float] = []

    class TooManyRequests(Exception):
        status_code = 429

    class RateLimitedOnce:
        calls = 0

        def complete(self, **_):
            self.calls += 1
            if self.calls == 1:
                raise TooManyRequests("rate limited")
            return '{"consistent":true,"summary":"ok"}'

    result = AgentInvoker(
        RateLimitedOnce(),
        TraceLogger(),
        retries=2,
        sleeper=sleeps.append,
    ).call(
        agent="customer",
        case_id="EC_002",
        payload={"candidate": {}},
        response_model=AgentAssessment,
    )

    assert result.consistent is True
    assert sleeps == [35.0]


def test_nvidia_requests_are_paced_below_the_free_endpoint_rate_limit():
    now = [0.0]
    sleeps: list[float] = []
    request_started: list[float] = []

    def clock():
        return now[0]

    def sleep(seconds: float):
        sleeps.append(seconds)
        now[0] += seconds

    class CompletionEndpoint:
        def create(self, **_):
            request_started.append(now[0])
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"status":"ok"}'))])

    class Client:
        def __init__(self, **_):
            # Client construction must not consume part of the provider interval.
            now[0] += 0.9
            self.chat = SimpleNamespace(completions=CompletionEndpoint())

    llm = MultiProviderLLM(
        secrets={"NVIDIA_API_KEY": "nvidia-token"},
        client_factory=Client,
        clock=clock,
        sleeper=sleep,
    )
    llm.complete(provider="nvidia", model="model", system="JSON", payload={})
    now[0] += 0.1
    llm.complete(provider="nvidia", model="model", system="JSON", payload={})

    assert sleeps == pytest.approx([1.6])
    assert request_started[1] - request_started[0] == pytest.approx(1.7)
