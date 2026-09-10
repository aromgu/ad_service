import { ArrowRight, Sparkles } from "lucide-react";
import Image from "next/image";

import { TopNav } from "@/components/TopNav";
import { ButtonLink } from "@/components/ui/Button";
import { assetUrl } from "@/lib/env";

const STEPS = [
  {
    no: "01",
    title: "상세페이지 제작",
    body: "제품 사진과 상품명만 올리면 바로 올릴 수 있는 상세페이지가 완성됩니다.",
  },
  {
    no: "02",
    title: "상품 등록",
    body: "방금 만든 상세페이지 그대로, 카테고리와 옵션까지 채워 등록만 누르세요.",
  },
  {
    no: "03",
    title: "블로그 홍보",
    body: "같은 사진으로 네이버 블로그 홍보글까지 만들어 손님을 데려옵니다.",
  },
];

export default function LandingPage() {
  // 데모 패널의 before/after 는 web/images 의 실제 촬영본과 생성 결과물.
  const before = assetUrl("/static/images/serum_real1.jpg");
  const after = assetUrl("/static/images/serum_gen1.png");

  return (
    <>
      <TopNav />

      {/* Hero */}
      <section className="flex flex-col items-center gap-[22px] px-20 pt-24 pb-[88px] text-center">
        <span className="flex items-center gap-2 rounded-full border border-line px-4 py-[7px] text-[13px] text-muted">
          <Sparkles className="size-3.5 text-accent" />
          상세페이지 · 상품등록 · 블로그를 한 번에 &nbsp;스마트한 스미스 씨
        </span>
        <h1
          className="m-0 text-[60px] leading-[1.22] font-extrabold text-fg"
          style={{ letterSpacing: "-0.03em" }}
        >
          상세페이지에 상품등록, 블로그 홍보까지
          <br />
          <span className="text-accent">혼자 다 하려니 막막하셨죠?</span>
        </h1>
        <p className="m-0 text-[17px] leading-[1.7] text-muted">
          제품 사진 한 장만 올리면 상세페이지부터 상품등록, 블로그 홍보글까지
          <br />
          스미스 씨가 순서대로 알아서 만들어 드립니다.
        </p>
        <div className="mt-2.5">
          <ButtonLink
            href="/detail/new"
            variant="primary"
            className="rounded-xl px-[34px] py-4 text-[16px]"
          >
            상세페이지 만들기 →
          </ButtonLink>
        </div>
      </section>

      {/* Before / After 데모 패널 */}
      <section className="px-20 pb-[90px]">
        <div className="overflow-hidden rounded-xl border border-line bg-surface">
          <div className="border-b border-line bg-inset px-6 py-[18px] text-[14px] text-fg">
            제품 사진 1장만 있으면 썸네일, 상세페이지를 한 번에 제작하고 상품 등록까지!
          </div>
          <div className="grid grid-cols-[1fr_140px_1fr] items-center gap-7 px-12 py-11">
            <div className="w-full overflow-hidden rounded-xl border border-line bg-footer">
              <div className="flex gap-1.5 border-b border-line px-3 py-2.5">
                <span className="size-2 rounded-full bg-ph" />
                <span className="size-2 rounded-full bg-ph" />
                <span className="size-2 rounded-full bg-ph" />
              </div>
              <Placeholder
                src={before}
                alt="휴대폰으로 찍은 제품 사진"
                label="휴대폰으로 찍은 제품 사진"
                height={460}
              />
            </div>

            <div className="flex flex-col items-center gap-2 text-muted">
              <ArrowRight className="size-7 text-accent" />
              <span className="text-[12px]">3초 소요</span>
            </div>

            <Placeholder
              src={after}
              alt="AI가 만든 상품 연출컷"
              label="AI가 만든 상품 연출컷"
              height={500}
              rounded
            />
          </div>
        </div>
      </section>

      {/* 이렇게 사용해요 */}
      <section className="px-20 pb-24">
        <h2
          className="m-0 mb-2 text-center text-[32px] font-bold text-fg"
          style={{ letterSpacing: "-0.02em" }}
        >
          이렇게 사용해요
        </h2>
        <p className="m-0 mb-10 text-center text-[15px] text-muted">
          사진 한 장으로 판매 준비부터 홍보까지
        </p>
        <div className="grid grid-cols-3 gap-5">
          {STEPS.map((s) => (
            <div
              key={s.no}
              className="flex flex-col gap-3 rounded-xl border border-line bg-surface px-[26px] py-[30px]"
            >
              <div className="flex size-11 items-center justify-center rounded-[10px] bg-ph text-[12px] text-muted">
                {s.no}
              </div>
              <span className="text-[17px] font-bold text-fg">{s.title}</span>
              <span className="text-[14px] leading-[1.6] text-muted">{s.body}</span>
            </div>
          ))}
        </div>
      </section>

      <footer className="flex items-center justify-between border-t border-line bg-footer px-20 py-7 text-[13px] text-muted">
        <span>© 2026 스마트한 스미스 씨</span>
        <div className="flex gap-5">
          <span>이용약관</span>
          <span>개인정보처리방침</span>
          <span>고객센터</span>
        </div>
      </footer>
    </>
  );
}

/** 이미지가 있으면 이미지를, 없으면(백엔드 미기동) 회색 슬롯을 보여준다. */
function Placeholder({
  src,
  alt,
  label,
  height,
  rounded,
}: {
  src: string | null;
  alt: string;
  label: string;
  height: number;
  rounded?: boolean;
}) {
  return (
    <div
      className={`relative flex items-center justify-center overflow-hidden bg-ph text-[13px] text-dim ${
        rounded ? "rounded-xl" : ""
      }`}
      style={{ height }}
    >
      {src ? (
        <Image src={src} alt={alt} fill sizes="480px" className="object-cover" unoptimized />
      ) : (
        label
      )}
    </div>
  );
}
