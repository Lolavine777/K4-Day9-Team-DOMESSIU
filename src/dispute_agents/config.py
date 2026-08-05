from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias


ProviderName: TypeAlias = Literal["openrouter", "nvidia"]


@dataclass(frozen=True)
class ModelConfig:
    model: str
    parameters_billion: float
    provider: ProviderName

    @property
    def parameter_size(self) -> str:
        return f"{self.parameters_billion:g}B"


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    credential_env: str
    min_request_interval_seconds: float


PROVIDER_BY_NAME: dict[ProviderName, ProviderConfig] = {
    "openrouter": ProviderConfig("https://openrouter.ai/api/v1/", "OPENROUTER_API_KEY", 0.0),
    "nvidia": ProviderConfig("https://integrate.api.nvidia.com/v1/", "NVIDIA_API_KEY", 1.7),
}


NVIDIA_MODEL = ModelConfig("meta/llama-3.1-8b-instruct", 8.0, "nvidia")
OPENROUTER_MODEL = ModelConfig("nvidia/nemotron-nano-9b-v2:free", 9.0, "openrouter")

MODEL_BY_AGENT: dict[str, ModelConfig] = {
    agent: NVIDIA_MODEL
    for agent in ("coordinator", "customer", "order_product", "payment", "delivery", "policy", "verifier")
}

# A single canary call proves OpenRouter participation without exceeding its
# basic free-model daily request budget during a 50-case strict run.
MODEL_OVERRIDE_BY_CASE_AGENT: dict[tuple[str, str], ModelConfig] = {
    ("EC_001", "customer"): OPENROUTER_MODEL,
}


def model_for_agent(agent: str, case_id: str) -> ModelConfig:
    return MODEL_OVERRIDE_BY_CASE_AGENT.get((case_id, agent), MODEL_BY_AGENT[agent])


def configured_model_configs() -> tuple[ModelConfig, ...]:
    unique = {(config.provider, config.model): config for config in (*MODEL_BY_AGENT.values(), *MODEL_OVERRIDE_BY_CASE_AGENT.values())}
    return tuple(unique.values())


def configured_model_metadata_rows() -> list[dict[str, str]]:
    """Return the canonical, source-controlled routing table for metadata validation."""
    return [
        {
            "agent": agent,
            "scope": "default",
            "model": config.model,
            "parameter_size": config.parameter_size,
            "provider": config.provider,
        }
        for agent, config in MODEL_BY_AGENT.items()
    ] + [
        {
            "agent": agent,
            "scope": case_id,
            "model": config.model,
            "parameter_size": config.parameter_size,
            "provider": config.provider,
        }
        for (case_id, agent), config in MODEL_OVERRIDE_BY_CASE_AGENT.items()
    ]

POLICY_VERSION = "EC_POLICY_V2"
