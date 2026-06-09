"use client"

import { useState, useEffect, useCallback, useRef } from "react";
import { Activity, Bell, X, Play, Search, Loader2, Trash2, FolderOpen, Square, Settings, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { Checkbox } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { cancelDownload, fetchDownloadOptions, inspectDownloadFolder, previewDownload, startDownload, detectExistingDownload, createMetadata } from "@/features/download/api";
import type { DisclosureItem, DownloadOptions, DownloadPayload } from "@/features/download/types";
import { UI_TEXT } from "@/config/uiText";

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
  const [checkingExisting, setCheckingExisting] = useState(false);
  const [runStarting, setRunStarting] = useState(false);
  const isRunTriggeredRef = useRef(false);
  const capturedPayloadRef = useRef<DownloadPayload | null>(null);
  const activeInspectionKeyRef = useRef<string | null>(null);
  const checkExistingRequestRef = useRef({ id: 0, key: "" });
  const [lastInspectedExistingKey, setLastInspectedExistingKey] = useState<string | null>(null);

  const { download_output_directory: outputDirectory, saveSetting } = useSettingsStore();

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
        setResult(data.result || data);
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
  const [expandedDisclosureGroups, setExpandedDisclosureGroups] = useState<Record<string, boolean>>({});

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
      const data = await fetchDownloadOptions();
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
  }, []);

  useEffect(() => {
    fetchOptions();
  }, [fetchOptions]);

  const checkExisting = useCallback(async (dir: string) => {
    if (!dir) {
      checkExistingRequestRef.current = { id: checkExistingRequestRef.current.id + 1, key: "" };
      setCheckingExisting(false);
      setExistingData(null);
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

    try {
      const result = await detectExistingDownload(submittedPayload);
      if (
        checkExistingRequestRef.current.id !== requestId ||
        checkExistingRequestRef.current.key !== requestKey ||
        dir !== useSettingsStore.getState().download_output_directory
      ) {
        return;
      }
      if (result && result.has_existing) {
        setExistingData(result);
      } else {
        setExistingData(null);
      }
    } catch {
      if (
        checkExistingRequestRef.current.id === requestId &&
        checkExistingRequestRef.current.key === requestKey &&
        dir === useSettingsStore.getState().download_output_directory
      ) {
        setExistingData(null);
      }
    } finally {
      if (
        checkExistingRequestRef.current.id === requestId &&
        checkExistingRequestRef.current.key === requestKey &&
        dir === useSettingsStore.getState().download_output_directory
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

  const handleCreateMetadata = async (range: any, force = false) => {
    try {
      setStatus(`[${range.folder_name}] 메타데이터 생성 체크 중...`);
      setIsErrorStatus(false);
      
      const folderPath = range.folder_path;
      
      const payload = {
        output_directory: folderPath,
        start_date: range.start_date,
        end_date: range.end_date,
        company_name: companyName,
        submitter_name: submitterName,
        market_label: marketLabel,
        securities_label: securitiesLabel,
        disclosure_type_groups: selectedDisclosures,
        last_report_only: lastReportOnly,
        page_size: Number(pageSize),
        wait_seconds: Number(waitSeconds),
        timeout: Number(timeout),
        force: force,
      };

      const res = await createMetadata(payload);
      if (res.success) {
        setStatus(`[${range.folder_name}] 메타데이터가 성공적으로 생성되었습니다.`);
        await checkExisting(outputDirectory);
      } else {
        setStatus(`[${range.folder_name}] 메타데이터 작성 보류: ${res.message}`);
        setIsErrorStatus(true);
        
        const confirmForce = window.confirm(
          `${res.message}\n\n현재 검색 설정으로 메타데이터를 강제로 작성하시겠습니까?`
        );
        if (confirmForce) {
          await handleCreateMetadata(range, true);
        }
      }
    } catch (err: any) {
      setStatus(`[${range.folder_name}] 메타데이터 작성 중 오류가 발생했습니다: ${err.message}`);
      setIsErrorStatus(true);
    }
  };

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
    log_limit: Number(logLimit),
    start_page: Number(startPage),
    end_page: endPage ? Number(endPage) : null,
    last_report_only: lastReportOnly,
    resume_yearly: resumeYearly,
    disclosure_type_groups: selectedDisclosures,
  });

  const handlePreview = async () => {
    try {
      setStatus("미리보기 생성 중...");
      const data = await previewDownload(buildPayload());
      setResult(data);
      setStatus("미리보기 완료");
      setNotificationPanelOpen(true);
      setDownloadPanelOpen(false);
      setSettingsPanelOpen(false);
    } catch (err: any) {
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
      `대상 페이지: ${data.requested_count || data.summary?.total || 0}`,
      `연도별 분할: ${data.split_by_year ? "On" : "Off"}`,
      `${deleted ? "삭제 파일" : "삭제 예정 파일"}: ${deleted ? data.deleted_count || 0 : data.deletion_candidate_count || 0}`,
      `추가 다운로드 필요: ${data.download_needed_count || 0}건`,
      `최신 상태: 성공 ${data.summary?.success || 0}/${data.summary?.total || 0}건`,
      `저장 경로: ${data.output_directory || ""}`,
    ];
    if (files.length) {
      lines.push("", deleted ? "삭제한 파일" : "삭제 예정 파일", ...files.map((file: any) => `- ${file.name} (${file.reason})`));
    }
    return lines.join("\n");
  };

  const handleInspectFolder = async () => {
    if (!outputDirectory) {
      setStatus("저장 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      setInspectRunning(true);
      setIsErrorStatus(false);
      setStatus("폴더 검사 작업을 시작하는 중...");
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
    if (runStarting) return;
    try {
      setRunStarting(true);
      if (existingData?.saved_filters && !filtersMatch) {
        throw new Error("현재 입력된 검색 필터가 기존 다운로드 폴더의 메타데이터와 다릅니다. 필터를 먼저 일치시켜 주세요.");
      }
      const payload = buildPayload();
      capturedPayloadRef.current = payload;
      isRunTriggeredRef.current = true;
      setIsErrorStatus(false);
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

  const toggleDisclosure = (suffix: string, code: string) => {
    setSelectedDisclosures(prev => {
      const current = prev[suffix] || [];
      const next = current.includes(code)
        ? current.filter(c => c !== code)
        : [...current, code];

      const newObj = { ...prev };
      if (next.length === 0) delete newObj[suffix];
      else newObj[suffix] = next;
      return newObj;
    });
  };

  const selectGroup = (suffix: string, items: DisclosureItem[]) => {
    setSelectedDisclosures(prev => ({
      ...prev,
      [suffix]: items.map(i => i.code)
    }));
  };

  const clearGroup = (suffix: string) => {
    setSelectedDisclosures(prev => {
      const newObj = { ...prev };
      delete newObj[suffix];
      return newObj;
    });
  };

  const toggleDisclosureGroup = (suffix: string) => {
    setExpandedDisclosureGroups(prev => ({
      ...prev,
      [suffix]: !prev[suffix],
    }));
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
      <div className="relative space-y-6" onClick={() => setNotificationPanelOpen(false)}>
        <section className="min-w-0 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Download Settings</p>
              <CardTitle className="dark:text-white">기본 설정</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label className="dark:text-slate-300">저장 경로</Label>
                <PathPickerInput
                  value={outputDirectory}
                  onChange={(val) => saveSetting("download_output_directory", val)}
                  placeholder="저장 경로를 선택하세요"
                  mode="folder"
                  onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                />
              </div>

              {checkingExisting && !existingData && (
                <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50/50 p-4 dark:border-[#30363d] dark:bg-[#161b22] text-sm animate-fade-in transition-all">
                  <div className="flex items-start gap-3">
                    <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-slate-500 dark:text-slate-400" />
                    <div className="space-y-1">
                      <p className="font-semibold text-slate-900 dark:text-slate-100">기존 다운로드 폴더 확인 중...</p>
                      <p className="break-all text-xs text-slate-500 dark:text-slate-400">
                        선택한 저장 경로의 폴더와 메타데이터 상태만 빠르게 확인하고 있습니다: {outputDirectory}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {existingData && existingData.has_existing && (
                <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50/50 p-4 dark:border-[#30363d] dark:bg-[#161b22] text-sm animate-fade-in transition-all">
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-200 pb-3 dark:border-[#30363d]">
                        <div className="space-y-1">
                          <p className="font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
                            📂 기존 다운로드 시도 범위 감지됨
                            {checkingExisting && (
                              <span className="inline-flex items-center gap-1 text-[10px] font-medium text-slate-500 dark:text-slate-400">
                                <Loader2 className="h-3 w-3 animate-spin" />
                                재확인 중
                              </span>
                            )}
                          </p>
                          <p className="text-xs text-slate-500 dark:text-slate-400">
                            전체 범위: <span className="font-semibold">{existingData?.earliest_date}</span> ~ <span className="font-semibold">{existingData?.latest_date}</span>
                          </p>
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-8 shrink-0 self-start md:self-auto border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-[#21262d] dark:hover:text-slate-100"
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
                          const statusColors = {
                            validated: "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-950/20 dark:text-teal-300 dark:border-teal-900/40",
                            stale: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/20 dark:text-rose-300 dark:border-rose-900/40",
                            unverified: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/20 dark:text-amber-300 dark:border-amber-900/40",
                          };
                          const statusLabels = {
                            validated: "검증 완료: KIND 건수 일치",
                            stale: "검증 실패: KIND 건수 불일치 (stale)",
                            unverified: range.metadata_status === "mismatch"
                              ? "메타데이터 설정 불일치"
                              : range.metadata_missing
                                ? (range.metadata_obsolete ? "구버전 메타데이터: 실행 시 보정 검사" : "메타데이터 없음: 실행 시 보정 검사")
                                : "메타데이터 확인됨",
                          };

                          return (
                            <div
                              key={index}
                              className="flex flex-col sm:flex-row sm:items-center justify-between p-2 rounded border dark:bg-[#0d1117] dark:border-[#30363d] gap-2 text-xs"
                            >
                              <div className="space-y-0.5">
                                <p className="font-medium text-slate-800 dark:text-slate-200">
                                  {range.folder_name} ({range.start_date} ~ {range.end_date})
                                </p>
                                <p className="text-[10px] text-slate-500 dark:text-slate-400">
                                  로컬 건수: {range.local_count ?? "-"} | KIND 건수: {range.kind_count ?? "-"}
                                </p>
                                {range.error_detail && (
                                  <p className="text-[10px] text-rose-500 dark:text-rose-400 font-medium">
                                    ⚠ {range.error_detail}
                                  </p>
                                )}
                                {range.metadata_missing && (
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleCreateMetadata(range);
                                    }}
                                    className="mt-1.5 px-2 py-0.5 bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200 rounded text-[10px] font-semibold transition-all dark:bg-blue-950/20 dark:text-blue-300 dark:border-blue-900/40 dark:hover:bg-blue-900/30"
                                  >
                                    현재 설정으로 메타데이터 작성
                                  </button>
                                )}
                              </div>
                              <span className={`px-2 py-0.5 text-[10px] font-semibold rounded-full border ${statusColors[range.status]}`}>
                                {statusLabels[range.status]}
                              </span>
                            </div>
                          );
                        })}
                      </div>

                      {/* Warning message if stale ranges exist */}
                      {existingData?.ranges?.some(r => r.status === "stale") && (
                        <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-200">
                          <strong>⚠ 경고:</strong> 기존 다운로드한 데이터 중 일부가 KIND의 현재 검색 결과와 일치하지 않습니다 (데이터 변경/정정/누락 가능성). 
                          무결성이 손상되었으므로 <strong>이어서 다운로드하기가 기본 비활성화</strong>됩니다. mismatch 폴더를 수동으로 검사/보완하거나 삭제 후 재실행해야 합니다.
                        </div>
                      )}

                      {/* Warning message if filters mismatch */}
                      {!filtersMatch && existingData?.saved_filters && (
                        <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-200">
                          <strong>⚠ 오류:</strong> 현재 입력된 검색 필터가 기존 다운로드 폴더의 메타데이터와 다릅니다. 폴더 내 데이터가 오염(mixed dataset)되는 것을 방지하기 위해 <strong>이어서 다운로드하기가 비활성화</strong>됩니다. 검색 필터를 메타데이터와 동일하게 일치시키거나 다른 경로를 선택해 주세요.
                          <div className="mt-2 pl-3 border-l-2 border-rose-300 space-y-1 text-[11px] opacity-90">
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
                            className="mt-3 h-8 border-rose-300 bg-white text-rose-800 hover:bg-rose-100 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200 dark:hover:bg-rose-900/30"
                            onClick={handleApplySavedFilters}
                          >
                            기존 메타데이터 기준으로 설정 맞추기
                          </Button>
                        </div>
                      )}

                      {existingData?.ranges?.some(r => r.status === "unverified") && !hasCompletedCurrentInspection && (
                        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
                          <strong>💡 알림:</strong> 일부 다운로드 범위는 {existingData.ranges?.some(r => r.metadata_obsolete) ? "workflow 메타데이터가 구버전입니다" : existingData.ranges?.some(r => r.metadata_missing) ? "workflow 메타데이터가 없습니다" : "아직 무결성 검사를 하지 않았습니다"}. 실행 또는 폴더 검사하기를 누르면 현재 검색 설정을 기준으로 무결성 검사와 메타데이터 보정을 진행합니다.
                        </div>
                      )}
                </div>
              )}

              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">시작일</Label>
                  <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 dark:[color-scheme:dark]" />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">종료일</Label>
                  <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 dark:[color-scheme:dark]" />
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">회사명</Label>
                  <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">제출인</Label>
                  <Input value={submitterName} onChange={(e) => setSubmitterName(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">시장</Label>
                  <Select value={marketLabel} onValueChange={setMarketLabel}>
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"><SelectValue /></SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      {options?.market_types.map(t => <SelectItem key={t.label} value={t.label}>{t.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">증권종류</Label>
                  <Select value={securitiesLabel} onValueChange={setSecuritiesLabel}>
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"><SelectValue /></SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      {options?.securities_types.map(t => <SelectItem key={t.label} value={t.label}>{t.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Disclosure Types</p>
              <CardTitle className="dark:text-white">공시 종류</CardTitle>
              <CardDescription className="dark:text-slate-400">다운로드할 공시 종류를 선택하세요.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {options?.disclosure_groups.map((group) => (
                <div key={group.suffix} className="border rounded-lg overflow-hidden dark:border-[#30363d]">
                  <div className="bg-slate-50 dark:bg-[#0d1117] px-4 py-2 border-b dark:border-[#30363d] flex items-center justify-between gap-3">
                    <button
                      type="button"
                      onClick={() => toggleDisclosureGroup(group.suffix)}
                      className="flex min-w-0 flex-1 items-center gap-2 text-left font-semibold text-sm dark:text-slate-200"
                    >
                      {expandedDisclosureGroups[group.suffix] ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
                      <span className="truncate">{group.label} ({group.items.length})</span>
                    </button>
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-[#21262d]"
                        onClick={() => selectGroup(group.suffix, group.items)}
                      >
                        전체 선택
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-[#21262d]"
                        onClick={() => clearGroup(group.suffix)}
                      >
                        전체 해제
                      </Button>
                    </div>
                  </div>
                  {expandedDisclosureGroups[group.suffix] && (
                    <div className="p-4 grid grid-cols-2 md:grid-cols-3 gap-2">
                      {group.items.map((item) => (
                        <div key={item.code} className="flex items-center space-x-2">
                          <Checkbox
                            id={`${group.suffix}-${item.code}`}
                            checked={selectedDisclosures[group.suffix]?.includes(item.code) || false}
                            onCheckedChange={() => toggleDisclosure(group.suffix, item.code)}
                            className="dark:border-[#30363d]"
                          />
                          <Label
                            htmlFor={`${group.suffix}-${item.code}`}
                            className="text-xs cursor-pointer truncate dark:text-slate-400 dark:hover:text-slate-200"
                            title={item.name}
                          >
                            {item.name}
                          </Label>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Run</p>
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

        <div className="absolute left-full top-0 z-40 ml-2" onClick={(event) => event.stopPropagation()}>
          <div className="flex w-16 flex-col items-center gap-2 rounded-lg border border-slate-200 bg-white p-2 shadow-lg dark:border-[#30363d] dark:bg-[#161b22]">
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
                  ? "relative h-10 w-10 border-blue-300 bg-blue-50 text-blue-700 shadow-sm dark:border-blue-500/60 dark:bg-blue-500/15 dark:text-blue-200"
                  : "relative h-10 w-10 border-slate-200 bg-white shadow-sm dark:border-[#30363d] dark:bg-[#161b22] dark:text-slate-300"
              }
              title={downloadPanelOpen ? "실행 현황 닫기" : "실행 현황 열기"}
            >
              <Activity className="h-5 w-5" />
              {activeJobId && (
                <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-blue-500 dark:bg-blue-300" />
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
                lastInspectionCandidateCount > 0 || deleteConfirmed || !!result || isErrorStatus
                  ? "relative h-10 w-10 border-amber-300 bg-amber-50 text-amber-700 shadow-sm dark:border-amber-500/60 dark:bg-amber-500/15 dark:text-amber-200"
                  : "relative h-10 w-10 border-slate-200 bg-white shadow-sm dark:border-[#30363d] dark:bg-[#161b22] dark:text-slate-300"
              }
              title={notificationPanelOpen ? "알림 닫기" : "알림 열기"}
            >
              <Bell className="h-5 w-5" />
              {(lastInspectionCandidateCount > 0 || !!result || isErrorStatus) && (
                <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-amber-500 dark:bg-amber-300" />
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
                  ? "h-10 w-10 border-slate-400 bg-slate-100 text-slate-900 shadow-sm dark:border-slate-500 dark:bg-[#21262d] dark:text-slate-100"
                  : "h-10 w-10 border-slate-200 bg-white shadow-sm dark:border-[#30363d] dark:bg-[#161b22] dark:text-slate-300"
              }
              title={settingsPanelOpen ? "다운로드 설정 닫기" : "다운로드 설정 열기"}
            >
              <Settings className="h-5 w-5" />
            </Button>
          </div>

          {notificationPanelOpen && (
            <Card className="absolute right-full top-0 mr-3 w-[min(420px,calc(100vw-2rem))] max-h-[calc(100vh-8rem)] overflow-auto shadow-xl dark:bg-[#161b22] dark:border-[#30363d]">
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="dark:text-white">알림</CardTitle>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setNotificationPanelOpen(false)}
                    className="h-8 w-8 dark:hover:bg-[#21262d]"
                    title="알림 닫기"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">작업 알림</Label>
                  <JobStatusLogger status={status} isErrorStatus={isErrorStatus} />
                </div>

                {lastInspectionCandidateCount > 0 && (
                  <div className="space-y-4 border-t border-slate-200 pt-4 dark:border-[#30363d]">
                    <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
                      삭제 예정 파일 {lastInspectionCandidateCount}개
                    </div>
                    <div className="flex items-center space-x-2">
                      <Checkbox id="downloadDeleteConfirmed" checked={deleteConfirmed} onCheckedChange={(v) => setDeleteConfirmed(!!v)} className="dark:border-[#30363d]" />
                      <Label htmlFor="downloadDeleteConfirmed" className="cursor-pointer text-sm dark:text-slate-300">삭제 허가</Label>
                    </div>
                    <div className="space-y-2">
                      <Label className="dark:text-slate-300">확인 문구</Label>
                      <Input
                        value={deleteConfirmationText}
                        onChange={(e) => setDeleteConfirmationText(e.target.value)}
                        placeholder="확인했습니다."
                        className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
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
                      삭제 예정 파일 {lastInspectionCandidateCount}개 삭제
                    </Button>
                  </div>
                )}

                {result && (
                  <div className="space-y-2 border-t border-slate-200 pt-4 dark:border-[#30363d]">
                    <Label className="dark:text-slate-300">결과</Label>
                    <pre className="max-h-72 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 dark:border-slate-700 dark:bg-[#090d12] dark:text-blue-100">
                      {JSON.stringify(result, null, 2)}
                    </pre>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {settingsPanelOpen && (
            <Card className="absolute right-full top-0 mr-3 w-[min(420px,calc(100vw-2rem))] max-h-[calc(100vh-8rem)] overflow-auto shadow-xl dark:bg-[#161b22] dark:border-[#30363d]">
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="dark:text-white">다운로드 설정</CardTitle>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setSettingsPanelOpen(false)}
                    className="h-8 w-8 dark:hover:bg-[#21262d]"
                    title="다운로드 설정 닫기"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="space-y-3">
                  <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">요청 설정</p>
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">페이지 크기</Label>
                    <Input type="number" value={pageSize} onChange={(e) => setPageSize(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">대기 시간 (초)</Label>
                    <Input type="number" value={waitSeconds} onChange={(e) => setWaitSeconds(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">타임아웃 (초)</Label>
                    <Input type="number" value={timeout} onChange={(e) => setTimeoutVal(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">작업 범위</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label className="dark:text-slate-300">시작 페이지</Label>
                      <Input type="number" value={startPage} onChange={(e) => setStartPage(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                    </div>
                    <div className="space-y-2">
                      <Label className="dark:text-slate-300">종료 페이지</Label>
                      <Input type="number" placeholder="전체" value={endPage} onChange={(e) => setEndPage(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Checkbox id="lastReportOnly" checked={lastReportOnly} onCheckedChange={(v) => setLastReportOnly(!!v)} className="dark:border-[#30363d]" />
                    <Label htmlFor="lastReportOnly" className="cursor-pointer dark:text-slate-300">최종보고서만</Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Checkbox id="resumeYearly" checked={resumeYearly} onCheckedChange={(v) => setResumeYearly(!!v)} className="dark:border-[#30363d]" />
                    <Label htmlFor="resumeYearly" className="cursor-pointer dark:text-slate-300">연간 작업 재개</Label>
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">실행 옵션</p>
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">워커 수</Label>
                    <Input type="number" value={workerCount} onChange={(e) => setWorkerCount(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">로그 줄 수</Label>
                    <Input type="number" value={logLimit} onChange={(e) => setLogLimit(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {downloadPanelOpen && (
            <Card className="absolute right-full top-0 mr-3 w-[min(420px,calc(100vw-2rem))] max-h-[calc(100vh-8rem)] overflow-auto shadow-xl dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                  <CardTitle className="dark:text-white">실행 현황</CardTitle>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setDownloadPanelOpen(false)}
                  className="h-8 w-8 dark:hover:bg-[#21262d]"
                  title="실행 현황 닫기"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <Label className="dark:text-slate-300">작업 상태</Label>
                  <Button
                    variant="outline"
                    onClick={handleCancelDownload}
                    disabled={!activeJobId}
                    className="h-8 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-300"
                  >
                    <Square className="mr-2 h-4 w-4" />
                    {UI_TEXT.actions.cancelJob}
                  </Button>
                </div>
                <JobStatusLogger
                  status={status}
                  isErrorStatus={isErrorStatus}
                />
              </div>

              {result && result.format !== "kind_download_folder_cleanup_v1" && (
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">실행 결과 요약</Label>
                  <div className="grid grid-cols-1 gap-2 mt-2">
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:bg-[#0d1117] dark:border-[#30363d]">
                      <span className="text-xs font-bold text-slate-500 dark:text-slate-400">성공 / 전체</span>
                      <strong className="mt-1 block text-xl font-bold text-slate-950 dark:text-slate-100">{result.summary?.success || result.success_count || 0}/{result.summary?.total || result.total_count || result.summary?.success || 0}</strong>
                    </div>
                  </div>
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
