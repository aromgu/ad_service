import hashlib
import json
import runpy
from pathlib import Path
from zipfile import ZipFile

import pytest

from ad_service.api.schemas.detail_page import DetailPageRequest, DetailPageResult

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/export_detail_page_handoff.py"


def test_handoff_export_is_consistent_and_refuses_overwrite(tmp_path):
    export = runpy.run_path(str(SCRIPT))["export"]
    output = tmp_path / "handoff-0.1"
    archive = export(output)
    assert archive.name == "handoff-0.1.zip"
    manifest = json.loads((output / "manifest.json").read_text())
    with ZipFile(archive) as zipped:
        assert len(zipped.namelist()) == len(manifest["files"]) + 1
        for name, digest in manifest["files"].items():
            data = (output / name).read_bytes()
            assert hashlib.sha256(data).hexdigest() == digest
            assert zipped.read(f"{output.name}/{name}") == data
    for case in manifest["cases"]:
        if case["http_status"] == 200:
            DetailPageRequest.model_validate_json((output / case["request"]).read_text())
            result = DetailPageResult.model_validate_json((output / case["response"]).read_text())
            assert result.execution.model_calls == 0
    before = archive.read_bytes()
    with pytest.raises(FileExistsError):
        export(output)
    assert archive.read_bytes() == before
