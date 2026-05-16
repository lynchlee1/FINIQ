"use client"

import { useState, useCallback } from "react";
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
        if (target === "quantiDir") setQuantiDir(data.path);
        else if (target === "registry") setItemRegistryPath(data.path);
        else setOutputPath(data.path);
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
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Market History Build</p>
              <CardTitle className="text-xl">시장 구분 이력 구축</CardTitle>
            </div>
            <Button 
              onClick={handleStartMarketHistory} 
              disabled={!!activeJobId}
              className="bg-slate-900 text-white hover:bg-slate-800"
            >
              {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              이력 구축 시작
            </Button>
          </CardHeader>
          <CardContent className="pt-6 space-y-6">
            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="quantiDir">Quantiwise (by_item) 폴더</Label>
                <div className="flex gap-2">
                  <Input 
                    id="quantiDir"
                    value={quantiDir}
                    onChange={(e) => setQuantiDir(e.target.value)}
                  />
                  <Button variant="outline" size="icon" onClick={() => handlePickPath("quantiDir")}>
                    <FolderOpen className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="itemRegistryPath">Item Registry (dbinfo.item.json)</Label>
                <div className="flex gap-2">
                  <Input 
                    id="itemRegistryPath"
                    value={itemRegistryPath}
                    onChange={(e) => setItemRegistryPath(e.target.value)}
                  />
                  <Button variant="outline" size="icon" onClick={() => handlePickPath("registry")}>
                    <File className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="outputPath">출력 Parquet 경로</Label>
                <div className="flex gap-2">
                  <Input 
                    id="outputPath"
                    value={outputPath}
                    onChange={(e) => setOutputPath(e.target.value)}
                  />
                  <Button variant="outline" size="icon" onClick={() => handlePickPath("output")}>
                    <FolderOpen className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Validation</p>
            <CardTitle className="text-xl">검증 결과</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={cn(
              "p-4 rounded-lg border font-mono text-xs whitespace-pre-wrap min-h-[120px]",
              isErrorStatus ? "bg-red-50 border-red-200 text-red-700" : "bg-slate-50 border-slate-200 text-slate-700"
            )}>
              {status}
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
