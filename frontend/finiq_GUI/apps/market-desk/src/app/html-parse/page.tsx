"use client"

import { useState, useEffect, useCallback } from "react";
import { FolderOpen, FileJson, Play, Square, FileSpreadsheet, Loader2 } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, CardDescription, Input, Label, Checkbox } from "@finiq/ui";
import { WorkflowTabs } from "@/components/layout/WorkflowTabs";
import { cn } from "@finiq/ui/utils";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { useSettingsStore } from "@/store/useSettingsStore";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { useJobPolling } from "@/hooks/useJobPolling";

const HTML_PROCESS_TABS = [
  { href: "/html-download", step: 1, label: "HTML 외부 저장" },
  { href: "/html-content-download", step: 2, label: "HTML 내부 저장" },
  { href: "/html-parse", step: 3, label: "HTML 파싱" },
  { href: "/html-change-log", step: 4, label: "변동기록조회" },
  { href: "/html-bond-summary", step: 5, label: "사채 발행 요약" },
];

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
    setStatus("HTML 파싱 중지를 요청했습니다. 현재 파일 처리가 끝나면 멈춥니다.");
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

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  // Customize job status presentation slightly for HTML Parse specifically
  // While useJobPolling provides a nice string by default, the original code had summary stats.
  // We can let JobStatusLogger display `status` string as usual, and also show the raw result JSON.

  return (
    <main className="flex flex-col gap-6 w-full">
      <WorkflowTabs tabs={HTML_PROCESS_TABS} />
      <div className="grid lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Parsing Settings</p>
              <CardTitle className="dark:text-white">HTML 파싱 설정</CardTitle>
              <CardDescription className="dark:text-slate-400">저장된 HTML 원문에서 핵심 데이터를 구조화된 JSON으로 추출합니다.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">입력 경로 (HTML 폴더)</Label>
                  <PathPickerInput 
                    mode="folder"
                    value={inputDirectory}
                    onChange={handleInputDirectoryChange}
                    onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">결과 경로 (JSON)</Label>
                  <PathPickerInput 
                    mode="save"
                    value={outputPath}
                    onChange={handleOutputPathChange}
                    onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                  />
                </div>
              </div>

              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">최대 처리 건수</Label>
                  <Input type="number" placeholder="전체" value={limit} onChange={(e) => setLimit(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">진행 확인 간격 (건)</Label>
                  <Input type="number" value={progressInterval} onChange={(e) => setProgressInterval(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                </div>
              </div>

              <div className="grid md:grid-cols-2 gap-4">
                <div className="flex items-center space-x-2">
                  <Checkbox id="resumeParse" checked={resumeParse} onCheckedChange={(v) => setResumeParse(!!v)} className="dark:border-[#30363d]" />
                  <Label htmlFor="resumeParse" className="cursor-pointer dark:text-slate-300">기존 결과 JSON 이후부터 진행 (이어하기)</Label>
                </div>
                <div className="flex items-center space-x-2">
                  <Checkbox id="skipErrors" checked={skipErrors} onCheckedChange={(v) => setSkipErrors(!!v)} className="dark:border-[#30363d]" />
                  <Label htmlFor="skipErrors" className="cursor-pointer dark:text-slate-300">실패 파일 건너뛰기</Label>
                </div>
              </div>
            </CardContent>
          </Card>

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
              <Button onClick={handleExport} disabled={!outputPath} variant="outline" className="dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-300">
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
                <Button className="w-full" onClick={handleRun} disabled={isJobActive}>
                  {isJobActive ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                <Button variant="outline" className="w-full" onClick={handleCancel} disabled={!activeCancelToken}>
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
    </main>
  );
}
