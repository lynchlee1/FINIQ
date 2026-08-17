"use client"

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Play, Square } from "lucide-react";
import { Button } from "@finiq/ui";
import { PageLoadingSpinner } from "@finiq/web-app/status";
import { useJobPolling } from "@/hooks/useJobPolling";
import { useSettingsStore } from "@/store/useSettingsStore";
import { UI_TEXT } from "@/config/uiText";
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

function waitForPollingInterval(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timeoutId = window.setTimeout(resolve, 1000);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timeoutId);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
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
  const [workers, setWorkers] = useState("1");
  const [inspectResult, setInspectResult] = useState<InspectResult | null>(null);
  const [integrityInspectionResult, setIntegrityInspectionResult] = useState<InspectResult | null>(null);
  const [integrityInspectionError, setIntegrityInspectionError] = useState("");
  const [sectionPatterns, setSectionPatterns] = useState<SectionPattern[]>([]);
  const [selectedPatternTocIds, setSelectedPatternTocIds] = useState<Record<string, string[]>>({});
  const [page, setPage] = useState(1);
  const [selectedDocument, setSelectedDocument] = useState<DocumentRow | null>(null);
  const [selectedSourceUrl, setSelectedSourceUrl] = useState("");
  const [splitResult, setSplitResult] = useState<SplitResult | null>(null);
  const [selectedSectionId, setSelectedSectionId] = useState("");
  const [activeReviewView, setActiveReviewView] = useState<ReviewView>("source");
  const [isSplitting, setIsSplitting] = useState(false);
  const [isInspecting, setIsInspecting] = useState(false);
  const [isIntegrityInspecting, setIsIntegrityInspecting] = useState(false);
  const [isLoadingSectionPatterns, setIsLoadingSectionPatterns] = useState(false);
  const inspectAbortControllerRef = useRef<AbortController | null>(null);
  const integrityInspectAbortControllerRef = useRef<AbortController | null>(null);
  const sectionPatternAbortControllerRef = useRef<AbortController | null>(null);
  const activeJobIdRef = useRef<string | null>(null);
  const activeIntegrityInspectionRef = useRef<{ jobId: string; key: string } | null>(null);
  const currentIntegrityInspectionKeyRef = useRef("");

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
        lines.push(`결과 데이터 경로: ${res.output_directory || ""}`);
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
  const patternsWithoutSelection = sectionPatterns.filter(
    (pattern) => !Object.prototype.hasOwnProperty.call(selectedPatternTocIds, pattern.signature),
  );
  const integrityInspectionPayload = {
    data_root: dataRoot,
    mode: htmlParseMode,
    input_directory: useSeparateOutputDirectory ? inputDirectory : "",
    workers: parseOptionalNumber(workers),
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
    return () => {
      inspectAbortControllerRef.current?.abort();
      integrityInspectAbortControllerRef.current?.abort();
      sectionPatternAbortControllerRef.current?.abort();
      if (activeJobIdRef.current) {
        fetch("/api/disclosures/html/cancel", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_id: activeJobIdRef.current }),
        }).catch(() => undefined);
      }
    };
  }, []);

  const handleWorkspaceDirectoryChange = async (value: string) => {
    integrityInspectAbortControllerRef.current?.abort();
    integrityInspectAbortControllerRef.current = null;
    sectionPatternAbortControllerRef.current?.abort();
    sectionPatternAbortControllerRef.current = null;
    if (await saveSetting("output_root", value)) {
      const settings = useSettingsStore.getState();
      setInputDirectory(settings.internal_html_output_directory || "");
      setOutputDirectory(settings.html_section_split_output_directory || "");
    }
    setInspectResult(null);
    setIntegrityInspectionResult(null);
    setIntegrityInspectionError("");
    setIsIntegrityInspecting(false);
    setSectionPatterns([]);
    setSelectedPatternTocIds({});
    setIsLoadingSectionPatterns(false);
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
    setIntegrityInspectionResult(null);
    setIntegrityInspectionError("");
    setIsIntegrityInspecting(false);
  }, [dataRoot, htmlParseMode, inputDirectory, useSeparateOutputDirectory, workers]);

  const handleOutputDirectoryChange = (value: string) => {
    setOutputDirectory(value);
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
      id: "workers",
      kind: "input",
      type: "number",
      label: "병렬 처리 개수",
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

  const loadSectionPatterns = async (targetInputDirectory: string) => {
    sectionPatternAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    sectionPatternAbortControllerRef.current = abortController;
    setIsLoadingSectionPatterns(true);
    setSectionPatterns([]);
    setSelectedPatternTocIds({});
    let jobId = "";
    try {
      const startResponse = await fetch("/api/disclosures/html/sections/kinds/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortController.signal,
        body: JSON.stringify({
          data_root: dataRoot,
          input_directory: targetInputDirectory,
          workers: parseOptionalNumber(workers),
        }),
      });
      if (!startResponse.ok) {
        const payload = await startResponse.json().catch(() => null);
        throw new Error(payload?.detail || "목차 조합 모아보기에 실패했습니다.");
      }
      const startPayload = await startResponse.json();
      jobId = String(startPayload.job_id || "");
      if (!jobId) {
        throw new Error("목차 조합 작업 ID를 받지 못했습니다.");
      }

      while (!abortController.signal.aborted) {
        const jobResponse = await fetch(`/api/disclosures/html/jobs/${jobId}`, {
          signal: abortController.signal,
        });
        if (!jobResponse.ok) {
          const payload = await jobResponse.json().catch(() => null);
          throw new Error(payload?.detail || "목차 조합 작업 상태를 불러오지 못했습니다.");
        }
        const snapshot = await jobResponse.json();
        if (snapshot.status === "completed") {
          const items = snapshot.result?.items || [];
          setSectionPatterns(items);
          return;
        }
        if (snapshot.status === "failed") {
          throw new Error(snapshot.error || "목차 조합 모아보기에 실패했습니다.");
        }
        if (snapshot.status === "cancelled") {
          return;
        }
        await waitForPollingInterval(abortController.signal);
      }
    } catch (err: any) {
      if (err?.name === "AbortError") {
        if (jobId) {
          fetch("/api/disclosures/html/cancel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ job_id: jobId }),
          }).catch(() => undefined);
        }
      } else {
        setStatus(errorMessage(err));
        setIsErrorStatus(true);
        setSectionPatterns([]);
        setSelectedPatternTocIds({});
      }
    } finally {
      if (sectionPatternAbortControllerRef.current === abortController) {
        sectionPatternAbortControllerRef.current = null;
        setIsLoadingSectionPatterns(false);
      }
    }
  };

  const loadSourcePage = async (targetPage: number, options: { refreshSectionPatterns?: boolean } = {}) => {
    if (!inputDirectory) {
      setStatus("입력 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    inspectAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    inspectAbortControllerRef.current = abortController;
    setIsInspecting(true);
    if (options.refreshSectionPatterns) {
      sectionPatternAbortControllerRef.current?.abort();
      sectionPatternAbortControllerRef.current = null;
      setSectionPatterns([]);
      setSelectedPatternTocIds({});
      setIsLoadingSectionPatterns(false);
    }
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
          input_directory: inputDirectory,
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
      if (options.refreshSectionPatterns) {
        window.requestAnimationFrame(() => {
          void loadSectionPatterns(data.input_directory || inputDirectory);
        });
      }
    } catch (err: any) {
      if (err?.name === "AbortError") {
        return;
      }
      setStatus(errorMessage(err));
      setIsErrorStatus(true);
      setIsInspecting(false);
      setInspectResult(null);
      if (options.refreshSectionPatterns) {
        setSectionPatterns([]);
        setSelectedPatternTocIds({});
        setIsLoadingSectionPatterns(false);
      }
      resetSelectedDisclosure();
    } finally {
      if (inspectAbortControllerRef.current === abortController) {
        inspectAbortControllerRef.current = null;
      }
      setIsInspecting(false);
    }
  };

  const inspectExistingData = async () => {
    if (!inputDirectory) {
      setStatus("입력 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    integrityInspectAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    integrityInspectAbortControllerRef.current = abortController;
    const inspectionKey = currentIntegrityInspectionKey;
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
        body: JSON.stringify(integrityInspectionPayload),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "입력 HTML 검사에 실패했습니다.");
      }
      const data = await response.json();
      const jobId = String(data.job_id || "");
      if (!jobId) {
        throw new Error("입력 HTML 검사 작업 ID를 받지 못했습니다.");
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
      activeIntegrityInspectionRef.current = { jobId, key: inspectionKey };
      startPolling(jobId);
    } catch (err: any) {
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
    loadSourcePage(1, { refreshSectionPatterns: true });
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
    void splitDocument(document);
  };

  const handleViewSource = (document: DocumentRow) => {
    openDocument(document, "source");
  };

  const handleViewSections = (document: DocumentRow) => {
    openDocument(document, "sections");
  };

  const togglePatternSection = (signature: string, tocId: string) => {
    setSelectedPatternTocIds((current) => {
      const pattern = sectionPatterns.find((item) => item.signature === signature);
      if (!pattern) return current;
      const selected = current[signature] || [];
      const nextSelected = selected.includes(tocId)
        ? selected.filter((item) => item !== tocId)
        : [...selected, tocId];
      return { ...current, [signature]: nextSelected };
    });
  };

  const setPatternSelection = (signature: string, tocIds: string[]) => {
    setSelectedPatternTocIds((current) => ({ ...current, [signature]: tocIds }));
  };

  const cancelInspectFolder = () => {
    inspectAbortControllerRef.current?.abort();
    inspectAbortControllerRef.current = null;
    sectionPatternAbortControllerRef.current?.abort();
    sectionPatternAbortControllerRef.current = null;
    setIsLoadingSectionPatterns(false);
    cancelJob();
    setStatus("작업 중단을 요청했습니다.");
    setIsErrorStatus(false);
  };

  const startSave = async () => {
    if (!dataRoot || (useSeparateOutputDirectory && !outputDirectory)) {
      setStatus("작업공간 디렉토리와 결과 데이터 경로를 확인하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (isLoadingSectionPatterns || !sectionPatterns.length) {
      setStatus("소스 불러오기 후 저장할 목차 구성을 직접 확인하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (patternsWithoutSelection.length) {
      setStatus(`모든 목차 구성에서 저장할 목차를 선택하세요: ${formatInteger(patternsWithoutSelection.length)}개`);
      setIsErrorStatus(true);
      return;
    }
    try {
      const response = await fetch("/api/disclosures/html/sections/save/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data_root: dataRoot,
          mode: htmlParseMode,
          input_directory: useSeparateOutputDirectory ? inputDirectory : "",
          output_directory: useSeparateOutputDirectory ? outputDirectory : "",
          workers: parseOptionalNumber(workers),
          section_save_rules: selectedPatternTocIds,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "목차 분리 작업을 시작하지 못했습니다.");
      }
      const data = await response.json();
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(errorMessage(err));
      setIsErrorStatus(true);
    }
  };

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  const integrityProblemFiles = integrityInspectionResult?.problem_files || [];
  const inspectionState: SingleCheckDataIntegrityInspectionState = !inputDirectory
    ? "waiting"
    : isIntegrityInspecting
      ? "running"
      : integrityInspectionError
        ? "failed"
      : integrityInspectionResult
        ? integrityProblemFiles.length > 0 ? "failed" : "success"
        : "ready";
  const inspectionCopy = {
    waiting: ["입력 데이터 경로를 선택하세요", "내부 HTML 데이터 경로를 선택한 다음 기존 원문의 목차 구성을 검사하세요."],
    ready: ["기존 원문 데이터 검사가 필요합니다", "목차 분리 전에 입력 HTML 전체의 구성을 확인하세요."],
    running: ["기존 원문 데이터를 확인하고 있습니다", "입력 HTML을 읽어 목차 구성과 문제 파일을 확인합니다."],
    success: ["기존 원문 데이터를 그대로 사용해도 됩니다", `목차가 있는 공시 ${formatInteger(integrityInspectionResult?.summary?.documents_with_sections || 0)}개를 확인했습니다.`],
    failed: ["기존 원문 데이터에 문제가 있습니다", integrityInspectionError || `읽거나 처리할 수 없는 파일 ${formatInteger(integrityProblemFiles.length)}개를 확인하세요.`],
  }[inspectionState];
  const inspectionStepSummary = integrityInspectionError
    || (integrityInspectionResult
      ? `대상 ${formatInteger(integrityInspectionResult.summary?.found_files || 0)}개, 목차 없음 ${formatInteger(integrityInspectionResult.summary?.files_without_sections || 0)}개, 문제 파일 ${formatInteger(integrityProblemFiles.length)}개입니다.`
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
            action={inputDirectory ? {
              label: isIntegrityInspecting ? "검사 중..." : "검사하기",
              onClick: inspectExistingData,
              disabled: isIntegrityInspecting || isInspecting || isJobActive,
              loading: isIntegrityInspecting,
              showResultStatus: true,
            } : undefined}
          />

          {/* LEGACY: 본문 데이터 경로 카드. 경로 입력은 우측 설정 패널(WorkflowPathSettings)로 옮겼다.
              <DataPathCard onError={handlePathError} fields={folderPathFields} /> */}

          <HtmlSectionSplitResults
            inputDirectory={reviewedInputDirectory}
            documents={documents}
            problemFiles={problemFiles}
            sectionPatterns={sectionPatterns}
            selectedPatternTocIds={selectedPatternTocIds}
            isLoadingSectionPatterns={isLoadingSectionPatterns}
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
            onTogglePatternSection={togglePatternSection}
            onSetPatternSelection={setPatternSelection}
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
        </section>

        <HtmlSectionSplitActionDock
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
