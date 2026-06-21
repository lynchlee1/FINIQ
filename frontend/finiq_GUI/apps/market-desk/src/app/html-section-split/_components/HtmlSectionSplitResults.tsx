"use client"

import type { ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { ActionDock } from "@/components/ui/ActionDock";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import {
  HtmlWorkflowCard,
  HtmlWorkflowForm,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import { formatInteger } from "@/lib/format";

export type TocItem = {
  toc_id: string;
  index: number;
  title: string;
};

export type DocumentRow = {
  source_file: string;
  source_name: string;
  source_relative_path: string;
  section_count: number;
  sections: TocItem[];
};

export type ProblemFile = {
  kind: "read_failed" | "no_sections";
  source_file: string;
  error?: string;
};

export type InspectResult = {
  input_directory?: string;
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

type HtmlSectionSplitResultsProps = {
  inputDirectory: string;
  documents: DocumentRow[];
  problemFiles: ProblemFile[];
};

type HtmlSectionSplitActionDockProps = {
  isJobActive: boolean;
  isInspecting: boolean;
  status: string;
  isErrorStatus: boolean;
  problemFileCount: number;
  settingsFields: HtmlWorkflowField[];
  onCancel: () => void;
};

function compactPath(path: string) {
  if (!path) return "";
  const parts = path.split("/");
  return parts.length > 4 ? `.../${parts.slice(-4).join("/")}` : path;
}

function problemKindLabel(kind: ProblemFile["kind"]) {
  if (kind === "read_failed") return "읽기 실패";
  return "목차 없음";
}

function sourceHtmlUrl(inputDirectory: string, document: DocumentRow) {
  const params = new URLSearchParams({
    input_directory: inputDirectory,
    source_name: document.source_relative_path || document.source_name,
  });
  return `/api/disclosures/html/sections/source?${params.toString()}`;
}

export function HtmlSectionSplitResults({
  inputDirectory,
  documents,
  problemFiles,
}: HtmlSectionSplitResultsProps) {
  return (
    <>
      <HtmlWorkflowCard
        title="개별 공시"
        description={`${formatInteger(documents.length)}개 공시의 원문을 열고 목차 분리 상태를 확인합니다.`}
      >
        {documents.length ? (
          <div className="max-h-[560px] overflow-auto rounded-md border border-slate-200 dark:border-[#30363d]">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead className="sticky top-0 bg-slate-50 text-xs text-slate-500 dark:bg-[#0d1117] dark:text-slate-400">
                <tr>
                  <th className="px-3 py-2 font-semibold">공시 파일</th>
                  <th className="w-28 px-3 py-2 text-right font-semibold">목차 수</th>
                  <th className="w-28 px-3 py-2 font-semibold">확인</th>
                  <th className="px-3 py-2 font-semibold">목차</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-[#30363d]">
                {documents.map((item) => (
                  <tr key={item.source_file}>
                    <td className="px-3 py-3 align-top">
                      <p className="font-medium text-slate-900 dark:text-slate-100">{item.source_name}</p>
                      <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">{compactPath(item.source_relative_path || item.source_file)}</p>
                    </td>
                    <td className="px-3 py-3 text-right align-top tabular-nums text-slate-700 dark:text-slate-300">
                      {formatInteger(item.section_count)}
                    </td>
                    <td className="px-3 py-3 align-top">
                      <div className="flex flex-col gap-2">
                        <a
                          className="inline-flex items-center gap-1 text-xs font-semibold text-slate-700 underline-offset-2 hover:underline dark:text-slate-200"
                          href={sourceHtmlUrl(inputDirectory, item)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                          공시 열기
                        </a>
                        <span className="inline-flex w-fit rounded bg-green-50 px-1.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-950/40 dark:text-green-300">
                          분리 확인
                        </span>
                      </div>
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
            폴더를 열면 개별 공시와 목차 분리 상태가 표시됩니다.
          </div>
        )}
      </HtmlWorkflowCard>

      {problemFiles.length ? (
        <HtmlWorkflowCard title="문제 파일" description="목차가 없거나 읽기에 실패한 HTML 파일입니다.">
          <div className="max-h-80 overflow-auto rounded-md border border-slate-200 dark:border-[#30363d]">
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
        </HtmlWorkflowCard>
      ) : null}

    </>
  );
}

export function HtmlSectionSplitActionDock({
  isJobActive,
  isInspecting,
  status,
  isErrorStatus,
  problemFileCount,
  settingsFields,
  onCancel,
}: HtmlSectionSplitActionDockProps) {
  let notificationContent: ReactNode;
  if (isErrorStatus) {
    notificationContent = (
      <div className="whitespace-pre-wrap text-sm text-red-600 dark:text-red-300">
        {status || "오류 내용을 확인할 수 없습니다."}
      </div>
    );
  } else if (problemFileCount > 0) {
    notificationContent = (
      <div className="text-sm text-slate-600 dark:text-slate-300">
        문제 파일 {formatInteger(problemFileCount)}건이 표시되었습니다.
      </div>
    );
  } else {
    notificationContent = <div className="text-sm text-slate-500 dark:text-slate-400">알림 없음</div>;
  }

  return (
    <ActionDock
      activityActive={isJobActive || isInspecting}
      activityContent={
        <JobStatusLogger
          status={status}
          isErrorStatus={isErrorStatus}
          isCancellable={isInspecting}
          onCancel={onCancel}
        />
      }
      notificationActive={isErrorStatus || problemFileCount > 0}
      notificationContent={notificationContent}
      settingsTitle="설정"
      settingsContent={
        <div className="space-y-3">
          <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">표시 옵션</p>
          </div>
          <HtmlWorkflowForm fields={settingsFields} />
        </div>
      }
    />
  );
}
