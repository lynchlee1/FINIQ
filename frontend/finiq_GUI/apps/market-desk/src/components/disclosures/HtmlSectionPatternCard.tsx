"use client";

import { CircleDashed, ExternalLink, Loader2 } from "lucide-react";
import { Button } from "@finiq/ui";
import { HtmlWorkflowCard } from "@/components/html-workflow/HtmlWorkflowTemplate";
import { formatInteger } from "@/lib/format";

export type SectionPattern = {
  signature: string;
  count: number;
  section_count: number;
  sections?: { toc_id: string; index?: number; title: string }[];
  sample_documents?: {
    source_file?: string;
    source_name?: string;
    source_relative_path?: string;
  }[];
};

type HtmlSectionPatternCardProps = {
  inputDirectory: string;
  sectionPatterns: SectionPattern[];
  selectedPatternTocIds: Record<string, string[]>;
  isLoading: boolean;
  onTogglePatternSection: (signature: string, tocId: string) => void;
  onSetPatternSelection: (signature: string, tocIds: string[]) => void;
  decidedPatterns?: Record<string, boolean>;
  defaultSelectAll?: boolean;
  pending?: boolean;
  emptyText?: string;
};

function sourceHtmlUrl(inputDirectory: string, document: NonNullable<SectionPattern["sample_documents"]>[number]) {
  const params = new URLSearchParams({
    input_directory: inputDirectory,
    source_name: document.source_relative_path || document.source_name || "",
  });
  return `/api/disclosures/html/sections/source?${params.toString()}`;
}

export function HtmlSectionPatternCard({
  inputDirectory,
  sectionPatterns,
  selectedPatternTocIds,
  isLoading,
  onTogglePatternSection,
  onSetPatternSelection,
  decidedPatterns,
  defaultSelectAll = false,
  pending = false,
  emptyText = "소스를 불러오면 전체 디렉토리의 목차 조합 빈도가 표시됩니다.",
}: HtmlSectionPatternCardProps) {
  const maxCount = Math.max(1, ...sectionPatterns.map((pattern) => pattern.count));

  return (
    <HtmlWorkflowCard
      title="목차 조합 모아보기"
      description="전체 입력 디렉토리에서 같은 목차 조합이 몇 번 나왔는지 표시합니다."
    >
      {isLoading ? (
        <div className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
          <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
          목차 조합을 불러오는 중입니다.
        </div>
      ) : sectionPatterns.length ? (
        <div className="space-y-2">
          {sectionPatterns.map((pattern) => {
            const sections = pattern.sections || [];
            const widthPercent = Math.max(4, Math.round((pattern.count / maxCount) * 100));
            const selectedTocIds = selectedPatternTocIds[pattern.signature]
              ?? (defaultSelectAll ? sections.map((section) => section.toc_id) : []);
            return (
              <div key={pattern.signature} className="grid w-full grid-cols-[minmax(0,1fr)_minmax(7rem,30%)_5rem] items-start gap-3 rounded-md px-3 py-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-xs font-medium text-slate-700 dark:text-slate-300">{pattern.signature}</p>
                      <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-500">목차 {formatInteger(pattern.section_count)}개 조합</p>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-[11px]" onClick={() => onSetPatternSelection(pattern.signature, sections.map((section) => section.toc_id))}>전체 선택</Button>
                      <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-[11px]" onClick={() => onSetPatternSelection(pattern.signature, [])}>전체 해제</Button>
                    </div>
                  </div>
                  {sections.length ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {sections.map((section) => (
                        <label key={`${pattern.signature}-${section.toc_id}`} className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-2 py-1 text-[11px] text-slate-600 dark:border-[#30363d] dark:text-slate-300">
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
                  <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-500">
                    {decidedPatterns ? (decidedPatterns[pattern.signature] ? "결정됨" : "Pending") : "저장할 목차"}
                  </p>
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
                  <div className="h-3 rounded-full bg-slate-700 dark:bg-slate-300" style={{ width: `${widthPercent}%` }} />
                </div>
                <div className="text-right text-xs tabular-nums text-slate-500 dark:text-slate-400">{formatInteger(pattern.count)}개</div>
              </div>
            );
          })}
        </div>
      ) : pending ? (
        <div className="flex min-h-20 items-center justify-between gap-3 rounded-md border border-dashed border-[color:var(--tv-border)] bg-[var(--tv-control)] px-4 text-sm">
          <div className="flex items-center gap-2 font-semibold text-[var(--tv-text)]">
            <CircleDashed className="h-4 w-4 text-[var(--tv-accent)]" aria-hidden="true" />
            Pending
          </div>
          <span className="text-xs text-[var(--tv-muted)]">공시원문 저장 후 입력 대기</span>
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
          {emptyText}
        </div>
      )}
    </HtmlWorkflowCard>
  );
}
