"use client"

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { FileJson, FolderOpen, Play, Square, Trash2 } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Label, Checkbox } from "@finiq/ui";
import { JobStatusLogger, PageLoadingSpinner, ActionDock } from "@finiq/web-app/status";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import {
  HtmlWorkflowForm,
  HtmlWorkflowPage,
  htmlControlClassName,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import {
  DATA_PATH_LABELS,
  type DataPathField,
} from "@/components/data-path/DataPathCard";
import { SETTINGS_LABELS, UI_TEXT } from "@/config/uiText";
import { formatInteger } from "@/lib/format";
import { WorkflowPathSettings } from "@/components/data-path/WorkflowPathSettings";
import {
  SingleCheckDataIntegrityInspectionCard,
  type SingleCheckDataIntegrityInspectionState,
} from "@/components/data-integrity/DataIntegrityInspectionCard";
import type { DataIntegrityInspectionStep } from "@/components/data-integrity/DataIntegrityInspectionPanel";
import {
  WorkflowModeSwitch,
  type WorkflowModeOption,
} from "@/components/layout/WorkflowModeSwitch";
import {
  FilterPresetCombobox,
  type DisclosureConditionPreset,
} from "@/components/disclosures/DisclosureConditionFilterCard";
import { listDisclosureConditionPresets } from "@/lib/disclosureConditionPresets";

type DownloadVariant = "external" | "internal";
type ExternalTaskMode = "download" | "compress";

const presetIdentity = (preset: DisclosureConditionPreset) => (
  preset.id || (preset.parent_mode ? `${preset.parent_mode}/${preset.mode}` : preset.mode)
);

const presetLabel = (preset: DisclosureConditionPreset) => (
  preset.parent_mode ? `${preset.parent_mode} › ${preset.mode}` : preset.mode
);

const EXTERNAL_TASK_MODE_OPTIONS: readonly WorkflowModeOption<ExternalTaskMode>[] = [
  { value: "download", label: "외부 HTML 저장", icon: FolderOpen },
  { value: "compress", label: "외부 HTML 압축", icon: FileJson },
];

const DOWNLOAD_VARIANTS = {
  external: {
    settingsTitle: "공시원문 외부 저장 설정",
    description: "다운로드된 공시 결과 JSON을 바탕으로 KIND 공시 뷰어 HTML을 대량 저장합니다.",
    sourcePickMode: "folder",
    sourceRequiredMessage: "작업공간 디렉토리를 선택하세요.",
    startEndpoint: "/api/disclosures/external-html-download/start",
    cancelEndpoint: "/api/disclosures/external-html-download/cancel",
    inspectEndpoint: "/api/disclosures/external-html-download/inspect-folder",
    checkExistingEndpoint: "/api/disclosures/external-html-download/check-existing",
    stopMessage: "공시원문 외부 저장 중지를 요청했습니다. 진행 중인 요청이 끝나면 멈춥니다.",
  },
  internal: {
    settingsTitle: "공시원문 내부 저장 설정",
    description: "공시원문 외부 데이터 경로를 바탕으로 KIND 공시 본문 HTML을 대량 저장합니다.",
    sourcePickMode: "folder",
    sourceRequiredMessage: "작업공간 디렉토리를 선택하세요.",
    startEndpoint: "/api/disclosures/internal-html-download/start",
    cancelEndpoint: "/api/disclosures/internal-html-download/cancel",
    inspectEndpoint: "/api/disclosures/internal-html-download/inspect-folder",
    checkExistingEndpoint: "/api/disclosures/internal-html-download/check-existing",
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

export function DisclosureHtmlDownloadPageView({ variant = "external" }: { variant?: DownloadVariant }) {
  const variantConfig = DOWNLOAD_VARIANTS[variant];

  const {
    output_root: dataRoot,
    html_parse_mode: htmlParseMode,
    fetchSettings,
    saveSetting,
  } = useSettingsStore();

  const [loading, setLoading] = useState(true);
  const [, setResult] = useState<any>(null);
  const [filterPresets, setFilterPresets] = useState<DisclosureConditionPreset[]>([]);
  const [selectedFilterId, setSelectedFilterId] = useState("");

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
      if (res.saved_count !== undefined) lines.push(`저장 파일: ${formatInteger(res.saved_count)}`);
      if (res.hashed_count !== undefined) lines.push(`기준 해시: ${formatInteger(res.hashed_count)}`);
      lines.push(`데이터 경로: ${res.output_directory || ""}`);
    }
    if (res.summary?.compressed_files !== undefined) {
      lines.push(`외부 HTML 압축: ${formatInteger(res.summary.compressed_files)}`);
      lines.push(`저장 JSON: ${formatInteger(res.summary.written_files)}`);
      if (res.metadata_check) {
        lines.push(`metadata 확인: ${formatInteger(res.metadata_check.matched_records)}/${formatInteger(res.metadata_check.expected_records)}`);
      }
      if (res.verification) {
        lines.push(`재검사: ${res.verification.passed ? "통과" : "누락/불일치 있음"}`);
        lines.push(`재검사 기록: ${formatInteger(res.verification.verified_records)}/${formatInteger(res.verification.expected_records)}`);
        lines.push(`누락 기록: ${formatInteger(res.verification.missing_records)}`);
      }
      if (Array.isArray(res.written_files)) {
        lines.push("결과 파일", ...res.written_files);
      }
    }
    if (res.format === "finiq_disclosure_external_html_compress_repair_result_v1") {
      lines.push(`재생성: ${formatInteger(res.regenerated_mode_count)}/${formatInteger(res.target_mode_count)}개 모드`);
      if (res.failed_mode_count) {
        lines.push(`재생성 실패: ${res.failed_modes.join(", ")}`);
      }
      if (res.verification) {
        lines.push(`최종 검사: ${res.verification.passed ? "정상" : "사용 불가"}`);
      }
    }
    if (res.format === "finiq_disclosure_external_html_redownload_result_v1") {
      lines.push(`재다운로드: ${formatInteger(res.completed_mode_count)}/${formatInteger(res.target_mode_count)}개 기본 모드`);
      if (res.failed_mode_count) {
        lines.push(`재다운로드 실패: ${res.failed_modes.join(", ")}`);
      }
      if (res.verification) {
        lines.push(`최종 검사: ${res.verification.passed ? "정상" : "사용 불가"}`);
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
  const [externalSaveInspectionData, setExternalSaveInspectionData] = useState<any>(null);
  const [existingCheckError, setExistingCheckError] = useState("");
  const [existingCheckCompleted, setExistingCheckCompleted] = useState(false);
  const [compressionInspectionData, setCompressionInspectionData] = useState<any>(null);
  const [compressionInspectionError, setCompressionInspectionError] = useState("");
  const [compressionInspectionCompleted, setCompressionInspectionCompleted] = useState(false);
  const inspectAbortControllerRef = useRef<AbortController | null>(null);

  // Form State
  const [externalTaskMode, setExternalTaskMode] = useState<ExternalTaskMode>("download");
  const [compressWorkers, setCompressWorkers] = useState("");
  const [timeout, setTimeoutVal] = useState("20");
  const [maxRequestsPerMinute, setMaxRequestsPerMinute] = useState("90");
  const [waitSeconds, setWaitSeconds] = useState("0");
  const [limit, setLimit] = useState("");
  const [skipExisting, setSkipExisting] = useState(true);
  const [progressInterval, setProgressInterval] = useState("10");
  const [problemFileLimit, setProblemFileLimit] = useState("20");

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
    onSuccess: (nextResult) => {
      setResult(nextResult);
      if (nextResult?.format === "finiq_disclosure_external_html_compress_repair_result_v1") {
        setCompressionInspectionData(nextResult.verification);
        setCompressionInspectionError(nextResult.passed ? "" : "압축 파일 재생성에 실패했습니다.");
        setCompressionInspectionCompleted(true);
        setIsErrorStatus(!nextResult.passed);
        return;
      }
      if (nextResult?.format === "finiq_disclosure_external_html_redownload_result_v1") {
        setExternalSaveInspectionData(nextResult.verification);
        setExistingCheckError(nextResult.passed ? "" : "재다운로드 후에도 외부 HTML 검사에 실패했습니다.");
        setExistingCheckCompleted(true);
        setIsErrorStatus(!nextResult.passed);
        return;
      }
      setExistingData(null);
      setExternalSaveInspectionData(null);
      setExistingCheckError("");
      setExistingCheckCompleted(false);
      setCompressionInspectionData(null);
      setCompressionInspectionError("");
      setCompressionInspectionCompleted(false);
      setLastInspectionCandidateCount(0);
      setLastInspectionResult(null);
    },
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

  const handlePathError = useCallback((message: string) => {
    setStatus(message);
    setIsErrorStatus(true);
  }, [setIsErrorStatus, setStatus]);

  useEffect(() => {
    fetchSettings().then((config) => {
      setSelectedFilterId(config.html_parse_mode || "");
    }).catch(err => {
      setStatus(err.message);
      setIsErrorStatus(true);
    }).finally(() => {
      setLoading(false);
    });
  }, [fetchSettings, setStatus, setIsErrorStatus]);

  useEffect(() => {
    if (!dataRoot?.trim()) {
      setFilterPresets([]);
      return;
    }
    listDisclosureConditionPresets(dataRoot).then((response) => {
      setFilterPresets(response.presets);
    }).catch((error) => {
      setFilterPresets([]);
      setStatus(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    });
  }, [dataRoot, setIsErrorStatus, setStatus]);

  const selectedFilterPreset = useMemo(
    () => filterPresets.find((preset) => presetIdentity(preset) === selectedFilterId),
    [filterPresets, selectedFilterId],
  );
  const selectedFilterMode = selectedFilterPreset?.mode || "";
  const selectedFilterParentMode = selectedFilterPreset?.parent_mode || "";

  useEffect(() => {
    if (!isJobActive) {
      setActiveCancelToken(null);
    }
  }, [isJobActive]);

  const currentSourcePath = dataRoot;
  const currentSourceRequiredMessage = variantConfig.sourceRequiredMessage;
  const inspectionFilterKey = variant === "external" ? "" : selectedFilterId;
  const inspectionLimitKey = variant === "external" ? "" : limit;

  const parsedProblemFileLimit = (() => {
    const parsed = Number(problemFileLimit);
    return Number.isInteger(parsed) && parsed >= 1 ? parsed : undefined;
  })();

  const buildRunPayload = useCallback((cancelToken: string) => ({
      data_root: dataRoot,
      mode: selectedFilterMode,
      ...(selectedFilterParentMode ? { parent_mode: selectedFilterParentMode } : {}),
      output_directory: "",
      timeout: Number(timeout),
      max_requests_per_minute: Number(maxRequestsPerMinute),
      wait_seconds: Number(waitSeconds),
      limit: limit ? Number(limit) : null,
      skip_existing: skipExisting,
      progress_interval: Number(progressInterval),
      ...(parsedProblemFileLimit != null ? { problem_file_limit: parsedProblemFileLimit } : {}),
      cancel_token: cancelToken,
  }), [
    dataRoot,
    selectedFilterMode,
    selectedFilterParentMode,
    timeout,
    maxRequestsPerMinute,
    waitSeconds,
    limit,
    skipExisting,
    progressInterval,
    parsedProblemFileLimit,
  ]);

  const handleRun = async () => {
    if (!currentSourcePath) {
      setStatus(currentSourceRequiredMessage);
      setIsErrorStatus(true);
      return;
    }
    if (!selectedFilterPreset) {
      setStatus("조건검색 필터를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const cancelToken = window.crypto.randomUUID();
    setActiveCancelToken(cancelToken);

    const payload = buildRunPayload(cancelToken);

    startJob(variantConfig.startEndpoint, payload);
  };

  const buildCleanupPayload = useCallback((dryRun: boolean) => ({
    data_root: dataRoot,
    mode: selectedFilterMode,
    ...(selectedFilterParentMode ? { parent_mode: selectedFilterParentMode } : {}),
    output_directory: "",
    limit: limit ? Number(limit) : null,
    ...(parsedProblemFileLimit != null ? { problem_file_limit: parsedProblemFileLimit } : {}),
    dry_run: dryRun,
    delete_confirmed: deleteConfirmed,
    delete_confirmation_text: deleteConfirmationText,
  }), [
    dataRoot,
    selectedFilterMode,
    selectedFilterParentMode,
    limit,
    parsedProblemFileLimit,
    deleteConfirmed,
    deleteConfirmationText,
  ]);

  useEffect(() => {
    inspectAbortControllerRef.current?.abort();
    inspectAbortControllerRef.current = null;
    setInspectRunning(false);
    setExistingData(null);
    setExternalSaveInspectionData(null);
    setExistingCheckError("");
    setExistingCheckCompleted(false);
    setCompressionInspectionData(null);
    setCompressionInspectionError("");
    setCompressionInspectionCompleted(false);
    setLastInspectionCandidateCount(0);
    setLastInspectionResult(null);
    setDeleteConfirmed(false);
    setDeleteConfirmationText("");
  }, [currentSourcePath, dataRoot, inspectionFilterKey, inspectionLimitKey, problemFileLimit, externalTaskMode]);

  useEffect(() => {
    if (variant !== "external" || !externalSaveInspectionData) return;
    const selectedResult = Array.isArray(externalSaveInspectionData.results)
      ? externalSaveInspectionData.results.find((item: any) => item.id === selectedFilterId)
      : null;
    setExistingData(selectedResult || null);
    setLastInspectionResult(selectedResult || null);
    setLastInspectionCandidateCount(selectedResult?.deletion_candidate_count || 0);
  }, [externalSaveInspectionData, selectedFilterId, variant]);

  useEffect(() => {
    return () => {
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
    if (variant !== "external" && !selectedFilterPreset) {
      setStatus("조건검색 필터를 선택하세요.");
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
      setExistingData(null);
      setExternalSaveInspectionData(null);
      setExistingCheckError("");
      setExistingCheckCompleted(false);
      setDeleteConfirmed(false);
      setDeleteConfirmationText("");
      setIsErrorStatus(false);
      setStatus("폴더를 검사하는 중입니다...");
      const payload = variant === "external"
        ? {
            data_root: dataRoot,
            ...(parsedProblemFileLimit != null ? { problem_file_limit: parsedProblemFileLimit } : {}),
          }
        : buildCleanupPayload(true);
      const response = await fetch(variantConfig.checkExistingEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const data = await readJsonResponse(response, "Folder inspection failed");
      if (!response.ok) throw new Error(data.detail || "Folder inspection failed");

      const selectedResult = variant === "external" && Array.isArray(data.results)
        ? data.results.find((item: any) => item.id === selectedFilterId)
        : data;
      const deleteCandidates = Array.isArray(selectedResult?.deletion_candidates) ? selectedResult.deletion_candidates : [];
      setLastInspectionCandidateCount(selectedResult?.deletion_candidate_count || 0);
      setLastInspectionResult(selectedResult || null);
      setExistingData(selectedResult || null);
      setExternalSaveInspectionData(variant === "external" ? data : null);
      setExistingCheckCompleted(true);
      const lines = variant === "external"
        ? [
            "외부 HTML 검사 완료",
            `대상 모드: ${formatInteger(data.mode_count)}`,
            `정상 모드: ${formatInteger(data.passed_mode_count)}`,
            `문제 모드: ${formatInteger(data.failed_mode_count)}`,
          ]
        : [
            "폴더 검사 완료",
            `대상 접수번호: ${formatInteger(data.requested_count)}`,
            `삭제 예정 파일: ${formatInteger(data.deletion_candidate_count)}`,
            `데이터 경로: ${data.output_directory || ""}`,
          ];
      if (deleteCandidates.length) {
        lines.push("", "삭제 예정 파일", ...deleteCandidates.map((file: any) => `- ${file.name} (${file.reason})`));
      }
      setStatus(lines.join("\n"));
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      setExistingCheckError(err.message || "기존 원문 데이터 검사에 실패했습니다.");
      setExistingCheckCompleted(false);
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      if (!controller.signal.aborted) {
        setInspectRunning(false);
      }
    }
  };

  const handleInspectCompressedFile = async () => {
    if (!currentSourcePath) {
      setStatus(currentSourceRequiredMessage);
      setIsErrorStatus(true);
      return;
    }
    inspectAbortControllerRef.current?.abort();
    const controller = new AbortController();
    inspectAbortControllerRef.current = controller;

    try {
      setInspectRunning(true);
      setCompressionInspectionData(null);
      setCompressionInspectionError("");
      setCompressionInspectionCompleted(false);
      setIsErrorStatus(false);
      setStatus("압축 파일을 검사하는 중입니다...");
      const response = await fetch(
        "/api/disclosures/external-html-download/compress/check-existing",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            data_root: dataRoot,
            parallel_workers: compressWorkers ? Number(compressWorkers) : null,
          }),
          signal: controller.signal,
        },
      );
      const data = await readJsonResponse(response, "압축 파일 검사에 실패했습니다.");
      if (!response.ok) throw new Error(data.detail || "압축 파일 검사에 실패했습니다.");

      setCompressionInspectionData(data);
      setCompressionInspectionCompleted(true);
      setStatus([
        "압축 파일 검사 완료",
        `대상 모드: ${formatInteger(data.mode_count)}`,
        `정상 모드: ${formatInteger(data.passed_mode_count)}`,
        `문제 모드: ${formatInteger(data.failed_mode_count)}`,
      ].join("\n"));
    } catch (err: any) {
      if (err.name === "AbortError") return;
      const message = err.message || "압축 파일 검사에 실패했습니다.";
      setCompressionInspectionError(message);
      setCompressionInspectionCompleted(false);
      setStatus(message);
      setIsErrorStatus(true);
    } finally {
      if (!controller.signal.aborted) {
        setInspectRunning(false);
      }
    }
  };

  const handleRepairCompressedFiles = () => {
    if (!dataRoot) {
      setStatus("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    startJob(
      "/api/disclosures/external-html-download/compress/repair/start",
      {
        data_root: dataRoot,
        parallel_workers: compressWorkers ? Number(compressWorkers) : null,
      },
    );
  };

  const handleRedownloadMissingExternalHtml = () => {
    if (!dataRoot) {
      setStatus("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    startJob(
      "/api/disclosures/external-html-download/redownload/start",
      {
        data_root: dataRoot,
        timeout: Number(timeout),
        max_requests_per_minute: Number(maxRequestsPerMinute),
        wait_seconds: Number(waitSeconds),
        skip_existing: skipExisting,
        progress_interval: Number(progressInterval),
        ...(parsedProblemFileLimit != null ? { problem_file_limit: parsedProblemFileLimit } : {}),
      },
    );
  };

  const handleDeleteUnexpectedFiles = async () => {
    if (selectedFilterParentMode) {
      setStatus("파생 필터에서는 상위 필터가 소유한 파일을 삭제할 수 없습니다.");
      setIsErrorStatus(true);
      return;
    }
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
      setExistingData(null);
      setExternalSaveInspectionData(null);
      setExistingCheckCompleted(false);
      setDeleteConfirmed(false);
      setDeleteConfirmationText("");
      const lines = [
        "파일 삭제 완료",
        `대상 접수번호: ${formatInteger(data.requested_count)}`,
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

  const handleCompressExternalHtml = async () => {
    if (variant !== "external") return;
    if (!dataRoot) {
      setStatus("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const payload = {
      data_root: dataRoot,
      mode: selectedFilterMode,
      ...(selectedFilterParentMode ? { parent_mode: selectedFilterParentMode } : {}),
      input_directory: "",
      output_directory: "",
      parallel_workers: compressWorkers ? Number(compressWorkers) : null,
    };
    startJob("/api/disclosures/external-html-download/compress/start", payload);
  };

  const saveWorkspaceDirectory = async (val: string) => {
    await saveSetting("output_root", val);
  };

  const basePathFields: DataPathField[] = [
    {
      id: "sourcePath",
      label: DATA_PATH_LABELS.workspace,
      mode: variantConfig.sourcePickMode,
      value: currentSourcePath,
      onChange: saveWorkspaceDirectory,
    },
  ];

  const baseFields: HtmlWorkflowField[] = [
    { id: "timeout", kind: "input", type: "number", label: SETTINGS_LABELS.timeoutSeconds, value: timeout, onChange: setTimeoutVal },
    { id: "maxRequestsPerMinute", kind: "input", type: "number", label: SETTINGS_LABELS.maxRequestsPerMinute, value: maxRequestsPerMinute, onChange: setMaxRequestsPerMinute },
    { id: "waitSeconds", kind: "input", type: "number", label: SETTINGS_LABELS.requestIntervalSeconds, value: waitSeconds, onChange: setWaitSeconds },
    { id: "limit", kind: "input", type: "number", label: SETTINGS_LABELS.maxItems, placeholder: "전체", value: limit, onChange: setLimit },
    { id: "progressInterval", kind: "input", type: "number", label: SETTINGS_LABELS.progressInterval, value: progressInterval, onChange: setProgressInterval, span: 2 },
    { id: "skipExisting", kind: "checkbox", checked: skipExisting, onChange: setSkipExisting, checkboxLabel: "기존 파일 건너뛰기", span: 2 },
    { id: "problemFileLimit", kind: "input", type: "number", label: "문제 파일 표시 수", value: problemFileLimit, onChange: setProblemFileLimit, span: 2 },
  ];
  const requestOptionFields = baseFields.filter((field) => ["timeout", "maxRequestsPerMinute", "waitSeconds"].includes(field.id));
  const executionOptionFields = baseFields.filter((field) => field.id === "progressInterval" || field.id === "skipExisting");
  const testOptionFields = baseFields.filter((field) => field.id === "limit");
  const displayOptionFields = baseFields.filter((field) => field.id === "problemFileLimit");

  const compressionFields: DataPathField[] = [
    {
      id: "compressInputDirectory",
      label: DATA_PATH_LABELS.workspace,
      value: dataRoot,
      onChange: saveWorkspaceDirectory,
    },
  ];
  const compressionSettingFields: HtmlWorkflowField[] = [
    {
      id: "compressWorkers",
      kind: "input",
      type: "number",
      label: SETTINGS_LABELS.workerCount,
      placeholder: "자동",
      value: compressWorkers,
      onChange: setCompressWorkers,
      span: 2,
    },
  ];
  const saveInspectionData = variant === "external"
    ? externalSaveInspectionData
    : existingData;
  const existingSummary = existingData ? (() => {
    const requestedCount = existingData.requested_count || 0;
    const existingCount = existingData.existing_target_html_count || 0;
    const downloadCount = existingData.download_required_target_html_count
      ?? existingData.missing_target_html_count
      ?? 0;
    const unverifiedCount = existingData.hash_unverified_target_html_count || 0;
    if (requestedCount > 0 && downloadCount === 0 && unverifiedCount === 0) {
      return `이번 대상 ${formatInteger(requestedCount)}건이 모두 저장되어 있습니다.`;
    }
    if (requestedCount > 0) {
      return `기존 원문 저장 ${formatInteger(existingCount)}건 감지됨. 이번 대상 ${formatInteger(requestedCount)}건 중 ${formatInteger(downloadCount)}건을 다운로드해야 합니다.`;
    }
    return `기존 원문 저장 ${formatInteger(existingCount)}건 감지됨.`;
  })() : "";


  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  const isExternalCompressMode = variant === "external" && externalTaskMode === "compress";
  const showSaveWorkflow =
    (variant === "external" && externalTaskMode === "download") ||
    variant === "internal";
  const hasInspectionInput = !!currentSourcePath;
  // Files still to download are normal work for a 기본 필터. A 파생 필터 cannot
  // save parent-owned HTML here, so missing parent files block reuse.
  const selectedPendingDownloadCount = existingData
    ? Number(
        existingData.download_required_target_html_count
          ?? existingData.missing_target_html_count
          ?? 0,
      )
    : 0;
  const pendingDownloadCount = selectedPendingDownloadCount;
  const parentMissingHtmlCount = selectedFilterParentMode
    ? Math.max(
        Number(existingData?.missing_target_html_count || 0)
          - Number(existingData?.invalid_target_html_count || 0),
        0,
      )
    : 0;
  const derivedParentIncomplete = Boolean(selectedFilterParentMode) && selectedPendingDownloadCount > 0;
  const integrityProblemCount = existingData
    ? Number(existingData.invalid_target_html_count || 0)
      + Number(existingData.hash_mismatch_target_html_count || 0)
      + Number(existingData.hash_unverified_target_html_count || 0)
      + Number(existingData.deletion_candidate_count || 0)
      + parentMissingHtmlCount
    : 0;
  const visibleProblemFiles = Array.isArray(lastInspectionResult?.deletion_candidates)
    ? lastInspectionResult.deletion_candidates
    : [];
  const problemFileTotal = Number(
    lastInspectionResult?.deleted_file_count
    ?? lastInspectionResult?.deletion_candidate_count
    ?? lastInspectionCandidateCount
    ?? 0,
  );
  const omittedProblemFileCount = Math.max(
    problemFileTotal - visibleProblemFiles.length,
    0,
  );
  const integrityProblems = existingData ? ([
    [existingData.invalid_target_html_count, "깨진 파일", "건"],
    [existingData.hash_mismatch_target_html_count, "해시 불일치", "건"],
    [existingData.hash_unverified_target_html_count, "기준 해시 없음", "건"],
    [parentMissingHtmlCount, "상위 필터에 없는 원문", "건"],
    [existingData.deletion_candidate_count, "대상 외 파일", "개"],
  ] as const)
    .filter(([count]) => Number(count || 0) > 0)
    .map(([count, label, unit]) => `${label} ${formatInteger(count)}${unit}`) : [];
  const remainingInspection = Boolean(
    variant !== "external"
    && showSaveWorkflow
    && existingCheckCompleted
    && pendingDownloadCount > 0
    && integrityProblemCount === 0
    && !existingCheckError
    && !inspectRunning,
  );
  const saveInspectionState: SingleCheckDataIntegrityInspectionState = !hasInspectionInput
    ? "waiting"
    : inspectRunning
      ? "running"
      : existingCheckError
          || (variant === "external"
            ? Boolean(externalSaveInspectionData && !externalSaveInspectionData.passed)
            : integrityProblemCount > 0)
        ? "failed"
        : remainingInspection
          ? "running"
          : existingCheckCompleted
            ? "success"
            : "waiting";
  const compressionInspectionState: SingleCheckDataIntegrityInspectionState = !hasInspectionInput
    ? "waiting"
    : inspectRunning
      ? "running"
      : compressionInspectionError || (compressionInspectionData && !compressionInspectionData.passed)
        ? "failed"
        : compressionInspectionCompleted
          ? "success"
          : "waiting";
  const compressionInspectionFailed = Boolean(
    compressionInspectionError
    || (compressionInspectionData && !compressionInspectionData.passed),
  );
  const externalSaveInspectionFailed = Boolean(
    externalSaveInspectionData && !externalSaveInspectionData.passed,
  );
  const compressionInspectionRepairable = Number(
    compressionInspectionData?.repairable_failed_mode_count || 0,
  ) > 0;
  const externalSaveRedownloadable = variant === "external"
    && externalTaskMode === "download"
    && Number(
      externalSaveInspectionData?.owner_download_required_target_html_count || 0,
    ) > 0;
  const inspectionState = isExternalCompressMode
    ? compressionInspectionState
    : saveInspectionState;
  const inspectionStepState: SingleCheckDataIntegrityInspectionState = remainingInspection
    ? "success"
    : inspectionState;
  const remainingInspectionSummary = `대상 ${formatInteger(existingData?.requested_count || 0)}건 중 ${formatInteger(pendingDownloadCount)}건이 아직 저장되지 않았습니다. 재다운로드를 누르면 확인된 기존 파일은 건너뛰고 미저장분만 내려받습니다.`;
  const saveInspectionCopy = {
    waiting: hasInspectionInput
      ? ["검사를 시작하지 않았습니다", variant === "external" ? "검사하기를 누르면 모든 모드의 저장 파일과 해시 구성을 확인합니다." : "검사하기를 누르면 현재 경로의 저장 파일과 해시 구성을 확인합니다."]
      : ["데이터 경로를 선택하세요", "입력 경로와 결과 경로를 선택한 다음 검사하기를 누르세요."],
    ready: ["기존 원문 데이터 검사가 필요합니다", "현재 경로의 저장 파일과 해시 구성을 확인하세요."],
    running: remainingInspection
      ? ["미저장 원문 다운로드", remainingInspectionSummary]
      : ["기존 원문 데이터를 확인하고 있습니다", variant === "external" ? "모든 모드의 대상과 저장 파일을 비교하고 기준 해시를 확인합니다." : "현재 대상과 저장 파일을 비교하고 기준 해시를 확인합니다."],
    success: saveInspectionData
      ? variant === "external"
        ? [
            "모든 모드의 외부 HTML이 정상입니다",
            `${formatInteger(externalSaveInspectionData?.mode_count || 0)}개 모드와 기본 모드 대상 ${formatInteger(externalSaveInspectionData?.owner_requested_count || 0)}건을 확인했습니다.`,
          ]
        : ["기존 원문 데이터를 그대로 사용해도 됩니다", existingSummary]
      : ["기존 원문 데이터가 없습니다", "현재 대상과 충돌하는 기존 원문 파일이 없습니다."],
    failed: [
      "기존 원문 데이터에 문제가 있습니다",
      existingCheckError
        || (variant === "external" && externalSaveInspectionData
          ? `${formatInteger(externalSaveInspectionData.failed_mode_count)}개 모드에 미저장 또는 무결성 문제가 있습니다.`
          : integrityProblems.length
            ? `${integrityProblems.join(" · ")} 때문에 기존 원문을 그대로 재사용할 수 없습니다.`
            : "검사 결과를 확인해 주세요."),
    ],
  }[saveInspectionState];
  const externalSaveResults = Array.isArray(externalSaveInspectionData?.results)
    ? externalSaveInspectionData.results
    : [];
  const compressionResults = Array.isArray(compressionInspectionData?.results)
    ? compressionInspectionData.results
    : [];
  const compressionInspectionCopy = {
    waiting: hasInspectionInput
      ? ["압축 파일 검사를 시작하지 않았습니다", "검사하기를 누르면 저장된 압축 JSON의 구성과 내용을 확인합니다."]
      : ["데이터 경로를 선택하세요", "압축 파일이 있는 작업공간 경로를 선택한 다음 검사하기를 누르세요."],
    ready: ["압축 파일 검사가 필요합니다", "저장된 압축 JSON의 구성과 내용을 확인하세요."],
    running: ["압축 파일을 확인하고 있습니다", "모든 모드의 저장된 원문 HTML과 압축 JSON의 기록·hash·size가 일치하는지 확인합니다."],
    success: [
      "모든 압축 파일이 정상입니다",
      `${formatInteger(compressionInspectionData?.mode_count || 0)}개 모드의 기록 ${formatInteger(compressionInspectionData?.verified_records || 0)}건을 확인했습니다.`,
    ],
    failed: [
      "압축 파일에 문제가 있습니다",
      compressionInspectionError
        || (compressionInspectionRepairable
          ? `${formatInteger(compressionInspectionData?.repairable_failed_mode_count || 0)}개 모드의 압축 파일을 다시 생성해야 합니다.`
          : "압축 파일 검사 결과를 확인해 주세요."),
    ],
  }[compressionInspectionState];
  const inspectionCopy = isExternalCompressMode
    ? compressionInspectionCopy
    : saveInspectionCopy;
  const saveInspectionStepSummary = variant === "external" && externalSaveInspectionData
    ? `전체 ${formatInteger(externalSaveInspectionData.mode_count)}개 모드 · 정상 ${formatInteger(externalSaveInspectionData.passed_mode_count)}개 · 문제 ${formatInteger(externalSaveInspectionData.failed_mode_count)}개 · 기본 모드 대상 ${formatInteger(externalSaveInspectionData.owner_requested_count)}건 중 미저장·재저장 필요 ${formatInteger(externalSaveInspectionData.owner_download_required_target_html_count)}건입니다.`
    : existingData
      ? `${existingData.output_directory} · 대상 ${formatInteger(existingData.requested_count)}건 중 ${formatInteger(existingData.existing_target_html_count)}건은 저장되어 있고 ${formatInteger(existingData.download_required_target_html_count ?? existingData.missing_target_html_count)}건은 새로 저장해야 합니다. 해시 불일치 ${formatInteger(existingData.hash_mismatch_target_html_count)}건, 기준 없음 ${formatInteger(existingData.hash_unverified_target_html_count)}건, 대상 외 파일 ${formatInteger(existingData.deletion_candidate_count)}개입니다.`
      : existingCheckCompleted
        ? "현재 대상과 충돌하는 기존 저장 파일이 없습니다."
        : variant === "external"
          ? "모든 모드의 대상과 저장 파일을 비교하고, 저장 파일의 기준 해시와 대상 외 파일을 함께 확인합니다."
          : "현재 대상과 저장 파일을 비교하고, 저장 파일의 기준 해시와 대상 외 파일을 함께 확인합니다.";
  const compressionInspectionStepSummary = compressionInspectionData
    ? `전체 ${formatInteger(compressionInspectionData.mode_count)}개 모드 · 정상 ${formatInteger(compressionInspectionData.passed_mode_count)}개 · 문제 ${formatInteger(compressionInspectionData.failed_mode_count)}개 · 확인 기록 ${formatInteger(compressionInspectionData.verified_records)}/${formatInteger(compressionInspectionData.expected_records)}건입니다.`
    : "모든 모드의 compressed-external-html.json 형식, 저장된 원문 HTML 기록, hash·size 일치 여부를 확인합니다.";
  const inspectionStepSummary = isExternalCompressMode
    ? compressionInspectionStepSummary
    : saveInspectionStepSummary;

  const inspectionRan = !!saveInspectionData || existingCheckCompleted;
  const pendingStepStatus = inspectRunning
    ? "waiting"
    : !inspectionRan
      ? "waiting"
      : derivedParentIncomplete
        ? "failed"
        : pendingDownloadCount > 0
          ? "ready"
          : "complete";
  const pendingStepSummary = inspectRunning
    ? "위 검사 결과를 기다리고 있습니다."
    : !inspectionRan
      ? "위에서 검사하면 새로 저장해야 할 원문 건수를 함께 확인합니다."
      : derivedParentIncomplete
        ? `대상 ${formatInteger(existingData?.requested_count || 0)}건 중 ${formatInteger(pendingDownloadCount)}건을 상위 필터에서 먼저 저장해야 합니다. 파생 필터에서는 다시 받을 수 없습니다.`
        : pendingDownloadCount > 0
          ? `대상 ${formatInteger(existingData?.requested_count || 0)}건 중 ${formatInteger(pendingDownloadCount)}건이 아직 저장되지 않았습니다. 재다운로드를 누르면 확인된 기존 파일은 건너뛰고 미저장분만 내려받습니다.`
          : "이번 대상이 모두 저장되어 있어 새로 받을 원문이 없습니다.";
  const pendingStepLabel = inspectRunning
    ? "대기"
    : !inspectionRan
      ? "대기"
      : derivedParentIncomplete
        ? "사용 불가"
        : pendingDownloadCount > 0
          ? "다운로드 필요"
          : "정상";
  const inspectionExtraSteps: DataIntegrityInspectionStep[] = variant === "internal" ? [{
    key: "pending-download",
    numbered: false,
    title: "미저장 원문 다운로드",
    summary: pendingStepSummary,
    status: pendingStepStatus,
    statusLabel: pendingStepLabel,
    action: !inspectRunning && selectedPendingDownloadCount > 0 && !selectedFilterParentMode ? {
      label: "재다운로드",
      onClick: handleRun,
      disabled: isJobActive
        || (skipExisting && (existingData?.hash_unverified_target_html_count || 0) > 0),
    } : undefined,
  }] : [];

  const activePathFields = isExternalCompressMode ? compressionFields : basePathFields;

  const existingDataInspectionCard = (
    <SingleCheckDataIntegrityInspectionCard
      description={isExternalCompressMode
        ? "저장된 압축 JSON의 기록 구성과 원문 일치 여부를 확인합니다."
        : variant === "external"
          ? "실행 전에 모든 모드의 대상과 저장 파일을 비교하고 기준 해시를 확인합니다."
          : "실행 전에 현재 대상과 저장 파일을 비교하고 기준 해시를 확인합니다."}
      state={inspectionState}
      stepState={inspectionStepState}
      verdictTitle={inspectionCopy[0]}
      verdictDescription={inspectionCopy[1]}
      stepTitle={isExternalCompressMode ? "압축 파일 검사" : "기존 원문 데이터 검사"}
      stepSummary={inspectionStepSummary}
      extraSteps={inspectionExtraSteps.length ? inspectionExtraSteps : undefined}
      action={hasInspectionInput ? {
        label: inspectRunning
          ? "검사 중..."
          : externalSaveRedownloadable
            ? "재다운로드"
          : isExternalCompressMode && compressionInspectionRepairable
            ? "재생성"
            : "검사하기",
        onClick: externalSaveRedownloadable
          ? handleRedownloadMissingExternalHtml
          : isExternalCompressMode && compressionInspectionRepairable
            ? handleRepairCompressedFiles
            : isExternalCompressMode
              ? handleInspectCompressedFile
              : handleInspectFolder,
        disabled: inspectRunning
          || isJobActive
          || (externalSaveRedownloadable
            && skipExisting
            && Number(externalSaveInspectionData?.owner_hash_unverified_target_html_count || 0) > 0),
        loading: inspectRunning,
        showResultStatus: !(externalSaveRedownloadable
          || (isExternalCompressMode && compressionInspectionRepairable)),
      } : undefined}
    />
  );

  return (
    <HtmlWorkflowPage
      eyebrow={variant === "external" ? "External HTML Save" : "Internal HTML Save"}
      title={isExternalCompressMode
        ? "외부 HTML 압축"
        : variantConfig.settingsTitle}
      description={isExternalCompressMode
        ? "저장된 KIND 뷰어 HTML에서 핵심 정보만 추출해 작은 JSON으로 저장합니다."
        : variantConfig.description}
    >
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          {variant === "external" && (
            <WorkflowModeSwitch
              ariaLabel="외부 HTML 작업 모드"
              value={externalTaskMode}
              options={EXTERNAL_TASK_MODE_OPTIONS}
              onValueChange={setExternalTaskMode}
              testId="external-html-mode-control"
            />
          )}

          {existingDataInspectionCard}

          <Card className="border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
            <CardHeader>
              <CardTitle className="dark:text-white">조건검색 필터</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2">
              <Label htmlFor={`${variant}-filter-preset`} className="dark:text-slate-300">조건검색 필터</Label>
              <FilterPresetCombobox
                id={`${variant}-filter-preset`}
                value={selectedFilterId}
                presets={filterPresets}
                onValueChange={setSelectedFilterId}
                onSelectExisting={setSelectedFilterId}
                getPresetIdentity={presetIdentity}
                getPresetLabel={presetLabel}
                allowCreate={false}
              />
            </CardContent>
          </Card>

          {/* LEGACY: 본문 데이터 경로 카드. 경로 입력은 우측 설정 패널(WorkflowPathSettings)로 옮겼다.
              <DataPathCard onError={handlePathError} fields={activePathFields} /> */}

          {isExternalCompressMode && (
            <Card className="border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
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

          {showSaveWorkflow && (
            <Card className="border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
              <CardHeader>
                <CardTitle className="dark:text-white">작업 실행</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 md:grid-cols-2">
                  <Button
                    className="h-10 w-full"
                    onClick={handleRun}
                    disabled={isJobActive
                      || derivedParentIncomplete
                      || (skipExisting && (existingData?.hash_unverified_target_html_count || 0) > 0)}
                  >
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
          notificationActive={isErrorStatus || !!existingCheckError || lastInspectionCandidateCount > 0 || !!lastInspectionResult || !!externalSaveInspectionData || !!compressionInspectionData}
          notificationTone={isErrorStatus ? "error" : existingCheckError || integrityProblemCount > 0 || remainingInspection || externalSaveInspectionFailed || compressionInspectionFailed ? "warning" : "success"}
          notificationDismissible={false}
          notificationContent={
            <>
              {variant === "external" && externalTaskMode === "download" && externalSaveInspectionData && (
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">외부 HTML 저장 검사</Label>
                  <p className="text-body text-[var(--tv-muted)]">
                    전체 {formatInteger(externalSaveInspectionData.mode_count)}개 모드 · 정상 {formatInteger(externalSaveInspectionData.passed_mode_count)}개 · 문제 {formatInteger(externalSaveInspectionData.failed_mode_count)}개
                  </p>
                  <div className="divide-y divide-[color:var(--tv-border)] rounded-md border border-[color:var(--tv-border)]">
                    {externalSaveResults.map((result: any) => (
                      <div key={result.id} className="space-y-1 px-3 py-2">
                        <p className="text-body font-semibold text-[var(--tv-text)]">
                          {result.id} · {result.passed ? "정상" : "사용 불가"}
                        </p>
                        <p className="text-body break-all text-[var(--tv-muted)]">
                          대상 {formatInteger(result.requested_count)}건 · 저장 {formatInteger(result.existing_target_html_count)}건 · 미저장·재저장 필요 {formatInteger(result.download_required_target_html_count)}건 · 해시 불일치 {formatInteger(result.hash_mismatch_target_html_count)}건 · 기준 없음 {formatInteger(result.hash_unverified_target_html_count)}건
                        </p>
                        {!result.passed && result.error && (
                          <p className="text-body text-[var(--tv-warning-text)]">{result.error}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {isExternalCompressMode && compressionInspectionData && (
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">압축 파일 검사</Label>
                  <p className="text-body text-[var(--tv-muted)]">
                    전체 {formatInteger(compressionInspectionData.mode_count)}개 모드 · 정상 {formatInteger(compressionInspectionData.passed_mode_count)}개 · 문제 {formatInteger(compressionInspectionData.failed_mode_count)}개
                  </p>
                  <div className="divide-y divide-[color:var(--tv-border)] rounded-md border border-[color:var(--tv-border)]">
                    {compressionResults.map((result: any) => (
                      <div key={result.id} className="space-y-1 px-3 py-2">
                        <p className="text-body font-semibold text-[var(--tv-text)]">
                          {result.id} · {result.passed ? "정상" : "사용 불가"}
                        </p>
                        <p className="text-body break-all text-[var(--tv-muted)]">
                          {result.compressed_path || result.error || "검사 결과 경로가 없습니다."}
                        </p>
                        {!result.passed && result.error && (
                          <p className="text-body text-[var(--tv-warning-text)]">{result.error}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {isExternalCompressMode && !compressionInspectionData && (compressionInspectionError || isErrorStatus) && (
                <div className="text-body whitespace-pre-wrap text-[var(--tv-down-text)]">
                  {compressionInspectionError || status || "압축 파일 검사 오류를 확인할 수 없습니다."}
                </div>
              )}
              {lastInspectionCandidateCount > 0 && (
                <div className="space-y-3">
                  <div className="text-body rounded-md border border-[color:var(--tv-warning)] bg-[var(--tv-warning-soft)] p-3 text-[var(--tv-warning-text)]">
                    삭제 예정 파일 {formatInteger(lastInspectionCandidateCount)}개
                  </div>
                  {selectedFilterParentMode ? (
                    <p className="text-body text-[var(--tv-warning-text)]">
                      파생 필터는 상위 필터의 HTML을 공유하므로 이 화면에서 파일을 삭제할 수 없습니다.
                    </p>
                  ) : (
                    <>
                      <p className="text-body text-[var(--tv-warning-text)]">
                        삭제하려면 아래 입력란에 &quot;확인했습니다.&quot;를 정확히 입력하고 삭제 허가를 선택하세요.
                      </p>
                      <div className="space-y-2">
                        <Label htmlFor="deleteConfirmationText" className="dark:text-slate-300">확인 문구</Label>
                        <Input
                          id="deleteConfirmationText"
                          value={deleteConfirmationText}
                          onChange={(event) => setDeleteConfirmationText(event.target.value)}
                          placeholder="확인했습니다."
                          className={htmlControlClassName}
                        />
                      </div>
                      <div className="flex items-center space-x-2">
                        <Checkbox id="deleteConfirmed" checked={deleteConfirmed} onCheckedChange={(v) => setDeleteConfirmed(!!v)} className="border-[color:var(--tv-border)]" />
                        <Label htmlFor="deleteConfirmed" className="text-body cursor-pointer dark:text-slate-300">삭제 허가</Label>
                      </div>
                      {deleteConfirmed && deleteConfirmationText.trim() === "확인했습니다." && (
                        <Button
                          variant="outline"
                          className="h-10 w-full"
                          onClick={handleDeleteUnexpectedFiles}
                          disabled={isJobActive || inspectRunning}
                        >
                          <Trash2 className="mr-2 h-4 w-4" />
                          삭제 예정 파일 {formatInteger(lastInspectionCandidateCount)}개 삭제
                        </Button>
                      )}
                    </>
                  )}
                </div>
              )}
              {lastInspectionResult && (
                <div className="space-y-2 border-t border-[color:var(--tv-border)] pt-4">
                  <Label className="dark:text-slate-300">문제 파일</Label>
                  {visibleProblemFiles.length ? (
                    <div className="max-h-72 space-y-2 overflow-auto rounded-lg border border-[color:var(--tv-border)] bg-[var(--tv-control)] p-3">
                      {visibleProblemFiles.map((file: any) => (
                        <div key={file.path || file.name} className="text-caption break-all text-[var(--tv-text)]">
                          {file.name} ({file.reason})
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-body text-[var(--tv-muted)]">표시할 문제 파일이 없습니다.</p>
                  )}
                  {omittedProblemFileCount > 0 && (
                    <p className="text-caption text-[var(--tv-muted)]">
                      나머지 {formatInteger(omittedProblemFileCount)}개는 표시하지 않았습니다.
                    </p>
                  )}
                </div>
              )}
              {!isExternalCompressMode && !lastInspectionCandidateCount && !lastInspectionResult && isErrorStatus && (
                <div className="text-body whitespace-pre-wrap text-[var(--tv-down-text)]">{status || "오류 내용을 확인할 수 없습니다."}</div>
              )}
              {!isExternalCompressMode && !lastInspectionCandidateCount && !lastInspectionResult && !isErrorStatus && existingCheckError && (
                <div className="text-body rounded-md border border-[color:var(--tv-warning)] bg-[var(--tv-warning-soft)] p-3 text-[var(--tv-warning-text)]">
                  {existingCheckError}
                </div>
              )}
              {!isExternalCompressMode && !lastInspectionCandidateCount && !lastInspectionResult && !isErrorStatus && !existingCheckError && (
                <div className="text-body text-slate-500 dark:text-slate-400">알림 없음</div>
              )}
            </>
          }
          settingsTitle="시스템 설정"
          settingsContent={
            <div className="space-y-5">
              <WorkflowPathSettings id={`${variant}-separate-output-directory`} fields={activePathFields} onError={handlePathError} />
              {isExternalCompressMode ? (
                <div className="space-y-3">
                  <div className="border-b border-[color:var(--tv-border)] pb-2">
                    <p className="text-caption font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">압축 처리</p>
                  </div>
                  <HtmlWorkflowForm layout="inspector" fields={compressionSettingFields} />
                </div>
              ) : (
                <div className="space-y-5">
                  <div className="space-y-3">
                    <div className="border-b border-[color:var(--tv-border)] pb-2">
                      <p className="text-caption font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">요청 설정</p>
                    </div>
                    <HtmlWorkflowForm layout="inspector" fields={requestOptionFields} />
                  </div>
                  <div className="space-y-3">
                    <div className="border-b border-[color:var(--tv-border)] pb-2">
                      <p className="text-caption font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">실행 옵션</p>
                    </div>
                    <HtmlWorkflowForm layout="inspector" fields={executionOptionFields} />
                  </div>
                  <div className="space-y-3">
                    <div className="border-b border-[color:var(--tv-border)] pb-2">
                      <p className="text-caption font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">표시 옵션</p>
                    </div>
                    <HtmlWorkflowForm layout="inspector" fields={displayOptionFields} />
                  </div>
                  <div className="space-y-3">
                    <div className="border-b border-[color:var(--tv-border)] pb-2">
                      <p className="text-caption font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">테스트 옵션</p>
                    </div>
                    <HtmlWorkflowForm layout="inspector" fields={testOptionFields} />
                  </div>
                </div>
              )}
            </div>
          }
        />
      </div>
    </HtmlWorkflowPage>
  );
}
