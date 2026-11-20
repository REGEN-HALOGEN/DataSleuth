import { jsonRequest, request } from "../../lib/api";

export type ScanSource = {
  id: string;
  name: string;
  configured_path: string;
  enabled: boolean;
};

export type Scan = {
  id: string;
  source_id: string;
  status:
    | "queued"
    | "running"
    | "completed"
    | "completed_with_errors"
    | "failed"
    | "cancelled";
  started_at: string;
  cancel_requested: boolean;
  files_discovered: number;
  files_processed: number;
  files_skipped: number;
  files_failed: number;
  findings_created: number;
  inventory_limited: boolean;
  error_summary: string | null;
};

export const scans = {
  sources: () => request<ScanSource[]>("sources"),
  createSource: (name: string, configured_path: string) =>
    request<ScanSource>(
      "sources",
      jsonRequest("POST", { name, configured_path }),
    ),
  updateSource: (id: string, update: { name?: string; enabled?: boolean }) =>
    request<ScanSource>(`sources/${id}`, jsonRequest("PATCH", update)),
  start: (source_id: string) =>
    request<Scan>("scans", jsonRequest("POST", { source_id, confirmed: true })),
  history: () => request<Scan[]>("scans"),
  cancel: (id: string) =>
    request<Scan>(`scans/${id}/cancel`, { method: "POST" }),
};
