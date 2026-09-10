import time


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


def test_retry_creates_new_job_with_same_input(client, png_bytes, sample_form):
    ids = _upload(client, png_bytes, 2)
    first = _wait(client, client.post("/api/jobs", json={
        "type": "detail_page", "form": sample_form, "image_ids": ids}).json()["id"])

    r = client.post(f"/api/jobs/{first['id']}/retry")
    assert r.status_code == 201
    again = r.json()
    assert again["id"] != first["id"], "원본은 그대로 두고 새 작업을 만들어야 한다"
    assert again["type"] == "detail_page"

    done = _wait(client, again["id"])
    assert done["status"] == "done"

    # 같은 입력값으로 같은 결과가 나온다
    doc = client.get(f"/api/documents/{done['document_id']}").json()
    assert sample_form["product_name"] in doc["title"]

    # 원본 작업도 목록에 남아 있다
    ws = client.get("/api/workspace").json()
    assert {i["job_id"] for i in ws} >= {first["id"], again["id"]}


def test_retry_reuses_source_document_for_handoff(client, png_bytes, sample_form):
    """상세페이지에서 인계된 상품등록도 재시도할 수 있어야 한다."""
    ids = _upload(client, png_bytes, 1)
    detail = _wait(client, client.post("/api/jobs", json={
        "type": "detail_page", "form": sample_form, "image_ids": ids}).json()["id"])

    handoff = _wait(client, client.post("/api/jobs", json={
        "type": "product_reg", "form": {"submit_mode": "auto"},
        "image_ids": [], "from_document_id": detail["document_id"]}).json()["id"])

    again = client.post(f"/api/jobs/{handoff['id']}/retry").json()
    done = _wait(client, again["id"])
    assert done["status"] == "done"
    draft = client.get(f"/api/product-drafts/{done['product_draft_id']}").json()
    assert draft["image_urls"], "출처 문서에서 이미지를 다시 끌어와야 한다"


def test_retry_unknown_job(client):
    assert client.post("/api/jobs/nope/retry").status_code == 404


def test_workspace_delete_removes_only_that_item(client, png_bytes, sample_form):
    ids = _upload(client, png_bytes, 1)
    a = _wait(client, client.post("/api/jobs", json={
        "type": "detail_page", "form": sample_form, "image_ids": ids}).json()["id"])
    b = _wait(client, client.post("/api/jobs", json={
        "type": "blog", "form": {"topic": "남아야 하는 것", "style": "기본 블로그"},
        "image_ids": ids}).json()["id"])

    before = len(client.get("/api/workspace").json())
    assert client.delete(f"/api/workspace/{a['id']}").status_code == 204
    after = client.get("/api/workspace").json()
    assert len(after) == before - 1
    assert any(i["job_id"] == b["id"] for i in after)
    assert client.get(f"/api/documents/{a['document_id']}").status_code == 404


def test_workspace_item_shape_for_cards(client, png_bytes, sample_form):
    """카드가 그리는 데 필요한 필드가 다 내려오는지."""
    ids = _upload(client, png_bytes, 1)
    job = _wait(client, client.post("/api/jobs", json={
        "type": "detail_page", "form": sample_form, "image_ids": ids}).json()["id"])
    item = next(i for i in client.get("/api/workspace").json() if i["job_id"] == job["id"])
    for key in ("id", "job_id", "type", "status", "progress", "title",
                "thumbnail_url", "created_at", "document_id", "product_draft_id"):
        assert key in item, key
    assert item["thumbnail_url"], "완료된 작업은 썸네일이 있어야 한다"


def test_workspace_newest_first(client, png_bytes, sample_form):
    ids = _upload(client, png_bytes, 1)
    for name in ("첫 번째", "두 번째"):
        _wait(client, client.post("/api/jobs", json={
            "type": "detail_page", "form": {**sample_form, "product_name": name},
            "image_ids": ids}).json()["id"])
    titles = [i["title"] for i in client.get("/api/workspace").json()]
    assert titles.index("두 번째 상세페이지") < titles.index("첫 번째 상세페이지")
