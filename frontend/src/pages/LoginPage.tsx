import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { isFullAccessUser, useAuth } from "../context/AuthContext";
import { getStationPanelPath, type StationId } from "../api/stationContext";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [loginValue, setLoginValue] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login({ login: loginValue, password });
      // Redirect based on station
      const user = JSON.parse(localStorage.getItem("auth_user") ?? "{}") as { station_id: string; is_admin: boolean };
      const target = isFullAccessUser({ login: loginValue, station_id: user.station_id, is_admin: user.is_admin })
        ? "/zlecenia"
        : getStationPanelPath(user.station_id as StationId);
      navigate(target, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Błąd logowania");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-shell flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="rounded-[1.9rem] bg-white px-8 py-10 shadow-panel ring-1 ring-brand-line/70">
          <div className="mb-8 flex justify-center">
            <img src="/logo.png" alt="TUSZKO Lakiernia Proszkowa" className="h-auto w-40" />
          </div>

          <h1 className="mb-1 text-center text-xl font-bold text-brand-ink">Logowanie</h1>
          <p className="mb-6 text-center text-sm text-brand-muted">System sterowania produkcją</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-brand-muted">
                Login
              </label>
              <input
                type="text"
                value={loginValue}
                onChange={(e) => setLoginValue(e.target.value)}
                required
                autoFocus
                autoComplete="username"
                className="w-full rounded-xl border border-brand-line bg-brand-surface px-4 py-2.5 text-sm font-medium text-brand-ink placeholder:text-brand-muted focus:border-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-900/20"
                placeholder="np. zawieszanie"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-brand-muted">
                Hasło
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="w-full rounded-xl border border-brand-line bg-brand-surface px-4 py-2.5 text-sm font-medium text-brand-ink placeholder:text-brand-muted focus:border-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-900/20"
                placeholder="••••"
              />
            </div>

            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-brand-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-brand-900/90 disabled:opacity-60"
            >
              {loading ? "Logowanie…" : "Zaloguj się"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
