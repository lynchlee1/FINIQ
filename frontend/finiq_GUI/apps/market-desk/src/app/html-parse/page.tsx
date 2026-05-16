"use client"

import { useState, useEffect, useCallback } from "react";
import { FolderOpen, FileJson, Play, Square, Loader2, FileSpreadsheet, Info } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { Checkbox } from "@finiq/ui";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { WorkflowTabs } from "@/components/layout/WorkflowTabs";
import { cn } from "@finiq/ui/utils";

const HTML_PROCESS_TABS = [
  { href: "/html-download", step: 4, label: "HTML 저장" },
  { href: "/html-parse", step: 5, label: "HTML 파싱" },
  { href: "/html-change-log", step: 6, label: "변동기록조회" },
  { href: "/html-bond-summary", step: 7, label: "사채 발행 요약" },
];

const PARSE_MODES = [
  {
    key: "bond_issuance",
    label: "사채발행파싱",
    status: "상세 필드 지원",
    description: "전환사채 등 사채 발행 HTML에서 회차, 발행금액, 발행목적, 만기일, 행사가액, 리픽싱, 납입일, 발행대상자를 추출합니다.",
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
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<string>("");
  const [isErrorStatus, setIsErrorStatus] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeCancelToken, setActiveCancelToken] = useState<string | null>(null);
  const [stopRequested, setStopRequested] = useState(false);

  // Form State
  const [inputDirectory, setInputDirectory] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [parseMode, setParseMode] = useState("bond_issuance");
  const [limit, setLimit] = useState("");
  const [skipErrors, setSkipErrors] = useState(true);
  const [resumeParse, setResumeParse] = useState(true);
  const [progressInterval, setProgressInterval] = useState("10");
  const [exportLatestOnly, setExportLatestOnly] = useState(false);

  const fetchConfig = useCallback(async () => {
    try {
      const response = await fetch("/api/config");
      if (!response.ok) throw new Error("Failed to fetch config");
      const config = await response.json();
      
      const defaultInput = config.html_output_directory || `${config.output_root || ""}/viewer_html`;
      setInputDirectory(defaultInput);
      
      if (config.html_parse_mode) {
        setParseMode(config.html_parse_mode);
      }

      if (config.html_parse_result_path) {
        setOutputPath(config.html_parse_result_path);
      } else {
        setOutputPath(defaultInput ? `${defaultInput}/parsed-${config.html_parse_mode || "bond_issuance"}.json` : "");
      }
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const updateOutputPath = useCallback((input: string, mode: string) => {
    setOutputPath(input ? `${input}/parsed-${mode}.json` : "");
  }, []);

  const handleInputDirectoryChange = (val: string) => {
    setInputDirectory(val);
    updateOutputPath(val, parseMode);
  };

  const handleParseModeChange = (val: string) => {
    setParseMode(val);
    updateOutputPath(inputDirectory, val);
  };

  const pollJob = useCallback(async (jobId: string) => {
    try {
      const response = await fetch(`/api/disclosures/html/jobs/${encodeURIComponent(jobId)}`);
      if (!response.ok) throw new Error("Job polling failed");
      const data = await response.json();
      setResult(data.result || data);
      
      const statusLbl = (s: string) => {
        if (s === "queued") return "대기 중";
        if (s === "running") return "실행 중";
        if (s === "completed") return "완료";
        if (s === "failed") return "실패";
        return s || "-";
      };

      const res = data.result || {};
      const summary = res.summary || {};
      const lines = [`작업 상태: ${statusLbl(data.status)}`];
      if (data.error) lines.push(`오류: ${data.error}`);
      
      if (summary.found_files !== undefined) {
        lines.push(`대상 HTML: ${summary.found_files || 0}`);
        lines.push(`이어받은 파일: ${summary.resumed_files || 0}`);
        lines.push(`파싱 성공: ${summary.parsed_files || 0}`);
        lines.push(`파싱 실패: ${summary.failed_files || 0}`);
        lines.push(`결과 경로: ${res.output_path || ""}`);
      }

      if (Array.isArray(data.progress_log) && data.progress_log.length) {
        lines.push("", "최근 로그", ...data.progress_log);
      }
      
      setStatus(lines.join("\n"));
      setIsErrorStatus(data.status === "failed" || (data.status === "completed" && Number(summary.failed_files || 0) > 0));

      if (data.status === "completed" || data.status === "failed") {
        setActiveJobId(null);
        setActiveCancelToken(null);
        setStopRequested(false);
        return;
      }
      
      setTimeout(() => pollJob(jobId), 2000);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
      setActiveJobId(null);
    }
  }, []);

  const handlePickPath = async (type: 'dir' | 'file' | 'save', setter: (v: string) => void, defaultPath: string) => {
    try {
      const response = await fetch("/api/file-dialog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: type, title: "선택", default_path: defaultPath }),
      });
      const data = await response.json();
      if (data.path) setter(data.path);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleRun = async () => {
    if (!inputDirectory) {
      setStatus("입력 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      const cancelToken = window.crypto.randomUUID();
      setActiveCancelToken(cancelToken);
      setStopRequested(false);
      
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

      const response = await fetch("/api/disclosures/html/parse/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("Job start failed");
      const data = await response.json();
      setActiveJobId(data.job_id);
      setResult(data);
      pollJob(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
      setActiveCancelToken(null);
    }
  };

  const handleCancel = async () => {
    if (!activeCancelToken || stopRequested) return;
    try {
      setStopRequested(true);
      setStatus("HTML 파싱 중지를 요청했습니다. 현재 파일 처리가 끝나면 멈춥니다.");
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
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
        <p className="text-slate-500 font-medium">설정을 불러오는 중입니다...</p>
      </div>
    );
  }

  return (
    <main className="flex flex-col gap-6 w-full">
      <WorkflowTabs tabs={HTML_PROCESS_TABS} />
      <div className="grid lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>HTML 파싱 설정</CardTitle>
              <CardDescription>저장된 HTML 원문에서 핵심 데이터를 구조화된 JSON으로 추출합니다.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>입력 경로 (HTML 폴더)</Label>
                  <div className="flex gap-2">
                    <Input value={inputDirectory} onChange={(e) => handleInputDirectoryChange(e.target.value)} />
                    <Button variant="outline" size="icon" onClick={() => handlePickPath('dir', handleInputDirectoryChange, inputDirectory)}>
                      <FolderOpen className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>결과 경로 (JSON)</Label>
                  <div className="flex gap-2">
                    <Input value={outputPath} onChange={(e) => setOutputPath(e.target.value)} />
                    <Button variant="outline" size="icon" onClick={() => handlePickPath('save', setOutputPath, outputPath)}>
                      <FileJson className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>

              <div className="grid md:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label>파싱 모드</Label>
                  <Select value={parseMode} onValueChange={handleParseModeChange}>
                    <SelectTrigger>
                      <SelectValue placeholder="모드 선택" />
                    </SelectTrigger>
                    <SelectContent>
                      {PARSE_MODES.map(mode => (
                        <SelectItem key={mode.key} value={mode.key}>{mode.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>최대 처리 건수</Label>
                  <Input type="number" placeholder="전체" value={limit} onChange={(e) => setLimit(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>진행 확인 간격 (건)</Label>
                  <Input type="number" value={progressInterval} onChange={(e) => setProgressInterval(e.target.value)} />
                </div>
              </div>

              <div className="grid md:grid-cols-2 gap-4">
                <div className="flex items-center space-x-2">
                  <Checkbox id="resumeParse" checked={resumeParse} onCheckedChange={(v) => setResumeParse(!!v)} />
                  <Label htmlFor="resumeParse" className="cursor-pointer">기존 결과 JSON 이후부터 진행 (이어하기)</Label>
                </div>
                <div className="flex items-center space-x-2">
                  <Checkbox id="skipErrors" checked={skipErrors} onCheckedChange={(v) => setSkipErrors(!!v)} />
                  <Label htmlFor="skipErrors" className="cursor-pointer">실패 파일 건너뛰기</Label>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>모드별 기능</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid md:grid-cols-2 gap-4">
                {PARSE_MODES.map(mode => (
                  <div 
                    key={mode.key} 
                    className={cn(
                      "p-4 rounded-xl border transition-all",
                      parseMode === mode.key 
                        ? "bg-slate-900 text-white border-slate-900 shadow-md" 
                        : "bg-white text-slate-600 border-slate-200"
                    )}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <strong className="text-sm font-bold">{mode.label}</strong>
                      <span className={cn(
                        "text-[10px] px-1.5 py-0.5 rounded font-medium",
                        parseMode === mode.key ? "bg-white/20 text-white" : "bg-slate-100 text-slate-500"
                      )}>{mode.status}</span>
                    </div>
                    <code className={cn(
                      "text-[10px] block mb-2 font-mono opacity-70",
                      parseMode === mode.key ? "text-white/80" : "text-slate-400"
                    )}>{mode.key}</code>
                    <p className="text-xs leading-relaxed opacity-90">{mode.description}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>결과 내보내기</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Checkbox id="exportLatestOnly" checked={exportLatestOnly} onCheckedChange={(v) => setExportLatestOnly(!!v)} />
                <Label htmlFor="exportLatestOnly" className="cursor-pointer">최신버전만 보기</Label>
              </div>
              <Button onClick={handleExport} disabled={!outputPath}>
                <FileSpreadsheet className="mr-2 h-4 w-4" />
                Excel로 내보내기
              </Button>
            </CardContent>
          </Card>
        </section>

        <section className="space-y-6">
          <Card className="sticky top-6">
            <CardHeader>
              <CardTitle>작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col gap-2">
                <Button className="w-full" onClick={handleRun} disabled={!!activeJobId}>
                  <Play className="mr-2 h-4 w-4" />
                  파싱 시작
                </Button>
                <Button variant="outline" className="w-full" onClick={handleCancel} disabled={!activeJobId || stopRequested}>
                  <Square className="mr-2 h-4 w-4" />
                  파싱 중지
                </Button>
              </div>

              <div className="space-y-2">
                <Label>작업 상태</Label>
                <div className={cn(
                  "p-3 rounded-lg border text-sm font-medium min-h-[120px] whitespace-pre-wrap font-mono text-xs overflow-auto max-h-[300px]",
                  isErrorStatus ? "bg-red-50 border-red-200 text-red-700" : "bg-slate-50 border-slate-200 text-slate-700"
                )}>
                  {status || "대기 중..."}
                </div>
              </div>

              <div className="space-y-2">
                <Label>실행 결과 (JSON)</Label>
                <div className="p-3 rounded-lg border bg-slate-900 text-slate-50 font-mono text-[10px] overflow-auto max-h-[300px]">
                  <pre>{result ? JSON.stringify(result, null, 2) : "결과 없음"}</pre>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}
