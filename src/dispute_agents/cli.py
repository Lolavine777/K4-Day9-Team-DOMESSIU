from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from importlib.metadata import version as package_version
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from .config import POLICY_VERSION, configured_model_configs, configured_model_metadata_rows
from .llm import MultiProviderLLM
from .models import CaseInput
from .repository import OlistRepository
from .tracing import TraceLogger
from .validation import (
    expected_case_names,
    validate_directory_against_source,
    validate_output_against_source,
    validate_runtime_artifacts,
)
from .workflow import DisputeWorkflow


def jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def load_cases(input_dir: Path) -> list[CaseInput]:
    names = sorted(path.name for path in input_dir.glob("EC_*.json"))
    if names != expected_case_names():
        raise ValueError(f"Input directory must contain exactly {len(expected_case_names())} EC JSON files")
    return [CaseInput.model_validate(json.loads((input_dir / name).read_text(encoding="utf-8"))) for name in names]


def promote_output_directory(*, staging: Path, output_dir: Path) -> None:
    """Swap a fully validated staging directory into place, restoring on failure."""
    backup = output_dir.parent / f".{output_dir.name}-backup-{uuid4().hex}"
    output_dir.replace(backup)
    try:
        staging.replace(output_dir)
    except Exception:
        backup.replace(output_dir)
        raise
    shutil.rmtree(backup)


def preflight_models(_: argparse.Namespace) -> int:
    llm = MultiProviderLLM()
    for config in configured_model_configs():
        provider, model = config.provider, config.model
        reply = llm.complete(provider=provider, model=model, system="Return only a JSON acknowledgement.", payload={"healthcheck": True})
        if not reply.strip():
            raise RuntimeError(f"Preflight returned empty content for {model} ({provider})")
        print(f"OK {model} ({config.provider})")
    return 0


def smoke(args: argparse.Namespace) -> int:
    case_path = Path(args.input_dir) / f"{args.case_id}.json"
    if not case_path.exists():
        raise FileNotFoundError(f"Smoke case not found: {case_path}")
    case = CaseInput.model_validate_json(case_path.read_text(encoding="utf-8"))
    repository = OlistRepository(Path(args.data_dir))
    output = DisputeWorkflow(repository=repository).run_case(case)
    validate_output_against_source(output=output, case=case, repository=repository)
    print(json.dumps({
        "case_id": output.case_id,
        "primary_issue": output.case_assessment.primary_issue,
        "status": "source_validated",
    }, sort_keys=True))
    return 0


def run(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir)
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    trace_path = Path(args.trace)
    metadata_path = Path(args.metadata)
    cases = load_cases(input_dir)
    repository = OlistRepository(data_dir)
    trace = TraceLogger(trace_path)
    workflow = DisputeWorkflow(repository=repository, trace=trace)
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="olist-output-", dir=output_dir.parent))
    started = datetime.now(timezone.utc)
    try:
        trace.event(case_id=None, agent="coordinator", event="run_started", cases_total=len(cases), policy_version=POLICY_VERSION)
        for case in cases:
            trace.event(case_id=case.case_id, agent="coordinator", event="case_started")
            output = workflow.run_case(case)
            (staging / f"{case.case_id}.json").write_text(
                json.dumps(jsonable(output.model_dump(mode="python")), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        validated = validate_directory_against_source(output_dir=staging, input_dir=input_dir, data_dir=data_dir)
        promote_output_directory(staging=staging, output_dir=output_dir)
        issue_distribution = Counter(output.case_assessment.primary_issue for output in validated)
        trace.event(
            case_id=None,
            agent="coordinator",
            event="run_completed",
            cases_succeeded=len(cases),
            model_calls=trace.model_calls,
            model_attempts=trace.model_attempts,
            model_failures=trace.model_failures,
        )
        metadata = {
            "policy_version": POLICY_VERSION,
            "models": configured_model_metadata_rows(),
            "framework": {"name": "LangGraph", "version": package_version("langgraph")},
            "runtime": {"language": "Python", "version": sys.version.split()[0], "platform": platform.platform()},
            "run": {
                "run_id": trace.run_id,
                "started_at": started.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "cases_total": len(cases),
                "cases_succeeded": len(cases),
                "model_calls": trace.model_calls,
                "model_attempts": trace.model_attempts,
                "model_failures": trace.model_failures,
                "calls_by_agent": dict(sorted(trace.calls_by_agent.items())),
                "calls_by_provider": dict(sorted(trace.calls_by_provider.items())),
                "primary_issue_distribution": dict(sorted(issue_distribution.items())),
                "strict_model_invocation": True,
            },
        }
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(cases)} validated outputs to {output_dir}")
        return 0
    except Exception as exc:
        trace.event(case_id=None, agent="coordinator", event="run_failed", error=str(exc))
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def validate(args: argparse.Namespace) -> int:
    outputs = validate_directory_against_source(
        output_dir=Path(args.output_dir),
        input_dir=Path(args.input_dir),
        data_dir=Path(args.data_dir),
    )
    validate_runtime_artifacts(trace_path=Path(args.trace), metadata_path=Path(args.metadata))
    distribution = Counter(output.case_assessment.primary_issue for output in outputs)
    print(f"Validated {len(outputs)} source-backed output files")
    print("Primary issue distribution: " + json.dumps(dict(sorted(distribution.items())), sort_keys=True))
    print("Validated trace.jsonl and metadata.json")
    return 0


def package(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    validate_directory_against_source(
        output_dir=output_dir,
        input_dir=Path(args.input_dir),
        data_dir=Path(args.data_dir),
    )
    archive = Path(args.archive)
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
        for name in expected_case_names():
            bundle.write(output_dir / name, arcname=name)
    with ZipFile(archive) as bundle:
        if sorted(bundle.namelist()) != expected_case_names():
            raise RuntimeError("Submission archive did not contain exactly the expected 50 JSON files")
    print(f"Created {archive}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Olist multi-agent dispute-resolution pipeline")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("preflight-models").set_defaults(handler=preflight_models)
    smoke_parser = subcommands.add_parser("smoke")
    smoke_parser.add_argument("--case-id", default="EC_001")
    smoke_parser.add_argument("--input-dir", default="input")
    smoke_parser.add_argument("--data-dir", default="data")
    smoke_parser.set_defaults(handler=smoke)
    run_parser = subcommands.add_parser("run")
    run_parser.add_argument("--input-dir", default="input")
    run_parser.add_argument("--data-dir", default="data")
    run_parser.add_argument("--output-dir", default="output")
    run_parser.add_argument("--trace", default="trace.jsonl")
    run_parser.add_argument("--metadata", default="metadata.json")
    run_parser.set_defaults(handler=run)
    validate_parser = subcommands.add_parser("validate")
    validate_parser.add_argument("--output-dir", default="output")
    validate_parser.add_argument("--input-dir", default="input")
    validate_parser.add_argument("--data-dir", default="data")
    validate_parser.add_argument("--trace", default="trace.jsonl")
    validate_parser.add_argument("--metadata", default="metadata.json")
    validate_parser.set_defaults(handler=validate)
    package_parser = subcommands.add_parser("package")
    package_parser.add_argument("--output-dir", default="output")
    package_parser.add_argument("--input-dir", default="input")
    package_parser.add_argument("--data-dir", default="data")
    package_parser.add_argument("--archive", default="submission_output.zip")
    package_parser.set_defaults(handler=package)
    args = parser.parse_args(argv)
    return args.handler(args)
