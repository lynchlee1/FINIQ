"use client"

import { useState, useEffect, useCallback } from "react";
import { FolderOpen, FileJson, Play, Square, Loader2, Trash2 } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Label, Checkbox } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import {
  HtmlWorkflowForm,
  HtmlWorkflowCard,
  HtmlWorkflowPage,
  htmlControlClassName,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";

type DownloadVariant = "external" | "content";
type SplitByYearButtonProps = {
  checked: boolean;
  onChange: () => void;
};

const DOWNLOAD_VARIANTS = {
  external: {
    settingsTitle: "공시원문 외부 저장 설정",
    description: "다운로드된 공시 결과 JSON을 바탕으로 KIND 공시 뷰어 HTML을 대량 저장합니다.",
    sourceLabel: "필터 결과 JSON 파일",
    sourceHelp: "공시 필터링 결과 파일(JSON)을 선택하세요.",
    sourcePickMode: "file",
    sourceSettingKey: "html_download_source_path",
    sourceRequiredMessage: "필터 결과 파일을 선택하세요.",
    sourcePayloadKey: "source_json_path",
    defaultDirectoryKey: "html_output_directory",
    defaultDirectorySuffix: "viewer_html",
    startEndpoint: "/api/disclosures/html/download/start",
    cancelEndpoint: "/api/disclosures/html/download/cancel",
    inspectEndpoint: "/api/disclosures/html/download/inspect-folder",
    stopMessage: "공시원문 외부 저장 중지를 요청했습니다. 진행 중인 요청이 끝나면 멈춥니다.",
  },
  content: {
    settingsTitle: "공시원문 내부 저장 설정",
    description: "공시원문 외부 저장 폴더를 바탕으로 KIND 공시 본문 HTML을 대량 저장합니다.",
    sourceLabel: "공시원문 외부 저장 경로",
    sourceHelp: "공시원문 외부 저장으로 만든 뷰어 HTML 폴더를 선택하세요.",
    sourcePickMode: "folder",
    sourceSettingKey: "html_output_directory",
    sourceRequiredMessage: "공시원문 외부 저장 경로를 선택하세요.",
    sourcePayloadKey: "source_directory",
    defaultDirectoryKey: "html_content_output_directory",
    defaultDirectorySuffix: "viewer_html_contents",
    startEndpoint: "/api/disclosures/html/content-download/start",
    cancelEndpoint: "/api/disclosures/html/content-download/cancel",
    inspectEndpoint: "/api/disclosures/html/content-download/inspect-folder",
    stopMessage: "공시원문 내부 저장 중지를 요청했습니다. 진행 중인 요청이 끝나면 멈춥니다.",
  },
} as const;

function SplitByYearButton({ checked, onChange }: SplitByYearButtonProps) {
  return (
    <Button
      variant={checked ? "default" : "outline"}
      onClick={onChange}
      className="h-10 w-[116px] shrink-0"
    >
      분할저장 {checked ? "On" : "Off"}
    </Button>
  );
}

export function HtmlDownloadPageView({ variant = "external" }: { variant?: DownloadVariant }) {
  const variantConfig = DOWNLOAD_VARIANTS[variant];
  
  const {
    fetchSettings,
    saveSetting,
  } = useSettingsStore();

  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState<any>(null);

  const formatStatus = useCallback((data: any) => {
    const statusLbl = (s: string) => {
      if (s === "queued") return "대기 중";
      if (s === "running") return "실행 중";
      if (s === "completed") return "완료";
      if (s === "failed") return "실패";
      return s || "-";
    };

    const res = data.result || {};
    const lines = [`작업 상태: ${statusLbl(data.status)}`];
    if (data.error) lines.push(`오류: ${data.error}`);
    if (res.requested_count !== undefined) {
      lines.push(`요청 접수번호: ${res.requested_count || 0}`);
      lines.push(`분할저장: ${res.split_by_year ? "On" : "Off"}`);
      lines.push(`저장 파일: ${res.saved_count || 0}`);
      lines.push(`저장 경로: ${res.output_directory || ""}`);
    }
    if (res.summary?.merged_files !== undefined) {
      lines.push(`병합 HTML: ${res.summary.merged_files || 0}`);
      lines.push(`저장 JSON: ${res.summary.written_files || 0}`);
      lines.push(`분할저장: ${res.split_by_year ? "On" : "Off"}`);
      if (Array.isArray(res.written_files)) {
        lines.push("결과 파일", ...res.written_files);
      }
    }
    if (res.summary?.compressed_files !== undefined) {
      lines.push(`압축 HTML: ${res.summary.compressed_files || 0}`);
      lines.push(`저장 JSON: ${res.summary.written_files || 0}`);
      lines.push(`분할저장: ${res.split_by_year ? "On" : "Off"}`);
      if (res.verification) {
        lines.push(`재검사: ${res.verification.passed ? "통과" : "누락/불일치 있음"}`);
        lines.push(`재검사 기록: ${res.verification.verified_records || 0}/${res.verification.expected_records || 0}`);
        lines.push(`누락 기록: ${res.verification.missing_records || 0}`);
      }
      if (Array.isArray(res.written_files)) {
        lines.push("결과 파일", ...res.written_files);
      }
    }
    if (Array.isArray(data.progress_log) && data.progress_log.length) {
      lines.push("", "최근 로그", ...data.progress_log);
    }
    return lines;
  }, []);

  const {
    status,
    isErrorStatus,
    activeJobId,
    startPolling,
    setStatus,
    setIsErrorStatus,
  } = useJobPolling({
    pollingEndpoint: "/api/disclosures/html/jobs/{jobId}",
    formatStatus,
    onSuccess: setResult,
  });

  const isJobActive = !!activeJobId;

  const [activeCancelToken, setActiveCancelToken] = useState<string | null>(null);
  const [inspectRunning, setInspectRunning] = useState(false);
  const [deleteConfirmed, setDeleteConfirmed] = useState(false);
  const [deleteConfirmationText, setDeleteConfirmationText] = useState("");
  const [lastInspectionCandidateCount, setLastInspectionCandidateCount] = useState(0);

  // Form State
  const [outputDirectory, setOutputDirectory] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const [timeout, setTimeoutVal] = useState("20");
  const [maxRequestsPerMinute, setMaxRequestsPerMinute] = useState("90");
  const [waitSeconds, setWaitSeconds] = useState("0");
  const [limit, setLimit] = useState("");
  const [skipExisting, setSkipExisting] = useState(true);
  const [downloadSplitByYear, setDownloadSplitByYear] = useState(false);
  const [contentSourceSplitByYear, setContentSourceSplitByYear] = useState(false);
  const [compressSplitByYear, setCompressSplitByYear] = useState(false);
  const [mergeSplitByYear, setMergeSplitByYear] = useState(false);
  const [progressInterval, setProgressInterval] = useState("10");
  const [mergeOutputPath, setMergeOutputPath] = useState("");

  const startJob = useCallback(async (endpoint: string, payload: any) => {
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("Job start failed");
      const data = await response.json();
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
      if (payload.cancel_token) {
         setActiveCancelToken(null);
      }
    }
  }, [setStatus, setIsErrorStatus, startPolling, setActiveCancelToken]);

  useEffect(() => {
    fetchSettings().then((config) => {
      const nextOutputDirectory = config[variantConfig.defaultDirectoryKey] || (config.output_root ? `${config.output_root}/${variantConfig.defaultDirectorySuffix}` : "");
      setOutputDirectory(nextOutputDirectory);
      
      const transferredPayload = variant === "external" ? sessionStorage.getItem("finiq.kind.filteredDisclosures") : null;
      if (transferredPayload) {
        const transferReference = JSON.parse(transferredPayload);
        setSourcePath(transferReference.source_json_path || "");
        sessionStorage.removeItem("finiq.kind.filteredDisclosures");
        setStatus("공시 필터에서 생성한 결과 파일을 불러왔습니다.");
      } else if (variant === "content") {
        setSourcePath(config.html_output_directory || (config.output_root ? `${config.output_root}/viewer_html` : ""));
        setMergeOutputPath(config.html_merge_output_path || (nextOutputDirectory ? `${nextOutputDirectory}/merged-content-html.json` : ""));
      } else if (config.html_download_source_path) {
        setSourcePath(config.html_download_source_path);
      }
    }).catch(err => {
      setStatus(err.message);
      setIsErrorStatus(true);
    }).finally(() => {
      setLoading(false);
    });
  }, [fetchSettings, variant, variantConfig.defaultDirectoryKey, variantConfig.defaultDirectorySuffix, setStatus, setIsErrorStatus]);

  const handleRun = async () => {
    if (!sourcePath) {
      setStatus(variantConfig.sourceRequiredMessage);
      setIsErrorStatus(true);
      return;
    }
    const cancelToken = window.crypto.randomUUID();
    setActiveCancelToken(cancelToken);
    
    const payload = {
      output_directory: outputDirectory,
      [variantConfig.sourcePayloadKey]: sourcePath,
      timeout: Number(timeout),
      max_requests_per_minute: Number(maxRequestsPerMinute),
      wait_seconds: Number(waitSeconds),
      limit: limit ? Number(limit) : null,
      skip_existing: skipExisting,
      split_by_year: downloadSplitByYear,
      source_split_by_year: variant === "content" ? contentSourceSplitByYear : downloadSplitByYear,
      output_split_by_year: downloadSplitByYear,
      progress_interval: Number(progressInterval),
      cancel_token: cancelToken,
    };

    startJob(variantConfig.startEndpoint, payload);
  };

  const buildCleanupPayload = (dryRun: boolean) => ({
    output_directory: outputDirectory,
    [variantConfig.sourcePayloadKey]: sourcePath,
    limit: limit ? Number(limit) : null,
    split_by_year: downloadSplitByYear,
    source_split_by_year: variant === "content" ? contentSourceSplitByYear : downloadSplitByYear,
    output_split_by_year: downloadSplitByYear,
    dry_run: dryRun,
    delete_confirmed: deleteConfirmed,
    delete_confirmation_text: deleteConfirmationText,
  });

  const handleInspectFolder = async () => {
    if (!sourcePath) {
      setStatus(variantConfig.sourceRequiredMessage);
      setIsErrorStatus(true);
      return;
    }
    if (!outputDirectory) {
      setStatus("저장 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      setInspectRunning(true);
      setIsErrorStatus(false);
      setStatus("폴더를 검사하는 중입니다...");
      const payload = buildCleanupPayload(true);
      const response = await fetch(variantConfig.inspectEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Folder inspection failed");

      const deleteCandidates = Array.isArray(data.deletion_candidates) ? data.deletion_candidates : [];
      setLastInspectionCandidateCount(data.deletion_candidate_count || 0);
      const lines = [
        "폴더 검사 완료",
        `대상 접수번호: ${data.requested_count || 0}`,
        `분할저장: ${data.split_by_year ? "On" : "Off"}`,
        `삭제 예정 파일: ${data.deletion_candidate_count || 0}`,
        `저장 경로: ${data.output_directory || ""}`,
      ];
      if (deleteCandidates.length) {
        lines.push("", "삭제 예정 파일", ...deleteCandidates.map((file: any) => `- ${file.name} (${file.reason})`));
      }
      setResult(data);
      setStatus(lines.join("\n"));
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setInspectRunning(false);
    }
  };

  const handleDeleteUnexpectedFiles = async () => {
    if (!deleteConfirmed || deleteConfirmationText.trim() !== "확인했습니다.") {
      setStatus('삭제하려면 삭제 허가를 체크하고 "확인했습니다."를 입력하세요.');
      setIsErrorStatus(true);
      return;
    }
    try {
      setInspectRunning(true);
      setIsErrorStatus(false);
      setStatus("허가된 파일 삭제를 실행하는 중입니다...");
      const response = await fetch(variantConfig.inspectEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildCleanupPayload(false)),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Folder cleanup failed");

      const deletedFiles = Array.isArray(data.deleted_files) ? data.deleted_files : [];
      setLastInspectionCandidateCount(0);
      setDeleteConfirmed(false);
      setDeleteConfirmationText("");
      const lines = [
        "파일 삭제 완료",
        `대상 접수번호: ${data.requested_count || 0}`,
        `분할저장: ${data.split_by_year ? "On" : "Off"}`,
        `삭제 파일: ${data.deleted_count || 0}`,
        `저장 경로: ${data.output_directory || ""}`,
      ];
      if (deletedFiles.length) {
        lines.push("", "삭제한 파일", ...deletedFiles.map((file: any) => `- ${file.name} (${file.reason})`));
      }
      setResult(data);
      setStatus(lines.join("\n"));
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setInspectRunning(false);
    }
  };

  const handleCancel = async () => {
    if (!activeCancelToken) return;
    setStatus(variantConfig.stopMessage);
    try {
      await fetch(variantConfig.cancelEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cancel_token: activeCancelToken }),
      });
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleMergeContentHtml = async () => {
    if (variant !== "content") return;
    if (!outputDirectory) {
      setStatus("내부 HTML 저장 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const defaultOutputPath = mergeSplitByYear ? outputDirectory : `${outputDirectory}/merged-content-html.json`;
    const payload = {
      input_directory: outputDirectory,
      output_path: mergeOutputPath || defaultOutputPath,
      split_by_year: mergeSplitByYear,
      input_split_by_year: mergeSplitByYear,
      output_split_by_year: mergeSplitByYear,
      limit: limit ? Number(limit) : null,
    };
    startJob("/api/disclosures/html/content-download/merge/start", payload);
  };

  const handleCompressExternalHtml = async () => {
    if (variant !== "external") return;
    if (!outputDirectory) {
      setStatus("공시원문 외부 저장 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const payload = {
      input_directory: outputDirectory,
      output_directory: outputDirectory,
      split_by_year: compressSplitByYear,
      input_split_by_year: compressSplitByYear,
      output_split_by_year: compressSplitByYear,
      limit: limit ? Number(limit) : null,
    };
    startJob("/api/disclosures/html/download/compress/start", payload);
  };

  const saveOutputDirectory = (val: string) => {
    setOutputDirectory(val);
    saveSetting(variantConfig.defaultDirectoryKey, val);
    if (variant === "content") {
      setMergeOutputPath(mergeSplitByYear ? val : (val ? `${val}/merged-content-html.json` : ""));
    }
  };

  const saveSourcePath = (val: string) => {
    setSourcePath(val);
    saveSetting(variantConfig.sourceSettingKey, val);
  };

  const baseFields: HtmlWorkflowField[] = [
    {
      id: "sourcePath",
      kind: "path",
      label: variantConfig.sourceLabel,
      help: variantConfig.sourceHelp,
      mode: variantConfig.sourcePickMode,
      value: sourcePath,
      onChange: saveSourcePath,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 4,
      trailing: variantConfig.sourcePickMode === "folder" ? (
        <SplitByYearButton
          checked={contentSourceSplitByYear}
          onChange={() => setContentSourceSplitByYear((value) => !value)}
        />
      ) : null,
    },
    {
      id: "outputDirectory",
      kind: "path",
      label: "저장 경로",
      mode: "folder",
      value: outputDirectory,
      onChange: saveOutputDirectory,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 4,
      trailing: (
        <SplitByYearButton
          checked={downloadSplitByYear}
          onChange={() => setDownloadSplitByYear((value) => !value)}
        />
      ),
    },
    { id: "timeout", kind: "input", type: "number", label: "타임아웃 (초)", value: timeout, onChange: setTimeoutVal },
    { id: "maxRequestsPerMinute", kind: "input", type: "number", label: "최대 요청/분", value: maxRequestsPerMinute, onChange: setMaxRequestsPerMinute },
    { id: "waitSeconds", kind: "input", type: "number", label: "요청 간격 (초)", value: waitSeconds, onChange: setWaitSeconds },
    { id: "limit", kind: "input", type: "number", label: "최대 처리 건수", placeholder: "전체", value: limit, onChange: setLimit },
    { id: "progressInterval", kind: "input", type: "number", label: "진행 확인 간격 (건)", value: progressInterval, onChange: setProgressInterval, span: 2 },
    { id: "skipExisting", kind: "checkbox", checked: skipExisting, onChange: setSkipExisting, checkboxLabel: "기존 파일 건너뛰기", span: 2 },
  ];

  const compressionFields: HtmlWorkflowField[] = [
    {
      id: "compressOutputDirectory",
      kind: "path",
      label: "공시원문 외부 저장 경로",
      mode: "folder",
      value: outputDirectory,
      onChange: saveOutputDirectory,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 4,
      trailing: (
        <SplitByYearButton
          checked={compressSplitByYear}
          onChange={() => setCompressSplitByYear((value) => !value)}
        />
      ),
    },
  ];

  const mergeFields: HtmlWorkflowField[] = [
    {
      id: "mergeOutputPath",
      kind: "path",
      label: "병합 파일 저장 경로",
      mode: mergeSplitByYear ? "folder" : "save",
      value: mergeOutputPath || (mergeSplitByYear ? outputDirectory : (outputDirectory ? `${outputDirectory}/merged-content-html.json` : "")),
      onChange: (val) => {
        setMergeOutputPath(val);
        saveSetting("html_merge_output_path", val);
      },
      placeholder: mergeSplitByYear ? `${outputDirectory || "/path/to/content_html"}` : `${outputDirectory || "/path/to/content_html"}/merged-content-html.json`,
      span: 4,
      trailing: (
        <SplitByYearButton
          checked={mergeSplitByYear}
          onChange={() => setMergeSplitByYear((value) => {
            const nextVal = !value;
            const newPath = nextVal ? outputDirectory : (outputDirectory ? `${outputDirectory}/merged-content-html.json` : "");
            setMergeOutputPath(newPath);
            return nextVal;
          })}
        />
      ),
    },
  ];

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  return (
    <HtmlWorkflowPage
      eyebrow={variant === "external" ? "External HTML Save" : "Content HTML Save"}
      title={variantConfig.settingsTitle}
      description={variantConfig.description}
    >
      <div className="grid lg:grid-cols-[minmax(0,2fr)_minmax(260px,0.85fr)] gap-6">
        <section className="min-w-0 space-y-6">
          <HtmlWorkflowCard
            title="저장 조건"
            description="경로, 속도 제한, 이어받기 기준을 같은 입력 규칙으로 관리합니다."
          >
              <HtmlWorkflowForm fields={baseFields} />
          </HtmlWorkflowCard>

          {variant === "external" && (
            <HtmlWorkflowCard
              title="외부 HTML JSON 압축"
              description="저장된 KIND 공시 뷰어 HTML에서 핵심 정보만 추출해 하나의 JSON으로 저장합니다."
            >
                <HtmlWorkflowForm fields={compressionFields} />
                <Button variant="outline" className="h-10 w-full" onClick={handleCompressExternalHtml} disabled={isJobActive}>
                  <FileJson className="mr-2 h-4 w-4" />
                  외부 HTML JSON 압축
                </Button>
            </HtmlWorkflowCard>
          )}

          {variant === "content" && (
            <HtmlWorkflowCard
              title="내부 HTML JSON 병합"
              description="저장된 KIND 공시 본문 HTML들을 하나의 JSON으로 병합합니다."
            >
                <HtmlWorkflowForm fields={mergeFields} />
                <Button variant="outline" className="h-10 w-full" onClick={handleMergeContentHtml} disabled={isJobActive}>
                  <FileJson className="mr-2 h-4 w-4" />
                  내부 HTML JSON 병합
                </Button>
            </HtmlWorkflowCard>
          )}
        </section>

        <section className="space-y-6">
          <Card className="sticky top-6 dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col gap-2">
                <Button variant="outline" className="h-10 w-full" onClick={handleInspectFolder} disabled={isJobActive || inspectRunning}>
                  {inspectRunning ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FolderOpen className="mr-2 h-4 w-4" />}
                  폴더 검사하기
                </Button>
                <div className="space-y-2 rounded-md border border-slate-200 p-3 dark:border-[#30363d]">
                  <div className="flex items-center space-x-2">
                    <Checkbox id="deleteConfirmed" checked={deleteConfirmed} onCheckedChange={(v) => setDeleteConfirmed(!!v)} className="dark:border-[#30363d]" />
                    <Label htmlFor="deleteConfirmed" className="cursor-pointer text-xs dark:text-slate-300">삭제 허가</Label>
                  </div>
                  <Input
                    value={deleteConfirmationText}
                    onChange={(e) => setDeleteConfirmationText(e.target.value)}
                    placeholder="확인했습니다."
                    className={htmlControlClassName}
                  />
                  <Button
                    variant="outline"
                    className="h-10 w-full"
                    onClick={handleDeleteUnexpectedFiles}
                    disabled={
                      isJobActive ||
                      inspectRunning ||
                      lastInspectionCandidateCount === 0 ||
                      !deleteConfirmed ||
                      deleteConfirmationText.trim() !== "확인했습니다."
                    }
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    삭제 예정 파일 {lastInspectionCandidateCount}개 삭제
                  </Button>
                </div>
                <Button className="h-10 w-full" onClick={handleRun} disabled={isJobActive}>
                  <Play className="mr-2 h-4 w-4" />
                  실행
                </Button>
                <Button variant="outline" className="h-10 w-full" onClick={handleCancel} disabled={!activeCancelToken}>
                  <Square className="mr-2 h-4 w-4" />
                  중지
                </Button>
              </div>

              <div className="space-y-2">
                <Label className="dark:text-slate-300">작업 상태</Label>
                <JobStatusLogger status={status} isErrorStatus={isErrorStatus} />
              </div>

              <div className="space-y-2">
                <Label className="dark:text-slate-300">실행 결과</Label>
                {result ? (
                  (() => {
                    const reqCount = result.requested_count;
                    const savedCount = result.saved_count;
                    
                    if (reqCount !== undefined && savedCount !== undefined) {
                      const failedCount = reqCount - savedCount;
                      const isAllSuccess = failedCount === 0;
                      
                      return (
                        <div className={cn(
                          "p-4 rounded-lg border text-sm font-semibold",
                          isAllSuccess
                            ? "bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-900/30 text-green-700 dark:text-green-400"
                            : "bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-900/30 text-red-700 dark:text-red-400"
                        )}>
                          {isAllSuccess
                            ? `전체 ${savedCount}/${reqCount} 저장 완료`
                            : `전체 ${reqCount}건 중 ${savedCount}건/${failedCount}건 저장 완료`}
                        </div>
                      );
                    }

                    if (result.format === "kind_disclosure_html_folder_cleanup_v1") {
                      const existingCount = result.existing_target_html_count || 0;
                      const missingCount = result.missing_target_html_count || 0;
                      const candidateCount = result.deletion_candidate_count || 0;
                      const isAllSaved = reqCount !== undefined && missingCount === 0;
                      const hasDeleteCandidates = candidateCount > 0;

                      return (
                        <div className={cn(
                          "p-4 rounded-lg border text-sm font-semibold",
                          isAllSaved && !hasDeleteCandidates
                            ? "bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-900/30 text-green-700 dark:text-green-400"
                            : "bg-amber-50 dark:bg-amber-900/10 border-amber-200 dark:border-amber-900/30 text-amber-700 dark:text-amber-400"
                        )}>
                          {isAllSaved
                            ? `폴더 검사 완료: 전체 ${existingCount}/${reqCount} 저장 확인`
                            : `폴더 검사 완료: 전체 ${reqCount || 0}건 중 ${existingCount}건 저장, 누락 ${missingCount}건`}
                          {hasDeleteCandidates ? `, 삭제 예정 ${candidateCount}건` : ""}
                        </div>
                      );
                    }

                    // 다른 형태의 결과 (예: merge)
                    const summary = result.summary;
                    if (summary && summary.merged_files !== undefined) {
                      const isAllSuccess = summary.merged_files === summary.written_files;

                      return (
                        <div className={cn(
                          "p-4 rounded-lg border text-sm font-semibold",
                          isAllSuccess
                            ? "bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-900/30 text-green-700 dark:text-green-400"
                            : "bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-900/30 text-red-700 dark:text-red-400"
                        )}>
                          병합 HTML {summary.merged_files}건 중 {summary.written_files}건 저장 완료
                        </div>
                      );
                    }

                    if (summary && summary.compressed_files !== undefined) {
                      const verification = result.verification;
                      const isAllSuccess = verification
                        ? verification.passed === true
                        : summary.written_files > 0;
                      const missingRecords = verification?.missing_records || 0;

                      return (
                        <div className={cn(
                          "p-4 rounded-lg border text-sm font-semibold",
                          isAllSuccess
                            ? "bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-900/30 text-green-700 dark:text-green-400"
                            : "bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-900/30 text-red-700 dark:text-red-400"
                        )}>
                          {isAllSuccess
                            ? `외부 HTML ${summary.compressed_files}건 압축 완료`
                            : `외부 HTML ${summary.compressed_files}건 압축 완료, 누락 ${missingRecords}건`}
                        </div>
                      );
                    }

                    // 기본 폴백
                    return (
                      <div className="p-4 rounded-lg border text-sm font-semibold bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-900/30 text-red-700 dark:text-red-400">
                        저장 결과를 확인할 수 없습니다.
                      </div>
                    );
                  })()
                ) : (
                  <div className="p-3 rounded-lg border border-slate-200 dark:border-[#30363d] bg-slate-50 dark:bg-[#161b22] text-slate-400 dark:text-slate-500 text-sm italic">
                    결과 없음
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </section>
      </div>
    </HtmlWorkflowPage>
  );
}
