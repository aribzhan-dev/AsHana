export function LogoMark({ size = 40 }: { size?: number }) {
  return (
    <svg
      className="logo-mark"
      width={size}
      height={size}
      viewBox="0 0 48 48"
      aria-hidden="true"
      focusable="false"
    >
      <path
        className="logo-arch"
        d="M6 42V24a18 18 0 0 1 36 0v18H32V24a8 8 0 0 0-16 0v18Z"
      />
      <path className="logo-bowl" d="M16 31h16a8 8 0 0 1-16 0Z" />
      <path
        className="logo-rays"
        d="M38 7l2-4M42 11l4-2M41 4.5l3.5-1.5"
        strokeWidth="2.6"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

export function Logo({ caption }: { caption?: string }) {
  return (
    <span className="logo">
      <LogoMark />
      <span className="logo-text">
        <span className="logo-word">ashana</span>
        {caption && <span className="logo-caption">{caption}</span>}
      </span>
    </span>
  );
}
