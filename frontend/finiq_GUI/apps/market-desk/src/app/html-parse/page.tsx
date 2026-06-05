"use client"

import { useState, useEffect, useCallback } from "react";
import { AlertTriangle, Database, FileSearch, FileSpreadsheet, Info, ListChecks, Loader2, Play, Square } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Label, Checkbox } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { useSettingsStore } from "@/store/useSettingsStore";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { useJobPolling } from "@/hooks/useJobPolling";
import {
  HtmlStepGuide,
  HtmlWorkflowForm,
  HtmlWorkflowCard,
  HtmlWorkflowPage,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";

const PARSE_MODES = [
  {
    key: "bond_issuance",
    label: "사채발행파싱",
    status: "상세 필드 지원",
    description: "전환사채 등 사채 발행 HTML에서 발행사, 종류, 행사대상, 발행금액, 행사가액, 일정, 투자자를 추출합니다.",
  },
  {
    key: "rights_issuance",
    label: "유무상증자파싱",
    status: "상세 필드 지원",
    description: "유무상증자 HTML에서 신주 수, 발행목적, 발행가액, 기준주가, 납입일, 상장예정일, 배정 대상자를 추출합니다.",
  },
  {
    key: "shareholder_meeting",
    label: "주주총회파싱",
    status: "원본 테이블 구조 지원",
    description: "주주총회 HTML을 공통 구조로 파싱합니다. 상세 필드 규칙은 아직 추가되지 않았습니다.",
  },
  {
    key: "asset_transaction",
    label: "유무형자산거래파싱",
    status: "원본 테이블 구조 지원",
    description: "유무형자산 거래 HTML을 공통 구조로 파싱합니다. 상세 필드 규칙은 아직 추가되지 않았습니다.",
  },
  {
    key: "security_transaction",
    label: "발행증권거래파싱",
    status: "원본 테이블 구조 지원",
    description: "발행증권 거래 HTML을 공통 구조로 파싱합니다. 상세 필드 규칙은 아직 추가되지 않았습니다.",
  },
];

const WORKFLOW_GUIDE = [
  {
    icon: FileSearch,
    title: "1. HTML 폴더 선택",
    description: "KIND 뷰어 HTML이 저장된 폴더를 입력합니다. .html 파일만 처리하고 파일명 순서대로 읽습니다.",
  },
  {
    icon: Database,
    title: "2. 파싱 모드 선택",
    description: "공시 양식에 맞는 파서를 고릅니다. 모드가 맞지 않으면 결과는 생성되지만 일부 필드가 비거나 경고가 남을 수 있습니다.",
  },
  {
    icon: ListChecks,
    title: "3. JSON 저장 후 검토",
    description: "결과 JSON에는 records, errors, warnings, progress_log가 저장됩니다. 이후 공시 정정내역 한눈에와 Excel 내보내기에 사용됩니다.",
  },
];

const PARSING_RULES = [
  "HTML 문서에서 KIND 뷰어 본문을 우선 찾고, 표의 rowspan/colspan을 펼쳐 논리 행으로 변환합니다.",
  "정정 신고 표는 별도 보존하되 핵심 필드 추출은 정정이 아닌 본문 표를 우선 사용합니다.",
  "다운로드 manifest가 있으면 접수번호 기준으로 상장시장과 발행사명을 보강합니다.",
  "이어하기를 켜면 기존 JSON의 source_file을 기준으로 이미 처리된 파일과 실패 파일을 건너뜁니다.",
];

const HTML_PARSE_RELATED_ROUTES = "/html-content-download /html-parse /html-change-log";

export default function HtmlParsePage() {
  const {
    fetchSettings,
    saveSetting,
  } = useSettingsStore();

  const [loading, setLoading] = useState(true);
  
  const [result, setResult] = useState<any>(null);

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
      lines.push(`대상 HTML: ${summary.found_files || 0}`);
      lines.push(`이어받은 파일: ${summary.resumed_files || 0}`);
      lines.push(`파싱 성공: ${summary.parsed_files || 0}`);
      lines.push(`파싱 경고: ${warningCount}`);
      lines.push(`파싱 실패: ${summary.failed_files || 0}`);
      lines.push(`결과 경로: ${res.output_path || ""}`);
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
    onSuccess: setResult,
  });

  const isJobActive = !!activeJobId;

  const [activeCancelToken, setActiveCancelToken] = useState<string | null>(null);

  // Form State
  const [inputDirectory, setInputDirectory] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [parseMode, setParseMode] = useState("bond_issuance");
  const [limit, setLimit] = useState("");
  const [skipErrors, setSkipErrors] = useState(true);
  const [resumeParse, setResumeParse] = useState(true);
  const [progressInterval, setProgressInterval] = useState("10");
  const [exportLatestOnly, setExportLatestOnly] = useState(false);

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

      if (config.html_parse_result_path) {
        setOutputPath(config.html_parse_result_path);
      } else {
        const initialInput = config.html_content_output_directory || config.html_output_directory || (config.output_root ? `${config.output_root}/viewer_html` : "");
        setOutputPath(initialInput ? `${initialInput}/parsed-${config.html_parse_mode || "bond_issuance"}.json` : "");
      }
    }).catch(err => {
      setStatus(err.message);
      setIsErrorStatus(true);
    }).finally(() => {
      setLoading(false);
    });
  }, [fetchSettings, setStatus, setIsErrorStatus]);

  const updateOutputPath = useCallback((input: string, mode: string) => {
    setOutputPath(input ? `${input}/parsed-${mode}.json` : "");
  }, []);

  const handleInputDirectoryChange = (val: string) => {
    setInputDirectory(val);
    updateOutputPath(val, parseMode);
    saveSetting("html_output_directory", val);
  };

  const handleOutputPathChange = (val: string) => {
    setOutputPath(val);
    saveSetting("html_parse_result_path", val);
  };

  const handleParseModeChange = (val: string) => {
    setParseMode(val);
    updateOutputPath(inputDirectory, val);
    saveSetting("html_parse_mode", val);
  };

  const handleRun = async () => {
    if (!inputDirectory) {
      setStatus("입력 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const cancelToken = window.crypto.randomUUID();
    setActiveCancelToken(cancelToken);
    
    const payload = {
      input_directory: inputDirectory,
      output_path: outputPath,
      mode: parseMode,
      limit: limit ? Number(limit) : null,
      skip_errors: skipErrors,
      resume: resumeParse,
      progress_interval: Number(progressInterval),
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

  const handleExport = () => {
    if (!outputPath) {
      setStatus("파싱 결과 경로가 필요합니다.");
      setIsErrorStatus(true);
      return;
    }
    const params = new URLSearchParams({
      output_path: outputPath,
      mode: parseMode,
      latest_only: String(exportLatestOnly),
    });
    window.location.href = `/api/disclosures/html/parse/export.xlsx?${params.toString()}`;
  };

  const parseSettingFields: HtmlWorkflowField[] = [
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
      id: "outputPath",
      kind: "path",
      label: "결과 경로 (JSON)",
      mode: "save",
      value: outputPath,
      onChange: handleOutputPathChange,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 2,
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

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  // Customize job status presentation slightly for HTML Parse specifically
  // While useJobPolling provides a nice string by default, the original code had summary stats.
  // We can let JobStatusLogger display `status` string as usual, and also show the raw result JSON.

  return (
    <HtmlWorkflowPage
      eyebrow="HTML Parse Guide"
      title="공시원문 변환"
      description="저장된 KIND HTML을 모드별 파서로 읽어 핵심 필드, 오류, 경고, 진행 로그를 하나의 JSON에 남깁니다. 결과 파일은 이어하기, 공시 정정내역 한눈에, 발행내역 한눈에, Excel 내보내기의 기준 데이터가 됩니다."
      notice={
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>새 양식에서 필드가 비면 warnings와 원본 HTML을 함께 확인하세요.</span>
          </div>
        </div>
      }
    >

      <HtmlStepGuide items={WORKFLOW_GUIDE} />

      <div className="grid lg:grid-cols-[minmax(0,2fr)_minmax(260px,0.85fr)] gap-6">
        <section className="min-w-0 space-y-6">
          <HtmlWorkflowCard
            title="공시원문 변환 설정"
            description="저장된 HTML 원문에서 핵심 데이터를 구조화된 JSON으로 추출합니다."
          >
              <HtmlWorkflowForm fields={parseSettingFields} />
          </HtmlWorkflowCard>

          <HtmlWorkflowCard
            title="작동 원리와 파싱 방식"
            description="버그 리포트가 들어왔을 때 확인할 기준 흐름입니다."
          >
              <div className="flex items-center gap-2">
                <Info className="h-4 w-4 text-slate-500 dark:text-slate-400" />
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">How Parsing Works</p>
              </div>
              <ol className="grid gap-3">
                {PARSING_RULES.map((rule, index) => (
                  <li key={rule} className="flex gap-3 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-700 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-300">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white dark:bg-slate-100 dark:text-slate-900">
                      {index + 1}
                    </span>
                    <span>{rule}</span>
                  </li>
                ))}
              </ol>
          </HtmlWorkflowCard>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Parsing Modes</p>
              <CardTitle className="dark:text-white">모드별 기능</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid md:grid-cols-2 gap-4">
                {PARSE_MODES.map(mode => (
                  <div 
                    key={mode.key} 
                    onClick={() => handleParseModeChange(mode.key)}
                    className={cn(
                      "p-4 rounded-xl border transition-all cursor-pointer",
                      parseMode === mode.key 
                        ? "bg-slate-900 text-white border-slate-900 dark:bg-slate-100 dark:text-slate-900 dark:border-slate-100 shadow-md" 
                        : "bg-white text-slate-600 border-slate-200 dark:bg-[#0d1117] dark:text-slate-300 dark:border-[#30363d]"
                    )}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <strong className="text-sm font-bold">{mode.label}</strong>
                      <span className={cn(
                        "text-[10px] px-1.5 py-0.5 rounded font-medium",
                        parseMode === mode.key ? "bg-white/20 text-white dark:bg-black/10 dark:text-black" : "bg-slate-100 text-slate-500 dark:bg-[#21262d] dark:text-slate-400"
                      )}>{mode.status}</span>
                    </div>
                    <code className={cn(
                      "text-[10px] block mb-2 font-mono opacity-70",
                      parseMode === mode.key ? "text-white/80 dark:text-black/70" : "text-slate-400"
                    )}>{mode.key}</code>
                    <p className="text-xs leading-relaxed opacity-90">{mode.description}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Export Results</p>
              <CardTitle className="dark:text-white">결과 내보내기</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Checkbox id="exportLatestOnly" checked={exportLatestOnly} onCheckedChange={(v) => setExportLatestOnly(!!v)} className="dark:border-[#30363d]" />
                <Label htmlFor="exportLatestOnly" className="cursor-pointer dark:text-slate-300">최신버전만 보기</Label>
              </div>
              <Button onClick={handleExport} disabled={!outputPath} variant="outline" className="h-10 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-300">
                <FileSpreadsheet className="mr-2 h-4 w-4" />
                Excel로 내보내기
              </Button>
            </CardContent>
          </Card>
        </section>

        <section className="space-y-6">
          <Card className="sticky top-6 dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col gap-2">
                <Button className="h-10 w-full" onClick={handleRun} disabled={isJobActive}>
                  {isJobActive ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                <Button variant="outline" className="h-10 w-full" onClick={handleCancel} disabled={!activeCancelToken}>
                  <Square className="mr-2 h-4 w-4" />
                  중지
                </Button>
              </div>

              <div className="space-y-2">
                <Label className="dark:text-slate-300">작업 상태</Label>
                <JobStatusLogger status={status} isErrorStatus={isErrorStatus} />
              </div>

              {result?.summary && (
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">실행 결과 요약</Label>
                  <div className="grid grid-cols-2 gap-2 mt-2">
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:bg-[#0d1117] dark:border-[#30363d]">
                      <span className="text-xs font-bold text-slate-500 dark:text-slate-400">성공</span>
                      <strong className="mt-1 block text-xl font-bold text-slate-950 dark:text-slate-100">{result.summary.parsed_files || 0}</strong>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:bg-[#0d1117] dark:border-[#30363d]">
                      <span className="text-xs font-bold text-slate-500 dark:text-slate-400">실패</span>
                      <strong className="mt-1 block text-xl font-bold text-slate-950 dark:text-slate-100">{result.summary.failed_files || 0}</strong>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      </div>
    </HtmlWorkflowPage>
  );
}
