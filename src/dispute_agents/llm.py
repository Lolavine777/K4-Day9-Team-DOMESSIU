from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from typing import Protocol, TypeVar

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from .config import PROVIDER_BY_NAME, ProviderName, model_for_agent
from .tracing import TraceLogger


class LLMClient(Protocol):
    def complete(self, *, provider: ProviderName, model: str, system: str, payload: dict) -> str: ...


class MultiProviderLLM:
    """Routes each agent call to its configured OpenAI-compatible provider."""

    def __init__(
        self,
        secrets: dict[str, str | None] | None = None,
        client_factory: Callable[..., OpenAI] = OpenAI,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        load_dotenv()
        self.secrets = secrets or {}
        self.client_factory = client_factory
        self.clients: dict[ProviderName, OpenAI] = {}
        self.clock = clock
        self.sleeper = sleeper
        self.last_request_started: dict[ProviderName, float] = {}

    def client_for(self, provider: ProviderName) -> OpenAI:
        if provider not in PROVIDER_BY_NAME:
            raise ValueError(f"Unsupported provider: {provider}")
        if provider in self.clients:
            return self.clients[provider]
        config = PROVIDER_BY_NAME[provider]
        token = self.secrets.get(config.credential_env) or os.getenv(config.credential_env)
        if not token:
            raise RuntimeError(f"{config.credential_env} is required for {provider}. Copy .env.example to .env and set it.")
        client = self.client_factory(base_url=config.base_url, api_key=token, timeout=60.0)
        self.clients[provider] = client
        return client

    def complete(self, *, provider: ProviderName, model: str, system: str, payload: dict) -> str:
        client = self.client_for(provider)
        self._pace(provider)
        provider_options = (
            {"extra_body": {"reasoning": {"effort": "low", "exclude": True}}}
            if provider == "openrouter"
            else {}
        )
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": build_user_content(model, payload)},
            ],
            temperature=0,
            max_tokens=max_tokens_for_model(model),
            **provider_options,
        )
        return completion.choices[0].message.content or ""

    def _pace(self, provider: ProviderName) -> None:
        interval = PROVIDER_BY_NAME[provider].min_request_interval_seconds
        now = self.clock()
        previous = self.last_request_started.get(provider)
        if previous is not None:
            delay = interval - (now - previous)
            if delay > 0:
                self.sleeper(delay)
                now = self.clock()
        self.last_request_started[provider] = now


class FakeLLM:
    """Deterministic model fake used only by automated tests."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.routes: list[tuple[ProviderName, str]] = []

    def complete(self, *, provider: ProviderName, model: str, system: str, payload: dict) -> str:
        self.calls.append((model, payload))
        self.routes.append((provider, model))
        if "verification_candidate" in payload:
            return '{"approved":true,"corrections":[]}'
        if "candidate" in payload:
            return '{"consistent":true,"summary":"CSV-backed candidate is consistent"}'
        return '{"status":"approved"}'


SYSTEM_PROMPTS = {
    "coordinator": "You are the Coordinator Agent. Route and synthesize one Olist complaint. Use supplied facts only. Return JSON only, with no Markdown.",
    "customer": "You are the Customer Agent. Analyze identity and source-ordered history only. Do not invent facts. Return a JSON consistency assessment only, with no Markdown.",
    "order_product": "You are the Order and Product Agent. Analyze supplied order, item, seller, product and category facts only. Return a JSON consistency assessment only, with no Markdown.",
    "payment": "You are the Payment Agent. Analyze supplied reconciliation facts only. Do not invent BRL amounts. Return a JSON consistency assessment only, with no Markdown.",
    "delivery": "You are the Delivery Agent. Analyze supplied delivery and seller-handoff facts only. Return a JSON consistency assessment only, with no Markdown.",
    "policy": "You are the Policy Agent. Check EC_POLICY_V2 priority against supplied handoffs. The word consistent refers to data/policy agreement, not whether a customer's refund claim is approved. Return a JSON consistency assessment only, with no Markdown.",
    "verifier": "You are the Verifier Agent. Review the supplied output and deterministic validation result. If deterministic_validation is passed, return exactly {\"approved\":true,\"corrections\":[]}. Use only keys approved and corrections. Return JSON only, with no Markdown.",
}

T = TypeVar("T", bound=BaseModel)


def build_user_content(_: str, payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def max_tokens_for_model(model: str) -> int:
    return 500


def parse_model_json(raw: str) -> dict:
    text = raw.strip()
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1].strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text[:-3].strip()
    decoder = json.JSONDecoder()
    start = text.find("{")
    if start < 0:
        raise ValueError("Model response did not contain a JSON object")
    payload, index = decoder.raw_decode(text[start:])
    if text[start + index:].strip():
        raise ValueError("Model response contained text after its JSON object")
    if not isinstance(payload, dict):
        raise ValueError("Model response JSON must be an object")
    return payload


class AgentInvoker:
    def __init__(
        self,
        llm: LLMClient,
        trace: TraceLogger,
        retries: int = 2,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.llm = llm
        self.trace = trace
        self.retries = retries
        self.sleeper = sleeper

    def call(self, *, agent: str, case_id: str, payload: dict, response_model: type[T] | None = None) -> T | str:
        config = model_for_agent(agent, case_id)
        error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            started = time.perf_counter()
            self.trace.event(case_id=case_id, agent=agent, event="model_started", model=config.model, provider=config.provider, attempt=attempt)
            try:
                answer = self.llm.complete(provider=config.provider, model=config.model, system=SYSTEM_PROMPTS[agent], payload=payload)
                if not answer.strip():
                    raise ValueError("Model response was empty")
                result = response_model.model_validate(parse_model_json(answer)) if response_model else answer
                self.trace.model_event(case_id=case_id, agent=agent, model=config.model, provider=config.provider, started=started, attempt=attempt, status="completed")
                return result
            except Exception as exc:  # provider failures are expected operational errors
                error = exc
                self.trace.model_event(case_id=case_id, agent=agent, model=config.model, provider=config.provider, started=started, attempt=attempt, status="failed")
                if attempt < self.retries and getattr(exc, "status_code", None) == 429:
                    delay_seconds = 35.0
                    self.trace.event(
                        case_id=case_id,
                        agent=agent,
                        event="retry_scheduled",
                        provider=config.provider,
                        attempt=attempt + 1,
                        delay_seconds=delay_seconds,
                        reason="rate_limit",
                    )
                    self.sleeper(delay_seconds)
        raise RuntimeError(f"{agent} model failed after {self.retries} attempts: {error}")
