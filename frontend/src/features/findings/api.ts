import { jsonRequest, request } from "../../lib/api";

export const categoryLabels = {
  email: "Email",
  phone_in: "Indian mobile",
  pan: "PAN-shaped value",
  aadhaar: "Aadhaar-shaped value",
  ifsc: "IFSC-shaped value",
  bank_account: "Bank account number",
};

export const reviewLabels = {
  needs_review: "Needs review",
  confirmed: "Confirmed",
  false_positive: "False positive",
  follow_up: "Follow-up",
};

export type ReviewStatus = keyof typeof reviewLabels;
export type Finding = {
  id: string;
  category: keyof typeof categoryLabels;
  source_id: string;
  source_name: string;
  scan_id: string;
  scan_submitted_at: string;
  relative_path: string;
  size_bytes: number | null;
  detector_version: number;
  confidence: number;
  location: number;
  masked_evidence: string;
  review_status: ReviewStatus;
  reviewed_at: string | null;
};
export type FindingDetail = Finding & {
  related_count: number;
  history: { status: ReviewStatus; reviewer: string; reviewed_at: string }[];
};
type FindingPage = { items: Finding[]; total: number };
export const pageSize = 25;

export const findings = {
  search: (filters: Record<string, string | number>) =>
    request<FindingPage>("findings/search", jsonRequest("POST", filters)),
  detail: (id: string) => request<FindingDetail>(`findings/${id}`),
  related: (id: string, offset: number) =>
    request<FindingPage>(
      `findings/${id}/related?limit=${pageSize}&offset=${offset}`,
    ),
  review: (id: string, status: ReviewStatus) =>
    request<Finding>(`findings/${id}/review`, jsonRequest("PATCH", { status })),
};
