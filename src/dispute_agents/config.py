from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    model: str
    parameter_size: str
    provider: str


MODEL_BY_AGENT: dict[str, ModelConfig] = {
    "coordinator": ModelConfig("Qwen/Qwen3-8B:nscale", "8.2B", "nscale"),
    "customer": ModelConfig("Qwen/Qwen2.5-7B-Instruct:together", "7B", "together"),
    "order_product": ModelConfig("meta-llama/Llama-3.1-8B-Instruct:deepinfra", "8B", "deepinfra"),
    "payment": ModelConfig("Qwen/Qwen2.5-7B-Instruct:together", "7B", "together"),
    "delivery": ModelConfig("meta-llama/Llama-3.1-8B-Instruct:deepinfra", "8B", "deepinfra"),
    "policy": ModelConfig("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B:nscale", "7B", "nscale"),
    "verifier": ModelConfig("Qwen/Qwen3-8B:nscale", "8.2B", "nscale"),
}

HF_ROUTER_URL = "https://router.huggingface.co/v1"
POLICY_VERSION = "EC_POLICY_V2"
