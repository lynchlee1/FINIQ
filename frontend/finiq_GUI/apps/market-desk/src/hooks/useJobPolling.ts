import { useState, useCallback } from "react";
import { apiGet } from "@/api/client";
import type { JobSnapshot } from "@/types/api";

interface UseJobPollingOptions {
  pollingEndpoint: string;
  onSuccess?: (data: any) => void;
  onError?: (error: Error) => void;
  onCancel?: () => void;
  pollInterval?: number;
  formatStatus?: (data: JobSnapshot<any>) => string[];
}

export function useJobPolling(options: UseJobPollingOptions) {
  const { pollingEndpoint, onSuccess, onError, onCancel, pollInterval = 1000, formatStatus } = options;
  const [status, setStatus] = useState<string>("작업을 실행할 준비가 되었습니다.");
  const [isErrorStatus, setIsErrorStatus] = useState<boolean>(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const pollJob = useCallback(
    async (jobId: string) => {
      try {
        const url = pollingEndpoint.replace("{jobId}", encodeURIComponent(jobId));
        const data = await apiGet<JobSnapshot<any>>(url);

        if (formatStatus) {
          const lines = formatStatus(data);
          setStatus(lines.join("\n"));
        } else {
          const statusLabel = (s: string) => {
            switch (s) {
              case "queued": return "대기 중";
              case "running": return "실행 중";
              case "completed": return "완료";
              case "failed": return "실패";
              case "cancelled": return "중단됨";
              default: return s || "-";
            }
          };

          const lines = [`작업 상태: ${statusLabel(data.status)}`];
          if (data.error) lines.push(`오류: ${data.error}`);
          if (data.progress_log?.length) {
            lines.push("", "최근 로그:", ...data.progress_log.slice(-10));
          }

          setStatus(lines.join("\n"));
        }
        
        setIsErrorStatus(data.status === "failed");

        if (data.status === "completed") {
          setActiveJobId(null);
          if (onSuccess) onSuccess(data.result || data);
          return;
        } else if (data.status === "cancelled") {
          setActiveJobId(null);
          if (onCancel) onCancel();
          return;
        } else if (data.status === "failed") {
          setActiveJobId(null);
          if (onError) onError(new Error(data.error || "Job failed"));
          return;
        }

        setTimeout(() => pollJob(jobId), pollInterval);
      } catch (err: any) {
        setStatus(err.message);
        setIsErrorStatus(true);
        setActiveJobId(null);
        if (onError) onError(err);
      }
    },
    [pollingEndpoint, onSuccess, onError, onCancel, pollInterval, formatStatus]
  );

  const startPolling = useCallback(
    (jobId: string) => {
      setActiveJobId(jobId);
      setIsErrorStatus(false);
      setStatus("작업을 시작하는 중...");
      pollJob(jobId);
    },
    [pollJob]
  );

  const appendStatus = useCallback((message: string, isError = false) => {
    setStatus((prev) => {
      const lines = prev ? prev.split("\n") : [];
      return [...lines, message].slice(-80).join("\n");
    });
    setIsErrorStatus(isError);
  }, []);

  const resetStatus = useCallback((initialMessage: string = "") => {
    setStatus(initialMessage);
    setIsErrorStatus(false);
    setActiveJobId(null);
  }, []);

  return {
    status,
    isErrorStatus,
    activeJobId,
    startPolling,
    appendStatus,
    resetStatus,
    setStatus,
    setIsErrorStatus,
    setActiveJobId,
  };
}
