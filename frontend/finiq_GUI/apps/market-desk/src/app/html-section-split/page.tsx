"use client"

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Eye, FileSearch, FolderOutput, ListTree, Loader2, Play, Rows3 } from "lucide-react";
import { Input, Label } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { useJobPolling } from "@/hooks/useJobPolling";
import { useSettingsStore } from "@/store/useSettingsStore";
import { HtmlWorkflowPage } from "@/components/html-workflow/HtmlWorkflowTemplate";
import { formatInteger } from "@/lib/format";

type TocItem = {
  toc_id: string;
  index: number;
  title: string;
};

type TocSection = TocItem & {
  file_count: number;
  coverage_percent: number;
  sample_file: string;
  title_variants?: Array<{ title: string; file_count: number }>;
};

type DocumentRow = {
  source_file: string;
  source_name: string;
  section_count: number;
  sections: TocItem[];
};

type InspectResult = {
  summary?: {
    found_files?: number;
    section_types?: number;
    files_without_sections?: number;
    failed_files?: number;
  };
  sections?: TocSection[];
  documents?: DocumentRow[];
  failed_files?: Array<{ source_file: string; error: string }>;
};

type PreviewResult = {
  source_file: string;
  source_name: string;
  sections: TocItem[];
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

function fileStem(path: string) {
  return path.split("/").pop() || path;
}

function rowButtonClassName(active: boolean) {
  return cn(
    "w-full rounded-md border p-3 text-left transition-colors",
    active
      ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
      : "border-slate-200 bg-white text-slate-800 hover:bg-slate-50 dark:border-[#30363d] dark:bg-[#161b22] dark:text-slate-200 dark:hover:bg-[#21262d]"
  );
}

function PanelShell({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="min-w-0 space-y-3">
      <div className="flex min-h-8 items-center justify-between gap-3 border-b border-slate-200 pb-2 dark:border-[#30363d]">
        <h2 className="text-sm font-semibold text-slate-950 dark:text-white">{title}</h2>
        {meta ? <div className="shrink-0">{meta}</div> : null}
      </div>
      {children}
    </section>
  );
}

function EmptyRow({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
      {children}
    </div>
  );
}

function RowBox({
  label,
  meta,
  children,
}: {
  label: string;
  meta?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3 shadow-sm dark:border-[#30363d] dark:bg-[#161b22]">
      <div className="mb-2 flex min-h-5 items-center justify-between gap-3">
        <Label className="text-sm font-semibold text-slate-700 dark:text-slate-300">{label}</Label>
        {meta ? <div className="shrink-0 text-xs text-slate-500 dark:text-slate-500">{meta}</div> : null}
      </div>
      {children}
    </div>
  );
}

function ActionBox({
  icon,
  label,
  onClick,
  disabled,
  primary,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex w-full items-center justify-between gap-3 rounded-md border p-3 text-left shadow-sm transition-colors",
        primary
          ? "border-slate-950 bg-slate-950 text-white hover:bg-slate-800 dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950 dark:hover:bg-slate-200"
          : "border-slate-200 bg-white text-slate-800 hover:bg-slate-50 dark:border-[#30363d] dark:bg-[#161b22] dark:text-slate-200 dark:hover:bg-[#21262d]",
        disabled && "cursor-not-allowed opacity-60"
      )}
    >
      <span className="flex min-w-0 items-center gap-3">
        <span
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-md border",
            primary
              ? "border-white/20 bg-white/10 dark:border-slate-900/10 dark:bg-slate-900/5"
              : "border-slate-200 bg-slate-50 dark:border-[#30363d] dark:bg-[#0d1117]"
          )}
        >
          {icon}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold">{label}</span>
        </span>
      </span>
    </button>
  );
}

function SectionBox({
  item,
  active,
  onClick,
}: {
  item: TocSection;
  active: boolean;
  onClick: () => void;
}) {
  const variantCount = item.title_variants?.length || 0;
  return (
    <button type="button" onClick={onClick} className={rowButtonClassName(active)}>
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-600 dark:bg-[#21262d] dark:text-slate-300">{item.toc_id}</span>
            <span className="truncate text-sm font-semibold">{item.title || "-"}</span>
          </div>
          <p className={cn("mt-2 truncate text-xs", active ? "text-white/70 dark:text-slate-700" : "text-slate-500 dark:text-slate-500")}>
            샘플 {compactPath(item.sample_file)}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-sm font-semibold tabular-nums">{formatInteger(item.file_count)}건</p>
          <p className={cn("text-xs tabular-nums", active ? "text-white/70 dark:text-slate-700" : "text-slate-500 dark:text-slate-500")}>{item.coverage_percent.toFixed(1)}%</p>
        </div>
      </div>
      {variantCount > 1 ? (
        <div className="mt-3 space-y-1">
          <p className={cn("text-xs font-medium", active ? "text-white/70 dark:text-slate-700" : "text-amber-700 dark:text-amber-300")}>
            제목 변형 {variantCount}개
          </p>
          <div className="space-y-1">
            {(item.title_variants || []).slice(0, 3).map((variant) => (
              <div
                key={variant.title}
                className={cn(
                  "flex items-center justify-between gap-2 rounded px-2 py-1 text-xs",
                  active ? "bg-white/10 text-white/80 dark:bg-black/10 dark:text-slate-800" : "bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200"
                )}
              >
                <span className="min-w-0 truncate">{variant.title}</span>
                <span className="shrink-0 tabular-nums">{formatInteger(variant.file_count)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </button>
  );
}

function DocumentBox({
  item,
  active,
  onClick,
}: {
  item: DocumentRow;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} className={rowButtonClassName(active)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{item.source_name}</p>
          <p className={cn("mt-1 truncate text-xs", active ? "text-white/70 dark:text-slate-700" : "text-slate-500 dark:text-slate-500")}>
            {compactPath(item.source_file)}
          </p>
        </div>
        <span className="shrink-0 rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 dark:bg-[#21262d] dark:text-slate-300">
          {formatInteger(item.section_count)}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {item.sections.map((section) => (
          <span
            key={section.toc_id}
            className={cn(
              "rounded px-1.5 py-0.5 font-mono text-[11px]",
              active ? "bg-white/15 text-white dark:bg-black/10 dark:text-slate-800" : "bg-slate-100 text-slate-600 dark:bg-[#21262d] dark:text-slate-300"
            )}
          >
            {section.toc_id}
          </span>
        ))}
      </div>
    </button>
  );
}

function TocBox({
  item,
  active,
  onClick,
}: {
  item: TocItem;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} className={rowButtonClassName(active)}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-xs">{item.toc_id}</p>
          <p className="mt-1 truncate text-sm font-semibold">{item.title || "-"}</p>
        </div>
        {active ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : null}
      </div>
    </button>
  );
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
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null);
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewTitle, setPreviewTitle] = useState("");
  const [isInspecting, setIsInspecting] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
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
  const documents = inspectResult?.documents || [];
  const activeSection = useMemo(
    () => sections.find((item) => item.toc_id === section || String(item.index) === section || item.title.includes(section)),
    [section, sections]
  );
  const activeDocument = useMemo(
    () => documents.find((item) => item.source_file === sourceFile),
    [documents, sourceFile]
  );
  const activeDocumentToc = activeDocument?.sections || [];
  const quickToc = activeDocumentToc.length ? activeDocumentToc : (previewResult?.sections || []);
  const activeDocumentHasSection = activeDocumentToc.some((item) => item.toc_id === section || String(item.index) === section || item.title.includes(section));
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
    setPreviewResult(null);
    setSourceFile("");
    setPreviewHtml("");
    setPreviewTitle("");
  };

  const useSampleDirectory = () => {
    setInputDirectory(SAMPLE_2026_DIRECTORY);
    setOutputDirectory(`${SAMPLE_2026_DIRECTORY}_sections`);
    setInspectResult(null);
    setPreviewResult(null);
    setSourceFile("");
    setPreviewHtml("");
    setPreviewTitle("");
  };

  const previewFirstDocument = async () => {
    if (!inputDirectory) {
      setStatus("입력 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    setIsPreviewing(true);
    try {
      const response = await fetch("/api/disclosures/html/sections/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          input_directory: inputDirectory,
          limit: limit ? Number(limit) : null,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "첫 문서 목차를 읽지 못했습니다.");
      }
      const data = await response.json();
      setPreviewResult(data);
      setSourceFile(data.source_file || "");
      const preferred = data.sections?.find((item: TocItem) => item.toc_id === "toc_2") || data.sections?.[0];
      if (preferred) setSection(preferred.toc_id);
      setPreviewHtml("");
      setPreviewTitle("");
      setStatus(`첫 문서 목차 확인: ${data.source_name || ""}`);
      setIsErrorStatus(false);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setIsPreviewing(false);
    }
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
      setPreviewResult(null);
      const preferredSection = data.sections?.find((item: TocSection) => item.toc_id === "toc_2") || data.sections?.[0];
      const preferredDocument =
        data.documents?.find((item: DocumentRow) => item.source_file === preferredSection?.sample_file) || data.documents?.[0];
      if (preferredSection) setSection(preferredSection.toc_id);
      if (preferredDocument) setSourceFile(preferredDocument.source_file);
      setPreviewHtml("");
      setPreviewTitle("");
      setStatus(`목차 스캔 완료: ${formatInteger(data.summary?.section_types || 0)}개 유형, ${formatInteger(data.summary?.found_files || 0)}개 문서`);
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

  const selectDocument = (item: DocumentRow) => {
    setSourceFile(item.source_file);
    if (!item.sections.some((toc) => toc.toc_id === section || String(toc.index) === section || toc.title.includes(section))) {
      const preferred = item.sections.find((toc) => toc.toc_id === "toc_2") || item.sections[0];
      if (preferred) setSection(preferred.toc_id);
    }
    setPreviewHtml("");
    setPreviewTitle("");
  };

  const selectDocumentToc = (item: TocItem) => {
    setSection(item.toc_id);
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
      setStatus("렌더링할 문서와 목차를 선택하세요.");
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

  const metrics = inspectResult?.summary ? [
    ["문서", formatInteger(inspectResult.summary.found_files || 0)],
    ["목차 유형", formatInteger(inspectResult.summary.section_types || 0)],
    ["목차 없음", formatInteger(inspectResult.summary.files_without_sections || 0)],
    ["읽기 실패", formatInteger(inspectResult.summary.failed_files || 0)],
  ] : [];

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  return (
    <HtmlWorkflowPage
      eyebrow="Disclosure Section Desk"
      title="공시원문 목차 분리"
      description="폴더 전체 목차 목록, 문서별 목차, 선택 목차 렌더링과 저장을 한 화면에서 처리합니다."
    >
      <section className="space-y-3">
        <div className="flex min-h-8 items-center justify-between gap-3 border-b border-slate-200 pb-2 dark:border-[#30363d]">
          <h2 className="text-sm font-semibold text-slate-950 dark:text-white">작업 기준</h2>
        </div>

        <RowBox label="입력 경로 (HTML 폴더)">
          <PathPickerInput
            mode="folder"
            value={inputDirectory}
            onChange={handleInputDirectoryChange}
            placeholder="/path/to/html-folder"
            onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
          />
        </RowBox>

        <RowBox label="결과 경로 (HTML 폴더)">
          <PathPickerInput
            mode="folder"
            value={outputDirectory}
            onChange={setOutputDirectory}
            placeholder="/path/to/output-folder"
            onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
          />
        </RowBox>

        <RowBox label="저장 대상 목차">
          <Input
            value={section}
            onChange={(event) => setSection(event.target.value)}
            placeholder="toc_2"
            className="h-10 text-sm dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-200 dark:placeholder:text-slate-600"
          />
        </RowBox>

        <RowBox label="최대 처리 건수">
          <Input
            type="number"
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
            placeholder="전체"
            className="h-10 text-sm dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-200 dark:placeholder:text-slate-600"
          />
        </RowBox>

        <RowBox label="렌더링 문서">
          <PathPickerInput
            mode="file"
            value={sourceFile}
            onChange={setSourceFile}
            placeholder="/path/to/source.html"
            onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
          />
        </RowBox>

        <ActionBox
          icon={<FolderOutput className="h-4 w-4" />}
          label="2026 샘플"
          onClick={useSampleDirectory}
        />
        <ActionBox
          icon={isPreviewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rows3 className="h-4 w-4" />}
          label="첫 문서 목차"
          onClick={previewFirstDocument}
          disabled={isPreviewing}
        />
        <ActionBox
          icon={isInspecting ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSearch className="h-4 w-4" />}
          label="목차 스캔"
          onClick={inspectFolder}
          disabled={isInspecting}
        />
        <ActionBox
          icon={isRendering ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
          label="목차 렌더링"
          onClick={renderPreview}
          disabled={isRendering}
        />
        <ActionBox
          icon={isJobActive ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          label="목차 저장"
          onClick={startSave}
          disabled={isJobActive}
          primary
        />

        {metrics.length ? (
          <RowBox label="스캔 결과">
            <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
              {metrics.map(([label, value]) => (
                <span key={label} className="text-slate-600 dark:text-slate-300">
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-500">{label}</span>
                  <span className="ml-2 font-semibold text-slate-950 dark:text-white">{value}</span>
                </span>
              ))}
            </div>
          </RowBox>
        ) : null}

        <RowBox label="작업 상태">
          <JobStatusLogger status={status} isErrorStatus={isErrorStatus} />
        </RowBox>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(320px,0.86fr)_minmax(320px,0.92fr)_minmax(420px,1fr)]">
        <PanelShell
          title="전체 목차 목록"
          meta={<ListTree className="h-5 w-5 text-slate-500 dark:text-slate-400" />}
        >
          {sections.length ? (
            <div className="max-h-[680px] space-y-2 overflow-auto pr-1">
              {sections.map((item) => (
                <SectionBox
                  key={item.toc_id}
                  item={item}
                  active={item.toc_id === activeSection?.toc_id}
                  onClick={() => selectSection(item)}
                />
              ))}
            </div>
          ) : previewResult?.sections?.length ? (
            <div className="space-y-2">
              <div className="border-b border-slate-200 pb-2 text-xs text-slate-500 dark:border-[#30363d] dark:text-slate-500">
                첫 문서 기준: {previewResult.source_name}
              </div>
              {previewResult.sections.map((item) => (
                <TocBox
                  key={item.toc_id}
                  item={item}
                  active={item.toc_id === section}
                  onClick={() => selectDocumentToc(item)}
                />
              ))}
            </div>
          ) : (
            <EmptyRow>첫 문서 목차 또는 목차 스캔을 실행하세요.</EmptyRow>
          )}
        </PanelShell>

        <PanelShell
          title="문서 목록"
          meta={documents.length ? <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{formatInteger(documents.length)}개</span> : null}
        >
          {documents.length ? (
            <div className="max-h-[680px] space-y-2 overflow-auto pr-1">
              {documents.map((item) => (
                <DocumentBox
                  key={item.source_file}
                  item={item}
                  active={item.source_file === activeDocument?.source_file}
                  onClick={() => selectDocument(item)}
                />
              ))}
            </div>
          ) : previewResult ? (
            <div className="space-y-2">
              <DocumentBox
                item={{
                  source_file: previewResult.source_file,
                  source_name: previewResult.source_name,
                  section_count: previewResult.sections.length,
                  sections: previewResult.sections,
                }}
                active={sourceFile === previewResult.source_file}
                onClick={() => {
                  setSourceFile(previewResult.source_file);
                  setPreviewHtml("");
                  setPreviewTitle("");
                }}
              />
            </div>
          ) : (
            <EmptyRow>문서 목록 없음</EmptyRow>
          )}
          {inspectResult?.failed_files?.length ? (
            <div className="flex items-start gap-2 border-l-2 border-amber-400 py-2 pl-3 text-sm text-amber-900 dark:text-amber-200">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>읽기 실패 {formatInteger(inspectResult.failed_files.length)}건: {compactPath(inspectResult.failed_files[0].source_file)}</span>
            </div>
          ) : null}
        </PanelShell>

        <PanelShell
          title="렌더링 검토"
          meta={sourceFile ? <span className="font-mono text-xs text-slate-500 dark:text-slate-400">{fileStem(sourceFile)}</span> : null}
        >
          <div className="space-y-3">
            {sourceFile ? (
              <div className="space-y-3">
                <div className="border-l-2 border-slate-300 py-1 pl-3 dark:border-[#30363d]">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-900 dark:text-white">{fileStem(sourceFile)}</p>
                      <p className="mt-1 truncate text-xs text-slate-500 dark:text-slate-500">{compactPath(sourceFile)}</p>
                    </div>
                    {(activeDocument || previewResult) ? (
                      <span className={cn(
                        "shrink-0 text-xs font-medium",
                        activeDocumentHasSection || previewResult?.sections.some((item) => item.toc_id === section)
                          ? "text-emerald-700 dark:text-emerald-300"
                          : "text-amber-800 dark:text-amber-300"
                      )}>
                        {activeDocumentHasSection || previewResult?.sections.some((item) => item.toc_id === section) ? "선택 목차 있음" : "선택 목차 없음"}
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="space-y-2">
                  {quickToc.map((item) => (
                    <TocBox
                      key={item.toc_id}
                      item={item}
                      active={item.toc_id === section}
                      onClick={() => selectDocumentToc(item)}
                    />
                  ))}
                </div>
              </div>
            ) : (
              <EmptyRow>문서를 선택하세요.</EmptyRow>
            )}
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
              <EmptyRow>렌더링 결과 없음</EmptyRow>
            )}
          </div>
        </PanelShell>
      </section>
    </HtmlWorkflowPage>
  );
}
