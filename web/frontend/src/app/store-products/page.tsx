"use client";

import { ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Loading } from "@/components/Loading";
import { TopNav } from "@/components/TopNav";
import { ButtonLink } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api";
import { SELLER_CENTER_PRODUCTS } from "@/lib/naver";
import type { StoreProduct, StoreProductPage } from "@/lib/types";

/** 네이버 판매 상태 → 화면 표시. 모르는 값은 코드 그대로 보여 준다. */
const STATUS: Record<string, { label: string; className: string }> = {
  SALE: { label: "판매중", className: "border-[#2E5A45] bg-[#132A20] text-[#5FC08D]" },
  OUTOFSTOCK: { label: "품절", className: "border-[#5A4A2E] bg-[#2A2213] text-[#E0B25F]" },
  WAIT: { label: "판매대기", className: "border-line text-muted" },
  SUSPENSION: { label: "판매중지", className: "border-line text-muted" },
  CLOSE: { label: "판매종료", className: "border-line text-muted" },
  UNADMISSION: { label: "승인대기", className: "border-line text-muted" },
  REJECTION: { label: "승인거부", className: "border-danger/40 text-danger" },
  PROHIBITION: { label: "판매금지", className: "border-danger/40 text-danger" },
};

function formatDate(value: string | null): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString("ko-KR");
}

/** 등록된 상품 관리 — 스마트스토어에 올라가 있는 상품. 로컬 DB 가 아니라 커머스 API 에서 읽는다. */
export default function StoreProductsPage() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [data, setData] = useState<StoreProductPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 상품을 여는 중이면 그 상품번호. 여는 동안 다른 줄을 누르지 못하게 한다.
  const [opening, setOpening] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .storeProducts(page)
      .then((next) => {
        if (!alive) return;
        setData(next);
        setError(null);
      })
      .catch((err) => {
        if (!alive) return;
        setError(err instanceof ApiError ? err.message : "상품 목록을 불러올 수 없습니다.");
        setData((prev) => prev ?? { items: [], page, total: 0, total_pages: 0 });
      });
    return () => {
      alive = false;
    };
  }, [page]);

  const open = async (product: StoreProduct) => {
    if (opening) return;
    setOpening(product.origin_product_no);
    setError(null);
    try {
      const draft = await api.openStoreProduct(product.origin_product_no);
      router.push(`/store-products/${draft.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "상품을 열 수 없습니다.");
      setOpening(null);
    }
  };

  return (
    <>
      <TopNav />
      <div className="px-14 pt-11 pb-16">
        <div className="mb-[26px] flex items-end justify-between gap-4">
          <div>
            <h1
              className="m-0 mb-1.5 text-[30px] font-bold text-fg"
              style={{ letterSpacing: "-0.02em" }}
            >
              등록된 상품 관리
            </h1>
            <p className="m-0 text-[14px] text-muted">
              스마트스토어에 올라가 있는 상품이에요. 눌러서 수정하거나 삭제할 수 있습니다
            </p>
          </div>
          <a
            href={SELLER_CENTER_PRODUCTS}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-none items-center gap-1.5 rounded-[10px] border border-line px-4 py-2.5 text-[13px] text-fg transition-ui hover:border-line-soft hover:bg-[#1b1b21]"
          >
            판매자센터 열기
            <ExternalLink className="size-3.5" />
          </a>
        </div>

        <div className="flex flex-col gap-4 rounded-xl border border-line bg-inset p-[26px]">
          {error && (
            <p
              role="alert"
              className="m-0 rounded-[10px] border border-danger/40 bg-[#2a1a1e] px-4 py-3 text-[13px] text-danger"
            >
              {error}
            </p>
          )}

          {data === null ? (
            <Loading className="py-16" />
          ) : data.items.length === 0 ? (
            // 목록을 못 불러온 경우엔 '상품이 없다'고 말하지 않는다.
            !error && <EmptyState />
          ) : (
            <>
              <span className="text-[12.5px] text-muted">{data.total}개의 상품</span>
              <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
                {data.items.map((p) => (
                  <li key={p.origin_product_no}>
                    <ProductRow
                      product={p}
                      opening={opening === p.origin_product_no}
                      disabled={opening !== null}
                      onOpen={() => open(p)}
                    />
                  </li>
                ))}
              </ul>

              {data.total_pages > 1 && (
                <div className="flex items-center justify-center gap-3 pt-2">
                  <button
                    type="button"
                    aria-label="이전 페이지"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                    className="flex size-9 items-center justify-center rounded-[10px] border border-line text-fg transition-ui hover:border-line-soft disabled:opacity-40"
                  >
                    <ChevronLeft className="size-4" />
                  </button>
                  <span className="text-[13px] text-muted">
                    {page} / {data.total_pages}
                  </span>
                  <button
                    type="button"
                    aria-label="다음 페이지"
                    disabled={page >= data.total_pages}
                    onClick={() => setPage((p) => p + 1)}
                    className="flex size-9 items-center justify-center rounded-[10px] border border-line text-fg transition-ui hover:border-line-soft disabled:opacity-40"
                  >
                    <ChevronRight className="size-4" />
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}

function ProductRow({
  product: p,
  opening,
  disabled,
  onOpen,
}: {
  product: StoreProduct;
  opening: boolean;
  disabled: boolean;
  onOpen: () => void;
}) {
  const status = STATUS[p.status_type] ?? {
    label: p.status_type || "상태 없음",
    className: "border-line text-muted",
  };
  const registered = formatDate(p.registered_at);

  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={disabled}
      className="flex w-full items-center gap-4 rounded-xl border border-line bg-surface p-3.5 text-left transition-ui hover:border-line-soft hover:bg-[#1b1b21] disabled:cursor-wait disabled:opacity-60"
    >
      <div className="relative size-[64px] flex-none overflow-hidden rounded-lg bg-ph">
        {p.image_url && (
          <Image src={p.image_url} alt="" fill sizes="64px" className="object-cover" unoptimized />
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="truncate text-[14px] font-semibold text-fg">
          {p.name || "이름 없는 상품"}
        </span>
        {p.category_name && (
          <span className="truncate text-[12px] text-muted">{p.category_name}</span>
        )}
        <span className="text-[11.5px] text-dim">
          상품번호 {p.origin_product_no}
          {registered && ` · ${registered} 등록`}
        </span>
      </div>

      <div className="flex flex-none flex-col items-end gap-1.5">
        <span className={`rounded-md border px-2.5 py-[3px] text-[11.5px] font-semibold ${status.className}`}>
          {status.label}
        </span>
        <span className="text-[14px] font-semibold text-fg">
          {p.sale_price != null ? `${p.sale_price.toLocaleString("ko-KR")}원` : "-"}
        </span>
        <span className="text-[11.5px] text-muted">재고 {p.stock_quantity ?? "-"}</span>
      </div>

      <span className="w-[60px] flex-none text-right text-[12.5px] text-accent">
        {opening ? "여는 중…" : "수정 →"}
      </span>
    </button>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-4 px-6 py-16 text-center">
      <span className="text-[17px] font-bold text-fg">스마트스토어에 등록된 상품이 없어요</span>
      <span className="text-[13px] text-muted">상품을 등록하면 여기에서 수정·삭제할 수 있어요.</span>
      <ButtonLink href="/product" variant="primary" className="mt-1 px-6 py-[13px] text-[14px]">
        상품 등록하러 가기 →
      </ButtonLink>
    </div>
  );
}
