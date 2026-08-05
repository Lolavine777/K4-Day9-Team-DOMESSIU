import json
from argparse import Namespace
from pathlib import Path
from zipfile import ZipFile

from dispute_agents.cli import jsonable, package
from dispute_agents.llm import FakeLLM
from dispute_agents.models import CaseInput
from dispute_agents.repository import OlistRepository
from dispute_agents.validation import expected_case_names, validate_directory
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
    package(Namespace(output_dir=str(output_dir), archive=str(archive)))

    with ZipFile(archive) as bundle:
        assert sorted(bundle.namelist()) == expected_case_names()
