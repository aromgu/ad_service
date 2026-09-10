"use client";

import { useParams, useRouter } from "next/navigation";

import { EditorShell } from "@/components/editor/EditorShell";
import { DETAIL_CANVAS } from "@/components/editor/DocumentCanvas";

/** 프레임 2c(보기) · 2d(편집). Edit 토글로 전환된다. */
export default function DetailEditorPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const router = useRouter();

  return (
    <EditorShell
      documentId={documentId}
      canvas={DETAIL_CANVAS}
      styleChip="Modernist"
      metric={() => "100%"}
      backTo="/detail/new"
      floatingCta={(doc) => (
        // 상세페이지 입력값·이미지를 그대로 상품등록으로 넘긴다 (4a 는 건너뛴다).
        <div className="absolute right-7 bottom-6 z-[3] flex flex-col items-end gap-2">
          <span className="rounded-lg border border-line bg-[rgba(11,11,15,.9)] px-[13px] py-2 text-[11.5px] text-muted">
            입력한 상품 정보와 이미지를 그대로 이어서 씁니다
          </span>
          <button
            type="button"
            onClick={() => router.push(`/product?from=${doc.id}`)}
            className="grad rounded-xl px-[22px] py-3.5 text-[14.5px] font-bold text-white transition-ui hover:brightness-110"
          >
            이 상세페이지로 상품등록 →
          </button>
        </div>
      )}
    />
  );
}
