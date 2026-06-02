import { NavLink, Outlet, useLocation } from "react-router-dom";

export function AppLayout() {
  const location = useLocation();

  function getSectionTitle(pathname: string): string {
    if (pathname.startsWith("/farby")) {
      return "Farby";
    }

    if (pathname.startsWith("/audyt")) {
      return "Audyt";
    }

    if (pathname.startsWith("/kierownik")) {
      return "Kierownik";
    }

    if (pathname.startsWith("/produkcja-reczna")) {
      return "Produkcja ręczna";
    }

    if (pathname.startsWith("/produkcja-automat")) {
      return "Produkcja: Automat";
    }

    if (pathname.startsWith("/produkcja-decoral")) {
      return "Produkcja Decoral";
    }

    if (pathname.startsWith("/pakowanie")) {
      return "Pakowanie";
    }

    if (pathname.startsWith("/zawieszanie")) {
      return "Zawieszanie";
    }

    if (pathname.startsWith("/przygotowanie")) {
      return "Przygotowanie powierzchni";
    }

    if (pathname.startsWith("/zlecenia/nowe")) {
      return "Nowe zlecenie";
    }

    if (pathname.startsWith("/zlecenia/")) {
      return "Szczegóły zlecenia";
    }

    return "Zlecenia";
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-white/60 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Panel operacyjny</p>
            <h1 className="text-xl font-semibold text-ink">{getSectionTitle(location.pathname)}</h1>
          </div>
          <nav className="flex flex-wrap items-center gap-2 rounded-full border border-line bg-mist p-1">
            <NavLink
              to="/zlecenia"
              className={({ isActive }) =>
                [
                  "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                ].join(" ")
              }
            >
              Zlecenia
            </NavLink>
            <NavLink
              to="/kierownik"
              className={({ isActive }) =>
                [
                  "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                ].join(" ")
              }
            >
              Kierownik
            </NavLink>
            <NavLink
              to="/przygotowanie"
              className={({ isActive }) =>
                [
                  "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                ].join(" ")
              }
            >
              Przygotowanie
            </NavLink>
            <NavLink
              to="/zawieszanie"
              className={({ isActive }) =>
                [
                  "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                ].join(" ")
              }
            >
              Zawieszanie
            </NavLink>
            <NavLink
              to="/produkcja-reczna"
              className={({ isActive }) =>
                [
                  "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                ].join(" ")
              }
            >
              Produkcja ręczna
            </NavLink>
            <NavLink
              to="/produkcja-automat"
              className={({ isActive }) =>
                [
                  "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                ].join(" ")
              }
            >
              Produkcja: Automat
            </NavLink>
            <NavLink
              to="/produkcja-decoral"
              className={({ isActive }) =>
                [
                  "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                ].join(" ")
              }
            >
              Produkcja Decoral
            </NavLink>
            <NavLink
              to="/pakowanie"
              className={({ isActive }) =>
                [
                  "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                ].join(" ")
              }
            >
              Pakowanie
            </NavLink>
            <NavLink
              to="/farby"
              className={({ isActive }) =>
                [
                  "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                ].join(" ")
              }
            >
              Farby
            </NavLink>
            <NavLink
              to="/audyt"
              className={({ isActive }) =>
                [
                  "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-white text-ink shadow-sm" : "text-steel hover:text-accent",
                ].join(" ")
              }
            >
              Audyt
            </NavLink>
            <NavLink
              to="/zlecenia/nowe"
              className={({ isActive }) =>
                [
                  "rounded-full px-4 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-accent text-white" : "text-steel hover:text-accent",
                ].join(" ")
              }
            >
              Dodaj zlecenie
            </NavLink>
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  );
}