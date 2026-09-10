"use client";

import { useEffect } from "react";

/** 열린 팝오버/드롭다운을 Esc 로 닫는다. 백드롭 클릭만으로는 키보드 사용자가 빠져나갈 수 없다. */
export function useEscape(open: boolean, close: () => void) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);
}
