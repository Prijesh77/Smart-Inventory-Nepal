/** Small line icons drawn inline (no icon font or extra download). Decorative: hidden from screen readers. */
import type { ReactNode, SVGProps } from "react";

function Svg({ children, className = "h-5 w-5", ...props }: SVGProps<SVGSVGElement> & { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true" focusable="false" className={className} {...props}>
      {children}
    </svg>
  );
}

type IconProps = { className?: string };

export const Icon = {
  dashboard: (p: IconProps) => (
    <Svg {...p}><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></Svg>
  ),
  box: (p: IconProps) => (
    <Svg {...p}><path d="M21 8 12 3 3 8l9 5 9-5Z" /><path d="M3 8v8l9 5 9-5V8" /><path d="M12 13v8" /></Svg>
  ),
  warehouse: (p: IconProps) => (
    <Svg {...p}><path d="M3 21V9l9-5 9 5v12" /><path d="M7 21v-8h10v8" /><path d="M7 17h10" /></Svg>
  ),
  trend: (p: IconProps) => (
    <Svg {...p}><path d="m3 17 6-6 4 4 8-8" /><path d="M15 7h6v6" /></Svg>
  ),
  cart: (p: IconProps) => (
    <Svg {...p}><circle cx="9" cy="20" r="1.3" /><circle cx="18" cy="20" r="1.3" />
      <path d="M2.5 3.5h2.5l2.3 11.2a2 2 0 0 0 2 1.6h7.9a2 2 0 0 0 2-1.5L21 8H6" /></Svg>
  ),
  clipboard: (p: IconProps) => (
    <Svg {...p}><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4V3h6v1" /><path d="M9 10h6M9 14h6M9 18h3" /></Svg>
  ),
  chart: (p: IconProps) => (
    <Svg {...p}><path d="M3 3v18h18" /><path d="M8 17v-5M13 17V8M18 17v-8" /></Svg>
  ),
  settings: (p: IconProps) => (
    <Svg {...p}><path d="M4 7h9M17 7h3M4 17h3M11 17h9" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" /></Svg>
  ),
  logout: (p: IconProps) => (
    <Svg {...p}><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" /><path d="m10 16-4-4 4-4" /><path d="M6 12h10" /></Svg>
  ),
  menu: (p: IconProps) => (
    <Svg {...p}><path d="M4 6h16M4 12h16M4 18h16" /></Svg>
  ),
  close: (p: IconProps) => (
    <Svg {...p}><path d="M6 6l12 12M18 6 6 18" /></Svg>
  ),
  info: (p: IconProps) => (
    <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></Svg>
  ),
  alert: (p: IconProps) => (
    <Svg {...p}><path d="M12 3 2 20h20L12 3Z" /><path d="M12 10v4M12 17h.01" /></Svg>
  ),
  money: (p: IconProps) => (
    <Svg {...p}><rect x="2.5" y="6" width="19" height="12" rx="2" /><circle cx="12" cy="12" r="2.5" /><path d="M6 9.5v.01M18 14.5v.01" /></Svg>
  ),
  inbox: (p: IconProps) => (
    <Svg {...p}><path d="M3 13h5l1.5 3h5L16 13h5" /><path d="M5 5h14l2 8v6H3v-6l2-8Z" /></Svg>
  ),
};

export type IconName = keyof typeof Icon;
