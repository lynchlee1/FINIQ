import { useState, useCallback, useEffect, useRef } from "react";
import { ApiError, apiGet, apiPost } from "@/api/client";
import type { JobSnapshot } from "@/types/api";

interface UseJobPollingOptions {
  pollingEndpoint: string;
  cancelEndpoint?: string;
  onSuccess?: (data: any) => void;
  onError?: (error: Error) => void;
  onCancel?: () => void;
  pollInterval?: number;
  formatStatus?: (data: JobSnapshot<any>) => string[];
}

export function useJobPolling(options: UseJobPollingOptions) {
  const { cancelEndpoint } = options;
  const [status, setStatus] = useState<string>("작업을 실행할 준비가 되었습니다.");
  const [isErrorStatus, setIsErrorStatus] = useState<boolean>(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const mountedRef = useRef(false);
  const optionsRef = useRef<UseJobPollingOptions>(options);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, []);

  const getStorageKey = useCallback(() => {
    if (typeof window === "undefined") return null;

    const { pollingEndpoint } = optionsRef.current;
    return `finiq.jobPolling:${window.location.pathname}:${pollingEndpoint}`;
  }, []);

  const rememberJobId = useCallback((jobId: string) => {
    const storageKey = getStorageKey();
    if (!storageKey) return;
    try {
      window.sessionStorage.setItem(storageKey, jobId);
    } catch {
      // Ignore storage failures; polling still works during the current mount.
    }
  }, [getStorageKey]);

  const forgetJobId = useCallback(() => {
    const storageKey = getStorageKey();
    if (!storageKey) return;
    try {
      window.sessionStorage.removeItem(storageKey);
    } catch {
      // Ignore storage failures; the backend job state remains authoritative.
    }
  }, [getStorageKey]);

  const pollJob = useCallback(
    async (jobId: string) => {
      try {
        const { pollingEndpoint, onSuccess, onError, onCancel, pollInterval = 1000, formatStatus } = optionsRef.current;
        const url = pollingEndpoint.replace("{jobId}", encodeURIComponent(jobId));
        const data = await apiGet<JobSnapshot<any>>(url);

        if (!mountedRef.current) return;

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
          forgetJobId();
          if (onSuccess) onSuccess(data.result);
          return;
        } else if (data.status === "cancelled") {
          setActiveJobId(null);
          forgetJobId();
          if (onCancel) onCancel();
          return;
        } else if (data.status === "failed") {
          setActiveJobId(null);
          forgetJobId();
          if (onError) onError(new Error(data.error || "Job failed"));
          return;
        }

        timeoutRef.current = setTimeout(() => {
          timeoutRef.current = null;
          pollJob(jobId);
        }, pollInterval);
      } catch (err: any) {
        if (!mountedRef.current) return;
        setStatus(err.message);
        setIsErrorStatus(true);
        setActiveJobId(null);
        if (err instanceof ApiError && err.status === 404) {
          forgetJobId();
        }
        const { onError } = optionsRef.current;
        if (onError) onError(err);
      }
    },
    [forgetJobId]
  );

  useEffect(() => {
    const storageKey = getStorageKey();
    if (!storageKey) return;

    let storedJobId = "";
    try {
      storedJobId = window.sessionStorage.getItem(storageKey) || "";
    } catch {
      storedJobId = "";
    }

    if (!storedJobId) return;
    setActiveJobId(storedJobId);
    setIsErrorStatus(false);
    pollJob(storedJobId);
  }, [getStorageKey, pollJob]);

  const startPolling = useCallback(
    (jobId: string) => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      rememberJobId(jobId);
      setActiveJobId(jobId);
      setIsErrorStatus(false);
      setStatus("작업을 시작하는 중...");
      pollJob(jobId);
    },
    [pollJob, rememberJobId]
  );

  const cancelJob = useCallback(async () => {
    if (!activeJobId || !cancelEndpoint) return;
    try {
      setStatus("작업 중단을 요청했습니다...");
      await apiPost<any>(cancelEndpoint, { job_id: activeJobId });
    } catch (err: any) {
      setStatus(`작업 중단 요청 실패: ${err.message}`);
      setIsErrorStatus(true);
    }
  }, [activeJobId, cancelEndpoint]);

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
    forgetJobId();
  }, [forgetJobId]);

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
    cancelJob,
  };
}
