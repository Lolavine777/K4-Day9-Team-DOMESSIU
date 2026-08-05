from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import langgraph

from .config import MODEL_BY_AGENT, POLICY_VERSION
from .llm import HuggingFaceLLM
from .models import CaseInput
from .repository import OlistRepository
from .tracing import TraceLogger
from .validation import expected_case_names, validate_directory
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


def preflight_models(_: argparse.Namespace) -> int:
    llm = HuggingFaceLLM()
    unique = {config.model: config for config in MODEL_BY_AGENT.values()}
    for model, config in unique.items():
        llm.complete(model=model, system="Return only a JSON acknowledgement.", payload={"healthcheck": True})
        print(f"OK {model} ({config.provider})")
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
        for case in cases:
            trace.event(case_id=case.case_id, agent="coordinator", event="case_started")
            output = workflow.run_case(case)
            (staging / f"{case.case_id}.json").write_text(
                json.dumps(jsonable(output.model_dump(mode="python")), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        validate_directory(staging)
        for old_file in output_dir.glob("EC_*.json"):
            old_file.unlink()
        gitkeep = output_dir / ".gitkeep"
        if gitkeep.exists():
            gitkeep.unlink()
        for file in sorted(staging.glob("EC_*.json")):
            shutil.move(str(file), output_dir / file.name)
        metadata = {
            "policy_version": POLICY_VERSION,
            "models": [
                {"agent": agent, "model": config.model, "parameter_size": config.parameter_size, "provider": config.provider}
                for agent, config in MODEL_BY_AGENT.items()
            ],
            "framework": {"name": "LangGraph", "version": getattr(langgraph, "__version__", "unknown")},
            "runtime": {"language": "Python", "version": sys.version.split()[0], "platform": platform.platform()},
            "run": {
                "run_id": trace.run_id,
                "started_at": started.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "cases_total": len(cases),
                "cases_succeeded": len(cases),
                "model_calls": trace.model_calls,
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
    outputs = validate_directory(Path(args.output_dir))
    print(f"Validated {len(outputs)} output files")
    return 0


def package(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    validate_directory(output_dir)
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
    run_parser = subcommands.add_parser("run")
    run_parser.add_argument("--input-dir", default="input")
    run_parser.add_argument("--data-dir", default="data")
    run_parser.add_argument("--output-dir", default="output")
    run_parser.add_argument("--trace", default="logging/trace.jsonl")
    run_parser.add_argument("--metadata", default="logging/metadata.json")
    run_parser.set_defaults(handler=run)
    validate_parser = subcommands.add_parser("validate")
    validate_parser.add_argument("--output-dir", default="output")
    validate_parser.set_defaults(handler=validate)
    package_parser = subcommands.add_parser("package")
    package_parser.add_argument("--output-dir", default="output")
    package_parser.add_argument("--archive", default="submission_output.zip")
    package_parser.set_defaults(handler=package)
    args = parser.parse_args(argv)
    return args.handler(args)
