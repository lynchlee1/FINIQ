"use client"

import { useState, useCallback, useEffect } from "react";
import { Play, Loader2, FolderOpen } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { WorkflowTabs } from "@/components/layout/WorkflowTabs";
import { cn } from "@finiq/ui/utils";

const INTEGRATED_TABS = [
  { href: "/integrated-data", step: 1, label: "원천 데이터 변환" },
  { href: "/integrated-merge", step: 2, label: "Parquet 병합" },
  { href: "/integrated-market-history", step: 3, label: "시장 구분 이력" },
];

export default function IntegratedMergePage() {
  const [inputDir, setInputDir] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [status, setStatus] = useState<string>("Parquet 병합 작업을 연결할 준비가 되어 있습니다.");
  const [isErrorStatus, setIsErrorStatus] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    try {
      const response = await fetch("/api/config");
      if (!response.ok) throw new Error("Failed to fetch config");
      const config = await response.json();
      if (config.integrated_merge_input_path) setInputDir(config.integrated_merge_input_path);
      if (config.integrated_merge_output_path) setOutputDir(config.integrated_merge_output_path);
    } catch (err: any) {
      console.error("Failed to fetch config:", err);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

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

  const pollJob = useCallback(async (jobId: string) => {
    try {
      const response = await fetch(`/api/disclosures/html/jobs/${encodeURIComponent(jobId)}`);
      if (!response.ok) throw new Error("Job polling failed");
      const data = await response.json();
      
      const statusLabel = (s: string) => {
        switch(s) {
          case "queued": return "대기 중";
          case "running": return "실행 중";
          case "completed": return "완료";
          case "failed": return "실패";
          default: return s || "-";
        }
      };

      const lines = [`작업 상태: ${statusLabel(data.status)}`];
      if (data.error) lines.push(`오류: ${data.error}`);
      if (data.progress_log?.length) {
        lines.push("", "최근 로그:", ...data.progress_log.slice(-10));
      }
      
      setStatus(lines.join("\n"));
      setIsErrorStatus(data.status === "failed");

      if (data.status === "completed" || data.status === "failed") {
        setActiveJobId(null);
        return;
      }
      
      setTimeout(() => pollJob(jobId), 1000);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
      setActiveJobId(null);
    }
  }, []);

  const handleStartMerge = async () => {
    if (activeJobId) return;
    setStatus("작업을 시작하는 중...");
    setIsErrorStatus(false);

    const payload = {
      provider_id: "quantiwise", 
      input_directories: [inputDir],
      output_directory: outputDir,
    };

    try {
      const response = await fetch("/api/integrated-data/merge/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.error || `HTTP ${response.status}`);
      }
      const data = await response.json();
      setActiveJobId(data.job_id);
      pollJob(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handlePickPath = async (target: "input" | "output") => {
    try {
      const response = await fetch("/api/file-dialog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          mode: "dir", 
          title: target === "input" ? "입력 데이터셋 폴더 선택" : "병합 결과 폴더 선택", 
          default_path: (target === "input" ? inputDir : outputDir) || "" 
        }),
      });
      const data = await response.json();
      if (data.path) {
        if (target === "input") {
          setInputDir(data.path);
          saveSetting("integrated_merge_input_path", data.path);
        } else {
          setOutputDir(data.path);
          saveSetting("integrated_merge_output_path", data.path);
        }
      }
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  return (
    <main className="flex flex-col w-full">
      <WorkflowTabs tabs={INTEGRATED_TABS} />

      <div className="space-y-6">
        <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Dataset Merge</p>
              <CardTitle className="text-xl dark:text-white">Parquet 병합</CardTitle>
            </div>
            <Button 
              onClick={handleStartMerge} 
              disabled={!!activeJobId}
              className="bg-slate-900 text-white hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
            >
              {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              병합 시작
            </Button>
          </CardHeader>
          <CardContent className="pt-6 space-y-6">
            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="inputDir" className="dark:text-slate-300">입력 데이터셋 폴더</Label>
                <div className="flex gap-2">
                  <Input 
                    placeholder="Parquet 파일들이 있는 폴더 경로" 
                    value={inputDir} 
                    onChange={(e) => setInputDir(e.target.value)}
                    onBlur={() => saveSetting("integrated_merge_input_path", inputDir)}
                    className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                  />
                  <Button variant="outline" size="icon" onClick={() => handlePickPath("input")} className="dark:border-[#30363d] dark:hover:bg-[#21262d]">
                    <FolderOpen className="h-4 w-4 dark:text-slate-400" />
                  </Button>
                  </div>
                  </div>

                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">결과 저장 폴더</Label>
                    <div className="flex gap-2">
                      <Input 
                        placeholder="병합된 데이터가 저장될 폴더 경로" 
                        value={outputDir} 
                        onChange={(e) => setOutputDir(e.target.value)}
                        onBlur={() => saveSetting("integrated_merge_output_path", outputDir)}
                        className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                      />
                      <Button variant="outline" size="icon" onClick={() => handlePickPath("output")} className="dark:border-[#30363d] dark:hover:bg-[#21262d]">
                        <FolderOpen className="h-4 w-4 dark:text-slate-400" />
                      </Button>
                    </div>
                  </div>
                </div>
              </CardContent>
        </Card>

        <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
          <CardHeader>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Validation</p>
            <CardTitle className="text-xl dark:text-white">검증 결과</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={cn(
              "p-4 rounded-lg border font-mono text-xs whitespace-pre-wrap min-h-[120px]",
              isErrorStatus ? "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-900/40 text-red-700 dark:text-red-300" : "bg-slate-50 dark:bg-[#21262d] border-slate-200 dark:border-[#30363d] text-slate-700 dark:text-slate-300"
            )}>
              {status}
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
