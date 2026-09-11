"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { ProgressRing } from "@/components/ProgressRing";
import { StepChecklist } from "@/components/StepChecklist";
import { TopNav } from "@/components/TopNav";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api";
import type { Job, JobType } from "@/lib/types";

const POLL_MS = 600;

/** 작업 타입별 문구 — 와이어프레임 2b · 3b · 4b */
const COPY: Record<JobType, { title: string; sub?: string; eta: string; backTo: string }> = {
  detail_page: {
    title: "상세페이지를 만들고 있어요",
    eta: "보통 40초 정도 걸려요",
    backTo: "/detail/new",
  },
  blog: {
    title: "블로그 글을 쓰고 있어요",
    eta: "보통 30초 정도 걸려요",
    backTo: "/blog",
  },
  product_reg: {
    title: "AI가 상품 정보를 분석 중이에요",
    sub: "브랜드, 카테고리, 속성을 추출하고 있습니다",
    eta: "보통 1~2분 소요됩니다 (이미지 OCR 분석 포함)",
    backTo: "/product",
  },
};

/**
 * 완료 시 이동할 곳.
 * 상품등록 자동 모드는 등록 완료 화면으로 간다. 등록이 실패했으면 그 화면이 사유가 보이는 4c 로 다시 보낸다.
 */
function destination(job: Job): string | null {
  if (job.type === "product_reg" && job.product_draft_id) {
    const review = `/product/${job.product_draft_id}`;
    return job.submit_mode === "auto" ? `${review}/done` : review;
  }
  if (!job.document_id) return null;
  return job.type === "blog" ? `/blog/${job.document_id}` : `/detail/${job.document_id}`;
}

const JOB_TYPES: JobType[] = ["detail_page", "blog", "product_reg"];

function GeneratingBody() {
  const { jobId } = useParams<{ jobId: string }>();
  const router = useRouter();
  // 첫 폴링이 돌아오기 전까지 쓸 타입. 없으면 문구를 비워 둔다 —
  // 기본값을 상세페이지로 두면 블로그·상품등록에서 엉뚱한 제목이 잠깐 스친다.
  const hinted = useSearchParams().get("type");
  const initialType = JOB_TYPES.includes(hinted as JobType) ? (hinted as JobType) : null;

  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [canceling, setCanceling] = useState(false);

  const type = job?.type ?? initialType;
  const copy = type ? COPY[type] : null;
  // 작업이 끝났으면 리다이렉트가 진행 중이므로 취소 버튼을 잠근다.
  const settled = job != null && job.status !== "queued" && job.status !== "running";

  useEffect(() => {
    if (!jobId) return;
    let timer: ReturnType<typeof setTimeout>;
    let alive = true;

    const tick = async () => {
      try {
        const next = await api.getJob(jobId);
        if (!alive) return;
        setJob(next);

        if (next.status === "done") {
          const to = destination(next);
          if (to) {
            router.replace(to);
            return;
          }
          setError("생성은 끝났지만 결과를 찾을 수 없습니다.");
          return;
        }
        if (next.status === "failed") {
          // 실패는 내 작업의 실패 카드 상태로 귀결된다.
          router.replace("/works?failed=1");
          return;
        }
        if (next.status === "canceled") {
          router.replace(COPY[next.type].backTo);
          return;
        }
        timer = setTimeout(tick, POLL_MS);
      } catch (err) {
        if (!alive) return;
        setError(err instanceof ApiError ? err.message : "작업 상태를 가져올 수 없습니다.");
      }
    };

    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [jobId, router]);

  async function cancel() {
    if (!window.confirm("생성을 중단하고 입력 화면으로 돌아갈까요?")) return;
    setCanceling(true);
    try {
      await api.cancelJob(jobId);
      router.replace(copy?.backTo ?? "/");
    } catch {
      setCanceling(false);
    }
  }

  return (
    <>
      <TopNav />
      <div className="flex flex-col items-center gap-[30px] px-10 pt-[100px] pb-[110px]">
        <ProgressRing progress={job?.progress ?? 0} />

        <div className="flex flex-col items-center gap-2.5 text-center">
          <h1 className="m-0 text-[28px] font-bold text-fg" style={{ letterSpacing: "-0.02em" }}>
            {copy?.title ?? "생성을 준비하고 있어요"}
          </h1>
          {copy?.sub && <p className="m-0 text-[14px] text-muted">{copy.sub}</p>}
        </div>

        {job ? (
          <StepChecklist steps={job.steps} />
        ) : (
          // 첫 상태가 오기 전 자리만 잡아 둔다 (화면이 튀지 않게). 회색 상자는 그리지 않는다.
          <div className="h-[248px] w-[420px]" aria-hidden />
        )}

        {error && (
          <p role="alert" className="m-0 text-[13px] text-danger">
            {error}
          </p>
        )}

        <div className="flex flex-col items-center gap-4">
          <span className="text-[13px] text-muted">{copy?.eta ?? "\u00a0"}</span>
          <Button
            type="button"
            variant="ghost"
            onClick={cancel}
            disabled={canceling || settled}
            className="px-6 py-2.5 text-[13.5px]"
          >
            취소
          </Button>
        </div>
      </div>
    </>
  );
}

export default function GeneratingPage() {
  return (
    <Suspense fallback={null}>
      <GeneratingBody />
    </Suspense>
  );
}
