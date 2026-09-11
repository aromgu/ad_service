"use client";

import { Download, type LucideIcon, PanelLeft, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Loading } from "@/components/Loading";
import { ApiError, api } from "@/lib/api";
import { documentToHtml, download, safeFilename } from "@/lib/document-export";
import { useEscape } from "@/lib/use-dismiss";
import type { ChatMessage, DocumentModel, Section, WorkspaceItem } from "@/lib/types";

import { ChatSidebar } from "./ChatSidebar";
import { CanvasSize, DETAIL_CANVAS, DocumentCanvas } from "./DocumentCanvas";

const SAVE_DEBOUNCE_MS = 800;

export interface EditorShellProps {
  documentId: string;
  /** 문서 캔버스 치수 — 상세페이지와 블로그가 다르다 */
  canvas?: CanvasSize;
  /** 제목 드롭다운에 띄울 목록의 종류 */
  docType: "detail_page" | "blog";
  /** 이 종류의 다른 문서로 갈 때 쓸 경로 */
  hrefFor: (id: string) => string;
  /** 상단 바 좌측에 붙는 보조 지표 (예: "1,412자") */
  metric?: (doc: DocumentModel | null) => string;
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
  docType,
  hrefFor,
  metric,
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
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [siblings, setSiblings] = useState<WorkspaceItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [exporting, setExporting] = useState<"html" | "png" | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const paperRef = useRef<HTMLDivElement>(null);

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
  }, [documentId, reloadKey]);

  // 제목 드롭다운에 띄울 같은 종류의 다른 문서들
  useEffect(() => {
    let alive = true;
    api
      .workspace(docType)
      .then((items) => {
        if (!alive) return;
        setSiblings(items.filter((i) => i.document_id && i.document_id !== documentId));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [docType, documentId]);

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

  const send = async (text: string, imageIds: string[] = []) => {
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
      const res = await api.chat(documentId, text, imageIds);
      setMessages((prev) => [...prev.filter((m) => m.id !== optimistic.id), ...res.messages]);
      setDoc(res.document);
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setError(err instanceof ApiError ? err.message : "메시지를 보내지 못했습니다.");
    } finally {
      setSending(false);
    }
  };

  /** 채팅으로 고친 결과를 다시 불러온다. */
  const refresh = async () => {
    setRefreshing(true);
    setReloadKey((k) => k + 1);
    setTimeout(() => setRefreshing(false), 500);
  };

  const exportAs = async (kind: "html" | "png") => {
    if (!doc || exporting) return;
    setExporting(kind);
    setError(null);
    try {
      const name = safeFilename(doc.title);
      if (kind === "html") {
        download(`${name}.html`, new Blob([documentToHtml(doc)], { type: "text/html" }));
      } else {
        if (!paperRef.current) throw new Error("문서 영역을 찾을 수 없습니다.");
        const { toBlob } = await import("html-to-image");
        const blob = await toBlob(paperRef.current, {
          pixelRatio: 2,
          backgroundColor: "#F7F7F3",
          cacheBust: true,
        });
        if (!blob) throw new Error("이미지를 만들지 못했습니다.");
        download(`${name}.png`, blob);
      }
    } catch (err) {
      setError(
        err instanceof Error ? `저장에 실패했습니다: ${err.message}` : "저장에 실패했습니다.",
      );
    } finally {
      setExporting(null);
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
      {sidebarOpen && (
        <ChatSidebar
          title={doc?.title ?? "문서"}
          siblings={siblings}
          onPickSibling={(item) => router.push(hrefFor(item.document_id!))}
          onToggle={() => setSidebarOpen(false)}
          messages={messages}
          sending={sending}
          onSend={send}
          onUploadImage={async (file) => (await api.uploadImages([file]))[0]}
        />
      )}

      <main className="flex min-w-0 flex-1 flex-col bg-canvas">
        <div className="flex h-[52px] items-center justify-between gap-4 border-b border-line bg-ink px-[18px]">
          <div className="flex items-center gap-3">
            {!sidebarOpen && (
              <IconButton
                label="사이드바 펼치기"
                icon={PanelLeft}
                onClick={() => setSidebarOpen(true)}
              />
            )}
            <IconButton
              label="최신 수정본 불러오기"
              icon={RefreshCw}
              onClick={refresh}
              spinning={refreshing}
            />
            <span className="text-[13px] text-fg">{doc?.title ?? "…"}</span>
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
            {metric && <span className="text-[12.5px] text-muted">{metric(doc)}</span>}
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
            <DownloadMenu disabled={!doc} busy={exporting} onPick={exportAs} />
          </div>
        </div>

        <div className="relative min-h-0 flex-1">
          <div className="flex h-full justify-center overflow-auto pt-9">
            {doc ? (
              <div ref={paperRef}>
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
              </div>
            ) : (
              // 빈 종이 상자 대신 불러오는 중 표시 — 상자는 덜 만든 화면처럼 보인다.
              <Loading className="pt-24" />
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

function IconButton({
  label,
  icon: Icon,
  onClick,
  spinning,
}: {
  label: string;
  icon: LucideIcon;
  onClick?: () => void;
  spinning?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex size-6 items-center justify-center rounded-md border border-line text-muted transition-ui hover:border-line-soft hover:bg-[#1b1b21] hover:text-fg"
    >
      <Icon className={`size-3.5 ${spinning ? "spin-1s" : ""}`} />
    </button>
  );
}

/** HTML / PNG 로 내려받기. */
function DownloadMenu({
  disabled,
  busy,
  onPick,
}: {
  disabled: boolean;
  busy: "html" | "png" | null;
  onPick: (kind: "html" | "png") => void;
}) {
  const [open, setOpen] = useState(false);
  useEscape(open, () => setOpen(false));
  return (
    <div className="relative">
      <button
        type="button"
        disabled={disabled || busy !== null}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded-lg bg-ph px-3.5 py-1.5 text-[12.5px] text-fg transition-ui hover:brightness-125 disabled:opacity-40"
      >
        <Download className="size-3.5" />
        {busy ? "저장 중…" : "Download"}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute top-full right-0 z-20 mt-1.5 w-[150px] overflow-hidden rounded-[10px] border border-line bg-surface py-1.5">
            {(["html", "png"] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => {
                  setOpen(false);
                  onPick(k);
                }}
                className="block w-full px-3 py-2 text-left text-[12.5px] text-fg transition-ui hover:bg-[#1b1b21]"
              >
                {k === "html" ? "HTML 파일로" : "PNG 이미지로"}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
