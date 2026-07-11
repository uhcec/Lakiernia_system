import { Navigate, useLocation } from "react-router-dom";
import { isFullAccessUser, readStoredAuthUser, useAuth } from "../context/AuthContext";
import { getStationPanelPath, type StationId } from "../api/stationContext";

const stationRouteMap: Record<string, string[]> = {
  SURFACE_PREPARATION: ["/przygotowanie"],
  HANGING: ["/zawieszanie"],
  MANUAL_PRODUCTION: ["/produkcja-reczna"],
  AUTOMATIC_PRODUCTION: ["/produkcja-automat"],
  PACKING: ["/pakowanie"],
  DECORAL_PRODUCTION: ["/produkcja-decoral"],
};

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();

  // React state may not be committed yet right after login (race condition),
  // so fall back to localStorage as the authoritative source (same guarded read as AuthContext —
  // CHANGES #16a keeps the parse guard in one place).
  const effectiveUser = user ?? readStoredAuthUser();

  if (!effectiveUser) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (!isFullAccessUser(effectiveUser)) {
    const allowed = stationRouteMap[effectiveUser.station_id] ?? [];
    const isAllowed = allowed.some((route) => location.pathname.startsWith(route));
    if (!isAllowed) {
      return <Navigate to={getStationPanelPath(effectiveUser.station_id as StationId)} replace />;
    }
  }

  return <>{children}</>;
}
