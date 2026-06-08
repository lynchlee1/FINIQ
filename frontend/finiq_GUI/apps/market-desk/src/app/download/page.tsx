"use client"

import { useState, useEffect, useCallback } from "react";
import { Activity, Bell, X, Play, Search, Loader2, Trash2, FolderOpen, Square, Settings, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { Checkbox } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { cancelDownload, fetchDownloadOptions, inspectDownloadFolder, previewDownload, startDownload } from "@/features/download/api";
import type { DisclosureItem, DownloadOptions, DownloadPayload } from "@/features/download/types";

export default function DownloadPage() {
  const [options, setOptions] = useState<DownloadOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [downloadPanelOpen, setDownloadPanelOpen] = useState(false);
  const [notificationPanelOpen, setNotificationPanelOpen] = useState(false);
  const [settingsPanelOpen, setSettingsPanelOpen] = useState(false);

  const { download_output_directory: outputDirectory, saveSetting } = useSettingsStore();

  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus } = useJobPolling({
    pollingEndpoint: "/api/download/jobs/{jobId}",
    onSuccess: (data) => setResult(data.result || data),
  });

  // Form State
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [submitterName, setSubmitterName] = useState("");
  const [marketLabel, setMarketLabel] = useState("검색대상");
  const [securitiesLabel, setSecuritiesLabel] = useState("전체");
  const [pageSize, setPageSize] = useState("100");
  const [waitSeconds, setWaitSeconds] = useState("1");
  const [timeout, setTimeoutVal] = useState("20");
  const [workerCount, setWorkerCount] = useState("1");
  const [startPage, setStartPage] = useState("1");
  const [endPage, setEndPage] = useState("");
  const [lastReportOnly, setLastReportOnly] = useState(false);
  const [resumeYearly, setResumeYearly] = useState(true);
  const [logLimit, setLogLimit] = useState("20");
  const [selectedDisclosures, setSelectedDisclosures] = useState<Record<string, string[]>>({});
  const [deleteConfirmed, setDeleteConfirmed] = useState(false);
  const [deleteConfirmationText, setDeleteConfirmationText] = useState("");
  const [inspectRunning, setInspectRunning] = useState(false);
  const [lastInspectionCandidateCount, setLastInspectionCandidateCount] = useState(0);
  const [expandedDisclosureGroups, setExpandedDisclosureGroups] = useState<Record<string, boolean>>({});

  const fetchOptions = useCallback(async () => {
    try {
      const data = await fetchDownloadOptions();
      setOptions(data);
      
      if (!useSettingsStore.getState().download_output_directory && data.default_output_directory) {
        saveSetting("download_output_directory", data.default_output_directory);
      }
      
      const today = new Date();
      const start = new Date(today);
      start.setDate(today.getDate() - 30);
      setStartDate(start.toISOString().slice(0, 10));
      setEndDate(today.toISOString().slice(0, 10));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOptions();
  }, [fetchOptions]);

  const buildPayload = (): DownloadPayload => ({
    mode: "yearly",
    output_directory: outputDirectory,
    start_date: startDate,
    end_date: endDate,
    company_name: companyName,
    submitter_name: submitterName,
    market_label: marketLabel,
    securities_label: securitiesLabel,
    page_size: Number(pageSize),
    wait_seconds: Number(waitSeconds),
    timeout: Number(timeout),
    worker_count: Number(workerCount),
    log_limit: Number(logLimit),
    start_page: Number(startPage),
    end_page: endPage ? Number(endPage) : null,
    last_report_only: lastReportOnly,
    resume_yearly: resumeYearly,
    disclosure_type_groups: selectedDisclosures,
  });

  const handlePreview = async () => {
    try {
      setStatus("미리보기 생성 중...");
      const data = await previewDownload(buildPayload());
      setResult(data);
      setStatus("미리보기 완료");
      setNotificationPanelOpen(true);
      setDownloadPanelOpen(false);
      setSettingsPanelOpen(false);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
      setNotificationPanelOpen(true);
      setDownloadPanelOpen(false);
      setSettingsPanelOpen(false);
    }
  };

  const startDownloadJob = async () => {
    const data = await startDownload(buildPayload());
    setResult(null);
    setDownloadPanelOpen(true);
    setNotificationPanelOpen(false);
    setSettingsPanelOpen(false);
    startPolling(data.job_id);
  };

  const handleCancelDownload = async () => {
    if (!activeJobId) return;
    try {
      setStatus("다운로드 중단을 요청했습니다. 진행 중인 요청이 끝나면 멈춥니다.");
      await cancelDownload(activeJobId);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const inspectExistingFiles = async (dryRun: boolean) => {
    return inspectDownloadFolder({
      ...buildPayload(),
      dry_run: dryRun,
      delete_confirmed: deleteConfirmed,
      delete_confirmation_text: deleteConfirmationText,
    });
  };

  const buildInspectionStatus = (data: any, deleted: boolean) => {
    const files = Array.isArray(deleted ? data.deleted_files : data.deletion_candidates)
      ? (deleted ? data.deleted_files : data.deletion_candidates)
      : [];
    const lines = [
      deleted ? "파일 삭제 완료" : "폴더 검사 완료",
      `대상 페이지: ${data.requested_count || data.summary?.total || 0}`,
      `연도별 분할: ${data.split_by_year ? "On" : "Off"}`,
      `${deleted ? "삭제 파일" : "삭제 예정 파일"}: ${deleted ? data.deleted_count || 0 : data.deletion_candidate_count || 0}`,
      `최신 상태: 성공 ${data.summary?.success || 0}/${data.summary?.total || 0}건`,
      `저장 경로: ${data.output_directory || ""}`,
    ];
    if (files.length) {
      lines.push("", deleted ? "삭제한 파일" : "삭제 예정 파일", ...files.map((file: any) => `- ${file.name} (${file.reason})`));
    }
    return lines.join("\n");
  };

  const handleInspectFolder = async () => {
    if (!outputDirectory) {
      setStatus("저장 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      setInspectRunning(true);
      setIsErrorStatus(false);
      setStatus("폴더를 검사하는 중입니다...");
      const data = await inspectExistingFiles(true);
      const candidateCount = data.deletion_candidate_count || 0;
      setLastInspectionCandidateCount(candidateCount);
      setResult(data);
      setStatus(buildInspectionStatus(data, false));
      setNotificationPanelOpen(true);
      setDownloadPanelOpen(false);
      setSettingsPanelOpen(false);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
      setNotificationPanelOpen(true);
      setDownloadPanelOpen(false);
      setSettingsPanelOpen(false);
    } finally {
      setInspectRunning(false);
    }
  };

  const handleRun = async () => {
    try {
      setStatus("기존 다운로드 파일을 검사하는 중...");
      const inspection = await inspectExistingFiles(true);
      const candidates = Array.isArray(inspection.deletion_candidates) ? inspection.deletion_candidates : [];
      setLastInspectionCandidateCount(inspection.deletion_candidate_count || 0);
      if (candidates.length) {
        setResult(inspection);
        setStatus(buildInspectionStatus(inspection, false));
        setIsErrorStatus(false);
        setNotificationPanelOpen(true);
        setDownloadPanelOpen(false);
        setSettingsPanelOpen(false);
        return;
      }
      setStatus("다운로드 작업을 시작하는 중...");
      await startDownloadJob();
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleDeleteUnexpectedFiles = async () => {
    try {
      if (!deleteConfirmed || deleteConfirmationText.trim() !== "확인했습니다.") {
        setStatus('삭제하려면 삭제 허가를 체크하고 "확인했습니다."를 입력하세요.');
        setIsErrorStatus(true);
        setNotificationPanelOpen(true);
        setDownloadPanelOpen(false);
        setSettingsPanelOpen(false);
        return;
      }
      setInspectRunning(true);
      setIsErrorStatus(false);
      setStatus("확인된 기존 파일을 삭제하는 중...");
      const inspection = await inspectExistingFiles(false);
      setLastInspectionCandidateCount(0);
      setDeleteConfirmed(false);
      setDeleteConfirmationText("");
      setResult(inspection);
      setStatus(buildInspectionStatus(inspection, true));
      setNotificationPanelOpen(true);
      setDownloadPanelOpen(false);
      setSettingsPanelOpen(false);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
      setNotificationPanelOpen(true);
      setDownloadPanelOpen(false);
      setSettingsPanelOpen(false);
    } finally {
      setInspectRunning(false);
    }
  };

  const toggleDisclosure = (suffix: string, code: string) => {
    setSelectedDisclosures(prev => {
      const current = prev[suffix] || [];
      const next = current.includes(code) 
        ? current.filter(c => c !== code) 
        : [...current, code];
      
      const newObj = { ...prev };
      if (next.length === 0) delete newObj[suffix];
      else newObj[suffix] = next;
      return newObj;
    });
  };

  const selectGroup = (suffix: string, items: DisclosureItem[]) => {
    setSelectedDisclosures(prev => ({
      ...prev,
      [suffix]: items.map(i => i.code)
    }));
  };

  const clearGroup = (suffix: string) => {
    setSelectedDisclosures(prev => {
      const newObj = { ...prev };
      delete newObj[suffix];
      return newObj;
    });
  };

  const toggleDisclosureGroup = (suffix: string) => {
    setExpandedDisclosureGroups(prev => ({
      ...prev,
      [suffix]: !prev[suffix],
    }));
  };

  if (loading) {
    return <PageLoadingSpinner message="옵션을 불러오는 중입니다..." />;
  }

  return (
    <WorkflowPageShell workflowId="disclosure-build">
      <div className="relative space-y-6" onClick={() => setNotificationPanelOpen(false)}>
        <section className="min-w-0 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Download Settings</p>
              <CardTitle className="dark:text-white">기본 설정</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label className="dark:text-slate-300">저장 경로</Label>
                <PathPickerInput 
                  value={outputDirectory} 
                  onChange={(val) => saveSetting("download_output_directory", val)} 
                  placeholder="저장 경로를 선택하세요" 
                  mode="folder"
                  onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                />
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">시작일</Label>
                  <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 dark:[color-scheme:dark]" />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">종료일</Label>
                  <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 dark:[color-scheme:dark]" />
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">회사명</Label>
                  <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">제출인</Label>
                  <Input value={submitterName} onChange={(e) => setSubmitterName(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">시장</Label>
                  <Select value={marketLabel} onValueChange={setMarketLabel}>
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"><SelectValue /></SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      {options?.market_types.map(t => <SelectItem key={t.label} value={t.label}>{t.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">증권종류</Label>
                  <Select value={securitiesLabel} onValueChange={setSecuritiesLabel}>
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"><SelectValue /></SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      {options?.securities_types.map(t => <SelectItem key={t.label} value={t.label}>{t.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Disclosure Types</p>
              <CardTitle className="dark:text-white">공시 종류</CardTitle>
              <CardDescription className="dark:text-slate-400">다운로드할 공시 종류를 선택하세요.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {options?.disclosure_groups.map((group) => (
                <div key={group.suffix} className="border rounded-lg overflow-hidden dark:border-[#30363d]">
                  <div className="bg-slate-50 dark:bg-[#0d1117] px-4 py-2 border-b dark:border-[#30363d] flex items-center justify-between gap-3">
                    <button
                      type="button"
                      onClick={() => toggleDisclosureGroup(group.suffix)}
                      className="flex min-w-0 flex-1 items-center gap-2 text-left font-semibold text-sm dark:text-slate-200"
                    >
                      {expandedDisclosureGroups[group.suffix] ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
                      <span className="truncate">{group.label} ({group.items.length})</span>
                    </button>
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-[#21262d]"
                        onClick={() => selectGroup(group.suffix, group.items)}
                      >
                        전체 선택
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-[#21262d]"
                        onClick={() => clearGroup(group.suffix)}
                      >
                        전체 해제
                      </Button>
                    </div>
                  </div>
                  {expandedDisclosureGroups[group.suffix] && (
                    <div className="p-4 grid grid-cols-2 md:grid-cols-3 gap-2">
                      {group.items.map((item) => (
                        <div key={item.code} className="flex items-center space-x-2">
                          <Checkbox 
                            id={`${group.suffix}-${item.code}`} 
                            checked={selectedDisclosures[group.suffix]?.includes(item.code) || false}
                            onCheckedChange={() => toggleDisclosure(group.suffix, item.code)}
                            className="dark:border-[#30363d]"
                          />
                          <Label 
                            htmlFor={`${group.suffix}-${item.code}`} 
                            className="text-xs cursor-pointer truncate dark:text-slate-400 dark:hover:text-slate-200"
                            title={item.name}
                          >
                            {item.name}
                          </Label>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Run</p>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-4">
                <Button variant="outline" className="w-full" onClick={handleInspectFolder} disabled={!!activeJobId || inspectRunning}>
                  {inspectRunning ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FolderOpen className="mr-2 h-4 w-4" />}
                  폴더 검사하기
                </Button>
                <Button variant="outline" className="w-full" onClick={handlePreview} disabled={!!activeJobId}>
                  <Search className="mr-2 h-4 w-4" />
                  미리보기
                </Button>
                <Button className="w-full" onClick={handleRun} disabled={!!activeJobId}>
                  {!!activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                <Button variant="outline" className="w-full" onClick={handleCancelDownload} disabled={!activeJobId}>
                  중단
                </Button>
              </div>

            </CardContent>
          </Card>
        </section>

        <div className="absolute left-full top-0 z-40 ml-2" onClick={(event) => event.stopPropagation()}>
          <div className="flex w-16 flex-col items-center gap-2 rounded-lg border border-slate-200 bg-white p-2 shadow-lg dark:border-[#30363d] dark:bg-[#161b22]">
            <Button
              variant="outline"
              size="icon"
              onClick={() => {
                setDownloadPanelOpen((value) => !value);
                setNotificationPanelOpen(false);
                setSettingsPanelOpen(false);
              }}
              className={
                activeJobId
                  ? "relative h-10 w-10 border-blue-300 bg-blue-50 text-blue-700 shadow-sm dark:border-blue-500/60 dark:bg-blue-500/15 dark:text-blue-200"
                  : "relative h-10 w-10 border-slate-200 bg-white shadow-sm dark:border-[#30363d] dark:bg-[#161b22] dark:text-slate-300"
              }
              title={downloadPanelOpen ? "실행 현황 닫기" : "실행 현황 열기"}
            >
              <Activity className="h-5 w-5" />
              {activeJobId && (
                <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-blue-500 dark:bg-blue-300" />
              )}
            </Button>

            <Button
              variant="outline"
              size="icon"
              onClick={() => {
                setNotificationPanelOpen((value) => !value);
                setDownloadPanelOpen(false);
                setSettingsPanelOpen(false);
              }}
              className={
                lastInspectionCandidateCount > 0 || deleteConfirmed || !!result || isErrorStatus
                  ? "relative h-10 w-10 border-amber-300 bg-amber-50 text-amber-700 shadow-sm dark:border-amber-500/60 dark:bg-amber-500/15 dark:text-amber-200"
                  : "relative h-10 w-10 border-slate-200 bg-white shadow-sm dark:border-[#30363d] dark:bg-[#161b22] dark:text-slate-300"
              }
              title={notificationPanelOpen ? "알림 닫기" : "알림 열기"}
            >
              <Bell className="h-5 w-5" />
              {(lastInspectionCandidateCount > 0 || !!result || isErrorStatus) && (
                <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-amber-500 dark:bg-amber-300" />
              )}
            </Button>

            <Button
              variant="outline"
              size="icon"
              onClick={() => {
                setSettingsPanelOpen((value) => !value);
                setDownloadPanelOpen(false);
                setNotificationPanelOpen(false);
              }}
              className={
                settingsPanelOpen
                  ? "h-10 w-10 border-slate-400 bg-slate-100 text-slate-900 shadow-sm dark:border-slate-500 dark:bg-[#21262d] dark:text-slate-100"
                  : "h-10 w-10 border-slate-200 bg-white shadow-sm dark:border-[#30363d] dark:bg-[#161b22] dark:text-slate-300"
              }
              title={settingsPanelOpen ? "다운로드 설정 닫기" : "다운로드 설정 열기"}
            >
              <Settings className="h-5 w-5" />
            </Button>
          </div>

          {notificationPanelOpen && (
            <Card className="absolute right-full top-0 mr-3 w-[min(420px,calc(100vw-2rem))] max-h-[calc(100vh-8rem)] overflow-auto shadow-xl dark:bg-[#161b22] dark:border-[#30363d]">
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="dark:text-white">알림</CardTitle>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setNotificationPanelOpen(false)}
                    className="h-8 w-8 dark:hover:bg-[#21262d]"
                    title="알림 닫기"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">작업 알림</Label>
                  <JobStatusLogger status={status} isErrorStatus={isErrorStatus} />
                </div>

                {lastInspectionCandidateCount > 0 && (
                  <div className="space-y-4 border-t border-slate-200 pt-4 dark:border-[#30363d]">
                    <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
                      삭제 예정 파일 {lastInspectionCandidateCount}개
                    </div>
                    <div className="flex items-center space-x-2">
                      <Checkbox id="downloadDeleteConfirmed" checked={deleteConfirmed} onCheckedChange={(v) => setDeleteConfirmed(!!v)} className="dark:border-[#30363d]" />
                      <Label htmlFor="downloadDeleteConfirmed" className="cursor-pointer text-sm dark:text-slate-300">삭제 허가</Label>
                    </div>
                    <div className="space-y-2">
                      <Label className="dark:text-slate-300">확인 문구</Label>
                      <Input
                        value={deleteConfirmationText}
                        onChange={(e) => setDeleteConfirmationText(e.target.value)}
                        placeholder="확인했습니다."
                        className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                      />
                    </div>
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={handleDeleteUnexpectedFiles}
                      disabled={
                        !!activeJobId ||
                        inspectRunning ||
                        !deleteConfirmed ||
                        deleteConfirmationText.trim() !== "확인했습니다."
                      }
                    >
                      <Trash2 className="mr-2 h-4 w-4" />
                      삭제 예정 파일 {lastInspectionCandidateCount}개 삭제
                    </Button>
                  </div>
                )}

                {result && (
                  <div className="space-y-2 border-t border-slate-200 pt-4 dark:border-[#30363d]">
                    <Label className="dark:text-slate-300">결과</Label>
                    <pre className="max-h-72 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 dark:border-slate-700 dark:bg-[#090d12] dark:text-blue-100">
                      {JSON.stringify(result, null, 2)}
                    </pre>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {settingsPanelOpen && (
            <Card className="absolute right-full top-0 mr-3 w-[min(420px,calc(100vw-2rem))] max-h-[calc(100vh-8rem)] overflow-auto shadow-xl dark:bg-[#161b22] dark:border-[#30363d]">
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="dark:text-white">다운로드 설정</CardTitle>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setSettingsPanelOpen(false)}
                    className="h-8 w-8 dark:hover:bg-[#21262d]"
                    title="다운로드 설정 닫기"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="space-y-3">
                  <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">요청 설정</p>
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">페이지 크기</Label>
                    <Input type="number" value={pageSize} onChange={(e) => setPageSize(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">대기 시간 (초)</Label>
                    <Input type="number" value={waitSeconds} onChange={(e) => setWaitSeconds(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">타임아웃 (초)</Label>
                    <Input type="number" value={timeout} onChange={(e) => setTimeoutVal(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">작업 범위</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                      <Label className="dark:text-slate-300">시작 페이지</Label>
                      <Input type="number" value={startPage} onChange={(e) => setStartPage(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                    </div>
                    <div className="space-y-2">
                      <Label className="dark:text-slate-300">종료 페이지</Label>
                      <Input type="number" placeholder="전체" value={endPage} onChange={(e) => setEndPage(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Checkbox id="lastReportOnly" checked={lastReportOnly} onCheckedChange={(v) => setLastReportOnly(!!v)} className="dark:border-[#30363d]" />
                    <Label htmlFor="lastReportOnly" className="cursor-pointer dark:text-slate-300">최종보고서만</Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Checkbox id="resumeYearly" checked={resumeYearly} onCheckedChange={(v) => setResumeYearly(!!v)} className="dark:border-[#30363d]" />
                    <Label htmlFor="resumeYearly" className="cursor-pointer dark:text-slate-300">연간 작업 재개</Label>
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">실행 옵션</p>
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">워커 수</Label>
                    <Input type="number" value={workerCount} onChange={(e) => setWorkerCount(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">로그 줄 수</Label>
                    <Input type="number" value={logLimit} onChange={(e) => setLogLimit(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {downloadPanelOpen && (
            <Card className="absolute right-full top-0 mr-3 w-[min(420px,calc(100vw-2rem))] max-h-[calc(100vh-8rem)] overflow-auto shadow-xl dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                  <CardTitle className="dark:text-white">실행 현황</CardTitle>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setDownloadPanelOpen(false)}
                  className="h-8 w-8 dark:hover:bg-[#21262d]"
                  title="실행 현황 닫기"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <Label className="dark:text-slate-300">작업 상태</Label>
                  <Button
                    variant="outline"
                    onClick={handleCancelDownload}
                    disabled={!activeJobId}
                    className="h-8 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-300"
                  >
                    <Square className="mr-2 h-4 w-4" />
                    중단
                  </Button>
                </div>
                <JobStatusLogger
                  status={status}
                  isErrorStatus={isErrorStatus}
                />
              </div>

              {result && (
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">실행 결과 요약</Label>
                  <div className="grid grid-cols-2 gap-2 mt-2">
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:bg-[#0d1117] dark:border-[#30363d]">
                      <span className="text-xs font-bold text-slate-500 dark:text-slate-400">성공</span>
                      <strong className="mt-1 block text-xl font-bold text-slate-950 dark:text-slate-100">{result.summary?.success || result.success_count || 0}/{result.summary?.total || result.total_count || result.summary?.success || 0}</strong>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:bg-[#0d1117] dark:border-[#30363d]">
                      <span className="text-xs font-bold text-slate-500 dark:text-slate-400">실패</span>
                      <strong className="mt-1 block text-xl font-bold text-slate-950 dark:text-slate-100">{result.summary?.failed || result.failed_count || result.error_count || 0}</strong>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
          )}
        </div>
      </div>
    </WorkflowPageShell>
  );
}
