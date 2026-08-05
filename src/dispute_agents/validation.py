from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .config import configured_model_metadata_rows, model_for_agent
from .facts import customer_handoff, delivery_handoff, order_product_handoff, payment_handoff
from .models import CaseInput, CaseOutput
from .models import CustomerHandoff, DeliveryHandoff, OrderProductHandoff, PaymentHandoff, PolicyDecision
from .output import build_output
from .policy import PolicyEngine
from .repository import OlistRepository

EVIDENCE_RE = re.compile(r"^(order:[0-9a-f]+|item:[0-9a-f]+:[0-9]+|payment:[0-9a-f]+:[0-9]+|seller:[0-9a-f]+|policy:[A-Z_]+)$")

PRIMARY_ACTION = {
    "canceled_order_paid": "issue_full_refund",
    "unavailable_order_paid": "issue_full_refund",
    "late_delivery_seller": "refund_freight",
    "late_delivery_logistics": "refund_freight",
    "valid_split_payment": "explain_valid_split_payment",
    "unsupported_late_claim": "reject_late_refund",
}
REQUIRED_AGENTS = {
    "coordinator",
    "customer",
    "order_product",
    "payment",
    "delivery",
    "policy",
    "verifier",
}


def expected_case_names() -> list[str]:
    return [f"EC_{index:03d}.json" for index in range(1, 51)]


def validate_case_payload(payload: dict) -> CaseOutput:
    output = CaseOutput.model_validate(payload)
    invalid = [evidence for evidence in output.evidence_ids if not EVIDENCE_RE.match(evidence)]
    if invalid:
        raise ValueError(f"Invalid evidence IDs: {invalid}")
    if len(output.evidence_ids) != len(set(output.evidence_ids)):
        raise ValueError("Evidence IDs must not contain duplicates")
    if output.case_assessment.case_status == "no_action" and output.financial_resolution.recommended_refund_brl != 0:
        raise ValueError("no_action cases must not recommend a refund")
    if output.case_assessment.case_status == "action_required" and output.financial_resolution.recommended_refund_brl <= 0:
        raise ValueError("action_required cases need a positive refund")
    if output.resolution_actions[0] != PRIMARY_ACTION[output.case_assessment.primary_issue]:
        raise ValueError("First resolution action does not match the primary issue")
    expected_ranks = list(range(1, len(output.root_cause_analysis.ranked_causes) + 1))
    if [cause.rank for cause in output.root_cause_analysis.ranked_causes] != expected_ranks:
        raise ValueError("Root-cause ranks must be contiguous and start at 1")
    return output


def expected_output_for_case(*, case: CaseInput, repository: OlistRepository) -> CaseOutput:
    """Rebuild the canonical answer from CSV data without invoking any model."""
    customer = customer_handoff(case, repository)
    order_product = order_product_handoff(case, repository)
    payment = payment_handoff(case, repository, order_product)
    delivery = delivery_handoff(case, repository, order_product)
    policy = PolicyEngine().decide(
        order_product=order_product,
        payment=payment,
        delivery=delivery,
        is_repeat_customer=bool(customer.related_order_ids),
    )
    return build_output(
        case=case,
        customer=customer,
        order_product=order_product,
        payment=payment,
        delivery=delivery,
        policy=policy,
    )


def validate_output_against_source(*, output: CaseOutput, case: CaseInput, repository: OlistRepository) -> None:
    """Hard-gate every scored field against deterministic CSV and policy results."""
    validate_case_payload(output.model_dump(mode="python"))
    expected = expected_output_for_case(case=case, repository=repository)
    if output != expected:
        differing_fields = [
            field
            for field in CaseOutput.model_fields
            if getattr(output, field) != getattr(expected, field)
        ]
        raise ValueError(
            "Output differs from deterministic CSV/policy result in: "
            + ", ".join(differing_fields)
        )


def validate_output_against_handoffs(
    *,
    output: CaseOutput,
    customer: CustomerHandoff,
    order_product: OrderProductHandoff,
    payment: PaymentHandoff,
    delivery: DeliveryHandoff,
    policy: PolicyDecision,
) -> None:
    """Verify the output remains a faithful projection of validated agent handoffs."""
    validate_case_payload(output.model_dump(mode="python"))
    if output.affected_entities.order_ids != [order_product.order_id]:
        raise ValueError("Output order IDs differ from order handoff")
    if output.affected_entities.item_ids != order_product.item_ids or output.affected_entities.seller_ids != order_product.seller_ids:
        raise ValueError("Output affected entities differ from order/product handoff")
    if output.affected_entities.payment_ids != payment.payment_ids:
        raise ValueError("Output payment IDs differ from payment handoff")
    if output.customer_context.customer_unique_id != customer.customer_unique_id or output.customer_context.related_order_ids != customer.related_order_ids:
        raise ValueError("Output customer context differs from customer handoff")
    reconciliation = output.payment_reconciliation
    if (
        reconciliation.item_total_brl != order_product.item_total_brl
        or reconciliation.freight_total_brl != order_product.freight_total_brl
        or reconciliation.expected_total_brl != payment.expected_total_brl
        or reconciliation.payment_total_brl != payment.payment_total_brl
        or reconciliation.difference_brl != payment.difference_brl
        or reconciliation.reconciled != payment.reconciled
    ):
        raise ValueError("Output reconciliation differs from source-backed handoffs")
    if (
        output.delivery_analysis.delivered_at != delivery.delivered_at
        or output.delivery_analysis.estimated_delivery_at != delivery.estimated_delivery_at
        or output.delivery_analysis.carrier_handoff_at != delivery.carrier_handoff_at
        or output.delivery_analysis.delivery_variance_hours != delivery.delivery_variance_hours
        or output.delivery_analysis.seller_handoff_analysis != delivery.seller_handoff_analysis
        or output.delivery_analysis.late_handoff_seller_ids != delivery.late_handoff_seller_ids
    ):
        raise ValueError("Output delivery analysis differs from delivery handoff")
    if output.case_assessment.primary_issue != policy.primary_issue or output.case_assessment.secondary_issues != policy.secondary_issues:
        raise ValueError("Output issue assessment differs from policy handoff")
    if output.financial_resolution.recommended_refund_brl != policy.recommended_refund_brl or output.resolution_actions != policy.resolution_actions:
        raise ValueError("Output financial resolution differs from policy handoff")
    if output.root_cause_analysis.ranked_causes[0].cause_code != policy.root_cause_code:
        raise ValueError("Output root cause differs from policy handoff")
    expected_evidence = [f"order:{order_product.order_id}"]
    expected_evidence.extend(f"item:{item_id}" for item_id in order_product.item_ids)
    expected_evidence.extend(f"payment:{payment_id}" for payment_id in payment.payment_ids)
    expected_evidence.extend(f"seller:{party.party_id}" for party in policy.responsible_parties if party.party_type == "seller")
    expected_evidence.append(f"policy:{policy.root_cause_code}")
    if output.evidence_ids != expected_evidence:
        raise ValueError("Output evidence IDs differ from validated source-backed evidence")


def validate_directory(output_dir: Path, *, require_full_set: bool = True) -> list[CaseOutput]:
    names = sorted(path.name for path in output_dir.glob("EC_*.json"))
    if require_full_set and names != expected_case_names():
        raise ValueError(f"Expected exactly {len(expected_case_names())} output files, found {len(names)}")
    outputs: list[CaseOutput] = []
    for name in names:
        payload = json.loads((output_dir / name).read_text(encoding="utf-8"))
        output = validate_case_payload(payload)
        if output.case_id + ".json" != name:
            raise ValueError(f"Filename/case_id mismatch: {name}")
        outputs.append(output)
    return outputs


def validate_directory_against_source(*, output_dir: Path, input_dir: Path, data_dir: Path) -> list[CaseOutput]:
    outputs = validate_directory(output_dir)
    repository = OlistRepository(data_dir)
    for output in outputs:
        input_path = input_dir / f"{output.case_id}.json"
        if not input_path.exists():
            raise FileNotFoundError(f"Input file is missing for {output.case_id}: {input_path}")
        case = CaseInput.model_validate_json(input_path.read_text(encoding="utf-8"))
        validate_output_against_source(output=output, case=case, repository=repository)
    return outputs


def validate_runtime_artifacts(*, trace_path: Path, metadata_path: Path) -> None:
    """Validate that runtime evidence represents one complete strict 50-case run."""
    if not trace_path.exists() or not metadata_path.exists():
        raise FileNotFoundError("trace.jsonl and metadata.json are required")
    records: list[dict] = []
    for line_number, line in enumerate(trace_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid trace JSON on line {line_number}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"Trace line {line_number} must be a JSON object")
        records.append(record)
    if not records:
        raise ValueError("trace.jsonl is empty")
    run_ids = {record.get("run_id") for record in records}
    if len(run_ids) != 1 or None in run_ids:
        raise ValueError("Trace must contain exactly one non-null run_id")
    if any(record.get("event") == "run_failed" for record in records):
        raise ValueError("Trace contains run_failed")
    if sum(record.get("event") == "run_started" for record in records) != 1:
        raise ValueError("Trace must contain exactly one run_started event")
    if sum(record.get("event") == "run_completed" for record in records) != 1:
        raise ValueError("Trace must contain exactly one run_completed event")

    expected_case_ids = {name.removesuffix(".json") for name in expected_case_names()}
    started_counts = Counter(
        record.get("case_id") for record in records if record.get("event") == "case_started"
    )
    completed_counts = Counter(
        record.get("case_id") for record in records if record.get("event") == "case_completed"
    )
    expected_boundary_counts = {case_id: 1 for case_id in expected_case_ids}
    if dict(started_counts) != expected_boundary_counts or dict(completed_counts) != expected_boundary_counts:
        raise ValueError("Trace has incorrect case boundary-event counts")
    for case_id in expected_case_ids:
        start_index = next(
            index for index, record in enumerate(records)
            if record.get("event") == "case_started" and record.get("case_id") == case_id
        )
        complete_index = next(
            index for index, record in enumerate(records)
            if record.get("event") == "case_completed" and record.get("case_id") == case_id
        )
        if start_index >= complete_index:
            raise ValueError(f"Trace case boundary events are out of order for {case_id}")

    completed_calls = [record for record in records if record.get("event") == "model_completed"]
    failed_calls = [record for record in records if record.get("event") == "model_failed"]
    for record in completed_calls:
        case_id = record.get("case_id")
        agent = record.get("agent")
        if case_id not in expected_case_ids or agent not in REQUIRED_AGENTS:
            raise ValueError(f"Trace contains an unknown completed model call: {record}")
        configured = model_for_agent(agent, case_id)
        if (record.get("provider"), record.get("model")) != (configured.provider, configured.model):
            raise ValueError(
                "Trace model call does not match configured route for "
                f"{case_id}/{agent}: expected {configured.provider}/{configured.model}"
            )
    for case_id in expected_case_ids:
        agent_counts = Counter(
            record.get("agent")
            for record in completed_calls
            if record.get("case_id") == case_id
        )
        if set(agent_counts) != REQUIRED_AGENTS:
            raise ValueError(f"Trace is missing required model-backed agents for {case_id}")
        if agent_counts["coordinator"] != 2 or any(
            agent_counts[agent] != 1 for agent in REQUIRED_AGENTS - {"coordinator"}
        ):
            raise ValueError(f"Trace has incorrect model-call counts for {case_id}")
    if len(completed_calls) != 400:
        raise ValueError(f"Expected 400 successful model calls, found {len(completed_calls)}")
    providers = {record.get("provider") for record in completed_calls}
    if providers != {"nvidia", "openrouter"}:
        raise ValueError(f"Trace provider coverage is incorrect: {sorted(providers)}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    framework = metadata.get("framework") or {}
    if framework.get("name") != "LangGraph" or framework.get("version") in (None, "", "unknown"):
        raise ValueError("Metadata must contain the installed LangGraph version")
    run = metadata.get("run") or {}
    run_id = next(iter(run_ids))
    if run.get("run_id") != run_id:
        raise ValueError("Metadata run_id does not match trace")
    if run.get("cases_total") != 50 or run.get("cases_succeeded") != 50:
        raise ValueError("Metadata does not report 50 successful cases")
    if run.get("model_calls") != len(completed_calls):
        raise ValueError("Metadata successful model-call count does not match trace")
    if run.get("model_attempts") != len(completed_calls) + len(failed_calls):
        raise ValueError("Metadata model-attempt count does not match trace")
    if run.get("model_failures") != len(failed_calls):
        raise ValueError("Metadata failed model-call count does not match trace")
    provider_counts = Counter(record.get("provider") for record in completed_calls)
    if run.get("calls_by_provider") != dict(sorted(provider_counts.items())):
        raise ValueError("Metadata provider call counts do not match trace")
    agent_counts = Counter(record.get("agent") for record in completed_calls)
    if run.get("calls_by_agent") != dict(sorted(agent_counts.items())):
        raise ValueError("Metadata agent call counts do not match trace")
    expected_models = configured_model_metadata_rows()
    if metadata.get("models") != expected_models:
        raise ValueError("Metadata model routing table does not match source configuration")
    for model in metadata.get("models", []):
        parameter_size = str(model.get("parameter_size", "")).removesuffix("B")
        try:
            parameters_billion = float(parameter_size)
        except ValueError as exc:
            raise ValueError(f"Invalid parameter_size in metadata: {model}") from exc
        if parameters_billion > 10:
            raise ValueError(f"Model exceeds 10B parameter limit: {model}")
