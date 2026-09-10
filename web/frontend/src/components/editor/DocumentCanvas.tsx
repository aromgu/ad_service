"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import { assetUrl } from "@/lib/env";
import type { Section } from "@/lib/types";

import { InlineToolbar } from "./InlineToolbar";

export interface CanvasSize {
  width: number;
  paddingY: number;
  paddingX: number;
  gap: number;
}

export const DETAIL_CANVAS: CanvasSize = { width: 860, paddingY: 56, paddingX: 64, gap: 22 };
export const BLOG_CANVAS: CanvasSize = { width: 820, paddingY: 52, paddingX: 60, gap: 20 };

interface CanvasProps {
  sections: Section[];
  size?: CanvasSize;
  editMode: boolean;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onPatchContent: (id: string, content: Partial<Section["content"]>) => void;
  onDelete: (id: string) => void;
  onReplaceImage: (id: string, file: File) => void;
}

/** 생성된 문서 캔버스. 보기 모드에서는 읽기 전용, 편집 모드에서는 블록 선택·인라인 편집. */
export function DocumentCanvas({
  sections,
  size = DETAIL_CANVAS,
  editMode,
  selectedId,
  onSelect,
  onPatchContent,
  onDelete,
  onReplaceImage,
}: CanvasProps) {
  return (
    <div
      className="flex flex-col rounded-[4px] border border-paper-line bg-paper"
      style={{
        width: size.width,
        gap: size.gap,
        padding: `${size.paddingY}px ${size.paddingX}px`,
      }}
      onClick={() => editMode && onSelect(null)}
    >
      {sections
        .filter((s) => s.visible !== false)
        .map((section) => (
          <Block
            key={section.id}
            section={section}
            editMode={editMode}
            selected={selectedId === section.id}
            onSelect={onSelect}
            onPatchContent={onPatchContent}
            onDelete={onDelete}
            onReplaceImage={onReplaceImage}
          />
        ))}
    </div>
  );
}

function Block({
  section,
  editMode,
  selected,
  onSelect,
  onPatchContent,
  onDelete,
  onReplaceImage,
}: {
  section: Section;
  editMode: boolean;
  selected: boolean;
} & Pick<CanvasProps, "onSelect" | "onPatchContent" | "onDelete" | "onReplaceImage">) {
  const editable = editMode && section.type !== "image";

  return (
    <div
      onClick={(e) => {
        if (!editMode) return;
        e.stopPropagation();
        onSelect(section.id);
      }}
      className={`relative rounded-[2px] ${
        selected ? "mt-11 p-2.5" : editable ? "cursor-text" : ""
      }`}
      /* 상단 마진 44px 는 플로팅 툴바가 eyebrow 를 가리지 않게 하는 여백 */
      style={selected ? { outline: "2px solid var(--color-blue)" } : undefined}
    >
      {selected && editable && (
        <InlineToolbar
          section={section}
          onPatch={(c) => onPatchContent(section.id, c)}
          onDelete={() => onDelete(section.id)}
        />
      )}
      <SectionBody
        section={section}
        editable={editable}
        onPatchContent={onPatchContent}
        onReplaceImage={onReplaceImage}
        editMode={editMode}
      />
    </div>
  );
}

function SectionBody({
  section,
  editable,
  editMode,
  onPatchContent,
  onReplaceImage,
}: {
  section: Section;
  editable: boolean;
  editMode: boolean;
} & Pick<CanvasProps, "onPatchContent" | "onReplaceImage">) {
  const { content } = section;

  switch (section.type) {
    case "eyebrow": {
      // 0.22em 자간은 대문자 라틴 기준. 한글/한자는 그대로 두면 글자가 흩어진다.
      const text = content.text ?? "";
      const latin = /^[\x00-\x7F\s™®©]*$/.test(text);
      return (
        <EditableText
          as="span"
          editable={editable}
          value={text}
          onCommit={(next) => onPatchContent(section.id, { text: next })}
          className="block text-[12px] text-paper-eyebrow"
          style={{ letterSpacing: content.letterSpacing ?? (latin ? "0.22em" : "0.06em") }}
        />
      );
    }

    case "headline": {
      const size = content.fontSize ?? 42;
      return (
        <EditableText
          as="h2"
          editable={editable}
          value={(content.lines ?? []).join("\n")}
          onCommit={(text) =>
            onPatchContent(section.id, { lines: text.split("\n").filter((l) => l !== "") })
          }
          className="m-0"
          style={{
            fontSize: size,
            lineHeight: size >= 40 ? 1.34 : 1.32,
            fontWeight: content.bold === false ? 400 : 700,
            fontStyle: content.italic ? "italic" : "normal",
            textAlign: content.align ?? "left",
            color: content.color ?? "#17171A",
            letterSpacing: "-0.02em",
            whiteSpace: "pre-wrap",
          }}
        />
      );
    }

    case "stat":
      return (
        <p
          className="m-0 text-[17px] text-paper-body"
          style={{ textAlign: content.align ?? "left" }}
        >
          <EditableText
            as="span"
            editable={editable}
            value={content.prefix ?? ""}
            onCommit={(prefix) => onPatchContent(section.id, { prefix })}
          />{" "}
          <strong className="text-[22px]" style={{ color: content.color ?? undefined }}>
            {content.value}
          </strong>{" "}
          <EditableText
            as="span"
            editable={editable}
            value={content.suffix ?? ""}
            onCommit={(suffix) => onPatchContent(section.id, { suffix })}
          />
        </p>
      );

    case "subclaim":
      return (
        <EditableText
          as="p"
          editable={editable}
          value={content.text ?? ""}
          onCommit={(text) => onPatchContent(section.id, { text })}
          className="m-0 text-[14px] text-paper-muted"
          style={{
            textAlign: content.align ?? "left",
            fontSize: content.fontSize ?? 14,
            fontWeight: content.bold ? 700 : 400,
            fontStyle: content.italic ? "italic" : "normal",
            color: content.color ?? undefined,
          }}
        />
      );

    case "image":
      return (
        <ImageBlock
          section={section}
          editMode={editMode}
          onReplaceImage={onReplaceImage}
          onPatchContent={onPatchContent}
        />
      );

    case "paragraph":
      return (
        <EditableText
          as="p"
          editable={editable}
          value={content.text ?? ""}
          onCommit={(text) => onPatchContent(section.id, { text })}
          className="m-0 text-paper-body"
          style={{
            fontSize: content.fontSize ?? 15,
            lineHeight: 1.85,
            textAlign: content.align ?? "left",
            fontWeight: content.bold ? 700 : 400,
            fontStyle: content.italic ? "italic" : "normal",
            color: content.color ?? undefined,
            whiteSpace: "pre-wrap",
          }}
        />
      );

    case "heading":
      return (
        <EditableText
          as="h2"
          editable={editable}
          value={content.text ?? ""}
          onCommit={(text) => onPatchContent(section.id, { text })}
          className="mt-2.5 mb-0 text-paper-fg"
          style={{
            fontSize: content.fontSize ?? 20,
            fontWeight: content.bold === false ? 400 : 700,
            fontStyle: content.italic ? "italic" : "normal",
            textAlign: content.align ?? "left",
            color: content.color ?? undefined,
          }}
        />
      );

    case "note":
      return (
        <div className="flex h-[60px] items-center justify-center text-[12px] text-[#A0A098]">
          {content.text}
        </div>
      );

    default:
      return null;
  }
}

function ImageBlock({
  section,
  editMode,
  onReplaceImage,
  onPatchContent,
}: {
  section: Section;
  editMode: boolean;
} & Pick<CanvasProps, "onReplaceImage" | "onPatchContent">) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [hover, setHover] = useState(false);
  const url = assetUrl(section.content.url);
  const height = section.content.height ?? 360;

  // 크롭: 지정된 높이 프리셋을 돌며 노출 영역을 바꾼다(원본은 그대로 두고 프레이밍만 조정).
  const cycleFraming = () => {
    const presets = [360, 300, 240, 460];
    const next = presets[(presets.indexOf(height) + 1) % presets.length];
    onPatchContent(section.id, { height: next });
  };

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className="relative overflow-hidden rounded-[2px] bg-paper-ph"
      style={{ height }}
    >
      {url ? (
        <Image
          src={url}
          alt={section.content.alt ?? "제품 사진"}
          fill
          sizes="860px"
          className="object-cover"
          unoptimized
        />
      ) : (
        <div className="flex h-full items-center justify-center text-[13px] text-paper-eyebrow">
          {section.content.caption ?? "제품 사진 영역"}
        </div>
      )}

      {editMode && hover && (
        <div className="absolute inset-0 flex items-center justify-center gap-2.5 bg-[rgba(11,11,15,.55)]">
          <OverlayButton onClick={() => inputRef.current?.click()}>이미지 교체</OverlayButton>
          <OverlayButton onClick={cycleFraming}>크롭</OverlayButton>
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onReplaceImage(section.id, file);
          e.target.value = "";
        }}
      />
    </div>
  );
}

function OverlayButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className="rounded-lg border border-line bg-surface px-4 py-[9px] text-[12.5px] text-fg transition-ui hover:border-line-soft hover:bg-[#1b1b21]"
    >
      {children}
    </button>
  );
}

/**
 * contentEditable 래퍼.
 * React 가 매 렌더마다 DOM 텍스트를 덮어쓰면 커서가 튀므로, 편집 중에는
 * 값을 다시 주입하지 않고 blur 시점에만 상위 상태로 커밋한다.
 */
function EditableText({
  as: Tag = "span",
  editable,
  value,
  onCommit,
  className,
  style,
}: {
  as?: "span" | "p" | "h2";
  editable: boolean;
  value: string;
  onCommit: (text: string) => void;
  className?: string;
  style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLElement>(null);

  // 편집 중(포커스 상태)에는 DOM 을 건드리지 않는다. 덮어쓰면 커서가 튄다.
  useEffect(() => {
    const el = ref.current;
    if (!el || !editable) return;
    if (document.activeElement === el) return;
    if (el.innerText !== value) el.innerText = value;
  }, [value, editable]);

  if (!editable) {
    return (
      <Tag className={className} style={style}>
        {value}
      </Tag>
    );
  }

  return (
    <Tag
      ref={ref as React.Ref<never>}
      contentEditable
      suppressContentEditableWarning
      onBlur={(e: React.FocusEvent<HTMLElement>) => {
        const next = e.currentTarget.innerText.replace(/\n{2,}/g, "\n").trimEnd();
        if (next !== value) onCommit(next);
      }}
      className={className}
      style={style}
    />
  );
}
