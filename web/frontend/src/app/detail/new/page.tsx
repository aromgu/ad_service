"use client";

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
const LENGTHS = ["숏(10장 내외)", "미들(15장 내외)", "롱(20장 이상)"] as const;
const TONES: readonly Tone[] = ["감성적", "정보 중심"];

const MAX_IMAGES = 5;

export default function DetailPageInput() {
  const router = useRouter();

  const [productName, setProductName] = useState("");
  const [target, setTarget] = useState("");
  const [tone, setTone] = useState<Tone>("감성적");
  const [length, setLength] = useState<string>(LENGTHS[0]);
  const [features, setFeatures] = useState("");
  const [images, setImages] = useState<PickedImage[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 필수 필드가 다 차기 전까지 CTA 비활성.
  const valid = useMemo(
    () =>
      productName.trim() !== "" &&
      target !== "" &&
      length !== "" &&
      features.trim() !== "" &&
      images.length > 0,
    [productName, target, length, features, images],
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
        // 언어 선택은 화면에서 제거했다. 백엔드는 계속 받으므로 기본값을 보낸다.
        language: "자동",
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
                title="스마트스토어에 바로 올릴 수 있는 형식으로 만들어 드립니다."
                className="inline-flex size-[18px] cursor-help items-center justify-center rounded-full border border-line text-[11px] text-muted"
              >
                i
              </span>
            </h1>
            <span className="text-[13px] text-muted">
              스마트스토어 연동 쇼핑몰 상세페이지
            </span>
          </header>

          <form
            onSubmit={submit}
            className="flex flex-col gap-6 rounded-xl border border-line bg-surface p-7"
          >
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

        </div>
      </div>
    </>
  );
}
