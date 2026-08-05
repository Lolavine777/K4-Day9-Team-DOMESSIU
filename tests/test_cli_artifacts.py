import json
from argparse import Namespace
from pathlib import Path
from zipfile import ZipFile

import pytest

from dispute_agents.cli import jsonable, package, promote_output_directory
from dispute_agents.config import configured_model_metadata_rows, model_for_agent
from dispute_agents.llm import FakeLLM
from dispute_agents.models import CaseInput
from dispute_agents.repository import OlistRepository
from dispute_agents.validation import expected_case_names, validate_directory, validate_runtime_artifacts
from dispute_agents.workflow import DisputeWorkflow


ROOT = Path(__file__).resolve().parents[1]


def test_package_contains_only_the_validated_50_json_files(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    cases = [
        CaseInput.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((ROOT / "input").glob("EC_*.json"))
    ]
    workflow = DisputeWorkflow(repository=OlistRepository(ROOT / "data"), llm=FakeLLM())
    for case in cases:
        payload = jsonable(workflow.run_case(case).model_dump(mode="python"))
        (output_dir / f"{case.case_id}.json").write_text(json.dumps(payload), encoding="utf-8")

    assert len(validate_directory(output_dir)) == 50
    archive = tmp_path / "submission.zip"
    package(Namespace(
        output_dir=str(output_dir),
        input_dir=str(ROOT / "input"),
        data_dir=str(ROOT / "data"),
        archive=str(archive),
    ))

    with ZipFile(archive) as bundle:
        assert sorted(bundle.namelist()) == expected_case_names()


def test_output_promotion_swaps_the_complete_directory(tmp_path):
    output_dir = tmp_path / "output"
    staging = tmp_path / "staging"
    output_dir.mkdir()
    staging.mkdir()
    (output_dir / "old.json").write_text("old", encoding="utf-8")
    (staging / "EC_001.json").write_text("new", encoding="utf-8")

    promote_output_directory(staging=staging, output_dir=output_dir)

    assert not staging.exists()
    assert sorted(path.name for path in output_dir.iterdir()) == ["EC_001.json"]


def test_runtime_artifact_gate_requires_one_complete_two_provider_run(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    metadata_path = tmp_path / "metadata.json"
    run_id = "test-run"
    records = [{"run_id": run_id, "case_id": None, "agent": "coordinator", "event": "run_started"}]
    providers = {"nvidia": 0, "openrouter": 0}
    for index in range(1, 51):
        case_id = f"EC_{index:03d}"
        records.append({"run_id": run_id, "case_id": case_id, "agent": "coordinator", "event": "case_started"})
        agents = ["coordinator", "customer", "order_product", "payment", "delivery", "policy", "verifier", "coordinator"]
        for agent in agents:
            config = model_for_agent(agent, case_id)
            providers[config.provider] += 1
            records.append({
                "run_id": run_id,
                "case_id": case_id,
                "agent": agent,
                "event": "model_completed",
                "provider": config.provider,
                "model": config.model,
                "attempt": 1,
            })
        records.append({"run_id": run_id, "case_id": case_id, "agent": "coordinator", "event": "case_completed"})
    records.append({"run_id": run_id, "case_id": None, "agent": "coordinator", "event": "run_completed"})
    trace_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    metadata_path.write_text(json.dumps({
        "models": configured_model_metadata_rows(),
        "framework": {"name": "LangGraph", "version": "1.2.9"},
        "run": {
            "run_id": run_id,
            "cases_total": 50,
            "cases_succeeded": 50,
            "model_calls": 400,
            "model_attempts": 400,
            "model_failures": 0,
            "calls_by_agent": {
                "coordinator": 100,
                "customer": 50,
                "delivery": 50,
                "order_product": 50,
                "payment": 50,
                "policy": 50,
                "verifier": 50,
            },
            "calls_by_provider": providers,
        },
    }), encoding="utf-8")

    validate_runtime_artifacts(trace_path=trace_path, metadata_path=metadata_path)

    duplicate_boundary = records[:1] + [dict(records[1])] + records[1:]
    trace_path.write_text("\n".join(json.dumps(record) for record in duplicate_boundary) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="boundary-event counts"):
        validate_runtime_artifacts(trace_path=trace_path, metadata_path=metadata_path)

    wrong_route = [dict(record) for record in records]
    canary = next(
        record
        for record in wrong_route
        if record.get("event") == "model_completed"
        and record.get("case_id") == "EC_001"
        and record.get("agent") == "customer"
    )
    canary["provider"] = "nvidia"
    trace_path.write_text("\n".join(json.dumps(record) for record in wrong_route) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="configured route"):
        validate_runtime_artifacts(trace_path=trace_path, metadata_path=metadata_path)

    wrong_model = [dict(record) for record in records]
    target = next(record for record in wrong_model if record.get("event") == "model_completed")
    target["model"] = "wrong/model"
    trace_path.write_text("\n".join(json.dumps(record) for record in wrong_model) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="configured route"):
        validate_runtime_artifacts(trace_path=trace_path, metadata_path=metadata_path)

    trace_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"run_id": run_id, "case_id": None, "agent": "coordinator", "event": "run_failed"}) + "\n")
    with pytest.raises(ValueError, match="run_failed"):
        validate_runtime_artifacts(trace_path=trace_path, metadata_path=metadata_path)
