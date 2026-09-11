"""실제 mock API 응답과 스키마만 모은 공유 묶음. 기존 경로를 덮어쓰지 않는다."""

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from ad_service.api.main import create_app
from ad_service.api.schemas.detail_page import DetailPageRequest, DetailPageResult

ROOT = Path(__file__).resolve().parents[1]


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def export(output: Path):
    archive = output.parent / f"{output.name}.zip"
    if output.exists() or archive.exists():
        raise FileExistsError("대상 폴더 또는 ZIP이 이미 있습니다. 새 이름을 사용하세요.")

    request = json.loads((ROOT / "examples/requests/detail_page_mock.json").read_text("utf-8"))
    sparse = deepcopy(request)
    sparse["request_id"] = "mug_sparse_001"
    sparse["product"]["facts"] = []
    sparse["product"]["images"] = []
    sparse["content_request"]["primary_image_asset_id"] = None
    invalid = deepcopy(request)
    invalid["request_id"] = "mug_invalid_001"
    invalid["content_request"]["primary_image_asset_id"] = "missing_asset"

    files = {}
    cases = []
    with TestClient(create_app()) as client:
        for prefix, payload, expected in (
            ("", request, 200),
            ("sparse.", sparse, 200),
            ("invalid.", invalid, 422),
        ):
            response = client.post("/v1/mock/detail-pages", json=payload)
            if response.status_code != expected:
                raise RuntimeError(f"{prefix or 'basic'}: unexpected HTTP {response.status_code}")
            result = response.json()
            if expected == 200:
                parsed = DetailPageResult.model_validate(result)
                if parsed.execution.model_calls != 0 or parsed.persisted:
                    raise RuntimeError("mock·미저장 조건을 만족하지 않습니다")
            files[f"{prefix}request.json"] = json_text(payload)
            files[f"{prefix}response.json"] = json_text(result)
            cases.append(
                {
                    "request": f"{prefix}request.json",
                    "response": f"{prefix}response.json",
                    "http_status": expected,
                }
            )

    files["request.schema.json"] = json_text(DetailPageRequest.model_json_schema(mode="validation"))
    files["response.schema.json"] = json_text(
        DetailPageResult.model_json_schema(mode="serialization")
    )
    files["README.md"] = (ROOT / "docs/detail_page_handoff.md").read_text("utf-8")
    files["manifest.json"] = json_text(
        {
            "schema_version": "mock-0.1",
            "endpoint": "/v1/mock/detail-pages",
            "source": "in_process_mock_api",
            "cases": cases,
            "files": {
                name: hashlib.sha256(value.encode("utf-8")).hexdigest()
                for name, value in files.items()
            },
        }
    )

    output.mkdir(parents=True, exist_ok=False)
    for name, value in files.items():
        with (output / name).open("x", encoding="utf-8") as file:
            file.write(value)
    with ZipFile(archive, "x", compression=ZIP_DEFLATED) as zip_file:
        for name in files:
            zip_file.write(output / name, arcname=f"{output.name}/{name}")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(export(args.output.resolve()))
