from app.core.korean import eul_reul, eun_neun, has_batchim, i_ga


def test_batchim_detection():
    assert has_batchim("상품명")   # ㅇ 받침
    assert has_batchim("가격")     # ㄱ 받침
    assert not has_batchim("판매가")
    assert not has_batchim("카테고리")
    assert not has_batchim("")


def test_particles():
    assert eul_reul("판매가") == "판매가를"
    assert eul_reul("상품명") == "상품명을"
    assert eul_reul("카테고리") == "카테고리를"
    assert i_ga("상품명") == "상품명이"
    assert i_ga("카테고리") == "카테고리가"
    assert eun_neun("상품명") == "상품명은"
    assert eun_neun("카테고리") == "카테고리는"


def test_register_error_message_reads_naturally(client, png_bytes):
    import time

    asset = client.post("/api/uploads", files={"files": ("a.png", png_bytes, "image/png")}).json()[0]
    job = client.post("/api/jobs", json={
        "type": "product_reg", "form": {"submit_mode": "review"}, "image_ids": [asset["id"]]}).json()
    deadline = time.time() + 20
    while time.time() < deadline:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] == "done":
            break
        time.sleep(0.2)

    detail = client.post(f"/api/product-drafts/{j['product_draft_id']}/register").json()["detail"]
    # 마지막 항목에만 조사가 붙고, 받침에 맞는 '를' 가 쓰인다
    assert detail == "카테고리, 판매가를 먼저 입력해 주세요.", detail
    assert "을(를)" not in detail
