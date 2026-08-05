from __future__ import annotations

import json
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TraceLogger:
    def __init__(self, path: Path | None = None, run_id: str | None = None):
        self.path = path
        self.run_id = run_id or uuid.uuid4().hex
        self.events: list[dict[str, Any]] = []
        self.model_calls = 0
        self.model_attempts = 0
        self.model_failures = 0
        self.calls_by_agent: Counter[str] = Counter()
        self.calls_by_provider: Counter[str] = Counter()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")

    def event(self, *, case_id: str | None, agent: str, event: str, **data: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "case_id": case_id,
            "agent": agent,
            "event": event,
            **data,
        }
        self.events.append(record)
        if self.path:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def model_event(self, *, case_id: str, agent: str, model: str, provider: str, started: float, attempt: int, status: str) -> None:
        self.model_attempts += 1
        if status == "completed":
            self.model_calls += 1
            self.calls_by_agent[agent] += 1
            self.calls_by_provider[provider] += 1
        else:
            self.model_failures += 1
        self.event(
            case_id=case_id,
            agent=agent,
            event=f"model_{status}",
            model=model,
            provider=provider,
            attempt=attempt,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
