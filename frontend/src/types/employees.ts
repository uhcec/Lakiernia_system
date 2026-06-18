export interface Employee {
  id: number;
  full_name: string;
  is_active: boolean;
}

export interface StationPresenceEntry {
  employee_id: number;
  full_name: string;
  checked_in_at: string;
}

export interface StationPresenceRoster {
  station_id: string;
  /** Employees currently checked in at this station (the attribution set for actions here). */
  present: StationPresenceEntry[];
  /** Active employees available to check in. */
  employees: Employee[];
}

export interface OperatorStatItem {
  employee_id: number;
  full_name: string;
  is_active: boolean;
  hours_present: number;
  orders_count: number;
  actions: number;
  pieces_credited: number;
  m2_credited: number;
}

export interface OperatorStats {
  date_from: string;
  date_to: string;
  operators: OperatorStatItem[];
}

export interface PresenceSession {
  employee_id: number | null;
  full_name: string;
  station_id: string;
  checked_in_at: string;
  checked_out_at: string | null;
  hours: number;
  is_open: boolean;
}

export interface PresenceHistory {
  date_from: string;
  date_to: string;
  sessions: PresenceSession[];
}
