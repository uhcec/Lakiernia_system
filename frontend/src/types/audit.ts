export type AuditStationId =
  | "OFFICE"
  | "MANAGER"
  | "SURFACE_PREPARATION"
  | "HANGING"
  | "AUTOMATIC_PRODUCTION"
  | "MANUAL_PRODUCTION"
  | "PACKING"
  | "DECORAL_PRODUCTION"
  | "SYSTEM"
  | "UNKNOWN";

export type AuditEventDetails = Record<string, unknown> | unknown[] | string | number | boolean | null;

export interface AuditEvent {
  id: number;
  event_type: string;
  station_id: AuditStationId;
  work_order_id: number | null;
  target_type: string | null;
  target_id: number | null;
  request_id: string | null;
  summary: string;
  details: AuditEventDetails;
  created_at: string;
}
