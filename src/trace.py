import json
import os
from typing import List, Dict, Any


class TraceLogger:
    """Logger for writing agent execution traces to trace.jsonl."""

    def __init__(self, filepath: str = "trace.jsonl"):
        self.filepath = filepath
        self.entries: List[Dict[str, Any]] = []

    def clear(self) -> None:
        self.entries = []
        if os.path.exists(self.filepath):
            os.remove(self.filepath)

    def log_case_trace(self, case_id: str, trace_entries: List[Dict[str, Any]]) -> None:
        case_trace = {
            "case_id": case_id,
            "agent_handoffs": trace_entries,
        }
        self.entries.append(case_trace)

    def flush(self) -> None:
        with open(self.filepath, "w", encoding="utf-8") as f:
            for entry in self.entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
