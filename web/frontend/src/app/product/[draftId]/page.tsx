"use client";

import { Check, Plus, Search, Trash2, X } from "lucide-react";
import Image from "next/image";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { TopNav } from "@/components/TopNav";
import { Field, RequiredMark, Select, TextArea, TextInput } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { assetUrl } from "@/lib/env";
import type {
  CategoryCandidate,
  ProductDraft,
  ProductDraftPatch,
  ProductOption,
} from "@/lib/types";

const SAVE_DEBOUNCE_MS = 700;

const ATTRIBUTE_OPTIONS: Record<string, readonly string[]> = {
  사용대상: ["여성", "남성", "공용", "아동"],
  패턴: ["프린트", "무지", "스트라이프", "체크"],
  주요소재: ["캔버스", "가죽", "나일론", "면", "폴리에스터"],
};

/** 프레임 4c — 검토 및 등록. 등록 완료 후에도 같은 화면에서 수정할 수 있다. */
export default function ProductDraftPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const router = useRouter();

  const [draft, setDraft] = useState<ProductDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [registering, setRegistering] = useState(false);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  // 등록 완료 화면에서 "등록 내용 수정"을 누르면 폼이 다시 열린다.
  const [forceEdit, setForceEdit] = useState(false);

  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 디바운스 창 안에서 들어온 변경을 모아 둔다.
  // 마지막 호출분만 보내면 그 사이 고친 값이 서버에 안 가고, 응답으로 되돌아온
  // 문서가 로컬 상태를 덮어써서 조용히 날아간다.
  const pending = useRef<ProductDraftPatch>({});

  useEffect(() => {
    if (!draftId) return;
    let alive = true;
    api
      .getProductDraft(draftId)
      .then((d) => alive && setDraft(d))
      .catch(
        (err) =>
          alive &&
          setError(err instanceof ApiError ? err.message : "등록 정보를 불러올 수 없습니다."),
      );
    return () => {
      alive = false;
    };
  }, [draftId]);

  /** 모아 둔 변경을 실제로 저장한다. */
  const flush = useCallback(async () => {
    const changes = pending.current;
    if (Object.keys(changes).length === 0) return;
    pending.current = {};
    setSaveState("saving");
    try {
      const saved = await api.patchProductDraft(draftId, changes);
      // 저장하는 사이에 또 고친 값이 있으면 서버 응답 위에 다시 얹는다.
      setDraft((prev) => (prev ? { ...saved, ...pending.current } : saved));
      setSaveState("saved");
    } catch {
      // 실패한 변경은 다시 대기열에 넣어 다음 저장 때 재시도한다.
      pending.current = { ...changes, ...pending.current };
      setSaveState("error");
    }
  }, [draftId]);

  /** 낙관적 반영 후 디바운스 저장. */
  const patch = useCallback(
    (changes: ProductDraftPatch) => {
      setDraft((prev) => (prev ? { ...prev, ...changes } : prev));
      pending.current = { ...pending.current, ...changes };
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(flush, SAVE_DEBOUNCE_MS);
    },
    [flush],
  );

  async function register() {
    if (!draft || registering) return;
    setRegistering(true);
    setError(null);
    try {
      // 아직 저장 안 된 수정이 있으면 먼저 반영한 뒤 등록한다.
      if (saveTimer.current) clearTimeout(saveTimer.current);
      await flush();
      await api.registerProduct(draftId);
      // 결과는 완료 화면에서 보여 준다 — 이 화면 맨 위 배너는 스크롤에 가려 안 보인다.
      // 이동하는 동안 버튼을 다시 누르면 같은 상품이 또 등록되므로 잠근 채로 둔다.
      router.push(`/product/${draftId}/done`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "상품 등록에 실패했습니다.");
      setRegistering(false);
    }
  }

  if (error && !draft) {
    return (
      <>
        <TopNav />
        <div className="flex flex-col items-center gap-4 px-6 pt-32 text-center">
          <p className="m-0 text-[15px] text-danger">{error}</p>
          <button
            onClick={() => router.push("/product")}
            className="rounded-[10px] border border-line px-4 py-2.5 text-[13px] text-fg transition-ui hover:border-line-soft"
          >
            상품등록 처음으로
          </button>
        </div>
      </>
    );
  }

  if (!draft) {
    return (
      <>
        <TopNav />
        <div className="flex justify-center px-10 pt-10">
          <div className="h-[600px] w-full max-w-[940px] rounded-xl border border-line bg-inset" />
        </div>
      </>
    );
  }

  const registered = draft.status === "registered" && !forceEdit;

  return (
    <>
      <TopNav />
      <div className="flex justify-center px-10 pt-10 pb-16">
        <div className="flex w-full max-w-[940px] flex-col gap-[18px]">
          {registered ? (
            <RegisteredBanner draft={draft} onEdit={() => setForceEdit(true)} />
          ) : (
            <>
              {typeof draft.analysis.register_error === "string" && (
                <RegisterErrorBanner reason={draft.analysis.register_error} />
              )}
              <AnalysisBanner draft={draft} saveState={saveState} />
            </>
          )}

          {/* 상세페이지 미리보기 */}
          <Card>
            <div className="flex items-baseline gap-2">
              <span className="text-[13px] font-bold text-fg">상세페이지 미리보기</span>
              <span className="text-[12px] text-muted">{draft.image_urls.length}장</span>
            </div>
            <div className="flex flex-col gap-[7px]">
              <span className="text-[12.5px] text-muted">상품 설명 (상단에 표시)</span>
              <TextArea
                value={draft.description}
                onChange={(e) => patch({ description: e.target.value })}
                disabled={registered}
                className="h-[92px] text-[13.5px] leading-[1.7]"
                maxLength={4000}
              />
            </div>
            <div className="flex gap-2.5 overflow-x-auto rounded-[10px] bg-ph p-2.5">
              {draft.image_urls.length === 0 && (
                <div className="flex h-[300px] w-full items-center justify-center text-[13px] text-dim">
                  상세페이지 이미지 미리보기
                </div>
              )}
              {draft.image_urls.map((u) => (
                <div
                  key={u}
                  className="relative h-[300px] w-[220px] flex-none overflow-hidden rounded-lg bg-ph-2"
                >
                  <Image
                    src={assetUrl(u)!}
                    alt="상세페이지 이미지"
                    fill
                    sizes="220px"
                    className="object-cover"
                    unoptimized
                  />
                </div>
              ))}
            </div>
          </Card>

          {/* 대표 이미지 + 상품명 */}
          <div className="grid grid-cols-[220px_1fr] gap-[18px]">
            <Card className="gap-2.5 p-[18px]">
              <span className="text-[12.5px] font-semibold text-fg">대표 이미지</span>
              <div className="relative h-[196px] overflow-hidden rounded-[10px] bg-ph">
                {draft.representative_image_url ? (
                  <Image
                    src={assetUrl(draft.representative_image_url)!}
                    alt="대표 이미지"
                    fill
                    sizes="220px"
                    className="object-cover"
                    unoptimized
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-[12px] text-dim">
                    1000×1000
                  </div>
                )}
              </div>
              {!registered && draft.image_urls.length > 1 && (
                <button
                  type="button"
                  onClick={() => {
                    const i = draft.image_urls.indexOf(draft.representative_image_url ?? "");
                    patch({
                      representative_image_url:
                        draft.image_urls[(i + 1) % draft.image_urls.length],
                    });
                  }}
                  className="self-center text-[12px] text-accent hover:underline"
                >
                  변경
                </button>
              )}
            </Card>

            <Card className="gap-4">
              <div className="flex items-center justify-between">
                <span className="text-[13px] font-bold text-fg">
                  상품명 <AiBadge />
                </span>
                <label className="flex cursor-pointer items-center gap-[7px] text-[12px] text-muted">
                  <input
                    type="checkbox"
                    checked={draft.exclude_brand_from_name}
                    disabled={registered}
                    onChange={(e) => patch({ exclude_brand_from_name: e.target.checked })}
                    className="size-[14px] accent-violet"
                  />
                  상품명에서 브랜드명 빼기
                </label>
              </div>
              <TextInput
                value={
                  draft.exclude_brand_from_name
                    ? draft.product_name.replace(draft.brand, "").trimStart()
                    : draft.product_name
                }
                onChange={(e) => patch({ product_name: e.target.value })}
                disabled={registered}
                maxLength={200}
              />
              <span className="text-[12px] leading-[1.6] text-muted">
                브랜드명과 핵심 키워드, 상품 특징을 포함해 40~50자 내로 작성하세요.
              </span>
              <div className="grid grid-cols-3 gap-3">
                <SmallField label="브랜드" value={draft.brand} disabled={registered} onChange={(v) => patch({ brand: v })} />
                <SmallField label="제조사" value={draft.manufacturer} disabled={registered} onChange={(v) => patch({ manufacturer: v })} />
                <SmallField label="판매자상품코드" value={draft.seller_code} disabled={registered} onChange={(v) => patch({ seller_code: v })} />
              </div>
            </Card>
          </div>

          <CategoryCard
            draft={draft}
            disabled={registered}
            // 경로만 저장하면 등록할 수 없다 — 네이버 카테고리 ID 를 함께 저장한다.
            onSelect={(c) => patch({ selected_category: c.path, selected_category_id: c.id })}
          />

          {/* 가격 · 배송 */}
          <Card className="gap-4">
            <span className="text-[13px] font-bold text-fg">
              가격 · 배송 <em className="not-italic text-[12px] font-normal text-danger">필수</em>
            </span>
            <div className="grid grid-cols-4 gap-3">
              <NumberField
                label="판매가"
                required
                unit="원"
                value={draft.price}
                placeholder="가격 입력"
                disabled={registered}
                onChange={(v) => patch({ price: v })}
              />
              <NumberField label="할인율" unit="%" value={draft.discount_rate} disabled={registered} onChange={(v) => patch({ discount_rate: v ?? 0 })} />
              <NumberField label="배송비" unit="원" value={draft.shipping_fee} disabled={registered} onChange={(v) => patch({ shipping_fee: v ?? 0 })} />
              <NumberField label="재고수량" value={draft.stock} disabled={registered} onChange={(v) => patch({ stock: v ?? 0 })} />
            </div>
            <span className="text-[12px] text-muted">
              배송비는 배송 설정값({(draft.shipping.shipping_fee ?? 3000).toLocaleString("ko-KR")}원)이
              기본으로 들어옵니다. 이 상품만 다르면 여기서 바꾸세요.
            </span>
          </Card>

          <OptionsCard
            options={draft.options}
            disabled={registered}
            onChange={(options) => patch({ options })}
          />

          <div className="grid grid-cols-2 gap-[18px]">
            <KcCard kc={draft.kc} disabled={registered} onChange={(kc) => patch({ kc })} />
            <TagsCard tags={draft.tags} disabled={registered} onChange={(tags) => patch({ tags })} />
          </div>

          <AttributesCard
            attributes={draft.attributes}
            disabled={registered}
            onChange={(attributes) => patch({ attributes })}
          />

          {error && (
            <p
              role="alert"
              className="m-0 rounded-[10px] border border-danger/40 bg-[#2a1a1e] px-4 py-3 text-[13px] text-danger"
            >
              {error}
            </p>
          )}

          {!registered && (
            <div className="grid grid-cols-[1fr_200px] gap-3">
              <button
                type="button"
                onClick={register}
                disabled={registering}
                className="grad rounded-xl py-4 text-[16px] font-bold text-white transition-ui hover:brightness-110 disabled:opacity-40"
              >
                {registering ? "등록 중…" : "네이버에 상품 등록 →"}
              </button>
              <button
                type="button"
                onClick={() => router.push("/product")}
                className="rounded-xl border border-line py-4 text-[14px] text-fg transition-ui hover:border-line-soft hover:bg-[#1b1b21]"
              >
                다시 시작
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

/* ---------------- 상단 배너 ---------------- */

function AnalysisBanner({
  draft,
  saveState,
}: {
  draft: ProductDraft;
  saveState: "idle" | "saving" | "saved" | "error";
}) {
  return (
    <div className="flex items-center justify-between gap-5 rounded-xl border border-accent-line bg-accent-bg px-[22px] py-[18px]">
      <div className="flex items-center gap-3">
        <span className="flex size-[26px] items-center justify-center rounded-full bg-success text-white">
          <Check className="size-3.5" strokeWidth={3} />
        </span>
        <div className="flex flex-col gap-[3px]">
          <span className="text-[15px] font-bold text-fg">AI 분석 완료</span>
          <span className="text-[12.5px] text-muted">
            아래 정보를 확인하고 수정한 후 상품을 등록하세요
            {saveState === "saving" && " · 저장 중…"}
            {saveState === "saved" && " · 저장됨"}
            {saveState === "error" && " · 저장 실패"}
          </span>
        </div>
      </div>
      <div className="flex flex-col items-end gap-[3px] text-[12px] text-muted">
        <span>이미지 분석: 상세 {draft.analysis.image_count ?? draft.image_urls.length}장</span>
        <span>OCR 텍스트: {draft.analysis.ocr_chars ?? 0}자</span>
      </div>
    </div>
  );
}

/** 자동 등록이 실패했을 때 이유를 알려 준다 — 여기서 고쳐 다시 등록할 수 있다. */
function RegisterErrorBanner({ reason }: { reason: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-xl border border-danger/50 bg-[#2a1a1e] px-[22px] py-[18px]"
    >
      <span className="mt-0.5 flex size-[26px] flex-none items-center justify-center rounded-full border border-[#5A3038] bg-[#2A1A1E] text-danger">
        !
      </span>
      <div className="flex flex-col gap-[3px]">
        <span className="text-[15px] font-bold text-fg">자동 등록에 실패했어요</span>
        <span className="text-[12.5px] leading-[1.6] text-muted">
          {reason} — 아래에서 고친 뒤 다시 등록해 주세요.
        </span>
      </div>
    </div>
  );
}

function RegisteredBanner({ draft, onEdit }: { draft: ProductDraft; onEdit: () => void }) {
  const when = draft.registered_at
    ? new Date(draft.registered_at).toLocaleString("ko-KR")
    : "방금";
  return (
    <div className="flex items-center justify-between gap-5 rounded-xl border border-[#2E7D5B] bg-[#132a20] px-[22px] py-[18px]">
      <div className="flex items-center gap-3">
        <span className="flex size-[26px] items-center justify-center rounded-full bg-success text-white">
          <Check className="size-3.5" strokeWidth={3} />
        </span>
        <div className="flex flex-col gap-[3px]">
          <span className="text-[15px] font-bold text-fg">네이버 스마트스토어에 등록되었습니다</span>
          <span className="text-[12.5px] text-muted">
            {when}
            {draft.naver_origin_product_no && ` · 상품번호 ${draft.naver_origin_product_no}`}
          </span>
        </div>
      </div>
      <button
        type="button"
        onClick={onEdit}
        className="rounded-lg border border-line bg-surface px-4 py-2.5 text-[12.5px] text-fg transition-ui hover:border-line-soft hover:bg-[#1b1b21]"
      >
        등록 내용 수정
      </button>
    </div>
  );
}

/* ---------------- 카드들 ---------------- */

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <section
      className={`flex flex-col gap-3.5 rounded-xl border border-line bg-surface p-[22px] ${className}`}
    >
      {children}
    </section>
  );
}

function AiBadge({ label = "AI 추천" }: { label?: string }) {
  return <em className="not-italic text-[12px] font-normal text-accent">{label}</em>;
}

function SmallField({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  disabled?: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <Field label={label}>
      {(id) => (
        <input
          id={id}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-[10px] border border-line bg-inset px-[13px] py-[11px] text-[13.5px] text-fg transition-ui hover:border-line-soft disabled:opacity-60"
        />
      )}
    </Field>
  );
}

function NumberField({
  label,
  value,
  unit,
  required,
  placeholder,
  disabled,
  onChange,
}: {
  label: string;
  value: number | null;
  unit?: string;
  required?: boolean;
  placeholder?: string;
  disabled?: boolean;
  onChange: (v: number | null) => void;
}) {
  return (
    <div className="flex flex-col gap-[7px]">
      <span className="text-[12.5px] font-semibold text-fg">
        {label} {required && <RequiredMark />}
      </span>
      <div className="flex items-center rounded-[10px] border border-line bg-inset pr-[13px] transition-ui hover:border-line-soft">
        <input
          type="number"
          min={0}
          value={value ?? ""}
          placeholder={placeholder}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value === "" ? null : Math.max(0, Number(e.target.value)))}
          className="w-full bg-transparent px-[13px] py-3 text-[13.5px] text-fg outline-none disabled:opacity-60"
        />
        {unit && <span className="flex-none text-[12px] text-muted">{unit}</span>}
      </div>
    </div>
  );
}

function CategoryCard({
  draft,
  disabled,
  onSelect,
}: {
  draft: ProductDraft;
  disabled: boolean;
  onSelect: (c: CategoryCandidate) => void;
}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<CategoryCandidate[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async () => {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const found = await api.searchCategories(query.trim());
      setHits(found);
      if (found.length === 0) setError("검색 결과가 없습니다. 다른 말로 찾아보세요.");
    } catch (err) {
      setHits([]);
      setError(err instanceof ApiError ? err.message : "카테고리를 불러오지 못했습니다.");
    } finally {
      setSearching(false);
    }
  };

  const rows: CategoryCandidate[] = [
    ...draft.category_candidates,
    ...hits.filter((h) => !draft.category_candidates.some((c) => c.id === h.id)),
  ];

  return (
    <Card className="gap-3">
      <span className="text-[13px] font-bold text-fg">
        카테고리 <AiBadge />
      </span>
      {rows.length === 0 && (
        <p className="m-0 rounded-[10px] border border-line border-dashed px-4 py-3.5 text-[12.5px] text-dim">
          아래에서 카테고리를 검색해 골라 주세요. 네이버 등록에 반드시 필요합니다.
        </p>
      )}
      {rows.map((c) => {
        const on = c.id ? c.id === draft.selected_category_id : c.path === draft.selected_category;
        return (
          <button
            key={c.id || c.path}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(c)}
            className={`flex items-center gap-3 rounded-[10px] border px-4 py-3.5 text-left transition-ui disabled:cursor-not-allowed ${
              on ? "border-accent-line bg-accent-bg" : "border-line bg-inset hover:border-line-soft"
            }`}
          >
            <span
              className={`flex size-4 flex-none items-center justify-center rounded-full ${
                on ? "border-2 border-violet" : "border border-line-soft"
              }`}
            >
              {on && <em className="block size-[7px] rounded-full bg-violet" />}
            </span>
            <span className={`flex-1 text-[13.5px] text-fg ${on ? "font-semibold" : ""}`}>
              {c.path}
            </span>
            {c.confidence > 0 && (
              <span
                className={`rounded-md px-[9px] py-[3px] text-[11px] ${
                  on ? "bg-ph text-fg" : "border border-line text-muted"
                }`}
              >
                AI {c.confidence}%
              </span>
            )}
          </button>
        );
      })}
      {!disabled && (
        <div className="mt-0.5 flex items-center gap-2.5">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), search())}
            placeholder="카테고리 직접 검색 (예: 문구, 생활용품)"
            className="flex-1 rounded-[10px] border border-line bg-inset px-3.5 py-3 text-[13px] text-fg transition-ui hover:border-line-soft"
          />
          <button
            type="button"
            onClick={search}
            className="flex items-center gap-1.5 rounded-[10px] border border-line px-[18px] py-3 text-[13px] text-fg transition-ui hover:border-line-soft hover:bg-[#1b1b21]"
          >
            <Search className="size-3.5" />
            {searching ? "검색 중…" : "검색"}
          </button>
        </div>
      )}
      {error && (
        <span className="text-[12px] text-danger">{error}</span>
      )}
    </Card>
  );
}

function OptionsCard({
  options,
  disabled,
  onChange,
}: {
  options: ProductOption[];
  disabled: boolean;
  onChange: (o: ProductOption[]) => void;
}) {
  const set = (i: number, changes: Partial<ProductOption>) =>
    onChange(options.map((o, idx) => (idx === i ? { ...o, ...changes } : o)));

  return (
    <Card className="gap-3">
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] font-bold text-fg">
          상품 옵션{" "}
          <em className="not-italic text-[12px] font-normal text-muted">
            {options.length}개 자동 인식
          </em>
        </span>
        {!disabled && options.length > 0 && (
          <button
            type="button"
            onClick={() => onChange([])}
            className="text-[12px] text-muted transition-ui hover:text-danger"
          >
            전체 삭제
          </button>
        )}
      </div>

      {options.length > 0 && (
        <div className="grid grid-cols-[1fr_120px_120px_40px] gap-2.5 px-1 text-[11.5px] text-dim">
          <span>옵션명</span>
          <span>옵션가</span>
          <span>재고</span>
          <span />
        </div>
      )}

      {options.map((o, i) => (
        <div key={i} className="grid grid-cols-[1fr_120px_120px_40px] items-center gap-2.5">
          <OptionInput value={o.name} disabled={disabled} onChange={(v) => set(i, { name: v })} />
          <OptionInput
            value={String(o.price)}
            type="number"
            disabled={disabled}
            onChange={(v) => set(i, { price: Number(v) || 0 })}
          />
          <OptionInput
            value={String(o.stock)}
            type="number"
            disabled={disabled}
            onChange={(v) => set(i, { stock: Number(v) || 0 })}
          />
          {!disabled && (
            <button
              type="button"
              aria-label={`${o.name} 옵션 삭제`}
              onClick={() => onChange(options.filter((_, idx) => idx !== i))}
              className="flex justify-center text-danger transition-ui hover:brightness-125"
            >
              <Trash2 className="size-3.5" />
            </button>
          )}
        </div>
      ))}

      {!disabled && (
        <button
          type="button"
          onClick={() => onChange([...options, { name: "", price: 0, stock: 0 }])}
          className="flex w-fit items-center gap-1.5 rounded-[10px] border border-dashed border-line-soft px-4 py-[9px] text-[12.5px] text-muted transition-ui hover:border-accent-line hover:text-accent"
        >
          <Plus className="size-3.5" />
          옵션 직접 추가
        </button>
      )}
    </Card>
  );
}

function OptionInput({
  value,
  type = "text",
  disabled,
  onChange,
}: {
  value: string;
  type?: string;
  disabled?: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <input
      type={type}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-[10px] border border-line bg-inset px-[13px] py-[11px] text-[13.5px] text-fg transition-ui hover:border-line-soft disabled:opacity-60"
    />
  );
}

function KcCard({
  kc,
  disabled,
  onChange,
}: {
  kc: ProductDraft["kc"];
  disabled: boolean;
  onChange: (kc: ProductDraft["kc"]) => void;
}) {
  return (
    <Card className="gap-3">
      <span className="text-[13px] font-bold text-fg">KC인증</span>
      <div className="flex gap-2">
        {(["has", "none"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            disabled={disabled}
            aria-pressed={kc.mode === mode}
            onClick={() => onChange({ ...kc, mode })}
            className={`flex-1 rounded-[10px] border py-[11px] text-center text-[13px] transition-ui disabled:cursor-not-allowed ${
              kc.mode === mode
                ? "border-accent-line bg-accent-bg font-semibold text-fg"
                : "border-line bg-inset text-muted hover:border-line-soft"
            }`}
          >
            {mode === "has" ? "인증 있음" : "인증 없음"}
          </button>
        ))}
      </div>

      {kc.mode === "has" ? (
        <TextInput
          value={kc.cert_number}
          disabled={disabled}
          placeholder="KC 인증번호"
          onChange={(e) => onChange({ ...kc, cert_number: e.target.value })}
        />
      ) : (
        <div className="flex items-center gap-3 rounded-[10px] border border-line bg-inset px-3.5 py-3">
          <span className="flex size-4 flex-none items-center justify-center rounded-full border-2 border-violet">
            <em className="block size-[7px] rounded-full bg-violet" />
          </span>
          <span className="text-[13px] text-fg">KC 대상 아님</span>
        </div>
      )}

      <span className="text-[11.5px] leading-[1.6] text-muted">
        KC인증이 필요한 상품을 인증 없이 판매하면 법적 책임이 발생할 수 있습니다.
      </span>
    </Card>
  );
}

function TagsCard({
  tags,
  disabled,
  onChange,
}: {
  tags: string[];
  disabled: boolean;
  onChange: (t: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const t = draft.trim().replace(/^#/, "");
    if (!t || tags.includes(t)) return;
    onChange([...tags, t]);
    setDraft("");
  };

  return (
    <Card className="gap-3">
      <span className="text-[13px] font-bold text-fg">
        검색 태그 <AiBadge />
      </span>
      <div className="flex flex-wrap gap-2">
        {tags.map((t) => (
          <span
            key={t}
            className="flex items-center gap-1.5 rounded-full border border-line bg-inset px-3 py-[7px] text-[12.5px] text-fg"
          >
            #{t}
            {!disabled && (
              <button
                type="button"
                aria-label={`${t} 태그 삭제`}
                onClick={() => onChange(tags.filter((x) => x !== t))}
                className="text-dim transition-ui hover:text-danger"
              >
                <X className="size-3" />
              </button>
            )}
          </span>
        ))}
        {tags.length === 0 && <span className="text-[12px] text-dim">태그가 없습니다.</span>}
      </div>
      {!disabled && (
        <div className="mt-0.5 flex items-center gap-2.5">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
            placeholder="새 태그 입력"
            className="flex-1 rounded-[10px] border border-line bg-inset px-[13px] py-[11px] text-[12.5px] text-fg transition-ui hover:border-line-soft"
          />
          <button
            type="button"
            onClick={add}
            className="rounded-[10px] border border-line px-4 py-[11px] text-[12.5px] text-fg transition-ui hover:border-line-soft hover:bg-[#1b1b21]"
          >
            추가
          </button>
        </div>
      )}
    </Card>
  );
}

function AttributesCard({
  attributes,
  disabled,
  onChange,
}: {
  attributes: Record<string, string>;
  disabled: boolean;
  onChange: (a: Record<string, string>) => void;
}) {
  const keys = Object.keys(attributes).length
    ? Object.keys(attributes)
    : Object.keys(ATTRIBUTE_OPTIONS);

  return (
    <Card>
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-bold text-fg">
          상품 속성 <AiBadge label="AI 추출" />
        </span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {keys.map((k) => (
          <Field key={k} label={k} required>
            {(id) => (
              <Select
                id={id}
                value={attributes[k] ?? ""}
                disabled={disabled}
                onChange={(e) => onChange({ ...attributes, [k]: e.target.value })}
                options={ATTRIBUTE_OPTIONS[k] ?? [attributes[k] ?? ""]}
                placeholder="선택"
              />
            )}
          </Field>
        ))}
      </div>
    </Card>
  );
}
