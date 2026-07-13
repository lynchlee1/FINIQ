import { useState, useCallback, useRef } from "react";

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
            const progress = event.progress || {};
            const unit = progress.unit_label || "항목";
            const records = Number(progress.records || 0).toLocaleString("ko-KR");
            appendStatus(`${unit} ${Number(progress.completed || 0).toLocaleString("ko-KR")}/${Number(progress.total || 0).toLocaleString("ko-KR")} 완료 · 누적 ${records}건`);
            if (onProgress) onProgress(progress);
          } else if (event.type === "result") {
            onResult(event.payload);
            return;
          } else if (event.type === "error") {
            throw new Error(event.error || "실행 중 오류가 발생했습니다.");
          }
        }
      }

      if (buffer.trim()) {
        const event = JSON.parse(buffer);
        if (event.type === "result") {
          onResult(event.payload);
          return;
        }
        if (event.type === "error") throw new Error(event.error || "실행 중 오류가 발생했습니다.");
      }
      throw new Error("결과를 받지 못했습니다.");
    } catch (err: any) {
      if (err.name === "AbortError") {
        appendStatus("작업을 중단했습니다.", true);
      } else {
        setStatus(err.message);
        setIsErrorStatus(true);
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
