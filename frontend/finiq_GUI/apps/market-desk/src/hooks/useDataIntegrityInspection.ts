"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type DataIntegrityInspectionOptions<TPayload, TResult> = {
  inspect: (payload: TPayload) => Promise<TResult>;
  onError?: (message: string) => void;
};

export function useDataIntegrityInspection<TPayload, TResult>({
  inspect,
  onError,
}: DataIntegrityInspectionOptions<TPayload, TResult>) {
  const inspectRef = useRef(inspect);
  const onErrorRef = useRef(onError);
  const requestRef = useRef({ id: 0, key: "" });
  const [result, setResult] = useState<TResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(false);

  useEffect(() => {
    inspectRef.current = inspect;
    onErrorRef.current = onError;
  }, [inspect, onError]);

  const clear = useCallback(() => {
    requestRef.current = { id: requestRef.current.id + 1, key: "" };
    setResult(null);
    setError(null);
    setIsChecking(false);
  }, []);

  const runInspection = useCallback(async (payload: TPayload, requestKey: string) => {
    const requestId = requestRef.current.id + 1;
    requestRef.current = { id: requestId, key: requestKey };
    setIsChecking(true);
    setError(null);

    try {
      const nextResult = await inspectRef.current(payload);
      if (requestRef.current.id !== requestId || requestRef.current.key !== requestKey) {
        return null;
      }
      setResult(nextResult);
      return nextResult;
    } catch (inspectionError) {
      if (requestRef.current.id !== requestId || requestRef.current.key !== requestKey) {
        return null;
      }
      const message = inspectionError instanceof Error
        ? inspectionError.message
        : String(inspectionError);
      setResult(null);
      setError(message);
      onErrorRef.current?.(message);
      return null;
    } finally {
      if (requestRef.current.id === requestId && requestRef.current.key === requestKey) {
        setIsChecking(false);
      }
    }
  }, []);

  return {
    result,
    error,
    isChecking,
    runInspection,
    clear,
  };
}
