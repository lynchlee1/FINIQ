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
  return apiPost<any>("/api/download/inspect-folder", payload);
}
