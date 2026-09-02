from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import Counter
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree

from PIL import Image

from ad_service.api.schemas.generation import (
    BoundingBox,
    GenerationOptions,
    GenerationRequest,
    OutputType,
)

IMAGE_PATTERN = re.compile(r"^(?P<item>\d+)_0_s_(?P<index>\d+)\.jpg$", re.IGNORECASE)
MASTER_IMAGE_PATTERN = re.compile(
    r"^(?P<item>\d+)_(?P<angle>\d+)_(?P<arrangement>[sm])_(?P<index>\d+)\.jpg$",
    re.IGNORECASE,
)
AIHUB_PRODUCT_DATASET_URL = (
    "https://aihub.or.kr/aihubdata/data/view.do?"
    "aihubDataSe=realm&currMenu=&dataSetSn=64&topMenu="
)

PRODUCT_DEFAULTS = {
    "10060": (["블루베리 풍미", "스틱형 과자"], "달콤한 간식을 찾는 20대"),
    "10091": (["고소한 맛", "바삭한 식감"], "익숙한 간식을 즐기는 전 연령"),
    "10092": (["짭짤한 풍미", "오징어 모양 스낵"], "짭짤한 간식을 찾는 소비자"),
    "10093": (["매콤한 풍미", "바삭한 새우 스낵"], "매운 간식을 즐기는 성인"),
    "10094": (["초콜릿 풍미", "바삭한 콘 스낵"], "달콤한 간식을 찾는 청소년과 성인"),
    "10095": (["바나나 풍미", "가벼운 식감"], "달콤한 스낵을 찾는 가족"),
    "10100": (["용기형 포장", "껌 제품"], "휴대하기 편한 간식을 찾는 소비자"),
}


def _relative_path(path: Path, project_root: Path | None) -> str:
    if project_root:
        try:
            return str(path.relative_to(project_root))
        except ValueError:
            pass
    return str(path)


def _xml_root(raw: bytes) -> ElementTree.Element:
    return ElementTree.fromstring(_decode_xml(raw))


def _xml_text(root: ElementTree.Element, path: str, default: str = "") -> str:
    node = root.find(path)
    return (node.text or "").strip() if node is not None else default


def _objects(root: ElementTree.Element) -> list[dict[str, Any]]:
    objects = []
    for node in root.findall("./object"):
        bbox = node.find("./bndbox")
        if bbox is None:
            continue
        objects.append(
            {
                "label": _xml_text(node, "./name"),
                "bbox": {
                    name: int(_xml_text(bbox, f"./{name}", "0"))
                    for name in ("xmin", "ymin", "xmax", "ymax")
                },
            }
        )
    return objects


def _product_metadata(root: ElementTree.Element) -> dict[str, Any]:
    return {
        "product_name": _xml_text(root, "./div_cd/img_prod_nm"),
        "category": {
            "large": _xml_text(root, "./div_cd/div_l"),
            "medium": _xml_text(root, "./div_cd/div_m"),
            "small": _xml_text(root, "./div_cd/div_s"),
            "normalized": _xml_text(root, "./div_cd/div_n"),
        },
        "manufacturer": _xml_text(root, "./div_cd/comp_nm"),
        "volume": _xml_text(root, "./div_cd/volume"),
        "barcode": _xml_text(root, "./div_cd/barcd"),
        "item_code": _xml_text(root, "./div_cd/item_cd"),
        "package_dimensions_raw": {
            name: _xml_text(root, f"./div_cd/{name}")
            for name in ("width", "length", "height")
        },
        "nutrition_info_raw": _xml_text(root, "./div_cd/nutrition_info"),
        "copyright": _xml_text(root, "./identifier/copyright"),
    }


def _bbox_is_valid(bbox: dict[str, int], width: int, height: int) -> bool:
    return (
        0 <= bbox["xmin"] < bbox["xmax"] <= width
        and 0 <= bbox["ymin"] < bbox["ymax"] <= height
    )


def prepare_aihub_sample_master(
    zip_path: Path,
    output_dir: Path,
    project_root: Path | None = None,
    expected_images: int | None = 798,
) -> dict[str, Any]:
    """Build a catalog from AI Hub dataset 64 lightweight sample files.

    The generated data remains explicitly marked as sample data. It is a source
    catalog for internal evaluation, not a train/validation/test split.
    """
    if not zip_path.is_file():
        raise FileNotFoundError(zip_path)

    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    products: dict[str, dict[str, Any]] = {}
    missing_annotations: list[str] = []
    missing_metadata: list[str] = []
    image_decode_failures: list[str] = []
    dimension_mismatches: list[str] = []
    invalid_bboxes: list[dict[str, Any]] = []
    record_ids: list[str] = []

    with zipfile.ZipFile(zip_path) as archive:
        by_basename = {PurePosixPath(info.filename).name: info for info in archive.infolist()}
        images = sorted(
            (
                info
                for info in archive.infolist()
                if MASTER_IMAGE_PATTERN.match(PurePosixPath(info.filename).name)
            ),
            key=lambda info: PurePosixPath(info.filename).name,
        )
        for image_info in images:
            filename = PurePosixPath(image_info.filename).name
            match = MASTER_IMAGE_PATTERN.match(filename)
            if match is None:  # pragma: no cover - guarded by the filter
                continue
            stem = PurePosixPath(filename).stem
            item = match.group("item")
            annotation_info = by_basename.get(f"{stem}.xml")
            metadata_info = by_basename.get(f"{stem}_meta.xml")
            if annotation_info is None:
                missing_annotations.append(stem)
                continue
            if metadata_info is None:
                missing_metadata.append(stem)
                continue

            image_bytes = archive.read(image_info)
            annotation_root = _xml_root(archive.read(annotation_info))
            metadata_root = _xml_root(archive.read(metadata_info))
            metadata = _product_metadata(metadata_root)
            width = int(_xml_text(annotation_root, "./size/width", "0"))
            height = int(_xml_text(annotation_root, "./size/height", "0"))
            depth = int(_xml_text(annotation_root, "./size/depth", "0"))
            try:
                with Image.open(BytesIO(image_bytes)) as image:
                    actual_width, actual_height = image.size
                    image.verify()
            except Exception as error:  # Pillow raises several decode exception types
                image_decode_failures.append(f"{stem}: {type(error).__name__}")
                actual_width, actual_height = 0, 0
            if (width, height) != (actual_width, actual_height):
                dimension_mismatches.append(stem)

            objects = _objects(annotation_root)
            for object_index, item_object in enumerate(objects):
                if not _bbox_is_valid(item_object["bbox"], width, height):
                    invalid_bboxes.append(
                        {
                            "record_id": stem,
                            "object_index": object_index,
                            "bbox": item_object["bbox"],
                        }
                    )

            destination = image_dir / item / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(image_bytes)
            arrangement_code = match.group("arrangement").lower()
            record = {
                "record_id": stem,
                "dataset_role": "sample_source_catalog",
                "product_id": item,
                **metadata,
                "shot": {
                    "angle_degrees": int(match.group("angle")),
                    "arrangement": (
                        "single" if arrangement_code == "s" else "multiple"
                    ),
                    "arrangement_code": arrangement_code,
                    "sequence": int(match.group("index")),
                },
                "image": {
                    "path": _relative_path(destination, project_root),
                    "width": actual_width,
                    "height": actual_height,
                    "depth": depth,
                    "file_size_bytes": len(image_bytes),
                    "sha256": hashlib.sha256(image_bytes).hexdigest(),
                },
                "objects": objects,
                "source": {
                    "provider": "AI Hub",
                    "dataset_id": 64,
                    "dataset_url": AIHUB_PRODUCT_DATASET_URL,
                    "archive_entry": image_info.filename,
                    "annotation_entry": annotation_info.filename,
                    "metadata_entry": metadata_info.filename,
                    "is_lightweight_sample": True,
                    "usage": "internal_evaluation_only",
                    "redistribution": "not_verified",
                },
            }
            records.append(record)
            record_ids.append(stem)
            products.setdefault(
                item,
                {
                    "product_id": item,
                    **metadata,
                    "source": {
                        "provider": "AI Hub",
                        "dataset_id": 64,
                        "is_lightweight_sample": True,
                    },
                },
            )

    duplicate_record_ids = sorted(
        record_id for record_id, count in Counter(record_ids).items() if count > 1
    )
    shot_counts = Counter(
        (
            str(record["shot"]["angle_degrees"]),
            str(record["shot"]["arrangement_code"]),
        )
        for record in records
    )
    product_counts = Counter(str(record["product_id"]) for record in records)
    qa_report = {
        "dataset_name": "sample_product_master_v1",
        "is_lightweight_sample": True,
        "expected_images": expected_images,
        "record_count": len(records),
        "product_count": len(products),
        "missing_annotations": missing_annotations,
        "missing_metadata": missing_metadata,
        "image_decode_failures": image_decode_failures,
        "dimension_mismatches": dimension_mismatches,
        "invalid_bboxes": invalid_bboxes,
        "duplicate_record_ids": duplicate_record_ids,
        "counts_by_product": dict(sorted(product_counts.items())),
        "counts_by_shot": {
            f"{angle}_{arrangement}": count
            for (angle, arrangement), count in sorted(shot_counts.items())
        },
    }
    qa_report["passed"] = (
        (expected_images is None or len(records) == expected_images)
        and not missing_annotations
        and not missing_metadata
        and not image_decode_failures
        and not dimension_mismatches
        and not invalid_bboxes
        and not duplicate_record_ids
    )

    records_path = output_dir / "records.jsonl"
    records_path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    candidates = [
        record for record in records if record["shot"]["arrangement_code"] == "s"
    ]
    (output_dir / "eval_candidates.jsonl").write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in candidates
        ),
        encoding="utf-8",
    )
    (output_dir / "products.json").write_text(
        json.dumps(list(products.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "qa_report.json").write_text(
        json.dumps(qa_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "DATA_CARD.md").write_text(
        "# sample_product_master_v1\n\n"
        "- 출처: AI Hub 데이터셋 64 상품 이미지 데이터의 경량 샘플\n"
        f"- 구성: 상품 {len(products)}종, 이미지 {len(records)}장\n"
        "- 용도: 내부 베이스라인 평가와 전처리 검증\n"
        "- 제한: 전체 데이터가 아니며 train/validation/test 분할이 아니다.\n"
        "- 재배포: 이용 조건 확인 전 금지\n"
        "- 영양 정보: 원문 문자열을 보존하며 광고 사실로 자동 사용하지 않는다.\n",
        encoding="utf-8",
    )
    return qa_report


def _decode_xml(raw: bytes) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _tag(text: str, name: str, default: str = "") -> str:
    match = re.search(rf"<{name}>(.*?)</{name}>", text, re.DOTALL)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else default


def _bbox(text: str) -> BoundingBox | None:
    values = {name: _tag(text, name) for name in ("xmin", "ymin", "xmax", "ymax")}
    if not all(values.values()):
        return None
    return BoundingBox(**{name: int(value) for name, value in values.items()})


def _select_images(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    grouped: dict[str, list[tuple[int, zipfile.ZipInfo]]] = {}
    for info in archive.infolist():
        name = PurePosixPath(info.filename).name
        match = IMAGE_PATTERN.match(name)
        if match:
            grouped.setdefault(match.group("item"), []).append((int(match.group("index")), info))
    selected: dict[str, zipfile.ZipInfo] = {}
    for item, candidates in grouped.items():
        selected[item] = min(candidates, key=lambda pair: (pair[0] != 1, pair[0]))[1]
    return selected


def prepare_aihub_eval_set(
    zip_path: Path,
    output_dir: Path,
    project_root: Path | None = None,
) -> list[GenerationRequest]:
    if not zip_path.is_file():
        raise FileNotFoundError(zip_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / "images"
    request_dir = output_dir / "requests"
    image_dir.mkdir(exist_ok=True)
    request_dir.mkdir(exist_ok=True)
    requests: list[GenerationRequest] = []
    with zipfile.ZipFile(zip_path) as archive:
        infos_by_basename = {PurePosixPath(info.filename).name: info for info in archive.infolist()}
        selected = _select_images(archive)
        if len(selected) != 7:
            raise ValueError(f"expected 7 products, found {len(selected)}")
        for sequence, item in enumerate(sorted(selected), start=1):
            image_info = selected[item]
            source_name = PurePosixPath(image_info.filename).name
            stem = Path(source_name).stem
            annotation_info = infos_by_basename.get(f"{stem}.xml")
            metadata_info = infos_by_basename.get(f"{stem}_meta.xml")
            annotation = _decode_xml(archive.read(annotation_info)) if annotation_info else ""
            metadata = _decode_xml(archive.read(metadata_info)) if metadata_info else ""
            product_name = _tag(metadata, "img_prod_nm") or _tag(annotation, "name") or item
            category = "/".join(
                part for part in (_tag(metadata, "div_l"), _tag(metadata, "div_m")) if part
            ) or "식품/과자"
            destination = image_dir / f"snack_{sequence:03d}.jpg"
            destination.write_bytes(archive.read(image_info))
            features, audience = PRODUCT_DEFAULTS.get(
                item,
                ([category, "국내 상품 이미지"], "상품 정보를 찾는 소비자"),
            )
            if project_root:
                try:
                    image_path = str(destination.relative_to(project_root))
                except ValueError:
                    image_path = str(destination)
            else:
                image_path = str(destination)
            request = GenerationRequest(
                request_id=f"snack_{sequence:03d}",
                text=(
                    f"{product_name}. 카테고리: {category}. "
                    f"특징: {', '.join(features)}"
                ),
                image_path=image_path,
                image_bbox=_bbox(annotation),
                outputs=[
                    OutputType.COPY,
                    OutputType.BANNER,
                    OutputType.DETAIL_VISUAL,
                    OutputType.PRODUCT_IMAGE,
                ],
                options=GenerationOptions(
                    target_audience=audience,
                    tone="밝고 친근함",
                ),
                source={
                    "dataset": "AI Hub 상품 이미지 데이터 샘플",
                    "item_id": item,
                    "archive_entry": image_info.filename,
                    "usage": "internal_evaluation_only",
                    "redistribution": "not_verified",
                },
            )
            requests.append(request)
            (request_dir / f"{request.request_id}.json").write_text(
                request.model_dump_json(indent=2),
                encoding="utf-8",
            )
    (output_dir / "requests.json").write_text(
        json.dumps(
            [item.model_dump(mode="json") for item in requests],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "DATA_USE.md").write_text(
        "# eval_v1\n\n"
        "AI Hub 상품 이미지 샘플에서 상품 7종의 정면 단품 이미지를 한 장씩 선택했다.\n"
        "이 자료는 내부 파이프라인 평가 전용이며, 이용 조건 확인 전 재배포하거나 "
        "파인튜닝에 사용하지 않는다.\n",
        encoding="utf-8",
    )
    return requests
