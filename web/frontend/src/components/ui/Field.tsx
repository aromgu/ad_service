"use client";

import { ChevronDown } from "lucide-react";
import { useId } from "react";

export function RequiredMark() {
  return (
    <em className="not-italic text-danger" aria-label="필수 항목">
      *
    </em>
  );
}

export function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: React.ReactNode;
  children: (id: string) => React.ReactNode;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-[13px] font-semibold text-fg">
        {label} {required && <RequiredMark />}{" "}
        {hint && <em className="not-italic font-normal text-muted">{hint}</em>}
      </label>
      {children(id)}
    </div>
  );
}

const CONTROL =
  "w-full rounded-[10px] border border-line bg-inset px-3.5 py-[13px] text-[14px] text-fg transition-ui hover:border-line-soft";

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${CONTROL} ${props.className ?? ""}`} />;
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`${CONTROL} resize-y leading-[1.6] ${props.className ?? ""}`}
    />
  );
}

export function Select({
  options,
  placeholder,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & {
  options: readonly string[];
  placeholder?: string;
}) {
  return (
    <div className="relative">
      <select
        {...props}
        className={`${CONTROL} cursor-pointer appearance-none pr-9 ${
          props.value ? "text-fg" : "text-dim"
        }`}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((o) => (
          <option key={o} value={o} className="bg-inset text-fg">
            {o}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden
        className="pointer-events-none absolute top-1/2 right-3.5 size-4 -translate-y-1/2 text-muted"
      />
    </div>
  );
}

/** 2버튼 토글 — 톤 & 스타일 같은 소수 선택지용. */
export function ToggleGroup<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: readonly T[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2" role="group">
      {options.map((o) => {
        const active = o === value;
        return (
          <button
            key={o}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(o)}
            className={`rounded-[10px] border py-3 text-center text-[13.5px] transition-ui ${
              active
                ? "border-accent-line bg-accent-bg font-semibold text-fg"
                : "border-line bg-inset text-muted hover:border-line-soft hover:text-fg"
            }`}
          >
            {o}
          </button>
        );
      })}
    </div>
  );
}
