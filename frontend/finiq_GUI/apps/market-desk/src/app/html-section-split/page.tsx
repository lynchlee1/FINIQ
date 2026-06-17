"use client"

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, BarChart3, Eye, FileSearch, FolderOutput, Loader2, Play } from "lucide-react";
import { Button, Label } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { useJobPolling } from "@/hooks/useJobPolling";
import { useSettingsStore } from "@/store/useSettingsStore";
import {
  HtmlWorkflowCard,
  HtmlWorkflowForm,
  HtmlWorkflowPage,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import { formatInteger } from "@/lib/format";

type TocSection = {
  toc_id: string;
  index: number;
  title: string;
  file_count: number;
  coverage_percent: number;
  sample_file: string;
};

type InspectResult = {
  summary?: {
    found_files?: number;
    section_types?: number;
    files_without_sections?: number;
    failed_files?: number;
  };
  sections?: TocSection[];
  failed_files?: Array<{ source_file: string; error: string }>;
};

const SAMPLE_2026_DIRECTORY = "resources/KIND/bond_issuance/kind_html_contents_grouped/2026";

function statusLabel(status: string) {
  if (status === "queued") return "대기 중";
  if (status === "running") return "실행 중";
  if (status === "completed") return "완료";
  if (status === "failed") return "실패";
  return status || "-";
}

function compactPath(path: string) {
  if (!path) return "";
  const parts = path.split("/");
  return parts.length > 4 ? `.../${parts.slice(-4).join("/")}` : path;
}

export default function HtmlSectionSplitPage() {
  const { fetchSettings } = useSettingsStore();
  const [loading, setLoading] = useState(true);
  const [inputDirectory, setInputDirectory] = useState("");
  const [outputDirectory, setOutputDirectory] = useState("");
  const [section, setSection] = useState("toc_2");
  const [limit, setLimit] = useState("");
  const [sourceFile, setSourceFile] = useState("");
  const [inspectResult, setInspectResult] = useState<InspectResult | null>(null);
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewTitle, setPreviewTitle] = useState("");
  const [isInspecting, setIsInspecting] = useState(false);
  const [isRendering, setIsRendering] = useState(false);

  const formatStatus = useCallback((data: any) => {
    const res = data.result || {};
    const summary = res.summary || {};
    const lines = [`작업 상태: ${statusLabel(data.status)}`];
    if (data.error) lines.push(`오류: ${data.error}`);
    if (summary.found_files !== undefined) {
      lines.push(`대상 HTML: ${formatInteger(summary.found_files)}`);
      lines.push(`저장 완료: ${formatInteger(summary.saved_files)}`);
      lines.push(`목차 없음: ${formatInteger(summary.skipped_files)}`);
      lines.push(`결과 경로: ${res.output_directory || ""}`);
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
  } = useJobPolling({
    pollingEndpoint: "/api/disclosures/html/jobs/{jobId}",
    formatStatus,
  });

  const sections = inspectResult?.sections || [];
  const activeSection = useMemo(
    () => sections.find((item) => item.toc_id === section || String(item.index) === section || item.title.includes(section)),
    [section, sections]
  );
  const isJobActive = !!activeJobId;

  useEffect(() => {
    fetchSettings().then((config) => {
      const defaultInput = config.html_content_output_directory || (config.output_root ? `${config.output_root}/viewer_html_contents` : "");
      const initialInput = defaultInput || SAMPLE_2026_DIRECTORY;
      setInputDirectory(initialInput);
      setOutputDirectory(initialInput ? `${initialInput}_sections` : "");
    }).catch((err) => {
      setStatus(err.message);
      setIsErrorStatus(true);
    }).finally(() => {
      setLoading(false);
    });
  }, [fetchSettings, setIsErrorStatus, setStatus]);

  const handleInputDirectoryChange = (value: string) => {
    setInputDirectory(value);
    setOutputDirectory(value ? `${value}_sections` : "");
    setInspectResult(null);
    setPreviewHtml("");
    setPreviewTitle("");
  };

  const inspectFolder = async () => {
    if (!inputDirectory) {
      setStatus("입력 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    setIsInspecting(true);
    try {
      const response = await fetch("/api/disclosures/html/sections/inspect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          input_directory: inputDirectory,
          limit: limit ? Number(limit) : null,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "목차 스캔에 실패했습니다.");
      }
      const data = await response.json();
      setInspectResult(data);
      const firstSection = data.sections?.[0];
      if (firstSection) {
        setSection(firstSection.toc_id);
        setSourceFile(firstSection.sample_file);
      }
      setPreviewHtml("");
      setPreviewTitle("");
      setStatus(`목차 스캔 완료: ${formatInteger(data.summary?.section_types || 0)}개 유형`);
      setIsErrorStatus(false);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setIsInspecting(false);
    }
  };

  const selectSection = (item: TocSection) => {
    setSection(item.toc_id);
    setSourceFile(item.sample_file);
    setPreviewHtml("");
    setPreviewTitle("");
  };

  const startSave = async () => {
    if (!inputDirectory || !outputDirectory || !section) {
      setStatus("입력 경로, 결과 경로, 목차를 모두 입력하세요.");
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
          section,
          limit: limit ? Number(limit) : null,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "목차 저장 작업을 시작하지 못했습니다.");
      }
      const data = await response.json();
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const renderPreview = async () => {
    const previewSource = sourceFile || activeSection?.sample_file || "";
    if (!previewSource || !section) {
      setStatus("렌더링할 파일과 목차를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    setIsRendering(true);
    try {
      const response = await fetch("/api/disclosures/html/sections/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_file: previewSource, section }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "목차 렌더링에 실패했습니다.");
      }
      const data = await response.json();
      setSourceFile(previewSource);
      setPreviewHtml(data.html || "");
      setPreviewTitle(data.section?.title || "");
      setStatus(`목차 렌더링 완료: ${data.section?.toc_id || section}`);
      setIsErrorStatus(false);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setIsRendering(false);
    }
  };

  const fields: HtmlWorkflowField[] = [
    {
      id: "inputDirectory",
      kind: "path",
      label: "입력 경로 (HTML 폴더)",
      mode: "folder",
      value: inputDirectory,
      onChange: handleInputDirectoryChange,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 2,
    },
    {
      id: "outputDirectory",
      kind: "path",
      label: "결과 경로 (HTML 폴더)",
      mode: "folder",
      value: outputDirectory,
      onChange: setOutputDirectory,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 2,
    },
    {
      id: "section",
      kind: "input",
      label: "목차",
      value: section,
      onChange: setSection,
      placeholder: "toc_2",
      span: 2,
    },
    {
      id: "limit",
      kind: "input",
      type: "number",
      label: "최대 처리 건수",
      value: limit,
      onChange: setLimit,
      placeholder: "전체",
      span: 1,
    },
    {
      id: "sourceFile",
      kind: "path",
      label: "샘플 파일",
      mode: "file",
      value: sourceFile,
      onChange: setSourceFile,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 1,
    },
  ];

  const metrics = inspectResult?.summary ? [
    ["대상 HTML", formatInteger(inspectResult.summary.found_files || 0)],
    ["목차 유형", formatInteger(inspectResult.summary.section_types || 0)],
    ["목차 없음", formatInteger(inspectResult.summary.files_without_sections || 0)],
    ["읽기 실패", formatInteger(inspectResult.summary.failed_files || 0)],
  ] : [];

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  return (
    <HtmlWorkflowPage
      eyebrow="HTML Section Workspace"
      title="공시원문 목차 분리"
      description="KIND 본문 HTML의 목차 coverage, 샘플 렌더링, 선택 목차 저장을 한 화면에서 관리합니다."
    >
      <HtmlWorkflowCard
        title="작업 기준"
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" className="h-10" onClick={inspectFolder} disabled={isInspecting}>
              {isInspecting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileSearch className="mr-2 h-4 w-4" />}
              목차 스캔
            </Button>
            <Button variant="outline" className="h-10" onClick={renderPreview} disabled={isRendering}>
              {isRendering ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Eye className="mr-2 h-4 w-4" />}
              목차 렌더링
            </Button>
            <Button className="h-10" onClick={startSave} disabled={isJobActive}>
              {isJobActive ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              목차 저장
            </Button>
          </div>
        }
      >
        <HtmlWorkflowForm fields={fields} />
        {metrics.length ? (
          <div className="grid gap-3 md:grid-cols-4">
            {metrics.map(([label, value]) => (
              <div key={label} className="rounded-md border border-slate-200 bg-slate-50 p-3 dark:border-[#30363d] dark:bg-[#0d1117]">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-500">{label}</p>
                <p className="mt-1 text-xl font-semibold text-slate-950 dark:text-white">{value}</p>
              </div>
            ))}
          </div>
        ) : null}
        <JobStatusLogger status={status} isErrorStatus={isErrorStatus} />
      </HtmlWorkflowCard>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(420px,0.75fr)]">
        <HtmlWorkflowCard
          title="목차 Coverage"
          actions={<BarChart3 className="h-5 w-5 text-slate-500 dark:text-slate-400" />}
        >
          {sections.length ? (
            <div className="overflow-hidden rounded-md border border-slate-200 dark:border-[#30363d]">
              <div className="grid grid-cols-[92px_minmax(220px,1fr)_110px_110px] border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-500 dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-400">
                <span>목차</span>
                <span>제목</span>
                <span className="text-right">파일 수</span>
                <span className="text-right">커버리지</span>
              </div>
              <div className="max-h-[560px] overflow-auto">
                {sections.map((item) => {
                  const active = item.toc_id === activeSection?.toc_id;
                  return (
                    <button
                      key={item.toc_id}
                      type="button"
                      onClick={() => selectSection(item)}
                      className={cn(
                        "grid w-full grid-cols-[92px_minmax(220px,1fr)_110px_110px] items-center border-b border-slate-100 px-3 py-3 text-left text-sm last:border-0 dark:border-[#21262d]",
                        active
                          ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-950"
                          : "bg-white text-slate-700 hover:bg-slate-50 dark:bg-[#161b22] dark:text-slate-300 dark:hover:bg-[#21262d]"
                      )}
                    >
                      <span className="font-mono text-xs">{item.toc_id}</span>
                      <span className="min-w-0 truncate font-medium">{item.title || "-"}</span>
                      <span className="text-right tabular-nums">{formatInteger(item.file_count)}</span>
                      <span className="text-right tabular-nums">{item.coverage_percent.toFixed(1)}%</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
              목차 스캔 결과 없음
            </div>
          )}
          {inspectResult?.failed_files?.length ? (
            <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>읽기 실패 {formatInteger(inspectResult.failed_files.length)}건: {compactPath(inspectResult.failed_files[0].source_file)}</span>
            </div>
          ) : null}
        </HtmlWorkflowCard>

        <HtmlWorkflowCard
          title="렌더링 검토"
          actions={activeSection ? <span className="rounded-md bg-slate-100 px-2 py-1 font-mono text-xs text-slate-600 dark:bg-[#21262d] dark:text-slate-300">{activeSection.toc_id}</span> : null}
        >
          {activeSection ? (
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3 dark:border-[#30363d] dark:bg-[#0d1117]">
              <p className="truncate text-sm font-semibold text-slate-900 dark:text-white">{activeSection.title || "-"}</p>
              <p className="mt-1 truncate text-xs text-slate-500 dark:text-slate-500">{compactPath(sourceFile || activeSection.sample_file)}</p>
            </div>
          ) : null}
          {previewHtml ? (
            <div className="space-y-2">
              <Label className="dark:text-slate-300">{previewTitle || "렌더링 결과"}</Label>
              <iframe
                title="공시원문 목차 렌더링"
                className="h-[720px] w-full rounded-md border border-slate-200 bg-white dark:border-[#30363d]"
                sandbox=""
                srcDoc={previewHtml}
              />
            </div>
          ) : (
            <div className="flex h-[360px] items-center justify-center rounded-md border border-dashed border-slate-300 text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
              렌더링 결과 없음
            </div>
          )}
        </HtmlWorkflowCard>
      </section>
    </HtmlWorkflowPage>
  );
}
