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
  [/^\/audyt(?:\/|$)/, "MANAGER"],
  [/^\/statystyki(?:\/|$)/, "MANAGER"],
  [/^\/kierownik(?:\/|$)/, "MANAGER"],
  [/^\/przygotowanie(?:\/|$)/, "SURFACE_PREPARATION"],
  [/^\/zawieszanie(?:\/|$)/, "HANGING"],
  [/^\/produkcja-automat(?:\/|$)/, "AUTOMATIC_PRODUCTION"],
  [/^\/produkcja-reczna(?:\/|$)/, "MANUAL_PRODUCTION"],
  [/^\/produkcja-decoral(?:\/|$)/, "DECORAL_PRODUCTION"],
  [/^\/pakowanie(?:\/|$)/, "PACKING"],
  [/^\/farby(?:\/|$)/, "OFFICE"],
  [/^\/klienci(?:\/|$)/, "OFFICE"],
  [/^\/zlecenia(?:\/|$)/, "OFFICE"],
];

const stationIds = new Set<StationId>([
  "OFFICE",
  "MANAGER",
  "SURFACE_PREPARATION",
  "HANGING",
  "AUTOMATIC_PRODUCTION",
  "MANUAL_PRODUCTION",
  "PACKING",
  "DECORAL_PRODUCTION",
  "UNKNOWN",
]);

const detailStationContextParam = "station_context";

export function isStationId(value: string | null): value is StationId {
  return value !== null && stationIds.has(value as StationId);
}

export function getStationIdForPath(pathname: string): StationId {
  const normalizedPathname = pathname.startsWith("/") ? pathname : `/${pathname}`;
  const matchedMapping = routeStationMappings.find(([pattern]) => pattern.test(normalizedPathname));
  return matchedMapping?.[1] ?? "UNKNOWN";
}

export function getStationIdForLocation(pathname: string, search = ""): StationId {
  const explicitStationId = new URLSearchParams(search).get(detailStationContextParam);
  if (isStationId(explicitStationId)) {
    return explicitStationId;
  }
  return getStationIdForPath(pathname);
}

export function buildWorkOrderDetailHref(workOrderId: number, stationId?: StationId): string {
  const pathname = `/zlecenia/${workOrderId}`;
  if (!stationId || stationId === "OFFICE" || stationId === "UNKNOWN") {
    return pathname;
  }
  return `${pathname}?${detailStationContextParam}=${encodeURIComponent(stationId)}`;
}

export function getStationPanelPath(stationId: StationId): string {
  switch (stationId) {
    case "MANAGER":
      return "/kierownik";
    case "SURFACE_PREPARATION":
      return "/przygotowanie";
    case "HANGING":
      return "/zawieszanie";
    case "AUTOMATIC_PRODUCTION":
      return "/produkcja-automat";
    case "MANUAL_PRODUCTION":
      return "/produkcja-reczna";
    case "DECORAL_PRODUCTION":
      return "/produkcja-decoral";
    case "PACKING":
      return "/pakowanie";
    case "OFFICE":
    case "UNKNOWN":
      return "/zlecenia";
  }
}

export function getCurrentStationHeaders(): Record<string, string> {
  return {
    "X-Station-Id": getStationIdForLocation(window.location.pathname, window.location.search),
  };
}
