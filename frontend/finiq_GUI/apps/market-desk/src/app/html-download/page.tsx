"use client"

import { useState, useEffect, useCallback } from "react";
import { FolderOpen, FileJson, Play, Square, Loader2, Info } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { Checkbox } from "@finiq/ui";
import { WorkflowTabs } from "@/components/layout/WorkflowTabs";
import { cn } from "@finiq/ui/utils";

const HTML_PROCESS_TABS = [
  { href: "/html-download", step: 4, label: "HTML 저장" },
  { href: "/html-parse", step: 5, label: "HTML 파싱" },
  { href: "/html-change-log", step: 6, label: "변동기록조회" },
  { href: "/html-bond-summary", step: 7, label: "사채 발행 요약" },
];

export default function HtmlDownloadPage() {
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<string>("");
  const [isErrorStatus, setIsErrorStatus] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeCancelToken, setActiveCancelToken] = useState<string | null>(null);
  const [stopRequested, setStopRequested] = useState(false);

  // Form State
  const [outputDirectory, setOutputDirectory] = useState("");
  const [sourceJsonPath, setSourceJsonPath] = useState("");
  const [timeout, setTimeoutVal] = useState("20");
  const [maxRequestsPerMinute, setMaxRequestsPerMinute] = useState("90");
  const [waitSeconds, setWaitSeconds] = useState("0");
  const [limit, setLimit] = useState("");
  const [skipExisting, setSkipExisting] = useState(true);
  const [progressInterval, setProgressInterval] = useState("10");

  const fetchConfig = useCallback(async () => {
    try {
      const response = await fetch("/api/config");
      if (!response.ok) throw new Error("Failed to fetch config");
      const config = await response.json();
      
      setOutputDirectory(config.html_output_directory || `${config.output_root || ""}/viewer_html`);
      
      const transferredPayload = sessionStorage.getItem("finiq.kind.filteredDisclosures");
      if (transferredPayload) {
        const transferReference = JSON.parse(transferredPayload);
        setSourceJsonPath(transferReference.source_json_path || "");
        sessionStorage.removeItem("finiq.kind.filteredDisclosures");
        setStatus("공시 필터에서 생성한 결과 파일을 불러왔습니다.");
      } else if (config.html_download_source_path) {
        setSourceJsonPath(config.html_download_source_path);
      }
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const saveSetting = async (key: string, value: string) => {
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: value }),
      });
    } catch (err) {
      console.error(`Failed to save setting ${key}:`, err);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

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
      const lines = [`작업 상태: ${statusLbl(data.status)}`];
      if (data.error) lines.push(`오류: ${data.error}`);
      if (res.requested_count !== undefined) {
        lines.push(`요청 접수번호: ${res.requested_count || 0}`);
        lines.push(`저장 파일: ${res.saved_count || 0}`);
        lines.push(`저장 경로: ${res.output_directory || ""}`);
      }
      if (Array.isArray(data.progress_log) && data.progress_log.length) {
        lines.push("", "최근 로그", ...data.progress_log);
      }
      
      setStatus(lines.join("\n"));
      setIsErrorStatus(data.status === "failed");

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

  const handlePickPath = async (type: 'dir' | 'file', setter: (v: string) => void, defaultPath: string) => {
    try {
      const response = await fetch("/api/file-dialog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: type, title: "선택", default_path: defaultPath }),
      });
      const data = await response.json();
      if (data.path) {
        setter(data.path);
        if (setter === setSourceJsonPath) {
          saveSetting("html_download_source_path", data.path);
        } else if (setter === setOutputDirectory) {
          saveSetting("html_output_directory", data.path);
        }
      }
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleRun = async () => {
    if (!sourceJsonPath) {
      setStatus("필터 결과 파일을 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      const cancelToken = window.crypto.randomUUID();
      setActiveCancelToken(cancelToken);
      setStopRequested(false);
      
      const payload = {
        output_directory: outputDirectory,
        source_json_path: sourceJsonPath,
        timeout: Number(timeout),
        max_requests_per_minute: Number(maxRequestsPerMinute),
        wait_seconds: Number(waitSeconds),
        limit: limit ? Number(limit) : null,
        skip_existing: skipExisting,
        progress_interval: Number(progressInterval),
        cancel_token: cancelToken,
      };

      const response = await fetch("/api/disclosures/html/download/start", {
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
      setStatus("HTML 저장 중지를 요청했습니다. 진행 중인 요청이 끝나면 멈춥니다.");
      await fetch("/api/disclosures/html/download/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cancel_token: activeCancelToken }),
      });
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
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
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">HTML 저장 설정</CardTitle>
              <CardDescription className="dark:text-slate-400">다운로드된 공시 결과 JSON을 바탕으로 HTML 원문을 대량 저장합니다.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label className="dark:text-slate-300">필터 결과 JSON 파일</Label>
                <div className="flex gap-2">
                  <Input value={sourceJsonPath} onChange={(e) => setSourceJsonPath(e.target.value)} onBlur={() => saveSetting("html_download_source_path", sourceJsonPath)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                  <Button variant="outline" size="icon" onClick={() => handlePickPath('file', setSourceJsonPath, sourceJsonPath)} className="dark:border-[#30363d] dark:hover:bg-[#21262d]">
                    <FileJson className="h-4 w-4 dark:text-slate-400" />
                  </Button>
                </div>
                <p className="text-[11px] text-slate-400 dark:text-slate-500 flex items-center gap-1">
                  <Info className="h-3 w-3" /> 공시 필터링 결과 파일(JSON)을 선택하세요.
                </p>
              </div>

              <div className="space-y-2">
                <Label className="dark:text-slate-300">저장 경로</Label>
                <div className="flex gap-2">
                  <Input value={outputDirectory} onChange={(e) => setOutputDirectory(e.target.value)} onBlur={() => saveSetting("html_output_directory", outputDirectory)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                  <Button variant="outline" size="icon" onClick={() => handlePickPath('dir', setOutputDirectory, outputDirectory)} className="dark:border-[#30363d] dark:hover:bg-[#21262d]">
                    <FolderOpen className="h-4 w-4 dark:text-slate-400" />
                  </Button>
                </div>
              </div>

              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">타임아웃 (초)</Label>
                  <Input type="number" value={timeout} onChange={(e) => setTimeoutVal(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">최대 요청/분</Label>
                  <Input type="number" value={maxRequestsPerMinute} onChange={(e) => setMaxRequestsPerMinute(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                </div>
              </div>

              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">요청 간격 (초)</Label>
                  <Input type="number" value={waitSeconds} onChange={(e) => setWaitSeconds(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">최대 처리 건수</Label>
                  <Input type="number" placeholder="전체" value={limit} onChange={(e) => setLimit(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                </div>
              </div>

              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">진행 확인 간격 (건)</Label>
                  <Input type="number" value={progressInterval} onChange={(e) => setProgressInterval(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                </div>
                <div className="flex items-center space-x-2 pt-8">
                  <Checkbox id="skipExisting" checked={skipExisting} onCheckedChange={(v) => setSkipExisting(!!v)} className="dark:border-[#30363d]" />
                  <Label htmlFor="skipExisting" className="cursor-pointer dark:text-slate-300">기존 파일 건너뛰기</Label>
                </div>
              </div>
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
                <Button className="w-full dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200" onClick={handleRun} disabled={!!activeJobId}>
                  <Play className="mr-2 h-4 w-4" />
                  저장 시작
                </Button>
                <Button variant="outline" className="w-full dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-300" onClick={handleCancel} disabled={!activeJobId || stopRequested}>
                  <Square className="mr-2 h-4 w-4" />
                  저장 중지
                </Button>
              </div>

              <div className="space-y-2">
                <Label className="dark:text-slate-300">작업 상태</Label>
                <div className={cn(
                  "p-3 rounded-lg border text-sm font-medium min-h-[120px] whitespace-pre-wrap font-mono text-xs overflow-auto max-h-[300px]",
                  isErrorStatus ? "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-900/30 text-red-700 dark:text-red-400" : "bg-slate-50 dark:bg-[#21262d] border-slate-200 dark:border-[#30363d] text-slate-700 dark:text-slate-300"
                )}>
                  {status || "대기 중..."}
                </div>
              </div>

              <div className="space-y-2">
                <Label className="dark:text-slate-300">실행 결과 (JSON)</Label>
                <div className="p-3 rounded-lg border bg-slate-900 dark:bg-[#0d1117] border-slate-800 dark:border-[#30363d] text-slate-50 dark:text-slate-300 font-mono text-[10px] overflow-auto max-h-[300px]">
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
