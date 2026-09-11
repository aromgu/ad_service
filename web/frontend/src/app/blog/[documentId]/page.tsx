"use client";

import { useParams } from "next/navigation";

import { BLOG_CANVAS } from "@/components/editor/DocumentCanvas";
import { EditorShell } from "@/components/editor/EditorShell";
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

/** 프레임 3c — 블로그 에디터. */
export default function BlogEditorPage() {
  const { documentId } = useParams<{ documentId: string }>();

  return (
    <EditorShell
      documentId={documentId}
      canvas={BLOG_CANVAS}
      docType="blog"
      hrefFor={(id) => `/blog/${id}`}
      metric={charCount}
      backTo="/blog"
    />
  );
}
