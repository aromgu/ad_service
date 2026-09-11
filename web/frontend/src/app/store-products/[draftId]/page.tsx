import { ProductDraftEditor } from "@/components/ProductDraftEditor";

/**
 * 등록된 상품 관리 → 상품 하나. 편집 화면은 4c 와 같고 버튼만 '수정'·'삭제'로 바뀐다.
 * 주소를 따로 둬서 상단 메뉴에서 '등록된 상품 관리'가 켜진다.
 */
export default function StoreProductPage() {
  return <ProductDraftEditor />;
}
