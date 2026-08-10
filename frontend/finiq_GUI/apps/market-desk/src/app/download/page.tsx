"use client"

import { useState, useEffect, useCallback, useRef } from "react";
import { Activity, Bell, X, Play, Search, Loader2, Trash2, ShieldCheck, Settings } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { Checkbox } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { JobStatusLogger, PageLoadingSpinner } from "@finiq/web-app/status";
import { htmlControlClassName, htmlSelectContentClassName } from "@/components/html-workflow/HtmlWorkflowTemplate";
import { cancelDownload, checkExistingDownload, fetchDownloadOptions, inspectDownloadFolder, previewDownload, startDownload, detectExistingDownload } from "@/features/download/api";
import type { DownloadExistingPayload, DownloadExistingResponse, DownloadOptions, DownloadPayload, DownloadSavedFilters } from "@/features/download/types";
import { UI_TEXT } from "@/config/uiText";
import { formatInteger } from "@/lib/format";
import {
  DisclosureSearchConditionCard,
  DisclosureTypeSelectionCard,
} from "@/components/disclosures/DisclosureSearchSettingsCards";
import { DisclosureSeparateOutputDirectorySetting } from "@/components/disclosures/DisclosureSeparateOutputDirectorySetting";
import {
  DataIntegrityInspectionPanel,
  type DataIntegrityInspectionStep,
  type DataIntegrityInspectionVerdict,
} from "@/components/data-integrity/DataIntegrityInspectionPanel";
import { useDataIntegrityInspection } from "@/hooks/useDataIntegrityInspection";

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

type DownloadExistingInspectionPayload = DownloadExistingPayload & {
  inspection_mode: "detect" | "verify";
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
  const [options, setOptions] = useState<DownloadOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [previewResult, setPreviewResult] = useState<any>(null);
  const [notificationPanelOpen, setNotificationPanelOpen] = useState(false);
  const [downloadPanelOpen, setDownloadPanelOpen] = useState(false);
  const [settingsPanelOpen, setSettingsPanelOpen] = useState(false);
  const [runStarting, setRunStarting] = useState(false);
  const isRunTriggeredRef = useRef(false);
  const capturedPayloadRef = useRef<DownloadPayload | null>(null);
  const activeInspectionKeyRef = useRef<string | null>(null);
  const [lastInspectedExistingKey, setLastInspectedExistingKey] = useState<string | null>(null);

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

  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus } = useJobPolling({
    pollingEndpoint: "/api/download/jobs/{jobId}",
    onSuccess: async (data) => {
      if (data && data.format === "kind_download_folder_cleanup_v1") {
        const candidateCount = data.dry_run ? (data.deletion_candidate_count || 0) : 0;
        const completedInspectionKey = activeInspectionKeyRef.current;
        const verified = await checkExisting(outputDirectory, true);
        const hasVerificationFailure = !verified || (verified.ranges?.some((range) => range.status === "stale") ?? false);
        if (verified && completedInspectionKey) {
          setLastInspectedExistingKey(completedInspectionKey);
        }
        activeInspectionKeyRef.current = null;
        setLastInspectionCandidateCount(candidateCount);
        setResult(data);
        setStatus(buildInspectionStatus(data, !data.dry_run));

        if (isRunTriggeredRef.current) {
          isRunTriggeredRef.current = false;
          if (candidateCount > 0 || hasVerificationFailure) {
            setNotificationPanelOpen(true);
            setDownloadPanelOpen(false);
            setSettingsPanelOpen(false);
          } else {
            try {
              setStatus("다운로드 작업을 시작하는 중...");
              await startDownloadJob();
            } catch (err: any) {
              setStatus(err.message);
              setIsErrorStatus(true);
            }
          }
        } else {
          setNotificationPanelOpen(true);
          setDownloadPanelOpen(false);
          setSettingsPanelOpen(false);
        }
      } else {
        setResult(data);
      }
    },
    onError: (error) => {
      isRunTriggeredRef.current = false;
      capturedPayloadRef.current = null;
    },
    onCancel: () => {
      isRunTriggeredRef.current = false;
      capturedPayloadRef.current = null;
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
  const [deleteConfirmed, setDeleteConfirmed] = useState(false);
  const [deleteConfirmationText, setDeleteConfirmationText] = useState("");
  const [inspectRunning, setInspectRunning] = useState(false);
  const [lastInspectionCandidateCount, setLastInspectionCandidateCount] = useState(0);
  const {
    result: existingInspectionResult,
    error: existingMetadataError,
    isChecking: checkingExisting,
    runInspection: runExistingInspection,
    clear: clearExistingInspection,
  } = useDataIntegrityInspection<DownloadExistingInspectionPayload, DownloadExistingResponse>({
    inspect: ({ inspection_mode, ...payload }) => (
      inspection_mode === "verify"
        ? checkExistingDownload(payload)
        : detectExistingDownload(payload)
    ),
    onError: (message) => {
      setStatus(message);
      setIsErrorStatus(true);
      setNotificationPanelOpen(true);
    },
  });
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

  const filtersMatch = areFiltersMatching(
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

  const checkExisting = useCallback(async (dir: string, verifyWithKind = false) => {
    if (!dir) {
      clearExistingInspection();
      return;
    }
    const submittedPayload: DownloadExistingInspectionPayload = {
      output_directory: dir,
      start_date: startDate,
      end_date: endDate,
      company_name: companyName,
      submitter_name: submitterName,
      market_label: marketLabel,
      securities_label: securitiesLabel,
      page_size: Number(pageSize),
      last_report_only: lastReportOnly,
      disclosure_type_groups: selectedDisclosures,
      inspection_mode: verifyWithKind ? "verify" : "detect",
    };
    const requestKey = checkExistingPayloadKey(submittedPayload);
    return runExistingInspection(submittedPayload, requestKey);
  }, [
    startDate,
    endDate,
    companyName,
    submitterName,
    marketLabel,
    securitiesLabel,
    pageSize,
    lastReportOnly,
    selectedDisclosures,
    clearExistingInspection,
    runExistingInspection,
  ]);

  useEffect(() => {
    checkExisting(outputDirectory);
  }, [outputDirectory, checkExisting]);

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

  const startDownloadJob = async () => {
    const payload = capturedPayloadRef.current || buildPayload();
    capturedPayloadRef.current = null;
    const data = await startDownload(payload);
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

  const inspectExistingFiles = async (dryRun: boolean, customPayload?: any) => {
    const basePayload = customPayload || buildPayload();
    activeInspectionKeyRef.current = checkExistingPayloadKey(existingPayloadFromDownloadPayload(basePayload));
    return inspectDownloadFolder({
      ...basePayload,
      dry_run: dryRun,
      delete_confirmed: deleteConfirmed,
      delete_confirmation_text: deleteConfirmationText,
    });
  };

  const buildInspectionStatus = (data: any, deleted: boolean) => {
    const files = Array.isArray(deleted ? data.deleted_files : data.deletion_candidates)
      ? (deleted ? data.deleted_files : data.deletion_candidates)
      : [];
    const lines = [
      deleted ? "파일 삭제 완료" : "검사 완료",
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
      isRunTriggeredRef.current = false;
      capturedPayloadRef.current = null;
      const data = await inspectExistingFiles(true);
      startPolling(data.job_id);
      setDownloadPanelOpen(true);
      setNotificationPanelOpen(false);
      setSettingsPanelOpen(false);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
      setNotificationPanelOpen(true);
      setDownloadPanelOpen(false);
      setSettingsPanelOpen(false);
    } finally {
      setInspectRunning(false);
    }
  };

  const handleRun = async () => {
    if (runStarting || checkingExisting) return;
    try {
      setRunStarting(true);
      if (existingMetadataError) {
        throw new Error(existingMetadataError);
      }
      if (existingData?.saved_filters && !filtersMatch) {
        throw new Error("현재 입력된 검색 필터가 기존 다운로드 폴더의 메타데이터와 다릅니다. 필터를 먼저 일치시켜 주세요.");
      }
      const payload = buildPayload();
      capturedPayloadRef.current = payload;
      isRunTriggeredRef.current = true;
      setIsErrorStatus(false);
      setPreviewResult(null);
      setStatus("기존 다운로드 파일을 검사하는 중...");
      const data = await inspectExistingFiles(true, payload);
      startPolling(data.job_id);
      setDownloadPanelOpen(true);
      setNotificationPanelOpen(false);
      setSettingsPanelOpen(false);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
      isRunTriggeredRef.current = false;
      capturedPayloadRef.current = null;
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
      isRunTriggeredRef.current = false;
      const payload = capturedPayloadRef.current || buildPayload();
      const data = await inspectExistingFiles(false, payload);
      setLastInspectionCandidateCount(0);
      setDeleteConfirmed(false);
      setDeleteConfirmationText("");
      startPolling(data.job_id);
      setDownloadPanelOpen(true);
      setNotificationPanelOpen(false);
      setSettingsPanelOpen(false);
    } catch (err: any) {
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
  const isCurrentInspectionRunning = inspectRunning || activeInspectionKeyRef.current === currentExistingKey;
  const inspectionRanges = existingData?.ranges || [];
  const staleRanges = inspectionRanges.filter((range) => range.status === "stale");
  const inspectionCandidates = hasCompletedCurrentInspection && result?.format === "kind_download_folder_cleanup_v1"
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
      label: "검토 대기",
      title: "데이터 경로를 선택해 주세요",
      description: "경로를 선택하면 기존 데이터와 메타데이터를 먼저 확인합니다.",
      tone: "neutral",
    };
  } else if (checkingExisting && !existingInspectionResult) {
    inspectionVerdict = {
      label: "확인 중",
      title: "기존 데이터와 메타데이터를 읽고 있습니다",
      description: outputDirectory,
      tone: "neutral",
    };
  } else if (existingMetadataError) {
    inspectionVerdict = {
      label: "검토 중단",
      title: "메타데이터를 확인할 수 없습니다",
      description: existingMetadataError,
      tone: "error",
    };
  } else if (!existingData) {
    inspectionVerdict = {
      label: "검토 완료",
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
  } else if (!hasCompletedCurrentInspection) {
    inspectionVerdict = {
      label: "검사 필요",
      title: "메타데이터는 확인됐지만 파일 검사가 남아 있습니다",
      description: "검사를 실행하면 저장 파일의 구성과 KIND 건수를 순서대로 확인합니다.",
      tone: "warning",
    };
  } else if (inspectionCandidates.length > 0 || staleRanges.length > 0) {
    inspectionVerdict = {
      label: "사용 불가",
      title: "기존 데이터에서 문제가 확인됐습니다",
      description: "아래 실패 단계의 원인과 조치를 확인해 주세요.",
      tone: "error",
    };
  } else {
    inspectionVerdict = {
      label: "사용 가능",
      title: "기존 데이터를 안전하게 재사용할 수 있습니다",
      description: `${existingData.earliest_date ?? "-"} ~ ${existingData.latest_date ?? "-"} · ${formatInteger(inspectionRanges.length)}개 범위 확인`,
      tone: "success",
    };
  }

  const inspectionSteps: DataIntegrityInspectionStep[] = [
    {
      key: "metadata",
      title: "메타데이터 읽기",
      summary: existingData
        ? `${formatInteger(inspectionRanges.length)}개 저장 범위의 메타데이터를 확인했습니다.`
        : existingMetadataError
          ? "저장된 메타데이터를 읽지 못했습니다."
          : "비교할 기존 데이터가 없습니다.",
      status: existingMetadataError ? "failed" : checkingExisting && !existingInspectionResult ? "running" : "complete",
      statusLabel: existingMetadataError ? "실패" : checkingExisting && !existingInspectionResult ? "확인 중" : "완료",
      detail: existingMetadataError ? (
        <p className="text-[13px] leading-5 text-[var(--tv-down-text)]">{existingMetadataError}</p>
      ) : undefined,
    },
    {
      key: "settings",
      title: "현재 설정과 비교",
      summary: !existingData
        ? "비교할 저장 설정이 없습니다."
        : filtersMatch
          ? "저장된 검색 설정과 현재 조건이 같습니다."
          : `${formatInteger(filterDifferences.length)}개 설정이 현재 조건과 다릅니다.`,
      status: existingMetadataError ? "waiting" : !existingData || filtersMatch ? "complete" : "failed",
      statusLabel: existingMetadataError ? "대기" : !existingData ? "대상 없음" : filtersMatch ? "일치" : "불일치",
      detail: !filtersMatch && savedFilters ? (
        <div className="space-y-3">
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
          <Button type="button" variant="outline" size="sm" className="h-8 text-[13px]" onClick={handleApplySavedFilters}>
            저장된 설정 적용
          </Button>
        </div>
      ) : undefined,
    },
    {
      key: "files",
      title: "저장 파일 구성 검사",
      summary: !existingData
        ? "검사할 기존 파일이 없습니다."
        : !filtersMatch
          ? "설정 불일치를 먼저 해결해야 합니다."
          : isCurrentInspectionRunning
            ? "페이지 번호의 연속성과 파일 구성을 검사하고 있습니다."
          : !hasCompletedCurrentInspection
            ? "페이지 번호의 연속성과 파일 구성을 검사할 준비가 됐습니다."
            : inspectionCandidates.length > 0
              ? `${formatInteger(inspectionCandidates.length)}개 파일에서 문제가 확인됐습니다.`
              : "페이지 번호와 저장 파일 구성이 정상입니다.",
      status: existingMetadataError || !filtersMatch
        ? "waiting"
        : !existingData
          ? "complete"
          : isCurrentInspectionRunning
            ? "running"
            : !hasCompletedCurrentInspection
              ? "ready"
              : inspectionCandidates.length > 0
                ? "failed"
                : "complete",
      statusLabel: existingMetadataError || !filtersMatch
        ? "대기"
        : !existingData
          ? "대상 없음"
          : isCurrentInspectionRunning
            ? "검사 중"
            : !hasCompletedCurrentInspection
              ? "검사 필요"
              : inspectionCandidates.length > 0
                ? "문제 발견"
                : "통과",
      detail: inspectionCandidates.length > 0 ? (
        <ul className="max-h-48 space-y-2 overflow-y-auto text-[13px] leading-5 text-[var(--tv-down-text)]">
          {inspectionCandidates.map((candidate: any) => (
            <li key={candidate.path} className="rounded-md border border-[color:var(--tv-down)] bg-[var(--tv-down-soft)] px-3 py-2">
              <span className="font-semibold">{candidate.name}</span> · {candidate.reason}
            </li>
          ))}
        </ul>
      ) : undefined,
      action: existingData && filtersMatch && !hasCompletedCurrentInspection ? {
        label: isCurrentInspectionRunning ? "검사 중..." : "검사하기",
        onClick: handleInspectFolder,
        disabled: isCurrentInspectionRunning || !!activeJobId || runStarting || checkingExisting,
        loading: isCurrentInspectionRunning,
      } : undefined,
    },
    {
      key: "kind-count",
      title: "KIND 건수 비교",
      summary: !existingData
        ? "비교할 기존 데이터가 없습니다."
        : !filtersMatch || !hasCompletedCurrentInspection
          ? "앞 단계가 끝나면 로컬 건수와 KIND 현재 건수를 비교합니다."
          : staleRanges.length > 0
            ? `${formatInteger(staleRanges.length)}개 범위가 KIND 현재 상태와 일치하지 않습니다.`
            : `${formatInteger(inspectionRanges.length)}개 범위의 로컬 건수와 KIND 건수가 일치합니다.`,
      status: existingMetadataError || !filtersMatch || (existingData && !hasCompletedCurrentInspection)
        ? "waiting"
        : !existingData
          ? "complete"
          : staleRanges.length > 0
            ? "failed"
            : "complete",
      statusLabel: existingMetadataError || !filtersMatch || (existingData && !hasCompletedCurrentInspection)
        ? "대기"
        : !existingData
          ? "대상 없음"
          : staleRanges.length > 0
            ? "불일치"
            : "통과",
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
            beforeFields={
              <>
              <div className="space-y-2">
                <Label className="dark:text-slate-300">작업공간 디렉토리</Label>
                <PathPickerInput
                  value={dataRoot}
                  onChange={(val) => saveSetting("output_root", val)}
                  placeholder="데이터 경로를 선택하세요"
                  mode="folder"
                  onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                />
              </div>

              {useSeparateOutputDirectory && (
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">결과 데이터 경로</Label>
                  <PathPickerInput
                    value={separateOutputDirectory}
                    onChange={(val) => saveSetting("download_output_directory", val)}
                    placeholder="결과 데이터 경로를 선택하세요"
                    mode="folder"
                    onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                  />
                </div>
              )}
              </>
            }
          />

          <Card className="border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
            <CardHeader className="gap-1.5">
              <div className="space-y-1.5">
                <CardTitle className="flex items-center gap-2 text-[16px] leading-6 dark:text-white">
                  <ShieldCheck className="h-5 w-5 text-[var(--tv-accent)]" />
                  기존 데이터 검토
                </CardTitle>
                <p className="text-[13px] leading-5 text-[var(--tv-muted)]">
                  실행 전에 저장된 메타데이터, 현재 설정, 파일 구성, KIND 건수를 순서대로 확인합니다.
                </p>
              </div>
            </CardHeader>
            <CardContent>
              <DataIntegrityInspectionPanel verdict={inspectionVerdict} steps={inspectionSteps} />
            </CardContent>
          </Card>

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
                <Button className="w-full" onClick={handleRun} disabled={!!activeJobId || runStarting || checkingExisting}>
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

        <div className="action-dock-root fixed inset-x-4 bottom-4 z-40 md:sticky md:inset-x-auto md:bottom-auto md:top-0 md:col-start-2 md:row-start-1 md:row-end-[-1] md:m-0 md:w-16 md:self-start md:justify-self-end" onClick={(event) => event.stopPropagation()}>
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
              className={
                downloadPanelOpen
                  ? "relative h-10 w-10 rounded-lg border-[color:var(--tv-accent)] bg-[var(--tv-accent)] text-[var(--tv-accent-foreground)]"
                  : activeJobId
                    ? "relative h-10 w-10 rounded-lg border-[color:var(--tv-accent)] bg-[var(--tv-accent-soft)] text-[var(--tv-accent)]"
                    : "relative h-10 w-10 rounded-lg border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-muted)]"
              }
              title={downloadPanelOpen ? "실행 현황 닫기" : "실행 현황 열기"}
            >
              <Activity className="h-5 w-5" />
              {activeJobId && (
                <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-[var(--tv-accent)]" />
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
                notificationPanelOpen
                  ? "relative h-10 w-10 rounded-lg border-[color:var(--tv-accent)] bg-[var(--tv-accent)] text-[var(--tv-accent-foreground)]"
                  : lastInspectionCandidateCount > 0 || isErrorStatus || !!previewResult
                    ? "relative h-10 w-10 rounded-lg border-[color:var(--tv-warning)] bg-[var(--tv-warning-soft)] text-[var(--tv-warning-text)]"
                    : "relative h-10 w-10 rounded-lg border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-muted)]"
              }
              title={notificationPanelOpen ? "알림 닫기" : "알림 열기"}
            >
              <Bell className="h-5 w-5" />
              {(lastInspectionCandidateCount > 0 || isErrorStatus || !!previewResult) && (
                <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-[var(--tv-warning)]" />
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
              className={
                settingsPanelOpen
                  ? "h-10 w-10 rounded-lg border-[color:var(--tv-accent)] bg-[var(--tv-accent)] text-[var(--tv-accent-foreground)]"
                  : "h-10 w-10 rounded-lg border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-muted)]"
              }
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
                {isErrorStatus ? (
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">작업 알림</Label>
                    <JobStatusLogger status={status} isErrorStatus={isErrorStatus} />
                  </div>
                ) : null}

                {previewResult && !isErrorStatus ? (
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">미리보기</Label>
                    <pre className="text-caption max-h-72 overflow-auto rounded-lg border border-[color:var(--tv-border)] bg-[var(--tv-control)] p-3 text-[var(--tv-text)]">
                      {JSON.stringify(previewResult, null, 2)}
                    </pre>
                  </div>
                ) : null}

                {lastInspectionCandidateCount > 0 && (
                  <div className="space-y-4 border-t border-[color:var(--tv-border)] pt-4">
                    <div className="text-body rounded-md border border-[color:var(--tv-warning)] bg-[var(--tv-warning-soft)] p-3 text-[var(--tv-warning-text)]">
                      삭제 예정 파일 {formatInteger(lastInspectionCandidateCount)}개
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
                      삭제 예정 파일 {formatInteger(lastInspectionCandidateCount)}개 삭제
                    </Button>
                  </div>
                )}

                {!isErrorStatus && lastInspectionCandidateCount === 0 && !previewResult && (
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
