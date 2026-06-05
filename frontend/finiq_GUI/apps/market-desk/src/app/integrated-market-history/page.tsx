"use client"

import { useEffect } from "react";
import { Play, Loader2 } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Label } from "@finiq/ui";
import { WorkflowTabs } from "@/components/layout/WorkflowTabs";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PathPickerInput } from "@/components/ui/PathPickerInput";

const INTEGRATED_TABS = [
  { href: "/integrated-data", step: 1, label: "원천 데이터 변환" },
  { href: "/integrated-merge", step: 2, label: "Parquet 병합" },
  { href: "/integrated-market-history", step: 3, label: "시장 구분 이력" },
];

export default function IntegratedMarketHistoryPage() {
  const { 
    quanti_dir: quantiDir, 
    integrated_history_item_registry_path: itemRegistryPath, 
    integrated_history_output_path: outputPath, 
    fetchSettings, 
    saveSetting,
    sqlite_manifest_path
  } = useSettingsStore();

  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus } = useJobPolling({
    pollingEndpoint: "/api/integrated-data/jobs/{jobId}",
  });

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const handleStartMarketHistory = async () => {
    if (activeJobId) return;
    setStatus("작업을 시작하는 중...");
    setIsErrorStatus(false);

    const payload = {
      quanti_dir: quantiDir,
      item_registry_path: itemRegistryPath || sqlite_manifest_path,
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
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  return (
    <main className="flex flex-col gap-6 w-full">
      <WorkflowTabs tabs={INTEGRATED_TABS} />

      <div className="grid lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 space-y-6">
        <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Market History Build</p>
              <CardTitle className="text-xl dark:text-white">시장 구분 이력 구축</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="pt-6 space-y-6">
            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="dark:text-slate-300">Quantiwise (by_item) 폴더</Label>
                <PathPickerInput 
                  mode="folder"
                  value={quantiDir || ""}
                  onChange={(val) => saveSetting("quanti_dir", val)}
                  onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                />
              </div>
              <div className="space-y-2">
                <Label className="dark:text-slate-300">Item Registry (dbinfo.item.json)</Label>
                <PathPickerInput 
                  mode="file"
                  value={itemRegistryPath || sqlite_manifest_path || ""}
                  onChange={(val) => saveSetting("integrated_history_item_registry_path", val)}
                  onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                />
              </div>
              <div className="space-y-2">
                <Label className="dark:text-slate-300">시장 구분 이력 저장 경로</Label>
                <PathPickerInput 
                  mode="save"
                  value={outputPath || ""}
                  onChange={(val) => saveSetting("integrated_history_output_path", val)}
                  onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                />
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
                <Button 
                  onClick={handleStartMarketHistory} 
                  disabled={!!activeJobId}
                  className="w-full"
                >
                  {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
              </div>

              <div className="space-y-2">
                <Label className="dark:text-slate-300">작업 상태</Label>
                <JobStatusLogger status={status} isErrorStatus={isErrorStatus} />
              </div>
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}
