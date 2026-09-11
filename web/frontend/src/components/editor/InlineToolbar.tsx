"use client";

import { AlignCenter, AlignLeft, AlignRight, Trash2 } from "lucide-react";

import type { Section } from "@/lib/types";

const ITEM =
  "rounded-md px-[7px] py-[3px] text-[11.5px] text-fg transition-ui hover:bg-ph";

/** 선택된 블록 위에 뜨는 플로팅 인라인 툴바 (편집 모드 전용). */
export function InlineToolbar({
  section,
  onPatch,
  onDelete,
}: {
  section: Section;
  onPatch: (content: Partial<Section["content"]>) => void;
  onDelete: () => void;
}) {
  const size = section.content.fontSize ?? 42;
  const align = section.content.align ?? "left";
  const accented = section.content.color === "#7C3AED";
  const AlignIcon =
    align === "center" ? AlignCenter : align === "right" ? AlignRight : AlignLeft;

  return (
    <div
      className="absolute -top-[46px] left-0 z-10 flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2 py-1.5"
      onMouseDown={(e) => e.preventDefault()} // contentEditable 포커스 유지
    >
      <span className="flex items-center gap-1.5 rounded-md bg-ph px-1.5 py-[3px] text-[11px] text-fg">
        <button
          type="button"
          aria-label="글자 크기 줄이기"
          onClick={() => onPatch({ fontSize: Math.max(size - 2, 12) })}
          className="px-0.5 hover:text-accent"
        >
          −
        </button>
        <em className="not-italic tabular-nums">{size}</em>
        <button
          type="button"
          aria-label="글자 크기 키우기"
          onClick={() => onPatch({ fontSize: Math.min(size + 2, 72) })}
          className="px-0.5 hover:text-accent"
        >
          +
        </button>
      </span>

      <Divider />
      <button
        type="button"
        aria-pressed={section.content.bold !== false}
        onClick={() => onPatch({ bold: section.content.bold === false })}
        className={`${ITEM} font-bold ${section.content.bold === false ? "text-dim" : ""}`}
      >
        B
      </button>
      <button
        type="button"
        aria-pressed={!!section.content.italic}
        onClick={() => onPatch({ italic: !section.content.italic })}
        className={`${ITEM} italic ${section.content.italic ? "text-accent" : ""}`}
      >
        I
      </button>

      <Divider />
      <button
        type="button"
        aria-label={`정렬: ${align}`}
        title={`정렬: ${align}`}
        onClick={() =>
          onPatch({
            align: align === "left" ? "center" : align === "center" ? "right" : "left",
          })
        }
        className={ITEM}
      >
        <AlignIcon className="size-3.5" />
      </button>
      <button
        type="button"
        aria-label="텍스트 색상"
        onClick={() => onPatch({ color: accented ? undefined : "#7C3AED" })}
        className={`${ITEM} flex items-center gap-1`}
      >
        A
        <em
          className="block size-2.5 rounded-[3px]"
          style={{ background: accented ? "#7C3AED" : "#17171A" }}
        />
      </button>

      <Divider />
      <button
        type="button"
        aria-label="블록 삭제"
        onClick={onDelete}
        className={`${ITEM} text-danger`}
      >
        <Trash2 className="size-3.5" />
      </button>
    </div>
  );
}

function Divider() {
  return <span className="block h-4 w-px bg-line" />;
}
