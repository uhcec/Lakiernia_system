import { Navigate, useLocation } from "react-router-dom";
import { isFullAccessUser, useAuth, type AuthUser } from "../context/AuthContext";
import { getStationPanelPath, type StationId } from "../api/stationContext";

const stationRouteMap: Record<string, string[]> = {
  SURFACE_PREPARATION: ["/przygotowanie"],
  HANGING: ["/zawieszanie"],
  MANUAL_PRODUCTION: ["/produkcja-reczna"],
  AUTOMATIC_PRODUCTION: ["/produkcja-automat"],
  PACKING: ["/pakowanie"],
  DECORAL_PRODUCTION: ["/produkcja-decoral"],
};

function readUserFromStorage(): AuthUser | null {
  try {
    const stored = localStorage.getItem("auth_user");
    return stored ? (JSON.parse(stored) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();

  // React state may not be committed yet right after login (race condition),
  // so fall back to localStorage as the authoritative source.
  const effectiveUser = user ?? readUserFromStorage();

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
