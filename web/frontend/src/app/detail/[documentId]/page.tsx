"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { EditorShell } from "@/components/editor/EditorShell";
import { DETAIL_CANVAS } from "@/components/editor/DocumentCanvas";
import { RequiredMark } from "@/components/ui/Field";
import { useEscape } from "@/lib/use-dismiss";
import type { DocumentModel } from "@/lib/types";

/** 프레임 2c(보기) · 2d(편집). Edit 토글로 전환된다. */
export default function DetailEditorPage() {
  const { documentId } = useParams<{ documentId: string }>();

  return (
    <EditorShell
      documentId={documentId}
      canvas={DETAIL_CANVAS}
      docType="detail_page"
      hrefFor={(id) => `/detail/${id}`}
      backTo="/detail/new"
      floatingCta={(doc) => <ProductRegisterCta key={doc.id} doc={doc} />}
    />
  );
}

const priceKey = (docId: string) => `smith:detail-price:${docId}`;

/** 이 상세페이지에 정해 둔 판매가. Edit 토글로 버튼이 사라졌다 돌아와도 유지된다. */
function readPrice(docId: string): number | null {
  try {
    const n = Number(localStorage.getItem(priceKey(docId)));
    return Number.isInteger(n) && n > 0 ? n : null;
  } catch {
    return null;
  }
}

/**
 * 상세페이지 입력값·이미지를 그대로 상품등록으로 넘긴다 (4a 는 건너뛴다).
 * 판매가는 네이버 등록에 반드시 필요해서 넘기기 전에 여기서 정한다.
 */
function ProductRegisterCta({ doc }: { doc: DocumentModel }) {
  const router = useRouter();
  // 문서를 불러온 뒤에만 그려지므로 서버 렌더와 어긋날 일이 없다.
  const [price, setPrice] = useState<number | null>(() => readPrice(doc.id));
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [hint, setHint] = useState<string | null>(null);

  const close = useCallback(() => {
    setOpen(false);
    setHint(null);
  }, []);
  useEscape(open, close);

  const openEditor = (message: string | null = null) => {
    setInput(price ? String(price) : "");
    setHint(message);
    setOpen(true);
  };

  const confirm = () => {
    const n = Number(input);
    if (!input || !Number.isInteger(n) || n <= 0) {
      setHint("판매가를 1원 이상 숫자로 입력해 주세요.");
      return;
    }
    setPrice(n);
    try {
      localStorage.setItem(priceKey(doc.id), String(n));
    } catch {
      // 저장이 막힌 브라우저에서도 이번 화면에서는 그대로 쓴다.
    }
    close();
  };

  const goRegister = () => {
    if (!price) {
      openEditor("판매가를 먼저 설정해 주세요.");
      return;
    }
    router.push(`/product?from=${doc.id}&price=${price}`);
  };

  return (
    <div className="absolute right-7 bottom-6 z-[3] flex flex-col items-end gap-2">
      {open && (
        <form
          aria-label="판매가 설정"
          // 브라우저 기본 검증 대신 confirm() 의 한국어 안내를 쓴다.
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            confirm();
          }}
          className="flex w-[260px] flex-col gap-2.5 rounded-xl border border-line bg-surface p-4 shadow-[0_12px_32px_rgba(0,0,0,.45)]"
        >
          <label htmlFor="cta-price" className="text-[12.5px] font-semibold text-fg">
            판매가 <RequiredMark />
          </label>
          <div className="flex items-center rounded-[10px] border border-line bg-inset pr-[13px] transition-ui hover:border-line-soft focus-within:border-accent-line">
            <input
              id="cta-price"
              type="number"
              inputMode="numeric"
              min={1}
              autoFocus
              value={input}
              placeholder="예: 19900"
              onChange={(e) => setInput(e.target.value)}
              className="w-full bg-transparent px-[13px] py-[11px] text-[13.5px] text-fg outline-none"
            />
            <span className="flex-none text-[12px] text-muted">원</span>
          </div>
          {hint && (
            <span role="alert" className="text-[12px] text-danger">
              {hint}
            </span>
          )}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={close}
              className="rounded-lg border border-line px-3.5 py-2 text-[12.5px] text-muted transition-ui hover:border-line-soft hover:text-fg"
            >
              취소
            </button>
            <button
              type="submit"
              className="grad rounded-lg px-4 py-2 text-[12.5px] font-bold text-white transition-ui hover:brightness-110"
            >
              확인
            </button>
          </div>
        </form>
      )}

      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => (open ? close() : openEditor())}
          className="rounded-xl border border-line bg-surface px-[18px] py-3.5 text-[14px] font-semibold text-fg transition-ui hover:border-line-soft hover:bg-[#1b1b21]"
        >
          {price ? `판매가 ${price.toLocaleString("ko-KR")}원` : "가격 설정"}
        </button>
        <button
          type="button"
          onClick={goRegister}
          className="grad rounded-xl px-[22px] py-3.5 text-[14.5px] font-bold text-white transition-ui hover:brightness-110"
        >
          이 상세페이지로 상품등록 →
        </button>
      </div>
    </div>
  );
}
