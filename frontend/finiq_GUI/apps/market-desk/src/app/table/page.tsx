"use client"

import { useState, useEffect, useCallback } from "react";
import { Play, Loader2 } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { JobStatusLogger, PageLoadingSpinner, ActionDock } from "@finiq/web-app/status";
import { UI_TEXT } from "@/config/uiText";
import { DisclosureSeparateOutputDirectorySetting } from "@/components/disclosures/DisclosureSeparateOutputDirectorySetting";

export default function TablePage() {
  const [loading, setLoading] = useState(true);
  
  const {
    output_root: dataRoot,
    parallel_worker_count: parallelWorkerCount,
    disclosure_separate_output_directory: useSeparateOutputDirectory,
    fetchSettings,
    saveSetting,
  } = useSettingsStore();
  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus, cancelJob } = useJobPolling({
    pollingEndpoint: "/api/disclosures/table/jobs/{jobId}",
    cancelEndpoint: "/api/disclosures/table/build/cancel",
  });
  
  // Form State
  const [outputPath, setOutputPath] = useState("");
  const [tableWorkers, setTableWorkers] = useState("1");
  const [maxTableWorkers, setMaxTableWorkers] = useState(1);

  const fetchConfig = useCallback(async () => {
    try {
      const config = await fetchSettings();
      if (config) {
        setOutputPath(config.sqlite_output_directory || config.sqlite_manifest_path || "");
        const workerCount = Number(config.parallel_worker_count || 1);
        setMaxTableWorkers(workerCount);
        setTableWorkers(String(workerCount));
      }
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setLoading(false);
    }
  }, [fetchSettings, setIsErrorStatus, setStatus]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleWorkspaceDirectoryChange = async (value: string) => {
    if (await saveSetting("output_root", value)) {
      const settings = useSettingsStore.getState();
      setOutputPath(settings.sqlite_output_directory || settings.sqlite_manifest_path || "");
    }
  };

  const handleBuild = async () => {
    if (!dataRoot) {
      setStatus("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      setStatus("SQLite 테이블 생성을 시작하는 중...");
      const response = await fetch("/api/disclosures/table/build/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data_root: dataRoot,
          root_directory: useSeparateOutputDirectory
            ? useSettingsStore.getState().download_output_directory
            : "",
          output_path: useSeparateOutputDirectory ? outputPath : "",
          table_name: "disclosures",
          table_workers: Number(tableWorkers || parallelWorkerCount || 1),
        }),
      });
      
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.error || "Build start failed");
      }
      
      const data = await response.json();
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  return (
    <WorkflowPageShell workflowId="disclosure-build">
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">데이터 경로</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">작업공간 디렉토리</Label>
                  <PathPickerInput
                    value={dataRoot}
                    onChange={handleWorkspaceDirectoryChange}
                    mode="folder"
                    placeholder="작업공간 디렉토리를 선택하세요"
                    onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                  />
                </div>
                {useSeparateOutputDirectory && <div className="space-y-2">
                  <Label className="dark:text-slate-300">결과 데이터 경로 (SQLite)</Label>
                  <PathPickerInput 
                    value={outputPath} 
                    onChange={(val) => {
                      setOutputPath(val);
                      saveSetting("sqlite_output_directory", val);
                    }}
                    mode="folder"
                    placeholder="데이터 경로를 선택하세요"
                    onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                  />
                </div>}
              </div>
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <Button className="w-full" onClick={handleBuild} disabled={!!activeJobId}>
                  {!!activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                <Button variant="outline" onClick={cancelJob} disabled={!activeJobId} className="w-full">
                  {UI_TEXT.actions.cancelJob}
                </Button>
              </div>
            </CardContent>
          </Card>
        </section>

        <ActionDock
          activityActive={!!activeJobId}
          activityContent={
            <JobStatusLogger
              status={status}
              isErrorStatus={isErrorStatus}
              isCancellable={!!activeJobId}
              onCancel={cancelJob}
            />
          }
          notificationActive={isErrorStatus}
          notificationContent={
            <div className={isErrorStatus ? "whitespace-pre-wrap text-sm text-red-600 dark:text-red-300" : "text-sm text-slate-500 dark:text-slate-400"}>{isErrorStatus ? status : "알림 없음"}</div>
          }
          settingsTitle="시스템 설정"
          settingsContent={
            <div className="space-y-5">
              <DisclosureSeparateOutputDirectorySetting id="table-separate-output-directory" />
              <div className="space-y-3">
                <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">실행 옵션</p>
                </div>
                <Label className="grid gap-2 dark:text-slate-300">
                  연도 샤드 worker 수
                  <Input
                    type="number"
                    min="1"
                    max={maxTableWorkers}
                    step="1"
                    value={tableWorkers}
                    onChange={(event) => setTableWorkers(event.target.value)}
                    className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                  />
                </Label>
                <p className="text-xs leading-5 text-slate-500 dark:text-slate-400">
                  최대 {maxTableWorkers}개까지 사용합니다. 실제 worker 수는 CPU 코어 수와 연도 shard 개수 중 작은 값으로 제한됩니다.
                </p>
              </div>
            </div>
          }
        />
      </div>
    </WorkflowPageShell>
  );
}
