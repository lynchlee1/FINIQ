"use client"

import { useState, useEffect, useCallback } from "react";
import { ExternalLink, Eye, Loader2, Play, RefreshCw, Square } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Checkbox, Label } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { useSettingsStore } from "@/store/useSettingsStore";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { useJobPolling } from "@/hooks/useJobPolling";
import { ActionDock } from "@/components/ui/ActionDock";
import {
  HtmlWorkflowForm,
  HtmlWorkflowCard,
  HtmlWorkflowPage,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import { UI_TEXT } from "@/config/uiText";
import { formatInteger } from "@/lib/format";

const PARSE_MODES = [
  {
    key: "bond_issuance",
    label: "사채발행파싱",
    status: "상세 필드 지원",
    description: "메자닌 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
  },
  {
    key: "rights_issuance",
    label: "유무상증자파싱",
    status: "상세 필드 지원",
    description: "유상증자 및 무상증자 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
  },
  {
    key: "shareholder_meeting",
    label: "주주총회파싱",
    status: "원본 테이블 구조 지원",
    description: "주주총회 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
  },
  {
    key: "asset_transaction",
    label: "유무형자산거래파싱",
    status: "원본 테이블 구조 지원",
    description: "유형자산 및 무형자산 거래 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
  },
  {
    key: "security_transaction",
    label: "발행증권거래파싱",
    status: "원본 테이블 구조 지원",
    description: "발행증권 거래 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
  },
];

const buildParseOutputPath = (inputDirectory: string, mode: string) => {
  const trimmedInputDirectory = inputDirectory.trim();
  const normalizedInputDirectory = trimmedInputDirectory === "/" ? trimmedInputDirectory : trimmedInputDirectory.replace(/\/+$/, "");
  if (!normalizedInputDirectory) return "";
  const outputDirectory = normalizedInputDirectory.endsWith("/kind_html_contents_grouped_sections")
    ? normalizedInputDirectory.slice(0, -"kind_html_contents_grouped_sections".length).replace(/\/+$/, "") || "/"
    : normalizedInputDirectory;
  return `${outputDirectory}/parsed-${mode}.json`;
};

const HTML_PARSE_RELATED_ROUTES = "/html-content-download /html-parse /html-change-log";
const BOND_ISSUE_METHOD_FILTER_FIELD = "사채발행방법";
const WARNING_OPEN_PAGE_SIZE = 20;
type FilterCandidate = {
  value: string;
  count: number;
};

type ParseWarningItem = {
  source_file?: string;
  source_name?: string;
  warning?: string;
};

type WarningReport = {
  sourceFile: string;
  sourceName: string;
  warnings: string[];
};

const buildWarningReports = (warnings: ParseWarningItem[]): WarningReport[] => {
  const reportMap = new Map<string, WarningReport>();

  warnings.forEach((item) => {
    const warning = String(item.warning || "").trim();
    if (!warning) return;

    const sourceFile = String(item.source_file || "").trim();
    const sourceName = String(item.source_name || "").trim() || sourceFile.split("/").pop() || "리포트";
    const key = sourceFile || sourceName;
    const report = reportMap.get(key) || {
      sourceFile,
      sourceName,
      warnings: [],
    };

    report.warnings.push(warning);
    reportMap.set(key, report);
  });

  return Array.from(reportMap.values());
};

const normalizePath = (path: string) => path.replace(/\\/g, "/").replace(/\/+$/, "");

const fileUrl = (path: string) => `file://${encodeURI(path)}`;

const warningSourceUrl = (sourceFile: string, inputDirectory: string) => {
  const normalizedSourceFile = normalizePath(sourceFile);
  const normalizedInputDirectory = normalizePath(inputDirectory.trim());

  if (normalizedSourceFile && normalizedInputDirectory) {
    const prefix = `${normalizedInputDirectory}/`;
    if (normalizedSourceFile === normalizedInputDirectory || normalizedSourceFile.startsWith(prefix)) {
      const sourceName = normalizedSourceFile.slice(prefix.length);
      const params = new URLSearchParams({
        input_directory: inputDirectory,
        source_name: sourceName,
      });
      return `/api/disclosures/html/sections/source?${params.toString()}`;
    }
  }

  return fileUrl(sourceFile);
};

export default function HtmlParsePage() {
  const {
    fetchSettings,
    parallel_worker_count: defaultParallelWorkers,
    saveSetting,
    saveSettings,
  } = useSettingsStore();

  const [loading, setLoading] = useState(true);
  const [latestParseResult, setLatestParseResult] = useState<any>(null);
  const [warningOpenPage, setWarningOpenPage] = useState(0);

  const formatStatus = useCallback((data: any) => {
    const statusLbl = (s: string) => {
      if (s === "queued") return "대기 중";
      if (s === "running") return "실행 중";
      if (s === "completed") return "완료";
      if (s === "failed") return "실패";
      return s || "-";
    };

    const res = data.result || {};
    const summary = res.summary || {};
    const warningCount = Array.isArray(res.warnings) ? res.warnings.length : 0;
    const lines = [`작업 상태: ${statusLbl(data.status)}`];
    if (data.error) lines.push(`오류: ${data.error}`);

    if (summary.found_files !== undefined) {
      lines.push(`대상 HTML: ${formatInteger(summary.found_files)}`);
      lines.push(`이어받은 파일: ${formatInteger(summary.resumed_files)}`);
      lines.push(`파싱 성공: ${formatInteger(summary.parsed_files)}`);
      lines.push(`파싱 경고: ${formatInteger(warningCount)}`);
      lines.push(`파싱 실패: ${formatInteger(summary.failed_files)}`);
      lines.push(`결과 데이터 경로: ${res.output_path || ""}`);
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
    onSuccess: (result) => {
      setLatestParseResult(result);
    },
  });

  const isJobActive = !!activeJobId;

  const [activeCancelToken, setActiveCancelToken] = useState<string | null>(null);

  // Form State
  const [inputDirectory, setInputDirectory] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [parseMode, setParseMode] = useState("bond_issuance");
  const [limit, setLimit] = useState("");
  const [skipErrors, setSkipErrors] = useState(true);
  const [resumeParse, setResumeParse] = useState(false);
  const [progressInterval, setProgressInterval] = useState("10");
  const [parallelWorkers, setParallelWorkers] = useState("");
  const [selectedIssueMethods, setSelectedIssueMethods] = useState<string[]>([]);
  const [issueMethodCandidates, setIssueMethodCandidates] = useState<FilterCandidate[]>([]);
  const [filterCandidatesLoading, setFilterCandidatesLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);

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

  useEffect(() => {
    fetchSettings().then((config) => {
      if (config.html_content_output_directory) {
        setInputDirectory(config.html_content_output_directory);
      } else {
        const defaultInput = config.html_output_directory || (config.output_root ? `${config.output_root}/viewer_html` : "");
        setInputDirectory(defaultInput);
      }

      if (config.html_parse_mode) {
        setParseMode(config.html_parse_mode);
      }

      const initialInput = config.html_content_output_directory || config.html_output_directory || (config.output_root ? `${config.output_root}/viewer_html` : "");
      setOutputPath(buildParseOutputPath(initialInput, config.html_parse_mode || "bond_issuance"));

      const configuredParallelWorkers = Number(config.parallel_worker_count || defaultParallelWorkers || 1);
      setParallelWorkers(String(configuredParallelWorkers));
    }).catch(err => {
      setStatus(err.message);
      setIsErrorStatus(true);
    }).finally(() => {
      setLoading(false);
    });
  }, [defaultParallelWorkers, fetchSettings, setStatus, setIsErrorStatus]);

  const handleInputDirectoryChange = (val: string) => {
    const nextOutputPath = buildParseOutputPath(val, parseMode);
    setInputDirectory(val);
    setOutputPath(nextOutputPath);
    saveSettings({
      html_content_output_directory: val,
      html_parse_result_path: nextOutputPath,
    });
  };

  const handleOutputPathChange = (val: string) => {
    setOutputPath(val);
    saveSetting("html_parse_result_path", val);
  };

  const handleParseModeChange = (val: string) => {
    const nextOutputPath = buildParseOutputPath(inputDirectory, val);
    setParseMode(val);
    setOutputPath(nextOutputPath);
    saveSettings({
      html_parse_mode: val,
      html_parse_result_path: nextOutputPath,
    });
  };

  useEffect(() => {
    if (!isJobActive) {
      setActiveCancelToken(null);
    }
  }, [isJobActive]);

  const handleRun = async () => {
    if (!inputDirectory) {
      setStatus("입력 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const activeRecordFilters = selectedIssueMethods.length ? [
      {
        field: BOND_ISSUE_METHOD_FILTER_FIELD,
        operator: "in",
        value: selectedIssueMethods,
      },
    ] : [];
    const cancelToken = window.crypto.randomUUID();
    setActiveCancelToken(cancelToken);
    setLatestParseResult(null);
    setWarningOpenPage(0);

    const payload = {
      input_directory: inputDirectory,
      output_path: outputPath,
      mode: parseMode,
      limit: limit ? Number(limit) : null,
      skip_errors: skipErrors,
      resume: resumeParse,
      progress_interval: Number(progressInterval),
      parallel_workers: parallelWorkers ? Number(parallelWorkers) : null,
      record_filters: activeRecordFilters,
      cancel_token: cancelToken,
    };

    startJob("/api/disclosures/html/parse/start", payload);
  };

  const handleCancel = async () => {
    if (!activeCancelToken) return;
    setStatus("공시원문 변환 중지를 요청했습니다. 현재 파일 처리가 끝나면 멈춥니다.");
    try {
      await fetch("/api/disclosures/html/parse/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cancel_token: activeCancelToken }),
      });
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleOpenWarningFiles = () => {
    warningPageSourceFiles.forEach((sourceFile) => {
      window.open(warningSourceUrl(sourceFile, inputDirectory), "_blank", "noopener,noreferrer");
    });
    const startIndex = warningOpenPage * WARNING_OPEN_PAGE_SIZE + 1;
    const endIndex = startIndex + warningPageSourceFiles.length - 1;
    setStatus(`경고 파일 ${formatInteger(startIndex)}-${formatInteger(endIndex)}번 열기를 요청했습니다.`);
    setIsErrorStatus(false);
  };

  const handleToggleIssueMethod = (value: string, checked: boolean) => {
    setSelectedIssueMethods((current) => {
      if (checked) return current.includes(value) ? current : [...current, value];
      return current.filter((item) => item !== value);
    });
  };

  const handleLoadIssueMethodCandidates = async () => {
    if (!inputDirectory) {
      setStatus("입력 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    setFilterCandidatesLoading(true);
    setIsErrorStatus(false);
    try {
      const response = await fetch("/api/disclosures/html/parse/filter-candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          input_directory: inputDirectory,
          mode: parseMode,
          field: BOND_ISSUE_METHOD_FILTER_FIELD,
          parallel_workers: parallelWorkers ? Number(parallelWorkers) : null,
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        let message = text;
        try {
          const detail = JSON.parse(text);
          message = detail.detail || detail.message || text;
        } catch {
          message = text;
        }
        throw new Error(message || "필터 후보를 불러오지 못했습니다.");
      }
      const data = await response.json();
      setIssueMethodCandidates(Array.isArray(data.candidates) ? data.candidates : []);
      setStatus(`사채발행방법 후보 ${formatInteger(data.summary?.candidates || 0)}개를 불러왔습니다.`);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setFilterCandidatesLoading(false);
    }
  };

  const handleLoadPreview = async () => {
    if (!inputDirectory && !outputPath) {
      setStatus("입력 데이터 경로 또는 결과 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }

    setPreviewLoading(true);
    setPreviewData(null);
    setIsErrorStatus(false);
    try {
      const response = await fetch("/api/disclosures/html/parse/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          input_directory: inputDirectory,
          output_path: outputPath,
          mode: parseMode,
          limit: 3,
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        let message = text;
        try {
          const detail = JSON.parse(text);
          message = detail.detail || detail.message || text;
        } catch {
          message = text;
        }
        throw new Error(message || "리포트 미리보기를 불러오지 못했습니다.");
      }
      const data = await response.json();
      setPreviewData(data);
      setStatus(`리포트 미리보기 ${formatInteger(data.summary?.visible_records || 0)}건을 불러왔습니다.`);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setPreviewLoading(false);
    }
  };

  const parseSettingFields: HtmlWorkflowField[] = [
    {
      id: "inputDirectory",
      kind: "path",
      label: "입력 데이터 경로 (HTML)",
      mode: "folder",
      value: inputDirectory,
      onChange: handleInputDirectoryChange,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 4,
    },
    {
      id: "outputPath",
      kind: "path",
      label: "결과 데이터 경로 (JSON)",
      mode: "save",
      value: outputPath,
      onChange: handleOutputPathChange,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 4,
    },
    {
      id: "limit",
      kind: "input",
      type: "number",
      label: "최대 처리 건수",
      placeholder: "전체",
      value: limit,
      onChange: setLimit,
      span: 2,
    },
    {
      id: "progressInterval",
      kind: "input",
      type: "number",
      label: "진행 확인 간격 (건)",
      value: progressInterval,
      onChange: setProgressInterval,
      span: 2,
    },
    {
      id: "parallelWorkers",
      kind: "input",
      type: "number",
      label: "병렬 워커 수",
      help: "앱 최초 접속 시 확인한 CPU 기준 기본값을 사용합니다.",
      placeholder: String(defaultParallelWorkers || 1),
      value: parallelWorkers,
      onChange: setParallelWorkers,
      span: 2,
    },
    {
      id: "resumeParse",
      kind: "checkbox",
      checked: resumeParse,
      onChange: setResumeParse,
      checkboxLabel: "기존 결과 JSON 이후부터 진행 (이어하기)",
      span: 2,
    },
    {
      id: "skipErrors",
      kind: "checkbox",
      checked: skipErrors,
      onChange: setSkipErrors,
      checkboxLabel: "실패 파일 건너뛰기",
      span: 2,
    },
  ];
  const parsePathFields = parseSettingFields.filter((field) => field.id === "inputDirectory" || field.id === "outputPath");
  const parseOptionFields = parseSettingFields.filter((field) => field.id !== "inputDirectory" && field.id !== "outputPath");
  const selectedParseMode = PARSE_MODES.find((mode) => mode.key === parseMode) || PARSE_MODES[0];
  const warningReports = buildWarningReports(Array.isArray(latestParseResult?.warnings) ? latestParseResult.warnings : []);
  const warningSourceFiles = Array.from(new Set(warningReports.map((report) => report.sourceFile).filter(Boolean)));
  const warningOpenPageCount = Math.max(1, Math.ceil(warningSourceFiles.length / WARNING_OPEN_PAGE_SIZE));
  const safeWarningOpenPage = Math.min(warningOpenPage, warningOpenPageCount - 1);
  const warningPageStartIndex = safeWarningOpenPage * WARNING_OPEN_PAGE_SIZE;
  const warningPageSourceFiles = warningSourceFiles.slice(warningPageStartIndex, warningPageStartIndex + WARNING_OPEN_PAGE_SIZE);
  const warningPageEndIndex = warningPageStartIndex + warningPageSourceFiles.length;
  const warningCount = warningReports.reduce((total, report) => total + report.warnings.length, 0);
  const parsedValueTableClassName = "w-full table-auto border-collapse text-left text-[11px] leading-5";
  const parsedValueCellClassName = "border-b border-slate-100 px-3 py-2 align-top text-left font-normal text-slate-700 dark:border-[#30363d] dark:text-slate-300";
  const parsedValueHeaderClassName = "w-44 border-b border-slate-200 bg-slate-50 px-3 py-2 align-top text-left text-[11px] font-semibold leading-5 text-slate-600 dark:border-[#30363d] dark:bg-[#161b22] dark:text-slate-300";
  const parsedValueIndexClassName = "w-12 border-b border-slate-200 bg-slate-50 px-3 py-2 align-top text-center text-[11px] font-semibold leading-5 text-slate-500 dark:border-[#30363d] dark:bg-[#161b22] dark:text-slate-400";

  const renderParsedValue = (value: any): any => {
    if (value === null || value === undefined || value === "") {
      return <span className="text-slate-400 dark:text-slate-500">-</span>;
    }
    if (typeof value !== "object") {
      return <span>{String(value)}</span>;
    }
    if (Array.isArray(value)) {
      if (value.length === 0) {
        return <span className="text-slate-400 dark:text-slate-500">-</span>;
      }
      if (value.every((item) => Array.isArray(item))) {
        return (
          <table className={parsedValueTableClassName}>
            <tbody>
              {value.map((row: any[], rowIndex: number) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex} className={parsedValueCellClassName}>{renderParsedValue(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        );
      }
      if (value.every((item) => item && typeof item === "object" && !Array.isArray(item))) {
        const columns = Array.from(new Set(value.flatMap((item) => Object.keys(item))));
        return (
          <table className={parsedValueTableClassName}>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column} className={parsedValueHeaderClassName}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {value.map((item, rowIndex) => (
                <tr key={rowIndex}>
                  {columns.map((column) => (
                    <td key={column} className={parsedValueCellClassName}>{renderParsedValue(item[column])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        );
      }
      return (
        <table className={parsedValueTableClassName}>
          <tbody>
            {value.map((item, index) => (
              <tr key={index}>
                <th className={parsedValueIndexClassName}>{index + 1}</th>
                <td className={parsedValueCellClassName}>{renderParsedValue(item)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      );
    }
    return (
      <table className={parsedValueTableClassName}>
        <tbody>
          {Object.entries(value).map(([key, nestedValue]) => (
            <tr key={key}>
              <th className={parsedValueHeaderClassName}>{key}</th>
              <td className={parsedValueCellClassName}>{renderParsedValue(nestedValue)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  useEffect(() => {
    if (warningOpenPage !== safeWarningOpenPage) {
      setWarningOpenPage(safeWarningOpenPage);
    }
  }, [safeWarningOpenPage, warningOpenPage]);

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  return (
    <HtmlWorkflowPage
      eyebrow="HTML Parse Guide"
      title="공시원문 변환"
      description="저장된 KIND HTML을 모드별 파서로 읽어 핵심 필드, 오류, 경고, 진행 로그를 하나의 JSON에 남깁니다. 결과 파일은 이어하기, 공시 정정내역 한눈에, 발행내역 한눈에, Excel 내보내기의 기준 데이터가 됩니다."
    >
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          <HtmlWorkflowCard
            title="데이터 경로"
          >
            <HtmlWorkflowForm fields={parsePathFields} />
          </HtmlWorkflowCard>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]" data-related-routes={HTML_PARSE_RELATED_ROUTES}>
            <CardHeader className="gap-3 pb-4">
              <div className="min-w-0 space-y-1">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Parsing Modes</p>
                <CardTitle className="dark:text-white">모드별 기능</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3">
                {PARSE_MODES.map(mode => (
                  <div
                    key={mode.key}
                    onClick={() => handleParseModeChange(mode.key)}
                    className={cn(
                      "rounded-md border px-4 py-3 transition-shadow cursor-pointer",
                      parseMode === mode.key
                        ? "bg-slate-900 text-white border-slate-900 dark:bg-slate-100 dark:text-slate-900 dark:border-slate-100 shadow-sm"
                        : "bg-white text-slate-600 border-slate-200 dark:bg-[#0d1117] dark:text-slate-300 dark:border-[#30363d]"
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <strong className="text-sm font-semibold">{mode.label}</strong>
                          <code className={cn(
                            "text-[10px] font-mono opacity-60",
                            parseMode === mode.key ? "text-white/75 dark:text-black/60" : "text-slate-400"
                          )}>{mode.key}</code>
                        </div>
                        <p className="mt-2 text-xs leading-6 opacity-85">{mode.description}</p>
                      </div>
                      <span className={cn(
                        "shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium",
                        parseMode === mode.key ? "bg-white/20 text-white dark:bg-black/10 dark:text-black" : "bg-slate-100 text-slate-500 dark:bg-[#21262d] dark:text-slate-400"
                      )}>{mode.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader className="flex flex-col gap-3 pb-4 md:flex-row md:items-start md:justify-between md:space-y-0">
              <div className="min-w-0 space-y-1">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Execution Options</p>
                <CardTitle className="dark:text-white">실행 옵션</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex justify-end">
                <Button variant="outline" className="h-9 shrink-0 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200" onClick={handleLoadIssueMethodCandidates} disabled={filterCandidatesLoading}>
                  {filterCandidatesLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                  불러오기
                </Button>
              </div>

              <div className="grid gap-2 lg:grid-cols-2">
                <div className="overflow-hidden rounded-md border border-slate-200 bg-slate-50/60 dark:border-[#30363d] dark:bg-[#0d1117] lg:col-span-2">
                  <div className="flex min-h-9 items-center px-3 py-2">
                    <Label className="shrink-0 text-sm font-semibold text-slate-900 dark:text-slate-100">{BOND_ISSUE_METHOD_FILTER_FIELD}</Label>
                  </div>

                  {issueMethodCandidates.length ? (
                    <div className="max-h-44 overflow-auto border-t border-slate-200 bg-white dark:border-[#30363d] dark:bg-[#161b22]">
                      {issueMethodCandidates.map((candidate) => {
                        const checked = selectedIssueMethods.includes(candidate.value);
                        return (
                          <label key={candidate.value} className="flex cursor-pointer items-center justify-between gap-3 border-b border-slate-100 px-3 py-1.5 last:border-b-0 dark:border-[#30363d]">
                            <span className="flex min-w-0 items-center gap-3">
                              <Checkbox checked={checked} onCheckedChange={(value) => handleToggleIssueMethod(candidate.value, !!value)} className="dark:border-[#30363d]" />
                              <span className="truncate text-sm text-slate-700 dark:text-slate-200">{candidate.value}</span>
                            </span>
                            <span className="shrink-0 text-xs tabular-nums text-slate-500 dark:text-slate-400">{formatInteger(candidate.count)}건</span>
                          </label>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader className="flex flex-col gap-3 pb-4 md:flex-row md:items-start md:justify-between md:space-y-0">
              <div className="min-w-0 space-y-1">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Report Preview</p>
                <CardTitle className="dark:text-white">리포트 미리보기</CardTitle>
              </div>
              <Button variant="outline" onClick={handleLoadPreview} disabled={previewLoading} className="h-10 shrink-0 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200">
                {previewLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Eye className="mr-2 h-4 w-4" />}
                미리보기 불러오기
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {previewData?.records?.length ? (
                previewData.records.map((record: any) => (
                  <div key={`${record.index}-${record.source_file}`} className="rounded-md border border-slate-200 bg-white px-4 py-3 dark:border-[#30363d] dark:bg-[#0d1117]">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{record.title || record.source_file || `리포트 ${record.index}`}</p>
                        <p className="mt-1 break-all text-xs text-slate-500 dark:text-slate-400">{record.source_file}</p>
                      </div>
                      <code className="rounded bg-slate-100 px-2 py-1 text-[10px] text-slate-500 dark:bg-[#161b22] dark:text-slate-400">
                        {record.acpt_no || record.rcept_no || `#${record.index}`}
                      </code>
                    </div>

                    <div className="mt-3 min-w-0 rounded-md border border-slate-200 dark:border-[#30363d]">
                      <div className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">
                        <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">파싱 결과</p>
                      </div>
                      <div className="max-h-[34rem] overflow-auto p-3">
                        {renderParsedValue(record.parsed_result)}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-md border border-dashed border-slate-300 p-4 text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
                  미리보기를 불러오면 경로 내 리포트의 파싱 결과가 표시됩니다.
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <Button className="h-10 w-full" onClick={handleRun} disabled={isJobActive}>
                  {isJobActive ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                <Button variant="outline" className="h-10 w-full" onClick={handleCancel} disabled={!activeCancelToken}>
                  <Square className="mr-2 h-4 w-4" />
                  {UI_TEXT.actions.cancelJob}
                </Button>
              </div>
            </CardContent>
          </Card>
        </section>

        <ActionDock
          activityActive={isJobActive}
          activityContent={
            <JobStatusLogger
              status={status}
              isErrorStatus={isErrorStatus}
              isCancellable={!!activeCancelToken}
              onCancel={handleCancel}
            />
          }
          notificationActive={isErrorStatus || warningReports.length > 0}
          notificationContent={
            <div className="space-y-3">
              {isErrorStatus ? (
                <div className="whitespace-pre-wrap text-sm text-red-600 dark:text-red-300">{status || "오류 내용을 확인할 수 없습니다."}</div>
              ) : warningReports.length ? (
                <div className="space-y-3">
                  <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
                    경고 리포트 {formatInteger(warningReports.length)}건, 경고 {formatInteger(warningCount)}건
                  </div>
                  <Button type="button" variant="outline" className="h-9 w-full justify-center dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200" onClick={handleOpenWarningFiles} disabled={!warningSourceFiles.length}>
                    <ExternalLink className="mr-2 h-4 w-4" />
                    현재 페이지 열기
                  </Button>
                  <div className="flex items-center justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
                    <Button type="button" variant="outline" size="sm" className="h-8 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200" onClick={() => setWarningOpenPage((page) => Math.max(0, page - 1))} disabled={safeWarningOpenPage === 0}>
                      이전
                    </Button>
                    <span className="text-center">
                      {warningSourceFiles.length ? `${formatInteger(warningPageStartIndex + 1)}-${formatInteger(warningPageEndIndex)} / ${formatInteger(warningSourceFiles.length)}` : "0 / 0"}
                    </span>
                    <Button type="button" variant="outline" size="sm" className="h-8 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200" onClick={() => setWarningOpenPage((page) => Math.min(warningOpenPageCount - 1, page + 1))} disabled={safeWarningOpenPage >= warningOpenPageCount - 1}>
                      다음
                    </Button>
                  </div>
                  <div className="max-h-[60vh] space-y-3 overflow-auto pr-1">
                    {warningReports.map((report, reportIndex) => (
                      <div key={`${report.sourceFile}-${report.sourceName}-${reportIndex}`} className="rounded-md border border-slate-200 bg-white px-3 py-2 dark:border-[#30363d] dark:bg-[#0d1117]">
                        <div className="min-w-0">
                          <p className="break-all text-sm font-semibold text-slate-900 dark:text-slate-100">{report.sourceName}</p>
                          {report.sourceFile ? (
                            <p className="mt-1 break-all text-[11px] text-slate-500 dark:text-slate-400">{report.sourceFile}</p>
                          ) : null}
                        </div>
                        <ul className="mt-2 space-y-1.5">
                          {report.warnings.map((warning, warningIndex) => (
                            <li key={`${warning}-${warningIndex}`} className="text-xs leading-5 text-slate-700 dark:text-slate-300">
                              {warning}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="text-sm text-slate-500 dark:text-slate-400">알림 없음</div>
              )}
            </div>
          }
          settingsTitle="시스템 설정"
          settingsContent={
            <>
              <div className="space-y-3">
                <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">실행 옵션</p>
                </div>
                <HtmlWorkflowForm fields={parseOptionFields} />
              </div>
            </>
          }
        />
      </div>
    </HtmlWorkflowPage>
  );
}
