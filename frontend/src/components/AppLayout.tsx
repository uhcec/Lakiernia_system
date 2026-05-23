import { NavLink, Outlet } from "react-router-dom";

export function AppLayout() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-white/60 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent">Panel operacyjny</p>
            <h1 className="text-xl font-semibold text-ink">Zlecenia</h1>
          </div>
          <nav className="flex items-center gap-2 rounded-full border border-line bg-mist p-1">
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