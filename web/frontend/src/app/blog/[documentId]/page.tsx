"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { BLOG_CANVAS } from "@/components/editor/DocumentCanvas";
import { EditorShell } from "@/components/editor/EditorShell";
import { API_BASE } from "@/lib/env";
import type { DocumentModel, Section } from "@/lib/types";

/** 문서 글자 수 — 상단 바 지표. */
function charCount(doc: DocumentModel | null): string {
  if (!doc) return "…";
  const n = doc.sections
    .filter((s) => s.visible !== false)
    .reduce((sum, s) => sum + textOf(s).length, 0);
  return `${n.toLocaleString("ko-KR")}자`;
}

function textOf(s: Section): string {
  const c = s.content;
  return [c.text, ...(c.lines ?? []), c.prefix, c.value, c.suffix].filter(Boolean).join(" ");
}

/** 네이버 블로그 편집기에 붙여넣을 수 있는 최소 HTML. */
function toHtml(doc: DocumentModel): string {
  const esc = (t: string) =>
    t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const body = doc.sections
    .filter((s) => s.visible !== false)
    .map((s) => {
      const c = s.content;
      switch (s.type) {
        case "eyebrow":
          return `<p><em>${esc(c.text ?? "")}</em></p>`;
        case "headline":
          return `<h1>${(c.lines ?? []).map(esc).join("<br>")}</h1>`;
        case "heading":
          return `<h2>${esc(c.text ?? "")}</h2>`;
        case "paragraph":
        case "subclaim":
          return `<p>${esc(c.text ?? "")}</p>`;
        case "stat":
          return `<p>${esc(c.prefix ?? "")} <strong>${esc(c.value ?? "")}</strong> ${esc(c.suffix ?? "")}</p>`;
        case "image":
          return c.url
            ? `<p><img src="${API_BASE}${c.url}" alt="${esc(c.alt ?? "")}"></p>`
            : "";
        default:
          return "";
      }
    })
    .filter(Boolean)
    .join("\n");

  return `<article>\n${body}\n</article>`;
}

/** 프레임 3c — 블로그 에디터. */
export default function BlogEditorPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const [copyState, setCopyState] = useState<"idle" | "done" | "failed">("idle");

  return (
    <EditorShell
      documentId={documentId}
      canvas={BLOG_CANVAS}
      styleChip="기본 블로그"
      metric={charCount}
      backTo="/blog"
      topBarExtra={(doc) => (
        <button
          type="button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(toHtml(doc));
              setCopyState("done");
            } catch {
              // 클립보드 접근이 막힌 브라우저/컨텍스트에서도 사용자가 알 수 있게 한다.
              setCopyState("failed");
            }
            setTimeout(() => setCopyState("idle"), 2000);
          }}
          className={`rounded-lg border px-3 py-1.5 text-[12.5px] transition-ui ${
            copyState === "failed"
              ? "border-danger/60 text-danger"
              : "border-line text-fg hover:border-line-soft hover:bg-[#1b1b21]"
          }`}
        >
          {copyState === "done" ? "복사됨" : copyState === "failed" ? "복사 실패" : "HTML 복사"}
        </button>
      )}
    />
  );
}
