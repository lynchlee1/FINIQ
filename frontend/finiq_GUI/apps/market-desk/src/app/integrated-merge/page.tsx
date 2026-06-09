"use client"

import { useCallback, useEffect } from "react";
import { Play, Loader2 } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Label } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { ActionDock } from "@/components/ui/ActionDock";
import { UI_TEXT } from "@/config/uiText";

export default function IntegratedMergePage() {
  const { 
    integrated_merge_input_path: inputDir, 
    integrated_merge_output_path: outputDir, 
    fetchSettings, 
    saveSetting 
  } = useSettingsStore();

  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus, cancelJob } = useJobPolling({
    pollingEndpoint: "/api/integrated-data/jobs/{jobId}",
    cancelEndpoint: "/api/integrated-data/cancel",
  });

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

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
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  return (
    <WorkflowPageShell workflowId="integrated-data">
      <div className="relative space-y-6">
        <section className="min-w-0 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Dataset Merge</p>
              <CardTitle className="text-xl dark:text-white">Parquet 병합</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">입력 데이터셋 폴더</Label>
                  <PathPickerInput mode="folder" value={inputDir || ""} onChange={(val) => saveSetting("integrated_merge_input_path", val)} placeholder="Parquet 파일들이 있는 폴더 경로" onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }} />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">결과 저장 폴더</Label>
                  <PathPickerInput mode="folder" value={outputDir || ""} onChange={(val) => saveSetting("integrated_merge_output_path", val)} placeholder="병합된 데이터가 저장될 폴더 경로" onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }} />
                </div>
              </div>
              <div className="flex gap-2">
                <Button onClick={handleStartMerge} disabled={!!activeJobId} className="w-full md:w-auto">
                  {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                {activeJobId && (
                  <Button variant="outline" onClick={cancelJob} className="w-full md:w-auto">
                    {UI_TEXT.actions.cancelJob}
                  </Button>
                )}
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
          notificationContent={<JobStatusLogger status={status || "알림 없음"} isErrorStatus={isErrorStatus} />}
          settingsTitle="병합 설정"
          settingsContent={<div className="text-sm text-slate-500 dark:text-slate-400">추가 병합 설정이 없습니다. 입출력 경로는 메인 화면에서 조정합니다.</div>}
        />
      </div>
    </WorkflowPageShell>
  );
}
