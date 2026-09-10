"use client";

import {
  ChevronDown,
  LayoutTemplate,
  type LucideIcon,
  MousePointer2,
  Undo2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { ChatMessage, DocumentModel, Section } from "@/lib/types";

import { ChatSidebar } from "./ChatSidebar";
import { CanvasSize, DETAIL_CANVAS, DocumentCanvas } from "./DocumentCanvas";

const SAVE_DEBOUNCE_MS = 800;

export interface EditorShellProps {
  documentId: string;
  /** 문서 캔버스 치수 — 상세페이지와 블로그가 다르다 */
  canvas?: CanvasSize;
  /** 좌측 컴포저 위 스타일 칩 라벨 */
  styleChip: string;
  /** 상단 바 좌측 문서명 옆에 붙는 보조 지표 (예: "100%", "1,412자") */
  metric: (doc: DocumentModel | null) => string;
  /** 상단 바에 추가할 버튼 (예: 블로그의 "HTML 복사") */
  topBarExtra?: (doc: DocumentModel) => React.ReactNode;
  /** 보기 모드에서만 뜨는 우하단 플로팅 CTA */
  floatingCta?: (doc: DocumentModel) => React.ReactNode;
  /** 오류 시 돌아갈 입력 화면 */
  backTo: string;
}

/**
 * 에디터 공통 껍데기 — 프레임 2c/2d(상세페이지)와 3c(블로그)가 공유한다.
 * 좌: 채팅 사이드바 / 우: 문서 캔버스 + Edit 토글.
 */
export function EditorShell({
  documentId,
  canvas = DETAIL_CANVAS,
  styleChip,
  metric,
  topBarExtra,
  floatingCta,
  backTo,
}: EditorShellProps) {
  const router = useRouter();

  const [doc, setDoc] = useState<DocumentModel | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [editMode, setEditMode] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!documentId) return;
    let alive = true;
    (async () => {
      try {
        const [d, m] = await Promise.all([
          api.getDocument(documentId),
          api.getMessages(documentId),
        ]);
        if (!alive) return;
        setDoc(d);
        setMessages(m);
      } catch (err) {
        if (alive) setError(err instanceof ApiError ? err.message : "문서를 불러올 수 없습니다.");
      }
    })();
    return () => {
      alive = false;
    };
  }, [documentId]);

  /** 섹션 변경 → 낙관적 반영 후 디바운스 저장. */
  const commitSections = useCallback(
    (sections: Section[]) => {
      setDoc((prev) => (prev ? { ...prev, sections } : prev));
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(async () => {
        setSaveState("saving");
        try {
          await api.patchDocument(documentId, { sections });
          setSaveState("saved");
        } catch {
          setSaveState("error");
        }
      }, SAVE_DEBOUNCE_MS);
    },
    [documentId],
  );

  const patchContent = (id: string, content: Partial<Section["content"]>) => {
    if (!doc) return;
    commitSections(
      doc.sections.map((s) => (s.id === id ? { ...s, content: { ...s.content, ...content } } : s)),
    );
  };

  const deleteSection = (id: string) => {
    if (!doc) return;
    setSelectedId(null);
    commitSections(doc.sections.map((s) => (s.id === id ? { ...s, visible: false } : s)));
  };

  const replaceImage = async (id: string, file: File) => {
    try {
      const [asset] = await api.uploadImages([file]);
      patchContent(id, { url: asset.url });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "이미지 교체에 실패했습니다.");
    }
  };

  const send = async (text: string) => {
    setSending(true);
    const optimistic: ChatMessage = {
      id: `tmp-${Date.now()}`,
      role: "user",
      content: text,
      meta: {},
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    try {
      const res = await api.chat(documentId, text);
      setMessages((prev) => [...prev.filter((m) => m.id !== optimistic.id), ...res.messages]);
      setDoc(res.document);
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setError(err instanceof ApiError ? err.message : "메시지를 보내지 못했습니다.");
    } finally {
      setSending(false);
    }
  };

  if (error && !doc) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="m-0 text-[15px] text-danger">{error}</p>
        <button
          onClick={() => router.push(backTo)}
          className="rounded-[10px] border border-line px-4 py-2.5 text-[13px] text-fg transition-ui hover:border-line-soft"
        >
          입력 화면으로
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-screen">
      <ChatSidebar
        title={doc?.title ?? "문서"}
        styleChip={styleChip}
        messages={messages}
        sending={sending}
        onSend={send}
      />

      <main className="flex min-w-0 flex-1 flex-col bg-canvas">
        <div className="flex h-[52px] items-center justify-between gap-4 border-b border-line bg-ink px-[18px]">
          <div className="flex items-center gap-3">
            <IconButton label="실행취소 / 히스토리" icon={Undo2} />
            <IconButton label="레이아웃" icon={LayoutTemplate} />
            <span className="flex items-center gap-1 text-[13px] text-fg">
              {doc?.title ?? "…"}
              <ChevronDown className="size-3.5 text-muted" />
            </span>
            {saveState !== "idle" && (
              <span className="text-[11.5px] text-dim">
                {saveState === "saving"
                  ? "저장 중…"
                  : saveState === "saved"
                    ? "저장됨"
                    : "저장 실패"}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[12.5px] text-muted">{metric(doc)}</span>
            <IconButton label="커서 도구" icon={MousePointer2} />
            <button
              type="button"
              aria-pressed={editMode}
              onClick={() => {
                setEditMode((v) => !v);
                setSelectedId(null);
              }}
              className={`rounded-lg px-3 py-1.5 text-[12.5px] transition-ui ${
                editMode
                  ? "grad font-semibold text-white hover:brightness-110"
                  : "border border-line text-fg hover:border-line-soft hover:bg-[#1b1b21]"
              }`}
            >
              Edit
            </button>
            {doc && topBarExtra?.(doc)}
            <button
              type="button"
              className="rounded-lg bg-ph px-3.5 py-1.5 text-[12.5px] text-fg transition-ui hover:brightness-125"
            >
              Share
            </button>
            <span className="block size-[26px] rounded-full bg-ph-3" aria-hidden />
          </div>
        </div>

        <div className="relative min-h-0 flex-1">
          <div className="flex h-full justify-center overflow-auto pt-9">
            {doc ? (
              <DocumentCanvas
                sections={doc.sections}
                size={canvas}
                editMode={editMode}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onPatchContent={patchContent}
                onDelete={deleteSection}
                onReplaceImage={replaceImage}
              />
            ) : (
              <div
                className="h-[600px] rounded-[4px] border border-paper-line bg-paper"
                style={{ width: canvas.width }}
              />
            )}
          </div>

          {!editMode && doc && floatingCta?.(doc)}
        </div>
      </main>

      {error && doc && (
        <p
          role="alert"
          className="fixed bottom-5 left-[340px] m-0 rounded-[10px] border border-danger/50 bg-[#2a1a1e] px-4 py-2.5 text-[12.5px] text-danger"
        >
          {error}
        </p>
      )}
    </div>
  );
}

function IconButton({ label, icon: Icon }: { label: string; icon: LucideIcon }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className="flex size-6 items-center justify-center rounded-md border border-line text-muted transition-ui hover:border-line-soft hover:bg-[#1b1b21] hover:text-fg"
    >
      <Icon className="size-3.5" />
    </button>
  );
}
