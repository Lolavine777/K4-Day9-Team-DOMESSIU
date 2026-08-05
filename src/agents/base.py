from abc import ABC, abstractmethod
from typing import Dict, Any
from src.repository import DataRepository
from src.llm_client import GroqLLMClient
from src.handoff import AgentHandoff, Fact


class BaseAgent(ABC):
    """Abstract Base Class for all domain agents in the multi-agent system."""

    def __init__(self, name: str, repository: DataRepository, llm_client: GroqLLMClient):
        self.name = name
        self.repository = repository
        self.llm_client = llm_client

    @abstractmethod
    def process_handoff(self, handoff: AgentHandoff) -> AgentHandoff:
        """Process incoming handoff from previous agent and produce output handoff."""
        pass
