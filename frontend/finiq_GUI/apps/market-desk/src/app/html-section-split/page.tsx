"use client"

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Play, Square } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Label } from "@finiq/ui";
import { PageLoadingSpinner } from "@finiq/web-app/status";
import { useJobPolling } from "@/hooks/useJobPolling";
import { useSettingsStore } from "@/store/useSettingsStore";
import { SETTINGS_LABELS, UI_TEXT } from "@/config/uiText";
import {
  HtmlWorkflowCard,
  HtmlWorkflowPage,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import {
  DATA_PATH_LABELS,
  type DataPathField,
} from "@/components/data-path/DataPathCard";
import { formatInteger } from "@/lib/format";
import {
  HtmlSectionSplitActionDock,
  HtmlSectionSplitResults,
  HtmlSectionStructureTypes,
  type DocumentRow,
  type InspectResult,
  type ReviewView,
  type SectionPattern,
  type SplitResult,
} from "./_components/HtmlSectionSplitResults";
import {
  SingleCheckDataIntegrityInspectionCard,
  type SingleCheckDataIntegrityInspectionState,
} from "@/components/data-integrity/DataIntegrityInspectionCard";
import {
  FilterPresetCombobox,
  type DisclosureConditionPreset,
} from "@/components/disclosures/DisclosureConditionFilterCard";
import { listDisclosureConditionPresets } from "@/lib/disclosureConditionPresets";

const presetIdentity = (preset: DisclosureConditionPreset) => (
  preset.id || (preset.parent_mode ? `${preset.parent_mode}/${preset.mode}` : preset.mode)
);

const presetLabel = (preset: DisclosureConditionPreset) => (
  preset.parent_mode ? `${preset.parent_mode} › ${preset.mode}` : preset.mode
);

function statusLabel(status: string) {
  if (status === "queued") return "대기 중";
  if (status === "running") return "실행 중";
  if (status === "completed") return "완료";
  if (status === "failed") return "실패";
  return status || "-";
}

function parseOptionalNumber(value: string) {
  const trimmed = value.trim();
  return trimmed ? Number(trimmed) : null;
}

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

export default function HtmlSectionSplitPage() {
  const {
    output_root: dataRoot,
    html_parse_mode: htmlParseMode,
    disclosure_separate_output_directory: useSeparateOutputDirectory,
    fetchSettings,
    saveSetting,
  } = useSettingsStore();
  const [loading, setLoading] = useState(true);
  const [inputDirectory, setInputDirectory] = useState("");
  const [outputDirectory, setOutputDirectory] = useState("");
  const [limit, setLimit] = useState("20");
  const [reportLimit, setReportLimit] = useState("50");
  const [progressInterval, setProgressInterval] = useState("25");
  const [workers, setWorkers] = useState("1");
  const [filterPresets, setFilterPresets] = useState<DisclosureConditionPreset[]>([]);
  const [selectedFilterId, setSelectedFilterId] = useState("");
  const [inspectResult, setInspectResult] = useState<InspectResult | null>(null);
  const [integrityInspectionResult, setIntegrityInspectionResult] = useState<InspectResult | null>(null);
  const [integrityInspectionError, setIntegrityInspectionError] = useState("");
  const [sectionPatterns, setSectionPatterns] = useState<SectionPattern[] | null>(null);
  const [page, setPage] = useState(1);
  const [selectedDocument, setSelectedDocument] = useState<DocumentRow | null>(null);
  const [selectedSourceUrl, setSelectedSourceUrl] = useState("");
  const [splitResult, setSplitResult] = useState<SplitResult | null>(null);
  const [selectedSectionId, setSelectedSectionId] = useState("");
  const [activeReviewView, setActiveReviewView] = useState<ReviewView>("source");
  const [isSplitting, setIsSplitting] = useState(false);
  const [isInspecting, setIsInspecting] = useState(false);
  const [isIntegrityInspecting, setIsIntegrityInspecting] = useState(false);
  const inspectAbortControllerRef = useRef<AbortController | null>(null);
  const integrityInspectAbortControllerRef = useRef<AbortController | null>(null);
  const activeJobIdRef = useRef<string | null>(null);
  const activeIntegrityInspectionRef = useRef<{ jobId: string; key: string } | null>(null);
  const currentIntegrityInspectionKeyRef = useRef("");

  const cancelActiveIntegrityInspection = useCallback(() => {
    const inspection = activeIntegrityInspectionRef.current;
    activeIntegrityInspectionRef.current = null;
    if (!inspection?.jobId) return;
    fetch("/api/disclosures/html/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: inspection.jobId }),
    }).catch(() => undefined);
  }, []);

  const formatStatus = useCallback((data: any) => {
    const res = data.result || {};
    const summary = res.summary || {};
    const lines = [`작업 상태: ${statusLabel(data.status)}`];
    if (data.error) lines.push(`오류: ${data.error}`);
    if (summary.found_files !== undefined) {
      lines.push(`대상 HTML: ${formatInteger(summary.found_files)}`);
      if (res.format === "finiq_disclosure_html_section_inspect_v1") {
        lines.push(`공시 표시: ${formatInteger(summary.documents_with_sections)}`);
        lines.push(`목차 없음: ${formatInteger(summary.files_without_sections)}`);
        lines.push(`읽기 실패: ${formatInteger(summary.failed_files)}`);
      } else {
        lines.push(`저장 대상: ${formatInteger(summary.expected_files)}`);
        lines.push(`저장 완료: ${formatInteger(summary.saved_files)}`);
        lines.push(`누락 파일: ${formatInteger(summary.missing_files)}`);
        lines.push(`건너뜀: ${formatInteger(summary.skipped_files)}`);
        lines.push(`${DATA_PATH_LABELS.workspace}: ${res.output_directory || ""}`);
      }
    }
    if (Array.isArray(data.progress_log) && data.progress_log.length) {
      lines.push("", "최근 로그", ...data.progress_log);
    }
    return lines;
  }, []);

  const {
    status,
    isErrorStatus,
    activeJobId,
    startPolling,
    setStatus,
    setIsErrorStatus,
    cancelJob,
  } = useJobPolling({
    pollingEndpoint: "/api/disclosures/html/jobs/{jobId}",
    cancelEndpoint: "/api/disclosures/html/cancel",
    onSuccess: (data, jobId) => {
      const inspectionContext = activeIntegrityInspectionRef.current;
      if (inspectionContext?.jobId === jobId) {
        activeIntegrityInspectionRef.current = null;
        setIsIntegrityInspecting(false);
        if (inspectionContext.key !== currentIntegrityInspectionKeyRef.current) return;
        if (data?.format !== "finiq_disclosure_html_section_inspect_v1") {
          setIntegrityInspectionError("입력 HTML 검사 결과 형식이 올바르지 않습니다.");
          return;
        }
        setIntegrityInspectionResult(data);
        setIntegrityInspectionError("");
        setStatus(`입력 HTML 검사 완료: ${formatInteger(data.summary?.found_files || 0)}개`);
        return;
      }
      if (data?.format === "finiq_disclosure_html_section_inspect_v1") {
        setInspectResult(data);
        setStatus(`폴더 열기 완료: ${formatInteger(data.summary?.documents_with_sections || 0)}개 공시`);
      }
      if (data?.format === "finiq_disclosure_html_section_save_v2") {
        setSectionPatterns(data.section_patterns || []);
      }
      setIsInspecting(false);
    },
    onError: (error, jobId) => {
      const inspectionContext = activeIntegrityInspectionRef.current;
      if (inspectionContext?.jobId === jobId) {
        activeIntegrityInspectionRef.current = null;
        setIsIntegrityInspecting(false);
        if (inspectionContext.key !== currentIntegrityInspectionKeyRef.current) return;
        setIntegrityInspectionError(error.message);
      }
      setIsInspecting(false);
    },
    onCancel: (jobId) => {
      const inspectionContext = activeIntegrityInspectionRef.current;
      if (inspectionContext?.jobId === jobId) {
        activeIntegrityInspectionRef.current = null;
        setIsIntegrityInspecting(false);
        if (inspectionContext.key !== currentIntegrityInspectionKeyRef.current) return;
      }
      setIsInspecting(false);
      setStatus("작업을 중단했습니다.");
      setIsErrorStatus(false);
    },
    formatStatus,
  });

  const documents = inspectResult?.documents || [];
  const problemFiles = inspectResult?.problem_files || [];
  const reviewedInputDirectory = inspectResult?.input_directory || inputDirectory;
  const hasNextPage = Boolean(inspectResult?.summary?.has_next_page);
  const isJobActive = !!activeJobId;
  const selectedFilterPreset = filterPresets.find(
    (preset) => presetIdentity(preset) === selectedFilterId,
  );
  const currentFilterMode = selectedFilterPreset?.mode || "";
  const currentParentMode = selectedFilterPreset?.parent_mode || "";
  const integrityInspectionPayload = {
    data_root: dataRoot,
    mode: currentFilterMode,
    ...(currentParentMode ? { parent_mode: currentParentMode } : {}),
    input_directory: useSeparateOutputDirectory ? inputDirectory : "",
    workers: parseOptionalNumber(workers),
    report_limit: parseOptionalNumber(reportLimit),
    progress_interval: parseOptionalNumber(progressInterval),
  };
  const currentIntegrityInspectionKey = JSON.stringify(integrityInspectionPayload);
  currentIntegrityInspectionKeyRef.current = currentIntegrityInspectionKey;

  useEffect(() => {
    activeJobIdRef.current = activeJobId;
  }, [activeJobId]);

  useEffect(() => {
    fetchSettings().then((config) => {
      const defaultInput = config.internal_html_output_directory || "";
      setInputDirectory(defaultInput || "");
      setOutputDirectory(config.html_section_split_output_directory || "");
      const workerCount = Number(config.parallel_worker_count);
      if (!Number.isInteger(workerCount) || workerCount < 1) {
        throw new Error("parallel_worker_count must be a positive integer");
      }
      setWorkers(String(workerCount));
    }).catch((err) => {
      setStatus(errorMessage(err));
      setIsErrorStatus(true);
    }).finally(() => {
      setLoading(false);
    });
  }, [fetchSettings, setIsErrorStatus, setStatus]);

  useEffect(() => {
    if (!dataRoot.trim()) {
      setFilterPresets([]);
      setSelectedFilterId("");
      return;
    }
    listDisclosureConditionPresets(dataRoot).then((response) => {
      setFilterPresets(response.presets.filter((preset) => !preset.parent_mode));
    }).catch((err) => {
      setFilterPresets([]);
      setSelectedFilterId("");
      setStatus(errorMessage(err));
      setIsErrorStatus(true);
    });
  }, [dataRoot, setIsErrorStatus, setStatus]);

  useEffect(() => {
    if (selectedFilterId || !htmlParseMode) return;
    const match = filterPresets.find(
      (preset) => !preset.parent_mode && preset.mode === htmlParseMode,
    );
    if (match) setSelectedFilterId(presetIdentity(match));
  }, [filterPresets, htmlParseMode, selectedFilterId]);

  useEffect(() => {
    return () => {
      inspectAbortControllerRef.current?.abort();
      integrityInspectAbortControllerRef.current?.abort();
      if (activeJobIdRef.current) {
        fetch("/api/disclosures/html/cancel", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_id: activeJobIdRef.current }),
        }).catch(() => undefined);
      }
      cancelActiveIntegrityInspection();
    };
  }, [cancelActiveIntegrityInspection]);

  const handleWorkspaceDirectoryChange = async (value: string) => {
    integrityInspectAbortControllerRef.current?.abort();
    integrityInspectAbortControllerRef.current = null;
    cancelActiveIntegrityInspection();
    if (await saveSetting("output_root", value)) {
      const settings = useSettingsStore.getState();
      setInputDirectory(settings.internal_html_output_directory || "");
      setOutputDirectory(settings.html_section_split_output_directory || "");
    }
    setInspectResult(null);
    setIntegrityInspectionResult(null);
    setIntegrityInspectionError("");
    setSectionPatterns(null);
    setIsIntegrityInspecting(false);
    setPage(1);
    setSelectedDocument(null);
    setSelectedSourceUrl("");
    setSplitResult(null);
    setSelectedSectionId("");
    setActiveReviewView("source");
  };

  useEffect(() => {
    integrityInspectAbortControllerRef.current?.abort();
    integrityInspectAbortControllerRef.current = null;
    cancelActiveIntegrityInspection();
    setIntegrityInspectionResult(null);
    setIntegrityInspectionError("");
    setSectionPatterns(null);
    setIsIntegrityInspecting(false);
  }, [
    currentFilterMode,
    currentParentMode,
    dataRoot,
    inputDirectory,
    useSeparateOutputDirectory,
    workers,
    cancelActiveIntegrityInspection,
  ]);

  const handleFilterInputChange = (value: string) => {
    if (value === selectedFilterId) return;
    inspectAbortControllerRef.current?.abort();
    if (activeJobId) cancelJob();
    setSelectedFilterId(value);
    setInspectResult(null);
    setSectionPatterns(null);
    setPage(1);
    resetSelectedDisclosure();
  };

  const handleFilterChange = async (value: string) => {
    handleFilterInputChange(value);
    const preset = filterPresets.find((item) => presetIdentity(item) === value);
    if (preset && !preset.parent_mode) {
      const saved = await saveSetting("html_parse_mode", preset.mode);
      if (saved) {
        const settings = useSettingsStore.getState();
        setInputDirectory(settings.internal_html_output_directory || "");
        setOutputDirectory(settings.html_section_split_output_directory || "");
      }
    }
  };

  const handleOutputDirectoryChange = (value: string) => {
    setOutputDirectory(value);
    setSectionPatterns(null);
    saveSetting("html_section_split_output_directory", value);
  };

  const handlePathError = (message: string) => {
    setStatus(message);
    setIsErrorStatus(true);
  };

  const folderPathFields: DataPathField[] = [
    {
      id: "inputDirectory",
      label: DATA_PATH_LABELS.workspace,
      value: dataRoot,
      onChange: handleWorkspaceDirectoryChange,
    },
    {
      id: "outputDirectory",
      label: DATA_PATH_LABELS.output,
      value: outputDirectory,
      onChange: handleOutputDirectoryChange,
      separateOutputOnly: true,
    },
  ];

  const splitOptionFields: HtmlWorkflowField[] = [
    {
      id: "limit",
      kind: "input",
      type: "number",
      label: "최대 표시 파일 수",
      value: limit,
      onChange: setLimit,
      span: 2,
    },
    {
      id: "reportLimit",
      kind: "input",
      type: "number",
      label: "문제 파일 표시 수",
      value: reportLimit,
      onChange: setReportLimit,
      span: 2,
    },
    {
      id: "progressInterval",
      kind: "input",
      type: "number",
      label: SETTINGS_LABELS.progressInterval,
      value: progressInterval,
      onChange: setProgressInterval,
      span: 2,
    },
    {
      id: "workers",
      kind: "input",
      type: "number",
      label: SETTINGS_LABELS.workerCount,
      value: workers,
      onChange: setWorkers,
      span: 2,
    },
  ];

  const sourceHtmlUrl = (document: DocumentRow) => {
    const params = new URLSearchParams({
      input_directory: reviewedInputDirectory,
      source_name: document.source_relative_path || document.source_name,
    });
    return `/api/disclosures/html/sections/source?${params.toString()}`;
  };

  const resetSelectedDisclosure = () => {
    setSelectedDocument(null);
    setSelectedSourceUrl("");
    setSplitResult(null);
    setSelectedSectionId("");
    setActiveReviewView("source");
  };

  const loadSourcePage = async (targetPage: number) => {
    if (!dataRoot || !currentFilterMode || (useSeparateOutputDirectory && !inputDirectory)) {
      setStatus("조건검색 필터와 작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    inspectAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    inspectAbortControllerRef.current = abortController;
    setIsInspecting(true);
    try {
      const configuredPageSize = Number(limit);
      if (!Number.isInteger(configuredPageSize) || configuredPageSize < 1) {
        throw new Error("page_size must be a positive integer");
      }
      const response = await fetch("/api/disclosures/html/sections/list", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortController.signal,
        body: JSON.stringify({
          data_root: dataRoot,
          mode: currentFilterMode,
          ...(currentParentMode ? { parent_mode: currentParentMode } : {}),
          input_directory: useSeparateOutputDirectory ? inputDirectory : "",
          page: targetPage,
          page_size: configuredPageSize,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "폴더 열기에 실패했습니다.");
      }
      const data = await response.json();
      setInspectResult(data);
      setPage(targetPage);
      resetSelectedDisclosure();
      setStatus(`폴더 열기 완료: ${formatInteger(data.summary?.returned_files || 0)}개 공시`);
      setIsErrorStatus(false);
    } catch (err: any) {
      if (err?.name === "AbortError") {
        return;
      }
      setStatus(errorMessage(err));
      setIsErrorStatus(true);
      setIsInspecting(false);
      setInspectResult(null);
      resetSelectedDisclosure();
    } finally {
      if (inspectAbortControllerRef.current === abortController) {
        inspectAbortControllerRef.current = null;
      }
      setIsInspecting(false);
    }
  };

  const inspectExistingData = async () => {
    if (!dataRoot || !currentFilterMode || (useSeparateOutputDirectory && !inputDirectory)) {
      setStatus("조건검색 필터와 작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    integrityInspectAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    integrityInspectAbortControllerRef.current = abortController;
    const inspectionKey = currentIntegrityInspectionKey;
    const requestedJobId = window.crypto.randomUUID().replaceAll("-", "");
    activeIntegrityInspectionRef.current = {
      jobId: requestedJobId,
      key: inspectionKey,
    };
    setIsIntegrityInspecting(true);
    setIntegrityInspectionResult(null);
    setIntegrityInspectionError("");
    setIsErrorStatus(false);
    setStatus("입력 HTML 전체를 검사하고 있습니다...");
    try {
      const response = await fetch("/api/disclosures/html/sections/inspect/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortController.signal,
        body: JSON.stringify({ ...integrityInspectionPayload, job_id: requestedJobId }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "입력 HTML 검사에 실패했습니다.");
      }
      const data = await response.json();
      const jobId = String(data.job_id || "");
      if (jobId !== requestedJobId) {
        if (activeIntegrityInspectionRef.current?.jobId === requestedJobId) {
          activeIntegrityInspectionRef.current = null;
        }
        throw new Error("입력 HTML 검사 작업 ID가 요청과 일치하지 않습니다.");
      }
      if (integrityInspectAbortControllerRef.current !== abortController
        || inspectionKey !== currentIntegrityInspectionKeyRef.current) {
        fetch("/api/disclosures/html/cancel", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_id: jobId }),
        }).catch(() => undefined);
        return;
      }
      startPolling(jobId);
    } catch (err: any) {
      if (activeIntegrityInspectionRef.current?.jobId === requestedJobId) {
        activeIntegrityInspectionRef.current = null;
      }
      if (err?.name === "AbortError") return;
      const message = errorMessage(err);
      setIntegrityInspectionError(message);
      setStatus(message);
      setIsErrorStatus(true);
      setIsIntegrityInspecting(false);
    } finally {
      if (integrityInspectAbortControllerRef.current === abortController) {
        integrityInspectAbortControllerRef.current = null;
      }
    }
  };

  const inspectFolder = () => {
    loadSourcePage(1);
  };

  const handlePreviousPage = () => {
    if (page > 1) {
      loadSourcePage(page - 1);
    }
  };

  const handleNextPage = () => {
    if (hasNextPage) {
      loadSourcePage(page + 1);
    }
  };

  const selectDocument = (document: DocumentRow, view: ReviewView) => {
    setSelectedDocument(document);
    setSelectedSourceUrl(sourceHtmlUrl(document));
    setSplitResult(null);
    setSelectedSectionId("");
    setActiveReviewView(view);
  };

  const splitDocument = async (document: DocumentRow) => {
    setIsSplitting(true);
    try {
      const response = await fetch("/api/disclosures/html/sections/source/split", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          input_directory: reviewedInputDirectory,
          source_name: document.source_relative_path || document.source_name,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "목차 분리에 실패했습니다.");
      }
      const data = await response.json();
      setSplitResult(data);
      setSelectedSectionId(data.sections?.[0]?.toc_id || "");
      setStatus(`목차 로딩 완료: ${formatInteger(data.section_count || 0)}개 목차`);
      setIsErrorStatus(false);
    } catch (err: any) {
      setStatus(errorMessage(err));
      setIsErrorStatus(true);
      setSplitResult(null);
      setSelectedSectionId("");
    } finally {
      setIsSplitting(false);
    }
  };

  const openDocument = (document: DocumentRow, view: ReviewView) => {
    selectDocument(document, view);
    if (!document.source_unavailable) {
      void splitDocument(document);
    }
  };

  const handleViewSource = (document: DocumentRow) => {
    openDocument(document, "source");
  };

  const handleViewSections = (document: DocumentRow) => {
    openDocument(document, "sections");
  };

  const cancelInspectFolder = () => {
    inspectAbortControllerRef.current?.abort();
    inspectAbortControllerRef.current = null;
    cancelJob();
    setStatus("작업 중단을 요청했습니다.");
    setIsErrorStatus(false);
  };

  const startSave = async () => {
    if (!dataRoot || !currentFilterMode || (useSeparateOutputDirectory && (!inputDirectory || !outputDirectory))) {
      setStatus("조건검색 필터와 작업공간 디렉토리를 확인하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      const response = await fetch("/api/disclosures/html/sections/save/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data_root: dataRoot,
          mode: currentFilterMode,
          ...(currentParentMode ? { parent_mode: currentParentMode } : {}),
          input_directory: useSeparateOutputDirectory ? inputDirectory : "",
          output_directory: useSeparateOutputDirectory ? outputDirectory : "",
          workers: parseOptionalNumber(workers),
          progress_interval: parseOptionalNumber(progressInterval),
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "목차 분리 작업을 시작하지 못했습니다.");
      }
      const data = await response.json();
      setSectionPatterns(null);
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(errorMessage(err));
      setIsErrorStatus(true);
    }
  };

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  const hasInspectionInput = !!dataRoot
    && !!currentFilterMode
    && (!useSeparateOutputDirectory || !!inputDirectory);
  const integrityProblemFiles = integrityInspectionResult?.problem_files || [];
  const integrityProblemCount = Number(integrityInspectionResult?.summary?.failed_files || 0)
    + Number(integrityInspectionResult?.summary?.files_without_sections || 0);
  const sourceUnavailableCount = Number(integrityInspectionResult?.summary?.source_unavailable_files || 0);
  const firstIntegrityProblem = integrityProblemFiles[0];
  const firstIntegrityProblemDescription = firstIntegrityProblem
    ? `${firstIntegrityProblem.source_relative_path || firstIntegrityProblem.source_file}: ${firstIntegrityProblem.error || "원인을 확인할 수 없습니다."}`
    : "";
  const inspectionState: SingleCheckDataIntegrityInspectionState = !hasInspectionInput
    ? "waiting"
    : isIntegrityInspecting
      ? "running"
      : integrityInspectionError
        ? "failed"
      : integrityInspectionResult
        ? integrityProblemCount > 0 ? "failed" : "success"
        : "ready";
  const inspectionCopy = {
    waiting: ["조건검색 필터와 경로를 선택하세요", "조건검색 필터와 작업공간 디렉토리를 선택한 다음 기존 원문의 목차 구성을 검사하세요."],
    ready: ["기존 원문 데이터 검사가 필요합니다", "목차 분리 전에 입력 HTML 전체의 구성을 확인하세요."],
    running: ["기존 원문 데이터를 확인하고 있습니다", "입력 HTML을 읽어 목차 구성과 문제 파일을 확인합니다."],
    success: ["기존 원문 데이터를 그대로 사용해도 됩니다", `목차가 있는 공시 ${formatInteger(integrityInspectionResult?.summary?.documents_with_sections || 0)}개를 확인했습니다.${sourceUnavailableCount > 0 ? ` KIND 원본 없음 ${formatInteger(sourceUnavailableCount)}건은 별도로 확인했습니다.` : ""}`],
    failed: ["기존 원문 데이터에 문제가 있습니다", integrityInspectionError || `문제 파일 ${formatInteger(integrityProblemCount)}개를 확인했습니다.${firstIntegrityProblemDescription ? ` 첫 문제: ${firstIntegrityProblemDescription}` : ""}`],
  }[inspectionState];
  const inspectionStepSummary = integrityInspectionError
    || (integrityInspectionResult
      ? `대상 ${formatInteger(integrityInspectionResult.summary?.found_files || 0)}개, 정상 ${formatInteger(integrityInspectionResult.summary?.documents_with_sections || 0)}개, KIND 원본 없음 ${formatInteger(sourceUnavailableCount)}개, 목차 없음 ${formatInteger(integrityInspectionResult.summary?.files_without_sections || 0)}개, 읽기 실패 ${formatInteger(integrityInspectionResult.summary?.failed_files || 0)}개입니다.${firstIntegrityProblemDescription ? ` 첫 문제: ${firstIntegrityProblemDescription}` : ""}`
      : "입력 HTML을 읽어 목차 구성과 문제 파일을 확인합니다.");

  return (
    <HtmlWorkflowPage
      eyebrow="Disclosure Section Desk"
      title="공시원문 목차 분리"
      description="KIND 내부 HTML 폴더를 열어 개별 공시 원문과 목차 분리 상태를 확인합니다."
    >
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          <SingleCheckDataIntegrityInspectionCard
            description="실행 전에 입력 HTML의 목차 구성과 문제 파일을 확인합니다."
            state={inspectionState}
            verdictTitle={inspectionCopy[0]}
            verdictDescription={inspectionCopy[1]}
            stepTitle="입력 HTML과 목차 구성 검사"
            stepSummary={inspectionStepSummary}
            action={hasInspectionInput ? {
              label: isIntegrityInspecting ? "검사 중..." : "검사하기",
              onClick: inspectExistingData,
              disabled: isIntegrityInspecting || isInspecting || isJobActive,
              loading: isIntegrityInspecting,
              showResultStatus: true,
            } : undefined}
          />

          <Card className="border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
            <CardHeader>
              <CardTitle className="dark:text-white">조건검색 필터</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2">
              <Label htmlFor="section-filter-preset" className="dark:text-slate-300">조건검색 필터</Label>
              <FilterPresetCombobox
                id="section-filter-preset"
                value={selectedFilterId}
                presets={filterPresets}
                onValueChange={handleFilterInputChange}
                onSelectExisting={handleFilterChange}
                getPresetIdentity={presetIdentity}
                getPresetLabel={presetLabel}
                allowCreate={false}
              />
            </CardContent>
          </Card>

          {/* LEGACY: 본문 데이터 경로 카드. 경로 입력은 우측 설정 패널(WorkflowPathSettings)로 옮겼다.
              <DataPathCard onError={handlePathError} fields={folderPathFields} /> */}

          <HtmlSectionSplitResults
            inputDirectory={reviewedInputDirectory}
            documents={documents}
            problemFiles={problemFiles}
            page={page}
            hasNextPage={hasNextPage}
            selectedDocument={selectedDocument}
            selectedSourceUrl={selectedSourceUrl}
            splitResult={splitResult}
            selectedSectionId={selectedSectionId}
            activeReviewView={activeReviewView}
            isInspecting={isInspecting}
            isSourceLoadDisabled={isInspecting || isJobActive}
            isSplitting={isSplitting}
            onInspectFolder={inspectFolder}
            onViewSource={handleViewSource}
            onViewSections={handleViewSections}
            onChangeReviewView={setActiveReviewView}
            onPreviousPage={handlePreviousPage}
            onNextPage={handleNextPage}
            onSelectSection={setSelectedSectionId}
          />

          <HtmlWorkflowCard title="작업 실행">
            <div className="grid gap-3 md:grid-cols-2">
              <Button className="h-10 w-full" onClick={startSave} disabled={isJobActive || isInspecting}>
                {isJobActive ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                실행
              </Button>
              <Button type="button" variant="outline" className="h-10 w-full" onClick={cancelInspectFolder} disabled={!isInspecting && !isJobActive}>
                <Square className="mr-2 h-4 w-4" />
                {UI_TEXT.actions.cancelJob}
              </Button>
            </div>
          </HtmlWorkflowCard>

          <HtmlSectionStructureTypes sectionPatterns={sectionPatterns} />
        </section>

        <HtmlSectionSplitActionDock
          dataRoot={dataRoot}
          isJobActive={isJobActive}
          isInspecting={isInspecting}
          status={status}
          isErrorStatus={isErrorStatus}
          problemFileCount={problemFiles.length}
          settingsFields={splitOptionFields}
          pathFields={folderPathFields}
          onPathError={handlePathError}
          onCancel={cancelInspectFolder}
        />
      </div>
    </HtmlWorkflowPage>
  );
}
