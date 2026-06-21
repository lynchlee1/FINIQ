"use client"

import type { ReactNode } from "react";
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
  section_count: number;
  sections: TocItem[];
};

export type ProblemFile = {
  kind: "read_failed" | "no_sections";
  source_file: string;
  error?: string;
};

export type InspectResult = {
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
  summary: InspectResult["summary"];
  documents: DocumentRow[];
  problemFiles: ProblemFile[];
  status: string;
  isErrorStatus: boolean;
};

type HtmlSectionSplitActionDockProps = {
  isJobActive: boolean;
  isInspecting: boolean;
  status: string;
  isErrorStatus: boolean;
  problemFileCount: number;
  settingsFields: HtmlWorkflowField[];
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

export function HtmlSectionSplitResults({
  summary,
  documents,
  problemFiles,
  status,
  isErrorStatus,
}: HtmlSectionSplitResultsProps) {
  return (
    <>
      {summary ? (
        <HtmlWorkflowCard title="스캔 결과" description="문서별 목차 구성과 문제 파일 범위를 요약합니다.">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {[
              ["문서", summary.found_files],
              ["목차 있음", summary.documents_with_sections],
              ["목차 없음", summary.files_without_sections],
              ["읽기 실패", summary.failed_files],
              ["문제 표시", summary.reported_problem_files],
            ].map(([label, value]) => (
              <div key={label} className="rounded-md border border-slate-200 bg-slate-50 p-4 dark:border-[#30363d] dark:bg-[#0d1117]">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-500">{label}</p>
                <p className="mt-1 text-xl font-semibold tabular-nums text-slate-950 dark:text-white">{formatInteger(Number(value || 0))}</p>
              </div>
            ))}
          </div>
        </HtmlWorkflowCard>
      ) : null}

      <HtmlWorkflowCard
        title="문서별 목차"
        description={`${formatInteger(documents.length)}개 문서가 표시됩니다.`}
      >
        {documents.length ? (
          <div className="max-h-[560px] overflow-auto rounded-md border border-slate-200 dark:border-[#30363d]">
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

      <HtmlWorkflowCard title="작업 상태">
        <JobStatusLogger status={status} isErrorStatus={isErrorStatus} />
      </HtmlWorkflowCard>
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
      activityContent={<JobStatusLogger status={status} isErrorStatus={isErrorStatus} />}
      notificationActive={isErrorStatus || problemFileCount > 0}
      notificationContent={notificationContent}
      settingsTitle="시스템 설정"
      settingsContent={
        <div className="space-y-3">
          <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">테스트 옵션</p>
          </div>
          <HtmlWorkflowForm fields={settingsFields} />
        </div>
      }
    />
  );
}
