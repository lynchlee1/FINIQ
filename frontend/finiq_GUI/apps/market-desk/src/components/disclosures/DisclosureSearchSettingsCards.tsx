"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Checkbox,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@finiq/ui";
import {
  htmlControlClassName,
  htmlSelectContentClassName,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import type { DownloadOptions } from "@/features/download/types";
import { formatInteger } from "@/lib/format";

type DisclosureSearchConditionCardProps = {
  options: DownloadOptions | null;
  startDate: string;
  endDate: string;
  companyName: string;
  submitterName: string;
  marketLabel: string;
  securitiesLabel: string;
  onStartDateChange: (value: string) => void;
  onEndDateChange: (value: string) => void;
  onCompanyNameChange: (value: string) => void;
  onSubmitterNameChange: (value: string) => void;
  onMarketLabelChange: (value: string) => void;
  onSecuritiesLabelChange: (value: string) => void;
  beforeFields?: ReactNode;
};

type DisclosureTypeSelectionCardProps = {
  options: DownloadOptions | null;
  selectedDisclosures: Record<string, string[]>;
  onSelectedDisclosuresChange: (value: Record<string, string[]>) => void;
};

export function DisclosureSearchConditionCard({
  options,
  startDate,
  endDate,
  companyName,
  submitterName,
  marketLabel,
  securitiesLabel,
  onStartDateChange,
  onEndDateChange,
  onCompanyNameChange,
  onSubmitterNameChange,
  onMarketLabelChange,
  onSecuritiesLabelChange,
  beforeFields,
}: DisclosureSearchConditionCardProps) {
  return (
    <Card className="border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
      <CardHeader>
        <CardTitle className="dark:text-white">검색 조건</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {beforeFields}
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label className="dark:text-slate-300">시작일</Label>
            <Input type="date" value={startDate} onChange={(event) => onStartDateChange(event.target.value)} className={`${htmlControlClassName} dark:[color-scheme:dark]`} />
          </div>
          <div className="space-y-2">
            <Label className="dark:text-slate-300">종료일</Label>
            <Input type="date" value={endDate} onChange={(event) => onEndDateChange(event.target.value)} className={`${htmlControlClassName} dark:[color-scheme:dark]`} />
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label className="dark:text-slate-300">회사명</Label>
            <Input value={companyName} onChange={(event) => onCompanyNameChange(event.target.value)} className={htmlControlClassName} />
          </div>
          <div className="space-y-2">
            <Label className="dark:text-slate-300">제출인</Label>
            <Input value={submitterName} onChange={(event) => onSubmitterNameChange(event.target.value)} className={htmlControlClassName} />
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label className="dark:text-slate-300">시장</Label>
            <Select value={marketLabel} onValueChange={onMarketLabelChange}>
              <SelectTrigger className={htmlControlClassName}><SelectValue /></SelectTrigger>
              <SelectContent className={htmlSelectContentClassName}>
                {options?.market_types.map((item) => <SelectItem key={item.label} value={item.label}>{item.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label className="dark:text-slate-300">증권종류</Label>
            <Select value={securitiesLabel} onValueChange={onSecuritiesLabelChange}>
              <SelectTrigger className={htmlControlClassName}><SelectValue /></SelectTrigger>
              <SelectContent className={htmlSelectContentClassName}>
                {options?.securities_types.map((item) => <SelectItem key={item.label} value={item.label}>{item.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function DisclosureTypeSelectionCard({
  options,
  selectedDisclosures,
  onSelectedDisclosuresChange,
}: DisclosureTypeSelectionCardProps) {
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  const updateGroup = (suffix: string, values: string[]) => {
    const next = { ...selectedDisclosures };
    if (values.length) next[suffix] = values;
    else delete next[suffix];
    onSelectedDisclosuresChange(next);
  };

  return (
    <Card className="border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
      <CardHeader>
        <p className="text-caption font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">Disclosure Types</p>
        <CardTitle className="dark:text-white">공시 종류</CardTitle>
        <CardDescription className="dark:text-slate-400">다운로드할 공시 종류를 선택하세요.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {options?.disclosure_groups.map((group) => {
          const selected = selectedDisclosures[group.suffix] || [];
          return (
            <div key={group.suffix} className="overflow-hidden rounded-lg border border-[color:var(--tv-border)]">
              <div className="flex items-center justify-between gap-3 border-b border-[color:var(--tv-border)] bg-[var(--tv-surface)] px-4 py-2">
                <button
                  type="button"
                  onClick={() => setExpandedGroups((current) => ({ ...current, [group.suffix]: !current[group.suffix] }))}
                  className="text-body flex min-w-0 flex-1 items-center gap-2 text-left font-semibold dark:text-slate-200"
                >
                  {expandedGroups[group.suffix] ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
                  <span className="truncate">{group.label} ({formatInteger(group.items.length)})</span>
                </button>
                <div className="flex gap-2">
                  <Button variant="ghost" size="sm" className="text-caption h-7 text-[var(--tv-muted)] hover:text-[var(--tv-text)]" onClick={() => updateGroup(group.suffix, group.items.map((item) => item.code))}>전체 선택</Button>
                  <Button variant="ghost" size="sm" className="text-caption h-7 text-[var(--tv-muted)] hover:text-[var(--tv-text)]" onClick={() => updateGroup(group.suffix, [])}>전체 해제</Button>
                </div>
              </div>
              {expandedGroups[group.suffix] && (
                <div className="grid grid-cols-2 gap-2 p-4 md:grid-cols-3">
                  {group.items.map((item) => (
                    <div key={item.code} className="flex items-center space-x-2">
                      <Checkbox
                        id={`${group.suffix}-${item.code}`}
                        checked={selected.includes(item.code)}
                        onCheckedChange={() => updateGroup(
                          group.suffix,
                          selected.includes(item.code)
                            ? selected.filter((code) => code !== item.code)
                            : [...selected, item.code],
                        )}
                        className="border-[color:var(--tv-border)]"
                      />
                      <Label htmlFor={`${group.suffix}-${item.code}`} className="text-caption cursor-pointer truncate dark:text-slate-400 dark:hover:text-slate-200" title={item.name}>{item.name}</Label>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
