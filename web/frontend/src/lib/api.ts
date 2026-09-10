import { API_BASE } from "./env";
import type {
  Asset,
  BlogForm,
  ChatMessage,
  DetailPageForm,
  DocumentModel,
  Job,
  ProductDraft,
  ProductDraftPatch,
  ProductRegForm,
  Section,
  ShippingSettings,
  WorkspaceItem,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      `백엔드에 연결할 수 없습니다. (${API_BASE}) 서버가 켜져 있는지 확인해 주세요.`,
      0,
    );
  }
  if (!res.ok) {
    const detail = await res
      .json()
      .then((d) => (typeof d?.detail === "string" ? d.detail : null))
      .catch(() => null);
    throw new ApiError(detail ?? `요청에 실패했습니다. (${res.status})`, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string; provider: string }>("/health"),

  uploadImages: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return request<Asset[]>("/uploads", { method: "POST", body: fd });
  },

  aiEditImages: (prompt: string, count: number, sourceIds: string[]) =>
    request<Asset[]>("/uploads/ai-edit", {
      method: "POST",
      body: JSON.stringify({ prompt, count, source_ids: sourceIds }),
    }),

  createDetailPageJob: (form: DetailPageForm, imageIds: string[]) =>
    request<Job>("/jobs", {
      method: "POST",
      body: JSON.stringify({ type: "detail_page", form, image_ids: imageIds }),
    }),

  createBlogJob: (form: BlogForm, imageIds: string[]) =>
    request<Job>("/jobs", {
      method: "POST",
      body: JSON.stringify({ type: "blog", form, image_ids: imageIds }),
    }),

  createProductJob: (form: ProductRegForm, imageIds: string[], fromDocumentId?: string) =>
    request<Job>("/jobs", {
      method: "POST",
      body: JSON.stringify({
        type: "product_reg",
        form,
        image_ids: imageIds,
        from_document_id: fromDocumentId ?? null,
      }),
    }),

  getJob: (id: string) => request<Job>(`/jobs/${id}`),
  cancelJob: (id: string) => request<Job>(`/jobs/${id}/cancel`, { method: "POST" }),
  retryJob: (id: string) => request<Job>(`/jobs/${id}/retry`, { method: "POST" }),

  getDocument: (id: string) => request<DocumentModel>(`/documents/${id}`),
  patchDocument: (id: string, patch: { title?: string; sections?: Section[] }) =>
    request<DocumentModel>(`/documents/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  getMessages: (id: string) => request<ChatMessage[]>(`/documents/${id}/messages`),
  chat: (id: string, message: string) =>
    request<{ messages: ChatMessage[]; document: DocumentModel }>(`/documents/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  getProductDraft: (id: string) => request<ProductDraft>(`/product-drafts/${id}`),
  patchProductDraft: (id: string, patch: ProductDraftPatch) =>
    request<ProductDraft>(`/product-drafts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  registerProduct: (id: string) =>
    request<ProductDraft>(`/product-drafts/${id}/register`, { method: "POST" }),
  searchCategories: (q: string) =>
    request<string[]>(`/product-drafts/categories/search?q=${encodeURIComponent(q)}`),

  getShippingSettings: () => request<ShippingSettings>("/settings/shipping"),
  putShippingSettings: (s: ShippingSettings) =>
    request<ShippingSettings>("/settings/shipping", { method: "PUT", body: JSON.stringify(s) }),

  workspace: (type?: string) =>
    request<WorkspaceItem[]>(`/workspace${type ? `?type=${encodeURIComponent(type)}` : ""}`),
  deleteWorkspaceItem: (jobId: string) =>
    request<void>(`/workspace/${jobId}`, { method: "DELETE" }),
};
