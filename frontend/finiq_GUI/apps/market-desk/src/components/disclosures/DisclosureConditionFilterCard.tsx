"use client"

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Eraser, ListPlus, Plus, Redo2, Save, Trash2, Undo2, Upload } from "lucide-react";
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
export type DisclosureFilterConnector = "" | "AND" | "XOR" | "OR";

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
  mode: string;
  condition_blocks: DisclosureConditionBlock[];
  status: "ready" | "running" | "interrupted" | "completed" | "failed";
  steps: {
    condition_input: { status: "completed" };
    database_query: { status: "pending" | "running" | "interrupted" | "completed" | "failed" };
    record: { status: "pending" | "running" | "interrupted" | "completed" | "failed" };
  };
};

export type DisclosureConditionPresetPayload = {
  name?: string;
  mode?: string;
  condition_blocks?: unknown;
  source_json_path?: string;
};

type DisclosureConditionFilterCardProps = {
  conditions: DisclosureConditionBlock[];
  onConditionsChange: (conditions: DisclosureConditionBlock[]) => void;
  presets?: DisclosureConditionPreset[];
  selectedPreset: string;
  onSelectedPresetChange: (value: string) => void;
  onLoadPreset: (name: string) => void;
  onLoadPresetFromJson?: () => void;
  onSavePreset: () => void;
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

function isEmptyDisclosureConditionBlocks(conditions: DisclosureConditionBlock[]) {
  if (conditions.length !== 1) return false;
  const [row] = conditions;
  const empty = makeEmptyDisclosureCondition();
  return (Object.keys(empty) as (keyof DisclosureConditionBlock)[]).every((key) => row[key] === empty[key]);
}

export function normalizeDisclosureConditionBlocks(value: unknown): DisclosureConditionBlock[] {
  if (!Array.isArray(value)) throw new Error("condition_blocks must be an array");
  const blocks = value.map((item, index) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      throw new Error(`condition_blocks[${index}] must be an object`);
    }
    const row = item as Record<string, unknown>;
    const connector = row.connector;
    if ((index === 0 && connector !== "") || (index > 0 && connector !== "AND" && connector !== "XOR" && connector !== "OR")) {
      throw new Error(`condition_blocks[${index}].connector is invalid`);
    }
    if (!DISCLOSURE_FILTER_FIELD_OPTIONS.some(([key]) => key === row.field)) {
      throw new Error(`condition_blocks[${index}].field is invalid`);
    }
    if (!DISCLOSURE_FILTER_OPERATOR_OPTIONS.some(([key]) => key === row.operator)) {
      throw new Error(`condition_blocks[${index}].operator is invalid`);
    }
    for (const key of ["open_count", "close_count"] as const) {
      if (!Number.isInteger(row[key]) || Number(row[key]) < 0) {
        throw new Error(`condition_blocks[${index}].${key} must be a non-negative integer`);
      }
    }
    for (const key of ["not", "ignore_spaces", "clean_search"] as const) {
      if (typeof row[key] !== "boolean") {
        throw new Error(`condition_blocks[${index}].${key} must be a boolean`);
      }
    }
    if (typeof row.value !== "string") {
      throw new Error(`condition_blocks[${index}].value must be a string`);
    }
    if (!row.value.trim() && row.operator !== "exists" && row.operator !== "empty") {
      throw new Error(`condition_blocks[${index}].value is required`);
    }
    return {
      connector: connector as DisclosureFilterConnector,
      open_count: row.open_count as number,
      not: row.not as boolean,
      ignore_spaces: row.ignore_spaces as boolean,
      clean_search: row.clean_search as boolean,
      field: row.field as DisclosureFilterFieldKey,
      operator: row.operator as DisclosureFilterOperatorKey,
      value: row.value,
      close_count: row.close_count as number,
    };
  });
  const connectorScopes: Set<DisclosureFilterConnector>[] = [new Set()];
  blocks.forEach((block, index) => {
    if (index > 0) connectorScopes[connectorScopes.length - 1].add(block.connector);
    for (let count = 0; count < block.open_count; count += 1) connectorScopes.push(new Set());
    for (let count = 0; count < block.close_count; count += 1) {
      if (connectorScopes.length === 1) throw new Error("condition_blocks has an unmatched closing parenthesis");
      if (connectorScopes[connectorScopes.length - 1].size > 1) {
        throw new Error("mixed condition block connectors must be separated by parentheses");
      }
      connectorScopes.pop();
    }
  });
  if (connectorScopes.length > 1) throw new Error("condition_blocks has an unmatched opening parenthesis");
  if (connectorScopes[0].size > 1) {
    throw new Error("mixed condition block connectors must be separated by parentheses");
  }
  return blocks;
}

function countParens(value: string, paren: "(" | ")") {
  return [...String(value || "")].filter((char) => char === paren).length;
}

function mergeConditionsWithPreset(
  conditions: DisclosureConditionBlock[],
  preset: DisclosureConditionPreset,
): DisclosureConditionBlock[] {
  const incoming = normalizeDisclosureConditionBlocks(preset.condition_blocks).map((block) => ({ ...block }));
  if (!incoming.length) return conditions;
  const hasExisting = conditions.some((row) => row.value.trim() || row.operator === "exists" || row.operator === "empty");
  if (!hasExisting) {
    incoming[0].connector = "";
    return incoming;
  }
  incoming[0] = { ...incoming[0], connector: "AND", open_count: incoming[0].open_count + 1 };
  incoming[incoming.length - 1] = {
    ...incoming[incoming.length - 1],
    close_count: incoming[incoming.length - 1].close_count + 1,
  };
  return [...conditions, ...incoming];
}

function fieldLabel(field: DisclosureFilterFieldKey) {
  return DISCLOSURE_FILTER_FIELD_OPTIONS.find(([key]) => key === field)?.[1] || field;
}

function operatorLabel(operator: DisclosureFilterOperatorKey) {
  return DISCLOSURE_FILTER_OPERATOR_OPTIONS.find(([key]) => key === operator)?.[1] || operator;
}

const CONDITION_OPTION_TOGGLES = [
  ["not", "NOT"],
  ["ignore_spaces", "공백무시"],
  ["clean_search", "Clean"],
] as const;

type ConditionOptionKey = (typeof CONDITION_OPTION_TOGGLES)[number][0];

function ConditionOptionsPopover({
  condition,
  open,
  onOpenChange,
  onToggle,
}: {
  condition: DisclosureConditionBlock;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onToggle: (key: ConditionOptionKey, value: boolean) => void;
}) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);
  const activeCount = CONDITION_OPTION_TOGGLES.filter(([key]) => condition[key]).length;

  useEffect(() => {
    if (!open) {
      setCoords(null);
      return;
    }
    const rect = buttonRef.current?.getBoundingClientRect();
    if (rect) setCoords({ top: rect.bottom + 4, left: rect.left });

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (buttonRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      onOpenChange(false);
    };
    const handleScrollOrResize = () => onOpenChange(false);
    document.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("scroll", handleScrollOrResize, true);
    window.addEventListener("resize", handleScrollOrResize);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("scroll", handleScrollOrResize, true);
      window.removeEventListener("resize", handleScrollOrResize);
    };
  }, [open, onOpenChange]);

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => onOpenChange(!open)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label="조건 옵션"
        className={cn(
          "flex h-9 w-full items-center justify-center gap-1.5 rounded-md border px-2 text-xs font-bold",
          activeCount > 0
            ? "border-teal-200 bg-teal-50 text-teal-800 dark:border-teal-900/50 dark:bg-teal-900/30 dark:text-teal-300"
            : "border-slate-200 bg-white text-slate-500 dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-300",
        )}
      >
        옵션
        {activeCount > 0 && (
          <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-teal-600 px-1 text-[10px] font-bold text-white dark:bg-teal-500">
            {activeCount}
          </span>
        )}
      </button>
      {open && coords && createPortal(
        <div
          ref={panelRef}
          style={{ top: coords.top, left: coords.left }}
          className="fixed z-50 w-36 rounded-lg border border-slate-200 bg-white p-1 shadow-lg dark:border-[#30363d] dark:bg-[#161b22]"
        >
          {CONDITION_OPTION_TOGGLES.map(([key, label]) => (
            <label
              key={key}
              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-[#21262d]"
            >
              <input type="checkbox" checked={condition[key]} onChange={(event) => onToggle(key, event.target.checked)} />
              {label}
            </label>
          ))}
        </div>,
        document.body,
      )}
    </div>
  );
}

function AddFilterPopover({
  presets,
  onSelect,
}: {
  presets: DisclosureConditionPreset[];
  onSelect: (preset: DisclosureConditionPreset) => void;
}) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);

  useEffect(() => {
    if (!open) {
      setCoords(null);
      return;
    }
    const rect = buttonRef.current?.getBoundingClientRect();
    if (rect) setCoords({ top: rect.bottom + 4, left: rect.left });

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (buttonRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    const handleScrollOrResize = () => setOpen(false);
    document.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("scroll", handleScrollOrResize, true);
    window.addEventListener("resize", handleScrollOrResize);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("scroll", handleScrollOrResize, true);
      window.removeEventListener("resize", handleScrollOrResize);
    };
  }, [open]);

  return (
    <div className="relative inline-block">
      <Button ref={buttonRef} variant="outline" onClick={() => setOpen((value) => !value)} disabled={!presets.length}>
        <ListPlus className="mr-2 h-4 w-4" />
        필터 추가
      </Button>
      {open && coords && createPortal(
        <div
          ref={panelRef}
          style={{ top: coords.top, left: coords.left }}
          className="fixed z-50 max-h-64 w-56 overflow-y-auto rounded-lg border border-slate-200 bg-white p-1 shadow-lg dark:border-[#30363d] dark:bg-[#161b22]"
        >
          {presets.length ? presets.map((preset) => (
            <button
              key={preset.name}
              type="button"
              onClick={() => {
                onSelect(preset);
                setOpen(false);
              }}
              className="block w-full truncate rounded-md px-2 py-1.5 text-left text-xs font-bold text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-[#21262d]"
            >
              {preset.name}
            </button>
          )) : (
            <p className="px-2 py-1.5 text-xs font-medium text-slate-400 dark:text-slate-500">저장된 필터가 없습니다.</p>
          )}
        </div>,
        document.body,
      )}
    </div>
  );
}

export function DisclosureConditionFilterCard({
  conditions,
  onConditionsChange,
  presets = [],
  selectedPreset,
  onSelectedPresetChange,
  onLoadPreset,
  onLoadPresetFromJson,
  onSavePreset,
  onDeletePreset,
}: DisclosureConditionFilterCardProps) {
  const [openOptionsIndex, setOpenOptionsIndex] = useState<number | null>(null);
  const [, setHistoryTick] = useState(0);
  const history = useRef<{ past: DisclosureConditionBlock[][]; future: DisclosureConditionBlock[][] }>({
    past: [],
    future: [],
  });
  const lastSelfSetRef = useRef<DisclosureConditionBlock[] | null>(null);
  const isFirstConditionsEffect = useRef(true);

  const applyConditionsChange = (next: DisclosureConditionBlock[]) => {
    history.current.past.push(conditions);
    history.current.future = [];
    lastSelfSetRef.current = next;
    setHistoryTick((tick) => tick + 1);
    onConditionsChange(next);
  };

  const undo = () => {
    if (!history.current.past.length) return;
    const previous = history.current.past.pop()!;
    history.current.future.push(conditions);
    lastSelfSetRef.current = previous;
    setHistoryTick((tick) => tick + 1);
    onConditionsChange(previous);
  };

  const redo = () => {
    if (!history.current.future.length) return;
    const next = history.current.future.pop()!;
    history.current.past.push(conditions);
    lastSelfSetRef.current = next;
    setHistoryTick((tick) => tick + 1);
    onConditionsChange(next);
  };

  const clear = () => {
    if (isEmptyDisclosureConditionBlocks(conditions)) return;
    setOpenOptionsIndex(null);
    applyConditionsChange([makeEmptyDisclosureCondition()]);
  };

  useEffect(() => {
    if (isFirstConditionsEffect.current) {
      isFirstConditionsEffect.current = false;
      return;
    }
    if (conditions === lastSelfSetRef.current) return;
    history.current = { past: [], future: [] };
    setHistoryTick((tick) => tick + 1);
  }, [conditions]);

  const updateCondition = (index: number, patch: Partial<DisclosureConditionBlock>) => {
    const next = conditions.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row);
    if (next[0]) next[0].connector = "";
    applyConditionsChange(next);
  };

  const removeCondition = (index: number) => {
    const next = conditions.filter((_, rowIndex) => rowIndex !== index);
    setOpenOptionsIndex(null);
    if (!next.length) {
      applyConditionsChange([makeEmptyDisclosureCondition()]);
      return;
    }
    next[0].connector = "";
    applyConditionsChange(next);
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
          <Label className="dark:text-slate-300">조건검색 필터</Label>
          <div className={cn(
            "grid gap-2",
            onLoadPresetFromJson
              ? "md:grid-cols-[minmax(150px,1fr)_auto_auto_auto]"
              : "md:grid-cols-[minmax(150px,1fr)_auto_auto]",
          )}>
            <select
              value={selectedPreset}
              onChange={(event) => {
                const nextPreset = event.target.value;
                onSelectedPresetChange(nextPreset);
                if (nextPreset) onLoadPreset(nextPreset);
              }}
              className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm font-semibold dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
              aria-label="조건검색 필터 선택"
            >
              <option value="">필터 선택</option>
              {presets.map((preset) => (
                <option key={preset.name} value={preset.name}>
                  {preset.name}
                </option>
              ))}
            </select>
            {onLoadPresetFromJson && <Button variant="outline" onClick={onLoadPresetFromJson}><Upload className="mr-2 h-4 w-4" />불러오기</Button>}
            <Button onClick={onSavePreset}><Save className="mr-2 h-4 w-4" />저장</Button>
            <Button variant="outline" onClick={onDeletePreset} disabled={!selectedPreset}><Trash2 className="mr-2 h-4 w-4" />삭제</Button>
          </div>
        </div>

        <div className="grid gap-2">
          <Label className="dark:text-slate-300">조건 블록</Label>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => applyConditionsChange([...conditions, makeEmptyDisclosureCondition(conditions.length ? "AND" : "")])}>
                <Plus className="mr-2 h-4 w-4" />
                조건 추가
              </Button>
              <AddFilterPopover
                presets={presets}
                onSelect={(preset) => applyConditionsChange(mergeConditionsWithPreset(conditions, preset))}
              />
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="icon"
                aria-label="실행 취소"
                onClick={undo}
                disabled={!history.current.past.length}
              >
                <Undo2 className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                aria-label="지우기"
                onClick={clear}
                disabled={isEmptyDisclosureConditionBlocks(conditions)}
              >
                <Eraser className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                aria-label="다시 실행"
                onClick={redo}
                disabled={!history.current.future.length}
              >
                <Redo2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
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
              <div key={index} className="grid min-w-[860px] items-center gap-2 rounded-lg border border-slate-200 bg-white/80 p-2 dark:bg-[#161b22] dark:border-[#30363d] lg:grid-cols-[96px_minmax(0,1fr)_58px]">
                <select
                  value={condition.connector}
                  disabled={index === 0}
                  onChange={(event) => updateCondition(index, { connector: event.target.value as DisclosureFilterConnector })}
                  className="h-9 rounded-md border border-slate-200 bg-white px-2 text-xs font-bold text-slate-500 disabled:text-teal-700 disabled:opacity-100 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-300 dark:disabled:text-teal-300"
                  aria-label="연결 조건"
                >
                  <option value="">START</option>
                  <option value="AND">AND</option>
                  <option value="XOR">XOR</option>
                  <option value="OR">OR</option>
                </select>
                <div className="grid min-w-0 items-center gap-2 lg:grid-cols-[36px_100px_minmax(84px,.45fr)_minmax(112px,.55fr)_minmax(240px,3fr)_36px]">
                  <Input value={"(".repeat(condition.open_count)} onChange={(event) => updateCondition(index, { open_count: countParens(event.target.value, "(") })} aria-label="그룹 시작" className={cn("h-9 text-center font-bold dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200", condition.open_count ? "bg-cyan-50 border-cyan-300 dark:bg-cyan-900/20" : "")} />
                  <ConditionOptionsPopover
                    condition={condition}
                    open={openOptionsIndex === index}
                    onOpenChange={(nextOpen) => setOpenOptionsIndex(nextOpen ? index : null)}
                    onToggle={(key, value) => updateCondition(index, { [key]: value })}
                  />
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
        </div>
      </CardContent>
    </Card>
  );
}
