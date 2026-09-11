import { Check } from "lucide-react";

import type { JobStep } from "@/lib/types";

/** 생성 중 화면의 스텝 체크리스트. 서버 진행 이벤트에 따라 순차 전환된다. */
export function StepChecklist({ steps }: { steps: JobStep[] }) {
  return (
    <ol className="flex w-[420px] flex-col gap-2.5">
      {steps.map((step) => {
        if (step.state === "done")
          return (
            <li
              key={step.key}
              className="flex items-center gap-3 rounded-[10px] border border-line bg-surface px-[18px] py-3.5"
            >
              <span className="flex size-[22px] items-center justify-center rounded-full bg-success text-white">
                <Check className="size-3.5" strokeWidth={3} />
              </span>
              <span className="text-[14px] text-muted">{step.label}</span>
            </li>
          );

        if (step.state === "active")
          return (
            <li
              key={step.key}
              aria-current="step"
              className="flex items-center justify-between gap-3 rounded-[10px] border border-accent-line bg-accent-bg px-[18px] py-3.5"
            >
              <div className="flex items-center gap-3">
                <span className="spin-1s block size-[22px] rounded-full border-2 border-violet border-t-transparent" />
                <span className="text-[14px] font-semibold text-fg">{step.label}</span>
              </div>
              <span className="text-[12px] text-accent">진행 중</span>
            </li>
          );

        return (
          <li
            key={step.key}
            className="flex items-center gap-3 rounded-[10px] border border-line bg-inset px-[18px] py-3.5"
          >
            <span className="block size-[22px] rounded-full border border-line" />
            <span className="text-[14px] text-dim">{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
