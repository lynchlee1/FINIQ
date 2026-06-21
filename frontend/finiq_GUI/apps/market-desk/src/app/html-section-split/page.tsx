"use client"

import { useCallback, useEffect, useState } from "react";
import { FileSearch, Loader2, Play } from "lucide-react";
import { Button } from "@finiq/ui";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { useJobPolling } from "@/hooks/useJobPolling";
import { useSettingsStore } from "@/store/useSettingsStore";
import {
  HtmlWorkflowCard,
  HtmlWorkflowForm,
  HtmlWorkflowPage,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import { formatInteger } from "@/lib/format";
import {
  HtmlSectionSplitActionDock,
  HtmlSectionSplitResults,
  type InspectResult,
} from "./_components/HtmlSectionSplitResults";

function statusLabel(status: string) {
  if (status === "queued") return "대기 중";
  if (status === "running") return "실행 중";
  if (status === "completed") return "완료";
  if (status === "failed") return "실패";
  return status || "-";
}

function parseOptionalNumber(value: string) {
  const trimmed = value.trim();
  return trimmed ? Number(trimmed) : null;
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
      lines.push(`결과 데이터 경로: ${res.output_directory || ""}`);
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

  const splitPathFields: HtmlWorkflowField[] = [
    {
      id: "inputDirectory",
      kind: "path",
      label: "입력 데이터 경로 (HTML)",
      mode: "folder",
      value: inputDirectory,
      onChange: handleInputDirectoryChange,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      placeholder: "/path/to/html-folder",
      span: 4,
    },
    {
      id: "outputDirectory",
      kind: "path",
      label: "결과 데이터 경로",
      mode: "folder",
      value: outputDirectory,
      onChange: setOutputDirectory,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      placeholder: "/path/to/output-folder",
      span: 4,
    },
  ];

  const splitOptionFields: HtmlWorkflowField[] = [
    {
      id: "limit",
      kind: "input",
      type: "number",
      label: "최대 처리 건수",
      help: "스캔과 저장에서 처리할 HTML 파일 수를 제한합니다.",
      placeholder: "전체",
      value: limit,
      onChange: setLimit,
      span: 2,
    },
    {
      id: "reportLimit",
      kind: "input",
      type: "number",
      label: "문제 파일 표시 수",
      help: "목차 없음과 읽기 실패 파일을 합쳐 표시할 최대 건수입니다.",
      value: reportLimit,
      onChange: setReportLimit,
      span: 2,
    },
  ];

  const inspectFolder = async () => {
    if (!inputDirectory) {
      setStatus("입력 데이터 경로를 선택하세요.");
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
      setStatus("입력 데이터 경로와 결과 데이터 경로를 모두 입력하세요.");
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
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          <HtmlWorkflowCard
            title="데이터 경로"
            description="입력 HTML 폴더와 목차별 저장 위치는 작업 대상이므로 메인 화면에서 관리합니다."
          >
            <HtmlWorkflowForm fields={splitPathFields} />
          </HtmlWorkflowCard>

          <HtmlWorkflowCard
            title="작업 실행"
            description="먼저 목차 스캔으로 문서별 목차를 확인한 뒤, 같은 입력 경로를 목차 단위로 저장합니다."
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <Button variant="outline" className="h-10 w-full" onClick={inspectFolder} disabled={isInspecting}>
                {isInspecting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileSearch className="mr-2 h-4 w-4" />}
                목차 스캔
              </Button>
              <Button className="h-10 w-full" onClick={startSave} disabled={isJobActive}>
                {isJobActive ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                목차 저장
              </Button>
            </div>
          </HtmlWorkflowCard>

          <HtmlSectionSplitResults
            summary={summary}
            documents={documents}
            problemFiles={problemFiles}
            status={status}
            isErrorStatus={isErrorStatus}
          />
        </section>

        <HtmlSectionSplitActionDock
          isJobActive={isJobActive}
          isInspecting={isInspecting}
          status={status}
          isErrorStatus={isErrorStatus}
          problemFileCount={problemFiles.length}
          settingsFields={splitOptionFields}
        />
      </div>
    </HtmlWorkflowPage>
  );
}
