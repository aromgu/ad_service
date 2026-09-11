export type JobType = "detail_page" | "blog" | "product_reg";

export type Tone = "감성적" | "정보 중심";

export interface DetailPageForm {
  product_name: string;
  target: string;
  language: string;
  tone: Tone;
  length: string;
  features: string;
  advanced?: Record<string, unknown>;
}

export interface Asset {
  id: string;
  kind: string;
  filename: string;
  url: string;
  content_type: string;
  size_bytes: number;
}

export type JobStatus = "queued" | "running" | "done" | "failed" | "canceled";

export interface JobStep {
  key: string;
  label: string;
  state: "done" | "active" | "pending";
}

export interface BlogForm {
  topic: string;
  style: string;
  extra_request: string;
}

export interface ShippingSettings {
  origin_address: string;
  return_address: string;
  return_same_as_origin: boolean;
  shipping_fee: number;
  return_fee: number;
  exchange_fee: number;
  cs_phone: string;
  courier: string;
}

export interface ProductRegForm {
  product_info: string;
  shipping: ShippingSettings;
  submit_mode: "auto" | "review";
  /** 2c 에디터 '가격 설정'에서 정한 판매가 */
  price?: number | null;
}

export interface Job {
  id: string;
  type: JobType;
  status: JobStatus;
  progress: number;
  steps: JobStep[];
  document_id: string | null;
  product_draft_id: string | null;
  submit_mode: string | null;
  error: string | null;
  created_at: string;
}

export type SectionType =
  | "eyebrow"
  | "headline"
  | "stat"
  | "subclaim"
  | "image"
  | "note"
  | "paragraph"  // 블로그 본문 문단
  | "heading";   // 블로그 소제목

export interface Section {
  id: string;
  type: SectionType | string;
  visible: boolean;
  content: {
    text?: string;
    lines?: string[];
    fontSize?: number;
    bold?: boolean;
    italic?: boolean;
    align?: "left" | "center" | "right";
    color?: string;
    prefix?: string;
    value?: string;
    suffix?: string;
    url?: string | null;
    alt?: string;
    height?: number;
    caption?: string;
    letterSpacing?: string;
  };
}

export interface DocumentModel {
  id: string;
  type: string;
  title: string;
  sections: Section[];
  thumbnail_url: string | null;
  updated_at: string;
}

export interface ChatMeta {
  images?: string[];
  toolSteps?: string[];
  askUser?: boolean;
  summaryCard?: { label: string; value: string }[];
  closing?: string;
  footer?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  meta: ChatMeta;
  created_at: string;
}

export interface WorkspaceItem {
  id: string;
  job_id: string;
  document_id: string | null;
  product_draft_id: string | null;
  type: JobType;
  status: JobStatus;
  progress: number;
  title: string;
  thumbnail_url: string | null;
  created_at: string;
}


// ---------- 상품등록 (4c) ----------
export interface CategoryCandidate {
  /** 네이버 leafCategoryId. 등록에 반드시 필요하다. */
  id: string;
  path: string;
  confidence: number;
}

export interface ProductOption {
  name: string;
  price: number;
  stock: number;
}

export interface KcInfo {
  mode: "has" | "none";
  detail: string;
  cert_number: string;
}

export interface ProductDraft {
  id: string;
  status: "draft" | "registered";
  /** 내 작업 카드에 보이는 이름. 상품명(product_name)과 별개다. */
  title: string;
  analysis: {
    image_count?: number;
    ocr_chars?: number;
    source?: string;
    /** 자동 등록이 실패했을 때의 사유 */
    register_error?: string;
  };
  description: string;
  image_urls: string[];
  representative_image_url: string | null;
  product_name: string;
  exclude_brand_from_name: boolean;
  brand: string;
  manufacturer: string;
  seller_code: string;
  category_candidates: CategoryCandidate[];
  selected_category: string;
  selected_category_id: string;
  /** 등록 성공 시 네이버가 준 번호 */
  naver_origin_product_no: string;
  naver_channel_product_no: string;
  price: number | null;
  discount_rate: number;
  shipping_fee: number;
  stock: number;
  options: ProductOption[];
  kc: KcInfo;
  tags: string[];
  attributes: Record<string, string>;
  shipping: Partial<ShippingSettings>;
  registered_at: string | null;
  updated_at: string;
}

export type ProductDraftPatch = Partial<
  Pick<
    ProductDraft,
    | "title"
    | "description"
    | "representative_image_url"
    | "product_name"
    | "exclude_brand_from_name"
    | "brand"
    | "manufacturer"
    | "seller_code"
    | "selected_category"
    | "selected_category_id"
    | "price"
    | "discount_rate"
    | "shipping_fee"
    | "stock"
    | "options"
    | "kc"
    | "tags"
    | "attributes"
  >
>;
