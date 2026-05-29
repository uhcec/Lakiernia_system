export type StationId =
  | "OFFICE"
  | "MANAGER"
  | "SURFACE_PREPARATION"
  | "HANGING"
  | "AUTOMATIC_PRODUCTION"
  | "MANUAL_PRODUCTION"
  | "PACKING"
  | "DECORAL_PRODUCTION"
  | "UNKNOWN";

const routeStationMappings: Array<[RegExp, StationId]> = [
  [/^\/kierownik(?:\/|$)/, "MANAGER"],
  [/^\/przygotowanie(?:\/|$)/, "SURFACE_PREPARATION"],
  [/^\/zawieszanie(?:\/|$)/, "HANGING"],
  [/^\/produkcja-automat(?:\/|$)/, "AUTOMATIC_PRODUCTION"],
  [/^\/produkcja-reczna(?:\/|$)/, "MANUAL_PRODUCTION"],
  [/^\/produkcja-decoral(?:\/|$)/, "DECORAL_PRODUCTION"],
  [/^\/pakowanie(?:\/|$)/, "PACKING"],
  [/^\/zlecenia(?:\/|$)/, "OFFICE"],
];

export function getStationIdForPath(pathname: string): StationId {
  const normalizedPathname = pathname.startsWith("/") ? pathname : `/${pathname}`;
  const matchedMapping = routeStationMappings.find(([pattern]) => pattern.test(normalizedPathname));
  return matchedMapping?.[1] ?? "UNKNOWN";
}

export function getCurrentStationHeaders(): Record<string, string> {
  return {
    "X-Station-Id": getStationIdForPath(window.location.pathname),
  };
}