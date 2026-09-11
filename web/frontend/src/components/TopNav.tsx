"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { LogoMark, Wordmark } from "./Logo";

/** 순서 고정: AI 상세페이지 → AI 상품등록 → AI 블로그 */
const TABS = [
  { label: "AI 상세페이지", href: "/detail/new", match: /^\/(detail|jobs)(\/|$)/ },
  { label: "AI 상품등록", href: "/product", match: /^\/product/ },
  { label: "AI 블로그", href: "/blog", match: /^\/blog/ },
] as const;

export function TopNav() {
  const pathname = usePathname() ?? "/";
  const onWorks = pathname.startsWith("/works");
  const onStore = pathname.startsWith("/store-products");

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-6 border-b border-line bg-ink px-7">
      <Link href="/" className="flex items-center gap-2.5 rounded-lg">
        <LogoMark size={28} />
        <Wordmark />
      </Link>

      <nav className="flex items-center gap-1 rounded-full border border-line p-1">
        {TABS.map((tab) => {
          // 내 작업·등록된 상품 관리는 특정 기능에 속하지 않으므로 그때는 세 탭 모두 비활성.
          const active = !onWorks && !onStore && tab.match.test(pathname);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={active ? "page" : undefined}
              className={
                active
                  ? "grad rounded-full px-4 py-2 text-[13px] font-semibold text-white transition-ui hover:brightness-110"
                  : "rounded-full px-3.5 py-2 text-[13px] text-muted transition-ui hover:bg-[#1b1b21] hover:text-fg"
              }
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>

      <div className="flex items-center gap-2">
        <NavPill href="/works" active={onWorks}>
          내 작업
        </NavPill>
        <NavPill href="/store-products" active={onStore}>
          등록된 상품 관리
        </NavPill>
      </div>
    </header>
  );
}

function NavPill({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`rounded-full border px-3.5 py-[7px] text-[13px] text-fg transition-ui ${
        active
          ? "border-accent-line bg-accent-bg"
          : "border-line hover:border-line-soft hover:bg-[#1b1b21]"
      }`}
    >
      {children}
    </Link>
  );
}
