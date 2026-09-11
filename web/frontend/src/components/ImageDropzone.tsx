"use client";

import { Upload, X } from "lucide-react";
import Image from "next/image";
import { useCallback, useEffect, useRef, useState } from "react";

import { fromFile, revoke, type PickedImage } from "@/lib/images";

const ACCEPT = ["image/png", "image/jpeg", "image/webp"];

/**
 * 상품 이미지 드롭존.
 * 드래그 앤 드롭 · Ctrl+V 붙여넣기 · 파일 선택 세 경로를 모두 지원한다.
 * `extraAction` 으로 AI 사진 편집 같은 버튼을 파일 선택 옆에 붙일 수 있다.
 */
export function ImageDropzone({
  images,
  onChange,
  max = 5,
  title,
  hint,
  extraAction,
}: {
  images: PickedImage[];
  onChange: (next: PickedImage[]) => void;
  max?: number;
  title?: string;
  hint?: string;
  extraAction?: React.ReactNode;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const add = useCallback(
    (files: FileList | File[] | null) => {
      if (!files) return;
      const incoming = Array.from(files);
      const accepted = incoming.filter((f) => ACCEPT.includes(f.type));

      if (accepted.length < incoming.length) setError("PNG, JPG, WEBP 파일만 올릴 수 있습니다.");
      else if (images.length + accepted.length > max)
        setError(`이미지는 최대 ${max}장까지 올릴 수 있습니다.`);
      else setError(null);

      const next = accepted.slice(0, max - images.length).map(fromFile);
      if (next.length) onChange([...images, ...next]);
    },
    [images, max, onChange],
  );

  // Ctrl+V 붙여넣기 — 화면 어디서든 받는다.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const files = Array.from(e.clipboardData?.files ?? []);
      if (files.length) {
        e.preventDefault();
        add(files);
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [add]);

  const remove = (idx: number) => {
    revoke(images[idx]);
    onChange(images.filter((_, i) => i !== idx));
    setError(null);
  };

  const full = images.length >= max;

  return (
    <div className="flex flex-col gap-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          add(e.dataTransfer.files);
        }}
        className={`flex flex-col items-center gap-2.5 rounded-[10px] border border-dashed px-5 py-[34px] text-center transition-ui ${
          dragging ? "border-accent-line bg-accent-bg" : "border-line-soft bg-inset"
        }`}
      >
        <div className="flex size-[38px] items-center justify-center rounded-lg bg-ph" aria-hidden>
          <Upload className="size-[18px] text-muted" />
        </div>
        <span className="text-[13.5px] text-fg">
          {title ?? `상품 이미지를 업로드하세요. (최대 ${max}장)`}
        </span>
        <span className="text-[12.5px] text-muted">
          {hint ?? "PNG, JPG, WEBP 파일을 드래그하거나 붙여넣기(Ctrl+V)하세요."}
        </span>
        <div className="mt-1 flex items-center gap-2">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={full}
            className="rounded-lg border border-line px-4 py-2 text-[12.5px] text-fg transition-ui hover:border-line-soft hover:bg-[#1b1b21] disabled:cursor-not-allowed disabled:opacity-40"
          >
            파일 선택
          </button>
          {extraAction}
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT.join(",")}
          multiple
          hidden
          onChange={(e) => {
            add(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {error && <span className="text-[12.5px] text-danger">{error}</span>}

      {images.length > 0 && (
        <ul className="flex flex-wrap gap-2.5">
          {images.map((img, i) => (
            <li
              key={img.key}
              className="group relative size-[74px] overflow-hidden rounded-lg border border-line bg-ph"
            >
              <Image
                src={img.previewUrl}
                alt={img.name}
                fill
                sizes="74px"
                className="object-cover"
                unoptimized
              />
              {img.assetId && !img.file && (
                <span className="absolute bottom-0 left-0 w-full bg-[rgba(11,11,15,.75)] py-0.5 text-center text-[9px] text-accent">
                  AI
                </span>
              )}
              <button
                type="button"
                onClick={() => remove(i)}
                aria-label={`${img.name} 삭제`}
                className="absolute top-1 right-1 hidden size-[22px] items-center justify-center rounded-md border border-line bg-[rgba(11,11,15,.75)] text-fg group-hover:flex hover:border-danger hover:text-danger"
              >
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
