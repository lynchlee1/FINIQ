import { apiGet, apiPost } from "@/api/client";
import type { JobStartResponse } from "@/types/api";
import type { DownloadInspectPayload, DownloadOptions, DownloadPayload } from "./types";

export function fetchDownloadOptions() {
  return apiGet<DownloadOptions>("/api/download/options");
}

export function previewDownload(payload: DownloadPayload) {
  return apiPost<any>("/api/download/preview", payload);
}

export function startDownload(payload: DownloadPayload) {
  return apiPost<JobStartResponse>("/api/download/run/start", payload);
}

export function cancelDownload(jobId: string) {
  return apiPost<any>("/api/download/run/cancel", { job_id: jobId });
}

export function inspectDownloadFolder(payload: DownloadInspectPayload) {
  return apiPost<JobStartResponse>("/api/download/inspect-folder/start", payload);
}

type ExistingDownloadResponse = {
  has_existing: boolean;
  earliest_date?: string | null;
  latest_date?: string | null;
  ranges?: {
    start_date: string | null;
    end_date: string | null;
    folder_name: string;
    local_count: number | null;
    kind_count: number | null;
    status: "validated" | "stale" | "unverified";
    error_detail: string | null;
    metadata_missing?: boolean;
    metadata_obsolete?: boolean;
    metadata_status?: "ok" | "missing" | "obsolete" | "mismatch";
    filters_match?: boolean;
    folder_path: string;
  }[];
  saved_filters?: {
    company_name: string;
    submitter_name: string;
    market_label: string;
    securities_label: string;
    disclosure_type_groups: Record<string, string[]>;
    last_report_only: boolean;
  } | null;
};

type ExistingDownloadPayload = Pick<
  DownloadPayload,
  | "output_directory"
  | "start_date"
  | "end_date"
  | "company_name"
  | "submitter_name"
  | "market_label"
  | "securities_label"
  | "page_size"
  | "last_report_only"
  | "disclosure_type_groups"
>;

export function detectExistingDownload(payload: ExistingDownloadPayload) {
  return apiPost<ExistingDownloadResponse>("/api/download/detect-existing", payload);
}

export function checkExistingDownload(payload: ExistingDownloadPayload) {
  return apiPost<ExistingDownloadResponse>("/api/download/check-existing", { ...payload, verify_with_kind: false });
}

export function createMetadata(payload: {
  output_directory: string;
  start_date: string;
  end_date: string;
  company_name: string;
  submitter_name: string;
  market_label: string;
  securities_label: string;
  disclosure_type_groups: Record<string, string[]>;
  last_report_only: boolean;
  page_size: number;
  wait_seconds: number;
  timeout: number;
  force?: boolean;
}) {
  return apiPost<{
    success: boolean;
    local_count: number;
    kind_count: number | null;
    message: string;
  }>("/api/download/create-metadata", payload);
}
