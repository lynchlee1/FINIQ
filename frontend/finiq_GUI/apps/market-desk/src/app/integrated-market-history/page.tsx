"use client"

import { useState, useCallback, useEffect } from "react";
import { Play, Loader2, FolderOpen, File } from "lucide-react";
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

export default function IntegratedMarketHistoryPage() {
  const [quantiDir, setQuantiDir] = useState("");
  const [itemRegistryPath, setItemRegistryPath] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [status, setStatus] = useState<string>("시장 구분 이력 구축 작업을 연결할 준비가 되어 있습니다.");
  const [isErrorStatus, setIsErrorStatus] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    try {
      const response = await fetch("/api/config");
      if (!response.ok) throw new Error("Failed to fetch config");
      const config = await response.json();
      if (config.quanti_dir) setQuantiDir(config.quanti_dir);
      if (config.integrated_history_item_registry_path) setItemRegistryPath(config.integrated_history_item_registry_path);
      else if (config.sqlite_manifest_path) setItemRegistryPath(config.sqlite_manifest_path);
      
      if (config.integrated_history_output_path) setOutputPath(config.integrated_history_output_path);
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

  const handleStartMarketHistory = async () => {
    if (activeJobId) return;
    setStatus("작업을 시작하는 중...");
    setIsErrorStatus(false);

    const payload = {
      quanti_dir: quantiDir,
      item_registry_path: itemRegistryPath,
      output_path: outputPath,
    };

    try {
      const response = await fetch("/api/integrated-data/market-history/start", {
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

  const handlePickPath = async (target: "quantiDir" | "registry" | "output") => {
    let mode: "dir" | "file" | "save" = "dir";
    let title = "";
    let defaultPath = "";

    if (target === "quantiDir") {
      mode = "dir";
      title = "Quantiwise 폴더 선택";
      defaultPath = quantiDir;
    } else if (target === "registry") {
      mode = "file";
      title = "Item Registry 파일 선택";
      defaultPath = itemRegistryPath;
    } else {
      mode = "save";
      title = "시장 구분 이력 저장 경로";
      defaultPath = outputPath;
    }

    try {
      const response = await fetch("/api/file-dialog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          mode, 
          title, 
          default_path: defaultPath 
        }),
      });
      const data = await response.json();
      if (data.path) {
        if (target === "quantiDir") {
          setQuantiDir(data.path);
          saveSetting("quanti_dir", data.path);
        } else if (target === "registry") {
          setItemRegistryPath(data.path);
          saveSetting("integrated_history_item_registry_path", data.path);
        } else {
          setOutputPath(data.path);
          saveSetting("integrated_history_output_path", data.path);
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
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Market History Build</p>
              <CardTitle className="text-xl dark:text-white">시장 구분 이력 구축</CardTitle>
            </div>
            <Button 
              onClick={handleStartMarketHistory} 
              disabled={!!activeJobId}
              className="bg-slate-900 text-white hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200"
            >
              {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              이력 구축 시작
            </Button>
          </CardHeader>
          <CardContent className="pt-6 space-y-6">
            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="quantiDir" className="dark:text-slate-300">Quantiwise (by_item) 폴더</Label>
                <div className="flex gap-2">
                  <Input 
                    id="quantiDir"
                    value={quantiDir}
                    onChange={(e) => setQuantiDir(e.target.value)}
                    onBlur={() => saveSetting("quanti_dir", quantiDir)}
                    className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                  />
                  <Button variant="outline" size="icon" onClick={() => handlePickPath("quantiDir")} className="dark:border-[#30363d] dark:hover:bg-[#21262d]">
                    <FolderOpen className="h-4 w-4 dark:text-slate-400" />
                  </Button>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="itemRegistryPath" className="dark:text-slate-300">Item Registry (dbinfo.item.json)</Label>
                <div className="flex gap-2">
                  <Input 
                    id="itemRegistryPath"
                    value={itemRegistryPath}
                    onChange={(e) => setItemRegistryPath(e.target.value)}
                    onBlur={() => saveSetting("integrated_history_item_registry_path", itemRegistryPath)}
                    className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                  />
                  <Button variant="outline" size="icon" onClick={() => handlePickPath("registry")} className="dark:border-[#30363d] dark:hover:bg-[#21262d]">
                    <File className="h-4 w-4 dark:text-slate-400" />
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
