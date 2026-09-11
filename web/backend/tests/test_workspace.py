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
    assert sample_form["product_name"] in doc["sections"][0]["content"]["text"]

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
    made = []
    for name in ("첫 번째", "두 번째"):
        job = _wait(client, client.post("/api/jobs", json={
            "type": "detail_page", "form": {**sample_form, "product_name": name},
            "image_ids": ids}).json()["id"])
        made.append(job["id"])
    order = [i["job_id"] for i in client.get("/api/workspace").json()]
    assert order.index(made[1]) < order.index(made[0]), "최근 것이 위에 와야 한다"


# ---------------- 카드 제목 (내 작업 5a) ----------------
def test_default_titles_are_numbered_per_type(client, png_bytes, sample_form):
    # 테스트끼리 DB 를 같이 쓰므로 '1번'이 남아 있다고 가정하지 않는다.
    # (예: 스토어에 등록된 상품등록 1 은 내 작업에서 빠진다) 이 테스트가 만든 작업만 본다.
    ids = _upload(client, png_bytes, 1)
    detail_jobs = [
        _wait(client, client.post("/api/jobs", json={
            "type": "detail_page", "form": sample_form, "image_ids": ids}).json()["id"])["id"]
        for _ in range(2)
    ]
    blog_job = _wait(client, client.post("/api/jobs", json={
        "type": "blog", "form": {"topic": "제목 확인", "style": "기본 블로그"},
        "image_ids": ids}).json()["id"])["id"]
    product_job = _wait(client, client.post("/api/jobs", json={
        "type": "product_reg", "form": {"submit_mode": "auto"}, "image_ids": ids}).json()["id"])["id"]

    titles = {i["job_id"]: i["title"] for i in client.get("/api/workspace").json()}

    def label_and_number(job_id: str) -> tuple[str, int]:
        label, _, n = titles[job_id].rpartition(" ")
        assert n.isdigit(), titles[job_id]
        return label, int(n)

    (first_label, first_n), (second_label, second_n) = map(label_and_number, detail_jobs)
    assert first_label == second_label == "상세페이지"
    assert second_n == first_n + 1, "같은 타입 안에서 순번이 1씩 올라간다"
    assert label_and_number(blog_job)[0] == "블로그"
    assert label_and_number(product_job)[0] == "상품등록"


def test_titles_are_editable(client, png_bytes, sample_form):
    ids = _upload(client, png_bytes, 1)
    doc_job = _wait(client, client.post("/api/jobs", json={
        "type": "detail_page", "form": sample_form, "image_ids": ids}).json()["id"])
    reg_job = _wait(client, client.post("/api/jobs", json={
        "type": "product_reg", "form": {"submit_mode": "auto"}, "image_ids": ids}).json()["id"])

    client.patch(f"/api/documents/{doc_job['document_id']}", json={"title": "내가 고친 이름"})
    client.patch(f"/api/product-drafts/{reg_job['product_draft_id']}", json={"title": "등록건 A"})

    titles = {i["title"] for i in client.get("/api/workspace").json()}
    assert "내가 고친 이름" in titles and "등록건 A" in titles


def test_product_title_is_separate_from_product_name(client, png_bytes):
    """카드 제목을 바꿔도 실제 상품명은 그대로여야 한다."""
    ids = _upload(client, png_bytes, 1)
    job = _wait(client, client.post("/api/jobs", json={
        "type": "product_reg", "form": {"submit_mode": "review"}, "image_ids": ids}).json()["id"])
    before = client.get(f"/api/product-drafts/{job['product_draft_id']}").json()["product_name"]
    after = client.patch(f"/api/product-drafts/{job['product_draft_id']}",
                         json={"title": "카드 이름만 변경"}).json()
    assert after["title"] == "카드 이름만 변경"
    assert after["product_name"] == before


# ---------------- 채팅으로 이미지 첨부 (에디터 10번) ----------------
def test_chat_image_is_inserted_into_document(client, png_bytes, sample_form):
    ids = _upload(client, png_bytes, 1)
    job = _wait(client, client.post("/api/jobs", json={
        "type": "detail_page", "form": sample_form, "image_ids": ids}).json()["id"])
    doc_id = job["document_id"]
    before = len([s for s in client.get(f"/api/documents/{doc_id}").json()["sections"]
                  if s["type"] == "image"])

    new_ids = _upload(client, png_bytes, 2)
    res = client.post(f"/api/documents/{doc_id}/chat",
                      json={"message": "이 사진들 넣어줘", "image_ids": new_ids}).json()

    sections = res["document"]["sections"]
    after = [s for s in sections if s["type"] == "image"]
    assert len(after) == before + 2
    # note 블록(문서 끝 안내) 앞에 들어가야 한다
    assert sections[-1]["type"] == "note"
    # 사용자 메시지에 첨부 기록이 남는다
    assert len(res["messages"][0]["meta"]["images"]) == 2


def test_chat_rejects_unknown_image(client, png_bytes, sample_form):
    ids = _upload(client, png_bytes, 1)
    job = _wait(client, client.post("/api/jobs", json={
        "type": "detail_page", "form": sample_form, "image_ids": ids}).json()["id"])
    r = client.post(f"/api/documents/{job['document_id']}/chat",
                    json={"message": "x", "image_ids": ["nope"]})
    assert r.status_code == 400
