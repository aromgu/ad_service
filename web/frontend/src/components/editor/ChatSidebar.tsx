"use client";

import { ArrowUp, ChevronDown, ImagePlus, type LucideIcon, PanelLeft, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { LogoMark } from "@/components/Logo";
import { assetUrl } from "@/lib/env";
import { useEscape } from "@/lib/use-dismiss";
import type { Asset, ChatMessage, WorkspaceItem } from "@/lib/types";

export function ChatSidebar({
  title,
  siblings,
  onPickSibling,
  onToggle,
  messages,
  sending,
  onSend,
  onUploadImage,
}: {
  title: string;
  /** 같은 종류의 다른 문서들 — 제목을 눌러 갈아탈 수 있다 */
  siblings: WorkspaceItem[];
  onPickSibling: (item: WorkspaceItem) => void;
  onToggle: () => void;
  messages: ChatMessage[];
  sending: boolean;
  onSend: (text: string, imageIds: string[]) => void;
  onUploadImage: (file: File) => Promise<Asset>;
}) {
  const [draft, setDraft] = useState("");
  const [attached, setAttached] = useState<Asset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEscape(menuOpen, () => setMenuOpen(false));

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, sending]);

  const submit = () => {
    const text = draft.trim();
    if ((!text && attached.length === 0) || sending) return;
    onSend(text || "이 사진을 넣어줘.", attached.map((a) => a.id));
    setDraft("");
    setAttached([]);
  };

  const pickFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    try {
      const added: Asset[] = [];
      for (const f of Array.from(files).slice(0, 5 - attached.length)) {
        added.push(await onUploadImage(f));
      }
      setAttached((prev) => [...prev, ...added]);
    } finally {
      setUploading(false);
    }
  };

  return (
    <aside className="flex w-80 flex-none flex-col border-r border-line bg-sidebar">
      {/* 로고 · 제목 · 접기를 3칸으로 나눠 제목이 가운데 오게 한다 */}
      <header className="relative grid grid-cols-[auto_1fr_auto] items-center gap-2 border-b border-line px-4 py-3.5">
        <Link
          href="/"
          aria-label="홈으로"
          title="홈으로"
          className="rounded-md p-0.5 transition-ui hover:bg-[#1b1b21]"
        >
          <LogoMark size={22} />
        </Link>

        <button
          type="button"
          onClick={() => setMenuOpen((v) => !v)}
          aria-expanded={menuOpen}
          className="mx-auto flex min-w-0 items-center gap-1 rounded-lg px-2 py-0.5 transition-ui hover:bg-[#1b1b21]"
        >
          <span className="truncate text-[13px] font-semibold text-fg">{title}</span>
          <ChevronDown className="size-3.5 flex-none text-muted" />
        </button>

        <IconButton label="사이드바 접기" icon={PanelLeft} onClick={onToggle} />

        {menuOpen && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
            <div className="absolute top-full left-1/2 z-20 mt-1 max-h-[320px] w-[272px] -translate-x-1/2 overflow-y-auto rounded-[10px] border border-line bg-surface py-1.5">
              {siblings.length === 0 ? (
                <p className="m-0 px-3 py-2.5 text-[12px] text-dim">다른 문서가 없습니다.</p>
              ) : (
                siblings.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      onPickSibling(item);
                    }}
                    className="block w-full truncate px-3 py-2 text-left text-[12.5px] text-fg transition-ui hover:bg-[#1b1b21]"
                  >
                    {item.title}
                  </button>
                ))
              )}
            </div>
          </>
        )}
      </header>

      <div ref={threadRef} className="flex flex-1 flex-col gap-3.5 overflow-y-auto p-4">
        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="flex flex-col gap-1.5">
              <span className="text-[11px] text-dim">나</span>
              <div className="max-w-[88%] self-end rounded-[10px] bg-ph px-3 py-2.5 text-[12.5px] leading-[1.6] text-fg">
                {m.meta?.images && m.meta.images.length > 0 && (
                  <div className="mb-2 flex gap-1.5">
                    {m.meta.images.map((u) => (
                      <span key={u} className="relative block size-12 overflow-hidden rounded-md">
                        <Image src={assetUrl(u)!} alt="첨부" fill sizes="48px" className="object-cover" unoptimized />
                      </span>
                    ))}
                  </div>
                )}
                {m.content}
              </div>
            </div>
          ) : (
            <AssistantMessage key={m.id} message={m} />
          ),
        )}
        {sending && (
          <div className="flex items-center gap-2 text-[11.5px] text-dim">
            <span className="spin-1s block size-3.5 rounded-full border-2 border-violet border-t-transparent" />
            스미스 씨가 문서를 고치는 중…
          </div>
        )}
      </div>

      <footer className="flex flex-none flex-col gap-2 border-t border-line px-4 pt-3.5 pb-4">
        {attached.length > 0 && (
          <ul className="flex flex-wrap gap-1.5">
            {attached.map((a) => (
              <li key={a.id} className="relative size-12 overflow-hidden rounded-md border border-line">
                <Image src={assetUrl(a.url)!} alt={a.filename} fill sizes="48px" className="object-cover" unoptimized />
                <button
                  type="button"
                  aria-label={`${a.filename} 첨부 취소`}
                  onClick={() => setAttached((p) => p.filter((x) => x.id !== a.id))}
                  className="absolute top-0 right-0 flex size-4 items-center justify-center bg-[rgba(11,11,15,.8)] text-fg hover:text-danger"
                >
                  <X className="size-2.5" />
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex items-center gap-2 rounded-xl border border-line bg-surface py-2.5 pr-2.5 pl-2.5">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={uploading || attached.length >= 5}
            aria-label="사진 첨부"
            title="사진 첨부"
            className="flex size-7 flex-none items-center justify-center rounded-lg text-muted transition-ui hover:bg-ph hover:text-fg disabled:opacity-40"
          >
            {uploading ? (
              <span className="spin-1s block size-3.5 rounded-full border-2 border-violet border-t-transparent" />
            ) : (
              <ImagePlus className="size-4" />
            )}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            multiple
            hidden
            onChange={(e) => {
              pickFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="수정하고 싶은 내용을 입력하세요…"
            aria-label="수정 요청"
            className="min-w-0 flex-1 bg-transparent text-[12.5px] text-fg outline-none"
          />
          <button
            type="button"
            onClick={submit}
            disabled={(!draft.trim() && attached.length === 0) || sending}
            aria-label="전송"
            className="grad flex size-7 flex-none items-center justify-center rounded-lg text-white transition-ui hover:brightness-110 disabled:opacity-40"
          >
            <ArrowUp className="size-4" />
          </button>
        </div>
      </footer>
    </aside>
  );
}

function AssistantMessage({ message }: { message: ChatMessage }) {
  // toolSteps / askUser 는 와이어프레임의 장식이었다. 펼쳐지지도 않는 ▾ 행이라 걷어냈다.
  const { summaryCard, closing, footer } = message.meta ?? {};
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[11px] text-dim">스미스 씨</span>
      <p className="m-0 text-[12.5px] leading-[1.7] text-fg">{message.content}</p>

      {summaryCard && summaryCard.length > 0 && (
        <dl className="m-0 flex flex-col gap-[7px] rounded-[10px] border border-line bg-surface p-3">
          {summaryCard.map((row) => (
            <div key={row.label} className="flex justify-between gap-3 text-[11.5px]">
              <dt className="text-dim">{row.label}</dt>
              <dd className="m-0 truncate text-fg">{row.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {closing && <p className="m-0 text-[12.5px] leading-[1.7] text-fg">{closing}</p>}
      {footer && <span className="pt-0.5 text-[11.5px] text-muted">{footer}</span>}
    </div>
  );
}

function IconButton({
  label,
  icon: Icon,
  onClick,
}: {
  label: string;
  icon: LucideIcon;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex size-6 flex-none items-center justify-center rounded-md border border-line text-muted transition-ui hover:border-line-soft hover:bg-[#1b1b21] hover:text-fg"
    >
      <Icon className="size-3.5" />
    </button>
  );
}
