# web — 스마트한 스미스 씨 (프론트엔드 + 백엔드)

담당: ihhwang. 이 디렉터리 밖(`src/ad_service`, `docker/`, `deploy/` 등)은 건드리지 않는다.

```
web/
├── frontend/          # Next.js 16 + TypeScript + Tailwind v4 (화면·UI)
├── backend/           # FastAPI + SQLite (인증·작업·업로드·문서 API)
├── design-reference/  # 클로드 디자인 와이어프레임 15프레임 + 스펙 (읽기 전용)
└── images/            # 로고·샘플·생성 결과 이미지 (백엔드가 /static/images 로 서빙)
```

## 사전 준비

Node 22 가 필요하다(이 VM 에는 `~/.local/lib/node` 에 설치돼 있고 `~/.local/bin` 이 PATH 에 잡혀 있다).

```bash
node -v   # v22.x
```

없으면:

```bash
curl -fsSL https://nodejs.org/dist/v22.20.0/node-v22.20.0-linux-x64.tar.xz -o /tmp/node.tar.xz
mkdir -p ~/.local/lib && tar -xf /tmp/node.tar.xz -C ~/.local/lib
mv ~/.local/lib/node-v22.20.0-linux-x64 ~/.local/lib/node
ln -sf ~/.local/lib/node/bin/{node,npm,npx} ~/.local/bin/
```

## 실행 (터미널 두 개)

```bash
# 1) 백엔드 — http://localhost:8000  (API 문서: /docs)
cd web/backend
uv venv .venv && uv pip install -r requirements.txt --python .venv/bin/python
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --reload --port 8000

# 2) 프론트엔드 — http://localhost:3000
cd web/frontend
npm install
cp .env.example .env.local
npm run dev
```

`http://localhost:3000` 을 열고 "상세페이지 만들기 →" 부터 진행하면 된다.

## 지금까지 구현된 것

| 프레임 | 화면 | 라우트 | 상태 |
| --- | --- | --- | --- |
| `1a` | 랜딩 | `/` | ✅ |
| `2a` | AI 상세페이지 — 입력 | `/detail/new` | ✅ |
| `2b` | 생성 중 | `/jobs/[jobId]` | ✅ 서버 진행률 폴링·스텝 전환·취소 |
| `2c` | 에디터 — 보기 | `/detail/[id]` | ✅ 채팅 스레드, 상품등록 인계 CTA |
| `2d` | 에디터 — 편집 | 〃 (Edit 토글) | ✅ 블록 선택, 인라인 툴바, 이미지 교체, 자동 저장 |
| `3a` | AI 블로그 — 입력 | `/blog` | ✅ |
| `3a-2` | AI 사진 편집 팝업 | 〃 (모달) | ✅ 장수 무제한 업로드, 1~4장 생성, 복수 선택 |
| `3b` | 생성 중 | `/jobs/[jobId]` | ✅ |
| `3c` | 블로그 에디터 | `/blog/[id]` | ✅ 글자 수 지표, HTML 복사 |
| `4a` | AI 상품등록 — 입력 | `/product` | ✅ 배송 설정 저장·재사용, 두 갈래 제출 |
| `4b` | 분석 중 | `/jobs/[jobId]` | ✅ |
| `4c` | 검토 및 등록 | `/product/[draftId]` | ✅ 카테고리 검색, 옵션·태그·속성 편집, 등록 후 재수정 |
| `5a` | 내 작업 — 목록 | `/works` | ✅ 타입 필터, 진행률 폴링, 삭제, 다시 시도 |
| `5b` | 내 작업 — 빈 상태 | 〃 | ✅ |

**와이어프레임 15개 프레임을 모두 구현했다.** 마이페이지는 팀 결정으로 만들지 않았다
(내비에서도 뺐다). 인증 API(`/api/auth`)는 백엔드에 남아 있으니 나중에 화면만 붙이면 된다.

### 플로우 분기

```
2c 에디터 ──"이 상세페이지로 상품등록"──▶ 4b 분석 ──▶ 바로 등록 완료   (4a·4c 건너뜀)
4a ──"AI가 알아서 등록하기"──▶ 4b 분석 ──▶ 바로 등록 완료              (4c 건너뜀)
4a ──"직접 확인하고 등록"────▶ 4b 분석 ──▶ 4c 검토 ──"등록"──▶ 완료
생성 실패·중단 ──▶ 5a 의 해당 카드 ──"다시 시도"──▶ 같은 입력값으로 재생성
5a 카드 클릭 ──▶ 2c / 3c / 4c
```

## 남은 일 / 팀에 물어볼 것

- **AI 생성은 아직 목업이다.** `web/backend/app/generation/` 의 provider 인터페이스 뒤에 숨겨 놨고,
  Gu·Park 의 추론 서버가 준비되면 `RemoteProvider` 를 추가하고 `.env` 의 `GENERATION_PROVIDER` 만 바꾸면 된다.
  필요한 것: 추론 서버의 엔드포인트 URL, 요청/응답 스키마, 진행률 이벤트 방식(폴링 or SSE).
- **로그인 UI 가 아직 없다.** 백엔드에는 `/api/auth/signup|login|me` 가 이미 있고, 화면이 붙기 전까지는
  `ALLOW_DEMO_USER=true` 로 토큰 없는 요청을 데모 계정으로 처리한다. 운영 배포 전 반드시 `false` 로 바꿀 것.
- **네이버 커머스 API 연동이 아직 안 붙었다.** 지금 "네이버에 상품 등록"은 필수값을 검증하고
  상태만 `registered` 로 바꾼다. 실제 연동은 `web/backend/app/api/routes/products.py` 의
  `register()` 안에서 토큰 발급 → 상품 등록을 호출하면 되고, 프론트는 바꿀 필요가 없다.
  토큰 발급 시 CLAUDE.md 의 주의사항(x-www-form-urlencoded, `type` 에 따른 `account_id` 포함 여부,
  `grant_type=client_credentials`)을 그대로 지킬 것.
- **AI 사진 편집(3a-2)도 목업이다.** 프롬프트와 원본 이미지는 이미 서버로 받고 있고
  (`POST /api/uploads/ai-edit`), 실제 이미지 생성 모델만 그 함수 안에 붙이면 된다.
- `web/images/` 는 레포에 함께 커밋한다(8.6MB). 랜딩 데모와 목업 생성 결과가 이 파일들을 쓰기 때문에
  팀원이 클론만 해도 화면이 제대로 보여야 한다. 대용량 원본이나 학습 데이터는 여기 두지 말고 `/home/data` 로.
