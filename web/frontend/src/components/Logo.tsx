/**
 * 로고마크 — 교차한 두 개의 해머.
 * fill/stroke 가 전부 currentColor 라 부모의 color 만 바꾸면 색이 따라온다.
 */
export function LogoMark({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 200 200"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="스마트한 스미스 씨"
      className={`block flex-none ${className}`}
      style={{ width: size, height: size, color: "#9184d9" }}
    >
      <g
        transform="translate(100,100) scale(0.9)"
        fill="currentColor"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeLinecap="round"
      >
        <g transform="rotate(-42)">
          <path d="M0,-85 L0,105" fill="none" strokeWidth="15" />
          <path d="M-21,-90 L1,-90 L45,-81 L45,-63 L1,-54 L-21,-54 Z" strokeWidth="10" />
        </g>
        <g transform="rotate(42)">
          <path d="M0,-85 L0,105" fill="none" strokeWidth="15" />
          <path d="M-25,-90 L25,-90 L25,-54 L-25,-54 Z" strokeWidth="14" />
        </g>
      </g>
    </svg>
  );
}

export function Wordmark({ size = 16 }: { size?: number }) {
  return (
    <span
      className="font-bold text-fg"
      style={{ fontSize: size, letterSpacing: "-0.01em" }}
    >
      스마트한 스미스 씨
    </span>
  );
}
