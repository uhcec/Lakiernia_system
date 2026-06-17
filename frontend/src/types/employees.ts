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
