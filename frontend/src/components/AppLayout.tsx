import { NavLink, Outlet, useLocation } from "react-router-dom";

import type { ReactNode, SVGProps } from "react";

type NavigationItem = {
  to: string;
  label: string;
  icon: (props: SVGProps<SVGSVGElement>) => ReactNode;
  accent?: boolean;
};

function ClipboardIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <rect x="6" y="4" width="12" height="16" rx="2" />
      <path d="M9 4.5h6a1.5 1.5 0 0 0-3 0H9a1.5 1.5 0 0 0 3 0" />
      <path d="M9 10h6" />
      <path d="M9 14h6" />
    </svg>
  );
}

function UsersIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2" />
      <circle cx="9.5" cy="7" r="3" />
      <path d="M20 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16.5 4.13a3 3 0 0 1 0 5.74" />
    </svg>
  );
}

function WandIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="m3 21 9-9" />
      <path d="m14 7 3-3" />
      <path d="m13 4 3 3" />
      <path d="M18 5h3" />
      <path d="M19.5 3.5v3" />
      <path d="M5 8H2" />
      <path d="M3.5 6.5v3" />
      <path d="m7 3 .8 1.7L9.5 5.5l-1.7.8L7 8 6.2 6.3l-1.7-.8 1.7-.8z" />
    </svg>
  );
}

function HangerIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 6a2 2 0 1 0-2-2" />
      <path d="M10 4h2a2 2 0 0 1 2 2v2" />
      <path d="M5 15h14" />
      <path d="m5 15 6.2 5.5a1.2 1.2 0 0 0 1.6 0L19 15" />
    </svg>
  );
}

function WrenchIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M14.7 6.3a4 4 0 1 0 3 3L10 17l-3 1 1-3 7.7-7.7Z" />
    </svg>
  );
}

function FactoryIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M3 21V9l7 4V9l7 4v8Z" />
      <path d="M3 21h18" />
      <path d="M7 21v-4" />
      <path d="M12 21v-4" />
      <path d="M17 21v-4" />
    </svg>
  );
}

function BoxIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="m12 3 8 4.5v9L12 21 4 16.5v-9Z" />
      <path d="m12 12 8-4.5" />
      <path d="m12 12-8-4.5" />
      <path d="M12 12v9" />
    </svg>
  );
}

function ShieldIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 3 5 6v5c0 5 3.5 8 7 10 3.5-2 7-5 7-10V6Z" />
      <path d="m9.5 12 1.7 1.7L15 10" />
    </svg>
  );
}

function PlusIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </svg>
  );
}

function TuszkoLogoMark() {
  return (
    <svg viewBox="0 0 188 84" aria-hidden="true" className="h-14 w-[7.2rem]">
      <defs>
        <linearGradient id="tuszkoOrange" x1="0" x2="1" y1="0.1" y2="0.9">
          <stop offset="0%" stopColor="#ff9a2f" />
          <stop offset="100%" stopColor="#f06a21" />
        </linearGradient>
        <linearGradient id="tuszkoViolet" x1="0" x2="1" y1="0.2" y2="0.8">
          <stop offset="0%" stopColor="#3b1f77" />
          <stop offset="100%" stopColor="#24124f" />
        </linearGradient>
      </defs>
      <path d="M18 21h54l-6.5 10.5H42.5v8.8h26.6l-6.4 10.4H42.5V61H29.2V31.5H18Z" fill="url(#tuszkoOrange)" />
      <path d="M43 10.5h48.8L84.8 21H58.4v9.6H45.1V21.1l-9.8-10.6Z" fill="url(#tuszkoOrange)" />
      <path d="M92.8 63.2c4.4 0 8-3.6 8-8.1s-3.6-8.1-8-8.1-8 3.6-8 8.1 3.6 8.1 8 8.1Z" fill="url(#tuszkoViolet)" />
      <path d="M84.6 30.8h38.4c17.1 0 31-13.9 31-31h13.3c0 24.4-19.8 44.3-44.3 44.3h-21.7v38.5H87.9V44.1H71.7Z" fill="url(#tuszkoViolet)" transform="translate(0 1)" />
      <path d="M127.2 19.6h42.3l-5.9 9.8h-36.4Z" fill="url(#tuszkoViolet)" />
    </svg>
  );
}

const primaryNavigation: NavigationItem[] = [
  { to: "/zlecenia", label: "Zlecenia", icon: ClipboardIcon },
  { to: "/kierownik", label: "Kierownik", icon: UsersIcon },
  { to: "/przygotowanie", label: "Przygotowanie", icon: WandIcon },
  { to: "/zawieszanie", label: "Zawieszanie", icon: HangerIcon },
  { to: "/produkcja-reczna", label: "Produkcja ręczna", icon: WrenchIcon },
  { to: "/produkcja-automat", label: "Produkcja: Automat", icon: FactoryIcon },
  { to: "/produkcja-decoral", label: "Produkcja Decoral", icon: BoxIcon },
  { to: "/pakowanie", label: "Pakowanie", icon: BoxIcon },
];

const secondaryNavigation: NavigationItem[] = [
  { to: "/farby", label: "Farby", icon: ClipboardIcon },
  { to: "/audyt", label: "Audyt", icon: ShieldIcon },
  { to: "/zlecenia/nowe", label: "Dodaj zlecenie", icon: PlusIcon, accent: true },
];

export function AppLayout() {
  const location = useLocation();

  function getSectionTitle(pathname: string): string {
    if (pathname.startsWith("/farby")) return "Farby";
    if (pathname.startsWith("/audyt")) return "Audyt";
    if (pathname.startsWith("/kierownik")) return "Kierownik";
    if (pathname.startsWith("/produkcja-reczna")) return "Produkcja ręczna";
    if (pathname.startsWith("/produkcja-automat")) return "Produkcja: Automat";
    if (pathname.startsWith("/produkcja-decoral")) return "Produkcja Decoral";
    if (pathname.startsWith("/pakowanie")) return "Pakowanie";
    if (pathname.startsWith("/zawieszanie")) return "Zawieszanie";
    if (pathname.startsWith("/przygotowanie")) return "Przygotowanie powierzchni";
    if (pathname.startsWith("/zlecenia/nowe")) return "Nowe zlecenie";
    if (pathname.startsWith("/zlecenia/")) return "Szczegóły zlecenia";
    return "Zlecenia";
  }

  return (
    <div className="min-h-screen bg-shell">
      <div className="mx-auto flex min-h-screen w-full max-w-[1520px] flex-col px-3 py-3 sm:px-4 lg:flex-row lg:gap-5 lg:px-5 lg:py-4">

        {/* Sidebar */}
        <aside className="flex w-full flex-col gap-4 lg:w-[220px] lg:flex-none">

          {/* Logo */}
          <div className="rounded-[1.9rem] bg-white px-5 py-5 shadow-panel ring-1 ring-brand-line/70">
            <div className="flex flex-col items-center text-center">
              <TuszkoLogoMark />
              <p className="mt-2 text-[2rem] font-black uppercase tracking-[0.08em] leading-none text-brand-ink">TUSZKO</p>
              <p className="mt-1.5 text-[0.6rem] font-bold uppercase tracking-[0.3em] text-brand-muted">Lakiernia proszkowa</p>
            </div>
          </div>

          {/* Navigation */}
          <div className="rounded-[1.9rem] bg-white px-3 py-3 shadow-panel ring-1 ring-brand-line/70">
            <nav className="space-y-1">
              {primaryNavigation.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    [
                      "group flex items-center gap-3 rounded-[1rem] px-3 py-2.5 text-sm font-semibold transition",
                      isActive
                        ? "bg-brand-900 text-white shadow-brand"
                        : "text-brand-muted hover:bg-brand-surface hover:text-brand-ink",
                    ].join(" ")
                  }
                >
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-current/10 bg-current/5">
                    <item.icon className="h-[1rem] w-[1rem]" />
                  </span>
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </nav>

            <div className="my-3 h-px bg-brand-line" />

            <nav className="space-y-1">
              {secondaryNavigation.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    [
                      "group flex items-center gap-3 rounded-[1rem] px-3 py-2.5 text-sm font-semibold transition",
                      item.accent || isActive
                        ? "bg-brand-warm text-brand-ink shadow-[0_8px_20px_rgba(255,140,32,0.2)] hover:bg-brand-warm-strong"
                        : "text-brand-muted hover:bg-brand-surface hover:text-brand-ink",
                    ].join(" ")
                  }
                >
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-current/10 bg-white/40">
                    <item.icon className="h-[1rem] w-[1rem]" />
                  </span>
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </nav>
          </div>

          {/* Footer info */}
          <div className="mt-auto rounded-[1.9rem] bg-white px-4 py-4 shadow-panel ring-1 ring-brand-line/70">
            <p className="text-xs font-semibold text-brand-ink">TUSZKO Lakiernia Proszkowa</p>
            <p className="mt-1 text-xs leading-5 text-brand-muted">System sterowania produkcją.</p>
            <p className="mt-2 text-[0.6rem] font-semibold uppercase tracking-[0.18em] text-brand-muted">Wersja 2.1.0</p>
          </div>
        </aside>

        {/* Main content */}
        <div className="flex min-w-0 flex-1 flex-col gap-4">

          {/* Header */}
          <header className="rounded-[1.9rem] bg-white px-5 py-4 shadow-panel ring-1 ring-brand-line/70 sm:px-6">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-muted">Panel operacyjny</p>
                <h1 className="mt-0.5 truncate text-[1.6rem] font-bold text-brand-ink">{getSectionTitle(location.pathname)}</h1>
              </div>
              <NavLink
                to="/zlecenia/nowe"
                className="inline-flex shrink-0 items-center gap-2 rounded-full bg-brand-warm px-5 py-2.5 text-sm font-semibold text-brand-ink transition hover:bg-brand-warm-strong"
              >
                <PlusIcon className="h-4 w-4" />
                <span className="hidden sm:inline">Dodaj zlecenie</span>
                <span className="sm:hidden">Dodaj</span>
              </NavLink>
            </div>
          </header>

          <div className="min-w-0 flex-1">
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  );
}
