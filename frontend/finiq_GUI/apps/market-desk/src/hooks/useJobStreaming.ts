import { useState, useCallback, useRef } from "react";

function formatElapsed(seconds: number) {
  const wholeSeconds = Math.floor(seconds);
  if (wholeSeconds < 60) return `${wholeSeconds}초`;
  const minutes = Math.floor(wholeSeconds / 60);
  const remainingSeconds = wholeSeconds % 60;
  return `${minutes}분 ${remainingSeconds}초`;
}

export function useJobStreaming() {
  const [status, setStatus] = useState<string>("");
  const [isErrorStatus, setIsErrorStatus] = useState<boolean>(false);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const abortRef = useRef<AbortController | null>(null);

  const appendStatus = useCallback((message: string, isError = false) => {
    setStatus((prev) => {
      const lines = prev ? prev.split("\n") : [];
      return [...lines, message].slice(-80).join("\n");
    });
    setIsErrorStatus(isError);
  }, []);

  const streamJob = useCallback(async (
    url: string,
    payload: any,
    onResult: (result: any) => void,
    onProgress?: (progress: any) => void
  ) => {
    const controller = new AbortController();
    abortRef.current = controller;
    setIsStreaming(true);
    setStatus("처리 중...");
    setIsErrorStatus(false);

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/x-ndjson",
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || data.error || `HTTP ${response.status}`);
      }

      if (!response.body) {
        throw new Error("결과를 받지 못했습니다.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.type === "progress") {
            const progress = event.progress;
            if (!progress || typeof progress !== "object") {
              throw new Error("progress event must contain an object");
            }
            const unit = progress.unit_label;
            const completed = progress.completed;
            const total = progress.total;
            const recordCount = progress.records;
            if (typeof unit !== "string" || !unit.trim()) {
              throw new Error("progress.unit_label is required");
            }
            if (![completed, total, recordCount].every((item) => typeof item === "number" && Number.isFinite(item))) {
              throw new Error("progress counts must be finite numbers");
            }
            const records = recordCount.toLocaleString("ko-KR");
            appendStatus(`${unit} ${completed.toLocaleString("ko-KR")}/${total.toLocaleString("ko-KR")} 완료 · 누적 ${records}건`);
            if (onProgress) onProgress(progress);
          } else if (event.type === "heartbeat") {
            const elapsedSeconds = event.elapsed_seconds;
            const progressIdleSeconds = event.progress_idle_seconds;
            if (![elapsedSeconds, progressIdleSeconds].every((item) => typeof item === "number" && Number.isFinite(item))) {
              throw new Error("heartbeat times must be finite numbers");
            }
            appendStatus(
              `작업 스레드 실행 중 · 총 경과 ${formatElapsed(elapsedSeconds)} · 새 진행 ${formatElapsed(progressIdleSeconds)}째 없음`
            );
          } else if (event.type === "result") {
            onResult(event.payload);
            return "completed" as const;
          } else if (event.type === "error") {
            throw new Error(event.error || "실행 중 오류가 발생했습니다.");
          }
        }
      }

      if (buffer.trim()) {
        const event = JSON.parse(buffer);
        if (event.type === "result") {
          onResult(event.payload);
          return "completed" as const;
        }
        if (event.type === "error") throw new Error(event.error || "실행 중 오류가 발생했습니다.");
      }
      throw new Error("결과를 받지 못했습니다.");
    } catch (err: any) {
      if (err.name === "AbortError") {
        appendStatus("작업을 중단했습니다.", true);
        return "aborted" as const;
      } else {
        setStatus(err.message);
        setIsErrorStatus(true);
        return "failed" as const;
      }
    } finally {
      abortRef.current = null;
      setIsStreaming(false);
    }
  }, [appendStatus]);

  const abortJob = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
  }, []);

  return {
    status,
    setStatus,
    isErrorStatus,
    setIsErrorStatus,
    isStreaming,
    streamJob,
    abortJob,
    appendStatus,
  };
}
