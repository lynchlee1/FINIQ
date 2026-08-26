export type JobStatus = "queued" | "running" | "completed" | "failed" | string;

export type JobStartResponse = {
  job_id: string;
};

export type JobSnapshot<T = unknown> = {
  job_id: string;
  kind: string;
  status: JobStatus;
  created_at?: number;
  updated_at?: number;
  server_time: number;
  elapsed_seconds: number;
  progress_idle_seconds: number;
  download_rate_window_seconds?: number;
  recent_download_count?: number;
  downloads_per_minute?: number;
  progress_log?: string[];
  result?: T;
  error?: string | null;
};
