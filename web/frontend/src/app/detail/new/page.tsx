"use client";

import { ChevronDown, ChevronUp, Zap } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { ImageDropzone } from "@/components/ImageDropzone";
import { TopNav } from "@/components/TopNav";
import { Button } from "@/components/ui/Button";
import { Field, RequiredMark, Select, TextArea, TextInput, ToggleGroup } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { resolveAssetIds, type PickedImage } from "@/lib/images";
import type { DetailPageForm, Tone } from "@/lib/types";

const TARGETS = [
  "20-30대 여성",
  "20-30대 남성",
  "30-40대 여성",
  "30-40대 남성",
  "10대",
  "50대 이상",
  "전 연령",
] as const;
const LANGUAGES = ["자동", "한국어", "English", "日本語", "中文"] as const;
const LENGTHS = ["숏(10장 내외)", "미들(15장 내외)", "롱(20장 이상)"] as const;
const TONES: readonly Tone[] = ["감성적", "정보 중심"];

const MAX_IMAGES = 5;

export default function DetailPageInput() {
  const router = useRouter();

  const [productName, setProductName] = useState("");
  const [target, setTarget] = useState("");
  const [language, setLanguage] = useState<string>("자동");
  const [tone, setTone] = useState<Tone>("감성적");
  const [length, setLength] = useState<string>(LENGTHS[0]);
  const [features, setFeatures] = useState("");
  const [images, setImages] = useState<PickedImage[]>([]);

  const [autoFillOpen, setAutoFillOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 필수 필드가 다 차기 전까지 CTA 비활성.
  const valid = useMemo(
    () =>
      productName.trim() !== "" &&
      target !== "" &&
      language !== "" &&
      length !== "" &&
      features.trim() !== "" &&
      images.length > 0,
    [productName, target, language, length, features, images],
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const imageIds = await resolveAssetIds(images);
      const form: DetailPageForm = {
        product_name: productName.trim(),
        target,
        language,
        tone,
        length,
        features: features.trim(),
      };
      const job = await api.createDetailPageJob(form, imageIds);
      router.push(`/jobs/${job.id}?type=${job.type}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "생성 요청에 실패했습니다.");
      setSubmitting(false);
    }
  }

  return (
    <>
      <TopNav />
      <div className="flex justify-center px-10 pt-14 pb-[72px]">
        <div className="flex w-full max-w-[760px] flex-col gap-[22px]">
          <header className="flex flex-col items-center gap-3.5 text-center">
            <h1
              className="m-0 flex items-center gap-2 text-[30px] font-bold text-fg"
              style={{ letterSpacing: "-0.02em" }}
            >
              어떤 상세페이지를 만들까요?
              <span
                title="스마트스토어·쿠팡 등 범용 쇼핑몰에 바로 올릴 수 있는 형식으로 만들어 드립니다."
                className="inline-flex size-[18px] cursor-help items-center justify-center rounded-full border border-line text-[11px] text-muted"
              >
                i
              </span>
            </h1>
            <span className="text-[13px] text-muted">
              스마트스토어·쿠팡 등 범용 쇼핑몰 상세페이지
            </span>
          </header>

          <form
            onSubmit={submit}
            className="flex flex-col gap-6 rounded-xl border border-line bg-surface p-7"
          >
            {/* AI 자동 완성 (선택) */}
            <div className="flex flex-col gap-3 rounded-[10px] border border-line bg-inset px-5 py-[18px]">
              <div className="flex items-start justify-between gap-5">
                <div className="flex flex-col gap-1.5">
                  <span className="flex items-center gap-1.5 text-[14px] font-semibold text-fg">
                    <Zap className="size-4 text-accent" />
                    AI 자동 완성 사용하기
                  </span>
                  <span className="text-[12.5px] leading-[1.6] text-muted">
                    기존 상세페이지 이미지를 업로드하면 AI가 상품명, 타겟, 특징을 자동으로
                    채웁니다. (선택사항)
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setAutoFillOpen((v) => !v)}
                  aria-expanded={autoFillOpen}
                  className="flex flex-none items-center gap-1 rounded-lg border border-line px-3.5 py-2 text-[12.5px] text-muted transition-ui hover:border-line-soft hover:text-fg"
                >
                  이미지 업로드
                  {autoFillOpen ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
                </button>
              </div>
              {autoFillOpen && (
                <p className="m-0 rounded-lg border border-line border-dashed px-4 py-3 text-[12.5px] leading-[1.6] text-dim">
                  자동 완성은 기존 상세페이지를 읽는 VLM 이 연결되면 열립니다. 지금은 아래 항목을
                  직접 채워 주세요.
                </p>
              )}
            </div>

            <Field label="상품명" required>
              {(id) => (
                <TextInput
                  id={id}
                  value={productName}
                  onChange={(e) => setProductName(e.target.value)}
                  placeholder="예: 글로우 비타민C 세럼"
                  maxLength={120}
                />
              )}
            </Field>

            <div className="grid grid-cols-2 gap-4">
              <Field label="주요 타겟" required>
                {(id) => (
                  <Select
                    id={id}
                    value={target}
                    onChange={(e) => setTarget(e.target.value)}
                    options={TARGETS}
                    placeholder="타겟 선택"
                  />
                )}
              </Field>
              <Field label="상세페이지 언어" required>
                {(id) => (
                  <Select
                    id={id}
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    options={LANGUAGES}
                  />
                )}
              </Field>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <span className="text-[13px] font-semibold text-fg">
                  톤 &amp; 스타일 <RequiredMark />
                </span>
                <ToggleGroup value={tone} options={TONES} onChange={setTone} />
              </div>
              <Field label="페이지 길이" required>
                {(id) => (
                  <Select
                    id={id}
                    value={length}
                    onChange={(e) => setLength(e.target.value)}
                    options={LENGTHS}
                  />
                )}
              </Field>
            </div>

            <Field label="특징" required>
              {(id) => (
                <TextArea
                  id={id}
                  value={features}
                  onChange={(e) => setFeatures(e.target.value)}
                  placeholder="예: 피부 톤 개선, 보습 효과, 저자극 성분"
                  className="h-24"
                  maxLength={2000}
                />
              )}
            </Field>

            <div className="flex flex-col gap-2">
              <span className="text-[13px] font-semibold text-fg">
                상품 이미지 <RequiredMark />{" "}
                <em className="not-italic font-normal text-muted">
                  ({images.length}/{MAX_IMAGES})
                </em>
              </span>
              <ImageDropzone images={images} onChange={setImages} max={MAX_IMAGES} />
            </div>

            <div className="flex flex-col items-center gap-3 pt-0.5">
              <button
                type="button"
                onClick={() => setAdvancedOpen((v) => !v)}
                aria-expanded={advancedOpen}
                className="flex items-center gap-1 text-[13px] text-muted transition-ui hover:text-fg"
              >
                상세 설정
                {advancedOpen ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
              </button>
              {advancedOpen && (
                <p className="m-0 w-full rounded-[10px] border border-line bg-inset px-4 py-3 text-center text-[12.5px] text-dim">
                  브랜드 톤, 금칙어, 레퍼런스 링크 같은 세부 옵션이 들어갈 자리입니다.
                </p>
              )}
            </div>

            {error && (
              <p
                role="alert"
                className="m-0 rounded-[10px] border border-danger/40 bg-[#2a1a1e] px-4 py-3 text-[13px] text-danger"
              >
                {error}
              </p>
            )}

            <Button
              type="submit"
              variant="primary"
              disabled={!valid || submitting}
              className="w-full rounded-xl py-4 text-[16px]"
            >
              {submitting ? "생성 요청 중…" : "상세페이지 생성하기 →"}
            </Button>
          </form>

          <aside className="flex items-center justify-between gap-5 rounded-xl border border-line bg-surface px-6 py-5">
            <div className="flex flex-col gap-1.5">
              <span className="text-[14px] font-bold text-fg">처음이신가요?</span>
              <span className="text-[12.5px] text-muted">
                사진 한 장으로 만드는 예시 결과물을 먼저 살펴보세요.
              </span>
            </div>
            <Button
              type="button"
              onClick={() => router.push("/")}
              className="flex-none px-4 py-[9px] text-[12.5px]"
            >
              자세히 보기
            </Button>
          </aside>
        </div>
      </div>
    </>
  );
}
