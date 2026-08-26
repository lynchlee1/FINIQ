import { useState, useCallback, useEffect, useRef } from "react";
import { ApiError, apiGet, apiPost } from "@/api/client";
import type { JobSnapshot } from "@/types/api";

interface UseJobPollingOptions {
  pollingEndpoint: string;
  cancelEndpoint?: string;
  onSuccess?: (data: any, jobId: string) => void | Promise<void>;
  onError?: (error: Error, jobId: string) => void;
  onCancel?: (jobId: string) => void;
  pollInterval?: number;
  formatStatus?: (data: JobSnapshot<any>) => string[];
}

const LONG_PROGRESS_SILENCE_SECONDS = 10;

function formatElapsed(seconds: number) {
  const wholeSeconds = Math.floor(seconds);
  if (wholeSeconds < 60) return `${wholeSeconds}초`;
  const minutes = Math.floor(wholeSeconds / 60);
  const remainingSeconds = wholeSeconds % 60;
  return `${minutes}분 ${remainingSeconds}초`;
}

function jobTimingLines(data: JobSnapshot<any>) {
  if (data.status !== "queued" && data.status !== "running") return [];
  const elapsed = formatElapsed(data.elapsed_seconds);
  const idle = formatElapsed(data.progress_idle_seconds);
  const progressState = data.progress_idle_seconds >= LONG_PROGRESS_SILENCE_SECONDS
    ? `새 로그 ${idle}째 없음`
    : `마지막 로그 ${idle} 전`;
  const lines = [
    `작업 경과: ${elapsed}`,
    `진행 확인: 상태 조회 정상 · ${progressState}`,
  ];
  if (
    data.downloads_per_minute !== undefined
    && data.recent_download_count !== undefined
    && data.download_rate_window_seconds !== undefined
  ) {
    lines.push(
      `다운로드 속도: ${data.downloads_per_minute} download/min · `
      + `최근 ${data.download_rate_window_seconds}초 ${data.recent_download_count}건`,
    );
  }
  return lines;
}

export function useJobPolling(options: UseJobPollingOptions) {
  const { cancelEndpoint } = options;
  const [status, setStatus] = useState<string>("작업을 실행할 준비가 되었습니다.");
  const [isErrorStatus, setIsErrorStatus] = useState<boolean>(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [isPollingRestored, setIsPollingRestored] = useState(false);
  const activeJobIdRef = useRef<string | null>(null);
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

  const forgetJobId = useCallback((expectedJobId?: string) => {
    const storageKey = getStorageKey();
    if (!storageKey) return;
    try {
      if (expectedJobId && window.sessionStorage.getItem(storageKey) !== expectedJobId) {
        return;
      }
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

        if (!mountedRef.current || activeJobIdRef.current !== jobId) return;

        if (formatStatus) {
          const lines = formatStatus(data);
          lines.splice(1, 0, ...jobTimingLines(data));
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
          lines.push(...jobTimingLines(data));
          if (data.error) lines.push(`오류: ${data.error}`);
          if (data.progress_log?.length) {
            lines.push("", "최근 로그:", ...data.progress_log.slice(-10));
          }

          setStatus(lines.join("\n"));
        }

        setIsErrorStatus(data.status === "failed");

        if (data.status === "completed") {
          try {
            if (onSuccess) await onSuccess(data.result, jobId);
          } catch (callbackError) {
            const error = callbackError instanceof Error
              ? callbackError
              : new Error(String(callbackError));
            setStatus(error.message);
            setIsErrorStatus(true);
            if (onError) onError(error, jobId);
          }
          if (activeJobIdRef.current === jobId) {
            activeJobIdRef.current = null;
            setActiveJobId(null);
          }
          forgetJobId(jobId);
          return;
        } else if (data.status === "cancelled") {
          activeJobIdRef.current = null;
          setActiveJobId(null);
          forgetJobId(jobId);
          if (onCancel) onCancel(jobId);
          return;
        } else if (data.status === "failed") {
          activeJobIdRef.current = null;
          setActiveJobId(null);
          forgetJobId(jobId);
          if (onError) onError(new Error(data.error || "Job failed"), jobId);
          return;
        }

        timeoutRef.current = setTimeout(() => {
          timeoutRef.current = null;
          pollJob(jobId);
        }, pollInterval);
      } catch (err: any) {
        if (!mountedRef.current || activeJobIdRef.current !== jobId) return;
        setStatus(err.message);
        setIsErrorStatus(true);
        if (err instanceof ApiError && err.status === 404) {
          if (activeJobIdRef.current === jobId) {
            activeJobIdRef.current = null;
            setActiveJobId(null);
          }
          forgetJobId(jobId);
          const { onError } = optionsRef.current;
          if (onError) onError(err, jobId);
          return;
        }
        const { pollInterval = 1000 } = optionsRef.current;
        timeoutRef.current = setTimeout(() => {
          timeoutRef.current = null;
          if (activeJobIdRef.current === jobId) {
            pollJob(jobId);
          }
        }, pollInterval);
      }
    },
    [forgetJobId]
  );

  useEffect(() => {
    const storageKey = getStorageKey();
    if (!storageKey) {
      setIsPollingRestored(true);
      return;
    }

    let storedJobId = "";
    try {
      storedJobId = window.sessionStorage.getItem(storageKey) || "";
    } catch {
      storedJobId = "";
    }

    if (storedJobId) {
      activeJobIdRef.current = storedJobId;
      setActiveJobId(storedJobId);
      setIsErrorStatus(false);
      pollJob(storedJobId);
    }
    setIsPollingRestored(true);
  }, [getStorageKey, pollJob]);

  const startPolling = useCallback(
    (jobId: string) => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      rememberJobId(jobId);
      activeJobIdRef.current = jobId;
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
    activeJobIdRef.current = null;
    setActiveJobId(null);
    forgetJobId();
  }, [forgetJobId]);

  return {
    status,
    isErrorStatus,
    activeJobId,
    isPollingRestored,
    startPolling,
    appendStatus,
    resetStatus,
    setStatus,
    setIsErrorStatus,
    setActiveJobId,
    cancelJob,
  };
}
