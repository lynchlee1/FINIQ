"use client"

import { useState, useEffect, useCallback, useRef } from "react";
import { FolderOpen, FileJson, Play, Square, Loader2, Trash2 } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Label, Checkbox } from "@finiq/ui";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import {
  HtmlWorkflowForm,
  HtmlWorkflowCard,
  HtmlWorkflowPage,
  htmlControlClassName,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import { ActionDock } from "@/components/ui/ActionDock";
import { UI_TEXT } from "@/config/uiText";
import { formatInteger } from "@/lib/format";

type DownloadVariant = "external" | "content";
type ContentSourceInputMode = "folder" | "file";
type ExternalTaskMode = "download" | "compress";
type ContentTaskMode = "download" | "merge";
type SplitByYearButtonProps = {
  checked: boolean;
  onChange: () => void;
};

const DOWNLOAD_VARIANTS = {
  external: {
    settingsTitle: "공시원문 외부 저장 설정",
    description: "다운로드된 공시 결과 JSON을 바탕으로 KIND 공시 뷰어 HTML을 대량 저장합니다.",
    sourceLabel: "입력 데이터 경로 (필터 결과 JSON)",
    sourceHelp: "공시 필터링 결과 파일(JSON)을 선택하세요.",
    sourcePickMode: "file",
    sourceSettingKey: "html_download_source_path",
    sourceRequiredMessage: "입력 데이터 경로를 선택하세요.",
    sourcePayloadKey: "source_json_path",
    defaultDirectoryKey: "html_output_directory",
    defaultDirectorySuffix: "viewer_html",
    startEndpoint: "/api/disclosures/html/download/start",
    cancelEndpoint: "/api/disclosures/html/download/cancel",
    inspectEndpoint: "/api/disclosures/html/download/inspect-folder",
    checkExistingEndpoint: "/api/disclosures/html/download/check-existing",
    stopMessage: "공시원문 외부 저장 중지를 요청했습니다. 진행 중인 요청이 끝나면 멈춥니다.",
  },
  content: {
    settingsTitle: "공시원문 내부 저장 설정",
    description: "공시원문 외부 데이터 경로를 바탕으로 KIND 공시 본문 HTML을 대량 저장합니다.",
    sourceLabel: "공시원문 외부 데이터 경로",
    sourceHelp: "공시원문 외부 저장으로 만든 뷰어 HTML 폴더를 선택하세요.",
    sourcePickMode: "folder",
    sourceSettingKey: "html_output_directory",
    sourceRequiredMessage: "공시원문 외부 데이터 경로를 선택하세요.",
    sourcePayloadKey: "source_directory",
    defaultDirectoryKey: "html_content_output_directory",
    defaultDirectorySuffix: "viewer_html_contents",
    startEndpoint: "/api/disclosures/html/content-download/start",
    cancelEndpoint: "/api/disclosures/html/content-download/cancel",
    inspectEndpoint: "/api/disclosures/html/content-download/inspect-folder",
    checkExistingEndpoint: "/api/disclosures/html/content-download/check-existing",
    stopMessage: "공시원문 내부 저장 중지를 요청했습니다. 진행 중인 요청이 끝나면 멈춥니다.",
  },
} as const;

async function readJsonResponse(response: Response, fallbackMessage: string) {
  const text = await response.text();
  if (!text.trim()) {
    if (!response.ok) throw new Error(fallbackMessage);
    return {};
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(response.ok ? fallbackMessage : text);
  }
}

function SplitByYearButton({ checked, onChange }: SplitByYearButtonProps) {
  return (
    <Button
      variant={checked ? "default" : "outline"}
      onClick={onChange}
      className="h-10 w-[116px] shrink-0"
    >
      분할저장 {checked ? "On" : "Off"}
    </Button>
  );
}

export function HtmlDownloadPageView({ variant = "external" }: { variant?: DownloadVariant }) {
  const variantConfig = DOWNLOAD_VARIANTS[variant];

  const {
    fetchSettings,
    saveSetting,
  } = useSettingsStore();

  const [loading, setLoading] = useState(true);
  const [, setResult] = useState<any>(null);

  const formatStatus = useCallback((data: any) => {
    const statusLbl = (s: string) => {
      if (s === "queued") return "대기 중";
      if (s === "running") return "실행 중";
      if (s === "completed") return "완료";
      if (s === "failed") return "실패";
      return s || "-";
    };

    const res = data.result || {};
    const lines = [`작업 상태: ${statusLbl(data.status)}`];
    if (data.error) lines.push(`오류: ${data.error}`);
    if (res.requested_count !== undefined) {
      lines.push(`요청 접수번호: ${formatInteger(res.requested_count)}`);
      lines.push(`분할저장: ${res.split_by_year ? "On" : "Off"}`);
      lines.push(`저장 파일: ${formatInteger(res.saved_count)}`);
      lines.push(`데이터 경로: ${res.output_directory || ""}`);
    }
    if (res.summary?.merged_files !== undefined) {
      lines.push(`병합 HTML: ${formatInteger(res.summary.merged_files)}`);
      lines.push(`저장 JSON: ${formatInteger(res.summary.written_files)}`);
      lines.push(`분할저장: ${res.split_by_year ? "On" : "Off"}`);
      if (Array.isArray(res.written_files)) {
        lines.push("결과 파일", ...res.written_files);
      }
    }
    if (res.summary?.compressed_files !== undefined) {
      lines.push(`외부 HTML 압축: ${formatInteger(res.summary.compressed_files)}`);
      lines.push(`저장 JSON: ${formatInteger(res.summary.written_files)}`);
      lines.push(`분할저장: ${res.split_by_year ? "On" : "Off"}`);
      if (res.verification) {
        lines.push(`재검사: ${res.verification.passed ? "통과" : "누락/불일치 있음"}`);
        lines.push(`재검사 기록: ${formatInteger(res.verification.verified_records)}/${formatInteger(res.verification.expected_records)}`);
        lines.push(`누락 기록: ${formatInteger(res.verification.missing_records)}`);
      }
      if (Array.isArray(res.written_files)) {
        lines.push("결과 파일", ...res.written_files);
      }
    }
    if (Array.isArray(data.progress_log) && data.progress_log.length) {
      lines.push("", "최근 로그", ...data.progress_log);
    }
    return lines;
  }, []);

  const [activeCancelToken, setActiveCancelToken] = useState<string | null>(null);
  const [inspectRunning, setInspectRunning] = useState(false);
  const [deleteConfirmed, setDeleteConfirmed] = useState(false);
  const [deleteConfirmationText, setDeleteConfirmationText] = useState("");
  const [lastInspectionCandidateCount, setLastInspectionCandidateCount] = useState(0);
  const [lastInspectionResult, setLastInspectionResult] = useState<any>(null);
  const [existingData, setExistingData] = useState<any>(null);
  const [existingCheckError, setExistingCheckError] = useState("");
  const [checkingExisting, setCheckingExisting] = useState(false);
  const [existingCheckRefreshKey, setExistingCheckRefreshKey] = useState(0);
  const checkExistingRequestRef = useRef({ id: 0, key: "" });
  const checkExistingAbortControllerRef = useRef<AbortController | null>(null);
  const inspectAbortControllerRef = useRef<AbortController | null>(null);

  // Form State
  const [outputDirectory, setOutputDirectory] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const [externalTaskMode, setExternalTaskMode] = useState<ExternalTaskMode>("download");
  const [contentTaskMode, setContentTaskMode] = useState<ContentTaskMode>("download");
  const [contentSourceInputMode, setContentSourceInputMode] = useState<ContentSourceInputMode>("folder");
  const [contentSourceFilePath, setContentSourceFilePath] = useState("");
  const [compressInputDirectory, setCompressInputDirectory] = useState("");
  const [compressOutputDirectory, setCompressOutputDirectory] = useState("");
  const [compressWorkers, setCompressWorkers] = useState("");
  const [timeout, setTimeoutVal] = useState("20");
  const [maxRequestsPerMinute, setMaxRequestsPerMinute] = useState("90");
  const [waitSeconds, setWaitSeconds] = useState("0");
  const [limit, setLimit] = useState("");
  const [skipExisting, setSkipExisting] = useState(true);
  const [downloadSplitByYear, setDownloadSplitByYear] = useState(false);
  const [contentSourceSplitByYear, setContentSourceSplitByYear] = useState(false);
  const [compressSplitByYear, setCompressSplitByYear] = useState(false);
  const [mergeSplitByYear, setMergeSplitByYear] = useState(false);
  const [progressInterval, setProgressInterval] = useState("10");
  const [mergeOutputPath, setMergeOutputPath] = useState("");

  const existingOutputSplitByYear =
    existingData && typeof existingData.detected_output_split_by_year === "boolean"
      ? existingData.detected_output_split_by_year
      : null;
  const existingSplitMismatch = existingOutputSplitByYear !== null && existingOutputSplitByYear !== downloadSplitByYear;
  const existingAllSaved = !!existingData && (existingData.requested_count || 0) > 0 && (existingData.missing_target_html_count || 0) === 0;

  const {
    status,
    isErrorStatus,
    activeJobId,
    startPolling,
    setStatus,
    setIsErrorStatus,
  } = useJobPolling({
    pollingEndpoint: "/api/disclosures/html/jobs/{jobId}",
    formatStatus,
    onSuccess: setResult,
  });

  const isJobActive = !!activeJobId;

  const startJob = useCallback(async (endpoint: string, payload: any) => {
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("Job start failed");
      const data = await response.json();
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
      if (payload.cancel_token) {
         setActiveCancelToken(null);
      }
    }
  }, [setStatus, setIsErrorStatus, startPolling, setActiveCancelToken]);

  useEffect(() => {
    fetchSettings().then((config) => {
      const nextOutputDirectory = config[variantConfig.defaultDirectoryKey] || (config.output_root ? `${config.output_root}/${variantConfig.defaultDirectorySuffix}` : "");
      setOutputDirectory(nextOutputDirectory);
      setCompressInputDirectory(config.html_external_compress_input_directory || nextOutputDirectory);
      setCompressOutputDirectory(config.html_external_compress_output_directory || nextOutputDirectory);

      const transferredPayload = variant === "external" ? sessionStorage.getItem("finiq.kind.filteredDisclosures") : null;
      if (transferredPayload) {
        const transferReference = JSON.parse(transferredPayload);
        setSourcePath(transferReference.source_json_path || "");
        sessionStorage.removeItem("finiq.kind.filteredDisclosures");
        setStatus("공시 필터에서 생성한 결과 파일을 불러왔습니다.");
      } else if (variant === "content") {
        setSourcePath(config.html_output_directory || (config.output_root ? `${config.output_root}/viewer_html` : ""));
        setContentSourceFilePath(config.html_content_compressed_json_path || "");
        setMergeOutputPath(config.html_merge_output_path || (nextOutputDirectory ? `${nextOutputDirectory}/merged-content-html.json` : ""));
      } else if (config.html_download_source_path) {
        setSourcePath(config.html_download_source_path);
      }
    }).catch(err => {
      setStatus(err.message);
      setIsErrorStatus(true);
    }).finally(() => {
      setLoading(false);
    });
  }, [fetchSettings, variant, variantConfig.defaultDirectoryKey, variantConfig.defaultDirectorySuffix, setStatus, setIsErrorStatus]);

  useEffect(() => {
    if (!isJobActive) {
      setActiveCancelToken(null);
    }
  }, [isJobActive]);

  const sourcePayload = useCallback(() => {
    if (variant === "content" && contentSourceInputMode === "file") {
      return { source_compressed_json_path: contentSourceFilePath };
    }
    return { [variantConfig.sourcePayloadKey]: sourcePath };
  }, [contentSourceFilePath, contentSourceInputMode, sourcePath, variant, variantConfig.sourcePayloadKey]);

  const currentSourcePath = variant === "content" && contentSourceInputMode === "file" ? contentSourceFilePath : sourcePath;
  const currentSourceRequiredMessage = variant === "content" && contentSourceInputMode === "file"
    ? "외부 HTML 압축 JSON 파일을 선택하세요."
    : variantConfig.sourceRequiredMessage;

  const buildRunPayload = useCallback((cancelToken: string) => ({
      output_directory: outputDirectory,
      ...sourcePayload(),
      timeout: Number(timeout),
      max_requests_per_minute: Number(maxRequestsPerMinute),
      wait_seconds: Number(waitSeconds),
      limit: limit ? Number(limit) : null,
      skip_existing: skipExisting,
      split_by_year: downloadSplitByYear,
      source_split_by_year: variant === "content" ? (contentSourceInputMode === "folder" && contentSourceSplitByYear) : downloadSplitByYear,
      output_split_by_year: downloadSplitByYear,
      progress_interval: Number(progressInterval),
      cancel_token: cancelToken,
  }), [
    outputDirectory,
    sourcePayload,
    timeout,
    maxRequestsPerMinute,
    waitSeconds,
    limit,
    skipExisting,
    downloadSplitByYear,
    contentSourceSplitByYear,
    contentSourceInputMode,
    progressInterval,
    variant,
  ]);

  const handleRun = async () => {
    if (!currentSourcePath) {
      setStatus(currentSourceRequiredMessage);
      setIsErrorStatus(true);
      return;
    }
    if (existingSplitMismatch) {
      setStatus("분할저장 설정이 기존 폴더 구조와 다릅니다. 기존 메타데이터 기준으로 설정을 맞춘 뒤 실행하세요.");
      setIsErrorStatus(true);
      return;
    }
    const cancelToken = window.crypto.randomUUID();
    setActiveCancelToken(cancelToken);

    const payload = buildRunPayload(cancelToken);

    startJob(variantConfig.startEndpoint, payload);
  };

  const buildCleanupPayload = useCallback((dryRun: boolean) => ({
    output_directory: outputDirectory,
    ...sourcePayload(),
    limit: limit ? Number(limit) : null,
    split_by_year: downloadSplitByYear,
    source_split_by_year: variant === "content" ? (contentSourceInputMode === "folder" && contentSourceSplitByYear) : downloadSplitByYear,
    output_split_by_year: downloadSplitByYear,
    dry_run: dryRun,
    delete_confirmed: deleteConfirmed,
    delete_confirmation_text: deleteConfirmationText,
  }), [
    outputDirectory,
    sourcePayload,
    limit,
    downloadSplitByYear,
    contentSourceSplitByYear,
    contentSourceInputMode,
    deleteConfirmed,
    deleteConfirmationText,
    variant,
  ]);

  const checkExisting = useCallback(async () => {
    if (!currentSourcePath || !outputDirectory) {
      checkExistingRequestRef.current = { id: checkExistingRequestRef.current.id + 1, key: "" };
      setExistingData(null);
      setExistingCheckError("");
      setCheckingExisting(false);
      return;
    }
    const payload = buildCleanupPayload(true);
    const requestId = checkExistingRequestRef.current.id + 1;
    const requestKey = JSON.stringify({
      endpoint: variantConfig.checkExistingEndpoint,
      payload,
    });
    checkExistingRequestRef.current = { id: requestId, key: requestKey };
    setCheckingExisting(true);

    const controller = new AbortController();
    checkExistingAbortControllerRef.current = controller;

    try {
      const response = await fetch(variantConfig.checkExistingEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const data = await readJsonResponse(response, "Existing HTML check failed");
      if (!response.ok) throw new Error(data.detail || "Existing HTML check failed");
      if (
        checkExistingRequestRef.current.id !== requestId ||
        checkExistingRequestRef.current.key !== requestKey
      ) {
        return;
      }
      setExistingCheckError("");
      setExistingData(
        data.has_existing ||
        typeof data.detected_output_split_by_year === "boolean" ||
        typeof data.detected_source_split_by_year === "boolean"
          ? data
          : null
      );
    } catch (err: any) {
      if (err.name === 'AbortError') {
        return;
      }
      if (
        checkExistingRequestRef.current.id === requestId &&
        checkExistingRequestRef.current.key === requestKey
      ) {
        setExistingCheckError(err.message || "기존 원문 데이터 경로 재확인에 실패했습니다.");
      }
    } finally {
      if (
        checkExistingRequestRef.current.id === requestId &&
        checkExistingRequestRef.current.key === requestKey
      ) {
        if (!controller.signal.aborted) {
          setCheckingExisting(false);
        }
      }
    }
  }, [currentSourcePath, outputDirectory, buildCleanupPayload, variantConfig.checkExistingEndpoint]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      checkExisting();
    }, 350);
    return () => window.clearTimeout(timer);
  }, [checkExisting, existingCheckRefreshKey]);

  useEffect(() => {
    return () => {
      if (checkExistingAbortControllerRef.current) {
        checkExistingAbortControllerRef.current.abort();
      }
      if (inspectAbortControllerRef.current) {
        inspectAbortControllerRef.current.abort();
      }
    };
  }, []);

  const handleInspectFolder = async () => {
    if (!currentSourcePath) {
      setStatus(currentSourceRequiredMessage);
      setIsErrorStatus(true);
      return;
    }
    if (!outputDirectory) {
      setStatus("데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (inspectAbortControllerRef.current) {
      inspectAbortControllerRef.current.abort();
      inspectAbortControllerRef.current = null;
    }
    const controller = new AbortController();
    inspectAbortControllerRef.current = controller;

    try {
      setInspectRunning(true);
      setIsErrorStatus(false);
      setStatus("폴더를 검사하는 중입니다...");
      const payload = buildCleanupPayload(true);
      const response = await fetch(variantConfig.inspectEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const data = await readJsonResponse(response, "Folder inspection failed");
      if (!response.ok) throw new Error(data.detail || "Folder inspection failed");

      const deleteCandidates = Array.isArray(data.deletion_candidates) ? data.deletion_candidates : [];
      setLastInspectionCandidateCount(data.deletion_candidate_count || 0);
      setLastInspectionResult(data);
      const lines = [
        "폴더 검사 완료",
        `대상 접수번호: ${formatInteger(data.requested_count)}`,
        `분할저장: ${data.split_by_year ? "On" : "Off"}`,
        `삭제 예정 파일: ${formatInteger(data.deletion_candidate_count)}`,
        `데이터 경로: ${data.output_directory || ""}`,
      ];
      if (deleteCandidates.length) {
        lines.push("", "삭제 예정 파일", ...deleteCandidates.map((file: any) => `- ${file.name} (${file.reason})`));
      }
      setStatus(lines.join("\n"));
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      if (!controller.signal.aborted) {
        setInspectRunning(false);
      }
    }
  };

  const handleDeleteUnexpectedFiles = async () => {
    if (!deleteConfirmed || deleteConfirmationText.trim() !== "확인했습니다.") {
      setStatus('삭제하려면 삭제 허가를 체크하고 "확인했습니다."를 입력하세요.');
      setIsErrorStatus(true);
      return;
    }
    if (inspectAbortControllerRef.current) {
      inspectAbortControllerRef.current.abort();
      inspectAbortControllerRef.current = null;
    }
    const controller = new AbortController();
    inspectAbortControllerRef.current = controller;

    try {
      setInspectRunning(true);
      setIsErrorStatus(false);
      setStatus("허가된 파일 삭제를 실행하는 중입니다...");
      const response = await fetch(variantConfig.inspectEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildCleanupPayload(false)),
        signal: controller.signal,
      });
      const data = await readJsonResponse(response, "Folder cleanup failed");
      if (!response.ok) throw new Error(data.detail || "Folder cleanup failed");

      const deletedFiles = Array.isArray(data.deleted_files) ? data.deleted_files : [];
      setLastInspectionCandidateCount(0);
      setLastInspectionResult(data);
      setDeleteConfirmed(false);
      setDeleteConfirmationText("");
      const lines = [
        "파일 삭제 완료",
        `대상 접수번호: ${formatInteger(data.requested_count)}`,
        `분할저장: ${data.split_by_year ? "On" : "Off"}`,
        `삭제 파일: ${formatInteger(data.deleted_count)}`,
        `데이터 경로: ${data.output_directory || ""}`,
      ];
      if (deletedFiles.length) {
        lines.push("", "삭제한 파일", ...deletedFiles.map((file: any) => `- ${file.name} (${file.reason})`));
      }
      setStatus(lines.join("\n"));
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      if (!controller.signal.aborted) {
        setInspectRunning(false);
      }
    }
  };

  const handleCancel = async () => {
    if (!activeCancelToken && !activeJobId) return;
    setStatus(variantConfig.stopMessage);
    try {
      await fetch(activeCancelToken ? variantConfig.cancelEndpoint : "/api/utility/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(activeCancelToken ? { cancel_token: activeCancelToken } : { job_id: activeJobId }),
      });
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleMergeContentHtml = async () => {
    if (variant !== "content") return;
    if (!outputDirectory) {
      setStatus("내부 HTML 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const defaultOutputPath = mergeSplitByYear ? outputDirectory : `${outputDirectory}/merged-content-html.json`;
    const payload = {
      input_directory: outputDirectory,
      output_path: mergeOutputPath || defaultOutputPath,
      split_by_year: mergeSplitByYear,
      input_split_by_year: mergeSplitByYear,
      output_split_by_year: mergeSplitByYear,
      limit: limit ? Number(limit) : null,
    };
    startJob("/api/disclosures/html/content-download/merge/start", payload);
  };

  const handleCompressExternalHtml = async () => {
    if (variant !== "external") return;
    if (!compressInputDirectory) {
      setStatus("입력 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (!compressOutputDirectory) {
      setStatus("압축 JSON 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const payload = {
      input_directory: compressInputDirectory,
      output_directory: compressOutputDirectory,
      split_by_year: compressSplitByYear,
      input_split_by_year: compressSplitByYear,
      output_split_by_year: false,
      parallel_workers: compressWorkers ? Number(compressWorkers) : null,
    };
    startJob("/api/disclosures/html/download/compress/start", payload);
  };

  const saveOutputDirectory = (val: string) => {
    setOutputDirectory(val);
    saveSetting(variantConfig.defaultDirectoryKey, val);
    if (variant === "content") {
      setMergeOutputPath(mergeSplitByYear ? val : (val ? `${val}/merged-content-html.json` : ""));
    }
  };

  const saveSourcePath = (val: string) => {
    setSourcePath(val);
    saveSetting(variantConfig.sourceSettingKey, val);
  };

  const saveContentSourceFilePath = (val: string) => {
    setContentSourceFilePath(val);
    saveSetting("html_content_compressed_json_path", val);
  };

  const baseFields: HtmlWorkflowField[] = [
    {
      id: "sourcePath",
      kind: "path",
      label: variant === "content" && contentSourceInputMode === "file" ? "입력 데이터 경로 (외부 HTML 압축 JSON)" : variantConfig.sourceLabel,
      help: variant === "content" && contentSourceInputMode === "file" ? undefined : variantConfig.sourceHelp,
      mode: variant === "content" && contentSourceInputMode === "file" ? "file" : variantConfig.sourcePickMode,
      value: currentSourcePath,
      onChange: variant === "content" && contentSourceInputMode === "file" ? saveContentSourceFilePath : saveSourcePath,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 4,
      trailing: variantConfig.sourcePickMode === "folder" && contentSourceInputMode === "folder" ? (
        <SplitByYearButton
          checked={contentSourceSplitByYear}
          onChange={() => setContentSourceSplitByYear((value) => !value)}
        />
      ) : null,
    },
    {
      id: "outputDirectory",
      kind: "path",
      label: "데이터 경로",
      mode: "folder",
      value: outputDirectory,
      onChange: saveOutputDirectory,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 4,
      trailing: (
        <SplitByYearButton
          checked={downloadSplitByYear}
          onChange={() => setDownloadSplitByYear((value) => !value)}
        />
      ),
    },
    { id: "timeout", kind: "input", type: "number", label: "타임아웃 (초)", value: timeout, onChange: setTimeoutVal },
    { id: "maxRequestsPerMinute", kind: "input", type: "number", label: "최대 요청/분", help: "KIND에 인터넷 요청을 보내는 저장 실행에만 적용됩니다.", value: maxRequestsPerMinute, onChange: setMaxRequestsPerMinute },
    { id: "waitSeconds", kind: "input", type: "number", label: "요청 간격 (초)", value: waitSeconds, onChange: setWaitSeconds },
    { id: "limit", kind: "input", type: "number", label: "최대 처리 건수", help: "테스트 실행이나 샘플 JSON 생성 때만 입력하세요. 비워 두면 전체 대상을 처리합니다.", placeholder: "전체", value: limit, onChange: setLimit },
    { id: "progressInterval", kind: "input", type: "number", label: "진행 확인 간격 (건)", value: progressInterval, onChange: setProgressInterval, span: 2 },
    { id: "skipExisting", kind: "checkbox", checked: skipExisting, onChange: setSkipExisting, checkboxLabel: "기존 파일 건너뛰기", span: 2 },
  ];
  const basePathFields = baseFields.filter((field) => field.id === "sourcePath" || field.id === "outputDirectory");
  const requestOptionFields = baseFields.filter((field) => ["timeout", "maxRequestsPerMinute", "waitSeconds"].includes(field.id));
  const executionOptionFields = baseFields.filter((field) => field.id === "progressInterval" || field.id === "skipExisting");
  const testOptionFields = baseFields.filter((field) => field.id === "limit");

  const compressionFields: HtmlWorkflowField[] = [
    {
      id: "compressInputDirectory",
      kind: "path",
      label: "입력 데이터 경로 (외부 HTML)",
      help: "공시원문 외부 저장으로 만든 KIND 뷰어 HTML 폴더를 선택하세요.",
      mode: "folder",
      value: compressInputDirectory,
      onChange: (val) => {
        setCompressInputDirectory(val);
        saveSetting("html_external_compress_input_directory", val);
      },
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 4,
      trailing: (
        <SplitByYearButton
          checked={compressSplitByYear}
          onChange={() => setCompressSplitByYear((value) => !value)}
        />
      ),
    },
    {
      id: "compressOutputDirectory",
      kind: "path",
      label: "압축 JSON 데이터 경로",
      mode: "folder",
      value: compressOutputDirectory,
      onChange: (val) => {
        setCompressOutputDirectory(val);
        saveSetting("html_external_compress_output_directory", val);
      },
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 4,
    },
  ];
  const compressionSettingFields: HtmlWorkflowField[] = [
    {
      id: "compressWorkers",
      kind: "input",
      type: "number",
      label: "병렬 워커 수",
      help: "비워 두면 파일 수와 CPU 수를 기준으로 자동 선택합니다.",
      placeholder: "자동",
      value: compressWorkers,
      onChange: setCompressWorkers,
      span: 2,
    },
  ];
  const mergeFields: HtmlWorkflowField[] = [
    {
      id: "mergeOutputPath",
      kind: "path",
      label: "병합 결과 데이터 경로",
      mode: mergeSplitByYear ? "folder" : "save",
      value: mergeOutputPath || (mergeSplitByYear ? outputDirectory : (outputDirectory ? `${outputDirectory}/merged-content-html.json` : "")),
      onChange: (val) => {
        setMergeOutputPath(val);
        saveSetting("html_merge_output_path", val);
      },
      placeholder: mergeSplitByYear ? `${outputDirectory || "/path/to/content_html"}` : `${outputDirectory || "/path/to/content_html"}/merged-content-html.json`,
      span: 4,
      trailing: (
        <SplitByYearButton
          checked={mergeSplitByYear}
          onChange={() => setMergeSplitByYear((value) => {
            const nextVal = !value;
            const newPath = nextVal ? outputDirectory : (outputDirectory ? `${outputDirectory}/merged-content-html.json` : "");
            setMergeOutputPath(newPath);
            return nextVal;
          })}
        />
      ),
    },
  ];

  const existingSummary = existingData ? (() => {
    const requestedCount = existingData.requested_count || 0;
    const existingCount = existingData.existing_target_html_count || 0;
    const missingCount = existingData.missing_target_html_count || 0;
    if (requestedCount > 0 && missingCount === 0) {
      return `이번 대상 ${formatInteger(requestedCount)}건이 모두 저장되어 있습니다.`;
    }
    if (requestedCount > 0) {
      return `기존 원문 저장 ${formatInteger(existingCount)}건 감지됨. 이번 대상 ${formatInteger(requestedCount)}건 중 ${formatInteger(missingCount)}건을 새로 저장합니다.`;
    }
    return `기존 원문 저장 ${formatInteger(existingCount)}건 감지됨.`;
  })() : "";

  const existingDetail = existingData ? (() => {
    const deletionCount = existingData.deletion_candidate_count || 0;
    if (deletionCount > 0) {
      return `대상 외 파일 ${formatInteger(deletionCount)}개가 있어 실행 전 폴더 검사가 필요합니다.`;
    }
    if (skipExisting) {
      return "기존 파일 건너뛰기 옵션이 켜져 있습니다.";
    }
    return "기존 파일 건너뛰기 옵션이 꺼져 있어 실행 시 다시 저장합니다.";
  })() : "";
  const existingStatus = existingData ? (() => {
    if (existingSplitMismatch) {
      return {
        className: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/20 dark:text-rose-300 dark:border-rose-900/40",
        label: "분할저장 설정 불일치",
      };
    }
    if ((existingData.deletion_candidate_count || 0) > 0) {
      return {
        className: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/20 dark:text-amber-300 dark:border-amber-900/40",
        label: "폴더 검사 필요",
      };
    }
    if (existingAllSaved) {
      return {
        className: "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-950/20 dark:text-teal-300 dark:border-teal-900/40",
        label: "모두 저장됨",
      };
    }
    return {
      className: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/20 dark:text-amber-300 dark:border-amber-900/40",
      label: "신규 저장 대상 있음",
    };
  })() : null;

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  const isExternalCompressMode = variant === "external" && externalTaskMode === "compress";
  const isContentMergeMode = variant === "content" && contentTaskMode === "merge";
  const showSaveWorkflow =
    (variant === "external" && externalTaskMode === "download") ||
    (variant === "content" && contentTaskMode === "download");

  return (
    <HtmlWorkflowPage
      eyebrow={variant === "external" ? "External HTML Save" : "Content HTML Save"}
      title={isExternalCompressMode
        ? "외부 HTML 압축"
        : isContentMergeMode
          ? "내부 HTML 병합"
          : variantConfig.settingsTitle}
      description={isExternalCompressMode
        ? "저장된 KIND 뷰어 HTML에서 핵심 정보만 추출해 작은 JSON으로 저장합니다."
        : isContentMergeMode
          ? "저장된 KIND 공시 본문 HTML들을 하나의 JSON으로 병합합니다."
          : variantConfig.description}
      actions={variant === "external" ? (
        <div className="inline-flex rounded-md border border-slate-200 p-1 dark:border-[#30363d]">
          <Button
            type="button"
            variant={externalTaskMode === "download" ? "default" : "ghost"}
            size="sm"
            className="h-8"
            onClick={() => setExternalTaskMode("download")}
          >
            <FolderOpen className="mr-2 h-4 w-4" />
            외부 HTML 저장
          </Button>
          <Button
            type="button"
            variant={externalTaskMode === "compress" ? "default" : "ghost"}
            size="sm"
            className="h-8"
            onClick={() => setExternalTaskMode("compress")}
          >
            <FileJson className="mr-2 h-4 w-4" />
            외부 HTML 압축
          </Button>
        </div>
      ) : variant === "content" ? (
        <div className="inline-flex rounded-md border border-slate-200 p-1 dark:border-[#30363d]">
          <Button
            type="button"
            variant={contentTaskMode === "download" ? "default" : "ghost"}
            size="sm"
            className="h-8"
            onClick={() => setContentTaskMode("download")}
          >
            <FolderOpen className="mr-2 h-4 w-4" />
            내부 HTML 저장
          </Button>
          <Button
            type="button"
            variant={contentTaskMode === "merge" ? "default" : "ghost"}
            size="sm"
            className="h-8"
            onClick={() => setContentTaskMode("merge")}
          >
            <FileJson className="mr-2 h-4 w-4" />
            내부 HTML 병합
          </Button>
        </div>
      ) : null}
    >
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          {showSaveWorkflow && (
            <HtmlWorkflowCard
              title="데이터 경로"
              description="원천 파일과 저장 위치는 작업 대상이므로 메인 화면에서 관리합니다."
              actions={variant === "content" ? (
                <div className="inline-flex gap-1 rounded-md border border-slate-200 p-1 dark:border-[#30363d]">
                  <Button
                    type="button"
                    variant={contentSourceInputMode === "folder" ? "default" : "ghost"}
                    size="sm"
                    className="h-8"
                    onClick={() => setContentSourceInputMode("folder")}
                  >
                    <FolderOpen className="mr-2 h-4 w-4" />
                    폴더 입력
                  </Button>
                  <Button
                    type="button"
                    variant={contentSourceInputMode === "file" ? "default" : "ghost"}
                    size="sm"
                    className="h-8"
                    onClick={() => setContentSourceInputMode("file")}
                  >
                    <FileJson className="mr-2 h-4 w-4" />
                    JSON 파일 입력
                  </Button>
                </div>
              ) : null}
            >
              <HtmlWorkflowForm fields={basePathFields} />
            {checkingExisting && !existingData && (
              <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-4 text-sm dark:border-[#30363d] dark:bg-[#161b22]">
                <div className="flex items-start gap-3">
                  <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-slate-500 dark:text-slate-400" />
                  <div className="space-y-1">
                    <p className="font-semibold text-slate-900 dark:text-slate-100">기존 원문 데이터 경로 자동 병렬 확인 중...</p>
                    <p className="break-all text-xs text-slate-500 dark:text-slate-400">{outputDirectory}</p>
                  </div>
                </div>
              </div>
            )}
            {existingCheckError && !existingData && !checkingExisting && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
                <p className="font-semibold">기존 원문 데이터 경로 재확인 실패</p>
                <p className="mt-1 break-words text-xs">{existingCheckError}</p>
              </div>
            )}
            {existingData && (
              <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50/50 p-4 text-sm dark:border-[#30363d] dark:bg-[#161b22] animate-fade-in transition-all">
                <div className="flex flex-col gap-3 border-b border-slate-200 pb-3 dark:border-[#30363d] md:flex-row md:items-center md:justify-between">
                  <div className="space-y-1">
                    <p className="flex items-center gap-1.5 font-semibold text-slate-900 dark:text-slate-100">
                      📂 기존 원문 저장 범위 감지됨
                      {checkingExisting && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-medium text-slate-500 dark:text-slate-400">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          재확인 중
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      저장됨: <span className="font-semibold">{formatInteger(existingData.existing_target_html_count || 0)}</span>건
                      {" "} / 대상: <span className="font-semibold">{formatInteger(existingData.requested_count || 0)}</span>건
                      {" "} / 신규 저장: <span className="font-semibold">{formatInteger(existingData.missing_target_html_count || 0)}</span>건
                      {" "} / 대상 외 파일: <span className="font-semibold">{formatInteger(existingData.deletion_candidate_count || 0)}</span>개
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
                    {(existingData.deletion_candidate_count || 0) > 0 && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-8 shrink-0 self-start border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-[#21262d] dark:hover:text-slate-100 md:self-auto"
                        onClick={handleInspectFolder}
                        disabled={isJobActive || inspectRunning}
                      >
                        폴더 검사하기
                      </Button>
                    )}
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex flex-col justify-between gap-2 rounded border p-2 text-xs dark:border-[#30363d] dark:bg-[#0d1117] sm:flex-row sm:items-center">
                    <div className="space-y-0.5">
                      <p className="font-medium text-slate-800 dark:text-slate-200">{existingSummary}</p>
                      <p className="break-all text-[10px] text-slate-500 dark:text-slate-400">{outputDirectory}</p>
                    </div>
                    {existingStatus && (
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${existingStatus.className}`}>
                        {existingStatus.label}
                      </span>
                    )}
                  </div>
                </div>

                {existingSplitMismatch && (
                  <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-200">
                    <strong>⚠ 오류:</strong> 분할저장 설정이 기존 폴더 구조와 다릅니다. 폴더 내 데이터가 섞이지 않도록 데이터 경로의 분할저장 On/Off를 맞춘 뒤 실행하세요.
                  </div>
                )}

                {(existingData.deletion_candidate_count || 0) > 0 && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
                    <strong>💡 알림:</strong> {existingDetail}
                  </div>
                )}

                {existingCheckError && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
                    <strong>⚠ 재확인 실패:</strong> {existingCheckError}
                  </div>
                )}
              </div>
            )}
            </HtmlWorkflowCard>
          )}

          {isExternalCompressMode && (
            <HtmlWorkflowCard
              title="외부 HTML 압축"
              description="저장된 KIND 뷰어 HTML에서 핵심 정보만 추출해 작은 JSON으로 저장합니다."
            >
                <HtmlWorkflowForm fields={compressionFields} />
            </HtmlWorkflowCard>
          )}

          {isExternalCompressMode && (
            <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
              <CardHeader>
                <CardTitle className="dark:text-white">작업 실행</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 md:grid-cols-2">
                  <Button className="h-10 w-full" onClick={handleCompressExternalHtml} disabled={isJobActive}>
                    <Play className="mr-2 h-4 w-4" />
                    실행
                  </Button>
                  <Button type="button" variant="outline" className="h-10 w-full" onClick={handleCancel} disabled={!activeCancelToken && !activeJobId}>
                    <Square className="mr-2 h-4 w-4" />
                    {UI_TEXT.actions.cancelJob}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {isContentMergeMode && (
            <HtmlWorkflowCard
              title="내부 HTML 병합"
              description="저장된 KIND 공시 본문 HTML들을 하나의 JSON으로 병합합니다. 로컬 파일 처리이므로 최대 요청/분은 적용되지 않습니다."
            >
                <HtmlWorkflowForm fields={mergeFields} />
                <Button variant="outline" className="h-10 w-full" onClick={handleMergeContentHtml} disabled={isJobActive}>
                  <FileJson className="mr-2 h-4 w-4" />
                  내부 HTML 병합
                </Button>
            </HtmlWorkflowCard>
          )}

          {showSaveWorkflow && (
            <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
              <CardHeader>
                <CardTitle className="dark:text-white">작업 실행</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 md:grid-cols-3">
                  <Button variant="outline" className="h-10 w-full" onClick={handleInspectFolder} disabled={isJobActive || inspectRunning}>
                    {inspectRunning ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FolderOpen className="mr-2 h-4 w-4" />}
                    폴더 검사하기
                  </Button>
                  <Button className="h-10 w-full" onClick={handleRun} disabled={isJobActive || existingSplitMismatch}>
                    <Play className="mr-2 h-4 w-4" />
                    실행
                  </Button>
                  <Button type="button" variant="outline" className="h-10 w-full" onClick={handleCancel} disabled={!activeCancelToken && !activeJobId}>
                    <Square className="mr-2 h-4 w-4" />
                    {UI_TEXT.actions.cancelJob}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </section>

        <ActionDock
          activityActive={isJobActive}
          activityContent={
            <JobStatusLogger
              status={status}
              isErrorStatus={isErrorStatus}
              isCancellable={!!activeCancelToken || !!activeJobId}
              onCancel={handleCancel}
            />
          }
          notificationActive={isErrorStatus || !!existingCheckError || lastInspectionCandidateCount > 0 || !!lastInspectionResult}
          notificationContent={
            <>
              {lastInspectionCandidateCount > 0 && (
                <div className="space-y-3">
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
                    삭제 예정 파일 {formatInteger(lastInspectionCandidateCount)}개
                  </div>
                  <div className="flex items-center space-x-2">
                    <Checkbox id="deleteConfirmed" checked={deleteConfirmed} onCheckedChange={(v) => setDeleteConfirmed(!!v)} className="dark:border-[#30363d]" />
                    <Label htmlFor="deleteConfirmed" className="cursor-pointer text-sm dark:text-slate-300">삭제 허가</Label>
                  </div>
                  <Input value={deleteConfirmationText} onChange={(e) => setDeleteConfirmationText(e.target.value)} placeholder="확인했습니다." className={htmlControlClassName} />
                  <Button
                    variant="outline"
                    className="h-10 w-full"
                    onClick={handleDeleteUnexpectedFiles}
                    disabled={isJobActive || inspectRunning || !deleteConfirmed || deleteConfirmationText.trim() !== "확인했습니다."}
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    삭제 예정 파일 {formatInteger(lastInspectionCandidateCount)}개 삭제
                  </Button>
                </div>
              )}
              {lastInspectionResult && (
                <div className="space-y-2 border-t border-slate-200 pt-4 dark:border-[#30363d]">
                  <Label className="dark:text-slate-300">폴더 검사 결과</Label>
                  <pre className="max-h-72 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 dark:border-slate-700 dark:bg-[#090d12] dark:text-blue-100">
                    {JSON.stringify(lastInspectionResult, null, 2)}
                  </pre>
                </div>
              )}
              {!lastInspectionCandidateCount && !lastInspectionResult && isErrorStatus && (
                <div className="whitespace-pre-wrap text-sm text-red-600 dark:text-red-300">{status || "오류 내용을 확인할 수 없습니다."}</div>
              )}
              {!lastInspectionCandidateCount && !lastInspectionResult && !isErrorStatus && existingCheckError && (
                <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
                  {existingCheckError}
                </div>
              )}
              {!lastInspectionCandidateCount && !lastInspectionResult && !isErrorStatus && !existingCheckError && (
                <div className="text-sm text-slate-500 dark:text-slate-400">알림 없음</div>
              )}
            </>
          }
          settingsTitle="시스템 설정"
          settingsContent={
            isExternalCompressMode ? (
              <div className="space-y-3">
                <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">압축 처리</p>
                </div>
                <HtmlWorkflowForm fields={compressionSettingFields} />
              </div>
            ) : isContentMergeMode ? (
              <div className="space-y-3">
                <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">테스트 옵션</p>
                </div>
                <HtmlWorkflowForm fields={testOptionFields} />
              </div>
            ) : (
              <div className="space-y-5">
                <div className="space-y-3">
                  <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">요청 설정</p>
                  </div>
                  <HtmlWorkflowForm fields={requestOptionFields} />
                </div>
                <div className="space-y-3">
                  <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">실행 옵션</p>
                  </div>
                  <HtmlWorkflowForm fields={executionOptionFields} />
                </div>
                <div className="space-y-3">
                  <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">테스트 옵션</p>
                  </div>
                  <HtmlWorkflowForm fields={testOptionFields} />
                </div>
              </div>
            )
          }
        />
      </div>
    </HtmlWorkflowPage>
  );
}
