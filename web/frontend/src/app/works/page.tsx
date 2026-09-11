"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { TopNav } from "@/components/TopNav";
import { WorkCard } from "@/components/WorkCard";
import { ButtonLink } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api";
import type { JobType, WorkspaceItem } from "@/lib/types";

const FILTERS: { label: string; value: JobType | "all" }[] = [
  { label: "전체", value: "all" },
  { label: "상세페이지", value: "detail_page" },
  { label: "블로그", value: "blog" },
  { label: "상품등록", value: "product_reg" },
];

// 생성 중인 카드가 있을 때만 폴링한다.
const POLL_MS = 1500;

export default function WorksPage() {
  const router = useRouter();
  const [filter, setFilter] = useState<JobType | "all">("all");
  const [items, setItems] = useState<WorkspaceItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  // 올리면 목록을 다시 불러온다 (폴링·삭제 실패 복구).
  const [reloadKey, setReloadKey] = useState(0);

  const reload = () => setReloadKey((k) => k + 1);

  useEffect(() => {
    let alive = true;
    api
      .workspace(filter === "all" ? undefined : filter)
      .then((next) => {
        if (!alive) return;
        setItems(next);
        setError(null);
      })
      .catch((err) => {
        if (!alive) return;
        setError(err instanceof ApiError ? err.message : "작업 목록을 불러올 수 없습니다.");
        // 목록을 비우지는 않는다 — 이미 보고 있던 카드가 사라지면 더 혼란스럽다.
        setItems((prev) => prev ?? []);
      });
    return () => {
      alive = false;
    };
  }, [filter, reloadKey]);

  // 생성 중 카드가 있을 때만 폴링한다. 끝나면 자동으로 일반 카드가 된다.
  useEffect(() => {
    if (!items?.some((i) => i.status === "queued" || i.status === "running")) return;
    const timer = setTimeout(reload, POLL_MS);
    return () => clearTimeout(timer);
  }, [items]);

  const remove = async (item: WorkspaceItem) => {
    if (!window.confirm(`'${item.title}'을(를) 삭제할까요? 되돌릴 수 없습니다.`)) return;
    // 낙관적으로 지우고, 실패하면 서버 상태로 되돌린다.
    setItems((prev) => prev?.filter((i) => i.job_id !== item.job_id) ?? null);
    try {
      await api.deleteWorkspaceItem(item.job_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "삭제하지 못했습니다.");
      reload();
    }
  };

  const rename = async (item: WorkspaceItem, title: string) => {
    // 낙관적 반영 후 저장. 문서와 상품등록은 저장하는 곳이 다르다.
    setItems((prev) =>
      prev?.map((i) => (i.job_id === item.job_id ? { ...i, title } : i)) ?? null,
    );
    try {
      if (item.type === "product_reg" && item.product_draft_id) {
        await api.patchProductDraft(item.product_draft_id, { title });
      } else if (item.document_id) {
        await api.patchDocument(item.document_id, { title });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "이름을 바꾸지 못했습니다.");
      reload();
    }
  };

  const retry = async (item: WorkspaceItem) => {
    setRetryingId(item.job_id);
    setError(null);
    try {
      const job = await api.retryJob(item.job_id);
      router.push(`/jobs/${job.id}?type=${job.type}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "다시 시도하지 못했습니다.");
      setRetryingId(null);
    }
  };

  const empty = items !== null && items.length === 0;

  return (
    <>
      <TopNav />
      <div className="px-14 pt-11 pb-16">
        <h1 className="m-0 mb-1.5 text-[30px] font-bold text-fg" style={{ letterSpacing: "-0.02em" }}>
          내 작업
        </h1>
        <p className="m-0 mb-[26px] text-[14px] text-muted">
          진행 중인 작업과 완성된 결과물을 확인하고 관리하세요
        </p>

        <div className="flex flex-col gap-5 rounded-xl border border-line bg-inset p-[26px]">
          <div className="flex gap-2 overflow-x-auto">
            {FILTERS.map((f) => {
              const on = filter === f.value;
              return (
                <button
                  key={f.value}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setFilter(f.value)}
                  className={`flex-none rounded-full px-4 py-2 text-[13px] transition-ui ${
                    on
                      ? "grad font-semibold text-white hover:brightness-110"
                      : "border border-line text-muted hover:border-line-soft hover:text-fg"
                  }`}
                >
                  {f.label}
                </button>
              );
            })}
          </div>

          {error && (
            <p
              role="alert"
              className="m-0 rounded-[10px] border border-danger/40 bg-[#2a1a1e] px-4 py-3 text-[13px] text-danger"
            >
              {error}
            </p>
          )}

          {items === null ? (
            <>
              <span className="text-[12.5px] text-muted">불러오는 중…</span>
              <ul className="grid grid-cols-2 gap-[18px] min-[820px]:grid-cols-2 min-[1100px]:grid-cols-3 min-[1440px]:grid-cols-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <li
                    key={i}
                    className="h-[520px] rounded-xl border border-line bg-surface"
                    aria-hidden
                  />
                ))}
              </ul>
            </>
          ) : empty ? (
            <EmptyState filtered={filter !== "all"} onClear={() => setFilter("all")} />
          ) : (
            <>
              <span className="text-[12.5px] text-muted">{items.length}개의 파일</span>
              <ul className="grid grid-cols-1 gap-[18px] min-[820px]:grid-cols-2 min-[1100px]:grid-cols-3 min-[1440px]:grid-cols-4">
                {items.map((item) => (
                  <WorkCard
                    key={item.job_id}
                    item={item}
                    onDelete={remove}
                    onRetry={retry}
                    onRename={rename}
                    retrying={retryingId === item.job_id}
                  />
                ))}
              </ul>
              <p className="m-0 py-3.5 text-center text-[12.5px] text-dim">
                모든 파일을 불러왔습니다.
              </p>
            </>
          )}
        </div>
      </div>
    </>
  );
}

/** 프레임 5b — 빈 상태. */
function EmptyState({ filtered, onClear }: { filtered: boolean; onClear: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 px-6 py-16 text-center">
      <div className="size-[110px] rounded-xl border border-line bg-[#1F1F26]" aria-hidden />
      <span className="text-[17px] font-bold text-fg">
        {filtered ? "이 종류의 작업이 아직 없어요" : "아직 만든 작업이 없어요"}
      </span>
      <span className="text-[13px] text-muted">제품 사진 한 장이면 3분 만에 시작할 수 있어요.</span>
      {filtered ? (
        <button
          type="button"
          onClick={onClear}
          className="mt-1 rounded-[10px] border border-line px-6 py-3 text-[14px] text-fg transition-ui hover:border-line-soft hover:bg-[#1b1b21]"
        >
          전체 보기
        </button>
      ) : (
        <ButtonLink
          href="/detail/new"
          variant="primary"
          className="mt-1 px-6 py-[13px] text-[14px]"
        >
          첫 상세페이지 만들기 →
        </ButtonLink>
      )}
    </div>
  );
}
