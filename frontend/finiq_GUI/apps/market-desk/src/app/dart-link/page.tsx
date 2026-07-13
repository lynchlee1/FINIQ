"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Play } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Label,
} from "@finiq/ui";
import { ActionDock, JobStatusLogger, PageLoadingSpinner } from "@finiq/web-app/status";
import { apiPost } from "@/api/client";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { UI_TEXT } from "@/config/uiText";
import { useJobPolling } from "@/hooks/useJobPolling";
import { formatInteger } from "@/lib/format";
import { useSettingsStore } from "@/store/useSettingsStore";
import type { JobStartResponse } from "@/types/api";

type DartLinkSummary = {
  total: number;
  matched: number;
  confirmed_absent: number;
  unresolved: number;
  ambiguous: number;
  lookup_failed: number;
  reused: number;
  queried: number;
};

type DartLinkResult = {
  output_directory: string;
  manifest_path: string;
  contains_dart_html: false;
  summary: DartLinkSummary;
};

const STATUS_ROWS: { key: keyof DartLinkSummary; label: string }[] = [
  { key: "matched", label: "연결 완료" },
  { key: "confirmed_absent", label: "DART 공시 없음 확인" },
  { key: "unresolved", label: "확인 불가" },
  { key: "ambiguous", label: "후보 중복" },
  { key: "lookup_failed", label: "조회 실패" },
];

function canonicalOutputDirectory(dataRoot: string) {
  const normalized = dataRoot.trim().replace(/[\\/]+$/, "");
  return normalized ? `${normalized}/01-list/dart-links` : "";
}

export default function DartLinkPage() {
  const { output_root: dataRoot, fetchSettings, saveSetting } = useSettingsStore();
  const [loading, setLoading] = useState(true);
  const [dartApiKey, setDartApiKey] = useState("");
  const [result, setResult] = useState<DartLinkResult | null>(null);

  const {
    status,
    isErrorStatus,
    activeJobId,
    startPolling,
    setStatus,
    setIsErrorStatus,
    cancelJob,
  } = useJobPolling({
    pollingEndpoint: "/api/disclosures/dart-links/jobs/{jobId}",
    cancelEndpoint: "/api/disclosures/dart-links/cancel",
    onSuccess: (nextResult: DartLinkResult) => {
      setResult(nextResult);
      setDartApiKey("");
    },
  });

  const outputDirectory = useMemo(
    () => result?.output_directory || canonicalOutputDirectory(dataRoot),
    [dataRoot, result],
  );

  const loadSettings = useCallback(async () => {
    await fetchSettings();
    setLoading(false);
  }, [fetchSettings]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const handleWorkspaceDirectoryChange = async (value: string) => {
    setResult(null);
    if (!(await saveSetting("output_root", value))) {
      setStatus("작업공간 디렉토리를 저장하지 못했습니다.");
      setIsErrorStatus(true);
    }
  };

  const handleRun = async () => {
    if (!dataRoot.trim()) {
      setStatus("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (dartApiKey && dartApiKey.length !== 40) {
      setStatus("OpenDART API 키는 40자여야 합니다.");
      setIsErrorStatus(true);
      return;
    }

    try {
      setResult(null);
      setStatus("KIND-DART 연결을 시작하는 중...");
      setIsErrorStatus(false);
      const response = await apiPost<JobStartResponse>(
        "/api/disclosures/dart-links/build/start",
        {
          data_root: dataRoot,
          ...(dartApiKey ? { dart_api_key: dartApiKey } : {}),
        },
      );
      setDartApiKey("");
      startPolling(response.job_id);
    } catch (error) {
      const message = error instanceof Error ? error.message : "KIND-DART 연결을 시작하지 못했습니다.";
      setStatus(message);
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
          <Card className="dark:border-[#30363d] dark:bg-[#161b22]">
            <CardHeader>
              <CardTitle className="dark:text-white">데이터 경로</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label className="dark:text-slate-300">작업공간 디렉토리</Label>
                <PathPickerInput
                  value={dataRoot}
                  onChange={handleWorkspaceDirectoryChange}
                  mode="folder"
                  placeholder="작업공간 디렉토리를 선택하세요"
                  onError={(error) => {
                    setStatus(error.message);
                    setIsErrorStatus(true);
                  }}
                />
              </div>
              <div className="space-y-2">
                <Label className="dark:text-slate-300">결과 데이터 경로</Label>
                <Input
                  value={outputDirectory}
                  readOnly
                  aria-readonly="true"
                  className="dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-300"
                />
              </div>
              <p className="text-sm leading-6 text-slate-500 dark:text-slate-400">
                입력은 02-table의 유효한 SQLite manifest를 우선하고, 없으면 01-list에서 읽습니다. DART 원문은 저장하지 않습니다.
              </p>
            </CardContent>
          </Card>

          <Card className="dark:border-[#30363d] dark:bg-[#161b22]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="dart-api-key" className="dark:text-slate-300">OpenDART API 키</Label>
                <Input
                  id="dart-api-key"
                  type="password"
                  value={dartApiKey}
                  onChange={(event) => setDartApiKey(event.target.value.trim())}
                  maxLength={40}
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="서버 환경변수를 사용하면 비워 두세요"
                  disabled={!!activeJobId}
                  className="dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-200"
                />
                <p className="text-xs leading-5 text-slate-500 dark:text-slate-400">
                  입력한 키는 이번 요청에만 사용하며 설정이나 결과 파일에 저장하지 않습니다.
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <Button className="w-full" onClick={handleRun} disabled={!!activeJobId || !dataRoot.trim()}>
                  {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                <Button variant="outline" className="w-full" onClick={cancelJob} disabled={!activeJobId}>
                  {UI_TEXT.actions.cancelJob}
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="dark:border-[#30363d] dark:bg-[#161b22]">
            <CardHeader>
              <CardTitle className="dark:text-white">연결 결과</CardTitle>
            </CardHeader>
            <CardContent>
              {result ? (
                <div className="space-y-4">
                  <div className="overflow-hidden rounded-md border border-slate-200 dark:border-[#30363d]">
                    <table className="w-full text-sm">
                      <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
                        <tr>
                          <th scope="row" className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-300">전체 KIND 공시</th>
                          <td className="px-4 py-3 text-right font-mono text-slate-900 dark:text-slate-100">{formatInteger(result.summary.total)}</td>
                        </tr>
                        {STATUS_ROWS.map((row) => (
                          <tr key={row.key}>
                            <th scope="row" className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-300">{row.label}</th>
                            <td className="px-4 py-3 text-right font-mono text-slate-900 dark:text-slate-100">{formatInteger(result.summary[row.key])}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    재사용 {formatInteger(result.summary.reused)}건, 이번 조회 {formatInteger(result.summary.queried)}건
                  </p>
                  <p className="break-all text-xs text-slate-500 dark:text-slate-400">
                    manifest: {result.manifest_path}
                  </p>
                </div>
              ) : (
                <p className="text-sm text-slate-500 dark:text-slate-400">실행 결과가 아직 없습니다.</p>
              )}
            </CardContent>
          </Card>
        </section>

        <ActionDock
          activityActive={!!activeJobId}
          activityContent={(
            <JobStatusLogger
              status={status}
              isErrorStatus={isErrorStatus}
              isCancellable={!!activeJobId}
              onCancel={cancelJob}
            />
          )}
          notificationActive={isErrorStatus}
          notificationContent={(
            <div className={isErrorStatus ? "whitespace-pre-wrap text-sm text-red-600 dark:text-red-300" : "text-sm text-slate-500 dark:text-slate-400"}>
              {isErrorStatus ? status : "알림 없음"}
            </div>
          )}
        />
      </div>
    </WorkflowPageShell>
  );
}
