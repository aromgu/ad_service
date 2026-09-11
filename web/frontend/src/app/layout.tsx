import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "스마트한 스미스 씨",
  description:
    "제품 사진 한 장으로 상세페이지·상품등록·블로그 홍보글까지. 소상공인을 위한 생성형 AI 서비스.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <head>
        {/* Pretendard — 레퍼런스 지정 폰트 */}
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
