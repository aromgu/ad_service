"use client";

import { Pencil, Trash2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { assetUrl } from "@/lib/env";
import type { JobType, WorkspaceItem } from "@/lib/types";

export const TYPE_LABEL: Record<JobType, string> = {
  detail_page: "상세페이지",
  blog: "블로그",
  product_reg: "상품등록",
};

/** 타입마다 색을 달리해 카드만 봐도 무엇인지 바로 구분되게 한다. */
const TYPE_STYLE: Record<JobType, string> = {
  detail_page: "border-accent-line bg-accent-bg text-accent",
  blog: "border-[#2C4A6E] bg-[#12233A] text-[#6BA5F0]",
  product_reg: "border-[#2E5A45] bg-[#132A20] text-[#5FC08D]",
};

/** 카드를 누르면 가는 곳 — 결과 종류별 에디터/검토 화면. */
export function itemHref(item: WorkspaceItem): string | null {
  if (item.type === "product_reg") {
    return item.product_draft_id ? `/product/${item.product_draft_id}` : null;
  }
  if (!item.document_id) return null;
  return item.type === "blog" ? `/blog/${item.document_id}` : `/detail/${item.document_id}`;
}

/** 남은 시간 추정 — 지금까지 걸린 시간과 진행률로 계산한다. */
function remainingText(item: WorkspaceItem): string | null {
  if (item.progress <= 1) return null;
  const elapsed = (Date.now() - new Date(item.created_at).getTime()) / 1000;
  const remain = Math.round((elapsed * (100 - item.progress)) / item.progress);
  if (!Number.isFinite(remain) || remain <= 0 || remain > 600) return null;
  return `약 ${remain}초 남음`;
}

export function WorkCard({
  item,
  onDelete,
  onRetry,
  onRename,
  retrying,
}: {
  item: WorkspaceItem;
  onDelete: (item: WorkspaceItem) => void;
  onRetry: (item: WorkspaceItem) => void;
  onRename: (item: WorkspaceItem, title: string) => void;
  retrying: boolean;
}) {
  const href = itemHref(item);
  const running = item.status === "queued" || item.status === "running";
  const failed = item.status === "failed" || item.status === "canceled";
  const thumb = assetUrl(item.thumbnail_url);
  const openable = href !== null && !running && !failed;

  const picture = (
    <div className="relative aspect-[3/4] overflow-hidden bg-ph">
      {!running && !failed && thumb ? (
        <Image
          src={thumb}
          alt={item.title}
          fill
          sizes="(max-width:820px) 100vw, (max-width:1440px) 33vw, 25vw"
          className="object-cover"
          unoptimized
        />
      ) : (
        <div className="size-full bg-[#1B1B21]" />
      )}

      {running && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
          <span className="spin-1s block size-[34px] rounded-full border-[3px] border-violet border-t-transparent" />
          <span className="text-[12.5px] font-semibold text-fg">
            생성 중… {Math.round(item.progress)}%
          </span>
          <span className="text-[11.5px] text-muted">
            {remainingText(item) ?? "잠시만 기다려 주세요"}
          </span>
        </div>
      )}

      {failed && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2.5">
          <span className="flex size-[34px] items-center justify-center rounded-full border border-[#5A3038] bg-[#2A1A1E] text-[15px] text-danger">
            !
          </span>
          <span className="text-[12.5px] font-semibold text-fg">
            {item.status === "canceled" ? "생성을 중단했어요" : "생성에 실패했어요"}
          </span>
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onRetry(item);
            }}
            disabled={retrying}
            className="text-[12px] text-accent underline transition-ui hover:brightness-125 disabled:opacity-50"
          >
            {retrying ? "다시 시도 중…" : "다시 시도"}
          </button>
        </div>
      )}
    </div>
  );

  return (
    <li className="group relative flex flex-col overflow-hidden rounded-xl border border-line bg-surface transition-ui hover:border-line-soft">
      <CardTitle title={item.title} onRename={(t) => onRename(item, t)} />

      {openable ? (
        <Link href={href} aria-label={`${item.title} 열기`}>
          {picture}
        </Link>
      ) : (
        picture
      )}

      <button
        type="button"
        onClick={() => onDelete(item)}
        aria-label={`${item.title} 삭제`}
        className="absolute top-[46px] right-2.5 hidden size-7 items-center justify-center rounded-lg border border-line bg-[rgba(11,11,15,.75)] text-fg transition-ui group-hover:flex hover:border-danger hover:text-danger"
      >
        <Trash2 className="size-3.5" />
      </button>

      <div className="flex items-center justify-between gap-2 border-t border-line px-3.5 py-3">
        <span className="truncate text-[12px] text-muted">
          {new Date(item.created_at).toLocaleDateString("ko-KR")}
        </span>
        <span
          className={`flex-none rounded-md border px-2.5 py-1 text-[11.5px] font-semibold ${TYPE_STYLE[item.type]}`}
        >
          {TYPE_LABEL[item.type]}
        </span>
      </div>
    </li>
  );
}

/** 카드 맨 위 제목. 누르면 그 자리에서 고칠 수 있다. */
function CardTitle({ title, onRename }: { title: string; onRename: (t: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  const commit = () => {
    setEditing(false);
    const next = draft.trim();
    if (next && next !== title) onRename(next);
    else setDraft(title);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") {
            setDraft(title);
            setEditing(false);
          }
        }}
        maxLength={200}
        aria-label="작업 이름"
        className="w-full border-b border-line bg-inset px-3.5 py-3 text-[14px] font-semibold text-fg outline-none"
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => {
        setDraft(title);
        setEditing(true);
      }}
      title="이름 바꾸기"
      className="flex w-full items-center gap-1.5 border-b border-line px-3.5 py-3 text-left transition-ui hover:bg-[#1b1b21]"
    >
      <span className="truncate text-[14px] font-semibold text-fg">{title}</span>
      <Pencil className="size-3 flex-none text-dim opacity-0 transition-ui group-hover:opacity-100" />
    </button>
  );
}
