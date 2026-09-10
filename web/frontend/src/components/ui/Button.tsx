import Link from "next/link";

type Variant = "primary" | "outline" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "grad text-white font-bold hover:brightness-110",
  outline: "border border-line bg-surface text-fg hover:border-line-soft hover:bg-[#1b1b21]",
  ghost: "text-muted hover:text-fg",
};

type BaseProps = {
  variant?: Variant;
  className?: string;
  children: React.ReactNode;
};

export function Button({
  variant = "outline",
  className = "",
  children,
  ...rest
}: BaseProps & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`inline-flex items-center justify-center rounded-[10px] transition-ui disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:brightness-100 ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function ButtonLink({
  variant = "outline",
  className = "",
  href,
  children,
}: BaseProps & { href: string }) {
  return (
    <Link
      href={href}
      className={`inline-flex items-center justify-center rounded-[10px] transition-ui ${VARIANTS[variant]} ${className}`}
    >
      {children}
    </Link>
  );
}
