from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path, PurePosixPath

from ad_service.api.schemas.generation import BoundingBox, GenerationRequest

IMAGE_PATTERN = re.compile(r"^(?P<item>\d+)_0_s_(?P<index>\d+)\.jpg$", re.IGNORECASE)

PRODUCT_DEFAULTS = {
    "10060": (["블루베리 풍미", "스틱형 과자"], "달콤한 간식을 찾는 20대"),
    "10091": (["고소한 맛", "바삭한 식감"], "익숙한 간식을 즐기는 전 연령"),
    "10092": (["짭짤한 풍미", "오징어 모양 스낵"], "짭짤한 간식을 찾는 소비자"),
    "10093": (["매콤한 풍미", "바삭한 새우 스낵"], "매운 간식을 즐기는 성인"),
    "10094": (["초콜릿 풍미", "바삭한 콘 스낵"], "달콤한 간식을 찾는 청소년과 성인"),
    "10095": (["바나나 풍미", "가벼운 식감"], "달콤한 스낵을 찾는 가족"),
    "10100": (["용기형 포장", "껌 제품"], "휴대하기 편한 간식을 찾는 소비자"),
}


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
                product_name=product_name,
                category=category,
                features=features,
                target_audience=audience,
                tone="밝고 친근함",
                product_image_path=image_path,
                product_bbox=_bbox(annotation),
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
