"use client"

import { Pencil, Plus, Save, Trash2, Upload } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Label } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";

export const DISCLOSURE_FILTER_FIELD_OPTIONS = [
  ["title", "제목"],
  ["company_name", "회사명"],
  ["submitter", "제출인"],
  ["market", "시장"],
  ["disclosed_date", "공시일"],
  ["acpt_no", "접수번호"],
  ["company_id", "회사코드"],
] as const;

export const DISCLOSURE_FILTER_OPERATOR_OPTIONS = [
  ["contains", "contains"],
  ["not_contains", "not contains"],
  ["exact_match", "exact match"],
  ["equals", "equals"],
  ["not_equals", "not equals"],
  ["starts_with", "starts with"],
  ["ends_with", "ends with"],
  ["in", "in"],
  ["before", "before"],
  ["after", "after"],
  ["on_or_before", "<="],
  ["on_or_after", ">="],
  ["between", "between"],
  ["exists", "exists"],
  ["empty", "is empty"],
] as const;

export type DisclosureFilterFieldKey = (typeof DISCLOSURE_FILTER_FIELD_OPTIONS)[number][0];
export type DisclosureFilterOperatorKey = (typeof DISCLOSURE_FILTER_OPERATOR_OPTIONS)[number][0];
export type DisclosureFilterConnector = "" | "AND" | "OR";

export type DisclosureConditionBlock = {
  connector: DisclosureFilterConnector;
  open_count: number;
  not: boolean;
  ignore_spaces: boolean;
  clean_search: boolean;
  field: DisclosureFilterFieldKey;
  operator: DisclosureFilterOperatorKey;
  value: string;
  close_count: number;
};

export type DisclosureConditionPreset = {
  name: string;
  condition_blocks: DisclosureConditionBlock[];
};

export type DisclosureConditionPresetPayload = {
  name?: string;
  condition_blocks?: unknown;
  source_json_path?: string;
};

type DisclosureConditionFilterCardProps = {
  conditions: DisclosureConditionBlock[];
  onConditionsChange: (conditions: DisclosureConditionBlock[]) => void;
  presets?: DisclosureConditionPreset[];
  presetName: string;
  selectedPreset: string;
  onPresetNameChange: (value: string) => void;
  onSelectedPresetChange: (value: string) => void;
  onLoadPreset: (name: string) => void;
  onLoadPresetFromJson: () => void;
  onSavePreset: () => void;
  onRenamePreset: () => void;
  onDeletePreset: () => void;
};

export function makeEmptyDisclosureCondition(connector: DisclosureFilterConnector = ""): DisclosureConditionBlock {
  return {
    connector,
    open_count: 0,
    not: false,
    ignore_spaces: false,
    clean_search: false,
    field: "title",
    operator: "contains",
    value: "",
    close_count: 0,
  };
}

export function normalizeDisclosureConditionBlocks(value: unknown): DisclosureConditionBlock[] {
  if (!Array.isArray(value)) return [makeEmptyDisclosureCondition()];
  const blocks = value.map((item, index) => {
    const row = item as Partial<DisclosureConditionBlock>;
    const connector = String(row.connector || "AND").toUpperCase();
    const field = DISCLOSURE_FILTER_FIELD_OPTIONS.some(([key]) => key === row.field) ? row.field as DisclosureFilterFieldKey : "title";
    const operator = DISCLOSURE_FILTER_OPERATOR_OPTIONS.some(([key]) => key === row.operator) ? row.operator as DisclosureFilterOperatorKey : "contains";
    return {
      ...makeEmptyDisclosureCondition(index === 0 || (connector !== "AND" && connector !== "OR") ? "" : connector as DisclosureFilterConnector),
      open_count: Math.max(0, Math.floor(Number(row.open_count || 0))),
      not: !!row.not,
      ignore_spaces: !!row.ignore_spaces,
      clean_search: !!row.clean_search,
      field,
      operator,
      value: String(row.value || ""),
      close_count: Math.max(0, Math.floor(Number(row.close_count || 0))),
    };
  }).filter((row) => row.value.trim() || row.operator === "exists" || row.operator === "empty");
  return blocks.length ? blocks : [makeEmptyDisclosureCondition()];
}

function countParens(value: string, paren: "(" | ")") {
  return [...String(value || "")].filter((char) => char === paren).length;
}

function fieldLabel(field: DisclosureFilterFieldKey) {
  return DISCLOSURE_FILTER_FIELD_OPTIONS.find(([key]) => key === field)?.[1] || field;
}

function operatorLabel(operator: DisclosureFilterOperatorKey) {
  return DISCLOSURE_FILTER_OPERATOR_OPTIONS.find(([key]) => key === operator)?.[1] || operator;
}

export function DisclosureConditionFilterCard({
  conditions,
  onConditionsChange,
  presets = [],
  presetName,
  selectedPreset,
  onPresetNameChange,
  onSelectedPresetChange,
  onLoadPreset,
  onLoadPresetFromJson,
  onSavePreset,
  onRenamePreset,
  onDeletePreset,
}: DisclosureConditionFilterCardProps) {
  const updateCondition = (index: number, patch: Partial<DisclosureConditionBlock>) => {
    const next = conditions.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row);
    if (next[0]) next[0].connector = "";
    onConditionsChange(next);
  };

  const removeCondition = (index: number) => {
    const next = conditions.filter((_, rowIndex) => rowIndex !== index);
    if (!next.length) {
      onConditionsChange([makeEmptyDisclosureCondition()]);
      return;
    }
    next[0].connector = "";
    onConditionsChange(next);
  };

  const conditionPreview = conditions.filter((row) => row.value.trim() || row.operator === "exists" || row.operator === "empty");

  return (
    <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
      <CardHeader>
        <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Filters</p>
        <CardTitle className="dark:text-white">공시 조건</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-2">
          <Label className="dark:text-slate-300">조건검색 프리셋</Label>
          <div className="grid gap-2 md:grid-cols-[minmax(150px,1fr)_minmax(150px,.9fr)_auto_auto_auto_auto]">
            <select
              value={selectedPreset}
              onChange={(event) => {
                const nextPreset = event.target.value;
                onSelectedPresetChange(nextPreset);
                onPresetNameChange(nextPreset);
                if (nextPreset) onLoadPreset(nextPreset);
              }}
              className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm font-semibold dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
              aria-label="조건검색 프리셋 선택"
            >
              <option value="">프리셋 선택</option>
              {presets.map((preset) => (
                <option key={preset.name} value={preset.name}>{preset.name}</option>
              ))}
            </select>
            <Input value={presetName} onChange={(event) => onPresetNameChange(event.target.value)} onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                onSavePreset();
              }
            }} placeholder="프리셋 이름" className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
            <Button variant="outline" onClick={onLoadPresetFromJson}><Upload className="mr-2 h-4 w-4" />불러오기</Button>
            <Button onClick={onSavePreset}><Save className="mr-2 h-4 w-4" />저장</Button>
            <Button variant="outline" onClick={onRenamePreset} disabled={!selectedPreset}><Pencil className="mr-2 h-4 w-4" />수정</Button>
            <Button variant="outline" onClick={onDeletePreset} disabled={!selectedPreset}><Trash2 className="mr-2 h-4 w-4" />삭제</Button>
          </div>
        </div>

        <div className="grid gap-2">
          <Label className="dark:text-slate-300">조건 블록</Label>
          <div className="flex min-h-[52px] flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:bg-[#0d1117] dark:border-[#30363d]">
            {conditionPreview.length ? conditionPreview.map((condition, index) => (
              <div key={`${condition.field}-${index}`} className="flex flex-wrap items-center gap-2">
                {index > 0 && <span className="rounded-lg border border-slate-200 bg-teal-50 px-2 py-1 text-xs font-bold text-teal-800 dark:bg-teal-900/30 dark:border-teal-900/50 dark:text-teal-300">{condition.connector || "AND"}</span>}
                {condition.open_count > 0 && <span className="rounded-lg border border-slate-200 bg-slate-100 px-2 py-1 text-xs font-bold dark:bg-[#21262d] dark:border-[#30363d] dark:text-slate-300">{"(".repeat(condition.open_count)}</span>}
                {condition.not && <span className="rounded-lg border border-slate-200 bg-teal-50 px-2 py-1 text-xs font-bold text-teal-800 dark:bg-teal-900/30 dark:border-teal-900/50 dark:text-teal-300">NOT</span>}
                <span className="inline-flex min-h-8 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-900 dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-100">
                  <span className="text-teal-700 dark:text-teal-300">{fieldLabel(condition.field)}</span>
                  <em className="not-italic text-slate-500 dark:text-slate-400">{operatorLabel(condition.operator)}</em>
                  {condition.operator !== "exists" && condition.operator !== "empty" && <strong>{condition.value}</strong>}
                  {condition.ignore_spaces && <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-[#21262d] dark:text-slate-300">공백무시</span>}
                  {condition.clean_search && <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-[#21262d] dark:text-slate-300">Clean</span>}
                </span>
                {condition.close_count > 0 && <span className="rounded-lg border border-slate-200 bg-slate-100 px-2 py-1 text-xs font-bold dark:bg-[#21262d] dark:border-[#30363d] dark:text-slate-300">{")".repeat(condition.close_count)}</span>}
              </div>
            )) : <span className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-bold text-slate-500 dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-400">조건 블록을 추가하세요.</span>}
          </div>

          <div className="grid gap-2 overflow-x-auto rounded-lg border border-slate-200 bg-slate-50/80 p-2 dark:bg-[#0d1117] dark:border-[#30363d]">
            {conditions.map((condition, index) => (
              <div key={index} className="grid min-w-[980px] items-center gap-2 rounded-lg border border-slate-200 bg-white/80 p-2 dark:bg-[#161b22] dark:border-[#30363d] lg:grid-cols-[96px_minmax(0,1fr)_58px]">
                <select
                  value={condition.connector}
                  disabled={index === 0}
                  onChange={(event) => updateCondition(index, { connector: event.target.value as DisclosureFilterConnector })}
                  className="h-9 rounded-md border border-slate-200 bg-white px-2 text-xs font-bold text-slate-500 disabled:text-teal-700 disabled:opacity-100 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-300 dark:disabled:text-teal-300"
                  aria-label="연결 조건"
                >
                  <option value="">START</option>
                  <option value="AND">AND</option>
                  <option value="OR">OR</option>
                </select>
                <div className="grid min-w-0 items-center gap-2 lg:grid-cols-[36px_68px_86px_72px_minmax(84px,.45fr)_minmax(112px,.55fr)_minmax(240px,3fr)_36px]">
                  <Input value={"(".repeat(condition.open_count)} onChange={(event) => updateCondition(index, { open_count: countParens(event.target.value, "(") })} aria-label="그룹 시작" className={cn("h-9 text-center font-bold dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200", condition.open_count ? "bg-cyan-50 border-cyan-300 dark:bg-cyan-900/20" : "")} />
                  <label className="flex h-9 items-center justify-center gap-1 rounded-md border border-slate-200 bg-white px-2 text-xs font-bold text-slate-500 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-300">
                    <input type="checkbox" checked={condition.not} onChange={(event) => updateCondition(index, { not: event.target.checked })} />
                    NOT
                  </label>
                  <label className="flex h-9 items-center justify-center gap-1 rounded-md border border-slate-200 bg-white px-2 text-xs font-bold text-slate-500 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-300">
                    <input type="checkbox" checked={condition.ignore_spaces} onChange={(event) => updateCondition(index, { ignore_spaces: event.target.checked })} />
                    공백무시
                  </label>
                  <label className="flex h-9 items-center justify-center gap-1 rounded-md border border-slate-200 bg-white px-2 text-xs font-bold text-slate-500 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-300">
                    <input type="checkbox" checked={condition.clean_search} onChange={(event) => updateCondition(index, { clean_search: event.target.checked })} />
                    Clean
                  </label>
                  <select value={condition.field} onChange={(event) => updateCondition(index, { field: event.target.value as DisclosureFilterFieldKey })} aria-label="필드" className="h-9 rounded-md border border-slate-200 bg-white px-2 text-xs font-bold text-slate-500 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-300">
                    {DISCLOSURE_FILTER_FIELD_OPTIONS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                  </select>
                  <select value={condition.operator} onChange={(event) => updateCondition(index, { operator: event.target.value as DisclosureFilterOperatorKey })} aria-label="연산자" className="h-9 rounded-md border border-slate-200 bg-white px-2 text-xs font-bold text-slate-500 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-300">
                    {DISCLOSURE_FILTER_OPERATOR_OPTIONS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                  </select>
                  <Input value={condition.value} onChange={(event) => updateCondition(index, { value: event.target.value })} placeholder="값" className="h-9 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                  <Input value={")".repeat(condition.close_count)} onChange={(event) => updateCondition(index, { close_count: countParens(event.target.value, ")") })} aria-label="그룹 끝" className={cn("h-9 text-center font-bold dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200", condition.close_count ? "bg-cyan-50 border-cyan-300 dark:bg-cyan-900/20" : "")} />
                </div>
                <Button variant="ghost" onClick={() => removeCondition(index)} className="h-8 px-2 text-xs text-slate-500 hover:text-red-600 dark:text-slate-400 dark:hover:bg-red-900/20 dark:hover:text-red-300">삭제</Button>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => onConditionsChange([...conditions, makeEmptyDisclosureCondition(conditions.length ? "AND" : "")])}>
              <Plus className="mr-2 h-4 w-4" />
              조건 추가
            </Button>
            <Button
              variant="outline"
              onClick={() => onConditionsChange([
                ...conditions,
                {
                  ...makeEmptyDisclosureCondition(conditions.length ? "OR" : ""),
                  open_count: 1,
                  close_count: 1,
                },
              ])}
            >
              <Plus className="mr-2 h-4 w-4" />
              그룹 조건 추가
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
