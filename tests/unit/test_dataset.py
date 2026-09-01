import io
import json
import zipfile

from PIL import Image

from ad_service.data.dataset import prepare_aihub_eval_set


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
