import time

from app.naver.client import NaverApiError


def _wait(client, job_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.2)
    raise AssertionError("작업이 끝나지 않았습니다")


def _upload(client, png_bytes, n=1):
    files = [("files", (f"{i}.png", png_bytes, "image/png")) for i in range(n)]
    return [a["id"] for a in client.post("/api/uploads", files=files).json()]


# ---------------- 블로그 (3a → 3b → 3c) ----------------
def test_blog_flow(client, png_bytes):
    ids = _upload(client, png_bytes, 3)
    form = {"topic": "캠핑용 접이식 미니 테이블", "style": "기본 블로그",
            "extra_request": "3040 주부 대상, 캠핑 초보 관점으로"}

    job = client.post("/api/jobs", json={"type": "blog", "form": form, "image_ids": ids}).json()
    assert [s["label"] for s in job["steps"]][:2] == ["주제·키워드 분석", "목차 구성"]

    job = _wait(client, job["id"])
    assert job["status"] == "done"

    doc = client.get(f"/api/documents/{job['document_id']}").json()
    assert doc["type"] == "blog"
    assert doc["title"].startswith("블로그 ")
    # 주제는 본문 헤드라인에 들어간다
    assert "캠핑용 접이식 미니 테이블" in " ".join(doc["sections"][1]["content"]["lines"])
    types = [s["type"] for s in doc["sections"]]
    assert "heading" in types and "paragraph" in types

    msgs = client.get(f"/api/documents/{doc['id']}/messages").json()
    # 추가 요청사항이 사용자 메시지로 스레드에 들어간다.
    assert msgs[0]["content"] == form["extra_request"]
    assert msgs[1]["meta"]["footer"] == "초안 1개 생성됨"


def test_blog_rejects_more_than_eight_images(client, png_bytes, sample_form):
    # 업로드 자체가 5장 제한이므로 두 번 나눠 올린 뒤 9장으로 작업을 만든다.
    ids = _upload(client, png_bytes, 5) + _upload(client, png_bytes, 4)
    r = client.post("/api/jobs", json={
        "type": "blog", "form": {"topic": "테스트", "style": "기본 블로그"}, "image_ids": ids})
    assert r.status_code == 400
    assert "8장" in r.json()["detail"]


# ---------------- 상품등록 (4a → 4b → 4c) ----------------
def test_product_review_flow(client, png_bytes, fake_naver):
    """'직접 확인하고 등록' — 4c 를 거쳐야 등록된다."""
    ids = _upload(client, png_bytes, 2)
    form = {"product_info": "구성품 본체 1개 · 소재 캔버스", "submit_mode": "review",
            "shipping": {"origin_address": "서울시 은평구", "shipping_fee": 3000}}

    job = _wait(client, client.post(
        "/api/jobs", json={"type": "product_reg", "form": form, "image_ids": ids}).json()["id"])
    assert job["status"] == "done"
    assert job["document_id"] is None
    assert job["product_draft_id"]

    draft = client.get(f"/api/product-drafts/{job['product_draft_id']}").json()
    assert draft["status"] == "draft", "review 모드는 자동 등록되면 안 된다"
    assert draft["product_name"]
    # 카테고리 후보는 네이버 API 에서 온다. 테스트에선 API 를 끄므로 비어 있고,
    # 사용자가 검토 화면에서 직접 검색해 고르는 흐름이 된다.
    assert draft["category_candidates"] == []
    assert draft["selected_category_id"] == ""
    assert draft["tags"] and draft["attributes"]["주요소재"] == "캔버스"
    # 직접 입력한 정보가 AI 분석보다 우선 적용된다
    assert "구성품 본체 1개" in draft["product_name"] or "구성품 본체 1개" in draft["description"]

    # 카테고리·판매가 없이 등록하면 막힌다
    r = client.post(f"/api/product-drafts/{draft['id']}/register")
    assert r.status_code == 400
    assert "카테고리" in r.json()["detail"] and "판매가" in r.json()["detail"]

    # 검토 화면에서 수정 — 카테고리는 네이버 ID 까지 함께 저장해야 한다
    patched = client.patch(f"/api/product-drafts/{draft['id']}", json={
        "price": 19900, "discount_rate": 10,
        "selected_category": "패션잡화 › 남성가방 › 에코백",
        "selected_category_id": "50015341",
        "options": [{"name": "화이트", "price": 0, "stock": 10}],
        "tags": ["에코백", "캔버스백"],
    }).json()
    assert patched["price"] == 19900
    assert patched["selected_category_id"] == "50015341"
    assert len(patched["options"]) == 1

    registered = client.post(f"/api/product-drafts/{draft['id']}/register").json()
    assert registered["status"] == "registered"
    assert registered["registered_at"]
    assert registered["naver_origin_product_no"] == "123"


def test_product_register_failure_keeps_draft(client, png_bytes, fake_naver):
    """네이버가 거절하거나 상품번호를 주지 않으면 '등록됨'으로 표시하면 안 된다."""
    ids = _upload(client, png_bytes, 1)
    job = _wait(client, client.post("/api/jobs", json={
        "type": "product_reg", "form": {"submit_mode": "review", "price": 19900},
        "image_ids": ids}).json()["id"])
    draft_id = job["product_draft_id"]
    assert client.get(f"/api/product-drafts/{draft_id}").json()["price"] == 19900
    client.patch(f"/api/product-drafts/{draft_id}", json={
        "selected_category": "패션잡화 › 남성가방 › 에코백", "selected_category_id": "50015341"})

    rejections = (
        {"register_error": NaverApiError("상품 등록 실패 (400) 판매가를 확인해 주세요",
                                         status=400, body="{}")},
        # 성공 응답인데 상품번호가 없는 경우
        {"register_error": None, "register_result": {}},
    )
    for change in rejections:
        for key, value in change.items():
            setattr(fake_naver, key, value)
        r = client.post(f"/api/product-drafts/{draft_id}/register")
        assert r.status_code == 502, r.json()
        draft = client.get(f"/api/product-drafts/{draft_id}").json()
        assert draft["status"] == "draft"
        assert draft["naver_origin_product_no"] == ""


def test_product_auto_flow_records_reason_when_naver_unavailable(client, png_bytes):
    """'AI가 알아서 등록하기' — 네이버 등록까지 시도한다.

    테스트엔 네이버 키가 없어 카테고리를 못 찾으므로 등록 전 검사에서 막힌다.
    작업을 실패시키는 대신 초안을 남기고 사유를 적어 사용자가 검토 화면에서 고칠 수 있게 한다.
    """
    ids = _upload(client, png_bytes, 1)
    job = _wait(client, client.post("/api/jobs", json={
        "type": "product_reg",
        "form": {"submit_mode": "auto"},
        "image_ids": ids,
    }).json()["id"])

    assert job["status"] == "done", "등록 실패가 생성 작업을 실패시키면 안 된다"
    assert job["submit_mode"] == "auto"
    draft = client.get(f"/api/product-drafts/{job['product_draft_id']}").json()
    assert draft["status"] == "draft"
    assert "카테고리" in draft["analysis"]["register_error"]


def test_product_from_detail_page(client, png_bytes, sample_form):
    """2c 에디터의 '이 상세페이지로 상품등록' — 문서 이미지를 그대로 이어받는다."""
    ids = _upload(client, png_bytes, 2)
    detail = _wait(client, client.post("/api/jobs", json={
        "type": "detail_page", "form": sample_form, "image_ids": ids}).json()["id"])
    doc = client.get(f"/api/documents/{detail['document_id']}").json()
    doc_image_url = doc["sections"][4]["content"]["url"]

    job = _wait(client, client.post("/api/jobs", json={
        "type": "product_reg",
        "form": {"submit_mode": "auto", "price": 25000},
        "image_ids": [],
        "from_document_id": doc["id"],
    }).json()["id"])

    draft = client.get(f"/api/product-drafts/{job['product_draft_id']}").json()
    assert draft["image_urls"] == [doc_image_url], "상세페이지 이미지를 그대로 이어받아야 한다"
    # '가격 설정'에서 정한 판매가와 상세페이지에 입력한 상품명도 이어받는다
    assert draft["price"] == 25000
    assert sample_form["product_name"] in draft["product_name"], draft["product_name"]


def test_product_from_unknown_document(client):
    r = client.post("/api/jobs", json={
        "type": "product_reg", "form": {"submit_mode": "auto"},
        "image_ids": [], "from_document_id": "nope"})
    assert r.status_code == 404


# ---------------- 배송 설정 ----------------
def test_shipping_settings_roundtrip(client):
    assert client.get("/api/settings/shipping").json()["courier"] == "CJ대한통운"

    saved = client.put("/api/settings/shipping", json={
        "origin_address": "서울시 은평구 은평터널로 15, 108-701",
        "return_same_as_origin": True,
        "shipping_fee": 2500, "return_fee": 3000, "exchange_fee": 6000,
        "cs_phone": "010-8607-8683", "courier": "롯데택배",
    }).json()
    assert saved["shipping_fee"] == 2500

    # 다음 등록에도 그대로 쓰인다
    assert client.get("/api/settings/shipping").json()["courier"] == "롯데택배"


# ---------------- 카테고리 검색 ----------------
def test_category_search_needs_naver_keys(client):
    """카테고리는 네이버 실제 카테고리를 쓴다. 키가 없으면 조용히 비우지 않고 알린다."""
    r = client.get("/api/product-drafts/categories/search?q=에코백")
    assert r.status_code == 503
    assert "NAVER_CLIENT_ID" in r.json()["detail"]


# ---------------- 내 작업 목록에 세 타입이 다 뜬다 ----------------
def test_workspace_includes_all_types(client, png_bytes, sample_form):
    ids = _upload(client, png_bytes, 1)
    for payload in (
        {"type": "detail_page", "form": sample_form, "image_ids": ids},
        {"type": "blog", "form": {"topic": "목록 확인용", "style": "기본 블로그"}, "image_ids": ids},
        {"type": "product_reg", "form": {"submit_mode": "auto"}, "image_ids": ids},
    ):
        _wait(client, client.post("/api/jobs", json=payload).json()["id"])

    items = client.get("/api/workspace").json()
    kinds = {i["type"] for i in items}
    assert {"detail_page", "blog", "product_reg"} <= kinds

    blog_only = client.get("/api/workspace?type=blog").json()
    assert blog_only and all(i["type"] == "blog" for i in blog_only)

    reg = next(i for i in items if i["type"] == "product_reg")
    assert reg["product_draft_id"] and reg["document_id"] is None


# ---------------- AI 사진 편집 팝업 (3a-2) ----------------
def test_ai_edit_returns_requested_count(client, png_bytes):
    src = _upload(client, png_bytes, 1)
    for n in (1, 2, 4):
        out = client.post("/api/uploads/ai-edit", json={
            "prompt": "배경을 밝은 우드 테이블로 바꿔 주세요", "count": n, "source_ids": src}).json()
        assert len(out) == n
        assert all(a["kind"] == "generated" and a["url"].startswith("/static/") for a in out)

    # 결과 이미지는 업로드본과 똑같이 작업에 넣을 수 있어야 한다
    gen_ids = [a["id"] for a in client.post("/api/uploads/ai-edit", json={
        "prompt": "밝게", "count": 2}).json()]
    job = client.post("/api/jobs", json={
        "type": "blog", "form": {"topic": "생성 이미지 사용", "style": "기본 블로그"},
        "image_ids": src + gen_ids}).json()
    assert _wait(client, job["id"])["status"] == "done"


def test_ai_edit_rejects_bad_count(client):
    assert client.post("/api/uploads/ai-edit", json={"prompt": "x", "count": 9}).status_code == 422
    assert client.post("/api/uploads/ai-edit", json={"prompt": "", "count": 2}).status_code == 422


def test_spec_list_is_not_used_as_product_name(client, png_bytes):
    """스펙 나열을 상품 정보에 적어도 그게 상품명이 되면 안 된다."""
    ids = _upload(client, png_bytes, 1)
    job = _wait(client, client.post("/api/jobs", json={
        "type": "product_reg",
        "form": {"product_info": "구성품 본체 1개 · 소재 캔버스 · 사이즈 43×36cm",
                 "submit_mode": "review"},
        "image_ids": ids}).json()["id"])
    draft = client.get(f"/api/product-drafts/{job['product_draft_id']}").json()
    assert "구성품 본체 1개 ·" not in draft["product_name"], draft["product_name"]
    # 설명에는 남아 있어야 한다 (입력을 버리지는 않는다)
    assert "구성품 본체 1개" in draft["description"]


def test_short_name_is_used_as_product_name(client, png_bytes):
    ids = _upload(client, png_bytes, 1)
    job = _wait(client, client.post("/api/jobs", json={
        "type": "product_reg",
        "form": {"product_info": "캠핑용 접이식 미니 테이블", "submit_mode": "review"},
        "image_ids": ids}).json()["id"])
    draft = client.get(f"/api/product-drafts/{job['product_draft_id']}").json()
    assert "캠핑용 접이식 미니 테이블" in draft["product_name"]
