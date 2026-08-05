from __future__ import annotations

from typing import Any, TypeVar, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from .facts import customer_handoff, delivery_handoff, order_product_handoff, payment_handoff
from .llm import AgentInvoker, LLMClient, MultiProviderLLM
from .models import (
    CaseInput,
    CaseOutput,
    AgentAssessment,
    CoordinatorResult,
    CustomerHandoff,
    DeliveryHandoff,
    OrderProductHandoff,
    PaymentHandoff,
    PolicyDecision,
    VerifierReview,
)
from .output import build_output
from .policy import PolicyEngine
from .repository import OlistRepository
from .tracing import TraceLogger
from .validation import validate_output_against_handoffs

T = TypeVar("T", bound=BaseModel)


class WorkflowState(TypedDict, total=False):
    case: CaseInput
    customer: CustomerHandoff
    order_product: OrderProductHandoff
    payment: PaymentHandoff
    delivery: DeliveryHandoff
    policy: PolicyDecision
    output: CaseOutput


class DisputeWorkflow:
    def __init__(self, *, repository: OlistRepository, llm: LLMClient | None = None, trace: TraceLogger | None = None):
        self.repository = repository
        self.trace = trace or TraceLogger()
        self.invoker = AgentInvoker(llm or MultiProviderLLM(), self.trace)
        self.policy_engine = PolicyEngine()
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(WorkflowState)
        graph.add_node("coordinator_start", self._coordinator_start)
        graph.add_node("customer", self._customer)
        graph.add_node("order_product", self._order_product)
        graph.add_node("payment", self._payment)
        graph.add_node("delivery", self._delivery)
        graph.add_node("policy", self._policy)
        graph.add_node("verifier", self._verifier)
        graph.add_node("coordinator_finish", self._coordinator_finish)
        graph.add_edge(START, "coordinator_start")
        graph.add_edge("coordinator_start", "customer")
        graph.add_edge("customer", "order_product")
        graph.add_edge("order_product", "payment")
        graph.add_edge("payment", "delivery")
        graph.add_edge("delivery", "policy")
        graph.add_edge("policy", "verifier")
        graph.add_edge("verifier", "coordinator_finish")
        graph.add_edge("coordinator_finish", END)
        return graph.compile()

    def run_case(self, case: CaseInput) -> CaseOutput:
        result = self.graph.invoke({"case": case})
        return result["output"]

    def _coordinator_start(self, state: WorkflowState) -> dict:
        case = state["case"]
        self._require_model_result(
            agent="coordinator",
            case_id=case.case_id,
            candidate=CoordinatorResult(case_id=case.case_id, status="ready"),
            facts={"claimed_order_id": case.customer_request.claimed_order_id},
        )
        return {}

    def _customer(self, state: WorkflowState) -> dict:
        case = state["case"]
        candidate = customer_handoff(case, self.repository)
        self.trace.event(case_id=case.case_id, agent="customer", event="tool_completed", tool="customer_history_lookup")
        handoff = self._require_model_result(agent="customer", case_id=case.case_id, candidate=candidate)
        self._record_handoff(case.case_id, "customer", handoff)
        return {"customer": handoff}

    def _order_product(self, state: WorkflowState) -> dict:
        case = state["case"]
        candidate = order_product_handoff(case, self.repository)
        self.trace.event(case_id=case.case_id, agent="order_product", event="tool_completed", tool="order_product_lookup")
        handoff = self._require_model_result(agent="order_product", case_id=case.case_id, candidate=candidate)
        self._record_handoff(case.case_id, "order_product", handoff)
        return {"order_product": handoff}

    def _payment(self, state: WorkflowState) -> dict:
        case = state["case"]
        candidate = payment_handoff(case, self.repository, state["order_product"])
        self.trace.event(case_id=case.case_id, agent="payment", event="tool_completed", tool="payment_reconciliation")
        handoff = self._require_model_result(
            agent="payment",
            case_id=case.case_id,
            candidate=candidate,
        )
        self._record_handoff(case.case_id, "payment", handoff)
        return {"payment": handoff}

    def _delivery(self, state: WorkflowState) -> dict:
        case = state["case"]
        candidate = delivery_handoff(case, self.repository, state["order_product"])
        self.trace.event(case_id=case.case_id, agent="delivery", event="tool_completed", tool="delivery_variance_calculator")
        handoff = self._require_model_result(
            agent="delivery",
            case_id=case.case_id,
            candidate=candidate,
        )
        self._record_handoff(case.case_id, "delivery", handoff)
        return {"delivery": handoff}

    def _policy(self, state: WorkflowState) -> dict:
        case = state["case"]
        expected_policy = self.policy_engine.decide(
            order_product=state["order_product"],
            payment=state["payment"],
            delivery=state["delivery"],
            is_repeat_customer=bool(state["customer"].related_order_ids),
        )
        self.trace.event(case_id=case.case_id, agent="policy", event="tool_completed", tool="ec_policy_v2_evaluator")
        policy = self._require_model_result(
            agent="policy",
            case_id=case.case_id,
            candidate=expected_policy,
            facts={key: state[key].model_dump(mode="json") for key in ("customer", "order_product", "payment", "delivery")},
        )
        self._record_handoff(case.case_id, "policy", policy)
        return {"policy": policy}

    def _verifier(self, state: WorkflowState) -> dict:
        case = state["case"]
        output = build_output(
            case=case,
            customer=state["customer"],
            order_product=state["order_product"],
            payment=state["payment"],
            delivery=state["delivery"],
            policy=state["policy"],
        )
        validate_output_against_handoffs(
            output=output,
            customer=state["customer"],
            order_product=state["order_product"],
            payment=state["payment"],
            delivery=state["delivery"],
            policy=state["policy"],
        )
        self.trace.event(case_id=case.case_id, agent="verifier", event="tool_completed", tool="output_schema_and_evidence_validator")
        review = self.invoker.call(
            agent="verifier",
            case_id=case.case_id,
            payload={
                "verification_candidate": output.model_dump(mode="json"),
                "deterministic_validation": "passed",
                "required_response": {"approved": True, "corrections": []},
            },
            response_model=VerifierReview,
        )
        if not review.approved or review.corrections:
            raise RuntimeError(f"Verifier rejected {case.case_id}: {review.corrections}")
        self.trace.event(case_id=case.case_id, agent="verifier", event="schema_validated", primary_issue=output.case_assessment.primary_issue, approved=review.approved)
        self._record_handoff(case.case_id, "verifier", output)
        return {"output": output}

    def _coordinator_finish(self, state: WorkflowState) -> dict:
        case = state["case"]
        self._require_model_result(
            agent="coordinator",
            case_id=case.case_id,
            candidate=CoordinatorResult(case_id=case.case_id, status="complete"),
            facts={"primary_issue": state["output"].case_assessment.primary_issue},
        )
        self.trace.event(case_id=case.case_id, agent="coordinator", event="case_completed")
        return {}

    def _record_handoff(self, case_id: str, agent: str, handoff: Any) -> None:
        """Record a schema-level trace without duplicating source data or model reasoning."""
        dumped = handoff.model_dump(mode="json")
        self.trace.event(
            case_id=case_id,
            agent=agent,
            event="handoff_created",
            handoff_schema=type(handoff).__name__,
            field_names=sorted(dumped),
        )

    def _require_model_result(self, *, agent: str, case_id: str, candidate: T, facts: dict | None = None) -> T:
        candidate_payload = candidate.model_dump(mode="json")
        assessment = self.invoker.call(
            agent=agent,
            case_id=case_id,
            payload={
                "handoff_schema": type(candidate).__name__,
                "tool_facts": facts or candidate_payload,
                "candidate": candidate_payload,
                "instruction": "The tool_facts are deterministic CSV/tool results. Check the candidate for consistency with them. Set consistent=true when they match, even when the business decision rejects a refund claim. Return {\"consistent\": boolean, \"summary\": string} as JSON only.",
            },
            response_model=AgentAssessment,
        )
        if not assessment.consistent:
            self.trace.event(case_id=case_id, agent=agent, event="handoff_rejected", reason=assessment.summary)
            raise RuntimeError(f"{agent} rejected the CSV-backed candidate: {assessment.summary}")
        self.trace.event(case_id=case_id, agent=agent, event="model_assessment", consistent=True, summary=assessment.summary[:300])
        return candidate
