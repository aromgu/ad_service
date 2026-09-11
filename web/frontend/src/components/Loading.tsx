/** 불러오는 중 표시. 빈 회색 상자 대신 쓴다 — 상자는 덜 만든 화면처럼 보인다. */
export function Loading({
  label = "불러오는 중…",
  className = "",
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      className={`flex flex-col items-center justify-center gap-3 text-[13px] text-muted ${className}`}
    >
      <span
        aria-hidden
        className="spin-1s block size-7 rounded-full border-[3px] border-violet border-t-transparent"
      />
      {label}
    </div>
  );
}
