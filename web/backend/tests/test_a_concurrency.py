"""동시 요청 테스트.

파일명이 test_a_ 로 시작하는 건 **가장 먼저 돌리기 위해서**다.
데모 계정이 아직 없는 빈 DB 상태여야 경합을 재현할 수 있다.
"""

import concurrent.futures as cf


def test_first_requests_on_empty_db_dont_collide(client, png_bytes):
    """빈 DB 에 동시에 첫 요청이 들어와도 전부 성공해야 한다.

    데모 계정을 여러 요청이 동시에 만들려다 UNIQUE 제약에 걸려
    500 이 나던 버그의 회귀 테스트.
    """

    def upload(i: int):
        r = client.post("/api/uploads", files={"files": (f"{i}.png", png_bytes, "image/png")})
        return r.status_code

    with cf.ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(upload, range(8)))

    assert all(c == 201 for c in codes), codes


def test_demo_user_is_created_once(client):
    me = client.get("/api/auth/me").json()
    again = client.get("/api/auth/me").json()
    assert me["id"] == again["id"], "요청마다 계정이 새로 생기면 안 된다"
    assert me["email"] == "demo@smith.local"
