"use client"

import { useState, useEffect, useCallback } from "react";
import { Play, RefreshCw, Loader2 } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { cn } from "@finiq/ui/utils";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { ActionDock } from "@/components/ui/ActionDock";

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
          config.sqlite_manifest_path || ""
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
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Run</p>
              <CardTitle className="dark:text-white">공시내역 변환</CardTitle>
              <CardDescription className="dark:text-slate-400">회사별로 분류된 Raw JSON 데이터를 검색과 분석에 용이한 SQLite 형식으로 변환합니다.</CardDescription>
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
                  <Label className="dark:text-slate-300">저장 경로 (SQLite)</Label>
                  <PathPickerInput 
                    value={outputPath} 
                    onChange={(val) => {
                      setOutputPath(val);
                      saveSetting("output_root", val);
                    }}
                    mode="folder"
                    placeholder="저장 경로를 선택하세요"
                    onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                  />
                </div>
              </div>
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
                  중단
                </Button>
              </div>
            </CardContent>
          </Card>
        </section>

        <ActionDock
          activityActive={!!activeJobId}
          activityContent={
            <div className="space-y-2">
              <Label className="dark:text-slate-300">작업 상태</Label>
              <JobStatusLogger
                status={status}
                isErrorStatus={isErrorStatus}
                isCancellable={!!activeJobId}
                onCancel={cancelJob}
              />
            </div>
          }
          notificationActive={isErrorStatus}
          notificationContent={
            <div className="space-y-2">
              <Label className="dark:text-slate-300">알림</Label>
              <JobStatusLogger status={status || "알림 없음"} isErrorStatus={isErrorStatus} />
            </div>
          }
          settingsTitle="설정"
          settingsContent={
            <div className="text-sm text-slate-500 dark:text-slate-400">추가 변환 설정이 없습니다. 입출력 경로는 메인 화면에서 조정합니다.</div>
          }
        />
      </div>
    </WorkflowPageShell>
  );
}
