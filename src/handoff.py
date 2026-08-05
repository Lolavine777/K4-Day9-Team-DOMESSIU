from dataclasses import dataclass, field, asdict
from typing import Any, List, Dict


@dataclass
class Fact:
    description: str
    source_ids: List[str]
    value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "source_ids": self.source_ids,
            "value": self.value,
        }


@dataclass
class AgentHandoff:
    ticket_id: str
    sender: str
    recipient: str
    question: str
    facts_found: List[Fact] = field(default_factory=list)
    facts_missing: List[str] = field(default_factory=list)
    next_suggestion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "question": self.question,
            "facts_found": [f.to_dict() if isinstance(f, Fact) else f for f in self.facts_found],
            "facts_missing": self.facts_missing,
            "next_suggestion": self.next_suggestion,
        }
