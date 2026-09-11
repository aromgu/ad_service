import type { NextConfig } from "next";

const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const { hostname, port, protocol } = new URL(apiBase);

const nextConfig: NextConfig = {
  // 좌하단 개발 표시기를 끈다. 컴포저의 사진 첨부 버튼을 가려서 클릭이 막혔다.
  devIndicators: false,

  images: {
    // 백엔드가 /static 아래로 서빙하는 업로드 원본과 생성 결과 이미지.
    remotePatterns: [
      {
        protocol: protocol.replace(":", "") as "http" | "https",
        hostname,
        port: port || undefined,
        pathname: "/static/**",
      },
      // 스마트스토어에 올라간 상품 이미지 (등록된 상품 관리).
      { protocol: "https", hostname: "**.pstatic.net" },
    ],
  },
};

export default nextConfig;
