"use client"

import { useCallback, useEffect, useRef, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, ExternalLink, FolderOpen, Loader2 } from "lucide-react";
import { Button } from "@finiq/ui";
import { ActionDock } from "@/components/ui/ActionDock";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import {
  HtmlWorkflowCard,
  HtmlWorkflowForm,
  htmlTableFrameClassName,
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
  section_count?: number;
  sections?: TocItem[];
};

export type SplitSection = TocItem & {
  html: string;
};

export type SplitResult = {
  document: DocumentRow;
  section_count: number;
  sections: SplitSection[];
};

export type ReviewView = "source" | "sections";

export type ProblemFile = {
  kind: "read_failed" | "no_sections";
  source_file: string;
  error?: string;
};

export type SectionPattern = {
  signature: string;
  count: number;
  section_count: number;
  sections?: TocItem[];
  sample_documents?: DocumentRow[];
};

export type InspectResult = {
  input_directory?: string;
  summary?: {
    found_files?: number;
    documents_with_sections?: number;
    files_without_sections?: number;
    failed_files?: number;
    reported_problem_files?: number;
    page?: number;
    page_size?: number;
    returned_files?: number;
    has_next_page?: boolean;
  };
  documents?: DocumentRow[];
  problem_files?: ProblemFile[];
  section_patterns?: SectionPattern[];
};

type HtmlSectionSplitResultsProps = {
  inputDirectory: string;
  documents: DocumentRow[];
  problemFiles: ProblemFile[];
  sectionPatterns: SectionPattern[];
  selectedPatternTocIds: Record<string, string[]>;
  isLoadingSectionPatterns: boolean;
  page: number;
  hasNextPage: boolean;
  selectedDocument: DocumentRow | null;
  selectedSourceUrl: string;
  splitResult: SplitResult | null;
  selectedSectionId: string;
  activeReviewView: ReviewView;
  isInspecting: boolean;
  isSourceLoadDisabled: boolean;
  isSplitting: boolean;
  onInspectFolder: () => void;
  onViewSource: (document: DocumentRow) => void;
  onViewSections: (document: DocumentRow) => void;
  onChangeReviewView: (view: ReviewView) => void;
  onPreviousPage: () => void;
  onNextPage: () => void;
  onSelectSection: (tocId: string) => void;
  onTogglePatternSection: (signature: string, tocId: string) => void;
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
  sectionPatterns,
  selectedPatternTocIds,
  isLoadingSectionPatterns,
  page,
  hasNextPage,
  selectedDocument,
  selectedSourceUrl,
  splitResult,
  selectedSectionId,
  activeReviewView,
  isInspecting,
  isSourceLoadDisabled,
  isSplitting,
  onInspectFolder,
  onViewSource,
  onViewSections,
  onChangeReviewView,
  onPreviousPage,
  onNextPage,
  onSelectSection,
  onTogglePatternSection,
}: HtmlSectionSplitResultsProps) {
  const reviewPanelRef = useRef<HTMLDivElement | null>(null);
  const selectedSection = splitResult?.sections.find((section) => section.toc_id === selectedSectionId) || splitResult?.sections[0] || null;
  const maxSectionPatternCount = Math.max(1, ...sectionPatterns.map((pattern) => pattern.count));

  const scrollToReviewPanel = useCallback(() => {
    window.requestAnimationFrame(() => {
      reviewPanelRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
    });
  }, []);

  useEffect(() => {
    if (selectedDocument) {
      scrollToReviewPanel();
    }
  }, [scrollToReviewPanel, selectedDocument?.source_file]);

  const reviewPanelActions = (
    <div className="inline-flex gap-1 rounded-md border border-slate-200 p-1 dark:border-[#30363d]">
      <Button
        type="button"
        variant={activeReviewView === "source" ? "default" : "ghost"}
        size="sm"
        className="h-8"
        onClick={() => onChangeReviewView("source")}
        disabled={!selectedDocument}
      >
        공시 원문
      </Button>
      <Button
        type="button"
        variant={activeReviewView === "sections" ? "default" : "ghost"}
        size="sm"
        className="h-8"
        onClick={() => onChangeReviewView("sections")}
        disabled={!selectedDocument}
      >
        목차별 보기
      </Button>
    </div>
  );

  const rowReviewActions = (item: DocumentRow, isSelected: boolean) => (
    <div className="inline-flex gap-1 rounded-md border border-slate-200 p-1 dark:border-[#30363d]">
      <Button
        type="button"
        variant={isSelected && activeReviewView === "source" ? "default" : "ghost"}
        size="sm"
        className="h-8 min-w-24"
        onClick={() => {
          onViewSource(item);
          scrollToReviewPanel();
        }}
        disabled={isSplitting && isSelected}
      >
        <Loader2
          className={[
            "mr-1 h-3.5 w-3.5 shrink-0",
            isSplitting && isSelected && activeReviewView === "source" ? "animate-spin opacity-100" : "opacity-0",
          ].join(" ")}
        />
        원문 보기
      </Button>
      <Button
        type="button"
        variant={isSelected && activeReviewView === "sections" ? "default" : "ghost"}
        size="sm"
        className="h-8 min-w-28"
        onClick={() => {
          onViewSections(item);
          scrollToReviewPanel();
        }}
        disabled={isSplitting && isSelected}
      >
        <Loader2
          className={[
            "mr-1 h-3.5 w-3.5 shrink-0",
            isSplitting && isSelected && activeReviewView === "sections" ? "animate-spin opacity-100" : "opacity-0",
          ].join(" ")}
        />
        목차별 보기
      </Button>
    </div>
  );

  const renderReviewContent = () => {
    if (!selectedDocument) {
      return (
        <div className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
          개별 공시에서 원문 보기 또는 목차별 보기를 선택하세요.
        </div>
      );
    }

    if (activeReviewView === "source") {
      return (
        <iframe
          className="h-[560px] w-full rounded-md border border-slate-200 bg-white dark:border-[#30363d]"
          src={selectedSourceUrl || sourceHtmlUrl(inputDirectory, selectedDocument)}
          title="공시 원문"
        />
      );
    }

    if (isSplitting && !splitResult) {
      return (
        <div className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
          목차를 불러오는 중입니다.
        </div>
      );
    }

    if (!splitResult) {
      return (
        <div className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
          이 공시의 목차 데이터를 아직 불러오지 못했습니다.
        </div>
      );
    }

    if (!splitResult.sections.length) {
      return (
        <div className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
          이 공시에서 분리할 목차를 찾지 못했습니다.
        </div>
      );
    }

    return (
      <>
        <div className="flex flex-wrap gap-1.5">
          {splitResult.sections.map((section) => (
            <Button
              key={section.toc_id}
              type="button"
              variant={section.toc_id === selectedSection?.toc_id ? "default" : "outline"}
              size="sm"
              onClick={() => onSelectSection(section.toc_id)}
            >
              <span className="font-mono">{section.toc_id}</span>
              {section.title ? <span className="ml-1">{section.title}</span> : null}
            </Button>
          ))}
        </div>
        <iframe
          className="h-[560px] w-full rounded-md border border-slate-200 bg-white dark:border-[#30363d]"
          srcDoc={selectedSection?.html || ""}
          title="목차별 보기"
        />
      </>
    );
  };

  return (
    <>
      <HtmlWorkflowCard
        title="개별 공시"
        actions={
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onInspectFolder} disabled={isSourceLoadDisabled}>
              {isInspecting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <FolderOpen className="mr-1 h-4 w-4" />}
              소스 불러오기
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onPreviousPage} disabled={page <= 1}>
              <ChevronLeft className="mr-1 h-4 w-4" />
              이전
            </Button>
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{formatInteger(page)}페이지</span>
            <Button type="button" variant="outline" size="sm" onClick={onNextPage} disabled={!hasNextPage}>
              다음
              <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        }
      >
        {documents.length ? (
          <div className="max-h-[560px] overflow-auto rounded-md border border-slate-200 dark:border-[#30363d]">
            <table className="w-full min-w-[780px] text-left text-sm">
              <thead className="sticky top-0 bg-slate-50 text-xs text-slate-500 dark:bg-[#0d1117] dark:text-slate-400">
                <tr>
                  <th className="px-3 py-2 font-semibold">공시 파일</th>
                  <th className="w-24 px-3 py-2 text-right font-semibold">목차 수</th>
                  <th className="w-64 px-3 py-2 text-center font-semibold">보기</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-[#30363d]">
                {documents.map((item) => {
                  const isSelected = selectedDocument?.source_file === item.source_file;
                  return (
                    <tr key={item.source_file} className={isSelected ? "bg-slate-50 dark:bg-[#21262d]" : ""}>
                      <td className="px-3 py-3 align-middle">
                        <p className="font-medium text-slate-900 dark:text-slate-100">{item.source_name}</p>
                        <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">{compactPath(item.source_relative_path || item.source_file)}</p>
                      </td>
                      <td className="px-3 py-3 text-right align-middle tabular-nums text-slate-700 dark:text-slate-300">
                        {formatInteger(item.section_count || 0)}
                      </td>
                      <td className="px-3 py-3 text-center align-middle">
                        {rowReviewActions(item, isSelected)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
            폴더를 열면 개별 공시와 목차 분리 상태가 표시됩니다.
          </div>
        )}
      </HtmlWorkflowCard>

      <div ref={reviewPanelRef}>
        <HtmlWorkflowCard
          title={activeReviewView === "source" ? "공시 원문" : "목차별 보기"}
          description={
            selectedDocument
              ? activeReviewView === "sections" && splitResult
                ? `${selectedDocument.source_relative_path || selectedDocument.source_name} - ${formatInteger(splitResult.section_count)}개 목차`
                : selectedDocument.source_relative_path || selectedDocument.source_name
              : "공시 파일을 선택하세요."
          }
          actions={reviewPanelActions}
        >
          {renderReviewContent()}
        </HtmlWorkflowCard>
      </div>

      <HtmlWorkflowCard
        title="목차 조합 모아보기"
        description="전체 입력 디렉토리에서 같은 목차 조합이 몇 번 나왔는지 표시합니다."
      >
        {isLoadingSectionPatterns ? (
          <div className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
            목차 조합을 불러오는 중입니다.
          </div>
        ) : sectionPatterns.length ? (
          <div className="space-y-2">
            {sectionPatterns.map((pattern) => {
              const widthPercent = Math.max(4, Math.round((pattern.count / maxSectionPatternCount) * 100));
              const selectedTocIds = selectedPatternTocIds[pattern.signature] || (pattern.sections || []).map((section) => section.toc_id);
              return (
                <div
                  key={pattern.signature}
                  className="grid w-full grid-cols-[minmax(0,1fr)_minmax(7rem,30%)_5rem] items-start gap-3 rounded-md px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-slate-700 dark:text-slate-300">{pattern.signature}</p>
                    <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-500">
                      목차 {formatInteger(pattern.section_count)}개 조합
                    </p>
                    {pattern.sections?.length ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {pattern.sections.map((section) => (
                          <label
                            key={`${pattern.signature}-${section.toc_id}`}
                            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-2 py-1 text-[11px] text-slate-600 dark:border-[#30363d] dark:text-slate-300"
                          >
                            <input
                              type="checkbox"
                              className="h-3.5 w-3.5 rounded border-slate-300"
                              checked={selectedTocIds.includes(section.toc_id)}
                              onChange={() => onTogglePatternSection(pattern.signature, section.toc_id)}
                            />
                            <span className="font-mono">{section.toc_id}</span>
                            {section.title ? <span>{section.title}</span> : null}
                          </label>
                        ))}
                      </div>
                    ) : null}
                    <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-500">저장할 목차</p>
                    {pattern.sample_documents?.length ? (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {pattern.sample_documents.map((document) => (
                          <a
                            key={`${pattern.signature}-${document.source_relative_path || document.source_name}`}
                            href={sourceHtmlUrl(inputDirectory, document)}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 px-2 text-[11px] font-medium text-slate-700 hover:bg-slate-50 dark:border-[#30363d] dark:text-slate-300 dark:hover:bg-[#21262d]"
                          >
                            <ExternalLink className="h-3 w-3" />
                            공시 열기
                          </a>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="h-3 rounded-full bg-slate-100 dark:bg-[#0d1117]">
                    <div
                      className="h-3 rounded-full bg-slate-700 dark:bg-slate-300"
                      style={{ width: `${widthPercent}%` }}
                    />
                  </div>
                  <div className="text-right text-xs tabular-nums text-slate-500 dark:text-slate-400">
                    {formatInteger(pattern.count)}개
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
            소스를 불러오면 전체 디렉토리의 목차 조합 빈도가 표시됩니다.
          </div>
        )}
      </HtmlWorkflowCard>

      {problemFiles.length ? (
        <HtmlWorkflowCard title="문제 파일" description="목차가 없거나 읽기에 실패한 HTML 파일입니다.">
          <div className={htmlTableFrameClassName}>
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
          isCancellable={isJobActive || isInspecting}
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
