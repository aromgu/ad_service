"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";

import { ImageDropzone } from "@/components/ImageDropzone";
import { TopNav } from "@/components/TopNav";
import { Field, RequiredMark, Select, TextArea, TextInput } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { resolveAssetIds, type PickedImage } from "@/lib/images";
import type { ProductRegForm, ShippingSettings } from "@/lib/types";

const COURIERS = ["CJ대한통운", "롯데택배", "한진택배", "우체국택배", "로젠택배"] as const;

const EMPTY_SHIPPING: ShippingSettings = {
  origin_address: "",
  return_address: "",
  return_same_as_origin: true,
  shipping_fee: 3000,
  return_fee: 3000,
  exchange_fee: 6000,
  cs_phone: "",
  courier: "CJ대한통운",
};

const MAX_IMAGES = 20;

/** 쿼리로 넘어온 판매가. 숫자가 아니거나 0 이하면 없는 것으로 본다(4c 에서 입력). */
function parsePrice(raw: string | null): number | null {
  const n = Number(raw);
  return raw && Number.isInteger(n) && n > 0 ? n : null;
}

function ProductInputBody() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // 2c 에디터에서 "이 상세페이지로 상품등록"으로 넘어온 경우
  const fromDocument = searchParams.get("from");
  // 2c 에디터 '가격 설정'에서 정한 판매가
  const handoffPrice = parsePrice(searchParams.get("price"));
  // 개발 모드 StrictMode 는 effect 를 두 번 돌린다. 막지 않으면 작업이 두 개 생기고
  // 네이버에 같은 상품이 두 번 등록된다. ref 는 그 재마운트 사이에도 유지된다.
  const handoffStarted = useRef<string | null>(null);

  const [images, setImages] = useState<PickedImage[]>([]);
  const [productInfo, setProductInfo] = useState("");
  const [shipping, setShipping] = useState<ShippingSettings>(EMPTY_SHIPPING);
  const [submitting, setSubmitting] = useState<"auto" | "review" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [handoff, setHandoff] = useState(!!fromDocument);

  // 저장해 둔 배송 설정을 초기값으로 불러온다.
  useEffect(() => {
    let alive = true;
    api
      .getShippingSettings()
      .then((s) => alive && setShipping((prev) => ({ ...prev, ...s })))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  /**
   * 상세페이지에서 넘어왔다면 4a 를 건너뛴다.
   * 이미 상품명·이미지가 다 있으므로 바로 분석(4b) → 자동 등록으로 보낸다.
   */
  useEffect(() => {
    if (!fromDocument || handoffStarted.current === fromDocument) return;
    handoffStarted.current = fromDocument;
    (async () => {
      try {
        // 저장해 둔 배송 설정(CS 전화·택배사·반품비)을 그대로 쓴다.
        const saved = await api.getShippingSettings().catch(() => null);
        const job = await api.createProductJob(
          {
            product_info: "",
            shipping: { ...EMPTY_SHIPPING, ...(saved ?? {}) },
            submit_mode: "auto",
            price: handoffPrice,
          },
          [],
          fromDocument,
        );
        router.replace(`/jobs/${job.id}?type=${job.type}`);
      } catch (err) {
        setHandoff(false);
        setError(
          err instanceof ApiError
            ? `${err.message} 아래에서 직접 등록을 진행해 주세요.`
            : "상세페이지 정보를 넘기지 못했습니다.",
        );
      }
    })();
  }, [fromDocument, handoffPrice, router]);

  const valid = useMemo(
    () => images.length > 0 && shipping.origin_address.trim() !== "",
    [images, shipping.origin_address],
  );

  const set = <K extends keyof ShippingSettings>(k: K, v: ShippingSettings[K]) =>
    setShipping((prev) => ({ ...prev, [k]: v }));

  async function submit(mode: "auto" | "review") {
    if (!valid || submitting) return;
    setSubmitting(mode);
    setError(null);
    try {
      const imageIds = await resolveAssetIds(images);
      const effective: ShippingSettings = {
        ...shipping,
        return_address: shipping.return_same_as_origin
          ? shipping.origin_address
          : shipping.return_address,
      };
      // 배송 설정은 저장해 두고 다음 등록에 재사용한다.
      await api.putShippingSettings(effective).catch(() => {});

      const form: ProductRegForm = {
        product_info: productInfo.trim(),
        shipping: effective,
        submit_mode: mode,
      };
      const job = await api.createProductJob(form, imageIds);
      router.push(`/jobs/${job.id}?type=${job.type}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "등록 요청에 실패했습니다.");
      setSubmitting(null);
    }
  }

  if (handoff) {
    return (
      <div className="flex flex-col items-center gap-4 px-10 pt-[140px] pb-[160px] text-center">
        <span className="spin-1s block size-9 rounded-full border-[3px] border-violet border-t-transparent" />
        <p className="m-0 text-[15px] text-fg">상세페이지 정보를 상품등록으로 넘기고 있어요</p>
        <p className="m-0 text-[13px] text-muted">
          입력한 상품 정보와 이미지를 그대로 이어서 씁니다.
        </p>
      </div>
    );
  }

  return (
    <div className="flex justify-center px-10 pt-14 pb-[72px]">
      <div className="flex w-full max-w-[760px] flex-col gap-[22px]">
        <header className="flex flex-col items-center gap-3 text-center">
          <h1 className="m-0 text-[30px] font-bold text-fg" style={{ letterSpacing: "-0.02em" }}>
            이미지만 올리면 상품 등록까지
          </h1>
          <p className="m-0 text-[14px] leading-[1.7] text-muted">
            상세페이지 이미지를 올리면 AI가 상품명·카테고리·태그·KC인증을 자동으로 채웁니다.
          </p>
        </header>

        {/* 상품 정보 */}
        <section className="flex flex-col gap-6 rounded-xl border border-line bg-surface p-7">
          <span className="text-[13px] font-bold text-fg">상품 정보</span>

          <div className="flex flex-col gap-2">
            <span className="text-[13px] font-semibold text-fg">
              상세페이지 이미지 <RequiredMark />{" "}
              <em className="not-italic font-normal text-muted">({images.length}장)</em>
            </span>
            <ImageDropzone
              images={images}
              onChange={setImages}
              max={MAX_IMAGES}
              title="이미지를 드래그하거나 붙여넣기(Ctrl+V)하세요."
              hint="첫 장이 대표 이미지로 사용됩니다 · 권장 1000×1000px"
            />
          </div>

          <Field label="상품 정보" hint="(선택)">
            {(id) => (
              <TextArea
                id={id}
                value={productInfo}
                onChange={(e) => setProductInfo(e.target.value)}
                placeholder={
                  "예: 구성품 본체 1개 · 소재 캔버스 · 사이즈 43×36cm\n입력하면 AI 분석보다 우선 적용됩니다."
                }
                className="h-[108px] leading-[1.7]"
                maxLength={4000}
              />
            )}
          </Field>
        </section>

        {/* 배송 설정 */}
        <section className="flex flex-col gap-5 rounded-xl border border-line bg-surface p-7">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[13px] font-bold text-fg">배송 설정</span>
            <span className="text-[12px] text-muted">
              한 번 저장하면 다음 등록에도 그대로 쓰입니다
            </span>
          </div>

          <Field label="출고지 주소" required>
            {(id) => (
              <TextInput
                id={id}
                value={shipping.origin_address}
                onChange={(e) => set("origin_address", e.target.value)}
                placeholder="예: 서울시 은평구 은평터널로 15, 108-701"
                maxLength={300}
              />
            )}
          </Field>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[13px] font-semibold text-fg">
                반품지 주소 <RequiredMark />
              </span>
              <label className="flex cursor-pointer items-center gap-[7px] text-[12.5px] text-muted">
                <input
                  type="checkbox"
                  checked={shipping.return_same_as_origin}
                  onChange={(e) => set("return_same_as_origin", e.target.checked)}
                  className="size-[15px] accent-violet"
                />
                출고지와 동일
              </label>
            </div>
            <TextInput
              value={
                shipping.return_same_as_origin ? shipping.origin_address : shipping.return_address
              }
              onChange={(e) => set("return_address", e.target.value)}
              disabled={shipping.return_same_as_origin}
              placeholder="반품 받을 주소"
              className={shipping.return_same_as_origin ? "text-muted" : ""}
              maxLength={300}
            />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <MoneyField label="기본 배송비" value={shipping.shipping_fee} onChange={(v) => set("shipping_fee", v)} />
            <MoneyField label="반품비" value={shipping.return_fee} onChange={(v) => set("return_fee", v)} />
            <MoneyField label="교환비" value={shipping.exchange_fee} onChange={(v) => set("exchange_fee", v)} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Field label="CS 전화">
              {(id) => (
                <TextInput
                  id={id}
                  value={shipping.cs_phone}
                  onChange={(e) => set("cs_phone", e.target.value)}
                  placeholder="010-0000-0000"
                  maxLength={40}
                />
              )}
            </Field>
            <Field label="택배사">
              {(id) => (
                <Select
                  id={id}
                  value={shipping.courier}
                  onChange={(e) => set("courier", e.target.value)}
                  options={COURIERS}
                />
              )}
            </Field>
          </div>
        </section>

        {error && (
          <p
            role="alert"
            className="m-0 rounded-[10px] border border-danger/40 bg-[#2a1a1e] px-4 py-3 text-[13px] text-danger"
          >
            {error}
          </p>
        )}

        {/* 두 갈래 제출 — 자동 등록은 4c 검토를 건너뛴다 */}
        <div className="flex gap-2.5">
          <button
            type="button"
            onClick={() => submit("auto")}
            disabled={!valid || submitting !== null}
            className="grad flex flex-1 flex-col items-center justify-center gap-[3px] rounded-xl py-3.5 transition-ui hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <span className="text-[16px] font-bold text-white">
              {submitting === "auto" ? "요청 중…" : "AI가 알아서 등록하기 →"}
            </span>
            <span className="text-[11.5px] text-white/70">분석이 끝나면 바로 등록까지 완료</span>
          </button>
          <button
            type="button"
            onClick={() => submit("review")}
            disabled={!valid || submitting !== null}
            className="flex flex-none flex-col items-center justify-center gap-[3px] rounded-xl border border-line bg-surface px-[22px] py-3.5 transition-ui hover:border-line-soft hover:bg-[#1b1b21] disabled:cursor-not-allowed disabled:opacity-40"
          >
            <span className="text-[14px] font-semibold text-fg">
              {submitting === "review" ? "요청 중…" : "직접 확인하고 등록"}
            </span>
            <span className="text-[11.5px] text-muted">등록 전에 내용 수정</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function MoneyField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <Field label={label}>
      {(id) => (
        <div className="flex items-center rounded-[10px] border border-line bg-inset pr-3.5 transition-ui hover:border-line-soft">
          <input
            id={id}
            type="number"
            min={0}
            step={100}
            value={value}
            onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))}
            className="w-full bg-transparent px-3.5 py-[13px] text-[14px] text-fg outline-none"
          />
          <span className="flex-none text-[12.5px] text-muted">원</span>
        </div>
      )}
    </Field>
  );
}

export default function ProductInputPage() {
  return (
    <>
      <TopNav />
      <Suspense fallback={null}>
        <ProductInputBody />
      </Suspense>
    </>
  );
}
