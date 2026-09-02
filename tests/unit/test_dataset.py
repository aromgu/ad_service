import io
import json
import zipfile

from PIL import Image

from ad_service.data.dataset import prepare_aihub_eval_set, prepare_aihub_sample_master


def _jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (128, 128), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_prepare_eval_set_selects_seven_products(tmp_path) -> None:
    archive_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for item in range(10001, 10008):
            stem = f"{item}_0_s_1"
            archive.writestr(f"root/{item}/{stem}.jpg", _jpeg_bytes())
            archive.writestr(
                f"root/{item}/{stem}.xml",
                "<annotation><object><name>상품</name><bndbox>"
                "<xmin>10</xmin><ymin>10</ymin><xmax>118</xmax><ymax>118</ymax>"
                "</bndbox></object></annotation>",
            )
            archive.writestr(
                f"root/{item}/{stem}_meta.xml",
                f"<comp_cd><div_l>과자</div_l><div_m>스낵</div_m>"
                f"<img_prod_nm>상품{item}</img_prod_nm></comp_cd>",
            )
    output = tmp_path / "eval_v1"
    requests = prepare_aihub_eval_set(archive_path, output, tmp_path)
    assert len(requests) == 7
    assert all(request.product_bbox is not None for request in requests)
    manifest = json.loads((output / "requests.json").read_text(encoding="utf-8"))
    assert len(manifest) == 7
    assert (output / "images/snack_001.jpg").is_file()


def test_prepare_sample_master_builds_catalog_and_qa_report(tmp_path) -> None:
    archive_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for item, arrangement in (("10001", "s"), ("10002", "m")):
            stem = f"{item}_30_{arrangement}_1"
            archive.writestr(f"원천데이터/{item}/{stem}.jpg", _jpeg_bytes())
            archive.writestr(
                f"라벨링데이터/{item}/{stem}.xml",
                "<annotation><size><width>128</width><height>128</height>"
                "<depth>3</depth></size><object><name>상품</name><bndbox>"
                "<xmin>10</xmin><ymin>10</ymin><xmax>118</xmax><ymax>118</ymax>"
                "</bndbox></object></annotation>",
            )
            archive.writestr(
                f"라벨링데이터/{item}/{stem}_meta.xml",
                "<comp_cd><identifier><copyright>제공자</copyright></identifier>"
                f"<div_cd><item_cd>code-{item}</item_cd><item_no>{item}</item_no>"
                "<div_l>과자</div_l><div_m>스낵</div_m><div_s>봉지과자</div_s>"
                "<div_n>봉지과자</div_n><comp_nm>제조사</comp_nm>"
                f"<img_prod_nm>상품{item}</img_prod_nm><volume>10G</volume>"
                "<barcd>123</barcd><width>1</width><length>2</length>"
                "<height>3</height><nutrition_info>{}</nutrition_info>"
                "</div_cd></comp_cd>",
            )

    output = tmp_path / "sample_product_master_v1"
    report = prepare_aihub_sample_master(
        archive_path,
        output,
        tmp_path,
        expected_images=2,
    )

    assert report["passed"] is True
    assert report["record_count"] == 2
    assert report["product_count"] == 2
    records = [
        json.loads(line)
        for line in (output / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["source"]["is_lightweight_sample"] is True
    assert records[0]["shot"]["angle_degrees"] == 30
    assert len(records[0]["image"]["sha256"]) == 64
    assert sum(1 for _ in (output / "eval_candidates.jsonl").open()) == 1
