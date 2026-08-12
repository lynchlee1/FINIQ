"use client"

import { useState, useEffect, useCallback, useRef } from "react";
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
import {
  SingleCheckDataIntegrityInspectionCard,
  type SingleCheckDataIntegrityInspectionState,
} from "@/components/data-integrity/DataIntegrityInspectionCard";
import { useDataIntegrityInspection } from "@/hooks/useDataIntegrityInspection";
import { apiPost } from "@/api/client";
import { formatInteger } from "@/lib/format";

type TableInspectionPayload = {
  data_root: string;
  root_directory: string;
  output_path: string;
  table_workers: number;
};

type TableInspectionResult = {
  format: "finiq_disclosure_table_inspection_v1";
  confirmed: boolean;
  reason: string;
  manifest_path: string;
  summary?: {
    source_rows: number;
    duplicate_rows: number;
    disclosures: number;
    shards: number;
  };
};

export default function TablePage() {
  const [loading, setLoading] = useState(true);
  const activeBuildInspectionRef = useRef<{ jobId: string; key: string } | null>(null);
  const currentInspectionKeyRef = useRef("");
  
  const {
    output_root: dataRoot,
    download_output_directory: downloadOutputDirectory,
    disclosure_separate_output_directory: useSeparateOutputDirectory,
    fetchSettings,
    saveSetting,
  } = useSettingsStore();
  const {
    result: inspectionResult,
    error: inspectionError,
    isChecking: inspectionRunning,
    runInspection,
    acceptResult: acceptInspectionResult,
    clear: clearInspection,
  } = useDataIntegrityInspection<TableInspectionPayload, TableInspectionResult>({
    inspect: (payload) => apiPost<TableInspectionResult>("/api/disclosures/table/inspect", payload),
    onError: (message) => {
      setStatus(message);
      setIsErrorStatus(true);
    },
  });
  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus, cancelJob } = useJobPolling({
    pollingEndpoint: "/api/disclosures/table/jobs/{jobId}",
    cancelEndpoint: "/api/disclosures/table/build/cancel",
    onSuccess: (result: any, jobId) => {
      const context = activeBuildInspectionRef.current;
      if (!context || context.jobId !== jobId) return;
      activeBuildInspectionRef.current = null;
      if (context.key !== currentInspectionKeyRef.current) return;
      const summary = result?.summary;
      acceptInspectionResult({
        format: "finiq_disclosure_table_inspection_v1",
        confirmed: true,
        reason: "변환 과정에서 다운로드한 원본 데이터와 변환 기록, 연도별 SQLite 파일의 건수를 모두 확인했습니다.",
        manifest_path: String(result?.manifest_path || ""),
        summary: summary ? {
          source_rows: Number(summary.source_rows || 0),
          duplicate_rows: Number(summary.duplicate_rows || 0),
          disclosures: Number(summary.disclosures || 0),
          shards: Number(summary.shards || 0),
        } : undefined,
      });
    },
    onError: (_error, jobId) => {
      if (activeBuildInspectionRef.current?.jobId === jobId) {
        activeBuildInspectionRef.current = null;
      }
    },
    onCancel: (jobId) => {
      if (activeBuildInspectionRef.current?.jobId === jobId) {
        activeBuildInspectionRef.current = null;
      }
    },
  });
  
  // Form State
  const [outputPath, setOutputPath] = useState("");
  const [tableWorkers, setTableWorkers] = useState("1");
  const [maxTableWorkers, setMaxTableWorkers] = useState(1);
  const currentInspectionPayload: TableInspectionPayload = {
    data_root: dataRoot,
    root_directory: useSeparateOutputDirectory ? downloadOutputDirectory : "",
    output_path: useSeparateOutputDirectory ? outputPath : "",
    table_workers: Number(tableWorkers),
  };
  currentInspectionKeyRef.current = JSON.stringify(currentInspectionPayload);

  const fetchConfig = useCallback(async () => {
    try {
      const config = await fetchSettings();
      if (config) {
        if (typeof config.sqlite_output_directory !== "string") {
          throw new Error("sqlite_output_directory must be a string");
        }
        setOutputPath(config.sqlite_output_directory);
        const workerCount = Number(config.parallel_worker_count);
        if (!Number.isInteger(workerCount) || workerCount < 1) {
          throw new Error("parallel_worker_count must be a positive integer");
        }
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

  useEffect(() => {
    clearInspection();
  }, [
    clearInspection,
    dataRoot,
    downloadOutputDirectory,
    outputPath,
    tableWorkers,
    useSeparateOutputDirectory,
  ]);

  const handleWorkspaceDirectoryChange = async (value: string) => {
    if (await saveSetting("output_root", value)) {
      const settings = useSettingsStore.getState();
      setOutputPath(settings.sqlite_output_directory);
    }
  };

  const handleBuild = async () => {
    if (!dataRoot) {
      setStatus("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (useSeparateOutputDirectory && !outputPath.trim()) {
      setStatus("결과 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const configuredWorkers = Number(tableWorkers);
    if (!Number.isInteger(configuredWorkers) || configuredWorkers < 1) {
      setStatus("table_workers must be a positive integer");
      setIsErrorStatus(true);
      return;
    }
    try {
      setStatus("SQLite 테이블 생성을 시작하는 중...");
      const payload = {
        ...currentInspectionPayload,
        table_name: "disclosures",
      };
      const inspectionKey = JSON.stringify(currentInspectionPayload);
      const response = await fetch("/api/disclosures/table/build/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.error || "Build start failed");
      }
      
      const data = await response.json();
      activeBuildInspectionRef.current = { jobId: data.job_id, key: inspectionKey };
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleInspect = async () => {
    if (!dataRoot) {
      setStatus("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (useSeparateOutputDirectory && (!downloadOutputDirectory.trim() || !outputPath.trim())) {
      setStatus("입력 및 결과 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const configuredWorkers = Number(tableWorkers);
    if (!Number.isInteger(configuredWorkers) || configuredWorkers < 1) {
      setStatus("table_workers must be a positive integer");
      setIsErrorStatus(true);
      return;
    }
    const payload = currentInspectionPayload;
    setStatus("기존 변환 데이터 검사를 시작합니다...");
    setIsErrorStatus(false);
    const result = await runInspection(payload, JSON.stringify(payload));
    if (!result) return;
    setStatus(result.confirmed ? "정상" : result.reason);
    setIsErrorStatus(!result.confirmed);
  };

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  const hasInspectionInput = !!dataRoot
    && (!useSeparateOutputDirectory || (!!downloadOutputDirectory.trim() && !!outputPath.trim()));
  const inspectionState: SingleCheckDataIntegrityInspectionState = !hasInspectionInput
    ? "waiting"
    : inspectionRunning
      ? "running"
      : inspectionError || inspectionResult?.confirmed === false
        ? "failed"
        : inspectionResult?.confirmed
          ? "success"
          : "ready";
  const inspectionCopy = {
    waiting: ["데이터 경로를 선택하세요", "입력 경로와 결과 경로를 선택한 다음 기존 SQLite 변환 결과를 검사하세요."],
    ready: ["기존 변환 데이터 검사가 필요합니다", "현재 입력과 결과 경로를 기준으로 전체 구성을 확인하세요."],
    running: ["기존 변환 데이터를 확인하고 있습니다", "다운로드한 원본 데이터와 변환 기록, 연도별 SQLite 파일의 내용이 서로 일치하는지 확인합니다."],
    success: ["기존 변환 데이터를 그대로 사용해도 됩니다", inspectionResult?.reason || "정상"],
    failed: ["기존 변환 데이터에 문제가 있습니다", inspectionError || inspectionResult?.reason || "검사 결과를 확인하세요."],
  }[inspectionState];
  const inspectionSummary = inspectionResult?.summary;
  const inspectionStepSummary = inspectionSummary
    ? `원본 데이터 ${formatInteger(inspectionSummary.source_rows)}행 중 중복된 ${formatInteger(inspectionSummary.duplicate_rows)}행을 제외한 ${formatInteger(inspectionSummary.disclosures)}행이 연도별 SQLite 파일 ${formatInteger(inspectionSummary.shards)}개에 저장되어 있습니다.`
    : inspectionResult?.reason || "원본 데이터의 페이지별 건수, 변환 기록의 요약, 연도별 SQLite 파일의 행 수가 일치하는지 확인합니다.";

  return (
    <WorkflowPageShell workflowId="disclosure-build">
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          <SingleCheckDataIntegrityInspectionCard
            description="실행 전에 다운로드한 원본 데이터와 변환 기록, 연도별 SQLite 파일의 내용이 서로 일치하는지 확인합니다."
            state={inspectionState}
            verdictTitle={inspectionCopy[0]}
            verdictDescription={inspectionCopy[1]}
            stepTitle="원본 데이터와 변환 결과 검사"
            stepSummary={inspectionStepSummary}
            action={hasInspectionInput && !inspectionResult ? {
              label: inspectionRunning ? "검사 중..." : "검사하기",
              onClick: handleInspect,
              disabled: inspectionRunning || !!activeJobId,
              loading: inspectionRunning,
            } : undefined}
          />

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
          notificationTone="error"
          notificationContent={
            <div className={isErrorStatus ? "whitespace-pre-wrap text-sm text-[var(--tv-down-text)]" : "text-sm text-[var(--tv-muted)]"}>{isErrorStatus ? status : "알림 없음"}</div>
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
                  연도별 SQLite 파일 생성 worker 수
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
                  최대 {maxTableWorkers}개까지 사용합니다. 실제 worker 수는 CPU 코어 수와 연도별 SQLite 파일 수 중 작은 값으로 제한됩니다.
                </p>
              </div>
            </div>
          }
        />
      </div>
    </WorkflowPageShell>
  );
}
