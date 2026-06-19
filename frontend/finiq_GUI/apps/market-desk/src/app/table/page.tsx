"use client"

import { useState, useEffect, useCallback } from "react";
import { Play, RefreshCw, Loader2 } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { cn } from "@finiq/ui/utils";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { ActionDock } from "@/components/ui/ActionDock";
import { UI_TEXT } from "@/config/uiText";

export default function TablePage() {
  const [loading, setLoading] = useState(true);
  
  const { fetchSettings, saveSetting } = useSettingsStore();
  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus, cancelJob } = useJobPolling({
    pollingEndpoint: "/api/disclosures/table/jobs/{jobId}",
    cancelEndpoint: "/api/disclosures/table/build/cancel",
  });
  
  // Data State
  const [classificationOptions, setClassificationOptions] = useState<any[]>([]);

  // Form State
  const [classificationPath, setClassificationPath] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [tableWorkers, setTableWorkers] = useState("1");
  const [maxTableWorkers, setMaxTableWorkers] = useState(1);

  const outputDirectoryFromRawPath = (path: string) => {
    const normalized = String(path || "").trim();
    if (!normalized) return "";
    if (/\.json$/i.test(normalized)) return normalized.replace(/\.json$/i, "_sqlite");
    return normalized.replace(/\/?$/, "/kind_sqlite");
  };

  const outputDirectoryFromSavedPath = (path: string) => {
    const normalized = String(path || "").trim();
    if (!/\.sqlite_manifest\.json$/i.test(normalized)) return normalized;
    return normalized.replace(/\/[^/]*$/i, "");
  };

  const loadClassifications = useCallback(async (rootDirectory: string, selectedPath: string = "", selectedOutputPath: string = "") => {
    try {
      const url = new URL("/api/classifications", window.location.origin);
      url.searchParams.set("root_directory", rootDirectory);
      const response = await fetch(url.pathname + url.search);
      if (!response.ok) throw new Error("Failed to load classifications");
      const data = await response.json();
      
      const files = data.classification_files || [];
      setClassificationOptions(files);
      
      const path = selectedPath || data.selected_classification_path || (files.length > 0 ? files[0].path : "");
      setClassificationPath(path);
      
      const outPath = outputDirectoryFromSavedPath(selectedOutputPath) || outputDirectoryFromRawPath(path);
      setOutputPath(outPath);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  }, []);

  const fetchConfig = useCallback(async () => {
    try {
      const config = await fetchSettings();
      if (config) {
        await loadClassifications(
          config.output_root || "",
          config.sqlite_source_path || config.selected_classification_path || "",
          config.sqlite_output_directory || config.sqlite_manifest_path || ""
        );
      }
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setLoading(false);
    }
  }, [loadClassifications, fetchSettings]);

  useEffect(() => {
    const hardwareConcurrency = Math.max(1, Math.floor(window.navigator.hardwareConcurrency || 1));
    setMaxTableWorkers(hardwareConcurrency);
    setTableWorkers(String(hardwareConcurrency));
    fetchConfig();
  }, [fetchConfig]);

  const handleClassificationPathChange = (val: string) => {
    setClassificationPath(val);
    setOutputPath(outputDirectoryFromRawPath(val));
    saveSetting("sqlite_source_path", val);
  };

  const handleRefresh = async () => {
    try {
      setStatus("소스를 새로고침하는 중...");
      const config = await fetchSettings();
      await loadClassifications(config?.output_root || "", classificationPath);
      setStatus("소스를 새로고침했습니다.");
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleBuild = async () => {
    if (!classificationPath) {
      setStatus("Raw JSON을 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      setStatus("SQLite 테이블 생성을 시작하는 중...");
      const response = await fetch("/api/disclosures/table/build/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          classification_path: classificationPath,
          output_path: outputPath,
          table_name: "disclosures",
          table_workers: Number(tableWorkers || maxTableWorkers || 1),
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
      <div className="relative space-y-6">
        <section className="min-w-0 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">데이터 경로</CardTitle>
              <CardDescription className="dark:text-slate-400">입력 경로와 SQLite 데이터 경로를 지정합니다.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">입력 경로 (Raw JSON 폴더)</Label>
                  <PathPickerInput
                    value={classificationPath}
                    onChange={handleClassificationPathChange}
                    mode="folder"
                    placeholder="분류 파일 또는 폴더 경로를 선택하세요"
                    onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">데이터 경로 (SQLite)</Label>
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
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <Button variant="outline" onClick={handleRefresh} disabled={!!activeJobId} className="w-full">
                  <RefreshCw className={cn("mr-2 h-4 w-4", !!activeJobId ? "animate-spin" : "")} />
                  소스 새로고침
                </Button>
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
