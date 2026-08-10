import { apiGet, apiPost } from "@/api/client";
import type { JobStartResponse } from "@/types/api";
import type {
  DownloadExistingPayload,
  DownloadExistingResponse,
  DownloadInspectPayload,
  DownloadOptions,
  DownloadPayload,
} from "./types";

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

export function detectExistingDownload(payload: DownloadExistingPayload) {
  return apiPost<DownloadExistingResponse>("/api/download/detect-existing", payload);
}

export function checkExistingDownload(payload: DownloadExistingPayload) {
  return apiPost<DownloadExistingResponse>("/api/download/check-existing", { ...payload, verify_with_kind: true });
}
