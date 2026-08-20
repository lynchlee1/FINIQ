"use client"

import { Loader2, RefreshCw } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Checkbox, Label } from "@finiq/ui";
import { formatInteger } from "@/lib/format";
import { cn } from "@finiq/ui/utils";

export type DisclosureFilterCandidate = {
  value: string;
  count: number;
};

type DisclosureFilterCandidateCardProps<TCandidate extends DisclosureFilterCandidate> = {
  eyebrow?: string;
  title: string;
  fieldLabel: string;
  candidates: TCandidate[];
  selectedValues: string[];
  loading: boolean;
  onLoadCandidates: () => void;
  onToggleValue: (value: string, checked: boolean) => void;
  onShowExamples?: (candidate: TCandidate) => void;
};

export function DisclosureFilterCandidateCard<TCandidate extends DisclosureFilterCandidate>({
  eyebrow = "Execution Options",
  title,
  fieldLabel,
  candidates,
  selectedValues,
  loading,
  onLoadCandidates,
  onToggleValue,
  onShowExamples,
}: DisclosureFilterCandidateCardProps<TCandidate>) {
  return (
    <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
      <CardHeader className="flex flex-col gap-3 pb-4 md:flex-row md:items-start md:justify-between md:space-y-0">
        <div className="min-w-0 space-y-1">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">{eyebrow}</p>
          <CardTitle className="dark:text-white">{title}</CardTitle>
        </div>
        <Button variant="outline" className="h-9 shrink-0 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200" onClick={onLoadCandidates} disabled={loading}>
          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
          불러오기
        </Button>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="grid gap-2 lg:grid-cols-2">
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-slate-50/80 dark:border-[#30363d] dark:bg-[#0d1117] lg:col-span-2">
            <div className="flex min-h-9 items-center px-3 py-2">
              <Label className="shrink-0 text-sm font-semibold text-slate-900 dark:text-slate-100">{fieldLabel}</Label>
            </div>

            {candidates.length ? (
              <div className="grid max-h-44 gap-2 overflow-auto border-t border-slate-200 p-2 dark:border-[#30363d]">
                {candidates.map((candidate) => {
                  const checked = selectedValues.includes(candidate.value);
                  return (
                    <div key={candidate.value} className={cn(
                      "grid items-center gap-2 rounded-lg border border-slate-200 bg-white/80 p-2 dark:bg-[#161b22] dark:border-[#30363d] lg:grid-cols-[minmax(0,1fr)_auto]",
                      checked ? "border-slate-300 bg-slate-100/80 dark:border-[#30363d] dark:bg-[#21262d]" : ""
                    )}>
                      <label className="flex min-w-0 cursor-pointer items-center gap-3 rounded-md border border-slate-200 bg-white px-3 py-2 dark:bg-[#0d1117] dark:border-[#30363d]">
                        <Checkbox checked={checked} onCheckedChange={(value) => onToggleValue(candidate.value, !!value)} className="dark:border-[#30363d]" />
                        <span className={cn(
                          "truncate text-sm font-bold",
                          checked ? "text-slate-900 dark:text-slate-100" : "text-slate-700 dark:text-slate-200"
                        )}>{candidate.value}</span>
                      </label>
                      <span className="flex shrink-0 items-center gap-2">
                        <span className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs font-bold tabular-nums text-slate-500 dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-300">{formatInteger(candidate.count)}건</span>
                        {onShowExamples ? (
                          <Button type="button" variant="outline" size="sm" className="h-7 px-2 text-xs dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200" onClick={() => onShowExamples(candidate)}>
                            예시
                          </Button>
                        ) : null}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
