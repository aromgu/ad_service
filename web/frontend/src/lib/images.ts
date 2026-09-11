import { api } from "./api";
import type { Asset } from "./types";

/**
 * 화면에 올라와 있는 이미지 한 장.
 * 아직 안 올린 로컬 파일(`file`)일 수도, 이미 업로드된 것(`assetId`)일 수도 있다.
 * AI 사진 편집(3a-2)으로 만든 이미지는 후자로 들어온다.
 */
export interface PickedImage {
  key: string;
  name: string;
  previewUrl: string;
  file?: File;
  assetId?: string;
}

let seq = 0;
const nextKey = () => `img-${++seq}-${Date.now()}`;

export function fromFile(file: File): PickedImage {
  return { key: nextKey(), name: file.name, previewUrl: URL.createObjectURL(file), file };
}

export function fromAsset(asset: Asset, previewUrl: string): PickedImage {
  return { key: nextKey(), name: asset.filename, previewUrl, assetId: asset.id };
}

/** 로컬 파일만 업로드하고, 화면에 보이는 순서 그대로 asset id 배열을 돌려준다. */
export async function resolveAssetIds(images: PickedImage[]): Promise<string[]> {
  const pending = images.filter((i) => i.file);
  const uploaded: string[] = [];
  // 업로드 API 는 한 번에 5장까지 받는다.
  for (let i = 0; i < pending.length; i += 5) {
    const batch = pending.slice(i, i + 5).map((p) => p.file!);
    uploaded.push(...(await api.uploadImages(batch)).map((a) => a.id));
  }
  let cursor = 0;
  return images.map((img) => img.assetId ?? uploaded[cursor++]);
}

/** objectURL 로 만든 미리보기만 해제한다. 서버 URL 은 건드리면 안 된다. */
export function revoke(image: PickedImage) {
  if (image.file) URL.revokeObjectURL(image.previewUrl);
}
