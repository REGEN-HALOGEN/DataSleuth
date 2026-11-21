import { jsonRequest, request } from "../../lib/api";

export type ScanSource = {
  id: string;
  name: string;
  configured_path: string | null;
  upload_state: "pending" | "ready" | "deleting" | "deleted" | null;
  size_bytes: number | null;
  expires_at: string | null;
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
  deleteDocument: (id: string) =>
    request<ScanSource>(`documents/${id}`, { method: "DELETE" }),
  start: (source_id: string) =>
    request<Scan>("scans", jsonRequest("POST", { source_id, confirmed: true })),
  history: () => request<Scan[]>("scans"),
  cancel: (id: string) =>
    request<Scan>(`scans/${id}/cancel`, { method: "POST" }),
};

export const scanStatusLabels: Record<Scan["status"], string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  completed_with_errors: "Completed with errors",
  failed: "Failed",
  cancelled: "Cancelled",
};
