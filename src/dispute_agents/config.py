from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias


ProviderName: TypeAlias = Literal["ollama", "openrouter", "nvidia"]


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
    credential_env: str | None


PROVIDER_BY_NAME: dict[ProviderName, ProviderConfig] = {
    "ollama": ProviderConfig("http://localhost:11434/v1/", None),
    "openrouter": ProviderConfig("https://openrouter.ai/api/v1/", "OPENROUTER_API_KEY"),
    "nvidia": ProviderConfig("https://integrate.api.nvidia.com/v1/", "NVIDIA_API_KEY"),
}


MODEL_BY_AGENT: dict[str, ModelConfig] = {
    "coordinator": ModelConfig("qwen3:8b", 8.19, "ollama"),
    "customer": ModelConfig("nvidia/nemotron-nano-9b-v2:free", 9.0, "openrouter"),
    "order_product": ModelConfig("meta/llama-3.1-8b-instruct", 8.0, "nvidia"),
    "payment": ModelConfig("qwen3:8b", 8.19, "ollama"),
    "delivery": ModelConfig("meta/llama-3.1-8b-instruct", 8.0, "nvidia"),
    "policy": ModelConfig("qwen3:8b", 8.19, "ollama"),
    "verifier": ModelConfig("meta/llama-3.1-8b-instruct", 8.0, "nvidia"),
}

POLICY_VERSION = "EC_POLICY_V2"
