"use client";

import { Check, ExternalLink } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { TopNav } from "@/components/TopNav";
import { ApiError, api } from "@/lib/api";
import { assetUrl } from "@/lib/env";
import type { ProductDraft } from "@/lib/types";

// 판매자센터 상품 조회/수정. 스토어 주소를 몰라도 방금 등록한 상품을 여기서 볼 수 있다.
const SELLER_CENTER_PRODUCTS = "https://sell.smartstore.naver.com/#/products/origin-list";

/** 등록 완료 화면. 4c 의 등록 버튼과 자동 등록 모두 성공하면 여기로 온다. */
export default function ProductDonePage() {
  const { draftId } = useParams<{ draftId: string }>();
  const router = useRouter();
  const [draft, setDraft] = useState<ProductDraft | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!draftId) return;
    let alive = true;
    api
      .getProductDraft(draftId)
      .then((d) => {
        if (!alive) return;
        // 자동 등록이 실패했으면 사유가 보이는 검토 화면(4c)으로 보낸다.
        if (d.status !== "registered") {
          router.replace(`/product/${draftId}`);
          return;
        }
        setDraft(d);
      })
      .catch(
        (err) =>
          alive &&
          setError(err instanceof ApiError ? err.message : "등록 정보를 불러올 수 없습니다."),
      );
    return () => {
      alive = false;
    };
  }, [draftId, router]);

  if (error) {
    return (
      <>
        <TopNav />
        <div className="flex flex-col items-center gap-4 px-6 pt-32 text-center">
          <p className="m-0 text-[15px] text-danger">{error}</p>
          <Link
            href="/product"
            className="rounded-[10px] border border-line px-4 py-2.5 text-[13px] text-fg transition-ui hover:border-line-soft"
          >
            상품등록 처음으로
          </Link>
        </div>
      </>
    );
  }

  if (!draft) {
    return (
      <>
        <TopNav />
        <div className="flex justify-center px-6 pt-[100px]">
          <div className="h-[420px] w-full max-w-[560px] rounded-xl border border-line bg-inset" />
        </div>
      </>
    );
  }

  const image = draft.representative_image_url ?? draft.image_urls[0] ?? null;
  const when = draft.registered_at
    ? new Date(draft.registered_at).toLocaleString("ko-KR")
    : "방금";

  return (
    <>
      <TopNav />
      <div className="flex justify-center px-6 pt-[88px] pb-[110px]">
        <div className="flex w-full max-w-[560px] flex-col items-center gap-7">
          <div className="flex flex-col items-center gap-4 text-center">
            <span className="flex size-[64px] items-center justify-center rounded-full bg-success text-white">
              <Check className="size-8" strokeWidth={3} />
            </span>
            <h1 className="m-0 text-[28px] font-bold text-fg" style={{ letterSpacing: "-0.02em" }}>
              상품 등록에 성공했습니다
            </h1>
            <p className="m-0 text-[14px] leading-[1.7] text-muted">
              네이버 스마트스토어에 상품이 올라갔어요.
              <br />
              판매자센터에서 바로 확인할 수 있습니다.
            </p>
          </div>

          <section className="flex w-full flex-col gap-5 rounded-xl border border-[#2E7D5B] bg-[#132a20] p-[22px]">
            <div className="flex items-center gap-4">
              <div className="relative size-[76px] flex-none overflow-hidden rounded-[10px] bg-ph">
                {image && (
                  <Image
                    src={assetUrl(image)!}
                    alt="대표 이미지"
                    fill
                    sizes="76px"
                    className="object-cover"
                    unoptimized
                  />
                )}
              </div>
              <div className="flex min-w-0 flex-col gap-1">
                <span className="text-[15px] font-bold break-keep text-fg">{draft.product_name}</span>
                {draft.price != null && (
                  <span className="text-[14px] text-fg">
                    {draft.price.toLocaleString("ko-KR")}원
                  </span>
                )}
              </div>
            </div>

            <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 border-t border-[#2E7D5B]/40 pt-4 text-[13px]">
              <dt className="text-muted">상품번호</dt>
              <dd className="m-0 text-right font-semibold text-fg">
                {draft.naver_origin_product_no}
              </dd>
              {draft.naver_channel_product_no && (
                <>
                  <dt className="text-muted">채널상품번호</dt>
                  <dd className="m-0 text-right text-fg">{draft.naver_channel_product_no}</dd>
                </>
              )}
              {draft.selected_category && (
                <>
                  <dt className="text-muted">카테고리</dt>
                  <dd className="m-0 text-right text-fg">{draft.selected_category}</dd>
                </>
              )}
              <dt className="text-muted">등록 시각</dt>
              <dd className="m-0 text-right text-fg">{when}</dd>
            </dl>
          </section>

          <div className="flex w-full flex-col gap-2.5">
            <a
              href={SELLER_CENTER_PRODUCTS}
              target="_blank"
              rel="noopener noreferrer"
              className="grad flex items-center justify-center gap-2 rounded-xl py-4 text-[15px] font-bold text-white transition-ui hover:brightness-110"
            >
              스마트스토어 판매자센터에서 보기
              <ExternalLink className="size-4" />
            </a>
            <div className="grid grid-cols-3 gap-2.5">
              {[
                { href: `/product/${draft.id}`, label: "등록 내용 보기·수정" },
                { href: "/product", label: "새 상품 등록" },
                { href: "/works", label: "내 작업" },
              ].map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  className="rounded-xl border border-line bg-surface py-3.5 text-center text-[13.5px] text-fg transition-ui hover:border-line-soft hover:bg-[#1b1b21]"
                >
                  {l.label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
