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
import type { DisclosureConditionPreset } from "@/components/disclosures/DisclosureConditionFilterCard";
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
  const [existingCheckCompleted, setExistingCheckCompleted] = useState(false);
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
      setExistingData(null);
      setExistingCheckError("");
      setExistingCheckCompleted(false);
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
    setExistingCheckError("");
    setExistingCheckCompleted(false);
    setLastInspectionCandidateCount(0);
    setLastInspectionResult(null);
    setDeleteConfirmed(false);
    setDeleteConfirmationText("");
  }, [currentSourcePath, dataRoot, selectedFilterId, limit, problemFileLimit]);

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
    if (!selectedFilterPreset) {
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
      setExistingCheckError("");
      setExistingCheckCompleted(false);
      setDeleteConfirmed(false);
      setDeleteConfirmationText("");
      setIsErrorStatus(false);
      setStatus("폴더를 검사하는 중입니다...");
      const payload = buildCleanupPayload(true);
      const response = await fetch(variantConfig.checkExistingEndpoint, {
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
      setExistingData(data.has_existing ? data : null);
      setExistingCheckCompleted(true);
      const lines = [
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
  const integrityProblemCount = existingData
    ? Number(existingData.invalid_target_html_count || 0)
      + Number(existingData.hash_mismatch_target_html_count || 0)
      + Number(existingData.hash_unverified_target_html_count || 0)
      + Number(existingData.deletion_candidate_count || 0)
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
  // Files still to download are normal work, not an integrity problem, so they
  // are kept out of integrityProblemCount and only change the success wording.
  const pendingDownloadCount = existingData
    ? Number(
        existingData.download_required_target_html_count
          ?? existingData.missing_target_html_count
          ?? 0,
      )
    : 0;
  const integrityProblems = existingData ? ([
    [existingData.invalid_target_html_count, "깨진 파일", "건"],
    [existingData.hash_mismatch_target_html_count, "해시 불일치", "건"],
    [existingData.hash_unverified_target_html_count, "기준 해시 없음", "건"],
    [existingData.deletion_candidate_count, "대상 외 파일", "개"],
  ] as const)
    .filter(([count]) => Number(count || 0) > 0)
    .map(([count, label, unit]) => `${label} ${formatInteger(count)}${unit}`) : [];
  const inspectionState: SingleCheckDataIntegrityInspectionState = !hasInspectionInput
    ? "waiting"
    : inspectRunning
      ? "running"
      : existingCheckError || integrityProblemCount > 0
        ? "failed"
        : existingCheckCompleted
          ? "success"
          : "waiting";
  const inspectionCopy = {
    waiting: hasInspectionInput
      ? ["검사를 시작하지 않았습니다", "검사하기를 누르면 현재 경로의 저장 파일과 해시 구성을 확인합니다."]
      : ["데이터 경로를 선택하세요", "입력 경로와 결과 경로를 선택한 다음 검사하기를 누르세요."],
    ready: ["기존 원문 데이터 검사가 필요합니다", "현재 경로의 저장 파일과 해시 구성을 확인하세요."],
    running: ["기존 원문 데이터를 확인하고 있습니다", "현재 대상과 저장 파일을 비교하고 기준 해시를 확인합니다."],
    success: existingData
      ? ["기존 원문 데이터를 그대로 사용해도 됩니다", existingSummary]
      : ["기존 원문 데이터가 없습니다", "현재 대상과 충돌하는 기존 원문 파일이 없습니다."],
    failed: [
      "기존 원문 데이터에 문제가 있습니다",
      existingCheckError
        || (integrityProblems.length
          ? `${integrityProblems.join(" · ")} 때문에 기존 원문을 그대로 재사용할 수 없습니다.`
          : "검사 결과를 확인해 주세요."),
    ],
  }[inspectionState];
  const inspectionStepSummary = existingData
    ? `${existingData.output_directory} · 대상 ${formatInteger(existingData.requested_count)}건 중 ${formatInteger(existingData.existing_target_html_count)}건은 저장되어 있고 ${formatInteger(existingData.download_required_target_html_count ?? existingData.missing_target_html_count)}건은 새로 저장해야 합니다. 해시 불일치 ${formatInteger(existingData.hash_mismatch_target_html_count)}건, 기준 없음 ${formatInteger(existingData.hash_unverified_target_html_count)}건, 대상 외 파일 ${formatInteger(existingData.deletion_candidate_count)}개입니다.`
    : existingCheckCompleted
      ? "현재 대상과 충돌하는 기존 저장 파일이 없습니다."
      : "현재 대상과 저장 파일을 비교하고, 저장 파일의 기준 해시와 대상 외 파일을 함께 확인합니다.";

  // Completeness is reported as its own step: it is filled in by the same
  // inspection run above and never changes the card verdict.
  const inspectionRan = !!existingData || existingCheckCompleted;
  const pendingStepStatus = inspectRunning
    ? "running"
    : !inspectionRan
      ? "waiting"
      : pendingDownloadCount > 0
        ? "ready"
        : "complete";
  const pendingStepSummary = inspectRunning
    ? "새로 저장해야 할 원문 건수를 확인하고 있습니다."
    : !inspectionRan
      ? "위에서 검사하면 새로 저장해야 할 원문 건수를 함께 확인합니다."
      : pendingDownloadCount > 0
        ? `대상 ${formatInteger(existingData?.requested_count || 0)}건 중 ${formatInteger(pendingDownloadCount)}건이 아직 저장되지 않았습니다. 재다운로드를 누르면 확인된 기존 파일은 건너뛰고 미저장분만 내려받습니다.`
        : "이번 대상이 모두 저장되어 있어 새로 받을 원문이 없습니다.";
  const pendingStepLabel = inspectRunning
    ? "확인 중"
    : !inspectionRan
      ? "대기"
      : pendingDownloadCount > 0
        ? "다운로드 필요"
        : "정상";
  const inspectionExtraSteps: DataIntegrityInspectionStep[] = showSaveWorkflow ? [{
    key: "pending-download",
    title: "미저장 원문 다운로드",
    summary: pendingStepSummary,
    status: pendingStepStatus,
    statusLabel: pendingStepLabel,
    action: pendingDownloadCount > 0 ? {
      label: "재다운로드",
      onClick: handleRun,
      disabled: isJobActive
        || (skipExisting && (existingData?.hash_unverified_target_html_count || 0) > 0),
    } : undefined,
  }] : [];

  const activePathFields = isExternalCompressMode ? compressionFields : basePathFields;

  const existingDataInspectionCard = showSaveWorkflow ? (
    <SingleCheckDataIntegrityInspectionCard
      description="실행 전에 현재 대상과 저장 파일을 비교하고 기준 해시를 확인합니다."
      state={inspectionState}
      verdictTitle={inspectionCopy[0]}
      verdictDescription={inspectionCopy[1]}
      stepTitle="기존 원문 데이터 검사"
      stepSummary={inspectionStepSummary}
      extraSteps={inspectionExtraSteps}
      action={hasInspectionInput ? {
        label: inspectRunning ? "검사 중..." : "검사하기",
        onClick: handleInspectFolder,
        disabled: inspectRunning || isJobActive,
        loading: inspectRunning,
        showResultStatus: true,
      } : undefined}
    />
  ) : null;

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
          {variant === "internal" && existingDataInspectionCard}

          {/* LEGACY: 본문 데이터 경로 카드. 경로 입력은 우측 설정 패널(WorkflowPathSettings)로 옮겼다.
              <DataPathCard onError={handlePathError} fields={activePathFields} /> */}

          {variant === "external" && (
            <WorkflowModeSwitch
              ariaLabel="외부 HTML 작업 모드"
              value={externalTaskMode}
              options={EXTERNAL_TASK_MODE_OPTIONS}
              onValueChange={setExternalTaskMode}
              testId="external-html-mode-control"
            />
          )}

          <Card className="border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
            <CardHeader>
              <CardTitle className="dark:text-white">조건검색 필터</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2">
              <Label htmlFor={`${variant}-filter-preset`} className="dark:text-slate-300">조건검색 필터</Label>
              <select
                id={`${variant}-filter-preset`}
                value={selectedFilterId}
                onChange={(event) => setSelectedFilterId(event.target.value)}
                className={`${htmlControlClassName} w-full font-semibold`}
              >
                {filterPresets.map((preset) => (
                  <option key={presetIdentity(preset)} value={presetIdentity(preset)}>
                    {presetLabel(preset)}
                  </option>
                ))}
              </select>
            </CardContent>
          </Card>

          {variant === "external" && existingDataInspectionCard}

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
                    disabled={isJobActive || (skipExisting && (existingData?.hash_unverified_target_html_count || 0) > 0)}
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
          notificationActive={isErrorStatus || !!existingCheckError || lastInspectionCandidateCount > 0 || !!lastInspectionResult}
          notificationTone={isErrorStatus ? "error" : existingCheckError || integrityProblemCount > 0 ? "warning" : "success"}
          notificationDismissible={false}
          notificationContent={
            <>
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
              {!lastInspectionCandidateCount && !lastInspectionResult && isErrorStatus && (
                <div className="text-body whitespace-pre-wrap text-[var(--tv-down-text)]">{status || "오류 내용을 확인할 수 없습니다."}</div>
              )}
              {!lastInspectionCandidateCount && !lastInspectionResult && !isErrorStatus && existingCheckError && (
                <div className="text-body rounded-md border border-[color:var(--tv-warning)] bg-[var(--tv-warning-soft)] p-3 text-[var(--tv-warning-text)]">
                  {existingCheckError}
                </div>
              )}
              {!lastInspectionCandidateCount && !lastInspectionResult && !isErrorStatus && !existingCheckError && (
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
