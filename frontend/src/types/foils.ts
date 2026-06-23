export interface Foil {
  id: number;
  name: string;
  code: string;
  supplier: string | null;
  notes: string | null;
  usage_count: number;
  created_at: string;
  updated_at: string;
}

export interface FoilSummary {
  id: number;
  name: string;
  code: string;
}

export interface FoilListResponse {
  items: Foil[];
  total: number;
  limit: number;
  offset: number;
}

export interface FoilCreateRequest {
  name: string;
  code: string;
  supplier?: string | null;
  notes?: string | null;
}

export interface FoilUpdateRequest {
  name?: string;
  code?: string;
  supplier?: string | null;
  notes?: string | null;
}
