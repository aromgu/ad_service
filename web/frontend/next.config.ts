import type { NextConfig } from "next";

const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const { hostname, port, protocol } = new URL(apiBase);

const nextConfig: NextConfig = {
  images: {
    // 백엔드가 /static 아래로 서빙하는 업로드 원본과 생성 결과 이미지.
    remotePatterns: [
      {
        protocol: protocol.replace(":", "") as "http" | "https",
        hostname,
        port: port || undefined,
        pathname: "/static/**",
      },
    ],
  },
};

export default nextConfig;
