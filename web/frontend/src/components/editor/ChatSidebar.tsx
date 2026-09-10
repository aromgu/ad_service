"use client";

import { ArrowUp, ChevronDown, type LucideIcon, PanelLeft, Search, Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { LogoMark } from "@/components/Logo";
import type { ChatMessage } from "@/lib/types";

export function ChatSidebar({
  title,
  styleChip = "Modernist",
  messages,
  sending,
  onSend,
}: {
  title: string;
  styleChip?: string;
  messages: ChatMessage[];
  sending: boolean;
  onSend: (text: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, sending]);

  const submit = () => {
    const text = draft.trim();
    if (!text || sending) return;
    onSend(text);
    setDraft("");
  };

  return (
    <aside className="flex w-80 flex-none flex-col border-r border-line bg-sidebar">
      <header className="flex items-center justify-between gap-2.5 border-b border-line px-4 py-3.5">
        <div className="flex min-w-0 items-center gap-2">
          <LogoMark size={22} />
          <span className="flex min-w-0 items-center gap-1 text-[13px] font-semibold text-fg">
            <span className="truncate">{title}</span>
            <ChevronDown className="size-3.5 flex-none text-muted" />
          </span>
        </div>
        <div className="flex gap-1.5">
          <IconButton label="패널 토글" icon={PanelLeft} />
          <IconButton label="검색" icon={Search} />
        </div>
      </header>

      <div ref={threadRef} className="flex flex-1 flex-col gap-3.5 overflow-y-auto p-4">
        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="flex flex-col gap-1.5">
              <span className="text-[11px] text-dim">나</span>
              <div className="max-w-[88%] self-end rounded-[10px] bg-ph px-3 py-2.5 text-[12.5px] leading-[1.6] text-fg">
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
        <span className="flex items-center gap-1 self-start rounded-full border border-line px-[11px] py-[5px] text-[11.5px] text-muted">
          {styleChip}
          <ChevronDown className="size-3" />
        </span>
        <div className="flex items-center gap-2 rounded-xl border border-line bg-surface py-2.5 pr-2.5 pl-3.5">
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
            className="flex-1 bg-transparent text-[12.5px] text-fg outline-none"
          />
          <button
            type="button"
            onClick={submit}
            disabled={!draft.trim() || sending}
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
  const { toolSteps, askUser, summaryCard, closing, footer } = message.meta ?? {};
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[11px] text-dim">스미스 씨</span>
      <p className="m-0 text-[12.5px] leading-[1.7] text-fg">{message.content}</p>

      {toolSteps?.map((step) => (
        <CollapsedRow key={step} label={step} />
      ))}
      {askUser && <CollapsedRow label="Ask user" icon={Zap} />}

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

function CollapsedRow({ label, icon: Icon }: { label: string; icon?: LucideIcon }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-line bg-inset px-[11px] py-[9px]">
      <span className="flex items-center gap-1.5 text-[11.5px] text-muted">
        {Icon && <Icon className="size-3 text-accent" />}
        {label}
      </span>
      <ChevronDown className="size-3 text-dim" />
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
