"use client";

import { Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { AiPhotoEditDialog } from "@/components/AiPhotoEditDialog";
import { ImageDropzone } from "@/components/ImageDropzone";
import { TopNav } from "@/components/TopNav";
import { Button } from "@/components/ui/Button";
import { Field, RequiredMark, Select, TextArea, TextInput } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { assetUrl } from "@/lib/env";
import { fromAsset, resolveAssetIds, type PickedImage } from "@/lib/images";
import type { BlogForm } from "@/lib/types";

const STYLES = ["기본 블로그", "체험단 리뷰", "정보성 포스트", "제품 비교"] as const;

const STYLE_HINTS: Record<string, string> = {
  "기본 블로그": "기본 블로그: 사진 최대 5장으로 네이버 블로그 포스트 생성",
  "체험단 리뷰": "체험단 리뷰: 사용 경험을 1인칭으로 풀어쓰는 협찬 고지 포함 포스트",
  "정보성 포스트": "정보성 포스트: 검색 유입을 노린 설명 위주 구성",
  "제품 비교": "제품 비교: 유사 상품과 비교하는 표·목록 중심 구성",
};

const MAX_IMAGES = 8;

export default function BlogInputPage() {
  const router = useRouter();

  const [topic, setTopic] = useState("");
  const [style, setStyle] = useState<string>(STYLES[0]);
  const [extraRequest, setExtraRequest] = useState("");
  const [images, setImages] = useState<PickedImage[]>([]);
  const [editorOpen, setEditorOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const valid = useMemo(
    () => topic.trim() !== "" && style !== "" && images.length > 0,
    [topic, style, images],
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const imageIds = await resolveAssetIds(images);
      const form: BlogForm = {
        topic: topic.trim(),
        style,
        extra_request: extraRequest.trim(),
      };
      const job = await api.createBlogJob(form, imageIds);
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
          <header className="flex flex-col items-center gap-3 text-center">
            <h1
              className="m-0 text-[30px] font-bold text-fg"
              style={{ letterSpacing: "-0.02em" }}
            >
              어떤 블로그 글을 써 드릴까요?
            </h1>
            <p className="m-0 text-[14px] leading-[1.7] text-muted">
              상품 사진과 제목만 넣으면 SEO에 맞춘 블로그 글을 만들어 드립니다.
              <br />
              등록된 상품이 아니어도 됩니다.
            </p>
          </header>

          <form
            onSubmit={submit}
            className="flex flex-col gap-6 rounded-xl border border-line bg-surface p-7"
          >
            <Field label="블로그 주제 / 상품명" required>
              {(id) => (
                <TextInput
                  id={id}
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="예: 캠핑용 접이식 미니 테이블"
                  maxLength={200}
                />
              )}
            </Field>

            <div className="flex flex-col gap-2">
              <Field label="블로그 스타일" required>
                {(id) => (
                  <Select
                    id={id}
                    value={style}
                    onChange={(e) => setStyle(e.target.value)}
                    options={STYLES}
                  />
                )}
              </Field>
              <span className="text-[12.5px] text-muted">ⓘ {STYLE_HINTS[style]}</span>
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-[13px] font-semibold text-fg">
                상품 사진{" "}
                <em className="not-italic font-normal text-muted">
                  ({images.length}/{MAX_IMAGES}장)
                </em>{" "}
                <RequiredMark />
              </span>
              <ImageDropzone
                images={images}
                onChange={setImages}
                max={MAX_IMAGES}
                title="블로그에 넣을 사진을 업로드하세요."
                extraAction={
                  <button
                    type="button"
                    onClick={() => setEditorOpen(true)}
                    className="flex items-center gap-1.5 rounded-lg border border-accent-line bg-accent-bg px-4 py-2 text-[12.5px] font-semibold text-accent transition-ui hover:brightness-125"
                  >
                    <Sparkles className="size-3.5" />
                    AI 사진 편집
                  </button>
                }
              />
            </div>

            <Field label="추가 요청사항" hint="(선택)">
              {(id) => (
                <TextArea
                  id={id}
                  value={extraRequest}
                  onChange={(e) => setExtraRequest(e.target.value)}
                  placeholder="예: 3040 주부 대상, 캠핑 초보 관점으로"
                  className="h-24"
                  maxLength={2000}
                />
              )}
            </Field>

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
              {submitting ? "생성 요청 중…" : "블로그 생성하기 →"}
            </Button>
          </form>
        </div>
      </div>

      {editorOpen && (
        <AiPhotoEditDialog
          onClose={() => setEditorOpen(false)}
          onAdd={(assets) =>
            // 생성된 이미지는 원본 업로드와 동일하게 취급한다(삭제·순서 변경 가능).
            setImages((prev) =>
              [...prev, ...assets.map((a) => fromAsset(a, assetUrl(a.url)!))].slice(0, MAX_IMAGES),
            )
          }
        />
      )}
    </>
  );
}
