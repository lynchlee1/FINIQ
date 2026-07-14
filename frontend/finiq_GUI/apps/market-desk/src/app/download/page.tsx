"use client"

import { useState, useEffect, useCallback, useRef } from "react";
import { Activity, AlertTriangle, Bell, Info, X, Play, Search, Loader2, Trash2, FolderOpen, Settings } from "lucide-react";
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
import { htmlControlClassName, htmlInsetPanelClassName, htmlSelectContentClassName } from "@/components/html-workflow/HtmlWorkflowTemplate";
import { cancelDownload, fetchDownloadOptions, inspectDownloadFolder, previewDownload, startDownload, detectExistingDownload } from "@/features/download/api";
import type { DownloadOptions, DownloadPayload } from "@/features/download/types";
import { UI_TEXT } from "@/config/uiText";
import { formatInteger } from "@/lib/format";
import {
  DisclosureSearchConditionCard,
  DisclosureTypeSelectionCard,
} from "@/components/disclosures/DisclosureSearchSettingsCards";
import { DisclosureSeparateOutputDirectorySetting } from "@/components/disclosures/DisclosureSeparateOutputDirectorySetting";

const parseISODate = (dateStr: string) => {
  const [year, month, day] = dateStr.split("-").map(Number);
  return new Date(year, month - 1, day);
};

const formatDateToISO = (date: Date) => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
};

const areDisclosureGroupsMatching = (g1: Record<string, string[]>, g2: Record<string, string[]>) => {
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
  saved: any
) => {
  if (!saved) return true;
  if (current.companyName.trim() !== (saved.company_name || "").trim()) return false;
  if (current.submitterName.trim() !== (saved.submitter_name || "").trim()) return false;
  if (current.marketLabel !== (saved.market_label || "검색대상")) return false;
  if (current.securitiesLabel !== (saved.securities_label || "전체")) return false;
  if (current.lastReportOnly !== !!saved.last_report_only) return false;
  if (!areDisclosureGroupsMatching(current.selectedDisclosures, saved.disclosure_type_groups || {})) {
    return false;
  }
  return true;
};

const checkExistingPayloadKey = (payload: {
  output_directory: string;
  start_date: string;
  end_date: string;
  company_name: string;
  submitter_name: string;
  market_label: string;
  securities_label: string;
  page_size: number;
  last_report_only: boolean;
  disclosure_type_groups: Record<string, string[]>;
}) => JSON.stringify({
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
  const [existingData, setExistingData] = useState<{
    has_existing: boolean;
    earliest_date?: string | null;
    latest_date?: string | null;
    ranges?: {
      start_date: string | null;
      end_date: string | null;
      folder_name: string;
      local_count: number | null;
      kind_count: number | null;
      status: "validated" | "stale" | "unverified";
      error_detail: string | null;
      metadata_missing?: boolean;
      metadata_obsolete?: boolean;
      metadata_status?: "ok" | "missing" | "obsolete" | "mismatch";
      filters_match?: boolean;
      folder_path: string;
    }[];
    saved_filters?: {
      company_name: string;
      submitter_name: string;
      market_label: string;
      securities_label: string;
      disclosure_type_groups: Record<string, string[]>;
      last_report_only: boolean;
    } | null;
  } | null>(null);
  const [existingMetadataError, setExistingMetadataError] = useState<string | null>(null);
  const [checkingExisting, setCheckingExisting] = useState(false);
  const [runStarting, setRunStarting] = useState(false);
  const isRunTriggeredRef = useRef(false);
  const capturedPayloadRef = useRef<DownloadPayload | null>(null);
  const activeInspectionKeyRef = useRef<string | null>(null);
  const checkExistingRequestRef = useRef({ id: 0, key: "" });
  const [lastInspectedExistingKey, setLastInspectedExistingKey] = useState<string | null>(null);

  const {
    output_root: dataRoot,
    download_output_directory: separateOutputDirectory,
    disclosure_separate_output_directory: useSeparateOutputDirectory,
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
        if (activeInspectionKeyRef.current) {
          setLastInspectedExistingKey(activeInspectionKeyRef.current);
          activeInspectionKeyRef.current = null;
        }
        await checkExisting(useSettingsStore.getState().download_output_directory);
        setLastInspectionCandidateCount(candidateCount);
        setResult(data);
        setStatus(buildInspectionStatus(data, !data.dry_run));

        if (isRunTriggeredRef.current) {
          isRunTriggeredRef.current = false;
          if (candidateCount > 0) {
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
  const [marketLabel, setMarketLabel] = useState("검색대상");
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
  const [resumeYearly, setResumeYearly] = useState(true);
  const [logLimit, setLogLimit] = useState("20");
  const [selectedDisclosures, setSelectedDisclosures] = useState<Record<string, string[]>>({});
  const [deleteConfirmed, setDeleteConfirmed] = useState(false);
  const [deleteConfirmationText, setDeleteConfirmationText] = useState("");
  const [inspectRunning, setInspectRunning] = useState(false);
  const [lastInspectionCandidateCount, setLastInspectionCandidateCount] = useState(0);

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
    setMarketLabel(saved.market_label || "검색대상");
    setSecuritiesLabel(saved.securities_label || "전체");
    setSelectedDisclosures(saved.disclosure_type_groups || {});
    setLastReportOnly(!!saved.last_report_only);
    setStatus("기존 메타데이터 기준으로 검색 설정을 맞췄습니다.");
    setIsErrorStatus(false);
  };

  const fetchOptions = useCallback(async () => {
    try {
      const [data] = await Promise.all([fetchDownloadOptions(), fetchSettings()]);
      setOptions(data);

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

  const checkExisting = useCallback(async (dir: string) => {
    if (!dir) {
      checkExistingRequestRef.current = { id: checkExistingRequestRef.current.id + 1, key: "" };
      setCheckingExisting(false);
      setExistingData(null);
      setExistingMetadataError(null);
      return;
    }
    const submittedPayload = {
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
    };
    const requestId = checkExistingRequestRef.current.id + 1;
    const requestKey = checkExistingPayloadKey(submittedPayload);
    checkExistingRequestRef.current = { id: requestId, key: requestKey };
    setCheckingExisting(true);
    setExistingMetadataError(null);

    try {
      const result = await detectExistingDownload(submittedPayload);
      if (
        checkExistingRequestRef.current.id !== requestId ||
        checkExistingRequestRef.current.key !== requestKey
      ) {
        return;
      }
      if (result && result.has_existing) {
        setExistingData(result);
      } else {
        setExistingData(null);
      }
      setExistingMetadataError(null);
    } catch (error) {
      if (
        checkExistingRequestRef.current.id === requestId &&
        checkExistingRequestRef.current.key === requestKey
      ) {
        const message = error instanceof Error ? error.message : String(error);
        setExistingData(null);
        setExistingMetadataError(message);
        setStatus(message);
        setIsErrorStatus(true);
        setNotificationPanelOpen(true);
      }
    } finally {
      if (
        checkExistingRequestRef.current.id === requestId &&
        checkExistingRequestRef.current.key === requestKey
      ) {
        setCheckingExisting(false);
      }
    }
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
  ]);

  useEffect(() => {
    checkExisting(outputDirectory);
  }, [outputDirectory, checkExisting]);

  const handleApplyUpdateRange = () => {
    if (!existingData || !existingData.latest_date) return;
    try {
      const latest = parseISODate(existingData.latest_date);
      latest.setDate(latest.getDate() + 1);
      const nextStartStr = formatDateToISO(latest);
      
      const today = new Date();
      const yesterday = new Date(today);
      yesterday.setDate(today.getDate() - 1);
      const yesterdayStr = formatDateToISO(yesterday);
      
      if (nextStartStr > yesterdayStr) {
        setStatus("이미 어제 날짜 공시 내역까지 다운로드되어 있거나 최신 상태입니다.");
        return;
      }
      
      setStartDate(nextStartStr);
      setEndDate(yesterdayStr);
      setStatus(`다운로드 기간이 업데이트용(어제까지)으로 변경되었습니다: ${nextStartStr} ~ ${yesterdayStr}`);
    } catch (err: any) {
      setStatus(`날짜 계산 중 오류가 발생했습니다: ${err.message}`);
      setIsErrorStatus(true);
    }
  };



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
    resume_yearly: resumeYearly,
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
      deleted ? "파일 삭제 완료" : "폴더 검사 완료",
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
      setStatus("폴더 검사 작업을 시작하는 중...");
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

              {checkingExisting && !existingData && (
                <div className={`${htmlInsetPanelClassName} text-body space-y-3 animate-fade-in transition-all`}>
                  <div className="flex items-start gap-3">
                    <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-slate-500 dark:text-slate-400" />
                    <div className="space-y-1">
                      <p className="font-semibold text-slate-900 dark:text-slate-100">기존 다운로드 폴더 확인 중...</p>
                      <p className="text-caption break-all text-slate-500 dark:text-slate-400">
                        선택한 데이터 경로의 폴더와 메타데이터 상태만 빠르게 확인하고 있습니다: {outputDirectory}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {existingData && existingData.has_existing && (
                <div className={`${htmlInsetPanelClassName} text-body space-y-3 animate-fade-in transition-all`}>
                      <div className="flex flex-col justify-between gap-3 border-b border-[color:var(--tv-border)] pb-3 md:flex-row md:items-center">
                        <div className="space-y-1">
                          <p className="text-body flex items-center gap-1.5 font-semibold text-slate-900 dark:text-slate-100">
                            <FolderOpen className="h-4 w-4 text-[var(--tv-accent)]" />
                            기존 다운로드 시도 범위 감지됨
                            {checkingExisting && (
                              <span className="text-caption inline-flex items-center gap-1 font-medium text-slate-500 dark:text-slate-400">
                                <Loader2 className="h-3 w-3 animate-spin" />
                                재확인 중
                              </span>
                            )}
                          </p>
                          <p className="text-caption text-slate-500 dark:text-slate-400">
                            전체 범위: <span className="font-semibold">{existingData?.earliest_date}</span> ~ <span className="font-semibold">{existingData?.latest_date}</span>
                          </p>
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-8 shrink-0 self-start border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-text)] hover:text-[var(--tv-accent)] md:self-auto"
                          onClick={handleApplyUpdateRange}
                          disabled={
                            (existingData?.ranges?.some(r => r.status === "stale") ?? false) ||
                            !filtersMatch
                          }
                        >
                          이어서 다운로드하기 (업데이트)
                        </Button>
                      </div>

                      {/* Range List */}
                      <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                        {existingData?.ranges?.map((range, index) => {
                          const metadataReady = range.status === "unverified" && !range.metadata_missing && range.metadata_status !== "mismatch";
                          const statusTone = metadataReady ? "metadataOk" : range.status;
                          const statusColors = {
                            validated: "border-[color:var(--tv-up)] bg-[var(--tv-up-soft)] text-[var(--tv-up-text)]",
                            metadataOk: "border-[color:var(--tv-up)] bg-[var(--tv-up-soft)] text-[var(--tv-up-text)]",
                            stale: "border-[color:var(--tv-down)] bg-[var(--tv-down-soft)] text-[var(--tv-down-text)]",
                            unverified: "border-[color:var(--tv-warning)] bg-[var(--tv-warning-soft)] text-[var(--tv-warning-text)]",
                          };
                          const statusLabels = {
                            validated: "검증 완료: KIND 건수 일치",
                            stale: range.metadata_missing
                              ? "검증 실패: 메타데이터 없음"
                              : "검증 실패: KIND 건수 불일치 (stale)",
                            unverified: range.metadata_status === "mismatch"
                              ? "메타데이터 설정 불일치"
                              : "메타데이터 확인됨",
                          };

                          return (
                            <div
                              key={index}
                              className="text-caption flex flex-col justify-between gap-2 rounded border border-[color:var(--tv-border)] bg-[var(--tv-surface)] p-2 sm:flex-row sm:items-center"
                            >
                              <div className="space-y-0.5">
                                <p className="font-medium text-slate-800 dark:text-slate-200">
                                  {range.folder_name} ({range.start_date ?? "-"} ~ {range.end_date ?? "-"})
                                </p>
                                <p className="text-caption text-slate-500 dark:text-slate-400">
                                  로컬 건수: {range.local_count == null ? "-" : formatInteger(range.local_count)} | KIND 건수: {range.kind_count == null ? "-" : formatInteger(range.kind_count)}
                                </p>
                                {range.error_detail && (
                                  <p className="text-caption flex items-center gap-1 font-medium text-[var(--tv-down-text)]">
                                    <AlertTriangle className="h-3.5 w-3.5" />
                                    {range.error_detail}
                                  </p>
                                )}
                              </div>
                              <span className={`text-caption rounded-full border px-2 py-0.5 font-semibold ${statusColors[statusTone]}`}>
                                {statusLabels[range.status]}
                              </span>
                            </div>
                          );
                        })}
                      </div>

                      {/* Warning message if stale ranges exist */}
                      {existingData?.ranges?.some(r => r.status === "stale") && (
                        <div className="text-caption rounded-md border border-[color:var(--tv-down)] bg-[var(--tv-down-soft)] p-3 text-[var(--tv-down-text)]">
                          <strong>경고:</strong> 기존 다운로드한 데이터 중 일부를 안전하게 재사용할 수 없습니다. KIND 건수가 다르거나 필수 메타데이터가 없습니다.
                          해당 폴더를 삭제한 뒤 다시 다운로드해야 합니다.
                        </div>
                      )}

                      {/* Warning message if filters mismatch */}
                      {!filtersMatch && existingData?.saved_filters && (
                        <div className="text-caption rounded-md border border-[color:var(--tv-down)] bg-[var(--tv-down-soft)] p-3 text-[var(--tv-down-text)]">
                          <strong>오류:</strong> 현재 입력된 검색 필터가 기존 다운로드 폴더의 메타데이터와 다릅니다. 폴더 내 데이터가 오염(mixed dataset)되는 것을 방지하기 위해 <strong>이어서 다운로드하기가 비활성화</strong>됩니다. 검색 필터를 메타데이터와 동일하게 일치시키거나 다른 경로를 선택해 주세요.
                          <div className="mt-2 space-y-1 border-l-2 border-[color:var(--tv-down)] pl-3 opacity-90">
                            {existingData.saved_filters.company_name.trim() !== companyName.trim() && (
                              <p>• 회사명 불일치: (기존) &ldquo;{existingData.saved_filters.company_name}&rdquo; &harr; (현재) &ldquo;{companyName}&rdquo;</p>
                            )}
                            {existingData.saved_filters.submitter_name.trim() !== submitterName.trim() && (
                              <p>• 제출인 불일치: (기존) &ldquo;{existingData.saved_filters.submitter_name}&rdquo; &harr; (현재) &ldquo;{submitterName}&rdquo;</p>
                            )}
                            {existingData.saved_filters.market_label !== marketLabel && (
                              <p>• 시장 불일치: (기존) &ldquo;{existingData.saved_filters.market_label}&rdquo; &harr; (현재) &ldquo;{marketLabel}&rdquo;</p>
                            )}
                            {existingData.saved_filters.securities_label !== securitiesLabel && (
                              <p>• 증권종류 불일치: (기존) &ldquo;{existingData.saved_filters.securities_label}&rdquo; &harr; (현재) &ldquo;{securitiesLabel}&rdquo;</p>
                            )}
                            {!!existingData.saved_filters.last_report_only !== lastReportOnly && (
                              <p>• 최종보고서만 불일치: (기존) &ldquo;{existingData.saved_filters.last_report_only ? "예" : "아니오"}&rdquo; &harr; (현재) &ldquo;{lastReportOnly ? "예" : "아니오"}&rdquo;</p>
                            )}
                            {!areDisclosureGroupsMatching(selectedDisclosures, existingData.saved_filters.disclosure_type_groups || {}) && (
                              <p>• 공시 종류 불일치</p>
                            )}
                          </div>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="mt-3 h-8 border-[color:var(--tv-down)] bg-[var(--tv-surface)] text-[var(--tv-down)]"
                            onClick={handleApplySavedFilters}
                          >
                            기존 메타데이터 기준으로 설정 맞추기
                          </Button>
                        </div>
                      )}

                      {existingData?.ranges?.some(r => r.status === "unverified") && !hasCompletedCurrentInspection && (
                        <div className="text-caption rounded-md border border-[color:var(--tv-warning)] bg-[var(--tv-warning-soft)] p-3 text-[var(--tv-warning-text)]">
                          <Info className="mr-1 inline h-3.5 w-3.5 align-[-2px]" />
                          <strong>알림:</strong> 일부 다운로드 범위는 아직 무결성 검사를 하지 않았습니다. 실행 또는 폴더 검사하기를 누르면 저장된 메타데이터를 기준으로 검사합니다.
                        </div>
                      )}
                </div>
              )}

              </>
            }
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
              <div className="grid gap-3 md:grid-cols-4">
                <Button variant="outline" className="w-full" onClick={handleInspectFolder} disabled={!!activeJobId || inspectRunning || runStarting}>
                  {inspectRunning ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FolderOpen className="mr-2 h-4 w-4" />}
                  폴더 검사하기
                </Button>
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
          <div className="flex h-14 items-center justify-center gap-2 rounded-xl border border-[color:var(--tv-border)] bg-[var(--tv-surface)] p-2 shadow-[var(--tv-shadow)] md:h-auto md:w-16 md:flex-col">
            <Button
              variant="outline"
              size="icon"
              onClick={() => {
                setDownloadPanelOpen((value) => !value);
                setNotificationPanelOpen(false);
                setSettingsPanelOpen(false);
              }}
              className={
                activeJobId
                  ? "relative h-10 w-10 border-[color:var(--tv-accent)] bg-[var(--tv-accent-soft)] text-[var(--tv-accent)] shadow-sm"
                  : "relative h-10 w-10 border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-muted)] shadow-sm"
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
              className={
                lastInspectionCandidateCount > 0 || isErrorStatus || !!previewResult
                  ? "relative h-10 w-10 border-[color:var(--tv-warning)] bg-[var(--tv-warning-soft)] text-[var(--tv-warning-text)] shadow-sm"
                  : "relative h-10 w-10 border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-muted)] shadow-sm"
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
              className={
                settingsPanelOpen
                  ? "h-10 w-10 border-[color:var(--tv-border-strong)] bg-[var(--tv-surface)] text-[var(--tv-text)] shadow-sm"
                  : "h-10 w-10 border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-muted)] shadow-sm"
              }
              title={settingsPanelOpen ? "다운로드 설정 닫기" : "다운로드 설정 열기"}
            >
              <Settings className="h-5 w-5" />
            </Button>
          </div>

          {notificationPanelOpen && (
            <Card className="fixed inset-x-4 bottom-20 max-h-[calc(100vh-7rem)] overflow-auto border-[color:var(--tv-border)] bg-[var(--tv-surface)] shadow-lg md:absolute md:inset-x-auto md:bottom-auto md:right-full md:top-0 md:mr-3 md:w-[min(420px,calc(100vw-2rem))] md:max-h-[calc(100vh-8rem)]">
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
            <Card className="fixed inset-x-4 bottom-20 max-h-[calc(100vh-7rem)] overflow-auto border-[color:var(--tv-border)] bg-[var(--tv-surface)] shadow-lg md:absolute md:inset-x-auto md:bottom-auto md:right-full md:top-0 md:mr-3 md:w-[min(420px,calc(100vw-2rem))] md:max-h-[calc(100vh-8rem)]">
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
                  <div className="flex items-center space-x-2">
                    <Checkbox id="resumeYearly" checked={resumeYearly} onCheckedChange={(v) => setResumeYearly(!!v)} className="border-[color:var(--tv-border)]" />
                    <Label htmlFor="resumeYearly" className="cursor-pointer dark:text-slate-300">연간 작업 재개</Label>
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
                    <Input type="number" value={workerCount} onChange={(e) => setWorkerCount(e.target.value)} className={htmlControlClassName} />
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
            <Card className="fixed inset-x-4 bottom-20 max-h-[calc(100vh-7rem)] overflow-auto border-[color:var(--tv-border)] bg-[var(--tv-surface)] shadow-lg md:absolute md:inset-x-auto md:bottom-auto md:right-full md:top-0 md:mr-3 md:w-[min(420px,calc(100vw-2rem))] md:max-h-[calc(100vh-8rem)]">
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
