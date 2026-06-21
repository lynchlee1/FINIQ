"use client"

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Play, Square } from "lucide-react";
import { Button } from "@finiq/ui";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { useJobPolling } from "@/hooks/useJobPolling";
import { useSettingsStore } from "@/store/useSettingsStore";
import { UI_TEXT } from "@/config/uiText";
import {
  HtmlWorkflowCard,
  HtmlWorkflowForm,
  HtmlWorkflowPage,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import { formatInteger } from "@/lib/format";
import {
  HtmlSectionSplitActionDock,
  HtmlSectionSplitResults,
  type DocumentRow,
  type InspectResult,
  type SplitResult,
} from "./_components/HtmlSectionSplitResults";

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
  const { fetchSettings } = useSettingsStore();
  const [loading, setLoading] = useState(true);
  const [inputDirectory, setInputDirectory] = useState("");
  const [outputDirectory, setOutputDirectory] = useState("");
  const [limit, setLimit] = useState("20");
  const [reportLimit, setReportLimit] = useState("50");
  const [workers, setWorkers] = useState("8");
  const [inspectResult, setInspectResult] = useState<InspectResult | null>(null);
  const [page, setPage] = useState(1);
  const [selectedDocument, setSelectedDocument] = useState<DocumentRow | null>(null);
  const [selectedSourceUrl, setSelectedSourceUrl] = useState("");
  const [splitResult, setSplitResult] = useState<SplitResult | null>(null);
  const [selectedSectionId, setSelectedSectionId] = useState("");
  const [isSplitting, setIsSplitting] = useState(false);
  const [isInspecting, setIsInspecting] = useState(false);
  const inspectAbortControllerRef = useRef<AbortController | null>(null);

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
        lines.push(`저장 완료: ${formatInteger(summary.saved_files)}`);
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
    onSuccess: (data) => {
      if (data?.format === "finiq_disclosure_html_section_inspect_v1") {
        setInspectResult(data.result || data);
        setStatus(`폴더 열기 완료: ${formatInteger(data.summary?.documents_with_sections || 0)}개 공시`);
      }
      setIsInspecting(false);
    },
    onError: () => {
      setIsInspecting(false);
    },
    onCancel: () => {
      setIsInspecting(false);
      setStatus("소스 불러오기를 중단했습니다.");
      setIsErrorStatus(false);
    },
    formatStatus,
  });

  const documents = inspectResult?.documents || [];
  const problemFiles = inspectResult?.problem_files || [];
  const reviewedInputDirectory = inspectResult?.input_directory || inputDirectory;
  const hasNextPage = Boolean(inspectResult?.summary?.has_next_page);
  const isJobActive = !!activeJobId;

  useEffect(() => {
    fetchSettings().then((config) => {
      const defaultInput = config.html_content_output_directory || (config.output_root ? `${config.output_root}/viewer_html_contents` : "");
      setInputDirectory(defaultInput || "");
      setOutputDirectory(defaultInput ? `${defaultInput}_sections` : "");
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
    };
  }, []);

  const handleInputDirectoryChange = (value: string) => {
    setInputDirectory(value);
    setOutputDirectory(value ? `${value}_sections` : "");
    setInspectResult(null);
    setPage(1);
    setSelectedDocument(null);
    setSelectedSourceUrl("");
    setSplitResult(null);
    setSelectedSectionId("");
  };

  const folderPathFields: HtmlWorkflowField[] = [
    {
      id: "inputDirectory",
      kind: "path",
      label: "입력 데이터 경로 (HTML)",
      mode: "folder",
      value: inputDirectory,
      onChange: handleInputDirectoryChange,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      placeholder: "/path/to/html-folder",
      span: 4,
    },
    {
      id: "outputDirectory",
      kind: "path",
      label: "결과 데이터 경로",
      mode: "folder",
      value: outputDirectory,
      onChange: setOutputDirectory,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      placeholder: "/path/to/output-folder",
      span: 4,
    },
  ];

  const splitOptionFields: HtmlWorkflowField[] = [
    {
      id: "limit",
      kind: "input",
      type: "number",
      label: "최대 표시 파일 수",
      help: "한 페이지에 표시할 HTML 파일 수입니다.",
      value: limit,
      onChange: setLimit,
      span: 2,
    },
    {
      id: "reportLimit",
      kind: "input",
      type: "number",
      label: "문제 파일 표시 수",
      help: "목차 없음과 읽기 실패 파일을 합쳐 표시할 최대 건수입니다.",
      value: reportLimit,
      onChange: setReportLimit,
      span: 2,
    },
    {
      id: "workers",
      kind: "input",
      type: "number",
      label: "병렬 처리 개수",
      help: "현재 기기 기준 최대 8개까지 사용합니다.",
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
  };

  const loadSourcePage = async (targetPage: number) => {
    if (!inputDirectory) {
      setStatus("입력 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    inspectAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    inspectAbortControllerRef.current = abortController;
    setIsInspecting(true);
    try {
      const response = await fetch("/api/disclosures/html/sections/list", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortController.signal,
        body: JSON.stringify({
          input_directory: inputDirectory,
          page: targetPage,
          page_size: Number(limit || 20),
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

  const selectDocument = (document: DocumentRow) => {
    setSelectedDocument(document);
    setSelectedSourceUrl(sourceHtmlUrl(document));
    setSplitResult(null);
    setSelectedSectionId("");
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
      setStatus(`목차 분리 완료: ${formatInteger(data.section_count || 0)}개 목차`);
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

  const handleViewSections = (document: DocumentRow) => {
    selectDocument(document);
    void splitDocument(document);
  };

  const cancelInspectFolder = () => {
    inspectAbortControllerRef.current?.abort();
    inspectAbortControllerRef.current = null;
    cancelJob();
    setStatus("소스 불러오기 중단을 요청했습니다.");
    setIsErrorStatus(false);
  };

  const startSave = async () => {
    if (!inputDirectory || !outputDirectory) {
      setStatus("입력 데이터 경로와 결과 데이터 경로를 모두 입력하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      const response = await fetch("/api/disclosures/html/sections/save/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          input_directory: inputDirectory,
          output_directory: outputDirectory,
          limit: parseOptionalNumber(limit),
          workers: parseOptionalNumber(workers),
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

  return (
    <HtmlWorkflowPage
      eyebrow="Disclosure Section Desk"
      title="공시원문 목차 분리"
      description="KIND 내부 HTML 폴더를 열어 개별 공시 원문과 목차 분리 상태를 확인합니다."
    >
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          <HtmlWorkflowCard
            title="데이터 경로"
          >
            <HtmlWorkflowForm fields={folderPathFields} />
          </HtmlWorkflowCard>

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
            isInspecting={isInspecting}
            isSourceLoadDisabled={isInspecting || isJobActive}
            isSplitting={isSplitting}
            onInspectFolder={inspectFolder}
            onViewSections={handleViewSections}
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
              <Button type="button" variant="outline" className="h-10 w-full" onClick={cancelInspectFolder} disabled={!isInspecting}>
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
          onCancel={cancelInspectFolder}
        />
      </div>
    </HtmlWorkflowPage>
  );
}
