import { NavLink, Outlet, useLocation } from "react-router-dom";
import { ClipboardList, UserCog, FlaskConical, Hand, Factory, Package, Palette, ShieldCheck, Plus, LogOut } from "lucide-react";
import type { SVGProps } from "react";
import { isFullAccessUser, useAuth } from "../context/AuthContext";
import { getStationPanelPath, type StationId } from "../api/stationContext";

type NavigationItem = {
  to: string;
  label: string;
  icon: React.ElementType;
  accent?: boolean;
};

function SHookIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 2.5v1" />
      <path d="M12 3.5a3.5 3.5 0 0 1 3.5 3.5 3.5 3.5 0 0 1-3.5 3.5 3.5 3.5 0 0 0-3.5 3.5 3.5 3.5 0 0 0 3.5 3.5" />
      <path d="M15.5 14a3.5 3.5 0 0 1-3.5 3.5v1" />
    </svg>
  );
}

function DecoralIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M5 10 8.5 7 12 10 15.5 7 19 10" />
      <path d="M5 15 8.5 12 12 15 15.5 12 19 15" />
    </svg>
  );
}

const primaryNavigation: NavigationItem[] = [
  { to: "/zlecenia", label: "Zlecenia", icon: ClipboardList },
  { to: "/kierownik", label: "Kierownik", icon: UserCog },
  { to: "/przygotowanie", label: "Przygotowanie", icon: FlaskConical },
  { to: "/zawieszanie", label: "Zawieszanie", icon: SHookIcon },
  { to: "/produkcja-reczna", label: "Produkcja ręczna", icon: Hand },
  { to: "/produkcja-automat", label: "Produkcja: Automat", icon: Factory },
  { to: "/produkcja-decoral", label: "Produkcja Decoral", icon: DecoralIcon },
  { to: "/pakowanie", label: "Pakowanie", icon: Package },
];

const secondaryNavigation: NavigationItem[] = [
  { to: "/farby", label: "Farby", icon: Palette },
  { to: "/audyt", label: "Audyt", icon: ShieldCheck },
  { to: "/zlecenia/nowe", label: "Dodaj zlecenie", icon: Plus, accent: true },
];

const stationLabels: Record<string, string> = {
  OFFICE: "Biuro",
  MANAGER: "Kierownik",
  SURFACE_PREPARATION: "Przygotowanie",
  HANGING: "Zawieszanie",
  MANUAL_PRODUCTION: "Produkcja ręczna",
  AUTOMATIC_PRODUCTION: "Produkcja automat",
  PACKING: "Pakowanie",
  DECORAL_PRODUCTION: "Produkcja Decoral",
};

export function AppLayout() {
  const location = useLocation();
  const { user, logout } = useAuth();
  const fullAccess = isFullAccessUser(user);

  const visiblePrimary = fullAccess
    ? primaryNavigation
    : primaryNavigation.filter((item) => item.to === getStationPanelPath(user?.station_id as StationId));

  const visibleSecondary = fullAccess ? secondaryNavigation : [];

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
          <div className="rounded-[1.9rem] bg-white px-4 py-5 shadow-panel ring-1 ring-brand-line/70">
            <div className="flex items-center justify-center">
              <img src="/logo.png" alt="TUSZKO Lakiernia Proszkowa" className="w-full max-w-[160px] h-auto" />
            </div>
          </div>

          {/* Navigation */}
          <div className="rounded-[1.9rem] bg-white px-3 py-3 shadow-panel ring-1 ring-brand-line/70">
            <nav className="space-y-1">
              {visiblePrimary.map((item) => (
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
                    <item.icon className="h-[1rem] w-[1rem]" strokeWidth={1.8} />
                  </span>
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </nav>

            {visibleSecondary.length > 0 && (
              <>
                <div className="my-3 h-px bg-brand-line" />
                <nav className="space-y-1">
                  {visibleSecondary.map((item) => (
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
                        <item.icon className="h-[1rem] w-[1rem]" strokeWidth={1.8} />
                      </span>
                      <span>{item.label}</span>
                    </NavLink>
                  ))}
                </nav>
              </>
            )}
          </div>

          {/* User info + logout */}
          <div className="mt-auto rounded-[1.9rem] bg-white px-4 py-4 shadow-panel ring-1 ring-brand-line/70">
            <p className="text-xs font-semibold text-brand-ink">TUSZKO Lakiernia Proszkowa</p>
            <p className="mt-1 text-xs leading-5 text-brand-muted">System sterowania produkcją.</p>
            {user && (
              <div className="mt-3 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-[0.65rem] font-semibold text-brand-ink">{stationLabels[user.station_id] ?? user.station_id}</p>
                  {user.is_admin && (
                    <p className="text-[0.6rem] font-semibold uppercase tracking-[0.15em] text-amber-600">Admin</p>
                  )}
                </div>
                <button
                  onClick={logout}
                  title="Wyloguj"
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-brand-muted transition hover:bg-brand-surface hover:text-brand-ink"
                >
                  <LogOut className="h-3.5 w-3.5" strokeWidth={1.8} />
                </button>
              </div>
            )}
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
              {fullAccess && (
                <NavLink
                  to="/zlecenia/nowe"
                  className="inline-flex shrink-0 items-center gap-2 rounded-full bg-brand-warm px-5 py-2.5 text-sm font-semibold text-brand-ink transition hover:bg-brand-warm-strong"
                >
                  <Plus className="h-4 w-4" strokeWidth={1.8} />
                  <span className="hidden sm:inline">Dodaj zlecenie</span>
                  <span className="sm:hidden">Dodaj</span>
                </NavLink>
              )}
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
