"use client"

import { useCallback, useEffect, useState } from "react";
import { FileSearch, Loader2, Play } from "lucide-react";
import { Button, Input, Label } from "@finiq/ui";
import { ActionDock } from "@/components/ui/ActionDock";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { useJobPolling } from "@/hooks/useJobPolling";
import { useSettingsStore } from "@/store/useSettingsStore";
import {
  HtmlField,
  HtmlWorkflowPage,
  htmlControlClassName,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import { formatInteger } from "@/lib/format";

type TocItem = {
  toc_id: string;
  index: number;
  title: string;
};

type DocumentRow = {
  source_file: string;
  source_name: string;
  section_count: number;
  sections: TocItem[];
};

type ProblemFile = {
  kind: "read_failed" | "no_sections";
  source_file: string;
  error?: string;
};

type InspectResult = {
  summary?: {
    found_files?: number;
    documents_with_sections?: number;
    files_without_sections?: number;
    failed_files?: number;
    reported_problem_files?: number;
  };
  documents?: DocumentRow[];
  problem_files?: ProblemFile[];
};

function statusLabel(status: string) {
  if (status === "queued") return "대기 중";
  if (status === "running") return "실행 중";
  if (status === "completed") return "완료";
  if (status === "failed") return "실패";
  return status || "-";
}

function compactPath(path: string) {
  if (!path) return "";
  const parts = path.split("/");
  return parts.length > 4 ? `.../${parts.slice(-4).join("/")}` : path;
}

function parseOptionalNumber(value: string) {
  const trimmed = value.trim();
  return trimmed ? Number(trimmed) : null;
}

function problemKindLabel(kind: ProblemFile["kind"]) {
  if (kind === "read_failed") return "읽기 실패";
  return "목차 없음";
}

export default function HtmlSectionSplitPage() {
  const { fetchSettings } = useSettingsStore();
  const [loading, setLoading] = useState(true);
  const [inputDirectory, setInputDirectory] = useState("");
  const [outputDirectory, setOutputDirectory] = useState("");
  const [limit, setLimit] = useState("");
  const [reportLimit, setReportLimit] = useState("50");
  const [inspectResult, setInspectResult] = useState<InspectResult | null>(null);
  const [isInspecting, setIsInspecting] = useState(false);

  const formatStatus = useCallback((data: any) => {
    const res = data.result || {};
    const summary = res.summary || {};
    const lines = [`작업 상태: ${statusLabel(data.status)}`];
    if (data.error) lines.push(`오류: ${data.error}`);
    if (summary.found_files !== undefined) {
      lines.push(`대상 HTML: ${formatInteger(summary.found_files)}`);
      lines.push(`저장 완료: ${formatInteger(summary.saved_files)}`);
      lines.push(`건너뜀: ${formatInteger(summary.skipped_files)}`);
      lines.push(`결과 경로: ${res.output_directory || ""}`);
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
  });

  const documents = inspectResult?.documents || [];
  const problemFiles = inspectResult?.problem_files || [];
  const summary = inspectResult?.summary;
  const isJobActive = !!activeJobId;

  useEffect(() => {
    fetchSettings().then((config) => {
      const defaultInput = config.html_content_output_directory || (config.output_root ? `${config.output_root}/viewer_html_contents` : "");
      setInputDirectory(defaultInput || "");
      setOutputDirectory(defaultInput ? `${defaultInput}_sections` : "");
    }).catch((err) => {
      setStatus(err.message);
      setIsErrorStatus(true);
    }).finally(() => {
      setLoading(false);
    });
  }, [fetchSettings, setIsErrorStatus, setStatus]);

  const handleInputDirectoryChange = (value: string) => {
    setInputDirectory(value);
    setOutputDirectory(value ? `${value}_sections` : "");
    setInspectResult(null);
  };

  const inspectFolder = async () => {
    if (!inputDirectory) {
      setStatus("입력 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    setIsInspecting(true);
    try {
      const response = await fetch("/api/disclosures/html/sections/inspect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          input_directory: inputDirectory,
          limit: parseOptionalNumber(limit),
          report_limit: Number(reportLimit || 50),
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "목차 스캔에 실패했습니다.");
      }
      const data = await response.json();
      setInspectResult(data);
      setStatus(`목차 스캔 완료: ${formatInteger(data.summary?.documents_with_sections || 0)}개 문서`);
      setIsErrorStatus(false);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setIsInspecting(false);
    }
  };

  const startSave = async () => {
    if (!inputDirectory || !outputDirectory) {
      setStatus("입력 경로와 결과 경로를 모두 입력하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      const response = await fetch("/api/disclosures/html/sections/save/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          input_directory: inputDirectory,
          output_directory: outputDirectory,
          limit: parseOptionalNumber(limit),
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "목차 저장 작업을 시작하지 못했습니다.");
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
    <HtmlWorkflowPage
      eyebrow="Disclosure Section Desk"
      title="공시원문 목차 분리"
      description="KIND 내부 HTML을 목차 단위로 분리하고, 문서별 목차 구성과 처리 상태를 확인합니다."
    >
      <div className="relative space-y-6">
        <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-[#30363d] dark:bg-[#161b22]">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <HtmlField label="입력 경로">
              <PathPickerInput
                mode="folder"
                value={inputDirectory}
                onChange={handleInputDirectoryChange}
                placeholder="/path/to/html-folder"
                onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
              />
            </HtmlField>
            <HtmlField label="결과 경로">
              <PathPickerInput
                mode="folder"
                value={outputDirectory}
                onChange={setOutputDirectory}
                placeholder="/path/to/output-folder"
                onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
              />
            </HtmlField>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Button variant="outline" className="h-10" onClick={inspectFolder} disabled={isInspecting}>
              {isInspecting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileSearch className="mr-2 h-4 w-4" />}
              목차 스캔
            </Button>
            <Button className="h-10" onClick={startSave} disabled={isJobActive}>
              {isJobActive ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              목차 저장
            </Button>
          </div>
        </section>

        {summary ? (
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {[
              ["문서", summary.found_files],
              ["목차 있음", summary.documents_with_sections],
              ["목차 없음", summary.files_without_sections],
              ["읽기 실패", summary.failed_files],
              ["문제 표시", summary.reported_problem_files],
            ].map(([label, value]) => (
              <div key={label} className="rounded-md border border-slate-200 bg-white p-4 dark:border-[#30363d] dark:bg-[#161b22]">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-500">{label}</p>
                <p className="mt-1 text-xl font-semibold tabular-nums text-slate-950 dark:text-white">{formatInteger(Number(value || 0))}</p>
              </div>
            ))}
          </section>
        ) : null}

        <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-[#30363d] dark:bg-[#161b22]">
          <div className="mb-3 flex items-center justify-between gap-3 border-b border-slate-200 pb-2 dark:border-[#30363d]">
            <h2 className="text-sm font-semibold text-slate-950 dark:text-white">문서별 목차</h2>
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{formatInteger(documents.length)}개</span>
          </div>
          {documents.length ? (
            <div className="max-h-[560px] overflow-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="sticky top-0 bg-slate-50 text-xs text-slate-500 dark:bg-[#0d1117] dark:text-slate-400">
                  <tr>
                    <th className="px-3 py-2 font-semibold">파일</th>
                    <th className="w-28 px-3 py-2 text-right font-semibold">목차 수</th>
                    <th className="px-3 py-2 font-semibold">목차</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-[#30363d]">
                  {documents.map((item) => (
                    <tr key={item.source_file}>
                      <td className="px-3 py-3 align-top">
                        <p className="font-medium text-slate-900 dark:text-slate-100">{item.source_name}</p>
                        <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">{compactPath(item.source_file)}</p>
                      </td>
                      <td className="px-3 py-3 text-right align-top tabular-nums text-slate-700 dark:text-slate-300">
                        {formatInteger(item.section_count)}
                      </td>
                      <td className="px-3 py-3 align-top">
                        <div className="flex flex-wrap gap-1.5">
                          {item.sections.map((section) => (
                            <span key={`${item.source_file}-${section.toc_id}`} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700 dark:bg-[#21262d] dark:text-slate-300">
                              <span className="font-mono">{section.toc_id}</span>
                              {section.title ? <span className="ml-1">{section.title}</span> : null}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
              목차 스캔을 실행하세요.
            </div>
          )}
        </section>

        {problemFiles.length ? (
          <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-[#30363d] dark:bg-[#161b22]">
            <div className="mb-3 border-b border-slate-200 pb-2 dark:border-[#30363d]">
              <h2 className="text-sm font-semibold text-slate-950 dark:text-white">문제 파일</h2>
            </div>
            <div className="max-h-80 overflow-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="sticky top-0 bg-slate-50 text-xs text-slate-500 dark:bg-[#0d1117] dark:text-slate-400">
                  <tr>
                    <th className="w-28 px-3 py-2 font-semibold">구분</th>
                    <th className="px-3 py-2 font-semibold">파일</th>
                    <th className="px-3 py-2 font-semibold">오류</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-[#30363d]">
                  {problemFiles.map((item) => (
                    <tr key={`${item.kind}-${item.source_file}`}>
                      <td className="px-3 py-3 align-top text-slate-700 dark:text-slate-300">{problemKindLabel(item.kind)}</td>
                      <td className="px-3 py-3 align-top text-slate-700 dark:text-slate-300">{compactPath(item.source_file)}</td>
                      <td className="px-3 py-3 align-top text-slate-500 dark:text-slate-500">{item.error || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-[#30363d] dark:bg-[#161b22]">
          <div className="mb-3 border-b border-slate-200 pb-2 dark:border-[#30363d]">
            <h2 className="text-sm font-semibold text-slate-950 dark:text-white">작업 상태</h2>
          </div>
          <JobStatusLogger status={status} isErrorStatus={isErrorStatus} />
        </section>

        <ActionDock
          activityActive={isJobActive || isInspecting}
          activityContent={<JobStatusLogger status={status} isErrorStatus={isErrorStatus} />}
          notificationActive={isErrorStatus || problemFiles.length > 0}
          notificationContent={
            isErrorStatus ? (
              <div className="whitespace-pre-wrap text-sm text-red-600 dark:text-red-300">{status || "오류 내용을 확인할 수 없습니다."}</div>
            ) : problemFiles.length ? (
              <div className="text-sm text-slate-600 dark:text-slate-300">
                문제 파일 {formatInteger(problemFiles.length)}건이 표시되었습니다.
              </div>
            ) : (
              <div className="text-sm text-slate-500 dark:text-slate-400">알림 없음</div>
            )
          }
          settingsTitle="시스템 설정"
          settingsContent={
            <div className="space-y-4">
              <div className="space-y-2">
                <Label className="text-xs font-semibold text-slate-600 dark:text-slate-300">최대 처리 건수</Label>
                <Input
                  type="number"
                  min="1"
                  value={limit}
                  onChange={(event) => setLimit(event.target.value)}
                  placeholder="전체"
                  className={htmlControlClassName}
                />
                <p className="text-xs leading-5 text-slate-500 dark:text-slate-500">스캔과 저장에서 처리할 HTML 파일 수를 제한합니다.</p>
              </div>
              <div className="space-y-2">
                <Label className="text-xs font-semibold text-slate-600 dark:text-slate-300">문제 파일 표시 수</Label>
                <Input
                  type="number"
                  min="0"
                  value={reportLimit}
                  onChange={(event) => setReportLimit(event.target.value)}
                  className={htmlControlClassName}
                />
                <p className="text-xs leading-5 text-slate-500 dark:text-slate-500">목차 없음과 읽기 실패 파일을 합쳐 표시할 최대 건수입니다.</p>
              </div>
            </div>
          }
        />
      </div>
    </HtmlWorkflowPage>
  );
}
