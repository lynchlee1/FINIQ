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

export function checkExistingDownload(outputDirectory: string) {
  return apiPost<{
    has_existing: boolean;
    earliest_date?: string;
    latest_date?: string;
    ranges?: {
      start_date: string;
      end_date: string;
      folder_name: string;
      local_count: number | null;
      kind_count: number | null;
      status: "validated" | "stale" | "unverified";
      error_detail: string | null;
      metadata_missing?: boolean;
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
  }>("/api/download/check-existing", { output_directory: outputDirectory, verify_with_kind: false });
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


