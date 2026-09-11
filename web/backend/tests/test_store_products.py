"""등록된 상품 관리 — 스마트스토어 목록·불러오기·수정·삭제.

네이버는 conftest 의 가짜 클라이언트(fake_naver)로 대신한다.
"""

import copy
import time

REP = "https://shop-phinf.pstatic.net/rep.jpg"
OPT = "https://shop-phinf.pstatic.net/opt.jpg"

# 원상품 조회 응답. 화면이 다루지 않는 값(고시·A/S·pageTitle)도 섞어 둔다.
SAMPLE = {
    "originProduct": {
        "statusType": "SALE",
        "saleType": "NEW",
        "leafCategoryId": "50000439",
        "name": "시카마누 바이옴 세럼 30ml",
        "detailContent": "<div><p>피부 장벽을 세우는 세럼</p><img src='https://shop-phinf.pstatic.net/d.jpg'></div>",
        "images": {"representativeImage": {"url": REP}, "optionalImages": [{"url": OPT}]},
        "salePrice": 25000,
        "stockQuantity": 10,
        "deliveryInfo": {
            "deliveryType": "DELIVERY",
            "deliveryFee": {"deliveryFeeType": "PAID", "baseFee": 3000, "deliveryFeePayType": "PREPAID"},
        },
        "detailAttribute": {
            "naverShoppingSearchInfo": {"brandName": "Parnell"},
            "seoInfo": {"sellerTags": [{"text": "세럼"}], "pageTitle": "유지돼야 하는 값"},
            "productInfoProvidedNotice": {"productInfoProvidedNoticeType": "COSMETIC", "cosmetic": {"capacity": "30ml"}},
            "afterServiceInfo": {"afterServiceTelephoneNumber": "010-0000-0000"},
        },
    },
    "smartstoreChannelProduct": {
        "channelProductNo": 777,
        "naverShoppingRegistration": False,
        "channelProductDisplayStatusType": "ON",
    },
}

SEARCH_RESULT = {
    "contents": [{
        "originProductNo": 901,
        "channelProducts": [{
            "channelProductNo": 777,
            "channelServiceType": "STOREFARM",
            "name": "시카마누 바이옴 세럼 30ml",
            "statusType": "SALE",
            "salePrice": 25000,
            "stockQuantity": 10,
            "representativeImage": {"url": REP},
            "wholeCategoryName": "화장품/미용>스킨케어>에센스/세럼/앰플",
            "regDate": "2026-09-11T14:00:00.000+09:00",
            "modifiedDate": "2026-09-11T15:00:00.000+09:00",
        }],
    }],
    "page": 1, "size": 20, "totalElements": 1, "totalPages": 1,
}


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


def _open(client, fake_naver, no: str) -> dict:
    fake_naver.products[no] = copy.deepcopy(SAMPLE)
    r = client.post(f"/api/store-products/{no}/open")
    assert r.status_code == 200, r.json()
    return r.json()


def _review_draft(client, png_bytes) -> tuple[dict, str]:
    ids = _upload(client, png_bytes, 1)
    job = _wait(client, client.post("/api/jobs", json={
        "type": "product_reg", "form": {"submit_mode": "review"}, "image_ids": ids}).json()["id"])
    return job, job["product_draft_id"]


# ---------------- 목록 ----------------
def test_list_needs_naver_keys(client):
    r = client.get("/api/store-products")
    assert r.status_code == 503
    assert "NAVER_CLIENT_ID" in r.json()["detail"]


def test_list_comes_from_commerce_api(client, fake_naver):
    fake_naver.search_result = copy.deepcopy(SEARCH_RESULT)
    body = client.get("/api/store-products").json()
    assert body["total"] == 1 and body["total_pages"] == 1 and body["page"] == 1
    assert body["items"] == [{
        "origin_product_no": "901",
        "channel_product_no": "777",
        "name": "시카마누 바이옴 세럼 30ml",
        "status_type": "SALE",
        "sale_price": 25000,
        "stock_quantity": 10,
        "image_url": REP,
        "category_name": "화장품/미용 › 스킨케어 › 에센스/세럼/앰플",
        "registered_at": "2026-09-11T14:00:00.000+09:00",
        "modified_at": "2026-09-11T15:00:00.000+09:00",
    }]


# ---------------- 불러오기 ----------------
def test_open_imports_product_and_reuses_the_draft(client, fake_naver):
    draft = _open(client, fake_naver, "902")
    assert draft["status"] == "registered"
    assert draft["naver_origin_product_no"] == "902"
    assert draft["naver_channel_product_no"] == "777"
    assert draft["product_name"] == "시카마누 바이옴 세럼 30ml"
    assert (draft["price"], draft["stock"], draft["shipping_fee"]) == (25000, 10, 3000)
    assert draft["image_urls"] == [REP, OPT] and draft["representative_image_url"] == REP
    assert draft["brand"] == "Parnell" and draft["tags"] == ["세럼"]
    assert draft["selected_category_id"] == "50000439"
    assert draft["selected_category"] == "화장품/미용 › 스킨케어 › 에센스/세럼/앰플"
    assert draft["description"] == "피부 장벽을 세우는 세럼"

    again = client.post("/api/store-products/902/open").json()
    assert again["id"] == draft["id"], "같은 상품을 다시 열면 초안을 새로 만들지 않는다"


def test_open_unknown_product(client, fake_naver):
    assert client.post("/api/store-products/555/open").status_code == 404
    assert client.post("/api/store-products/abc/open").status_code == 422


# ---------------- 수정 ----------------
def test_update_changes_only_what_the_screen_manages(client, fake_naver):
    draft = _open(client, fake_naver, "903")
    client.patch(f"/api/product-drafts/{draft['id']}", json={
        "price": 19900, "product_name": "시카마누 세럼 새 이름", "tags": ["보습"]})

    r = client.post(f"/api/product-drafts/{draft['id']}/update")
    assert r.status_code == 200, r.json()

    no, payload = fake_naver.updated[-1]
    origin = payload["originProduct"]
    attr = origin["detailAttribute"]
    assert no == "903"
    assert origin["salePrice"] == 19900 and origin["name"] == "시카마누 세럼 새 이름"
    assert attr["seoInfo"] == {"sellerTags": [{"text": "보습"}], "pageTitle": "유지돼야 하는 값"}
    # 화면이 다루지 않는 정보는 조회한 그대로 다시 보낸다 — 빠지면 네이버에서 지워진다
    sample_attr = SAMPLE["originProduct"]["detailAttribute"]
    assert attr["productInfoProvidedNotice"] == sample_attr["productInfoProvidedNotice"]
    assert attr["afterServiceInfo"] == sample_attr["afterServiceInfo"]
    assert origin["deliveryInfo"] == SAMPLE["originProduct"]["deliveryInfo"]
    assert payload["smartstoreChannelProduct"] == SAMPLE["smartstoreChannelProduct"]
    assert origin["images"] == SAMPLE["originProduct"]["images"]
    assert origin["detailContent"] == SAMPLE["originProduct"]["detailContent"], \
        "설명을 안 고쳤으면 스토어의 상세 HTML 을 그대로 둔다"

    # 설명을 고치면 상세 HTML 도 새로 만든다
    client.patch(f"/api/product-drafts/{draft['id']}", json={"description": "새 설명"})
    assert client.post(f"/api/product-drafts/{draft['id']}/update").status_code == 200
    assert fake_naver.updated[-1][1]["originProduct"]["detailContent"] == "<div><p>새 설명</p></div>"


def test_update_needs_a_registered_product(client, png_bytes, fake_naver):
    _, draft_id = _review_draft(client, png_bytes)
    assert client.post(f"/api/product-drafts/{draft_id}/update").status_code == 409


def test_update_product_deleted_on_naver(client, fake_naver):
    draft = _open(client, fake_naver, "904")
    fake_naver.products.clear()
    r = client.post(f"/api/product-drafts/{draft['id']}/update")
    assert r.status_code == 404
    assert "삭제" in r.json()["detail"]


# ---------------- 내 작업 · 중복 등록 ----------------
def test_registered_product_leaves_workspace_and_cannot_register_twice(client, png_bytes, fake_naver):
    job, draft_id = _review_draft(client, png_bytes)

    def in_workspace() -> bool:
        return any(i["job_id"] == job["id"] for i in client.get("/api/workspace").json())

    assert in_workspace(), "등록 전 초안은 내 작업에 있어야 한다"
    client.patch(f"/api/product-drafts/{draft_id}", json={
        "price": 19900, "selected_category": "화장품/미용 › 스킨케어 › 에센스/세럼/앰플",
        "selected_category_id": "50000439"})
    assert client.post(f"/api/product-drafts/{draft_id}/register").status_code == 200
    assert not in_workspace(), "스토어에 올라간 상품은 내 작업에서 빠진다"

    again = client.post(f"/api/product-drafts/{draft_id}/register")
    assert again.status_code == 409, "다시 등록하면 스토어에 같은 상품이 하나 더 생긴다"


# ---------------- 삭제 ----------------
def test_delete_removes_product_from_store_and_locally(client, fake_naver):
    draft = _open(client, fake_naver, "905")
    assert client.delete(f"/api/product-drafts/{draft['id']}").status_code == 204
    assert fake_naver.deleted == ["905"]
    assert client.get(f"/api/product-drafts/{draft['id']}").status_code == 404


def test_delete_when_already_gone_on_naver(client, fake_naver):
    draft = _open(client, fake_naver, "906")
    fake_naver.products.clear()
    assert client.delete(f"/api/product-drafts/{draft['id']}").status_code == 204
    assert client.get(f"/api/product-drafts/{draft['id']}").status_code == 404


def test_delete_unregistered_draft_is_conflict(client, png_bytes, fake_naver):
    _, draft_id = _review_draft(client, png_bytes)
    assert client.delete(f"/api/product-drafts/{draft_id}").status_code == 409
    assert client.get(f"/api/product-drafts/{draft_id}").status_code == 200
    assert fake_naver.deleted == []
