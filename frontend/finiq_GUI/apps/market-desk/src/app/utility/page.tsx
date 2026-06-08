"use client"

import { useEffect, useMemo, useState } from "react";
import { FolderTree, Loader2, Play } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Checkbox, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { useJobPolling } from "@/hooks/useJobPolling";
import { useSettingsStore } from "@/store/useSettingsStore";
import { ActionDock } from "@/components/ui/ActionDock";

type PartitionMode = "split" | "flatten";

function formatResult(result: any): string[] {
  if (!result) return [];
  const modeLabel = result.mode === "flatten" ? "분할저장 해제" : "분할저장";
  const lines = [
    `${modeLabel} 완료`,
    `입력 파일: ${result.input_files || 0}개`,
    `복사 파일: ${result.copied_files || 0}개`,
    `기존 파일 건너뜀: ${result.skipped_existing_files || 0}개`,
  ];
  if (result.skipped_invalid_year_files) {
    lines.push(`연도 판별 불가: ${result.skipped_invalid_year_files}개`);
  }
  if (result.years?.length) {
    lines.push(`대상 연도: ${result.years.join(", ")}`);
  }
  lines.push(`저장 경로: ${result.output_directory || ""}`);
  return lines;
}

export default function UtilityPage() {
  const [mode, setMode] = useState<PartitionMode>("split");
  const [sourceDirectory, setSourceDirectory] = useState("");
  const [outputDirectory, setOutputDirectory] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [loading, setLoading] = useState(true);

  const { output_root, fetchSettings } = useSettingsStore();
  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus } = useJobPolling({
    pollingEndpoint: "/api/utility/jobs/{jobId}",
    formatStatus: (data) => {
      const statusLabel = data.status === "completed" ? "완료" : data.status === "failed" ? "실패" : data.status === "running" ? "실행 중" : "대기 중";
      const lines = [`작업 상태: ${statusLabel}`];
      if (data.error) lines.push(`오류: ${data.error}`);
      if (data.progress_log?.length) lines.push("", "최근 로그:", ...data.progress_log.slice(-10));
      if (data.status === "completed") lines.push("", ...formatResult(data.result));
      return lines;
    },
  });

  useEffect(() => {
    fetchSettings().then((config) => {
      const root = config?.output_root || output_root || "";
      if (root) {
        setSourceDirectory((current) => current || root);
        setOutputDirectory((current) => current || root);
      }
      setLoading(false);
    });
  }, [fetchSettings, output_root]);

  const actionLabel = useMemo(
    () => mode === "flatten" ? "분할저장 해제 실행" : "분할저장 실행",
    [mode],
  );

  const handleStart = async () => {
    if (activeJobId) return;
    if (!sourceDirectory.trim()) {
      setStatus("입력 폴더를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (!outputDirectory.trim()) {
      setStatus("저장 폴더를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }

    setStatus("작업을 시작하는 중...");
    setIsErrorStatus(false);

    try {
      const response = await fetch("/api/utility/partition-storage/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          source_directory: sourceDirectory,
          output_directory: outputDirectory,
          overwrite,
        }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || errData.error || `HTTP ${response.status}`);
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
    <WorkflowPageShell workflowId="utility">
      <div className="relative space-y-6">
        <section className="min-w-0 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Storage Utility</p>
              <CardTitle className="text-xl dark:text-white">분할저장</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">입력 폴더</Label>
                  <PathPickerInput mode="folder" value={sourceDirectory} onChange={setSourceDirectory} placeholder="/path/to/source" onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }} />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">저장 폴더</Label>
                  <PathPickerInput mode="folder" value={outputDirectory} onChange={setOutputDirectory} placeholder="/path/to/output" onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }} />
                </div>
              </div>
              <Button onClick={handleStart} disabled={!!activeJobId} className="w-full md:w-auto">
                {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                {actionLabel}
              </Button>
            </CardContent>
          </Card>
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base dark:text-white">
                <FolderTree className="h-4 w-4" />
                처리 기준
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-slate-600 dark:text-slate-400">
              <p>파일명 앞 4자리가 숫자인 파일만 처리합니다.</p>
              <p>출력 경로에 같은 이름이 있으면 덮어쓰기 옵션이 꺼진 경우 건너뜁니다.</p>
            </CardContent>
          </Card>
        </section>
        <ActionDock
          activityActive={!!activeJobId}
          activityContent={<JobStatusLogger status={status} isErrorStatus={isErrorStatus} />}
          notificationActive={isErrorStatus}
          notificationContent={<JobStatusLogger status={status || "알림 없음"} isErrorStatus={isErrorStatus} />}
          settingsTitle="분할저장 설정"
          settingsContent={
            <>
              <div className="space-y-2">
                <Label className="dark:text-slate-300">변환 방향</Label>
                <Select value={mode} onValueChange={(value) => setMode(value as PartitionMode)}>
                  <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"><SelectValue /></SelectTrigger>
                  <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                    <SelectItem value="split">일반 폴더 → 연도별 폴더</SelectItem>
                    <SelectItem value="flatten">연도별 폴더 → 일반 폴더</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 dark:border-[#30363d]">
                <Checkbox id="overwrite" checked={overwrite} onCheckedChange={(checked) => setOverwrite(checked === true)} className="dark:border-[#30363d]" />
                <Label htmlFor="overwrite" className="text-sm dark:text-slate-300">기존 파일 덮어쓰기</Label>
              </div>
            </>
          }
        />
      </div>
    </WorkflowPageShell>
  );
}
