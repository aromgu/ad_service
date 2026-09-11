/** 원형 진행 인디케이터 — conic-gradient 각도를 실제 진행률로 계산한다. */
export function ProgressRing({ progress }: { progress: number }) {
  const pct = Math.min(Math.max(progress, 0), 100);
  const deg = (pct / 100) * 360;
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      className="relative size-[104px] rounded-full"
      style={{
        background: `conic-gradient(var(--color-violet) 0deg, var(--color-blue) ${deg}deg, var(--color-ph) ${deg}deg 360deg)`,
        transition: "background 300ms linear",
      }}
    >
      <div className="absolute inset-[9px] flex items-center justify-center rounded-full bg-ink text-[20px] font-bold text-fg">
        {Math.round(pct)}%
      </div>
    </div>
  );
}
