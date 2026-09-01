"use client";

import { useMemo, useState } from "react";
import { cn } from "@finiq/ui/utils";
import type {
  GovernanceEvidenceStatus,
  GovernanceTransitionCase,
} from "./governanceTransitionModel";

const ALL_CATEGORY_ID = "all";

const STATUS_LABELS: Record<GovernanceEvidenceStatus, string> = {
  filing: "공시",
  analysis: "공시 분석",
  charged: "검찰 공소",
  reported: "보도",
};

const STATUS_STYLES: Record<GovernanceEvidenceStatus, string> = {
  filing: "text-[var(--tv-up-text)]",
  analysis: "text-[var(--tv-text)]",
  charged: "text-[var(--tv-warning-text)]",
  reported: "text-[var(--tv-accent)]",
};

const STATUS_NOTES: Record<GovernanceEvidenceStatus, string> = {
  filing: "거래 당사자, 금액 또는 지분율을 공시 원문에서 확인했습니다.",
  analysis: "여러 공시의 자금 내역을 합산한 분석이며 단일 공시 문구가 아닙니다.",
  charged: "수사기관의 공소사실이며 유죄 확정 사실과 구분합니다.",
  reported: "언론이 공시 또는 취재로 연결한 내용이며 원문 공시와 확정도가 다릅니다.",
};

type GovernanceTransitionMonitorProps = {
  caseData: GovernanceTransitionCase;
};

export function GovernanceTransitionMonitor({ caseData }: GovernanceTransitionMonitorProps) {
  return <GovernanceTransitionCaseView key={caseData.id} caseData={caseData} />;
}

function GovernanceTransitionCaseView({ caseData }: GovernanceTransitionMonitorProps) {
  const [activeCategoryId, setActiveCategoryId] = useState(ALL_CATEGORY_ID);
  const [selectedEventId, setSelectedEventId] = useState(caseData.defaultEventId);
  const categoryLabels = useMemo(
    () => new Map(caseData.categories.map((category) => [category.id, category.label])),
    [caseData.categories],
  );
  const visibleEvents = useMemo(
    () => activeCategoryId === ALL_CATEGORY_ID
      ? caseData.events
      : caseData.events.filter((event) => event.categoryId === activeCategoryId),
    [activeCategoryId, caseData.events],
  );
  const selectedEvent = caseData.events.find((event) => event.id === selectedEventId)!;

  const handleCategoryChange = (categoryId: string) => {
    setActiveCategoryId(categoryId);
    const nextEvents = categoryId === ALL_CATEGORY_ID
      ? caseData.events
      : caseData.events.filter((event) => event.categoryId === categoryId);
    if (!nextEvents.some((event) => event.id === selectedEventId)) {
      setSelectedEventId(nextEvents[0].id);
    }
  };

  return (
    <section className="border-y border-[color:var(--tv-border-strong)]" aria-labelledby="governance-monitor-title">
      <header className="border-b border-[color:var(--tv-border)] py-4">
        <div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--tv-muted)]">
            <span>분석 사례</span>
            <strong className="font-medium text-[var(--tv-text)]">{caseData.name}</strong>
            <span className="font-mono tabular-nums">{caseData.market} {caseData.stockCode}</span>
            <span className="font-mono tabular-nums">기준 {caseData.referenceDate}</span>
          </div>
          <h2 id="governance-monitor-title" className="mt-2 text-xl font-semibold tracking-tight text-[var(--tv-text)]">
            지배구조 변화 모니터
          </h2>
          <p className="mt-1 max-w-4xl text-sm leading-6 text-[var(--tv-muted)]">{caseData.description}</p>
          <p className="mt-1 text-xs text-[var(--tv-muted)]">{caseData.scopeNote}</p>
        </div>
      </header>

      <div className="overflow-x-auto">
        <div className="grid min-w-max grid-flow-col auto-cols-[minmax(340px,1fr)] md:min-w-full">
          {caseData.comparisonPanels.map((panel, panelIndex) => (
            <section
              key={panel.id}
              className={cn("py-4 md:px-5", panelIndex > 0 ? "border-l border-[color:var(--tv-border)]" : "md:pl-0", panelIndex === caseData.comparisonPanels.length - 1 ? "md:pr-0" : "")}
              aria-label={panel.title}
            >
              <div className="mb-2 flex items-baseline justify-between gap-3">
                <h3 className="text-sm font-semibold text-[var(--tv-text)]">{panel.title}</h3>
                <span className="text-[11px] text-[var(--tv-muted)]">{panel.caption}</span>
              </div>
              <dl>
                {panel.rows.map((row) => (
                  <div key={row.label} className="grid grid-cols-[112px_minmax(0,1fr)] gap-3 border-b border-[color:var(--tv-border)] py-2 text-xs last:border-b-0">
                    <dt className="text-[var(--tv-muted)]">{row.label}</dt>
                    <dd className="text-right font-medium tabular-nums text-[var(--tv-text)]">{row.value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </div>

      <div className="border-t border-[color:var(--tv-border-strong)] pt-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-[var(--tv-text)]">근거 원장</h3>
            <p className="mt-1 text-xs text-[var(--tv-muted)]">경로를 선택하면 수치의 해석 기준과 원문을 확인할 수 있습니다.</p>
          </div>
          <div className="flex gap-4 overflow-x-auto" aria-label="근거 유형 필터">
            {[{ id: ALL_CATEGORY_ID, label: "전체" }, ...caseData.categories].map((category) => (
              <button
                key={category.id}
                type="button"
                className={cn(
                  "shrink-0 border-b pb-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--tv-accent)]",
                  activeCategoryId === category.id
                    ? "border-[var(--tv-accent)] text-[var(--tv-text)]"
                    : "border-transparent text-[var(--tv-muted)] hover:text-[var(--tv-text)]",
                )}
                onClick={() => handleCategoryChange(category.id)}
              >
                {category.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-left text-xs">
            <thead>
              <tr className="border-y border-[color:var(--tv-border-strong)] text-[11px] font-medium text-[var(--tv-muted)]">
                <th className="w-[132px] px-2 py-2 font-medium">시점</th>
                <th className="w-[90px] px-2 py-2 font-medium">구간</th>
                <th className="px-2 py-2 font-medium">자금·지배권 경로</th>
                <th className="w-[112px] px-2 py-2 text-right font-medium">규모</th>
                <th className="w-[100px] px-2 py-2 text-right font-medium">상태</th>
              </tr>
            </thead>
            <tbody>
              {visibleEvents.map((event) => {
                const isSelected = event.id === selectedEvent.id;
                return (
                  <tr
                    key={event.id}
                    className={cn(
                      "border-b border-[color:var(--tv-border)] transition-colors",
                      isSelected ? "bg-[var(--tv-accent-soft)]" : "hover:bg-[var(--tv-surface-muted)]",
                    )}
                  >
                    <td className="whitespace-nowrap px-2 py-2.5 font-mono tabular-nums text-[var(--tv-muted)]">{event.date}</td>
                    <td className="whitespace-nowrap px-2 py-2.5 text-[var(--tv-muted)]">{categoryLabels.get(event.categoryId)}</td>
                    <td className="px-2 py-2">
                      <button
                        type="button"
                        className="w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--tv-accent)]"
                        onClick={() => setSelectedEventId(event.id)}
                        aria-pressed={isSelected}
                      >
                        <span className="font-medium text-[var(--tv-text)]">{event.path}</span>
                        <span className="ml-2 text-[11px] text-[var(--tv-muted)]">{event.title}</span>
                      </button>
                    </td>
                    <td className="whitespace-nowrap px-2 py-2.5 text-right font-mono font-semibold tabular-nums text-[var(--tv-text)]">{event.scale}</td>
                    <td className={cn("whitespace-nowrap px-2 py-2.5 text-right font-medium", STATUS_STYLES[event.status])}>
                      {STATUS_LABELS[event.status]}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="grid gap-3 border-t border-[color:var(--tv-border-strong)] py-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(280px,0.6fr)]" aria-live="polite">
          <div>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h4 className="text-sm font-semibold text-[var(--tv-text)]">{selectedEvent.title}</h4>
              <span className={cn("text-xs font-medium", STATUS_STYLES[selectedEvent.status])}>{STATUS_LABELS[selectedEvent.status]}</span>
            </div>
            <p className="mt-1 text-sm leading-6 text-[var(--tv-text)]">{selectedEvent.summary}</p>
            <p className="mt-1 text-xs leading-5 text-[var(--tv-muted)]">{selectedEvent.evidence}</p>
          </div>
          <dl className="grid grid-cols-[88px_minmax(0,1fr)] content-start gap-x-3 gap-y-2 text-xs">
            <dt className="text-[var(--tv-muted)]">해석 기준</dt>
            <dd className="text-[var(--tv-text)]">{STATUS_NOTES[selectedEvent.status]}</dd>
            <dt className="text-[var(--tv-muted)]">그래프 노드</dt>
            <dd className="break-all font-mono text-[var(--tv-text)]">{selectedEvent.graphNodeId}</dd>
            <dt className="text-[var(--tv-muted)]">원문</dt>
            <dd>
              <a className="font-medium text-[var(--tv-accent)] underline decoration-[color:var(--tv-border-strong)] underline-offset-4 hover:decoration-current" href={selectedEvent.sourceUrl} target="_blank" rel="noreferrer">
                {selectedEvent.sourceLabel}
              </a>
            </dd>
          </dl>
        </div>
      </div>
    </section>
  );
}
