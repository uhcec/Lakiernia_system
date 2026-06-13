import type { ProcessStatusValue, WorkOrderStatus } from "./workOrders";

export interface Client {
  id: number;
  company_name: string;
  contact_phone: string | null;
  nip: string | null;
  order_count: number;
  created_at: string;
  updated_at: string;
}

export interface ClientListResponse {
  items: Client[];
  total: number;
  limit: number;
  offset: number;
}

export interface ClientOrderHistoryItem {
  id: number;
  order_number: string;
  external_order_number: string | null;
  title: string;
  total_quantity: number;
  ral_code: string;
  received_date: string;
  planned_pickup_date: string | null;
  status: WorkOrderStatus;
  production_type: { value: string; label: string } | null;
  process_status: { value: ProcessStatusValue; label: string } | null;
}

export interface ClientDetail {
  id: number;
  company_name: string;
  contact_phone: string | null;
  nip: string | null;
  created_at: string;
  updated_at: string;
  orders: ClientOrderHistoryItem[];
}

export interface ClientCreateRequest {
  company_name: string;
  contact_phone?: string | null;
  nip?: string | null;
}

export interface ClientUpdateRequest {
  company_name?: string;
  contact_phone?: string | null;
  nip?: string | null;
}
