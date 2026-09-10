# web/frontend — 화면

Next.js 16 (App Router) · React 19 · TypeScript · Tailwind v4 · lucide-react.

```bash
npm install
cp .env.example .env.local     # NEXT_PUBLIC_API_BASE=http://localhost:8000
npm run dev                    # http://localhost:3000
```

백엔드(`web/backend`)가 함께 떠 있어야 생성 플로우가 동작한다.

## 라우트 ↔ 와이어프레임

| 라우트 | 프레임 | 설명 |
| --- | --- | --- |
| `/` | `1a` | 랜딩 |
| `/detail/new` | `2a` | 상세페이지 입력 |
| `/jobs/[jobId]` | `2b` | 생성 중 (진행률 폴링) |
| `/detail/[documentId]` | `2c` / `2d` | 에디터 — Edit 토글로 보기/편집 전환 |
| `/blog` | `3a` · `3a-2` | 블로그 입력 + AI 사진 편집 팝업 |
| `/blog/[documentId]` | `3c` | 블로그 에디터 |
| `/product` | `4a` | 상품등록 입력 (`?from=<문서id>` 면 4a 를 건너뛰고 바로 분석) |
| `/product/[draftId]` | `4c` | 검토 및 등록 · 등록 완료 상태를 한 화면에서 처리 |
| `/works` | `5a` / `5b` | 내 작업 — 목록 · 빈 상태 |

## 구조

```
src/
├── app/                 # 라우트별 페이지
├── components/
│   ├── TopNav.tsx       # 공용 상단 내비 (탭 순서 고정)
│   ├── Logo.tsx         # 해머 로고마크 (currentColor)
│   ├── ImageDropzone.tsx# 드래그 · Ctrl+V · 파일선택
│   ├── AiPhotoEditDialog.tsx  # 3a-2 팝업
│   ├── WorkCard.tsx     # 5a 카드 (완료·생성 중·실패 상태 + 미니 미리보기)
│   ├── ProgressRing.tsx / StepChecklist.tsx
│   ├── ui/              # Button, Field, Select, ToggleGroup
│   └── editor/
│       ├── EditorShell.tsx    # 2c/2d 와 3c 가 공유하는 껍데기
│       ├── DocumentCanvas.tsx # 섹션 렌더 + 인라인 편집 (DETAIL_CANVAS / BLOG_CANVAS)
│       ├── ChatSidebar.tsx / InlineToolbar.tsx
└── lib/                 # api.ts (타입 있는 fetch), types.ts, images.ts, env.ts
```

## 디자인 토큰

`src/app/globals.css` 의 `@theme` 블록이 `web/design-reference/README.md` 의 Color 표와 1:1로 대응한다.
색을 바꿀 일이 생기면 **레퍼런스 문서와 함께** 갱신할 것.

- 그라디언트(`grad` 유틸)는 primary CTA · 활성 내비 필 · 활성 필터 칩에만 쓴다.
- 드롭섀도는 어디에도 쓰지 않는다. 계층은 배경 명도 차이 + 1px 보더로만 표현한다.
- 포커스 링은 `2px #7C3AED` + offset 2px. 브라우저 기본 파란 링은 쓰지 않는다.

## 알아 둘 제약

- 폰트는 Pretendard 를 jsDelivr CDN 에서 받는다. 폐쇄망 배포 시 셀프 호스팅으로 바꿔야 한다.
- 에디터 2분할은 데스크톱 전용이다(레퍼런스에 모바일 디자인 없음). 좁은 폭 대응은 별도 협의 필요.
- 로그인 화면이 아직 없어서 모든 요청이 백엔드의 데모 계정으로 처리된다.
- 생성 중 화면(`/jobs/[jobId]`)은 `?type=` 쿼리로 작업 종류를 받는다. 없으면 첫 폴링이
  돌아올 때까지 중립 문구를 보여준다 — 기본값을 정해 두면 엉뚱한 제목이 잠깐 스친다.
- 여러 필드를 연달아 고치는 화면(4c)에서는 디바운스 저장 시 변경분을 **누적**해야 한다.
  마지막 호출분만 보내면 그 사이 수정이 서버에 안 가고 응답이 로컬 상태를 덮어써서 조용히 날아간다.
- 내 작업(`/works`)은 생성 중 카드가 있을 때만 1.5초 간격으로 폴링한다. 전부 완료되면 멈춘다.
- 마이페이지는 만들지 않기로 했다. 되살릴 일이 생기면 `TopNav` 의 우측 필과 라우트를 함께 추가할 것.
