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
  progress_log?: string[];
  result?: T;
  error?: string | null;
};
