"use client";

import { Trash2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { assetUrl } from "@/lib/env";
import type { JobType, WorkspaceItem } from "@/lib/types";

export const TYPE_LABEL: Record<JobType, string> = {
  detail_page: "상세페이지",
  blog: "블로그",
  product_reg: "상품등록",
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
  retrying,
}: {
  item: WorkspaceItem;
  onDelete: (item: WorkspaceItem) => void;
  onRetry: (item: WorkspaceItem) => void;
  retrying: boolean;
}) {
  const href = itemHref(item);
  const running = item.status === "queued" || item.status === "running";
  const failed = item.status === "failed" || item.status === "canceled";
  const thumb = assetUrl(item.thumbnail_url);

  const body = (
    <div
      className="relative h-[280px] overflow-hidden"
      style={{ background: running || failed ? "#1B1B21" : "var(--color-ph)" }}
    >
      {/* 생성된 페이지를 축소한 미리보기 — 텍스트는 막대로, 이미지 자리에는 실제 결과물 */}
      <Preview
        type={item.type}
        thumb={running || failed ? null : thumb}
        alt={item.title}
        opacity={running ? 0.28 : failed ? 0.18 : 1}
      />

      {running && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
          <span className="spin-1s block size-[34px] rounded-full border-[3px] border-violet border-t-transparent" />
          <span className="text-[12.5px] font-semibold text-fg">
            생성 중… {Math.round(item.progress)}%
          </span>
          <span className="text-[11.5px] text-muted">{remainingText(item) ?? "잠시만 기다려 주세요"}</span>
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
    <li
      title={item.title}
      className="group relative flex flex-col overflow-hidden rounded-xl border border-line bg-surface transition-ui hover:border-line-soft"
    >
      {href && !running && !failed ? (
        <Link href={href} aria-label={`${item.title} 열기`}>
          {body}
        </Link>
      ) : (
        body
      )}

      <button
        type="button"
        onClick={() => onDelete(item)}
        aria-label={`${item.title} 삭제`}
        className="absolute top-2.5 right-2.5 hidden size-7 items-center justify-center rounded-lg border border-line bg-[rgba(11,11,15,.75)] text-fg transition-ui group-hover:flex hover:border-danger hover:text-danger"
      >
        <Trash2 className="size-3.5" />
      </button>

      <div className="flex items-center justify-between gap-2 border-t border-line px-3.5 py-3">
        <span className="truncate text-[12px] text-muted">
          {new Date(item.created_at).toLocaleDateString("ko-KR")}
        </span>
        <span className="flex-none rounded-md border border-line px-[9px] py-[3px] text-[11px] text-muted">
          {TYPE_LABEL[item.type]}
        </span>
      </div>
    </li>
  );
}

/**
 * 생성 결과를 축소한 미리보기.
 * 문단·제목은 회색 막대로, 이미지 블록 자리에는 실제 결과 이미지를 넣는다.
 * 타입마다 배치가 달라 카드만 봐도 무엇인지 구분된다.
 */
function Preview({
  type,
  thumb,
  alt,
  opacity,
}: {
  type: JobType;
  thumb: string | null;
  alt: string;
  opacity: number;
}) {
  const bar = (key: string, w: string, h: number, tone: "a" | "b" = "a", mt = 0) => (
    <span
      key={key}
      className="block rounded"
      style={{
        width: w,
        height: h,
        marginTop: mt,
        background: tone === "a" ? "var(--color-ph-2)" : "var(--color-ph-3)",
      }}
    />
  );

  const slot = (key: string, h: number) => (
    <span
      key={key}
      className="relative block overflow-hidden rounded-md"
      style={{ height: h, background: "var(--color-ph-2)" }}
    >
      {thumb && (
        <Image src={thumb} alt={alt} fill sizes="320px" className="object-cover" unoptimized />
      )}
    </span>
  );

  // 각 타입의 실제 문서 구조를 따라간다 (상세페이지: 히어로 → 큰 이미지, 블로그: 제목 → 사진 → 본문)
  const rows =
    type === "blog"
      ? [bar("b1", "44%", 8), slot("b2", 90), bar("b3", "80%", 14, "b"), bar("b4", "64%", 14, "b"), bar("b5", "100%", 60)]
      : type === "product_reg"
        ? [bar("p1", "52%", 8), slot("p2", 110), bar("p3", "70%", 14, "b"), bar("p4", "40%", 14, "b"), bar("p5", "100%", 44)]
        : [
            bar("d1", "60%", 8),
            bar("d2", "88%", 16, "b"),
            bar("d3", "70%", 16, "b"),
            slot("d4", 120),
            bar("d5", "50%", 8),
          ];

  return (
    <div className="flex flex-col gap-2 p-[18px]" style={{ opacity }} aria-hidden={!thumb}>
      {rows}
    </div>
  );
}
