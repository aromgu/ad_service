import { ProductDraftEditor } from "@/components/ProductDraftEditor";

/** 프레임 4c — 등록 전 초안의 검토·등록. 등록된 상품은 /store-products/[draftId] 에서 연다. */
export default function ProductDraftPage() {
  return <ProductDraftEditor />;
}
