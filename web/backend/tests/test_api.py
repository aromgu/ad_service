import time


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "provider": "mock"}


def test_signup_login_me(client):
    payload = {"email": "hong@example.com", "password": "verysecret1", "name": "홍길동"}
    r = client.post("/api/auth/signup", json=payload)
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]

    # 같은 이메일로 두 번 가입할 수 없다.
    assert client.post("/api/auth/signup", json=payload).status_code == 409

    r = client.post("/api/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert r.status_code == 200

    assert client.post(
        "/api/auth/login", json={"email": payload["email"], "password": "wrong-password"}
    ).status_code == 401

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["name"] == "홍길동"

    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_upload_rejects_unsupported_type(client):
    r = client.post("/api/uploads", files={"files": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 415


def test_upload_rejects_more_than_five(client, png_bytes):
    files = [("files", (f"{i}.png", png_bytes, "image/png")) for i in range(6)]
    assert client.post("/api/uploads", files=files).status_code == 400


def test_job_requires_image(client, sample_form):
    r = client.post("/api/jobs", json={"type": "detail_page", "form": sample_form, "image_ids": []})
    assert r.status_code == 400
    assert "이미지" in r.json()["detail"]


def test_job_rejects_unknown_image_id(client, sample_form):
    r = client.post(
        "/api/jobs",
        json={"type": "detail_page", "form": sample_form, "image_ids": ["does-not-exist"]},
    )
    assert r.status_code == 400


def test_form_validation(client, png_bytes, sample_form):
    asset = client.post("/api/uploads", files={"files": ("a.png", png_bytes, "image/png")}).json()[0]
    bad = {**sample_form, "product_name": ""}
    r = client.post(
        "/api/jobs", json={"type": "detail_page", "form": bad, "image_ids": [asset["id"]]}
    )
    assert r.status_code == 422


def test_full_generation_flow(client, png_bytes, sample_form):
    """업로드 → 작업 생성 → 완료 → 문서 → 채팅 수정 → 목록."""
    assets = client.post(
        "/api/uploads",
        files=[("files", ("a.png", png_bytes, "image/png")), ("files", ("b.png", png_bytes, "image/png"))],
    ).json()
    ids = [a["id"] for a in assets]

    job = client.post(
        "/api/jobs", json={"type": "detail_page", "form": sample_form, "image_ids": ids}
    ).json()
    assert job["status"] in ("queued", "running")
    assert [s["state"] for s in job["steps"]] == ["pending"] * 4

    deadline = time.time() + 20
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job['id']}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.2)

    assert job["status"] == "done", job
    assert job["progress"] == 100.0
    assert all(s["state"] == "done" for s in job["steps"])
    assert job["document_id"]

    doc = client.get(f"/api/documents/{job['document_id']}").json()
    # 카드 제목은 "상세페이지 N" 형식. 상품명은 본문(eyebrow)에 들어간다.
    assert doc["title"].startswith("상세페이지 ")
    assert sample_form["product_name"] in doc["sections"][0]["content"]["text"]
    types = [s["type"] for s in doc["sections"]]
    assert types == ["eyebrow", "headline", "stat", "subclaim", "image", "note"]
    # 업로드한 이미지가 첫 번째 순서 그대로 문서에 들어간다.
    assert doc["sections"][4]["content"]["url"] == assets[0]["url"]

    messages = client.get(f"/api/documents/{doc['id']}/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["meta"]["summaryCard"]

    # 채팅으로 헤드라인 축약
    before = doc["sections"][1]["content"]["lines"]
    res = client.post(f"/api/documents/{doc['id']}/chat", json={"message": "히어로 문구를 짧게 줄여줘."}).json()
    after = next(s for s in res["document"]["sections"] if s["type"] == "headline")["content"]
    assert len(after["lines"]) == 2 < len(before)
    assert after["fontSize"] == 38

    # 인라인 편집 저장
    sections = res["document"]["sections"]
    sections[1]["content"]["fontSize"] = 46
    patched = client.patch(f"/api/documents/{doc['id']}", json={"sections": sections}).json()
    assert patched["sections"][1]["content"]["fontSize"] == 46

    items = client.get("/api/workspace").json()
    assert any(i["document_id"] == doc["id"] and i["status"] == "done" for i in items)
    assert client.get("/api/workspace?type=blog").json() == []

    assert client.delete(f"/api/workspace/{job['id']}").status_code == 204
    assert client.get(f"/api/documents/{doc['id']}").status_code == 404


def test_cancel_job(client, png_bytes, sample_form):
    asset = client.post("/api/uploads", files={"files": ("a.png", png_bytes, "image/png")}).json()[0]
    job = client.post(
        "/api/jobs", json={"type": "detail_page", "form": sample_form, "image_ids": [asset["id"]]}
    ).json()
    r = client.post(f"/api/jobs/{job['id']}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "canceled"


def test_document_not_found(client):
    assert client.get("/api/documents/nope").status_code == 404
