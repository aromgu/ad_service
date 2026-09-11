"use client";

import { Check, Plus, Sparkles, X } from "lucide-react";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { assetUrl } from "@/lib/env";
import type { Asset } from "@/lib/types";

const COUNTS = [1, 2, 3, 4] as const;

/**
 * AI 사진 편집 팝업 (프레임 3a-2).
 * 올린 사진에 원하는 연출을 적으면 블로그용 이미지로 다시 만들어,
 * 고른 것만 상품 사진 목록에 추가한다.
 */
/** 부모가 조건부로 렌더한다 — 닫히면 언마운트되므로 상태가 자연히 초기화된다. */
export function AiPhotoEditDialog({
  onClose,
  onAdd,
}: {
  onClose: () => void;
  onAdd: (assets: Asset[]) => void;
}) {
  const [sources, setSources] = useState<Asset[]>([]);
  const [prompt, setPrompt] = useState("");
  const [count, setCount] = useState<number>(4);
  const [results, setResults] = useState<Asset[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // ESC 로 닫기
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const addSources = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    setError(null);
    try {
      // 업로드는 한 번에 5장까지라 나눠 보낸다 (팝업은 장수 제한이 없다).
      const all = Array.from(files);
      const uploaded: Asset[] = [];
      for (let i = 0; i < all.length; i += 5) {
        uploaded.push(...(await api.uploadImages(all.slice(i, i + 5))));
      }
      setSources((prev) => [...prev, ...uploaded]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "사진을 올리지 못했습니다.");
    } finally {
      setUploading(false);
    }
  };

  const generate = async () => {
    if (!prompt.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResults([]);
    setSelected(new Set());
    try {
      const out = await api.aiEditImages(
        prompt.trim(),
        count,
        sources.map((s) => s.id),
      );
      setResults(out);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "이미지를 만들지 못했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const confirm = () => {
    onAdd(results.filter((r) => selected.has(r.id)));
    onClose();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="AI 사진 편집"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(11,11,15,.72)] p-10"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-[920px] max-w-full overflow-hidden rounded-xl border border-line bg-surface"
      >
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
          <div className="flex flex-col gap-1.5">
            <span className="flex items-center gap-1.5 text-[17px] font-bold text-fg">
              <Sparkles className="size-4 text-accent" />
              AI 사진 편집
            </span>
            <span className="text-[12.5px] text-muted">
              올린 사진에 원하는 연출을 적으면 블로그용 이미지로 다시 만들어 드려요.
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="flex size-7 flex-none items-center justify-center rounded-lg border border-line text-muted transition-ui hover:border-line-soft hover:text-fg"
          >
            <X className="size-3.5" />
          </button>
        </header>

        <div className="grid grid-cols-2 gap-6 p-6">
          {/* 좌: 입력 */}
          <div className="flex flex-col gap-[18px]">
            <div className="flex flex-col gap-2">
              <span className="text-[12.5px] font-semibold text-fg">
                사진 업로드{" "}
                <em className="not-italic font-normal text-muted">(장수 제한 없음)</em>
              </span>
              <div className="flex gap-2 overflow-x-auto pb-1">
                <button
                  type="button"
                  onClick={() => inputRef.current?.click()}
                  disabled={uploading}
                  className="flex size-[74px] flex-none flex-col items-center justify-center gap-0.5 rounded-lg border border-dashed border-line-soft text-dim transition-ui hover:border-accent-line hover:text-accent disabled:opacity-40"
                >
                  <Plus className="size-4" />
                  <span className="text-[10px]">추가</span>
                </button>
                {sources.map((s) => (
                  <div
                    key={s.id}
                    className="relative size-[74px] flex-none overflow-hidden rounded-lg border border-line bg-ph"
                  >
                    <Image
                      src={assetUrl(s.url)!}
                      alt={s.filename}
                      fill
                      sizes="74px"
                      className="object-cover"
                      unoptimized
                    />
                  </div>
                ))}
              </div>
              <span className="text-[11.5px] leading-[1.6] text-dim">
                {uploading ? "올리는 중…" : "원하는 만큼 올릴 수 있어요."}
              </span>
              <input
                ref={inputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                multiple
                hidden
                onChange={(e) => {
                  addSources(e.target.files);
                  e.target.value = "";
                }}
              />
            </div>

            <div className="flex flex-col gap-2">
              <label htmlFor="ai-edit-prompt" className="text-[12.5px] font-semibold text-fg">
                어떻게 바꿀까요? <em className="not-italic text-danger">*</em>
              </label>
              <textarea
                id="ai-edit-prompt"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="예: 배경을 밝은 우드 테이블로 바꾸고, 오른쪽에 글자 넣을 여백을 만들어 주세요"
                className="h-[88px] resize-none rounded-[10px] border border-line bg-inset px-3.5 py-3 text-[13.5px] leading-[1.6] text-fg transition-ui hover:border-line-soft"
              />
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-[12.5px] font-semibold text-fg">만들 이미지 수</span>
              <div className="flex gap-1.5">
                {COUNTS.map((n) => (
                  <button
                    key={n}
                    type="button"
                    aria-pressed={count === n}
                    onClick={() => setCount(n)}
                    className={`rounded-full border px-4 py-[7px] text-[12px] transition-ui ${
                      count === n
                        ? "border-accent-line bg-accent-bg font-semibold text-fg"
                        : "border-line text-muted hover:border-line-soft hover:text-fg"
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={generate}
              disabled={!prompt.trim() || loading}
              className="grad rounded-[10px] py-[13px] text-[14px] font-bold text-white transition-ui hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading ? "만드는 중…" : "이미지 만들기"}
            </button>

            {error && (
              <p role="alert" className="m-0 text-[12px] text-danger">
                {error}
              </p>
            )}
          </div>

          {/* 우: 결과 */}
          <div className="flex flex-col gap-2.5 rounded-[10px] border border-line bg-inset p-[18px]">
            <div className="flex items-baseline justify-between gap-2.5">
              <span className="text-[12.5px] font-semibold text-fg">
                결과 <em className="not-italic font-normal text-muted">(원하는 만큼 선택)</em>
              </span>
              <span className="text-[11.5px] text-accent">{selected.size}장 선택됨</span>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              {loading &&
                Array.from({ length: count }).map((_, i) => (
                  <div
                    key={i}
                    className="flex h-[134px] items-center justify-center rounded-lg border border-line bg-ph"
                  >
                    <span className="spin-1s block size-6 rounded-full border-2 border-violet border-t-transparent" />
                  </div>
                ))}

              {!loading &&
                results.map((r, i) => {
                  const on = selected.has(r.id);
                  return (
                    <button
                      key={r.id}
                      type="button"
                      aria-pressed={on}
                      onClick={() => toggle(r.id)}
                      className={`relative h-[134px] overflow-hidden rounded-lg bg-ph transition-ui ${
                        on ? "border-2 border-violet" : "border border-line hover:border-line-soft"
                      }`}
                    >
                      <Image
                        src={assetUrl(r.url)!}
                        alt={`결과 ${String.fromCharCode(65 + i)}`}
                        fill
                        sizes="220px"
                        className="object-cover"
                        unoptimized
                      />
                      <span
                        className={`absolute top-[7px] right-[7px] flex size-[18px] items-center justify-center rounded-[5px] ${
                          on ? "bg-violet text-white" : "border border-line-soft bg-[rgba(11,11,15,.6)]"
                        }`}
                      >
                        {on && <Check className="size-3" strokeWidth={3} />}
                      </span>
                    </button>
                  );
                })}

              {!loading && results.length === 0 && (
                <p className="col-span-2 m-0 py-10 text-center text-[12px] text-dim">
                  요청을 적고 &lsquo;이미지 만들기&rsquo;를 눌러 주세요.
                </p>
              )}
            </div>

            <span className="text-[11.5px] leading-[1.6] text-dim">
              마음에 들지 않으면 요청을 고쳐서 다시 만들 수 있어요.
            </span>

            <div className="mt-auto flex gap-2">
              <button
                type="button"
                onClick={generate}
                disabled={!prompt.trim() || loading}
                className="flex-none rounded-lg border border-line px-3.5 py-2.5 text-[12.5px] text-fg transition-ui hover:border-line-soft hover:bg-[#1b1b21] disabled:opacity-40"
              >
                다시 만들기
              </button>
              <button
                type="button"
                onClick={confirm}
                disabled={selected.size === 0}
                className="grad flex-1 rounded-lg px-3.5 py-2.5 text-[12.5px] font-bold text-white transition-ui hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
              >
                선택한 {selected.size}장 추가
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
