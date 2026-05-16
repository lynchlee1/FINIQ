"use client"

import { useState, useEffect, useCallback } from "react";
import { FolderOpen, Play, Search, Loader2, ChevronRight, ChevronDown, CheckSquare, Square } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { Checkbox } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";

interface DisclosureItem {
  code: string;
  name: string;
}

interface DisclosureGroup {
  label: string;
  suffix: string;
  items: DisclosureItem[];
}

interface DownloadOptions {
  market_types: { label: string }[];
  securities_types: { label: string }[];
  disclosure_groups: DisclosureGroup[];
  default_output_directory: string;
}

export default function DownloadPage() {
  const [options, setOptions] = useState<DownloadOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");
  const [isErrorStatus, setIsErrorStatus] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  // Form State
  const [outputDirectory, setOutputDirectory] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [submitterName, setSubmitterName] = useState("");
  const [marketLabel, setMarketLabel] = useState("검색대상");
  const [securitiesLabel, setSecuritiesLabel] = useState("전체");
  const [pageSize, setPageSize] = useState("100");
  const [waitSeconds, setWaitSeconds] = useState("1");
  const [timeout, setTimeoutVal] = useState("20");
  const [workerCount, setWorkerCount] = useState("1");
  const [startPage, setStartPage] = useState("1");
  const [endPage, setEndPage] = useState("");
  const [lastReportOnly, setLastReportOnly] = useState(false);
  const [resumeYearly, setResumeYearly] = useState(false);
  const [logLimit, setLogLimit] = useState("20");
  const [selectedDisclosures, setSelectedDisclosures] = useState<Record<string, string[]>>({});

  const fetchOptions = useCallback(async () => {
    try {
      const response = await fetch("/api/download/options");
      if (!response.ok) throw new Error("Failed to fetch download options");
      const data: DownloadOptions = await response.json();
      setOptions(data);
      setOutputDirectory(data.default_output_directory || "");
      
      const today = new Date();
      const start = new Date(today);
      start.setDate(today.getDate() - 30);
      setStartDate(start.toISOString().slice(0, 10));
      setEndDate(today.toISOString().slice(0, 10));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOptions();
  }, [fetchOptions]);

  const pollJob = useCallback(async (jobId: string) => {
    try {
      const response = await fetch(`/api/download/jobs/${encodeURIComponent(jobId)}`);
      if (!response.ok) throw new Error("Job polling failed");
      const data = await response.json();
      setResult(data.result || data);
      
      const lines = [
        `작업 상태: ${statusLabel(data.status)}`,
        ...(data.progress_log || data.result?.progress_log || [])
      ].filter(Boolean);
      
      setStatus(lines.join("\n"));
      setIsErrorStatus(data.status === "failed");

      if (data.status === "completed" || data.status === "failed") {
        setActiveJobId(null);
        return;
      }
      
      setTimeout(() => pollJob(jobId), 2000);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
      setActiveJobId(null);
    }
  }, []);

  const statusLabel = (s: string) => {
    switch(s) {
      case "queued": return "대기 중";
      case "running": return "실행 중";
      case "completed": return "완료";
      case "failed": return "실패";
      default: return s || "-";
    }
  };

  const buildPayload = () => ({
    mode: "yearly",
    output_directory: outputDirectory,
    start_date: startDate,
    end_date: endDate,
    company_name: companyName,
    submitter_name: submitterName,
    market_label: marketLabel,
    securities_label: securitiesLabel,
    page_size: Number(pageSize),
    wait_seconds: Number(waitSeconds),
    timeout: Number(timeout),
    worker_count: Number(workerCount),
    log_limit: Number(logLimit),
    start_page: Number(startPage),
    end_page: endPage ? Number(endPage) : null,
    last_report_only: lastReportOnly,
    resume_yearly: resumeYearly,
    disclosure_type_groups: selectedDisclosures,
  });

  const handlePreview = async () => {
    try {
      setStatus("미리보기 생성 중...");
      const response = await fetch("/api/download/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      if (!response.ok) throw new Error("Preview failed");
      const data = await response.json();
      setResult(data);
      setStatus("미리보기 완료");
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleRun = async () => {
    try {
      setStatus("다운로드 작업을 시작하는 중...");
      const response = await fetch("/api/download/run/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      if (!response.ok) throw new Error("Job start failed");
      const data = await response.json();
      setActiveJobId(data.job_id);
      setResult(data);
      setStatus(`작업 상태: ${statusLabel(data.status)}`);
      pollJob(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handlePickPath = async () => {
    try {
      const response = await fetch("/api/file-dialog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "dir", title: "저장 경로 선택", default_path: outputDirectory }),
      });
      const data = await response.json();
      if (data.path) {
        setOutputDirectory(data.path);
        try {
          await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ download_output_directory: data.path }),
          });
        } catch (err) {
          console.error("Failed to save setting:", err);
        }
      }
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const toggleDisclosure = (suffix: string, code: string) => {
    setSelectedDisclosures(prev => {
      const current = prev[suffix] || [];
      const next = current.includes(code) 
        ? current.filter(c => c !== code) 
        : [...current, code];
      
      const newObj = { ...prev };
      if (next.length === 0) delete newObj[suffix];
      else newObj[suffix] = next;
      return newObj;
    });
  };

  const selectGroup = (suffix: string, items: DisclosureItem[]) => {
    setSelectedDisclosures(prev => ({
      ...prev,
      [suffix]: items.map(i => i.code)
    }));
  };

  const clearGroup = (suffix: string) => {
    setSelectedDisclosures(prev => {
      const newObj = { ...prev };
      delete newObj[suffix];
      return newObj;
    });
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
        <p className="text-slate-500 font-medium">옵션을 불러오는 중입니다...</p>
      </div>
    );
  }

  return (
    <main className="flex flex-col gap-6 w-full">
      <div className="grid lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">기본 설정</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label className="dark:text-slate-300">저장 경로</Label>
                <div className="flex gap-2">
                  <Input 
                    value={outputDirectory} 
                    onChange={(e) => setOutputDirectory(e.target.value)} 
                    className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                    onBlur={() => {
                      fetch("/api/settings", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ download_output_directory: outputDirectory }),
                      });
                    }}
                  />
                  <Button variant="outline" size="icon" onClick={handlePickPath} className="dark:border-[#30363d] dark:hover:bg-[#21262d]">
                    <FolderOpen className="h-4 w-4 dark:text-slate-400" />
                  </Button>
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">시작일</Label>
                  <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 dark:[color-scheme:dark]" />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">종료일</Label>
                  <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 dark:[color-scheme:dark]" />
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">회사명</Label>
                  <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">제출인</Label>
                  <Input value={submitterName} onChange={(e) => setSubmitterName(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">시장</Label>
                  <Select value={marketLabel} onValueChange={setMarketLabel}>
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"><SelectValue /></SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      {options?.market_types.map(t => <SelectItem key={t.label} value={t.label}>{t.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">증권종류</Label>
                  <Select value={securitiesLabel} onValueChange={setSecuritiesLabel}>
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"><SelectValue /></SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      {options?.securities_types.map(t => <SelectItem key={t.label} value={t.label}>{t.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">세부 옵션</CardTitle>
            </CardHeader>
            <CardContent className="grid md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label className="dark:text-slate-300">페이지 크기</Label>
                <Input type="number" value={pageSize} onChange={(e) => setPageSize(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
              </div>
              <div className="space-y-2">
                <Label className="dark:text-slate-300">대기 시간 (초)</Label>
                <Input type="number" value={waitSeconds} onChange={(e) => setWaitSeconds(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
              </div>
              <div className="space-y-2">
                <Label className="dark:text-slate-300">타임아웃 (초)</Label>
                <Input type="number" value={timeout} onChange={(e) => setTimeoutVal(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
              </div>
              <div className="space-y-2">
                <Label className="dark:text-slate-300">워커 수</Label>
                <Input type="number" value={workerCount} onChange={(e) => setWorkerCount(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
              </div>
              <div className="space-y-2">
                <Label className="dark:text-slate-300">시작 페이지</Label>
                <Input type="number" value={startPage} onChange={(e) => setStartPage(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
              </div>
              <div className="space-y-2">
                <Label className="dark:text-slate-300">종료 페이지</Label>
                <Input type="number" placeholder="전체" value={endPage} onChange={(e) => setEndPage(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
              </div>
              <div className="flex items-center space-x-2 pt-8">
                <Checkbox id="lastReportOnly" checked={lastReportOnly} onCheckedChange={(v) => setLastReportOnly(!!v)} className="dark:border-[#30363d]" />
                <Label htmlFor="lastReportOnly" className="cursor-pointer dark:text-slate-300">최종보고서만</Label>
              </div>
              <div className="flex items-center space-x-2 pt-8">
                <Checkbox id="resumeYearly" checked={resumeYearly} onCheckedChange={(v) => setResumeYearly(!!v)} className="dark:border-[#30363d]" />
                <Label htmlFor="resumeYearly" className="cursor-pointer dark:text-slate-300">연간 작업 재개</Label>
              </div>
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">공시 종류</CardTitle>
              <CardDescription className="dark:text-slate-400">다운로드할 공시 종류를 선택하세요.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {options?.disclosure_groups.map((group) => (
                <div key={group.suffix} className="border rounded-lg overflow-hidden dark:border-[#30363d]">
                  <div className="bg-slate-50 dark:bg-[#0d1117] px-4 py-2 border-b dark:border-[#30363d] flex items-center justify-between">
                    <span className="font-semibold text-sm dark:text-slate-200">{group.label} ({group.items.length})</span>
                    <div className="flex gap-2">
                      <Button variant="ghost" size="sm" className="h-7 text-xs dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-[#21262d]" onClick={() => selectGroup(group.suffix, group.items)}>전체 선택</Button>
                      <Button variant="ghost" size="sm" className="h-7 text-xs dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-[#21262d]" onClick={() => clearGroup(group.suffix)}>전체 해제</Button>
                    </div>
                  </div>
                  <div className="p-4 grid grid-cols-2 md:grid-cols-3 gap-2">
                    {group.items.map((item) => (
                      <div key={item.code} className="flex items-center space-x-2">
                        <Checkbox 
                          id={`${group.suffix}-${item.code}`} 
                          checked={selectedDisclosures[group.suffix]?.includes(item.code) || false}
                          onCheckedChange={() => toggleDisclosure(group.suffix, item.code)}
                          className="dark:border-[#30363d]"
                        />
                        <Label 
                          htmlFor={`${group.suffix}-${item.code}`} 
                          className="text-xs cursor-pointer truncate dark:text-slate-400 dark:hover:text-slate-200"
                          title={item.name}
                        >
                          {item.name}
                        </Label>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
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
                <Button variant="outline" className="w-full dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-300" onClick={handlePreview} disabled={!!activeJobId}>
                  <Search className="mr-2 h-4 w-4" />
                  미리보기
                </Button>
                <Button className="w-full dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200" onClick={handleRun} disabled={!!activeJobId}>
                  <Play className="mr-2 h-4 w-4" />
                  실행
                </Button>
              </div>

              <div className="space-y-2">
                <Label className="dark:text-slate-300">작업 상태</Label>
                <div className={cn(
                  "p-3 rounded-lg border text-sm font-medium min-h-[100px] whitespace-pre-wrap font-mono text-xs overflow-auto max-h-[300px]",
                  isErrorStatus ? "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-900/30 text-red-700 dark:text-red-400" : "bg-slate-50 dark:bg-[#21262d] border-slate-200 dark:border-[#30363d] text-slate-700 dark:text-slate-300"
                )}>
                  {status || "대기 중..."}
                </div>
              </div>

              <div className="space-y-2">
                <Label className="dark:text-slate-300">실행 결과 (JSON)</Label>
                <div className="p-3 rounded-lg border bg-slate-900 dark:bg-[#0d1117] border-slate-800 dark:border-[#30363d] text-slate-50 dark:text-slate-300 font-mono text-[10px] overflow-auto max-h-[400px]">
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
