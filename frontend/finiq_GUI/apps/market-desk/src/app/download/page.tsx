"use client"

import { useState, useEffect, useCallback, useRef, type CSSProperties } from "react";
import { Activity, Bell, X, Play, Search, Loader2, Trash2, Settings } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { Checkbox } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import { DataPathCard, DATA_PATH_LABELS } from "@/components/data-path/DataPathCard";
import { JobStatusLogger, PageLoadingSpinner, useActionDockFollow } from "@finiq/web-app/status";
import { htmlControlClassName, htmlSelectContentClassName } from "@/components/html-workflow/HtmlWorkflowTemplate";
import { cancelDownload, fetchDownloadOptions, inspectDownloadFolder, previewDownload, startDownload } from "@/features/download/api";
import type { DownloadExistingPayload, DownloadExistingResponse, DownloadOptions, DownloadPayload, DownloadSavedFilters } from "@/features/download/types";
import { UI_TEXT } from "@/config/uiText";
import { formatInteger } from "@/lib/format";
import {
  DisclosureSearchConditionCard,
  DisclosureTypeSelectionCard,
} from "@/components/disclosures/DisclosureSearchSettingsCards";
import { DisclosureSeparateOutputDirectorySetting } from "@/components/disclosures/DisclosureSeparateOutputDirectorySetting";
import {
  type DataIntegrityInspectionStep,
  type DataIntegrityInspectionVerdict,
} from "@/components/data-integrity/DataIntegrityInspectionPanel";
import { DataIntegrityInspectionCard } from "@/components/data-integrity/DataIntegrityInspectionCard";

const formatDateToISO = (date: Date) => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
};

export const areDisclosureGroupsMatching = (g1: Record<string, string[]>, g2: Record<string, string[]>) => {
  const canonicalize = (groups: Record<string, string[]>) => {
    const obj: Record<string, string[]> = {};
    for (const key of Object.keys(groups).sort()) {
      const vals = groups[key] || [];
      if (vals.length > 0) {
        obj[key] = [...vals].sort();
      }
    }
    return JSON.stringify(obj);
  };
  return canonicalize(g1) === canonicalize(g2);
};

const areFiltersMatching = (
  current: {
    companyName: string;
    submitterName: string;
    marketLabel: string;
    securitiesLabel: string;
    selectedDisclosures: Record<string, string[]>;
    lastReportOnly: boolean;
  },
  saved: DownloadSavedFilters | null | undefined
) => {
  if (!saved) return true;
  if (current.companyName.trim() !== (saved.company_name || "").trim()) return false;
  if (current.submitterName.trim() !== (saved.submitter_name || "").trim()) return false;
  if (current.marketLabel !== (saved.market_label || "전체")) return false;
  if (current.securitiesLabel !== (saved.securities_label || "전체")) return false;
  if (current.lastReportOnly !== !!saved.last_report_only) return false;
  if (!areDisclosureGroupsMatching(current.selectedDisclosures, saved.disclosure_type_groups || {})) {
    return false;
  }
  return true;
};

type DownloadInspectionContext = {
  jobId: string;
  key: string;
  payload: DownloadPayload;
  runTriggered: boolean;
};

const DOWNLOAD_INSPECTION_STORAGE_KEY = "finiq.downloadInspectionContext:/download";
const EXISTING_DATA_SUCCESS_LABEL = "정상";

const readStoredInspectionContext = (): DownloadInspectionContext | null => {
  if (typeof window === "undefined") return null;
  try {
    const stored = window.sessionStorage.getItem(DOWNLOAD_INSPECTION_STORAGE_KEY);
    return stored ? JSON.parse(stored) as DownloadInspectionContext : null;
  } catch {
    return null;
  }
};

const checkExistingPayloadKey = (payload: DownloadExistingPayload) => JSON.stringify({
  ...payload,
  disclosure_type_groups: Object.fromEntries(
    Object.entries(payload.disclosure_type_groups)
      .filter(([, values]) => values.length > 0)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, values]) => [key, [...values].sort()])
  ),
});

const existingPayloadFromDownloadPayload = (payload: DownloadPayload) => ({
  output_directory: payload.output_directory,
  start_date: payload.start_date,
  end_date: payload.end_date,
  company_name: payload.company_name,
  submitter_name: payload.submitter_name,
  market_label: payload.market_label,
  securities_label: payload.securities_label,
  page_size: payload.page_size,
  last_report_only: payload.last_report_only,
  disclosure_type_groups: payload.disclosure_type_groups,
});

export default function DownloadPage() {
  const actionDockRef = useActionDockFollow<HTMLDivElement>();
  const [options, setOptions] = useState<DownloadOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [previewResult, setPreviewResult] = useState<any>(null);
  const [notificationPanelOpen, setNotificationPanelOpen] = useState(false);
  const [downloadPanelOpen, setDownloadPanelOpen] = useState(false);
  const [settingsPanelOpen, setSettingsPanelOpen] = useState(false);
  const [runStarting, setRunStarting] = useState(false);
  const activeInspectionRef = useRef<DownloadInspectionContext | null>(readStoredInspectionContext());
  const cleanupCandidatePayloadRef = useRef<DownloadPayload | null>(null);
  const [cleanupCandidateKey, setCleanupCandidateKey] = useState<string | null>(null);
  const [lastInspectionCandidateCount, setLastInspectionCandidateCount] = useState(0);
  const [lastInspectedExistingKey, setLastInspectedExistingKey] = useState<string | null>(null);
  const [deleteConfirmed, setDeleteConfirmed] = useState(false);
  const [deleteConfirmationText, setDeleteConfirmationText] = useState("");

  const clearActiveInspection = useCallback((expected?: DownloadInspectionContext | null) => {
    if (expected && activeInspectionRef.current !== expected) return;
    activeInspectionRef.current = null;
    try {
      window.sessionStorage.removeItem(DOWNLOAD_INSPECTION_STORAGE_KEY);
    } catch {
      // The in-memory context is still cleared when storage is unavailable.
    }
  }, []);

  const clearCleanupCandidates = useCallback(() => {
    cleanupCandidatePayloadRef.current = null;
    setCleanupCandidateKey(null);
    setLastInspectionCandidateCount(0);
    setDeleteConfirmed(false);
    setDeleteConfirmationText("");
  }, []);

  const {
    output_root: dataRoot,
    download_output_directory: separateOutputDirectory,
    disclosure_separate_output_directory: useSeparateOutputDirectory,
    parallel_worker_count: parallelWorkerCount,
    job_retention_minutes: jobRetentionMinutes,
    fetchSettings,
    saveSetting,
  } = useSettingsStore();
  const outputDirectory = useSeparateOutputDirectory
    ? separateOutputDirectory
    : dataRoot
      ? `${dataRoot.replace(/\/$/, "")}/01-list`
      : "";

  const { status, isErrorStatus, activeJobId, isPollingRestored, startPolling, setStatus, setIsErrorStatus } = useJobPolling({
    pollingEndpoint: "/api/download/jobs/{jobId}",
    onSuccess: async (data, jobId) => {
      if (data && data.format === "kind_download_folder_cleanup_v1") {
        const completedInspection = activeInspectionRef.current;
        if (!completedInspection || completedInspection.jobId !== jobId) {
          throw new Error("완료된 검사 작업의 실행 입력을 확인할 수 없습니다. 같은 조건으로 다시 검사해 주세요.");
        }
        const candidateCount = data.dry_run ? (data.deletion_candidate_count || 0) : 0;
        const completedInspectionKey = completedInspection.key;
        const completedPayload = completedInspection.payload;
        const verified = data.existing_downloads as DownloadExistingResponse | null | undefined;
        if (verified) acceptExistingInspectionResult(verified);
        const hasVerificationFailure = !verified || (verified.ranges?.some(
          (range) => range.status === "stale"
            || range.filters_match === false
            || range.metadata_status === "mismatch"
        ) ?? false);
        if (verified) {
          setLastInspectedExistingKey(completedInspectionKey);
        }
        setLastInspectionCandidateCount(candidateCount);
        if (candidateCount > 0 && data.dry_run) {
          cleanupCandidatePayloadRef.current = completedPayload;
          setCleanupCandidateKey(completedInspectionKey);
        } else {
          clearCleanupCandidates();
        }
        setResult(data);
        const hasInspectionFailure = candidateCount > 0 || hasVerificationFailure;
        setStatus(buildInspectionStatus(data, !data.dry_run, hasInspectionFailure));
        setIsErrorStatus(hasInspectionFailure);

        if (completedInspection.runTriggered) {
          if (hasInspectionFailure) {
            clearActiveInspection(completedInspection);
            setNotificationPanelOpen(true);
            setDownloadPanelOpen(false);
            setSettingsPanelOpen(false);
          } else {
            try {
              setStatus("다운로드 작업을 시작하는 중...");
              await startDownloadJob(completedPayload, jobId);
            } catch (err: any) {
              setStatus(err.message);
              setIsErrorStatus(true);
            } finally {
              clearActiveInspection(completedInspection);
            }
          }
        } else {
          clearActiveInspection(completedInspection);
          setNotificationPanelOpen(false);
          setDownloadPanelOpen(true);
          setSettingsPanelOpen(false);
        }
      } else {
        setResult(data);
      }
    },
    onError: (error, jobId) => {
      const activeInspection = activeInspectionRef.current;
      if (activeInspection?.jobId === jobId) {
        const currentKey = checkExistingPayloadKey(
          existingPayloadFromDownloadPayload(buildPayload()),
        );
        if (activeInspection.key === currentKey) {
          setExistingMetadataError(error.message);
        }
        clearActiveInspection(activeInspection);
      }
    },
    onCancel: (jobId) => {
      const activeInspection = activeInspectionRef.current;
      if (activeInspection?.jobId === jobId) {
        clearActiveInspection(activeInspection);
      }
    },
  });

  // Form State
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [submitterName, setSubmitterName] = useState("");
  const [marketLabel, setMarketLabel] = useState("전체");
  const [securitiesLabel, setSecuritiesLabel] = useState("전체");
  const [pageSize, setPageSize] = useState("100");
  const [waitSeconds, setWaitSeconds] = useState("1");
  const [timeout, setTimeoutVal] = useState("20");
  const [workerCount, setWorkerCount] = useState("1");
  const [parallelStrategy, setParallelStrategy] = useState<"years" | "pages">("years");
  const [jobRetentionInput, setJobRetentionInput] = useState("60");
  const [startPage, setStartPage] = useState("1");
  const [endPage, setEndPage] = useState("");
  const [lastReportOnly, setLastReportOnly] = useState(false);
  const [logLimit, setLogLimit] = useState("20");
  const [selectedDisclosures, setSelectedDisclosures] = useState<Record<string, string[]>>({});
  const [inspectRunning, setInspectRunning] = useState(false);
  const [existingInspectionResult, setExistingInspectionResult] = useState<DownloadExistingResponse | null>(null);
  const [existingMetadataError, setExistingMetadataError] = useState<string | null>(null);
  const acceptExistingInspectionResult = useCallback((nextResult: DownloadExistingResponse) => {
    setExistingInspectionResult(nextResult);
    setExistingMetadataError(null);
  }, []);
  const clearExistingInspection = useCallback(() => {
    setExistingInspectionResult(null);
    setExistingMetadataError(null);
  }, []);
  const handlePathError = useCallback((message: string) => {
    setStatus(message);
    setIsErrorStatus(true);
  }, [setIsErrorStatus, setStatus]);
  const existingData = existingInspectionResult?.has_existing
    ? existingInspectionResult
    : null;

  useEffect(() => {
    setJobRetentionInput(String(jobRetentionMinutes || 60));
  }, [jobRetentionMinutes]);

  const saveJobRetentionMinutes = async () => {
    const parsed = Number(jobRetentionInput);
    const normalized = Number.isInteger(parsed) && parsed >= 1
      ? parsed
      : jobRetentionMinutes || 60;
    setJobRetentionInput(String(normalized));
    await saveSetting("job_retention_minutes", normalized);
  };

  const mismatchedFilterRanges = existingData?.ranges?.filter(
    (range) => range.filters_match === false || range.metadata_status === "mismatch"
  ) || [];
  const filtersMatch = mismatchedFilterRanges.length === 0 && areFiltersMatching(
    {
      companyName,
      submitterName,
      marketLabel,
      securitiesLabel,
      selectedDisclosures,
      lastReportOnly,
    },
    existingData?.saved_filters
  );

  const handleApplySavedFilters = () => {
    const saved = existingData?.saved_filters;
    if (!saved) return;
    setCompanyName(saved.company_name || "");
    setSubmitterName(saved.submitter_name || "");
    setMarketLabel(saved.market_label || "전체");
    setSecuritiesLabel(saved.securities_label || "전체");
    setSelectedDisclosures(saved.disclosure_type_groups || {});
    setLastReportOnly(!!saved.last_report_only);
    setStatus("기존 메타데이터 기준으로 검색 설정을 맞췄습니다.");
    setIsErrorStatus(false);
  };

  const fetchOptions = useCallback(async () => {
    try {
      const [data, config] = await Promise.all([fetchDownloadOptions(), fetchSettings()]);
      setOptions(data);
      const workerCount = Number(config?.parallel_worker_count);
      if (!Number.isInteger(workerCount) || workerCount < 1) {
        throw new Error("parallel_worker_count must be a positive integer");
      }
      setWorkerCount(String(workerCount));

      if (!useSettingsStore.getState().download_output_directory && data.default_output_directory) {
        saveSetting("download_output_directory", data.default_output_directory);
      }

      const today = new Date();
      const yesterday = new Date(today);
      yesterday.setDate(today.getDate() - 1);
      
      const start = new Date(yesterday);
      start.setDate(yesterday.getDate() - 30);
      
      setStartDate(formatDateToISO(start));
      setEndDate(formatDateToISO(yesterday));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [fetchSettings, saveSetting]);

  useEffect(() => {
    fetchOptions();
  }, [fetchOptions]);

  useEffect(() => {
    const activeInspection = activeInspectionRef.current;
    if (isPollingRestored && !loading && !activeJobId && activeInspection?.jobId) {
      clearActiveInspection(activeInspection);
    }
  }, [activeJobId, clearActiveInspection, isPollingRestored, loading]);

  useEffect(() => {
    clearExistingInspection();
    clearCleanupCandidates();
    setLastInspectedExistingKey(null);
  }, [
    clearCleanupCandidates,
    clearExistingInspection,
    companyName,
    endDate,
    lastReportOnly,
    marketLabel,
    outputDirectory,
    pageSize,
    securitiesLabel,
    selectedDisclosures,
    startDate,
    submitterName,
  ]);

  const buildPayload = (): DownloadPayload => ({
    data_root: dataRoot,
    separate_output_directory: useSeparateOutputDirectory,
    mode: "yearly",
    output_directory: outputDirectory,
    start_date: startDate,
    end_date: endDate,
    company_name: companyName,
    submitter_name: submitterName,
    market_label: marketLabel,
    securities_label: securitiesLabel,
    page_size: Number(pageSize),
    wait_seconds: Number(waitSeconds),
    timeout: Number(timeout),
    worker_count: Number(workerCount),
    parallel_strategy: parallelStrategy,
    log_limit: Number(logLimit),
    start_page: Number(startPage),
    end_page: endPage ? Number(endPage) : null,
    last_report_only: lastReportOnly,
    disclosure_type_groups: selectedDisclosures,
  });

  const handlePreview = async () => {
    try {
      setPreviewResult(null);
      setIsErrorStatus(false);
      setStatus("미리보기 생성 중...");
      const data = await previewDownload(buildPayload());
      setPreviewResult(data);
      setResult(null);
      setStatus("미리보기 완료");
      setNotificationPanelOpen(true);
      setDownloadPanelOpen(false);
      setSettingsPanelOpen(false);
    } catch (err: any) {
      setPreviewResult(null);
      setStatus(err.message);
      setIsErrorStatus(true);
      setNotificationPanelOpen(true);
      setDownloadPanelOpen(false);
      setSettingsPanelOpen(false);
    }
  };

  const startDownloadJob = async (payload: DownloadPayload, inspectionJobId?: string) => {
    const data = await startDownload(payload, inspectionJobId);
    setPreviewResult(null);
    setResult(null);
    setDownloadPanelOpen(true);
    setNotificationPanelOpen(false);
    setSettingsPanelOpen(false);
    startPolling(data.job_id);
  };

  const handleCancelDownload = async () => {
    if (!activeJobId) return;
    try {
      setStatus("다운로드 중단을 요청했습니다. 진행 중인 요청이 끝나면 멈춥니다.");
      await cancelDownload(activeJobId);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const inspectExistingFiles = async (
    dryRun: boolean,
    customPayload?: DownloadPayload,
    runTriggered = false,
  ) => {
    const basePayload = customPayload || buildPayload();
    const pendingInspection: DownloadInspectionContext = {
      jobId: "",
      key: checkExistingPayloadKey(existingPayloadFromDownloadPayload(basePayload)),
      payload: basePayload,
      runTriggered,
    };
    activeInspectionRef.current = pendingInspection;
    if (dryRun) {
      clearCleanupCandidates();
    }
    try {
      const data = await inspectDownloadFolder({
        ...basePayload,
        dry_run: dryRun,
        delete_confirmed: deleteConfirmed,
        delete_confirmation_text: deleteConfirmationText,
      });
      const activeInspection = { ...pendingInspection, jobId: data.job_id };
      activeInspectionRef.current = activeInspection;
      try {
        window.sessionStorage.setItem(
          DOWNLOAD_INSPECTION_STORAGE_KEY,
          JSON.stringify(activeInspection),
        );
      } catch {
        // Polling still works during the current mount when storage is unavailable.
      }
      if (!dryRun) {
        clearCleanupCandidates();
      }
      startPolling(data.job_id);
      return data;
    } catch (inspectionError) {
      clearActiveInspection(pendingInspection);
      throw inspectionError;
    }
  };

  const buildInspectionStatus = (data: any, deleted: boolean, failed: boolean) => {
    const files = Array.isArray(deleted ? data.deleted_files : data.deletion_candidates)
      ? (deleted ? data.deleted_files : data.deletion_candidates)
      : [];
    const lines = [
      failed ? "사용 불가" : deleted ? "파일 삭제 완료" : EXISTING_DATA_SUCCESS_LABEL,
      `대상 페이지: ${formatInteger(data.requested_count || data.summary?.total)}`,
      `연도별 분할: ${data.split_by_year ? "On" : "Off"}`,
      `${deleted ? "삭제 파일" : "삭제 예정 파일"}: ${formatInteger(deleted ? data.deleted_count : data.deletion_candidate_count)}`,
      `추가 다운로드 필요: ${formatInteger(data.download_needed_count)}건`,
      `최신 상태: 성공 ${formatInteger(data.summary?.success)}/${formatInteger(data.summary?.total)}건`,
      `데이터 경로: ${data.output_directory || ""}`,
    ];
    if (files.length) {
      lines.push("", deleted ? "삭제한 파일" : "삭제 예정 파일", ...files.map((file: any) => `- ${file.name} (${file.reason})`));
    }
    return lines.join("\n");
  };

  const handleInspectFolder = async () => {
    if (!outputDirectory) {
      setStatus("데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      setInspectRunning(true);
      setIsErrorStatus(false);
      setStatus("기존 데이터 검사를 시작하는 중...");
      setPreviewResult(null);
      setResult(null);
      setDownloadPanelOpen(true);
      setNotificationPanelOpen(false);
      setSettingsPanelOpen(false);
      await inspectExistingFiles(true);
    } catch (err: any) {
      clearActiveInspection();
      setExistingMetadataError(err.message);
      setStatus(err.message);
      setIsErrorStatus(true);
      setNotificationPanelOpen(false);
      setDownloadPanelOpen(true);
      setSettingsPanelOpen(false);
    } finally {
      setInspectRunning(false);
    }
  };

  const handleRun = async () => {
    if (runStarting) return;
    try {
      setRunStarting(true);
      if (existingMetadataError) {
        throw new Error(existingMetadataError);
      }
      if (existingData?.saved_filters && !filtersMatch) {
        throw new Error("현재 입력된 검색 필터가 기존 다운로드 폴더의 메타데이터와 다릅니다. 필터를 먼저 일치시켜 주세요.");
      }
      const payload = buildPayload();
      setIsErrorStatus(false);
      setPreviewResult(null);
      setStatus("기존 다운로드 파일을 검사하는 중...");
      await inspectExistingFiles(true, payload, true);
      setDownloadPanelOpen(true);
      setNotificationPanelOpen(false);
      setSettingsPanelOpen(false);
    } catch (err: any) {
      clearActiveInspection();
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setRunStarting(false);
    }
  };

  const handleDeleteUnexpectedFiles = async () => {
    try {
      if (!deleteConfirmed || deleteConfirmationText.trim() !== "확인했습니다.") {
        setStatus('삭제하려면 삭제 허가를 체크하고 "확인했습니다."를 입력하세요.');
        setIsErrorStatus(true);
        setNotificationPanelOpen(true);
        setDownloadPanelOpen(false);
        setSettingsPanelOpen(false);
        return;
      }
      setInspectRunning(true);
      setIsErrorStatus(false);
      setStatus("확인된 기존 파일을 삭제하는 중...");
      setPreviewResult(null);
      const currentKey = checkExistingPayloadKey(existingPayloadFromDownloadPayload(buildPayload()));
      const payload = cleanupCandidatePayloadRef.current;
      if (!payload || cleanupCandidateKey !== currentKey) {
        throw new Error("현재 조건과 일치하는 삭제 예정 파일 검사가 없습니다. 같은 조건으로 다시 검사해 주세요.");
      }
      await inspectExistingFiles(false, payload);
      setDeleteConfirmed(false);
      setDeleteConfirmationText("");
      setDownloadPanelOpen(true);
      setNotificationPanelOpen(false);
      setSettingsPanelOpen(false);
    } catch (err: any) {
      clearActiveInspection();
      setStatus(err.message);
      setIsErrorStatus(true);
      setNotificationPanelOpen(true);
      setDownloadPanelOpen(false);
      setSettingsPanelOpen(false);
    } finally {
      setInspectRunning(false);
    }
  };

  if (loading) {
    return <PageLoadingSpinner message="옵션을 불러오는 중입니다..." />;
  }

  const currentExistingKey = outputDirectory
    ? checkExistingPayloadKey(existingPayloadFromDownloadPayload(buildPayload()))
    : "";
  const hasCompletedCurrentInspection = currentExistingKey === lastInspectedExistingKey;
  const isCurrentInspectionRunning = inspectRunning || activeInspectionRef.current?.key === currentExistingKey;
  const currentInspectionCandidateCount = cleanupCandidateKey === currentExistingKey
    ? lastInspectionCandidateCount
    : 0;
  const inspectionRanges = existingData?.ranges || [];
  const staleRanges = inspectionRanges.filter((range) => range.status === "stale");
  const hasInspectionFailureNotification = hasCompletedCurrentInspection && staleRanges.length > 0;
  const hasSuccessfulInspectionNotification = hasCompletedCurrentInspection
    && result?.format === "kind_download_folder_cleanup_v1"
    && currentInspectionCandidateCount === 0
    && staleRanges.length === 0
    && filtersMatch
    && !isErrorStatus
    && !existingMetadataError;
  const hasWarningNotification = currentInspectionCandidateCount > 0
    || hasInspectionFailureNotification
    || isErrorStatus
    || !!existingMetadataError
    || !!previewResult;
  const notificationTone = isErrorStatus || !!existingMetadataError
    ? "error"
    : currentInspectionCandidateCount > 0 || hasInspectionFailureNotification
      ? "warning"
      : hasSuccessfulInspectionNotification
        ? "success"
        : "neutral";
  const dockToneStyle = (tone: "neutral" | "success" | "warning" | "error", selected: boolean): CSSProperties | undefined => {
    if (tone === "neutral") return undefined;
    const tokens = tone === "error"
      ? ["--tv-down", "--tv-down-soft", "--tv-down-text"]
      : tone === "warning"
        ? ["--tv-warning", "--tv-warning-soft", "--tv-warning-text"]
        : ["--tv-up", "--tv-up-soft", "--tv-up-text"];
    return {
      borderColor: `var(${tokens[0]})`,
      backgroundColor: `var(${tokens[1]})`,
      color: `var(${tokens[2]})`,
      outline: selected ? `2px solid var(${tokens[0]})` : undefined,
      outlineOffset: selected ? "1px" : undefined,
    };
  };
  const notificationDotClass = notificationTone === "error"
    ? "bg-[var(--tv-down)]"
    : notificationTone === "warning"
      ? "bg-[var(--tv-warning)]"
      : notificationTone === "success"
        ? "bg-[var(--tv-up)]"
        : "bg-[var(--tv-muted)]";
  const inspectionCandidates = hasCompletedCurrentInspection
    && result?.format === "kind_download_folder_cleanup_v1"
    && result?.dry_run === true
    ? (Array.isArray(result.deletion_candidates) ? result.deletion_candidates : [])
    : [];
  const savedFilters = existingData?.saved_filters;
  const filterDifferences: { label: string; saved: string; current: string }[] = [];

  if (savedFilters) {
    if (savedFilters.company_name.trim() !== companyName.trim()) {
      filterDifferences.push({ label: "회사명", saved: savedFilters.company_name || "전체", current: companyName || "전체" });
    }
    if (savedFilters.submitter_name.trim() !== submitterName.trim()) {
      filterDifferences.push({ label: "제출인", saved: savedFilters.submitter_name || "전체", current: submitterName || "전체" });
    }
    if (savedFilters.market_label !== marketLabel) {
      filterDifferences.push({ label: "시장", saved: savedFilters.market_label, current: marketLabel });
    }
    if (savedFilters.securities_label !== securitiesLabel) {
      filterDifferences.push({ label: "증권종류", saved: savedFilters.securities_label, current: securitiesLabel });
    }
    if (!!savedFilters.last_report_only !== lastReportOnly) {
      filterDifferences.push({ label: "최종보고서만", saved: savedFilters.last_report_only ? "예" : "아니오", current: lastReportOnly ? "예" : "아니오" });
    }
    if (!areDisclosureGroupsMatching(selectedDisclosures, savedFilters.disclosure_type_groups || {})) {
      filterDifferences.push({ label: "공시 종류", saved: "저장된 선택", current: "현재 선택" });
    }
  }

  let inspectionVerdict: DataIntegrityInspectionVerdict;
  if (!outputDirectory) {
    inspectionVerdict = {
      label: "대기",
      title: "데이터 경로를 선택해 주세요",
      description: "경로를 선택하고 검사하기를 누르면 기존 데이터와 메타데이터를 확인합니다.",
      tone: "neutral",
    };
  } else if (isCurrentInspectionRunning) {
    inspectionVerdict = {
      label: "검사 중",
      title: "기존 데이터를 검사하고 있습니다",
      description: outputDirectory,
      tone: "neutral",
    };
  } else if (existingMetadataError) {
    inspectionVerdict = {
      label: "사용 불가",
      title: "메타데이터를 확인할 수 없습니다",
      description: existingMetadataError,
      tone: "error",
    };
  } else if (!hasCompletedCurrentInspection) {
    inspectionVerdict = {
      label: "대기",
      title: "검사를 시작하지 않았습니다",
      description: "검사하기를 누르면 저장된 메타데이터와 현재 설정, 파일 구성, KIND 건수를 차례로 확인합니다.",
      tone: "neutral",
    };
  } else if (!existingData) {
    inspectionVerdict = {
      label: EXISTING_DATA_SUCCESS_LABEL,
      title: "기존 데이터가 없습니다",
      description: "현재 조건으로 새 다운로드를 시작할 수 있습니다.",
      tone: "success",
    };
  } else if (!filtersMatch) {
    inspectionVerdict = {
      label: "사용 불가",
      title: "저장된 설정과 현재 조건이 다릅니다",
      description: "설정을 맞추기 전에는 기존 데이터에 이어서 저장할 수 없습니다.",
      tone: "error",
    };
  } else if (inspectionCandidates.length > 0 || staleRanges.length > 0) {
    inspectionVerdict = {
      label: "사용 불가",
      title: "기존 데이터에 문제가 있습니다",
      description: "아래 실패 단계의 원인과 조치를 확인해 주세요.",
      tone: "error",
    };
  } else {
    inspectionVerdict = {
      label: EXISTING_DATA_SUCCESS_LABEL,
      title: "기존 데이터에 이어서 저장해도 됩니다",
      description: `${existingData.earliest_date ?? "-"} ~ ${existingData.latest_date ?? "-"} · ${formatInteger(inspectionRanges.length)}개 범위 확인`,
      tone: "success",
    };
  }
  const inspectionResultStatus = inspectionVerdict.tone === "success"
    ? { status: "complete", label: "정상" } as const
    : inspectionVerdict.tone === "error"
      ? { status: "failed", label: "사용 불가" } as const
      : undefined;

  const inspectionSteps: DataIntegrityInspectionStep[] = [
    {
      key: "metadata",
      title: "메타데이터 읽기",
      summary: existingData
        ? `${formatInteger(inspectionRanges.length)}개 저장 범위의 메타데이터를 확인했습니다.`
        : existingMetadataError
          ? "저장된 메타데이터를 읽지 못했습니다."
          : hasCompletedCurrentInspection
            ? "비교할 기존 데이터가 없습니다."
            : "검사하기를 누르면 저장된 메타데이터를 확인합니다.",
      status: existingMetadataError
        ? "failed"
        : isCurrentInspectionRunning
          ? "running"
          : hasCompletedCurrentInspection
            ? "complete"
            : "waiting",
      statusLabel: existingMetadataError
        ? "실패"
        : isCurrentInspectionRunning
          ? "검사 중"
          : hasCompletedCurrentInspection
            ? existingData ? EXISTING_DATA_SUCCESS_LABEL : "대상 없음"
            : "대기",
      detail: existingMetadataError ? (
        <p className="text-[13px] leading-5 text-[var(--tv-down-text)]">{existingMetadataError}</p>
      ) : undefined,
      action: outputDirectory ? {
        label: isCurrentInspectionRunning ? "검사 중..." : "검사하기",
        onClick: handleInspectFolder,
        disabled: isCurrentInspectionRunning || !!activeJobId || runStarting,
        loading: isCurrentInspectionRunning,
        showResultStatus: true,
        resultStatus: inspectionResultStatus,
      } : undefined,
    },
    {
      key: "settings",
      title: "현재 설정과 비교",
      summary: !hasCompletedCurrentInspection
        ? "메타데이터를 읽은 뒤 현재 설정과 비교합니다."
        : !existingData
          ? "비교할 저장 설정이 없습니다."
        : filtersMatch
          ? "저장된 검색 설정과 현재 조건이 같습니다."
          : filterDifferences.length > 0
            ? `${formatInteger(filterDifferences.length)}개 설정이 현재 조건과 다릅니다.`
            : `${formatInteger(mismatchedFilterRanges.length)}개 저장 범위의 설정이 현재 조건과 다릅니다.`,
      status: existingMetadataError || !hasCompletedCurrentInspection
        ? "waiting"
        : !existingData || filtersMatch ? "complete" : "failed",
      statusLabel: existingMetadataError || !hasCompletedCurrentInspection
        ? "대기"
        : !existingData ? "대상 없음" : filtersMatch ? EXISTING_DATA_SUCCESS_LABEL : "불일치",
      detail: !filtersMatch && savedFilters ? (
        <div className="space-y-3">
          {filterDifferences.length > 0 && (
            <div className="overflow-x-auto rounded-md border border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
              <table className="w-full min-w-[32rem] text-left text-[13px] leading-5">
                <thead className="border-b border-[color:var(--tv-border)] text-[var(--tv-muted)]">
                  <tr>
                    <th className="px-3 py-2 font-semibold">항목</th>
                    <th className="px-3 py-2 font-semibold">저장된 설정</th>
                    <th className="px-3 py-2 font-semibold">현재 설정</th>
                  </tr>
                </thead>
                <tbody>
                  {filterDifferences.map((difference) => (
                    <tr key={difference.label} className="border-b border-[color:var(--tv-border)] last:border-b-0">
                      <th className="px-3 py-2 font-semibold text-[var(--tv-text)]">{difference.label}</th>
                      <td className="px-3 py-2 text-[var(--tv-down-text)]">{difference.saved}</td>
                      <td className="px-3 py-2 text-[var(--tv-text)]">{difference.current}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {mismatchedFilterRanges.length > 0 && (
            <ul className="max-h-48 space-y-2 overflow-y-auto text-[13px] leading-5 text-[var(--tv-down-text)]">
              {mismatchedFilterRanges.map((range) => (
                <li key={range.folder_path} className="rounded-md border border-[color:var(--tv-down)] bg-[var(--tv-down-soft)] px-3 py-2">
                  <span className="font-semibold">{range.folder_name}</span> · {range.start_date ?? "-"} ~ {range.end_date ?? "-"}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : undefined,
      action: !filtersMatch && savedFilters && filterDifferences.length > 0 ? {
        label: "저장된 설정 적용",
        onClick: handleApplySavedFilters,
      } : undefined,
    },
    {
      key: "files",
      title: "저장 파일 구성 검사",
      summary: !hasCompletedCurrentInspection
        ? "검사하기를 누르면 페이지 번호가 빠짐없이 이어지는지, 파일 구성이 올바른지 확인합니다."
        : !existingData
          ? "검사할 기존 파일이 없습니다."
        : !filtersMatch
          ? "설정 불일치를 먼저 해결해야 합니다."
          : isCurrentInspectionRunning
            ? "페이지 번호와 파일 구성을 검사하고 있습니다."
          : !hasCompletedCurrentInspection
            ? "페이지 번호의 연속성과 파일 구성을 검사할 준비가 됐습니다."
            : inspectionCandidates.length > 0
              ? `${formatInteger(inspectionCandidates.length)}개 파일에 문제가 있습니다.`
              : "페이지 번호와 저장 파일 구성이 정상입니다.",
      status: existingMetadataError || !filtersMatch
        ? "waiting"
        : isCurrentInspectionRunning
          ? "running"
          : !hasCompletedCurrentInspection
            ? "waiting"
            : !existingData
              ? "complete"
              : inspectionCandidates.length > 0
                ? "failed"
                : "complete",
      statusLabel: existingMetadataError || !filtersMatch
        ? "대기"
        : isCurrentInspectionRunning
          ? "검사 중"
          : !hasCompletedCurrentInspection
            ? "대기"
            : !existingData
              ? "대상 없음"
              : inspectionCandidates.length > 0
                ? "문제 발견"
                : EXISTING_DATA_SUCCESS_LABEL,
      detail: inspectionCandidates.length > 0 ? (
        <ul className="max-h-48 space-y-2 overflow-y-auto text-[13px] leading-5 text-[var(--tv-down-text)]">
          {inspectionCandidates.map((candidate: any) => (
            <li key={candidate.path} className="rounded-md border border-[color:var(--tv-down)] bg-[var(--tv-down-soft)] px-3 py-2">
              <span className="font-semibold">{candidate.name}</span> · {candidate.reason}
            </li>
          ))}
        </ul>
      ) : undefined,
    },
    {
      key: "kind-count",
      title: "KIND 건수 비교",
      summary: !hasCompletedCurrentInspection
        ? "앞 단계가 끝나면 로컬 건수와 KIND의 현재 건수를 비교합니다."
        : !existingData
          ? "비교할 기존 데이터가 없습니다."
        : !filtersMatch || !hasCompletedCurrentInspection
          ? "앞 단계가 끝나면 로컬 건수와 KIND의 현재 건수를 비교합니다."
          : staleRanges.length > 0
            ? `${formatInteger(staleRanges.length)}개 범위의 로컬 건수가 KIND의 현재 건수와 일치하지 않습니다.`
            : `${formatInteger(inspectionRanges.length)}개 범위의 로컬 건수와 KIND 건수가 일치합니다.`,
      status: existingMetadataError || !filtersMatch || !hasCompletedCurrentInspection
        ? "waiting"
        : !existingData
          ? "complete"
          : staleRanges.length > 0
            ? "failed"
            : "complete",
      statusLabel: existingMetadataError || !filtersMatch || !hasCompletedCurrentInspection
        ? "대기"
        : !existingData
          ? "대상 없음"
          : staleRanges.length > 0
            ? "불일치"
            : EXISTING_DATA_SUCCESS_LABEL,
      detail: staleRanges.length > 0 ? (
        <div className="max-h-64 space-y-2 overflow-y-auto">
          {staleRanges.map((range) => (
            <div key={range.folder_path} className="rounded-md border border-[color:var(--tv-down)] bg-[var(--tv-down-soft)] px-3 py-2 text-[13px] leading-5 text-[var(--tv-down-text)]">
              <p className="font-semibold">{range.folder_name} · {range.start_date ?? "-"} ~ {range.end_date ?? "-"}</p>
              <p>로컬 {range.local_count == null ? "확인 실패" : `${formatInteger(range.local_count)}건`} / KIND {range.kind_count == null ? "확인 실패" : `${formatInteger(range.kind_count)}건`}</p>
              {range.error_detail && <p>{range.error_detail}</p>}
            </div>
          ))}
        </div>
      ) : undefined,
    },
  ];

  return (
    <WorkflowPageShell workflowId="disclosure-build">
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4" onClick={() => setNotificationPanelOpen(false)}>
        <section className="min-w-0 space-y-6">
          <DataIntegrityInspectionCard
            description="실행 전에 저장된 메타데이터와 현재 설정, 파일 구성, KIND 건수를 차례로 확인합니다."
            verdict={inspectionVerdict}
            steps={inspectionSteps}
          />

          <DataPathCard
            onError={handlePathError}
            fields={[
              {
                id: "workspace",
                label: DATA_PATH_LABELS.workspace,
                value: dataRoot,
                onChange: (val) => saveSetting("output_root", val),
              },
              {
                id: "output",
                label: DATA_PATH_LABELS.output,
                value: separateOutputDirectory,
                onChange: (val) => saveSetting("download_output_directory", val),
                separateOutputOnly: true,
              },
            ]}
          />

          <DisclosureSearchConditionCard
            options={options}
            startDate={startDate}
            endDate={endDate}
            companyName={companyName}
            submitterName={submitterName}
            marketLabel={marketLabel}
            securitiesLabel={securitiesLabel}
            onStartDateChange={setStartDate}
            onEndDateChange={setEndDate}
            onCompanyNameChange={setCompanyName}
            onSubmitterNameChange={setSubmitterName}
            onMarketLabelChange={setMarketLabel}
            onSecuritiesLabelChange={setSecuritiesLabel}
          />

          <DisclosureTypeSelectionCard
            options={options}
            selectedDisclosures={selectedDisclosures}
            onSelectedDisclosuresChange={setSelectedDisclosures}
          />

          <Card className="border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <Button variant="outline" className="w-full" onClick={handlePreview} disabled={!!activeJobId || runStarting}>
                  <Search className="mr-2 h-4 w-4" />
                  미리보기
                </Button>
                <Button className="w-full" onClick={handleRun} disabled={!!activeJobId || runStarting}>
                  {!!activeJobId || runStarting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                <Button variant="outline" className="w-full" onClick={handleCancelDownload} disabled={!activeJobId}>
                  {UI_TEXT.actions.cancelJob}
                </Button>
              </div>

            </CardContent>
          </Card>
        </section>

        <div ref={actionDockRef} className="action-dock-root fixed inset-x-4 bottom-4 z-40 md:relative md:inset-x-auto md:bottom-auto md:top-auto md:col-start-2 md:row-start-1 md:row-end-[-1] md:m-0 md:w-16 md:self-start md:justify-self-end" onClick={(event) => event.stopPropagation()}>
          <div className="flex h-14 items-center justify-center gap-2 rounded-lg border border-[color:var(--tv-border)] bg-[var(--tv-surface)] p-2 md:h-auto md:w-16 md:flex-col">
            <Button
              variant="outline"
              size="icon"
              onClick={() => {
                setDownloadPanelOpen((value) => !value);
                setNotificationPanelOpen(false);
                setSettingsPanelOpen(false);
              }}
              aria-pressed={downloadPanelOpen}
              className="relative h-10 w-10 rounded-lg border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-muted)]"
              title={downloadPanelOpen ? "실행 현황 닫기" : "실행 현황 열기"}
            >
              <Activity className="h-5 w-5" />
              {activeJobId && (
                <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-[var(--tv-muted)]" />
              )}
            </Button>

            <Button
              variant="outline"
              size="icon"
              onClick={() => {
                setNotificationPanelOpen((value) => !value);
                setDownloadPanelOpen(false);
                setSettingsPanelOpen(false);
              }}
              aria-pressed={notificationPanelOpen}
              className={
                (hasWarningNotification || hasSuccessfulInspectionNotification) && notificationTone !== "neutral"
                  ? "relative h-10 w-10 rounded-lg"
                    : "relative h-10 w-10 rounded-lg border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-muted)]"
              }
              style={hasWarningNotification || hasSuccessfulInspectionNotification
                ? dockToneStyle(notificationTone, notificationPanelOpen)
                : undefined}
              title={notificationPanelOpen ? "알림 닫기" : "알림 열기"}
            >
              <Bell className="h-5 w-5" />
              {(hasWarningNotification || hasSuccessfulInspectionNotification) && (
                <span className={`absolute right-2 top-2 h-2 w-2 rounded-full ${notificationDotClass}`} />
              )}
            </Button>

            <Button
              variant="outline"
              size="icon"
              onClick={() => {
                setSettingsPanelOpen((value) => !value);
                setDownloadPanelOpen(false);
                setNotificationPanelOpen(false);
              }}
              aria-pressed={settingsPanelOpen}
              className="h-10 w-10 rounded-lg border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-muted)]"
              title={settingsPanelOpen ? "다운로드 설정 닫기" : "다운로드 설정 열기"}
            >
              <Settings className="h-5 w-5" />
            </Button>
          </div>

          {notificationPanelOpen && (
            <Card className="fixed inset-x-4 bottom-20 max-h-[calc(100vh-7rem)] overflow-auto border-[color:var(--tv-border)] bg-[var(--tv-surface)] shadow-md md:absolute md:inset-x-auto md:bottom-auto md:right-full md:top-0 md:mr-3 md:w-[min(420px,calc(100vw-2rem))] md:max-h-[calc(100vh-8rem)]">
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="dark:text-white">알림</CardTitle>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setNotificationPanelOpen(false)}
                    className="h-8 w-8 text-[var(--tv-text)] hover:text-[var(--tv-accent)]"
                    title="알림 닫기"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {isErrorStatus || existingMetadataError ? (
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">작업 알림</Label>
                    <JobStatusLogger status={existingMetadataError || status} isErrorStatus />
                  </div>
                ) : null}

                {previewResult && !isErrorStatus && !existingMetadataError ? (
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">미리보기</Label>
                    <pre className="text-caption max-h-72 overflow-auto rounded-lg border border-[color:var(--tv-border)] bg-[var(--tv-control)] p-3 text-[var(--tv-text)]">
                      {JSON.stringify(previewResult, null, 2)}
                    </pre>
                  </div>
                ) : null}

                {currentInspectionCandidateCount > 0 && (
                  <div className="space-y-4 border-t border-[color:var(--tv-border)] pt-4">
                    <div className="text-body rounded-md border border-[color:var(--tv-warning)] bg-[var(--tv-warning-soft)] p-3 text-[var(--tv-warning-text)]">
                      삭제 예정 파일 {formatInteger(currentInspectionCandidateCount)}개
                    </div>
                    <div className="flex items-center space-x-2">
                      <Checkbox id="downloadDeleteConfirmed" checked={deleteConfirmed} onCheckedChange={(v) => setDeleteConfirmed(!!v)} className="border-[color:var(--tv-border)]" />
                      <Label htmlFor="downloadDeleteConfirmed" className="text-body cursor-pointer dark:text-slate-300">삭제 허가</Label>
                    </div>
                    <div className="space-y-2">
                      <Label className="dark:text-slate-300">확인 문구</Label>
                      <Input
                        value={deleteConfirmationText}
                        onChange={(e) => setDeleteConfirmationText(e.target.value)}
                        placeholder="확인했습니다."
                        className={htmlControlClassName}
                      />
                    </div>
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={handleDeleteUnexpectedFiles}
                      disabled={
                        !!activeJobId ||
                        inspectRunning ||
                        !deleteConfirmed ||
                        deleteConfirmationText.trim() !== "확인했습니다."
                      }
                    >
                      <Trash2 className="mr-2 h-4 w-4" />
                      삭제 예정 파일 {formatInteger(currentInspectionCandidateCount)}개 삭제
                    </Button>
                  </div>
                )}

                {hasInspectionFailureNotification && currentInspectionCandidateCount === 0 && !isErrorStatus && !existingMetadataError && (
                  <div className="text-body rounded-md border border-[color:var(--tv-warning)] bg-[var(--tv-warning-soft)] p-3 text-[var(--tv-warning-text)]">
                    기존 데이터 검사에서 확인이 필요한 범위가 {formatInteger(staleRanges.length)}개 발견됐습니다.
                  </div>
                )}

                {hasSuccessfulInspectionNotification && (
                  <div className="text-body rounded-md border border-[color:var(--tv-up)] bg-[var(--tv-up-soft)] p-3 text-[var(--tv-up-text)]">
                    <span className="font-semibold">{EXISTING_DATA_SUCCESS_LABEL}</span>
                    <p className="mt-1">기존 데이터 검사가 완료됐습니다. 모든 검사 단계를 통과했습니다.</p>
                  </div>
                )}

                {!hasWarningNotification && !hasSuccessfulInspectionNotification && (
                  <div className="text-body text-slate-500 dark:text-slate-400">알림 없음</div>
                )}
              </CardContent>
            </Card>
          )}

          {settingsPanelOpen && (
            <Card className="fixed inset-x-4 bottom-20 max-h-[calc(100vh-7rem)] overflow-auto border-[color:var(--tv-border)] bg-[var(--tv-surface)] shadow-md md:absolute md:inset-x-auto md:bottom-auto md:right-full md:top-0 md:mr-3 md:w-[min(420px,calc(100vw-2rem))] md:max-h-[calc(100vh-8rem)]">
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="dark:text-white">다운로드 설정</CardTitle>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setSettingsPanelOpen(false)}
                    className="h-8 w-8 text-[var(--tv-text)] hover:text-[var(--tv-accent)]"
                    title="다운로드 설정 닫기"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-5">
                <DisclosureSeparateOutputDirectorySetting id="download-separate-output-directory" />
                <div className="space-y-3">
                  <div className="border-b border-[color:var(--tv-border)] pb-2">
                    <p className="text-caption font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">요청 설정</p>
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">페이지 크기</Label>
                    <Input type="number" value={pageSize} onChange={(e) => setPageSize(e.target.value)} className={htmlControlClassName} />
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">대기 시간 (초)</Label>
                    <Input type="number" value={waitSeconds} onChange={(e) => setWaitSeconds(e.target.value)} className={htmlControlClassName} />
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">타임아웃 (초)</Label>
                    <Input type="number" value={timeout} onChange={(e) => setTimeoutVal(e.target.value)} className={htmlControlClassName} />
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="border-b border-[color:var(--tv-border)] pb-2">
                    <p className="text-caption font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">작업 범위</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label className="dark:text-slate-300">시작 페이지</Label>
                      <Input type="number" value={startPage} onChange={(e) => setStartPage(e.target.value)} className={htmlControlClassName} />
                    </div>
                    <div className="space-y-2">
                      <Label className="dark:text-slate-300">종료 페이지</Label>
                      <Input type="number" placeholder="전체" value={endPage} onChange={(e) => setEndPage(e.target.value)} className={htmlControlClassName} />
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Checkbox id="lastReportOnly" checked={lastReportOnly} onCheckedChange={(v) => setLastReportOnly(!!v)} className="border-[color:var(--tv-border)]" />
                    <Label htmlFor="lastReportOnly" className="cursor-pointer dark:text-slate-300">최종보고서만</Label>
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="border-b border-[color:var(--tv-border)] pb-2">
                    <p className="text-caption font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">실행 옵션</p>
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">병렬 처리 방식</Label>
                    <Select value={parallelStrategy} onValueChange={(value) => setParallelStrategy(value as "years" | "pages")}>
                      <SelectTrigger className={htmlControlClassName}><SelectValue /></SelectTrigger>
                      <SelectContent className={htmlSelectContentClassName}>
                        <SelectItem value="years">여러 연도 병렬 처리</SelectItem>
                        <SelectItem value="pages">한 연도 내 페이지 병렬 처리</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-caption text-slate-500 dark:text-slate-400">
                      같은 워커 수를 연도 간 분산하거나 한 연도의 페이지 처리에 집중합니다.
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">워커 수</Label>
                    <Input type="number" min="1" max={parallelWorkerCount} value={workerCount} onChange={(e) => setWorkerCount(e.target.value)} className={htmlControlClassName} />
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">로그 줄 수</Label>
                    <Input type="number" value={logLimit} onChange={(e) => setLogLimit(e.target.value)} className={htmlControlClassName} />
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">작업 기록 보관 시간 (분)</Label>
                    <Input
                      type="number"
                      min={1}
                      value={jobRetentionInput}
                      onChange={(e) => setJobRetentionInput(e.target.value)}
                      onBlur={saveJobRetentionMinutes}
                      className={htmlControlClassName}
                    />
                    <p className="text-caption text-slate-500 dark:text-slate-400">
                      완료·실패·중단된 작업 상태만 정리하며 저장 파일과 메타데이터는 유지합니다.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {downloadPanelOpen && (
            <Card className="fixed inset-x-4 bottom-20 max-h-[calc(100vh-7rem)] overflow-auto border-[color:var(--tv-border)] bg-[var(--tv-surface)] shadow-md md:absolute md:inset-x-auto md:bottom-auto md:right-full md:top-0 md:mr-3 md:w-[min(420px,calc(100vw-2rem))] md:max-h-[calc(100vh-8rem)]">
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                  <CardTitle className="dark:text-white">실행 현황</CardTitle>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setDownloadPanelOpen(false)}
                  className="h-8 w-8 text-[var(--tv-text)] hover:text-[var(--tv-accent)]"
                  title="실행 현황 닫기"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <JobStatusLogger
                status={status}
                isErrorStatus={isErrorStatus}
                isCancellable={!!activeJobId}
                onCancel={handleCancelDownload}
              />

              {result && (
                <div className="space-y-2 border-t border-[color:var(--tv-border)] pt-4">
                  <Label className="dark:text-slate-300">실행 결과</Label>
                  <pre className="text-caption max-h-72 overflow-auto rounded-lg border border-[color:var(--tv-border)] bg-[var(--tv-control)] p-3 text-[var(--tv-text)]">
                    {JSON.stringify(result, null, 2)}
                  </pre>
                </div>
              )}
            </CardContent>
          </Card>
          )}
        </div>
      </div>
    </WorkflowPageShell>
  );
}
