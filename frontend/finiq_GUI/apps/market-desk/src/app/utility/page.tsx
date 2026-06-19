"use client"

import { useMemo, useState } from "react";
import { FolderTree, Loader2, Play } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { useJobPolling } from "@/hooks/useJobPolling";
import { ActionDock } from "@/components/ui/ActionDock";
import { UI_TEXT } from "@/config/uiText";
import { formatInteger } from "@/lib/format";

type PartitionMode = "split" | "flatten";

function formatResult(result: any): string[] {
  if (!result) return [];
  const modeLabel = result.mode === "flatten" ? "분할저장 해제" : "분할저장";
  const lines = [
    `${modeLabel} 완료`,
    `입력 파일: ${formatInteger(result.input_files)}개`,
    `복사 파일: ${formatInteger(result.copied_files)}개`,
    `이동 파일: ${formatInteger(result.moved_files || 0)}개`,
    `기존 파일 건너뜀: ${formatInteger(result.skipped_existing_files)}개`,
  ];
  if (result.skipped_invalid_year_files) {
    lines.push(`연도 판별 불가: ${formatInteger(result.skipped_invalid_year_files)}개`);
  }
  if (result.years?.length) {
    lines.push(`대상 연도: ${result.years.join(", ")}`);
  }
  lines.push(`데이터 경로: ${result.output_directory || ""}`);
  return lines;
}

export default function UtilityPage() {
  const [mode, setMode] = useState<PartitionMode>("split");
  const [sourceDirectory, setSourceDirectory] = useState("");
  const [outputDirectory, setOutputDirectory] = useState("");

  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus, cancelJob } = useJobPolling({
    pollingEndpoint: "/api/utility/jobs/{jobId}",
    cancelEndpoint: "/api/utility/cancel",
    formatStatus: (data) => {
      const statusLabel =
        data.status === "completed" ? "완료" :
        data.status === "failed" ? "실패" :
        data.status === "running" ? "실행 중" :
        data.status === "cancelled" ? "중단됨" :
        "대기 중";
      const lines = [`작업 상태: ${statusLabel}`];
      if (data.error) lines.push(`오류: ${data.error}`);
      if (data.progress_log?.length) lines.push("", "최근 로그:", ...data.progress_log.slice(-10));
      if (data.status === "completed") lines.push("", ...formatResult(data.result));
      return lines;
    },
  });

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
      setStatus("데이터 경로를 선택하세요.");
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
          overwrite: false,
          move: false,
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

  return (
    <WorkflowPageShell workflowId="utility">
      <div className="relative space-y-6">
        <section className="min-w-0 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">데이터 경로</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">입력 데이터 경로</Label>
                  <PathPickerInput mode="folder" value={sourceDirectory} onChange={setSourceDirectory} placeholder="/path/to/source" onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }} />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">결과 데이터 경로</Label>
                  <PathPickerInput mode="folder" value={outputDirectory} onChange={setOutputDirectory} placeholder="/path/to/output" onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }} />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-2">
                <Button onClick={handleStart} disabled={!!activeJobId || !sourceDirectory.trim() || !outputDirectory.trim()} className="w-full">
                  {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  {actionLabel}
                </Button>
                <Button variant="outline" onClick={cancelJob} disabled={!activeJobId} className="w-full">
                  {UI_TEXT.actions.cancelJob}
                </Button>
              </div>
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
          activityContent={
            <JobStatusLogger
              status={status}
              isErrorStatus={isErrorStatus}
              isCancellable={!!activeJobId}
              onCancel={cancelJob}
            />
          }
          notificationActive={isErrorStatus}
          notificationContent={<div className={isErrorStatus ? "whitespace-pre-wrap text-sm text-red-600 dark:text-red-300" : "text-sm text-slate-500 dark:text-slate-400"}>{isErrorStatus ? status : "알림 없음"}</div>}
          settingsTitle="시스템 설정"
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
            </>
          }
        />
      </div>
    </WorkflowPageShell>
  );
}
