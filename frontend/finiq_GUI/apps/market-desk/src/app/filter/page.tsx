"use client"

import { useCallback, useEffect, useMemo, useState } from "react";
import { Play, Plus, Save, Trash2, Loader2 } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Label } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { cn } from "@finiq/ui/utils";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobStreaming } from "@/hooks/useJobStreaming";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";

const TRANSFER_STORAGE_KEY = "finiq.kind.filteredDisclosures";
const PAGE_SIZE = 20;

const FIELD_OPTIONS = [
  ["title", "제목"],
  ["company_name", "회사명"],
  ["submitter", "제출인"],
  ["market", "시장"],
  ["disclosed_date", "공시일"],
  ["acpt_no", "접수번호"],
  ["company_id", "회사코드"],
] as const;

const OPERATOR_OPTIONS = [
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

type FieldKey = (typeof FIELD_OPTIONS)[number][0];
type OperatorKey = (typeof OPERATOR_OPTIONS)[number][0];
type Connector = "" | "AND" | "OR";

type ConditionBlock = {
  connector: Connector;
  open_count: number;
  not: boolean;
  ignore_spaces: boolean;
  clean_search: boolean;
  field: FieldKey;
  operator: OperatorKey;
  value: string;
  close_count: number;
};

type Preset = {
  name: string;
  condition_blocks: ConditionBlock[];
};

type FilterResult = {
  summary?: {
    matched_disclosures?: number;
    returned_disclosures?: number;
    unique_acpt_numbers?: number;
  };
  disclosures?: any[];
  html_download_transfer?: {
    path?: string;
    acpt_numbers?: number;
  };
};

function makeEmptyCondition(connector: Connector = ""): ConditionBlock {
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

function countParens(value: string, paren: "(" | ")") {
  return [...String(value || "")].filter((char) => char === paren).length;
}

function normalizeConditionBlocks(value: unknown): ConditionBlock[] {
  if (!Array.isArray(value)) return [makeEmptyCondition()];
  const blocks = value.map((item, index) => {
    const row = item as Partial<ConditionBlock>;
    const connector = String(row.connector || "AND").toUpperCase();
    const field = FIELD_OPTIONS.some(([key]) => key === row.field) ? row.field as FieldKey : "title";
    const operator = OPERATOR_OPTIONS.some(([key]) => key === row.operator) ? row.operator as OperatorKey : "contains";
    return {
      ...makeEmptyCondition(index === 0 || (connector !== "AND" && connector !== "OR") ? "" : connector as Connector),
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
  return blocks.length ? blocks : [makeEmptyCondition()];
}

function fieldLabel(field: FieldKey) {
  return FIELD_OPTIONS.find(([key]) => key === field)?.[1] || field;
}

function operatorLabel(operator: OperatorKey) {
  return OPERATOR_OPTIONS.find(([key]) => key === operator)?.[1] || operator;
}

function getKindDisclosureUrl(acptNo: string) {
  return `https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno=${encodeURIComponent(acptNo)}&docno=&viewerhost=&viewerport=`;
}

export default function FilterPage() {
  const {
    output_root: rootDirectory,
    html_transfer_directory: htmlTransferPath,
    condition_presets: presets,
    fetchSettings,
    saveSetting,
  } = useSettingsStore();

  const { status, setStatus, isErrorStatus, setIsErrorStatus, isStreaming, streamJob, abortJob, appendStatus } = useJobStreaming();

  const [loading, setLoading] = useState(true);
  const [conditions, setConditions] = useState<ConditionBlock[]>([makeEmptyCondition()]);
  const [presetName, setPresetName] = useState("");
  const [selectedPreset, setSelectedPreset] = useState("");
  const [limitUnlimited, setLimitUnlimited] = useState(true);
  const [limit, setLimit] = useState("1000");
  const [filterWorkers, setFilterWorkers] = useState("8");
  const [progressInterval, setProgressInterval] = useState("100");
  const [result, setResult] = useState<FilterResult | null>(null);
  const [pageIndex, setPageIndex] = useState(0);

  useEffect(() => {
    fetchSettings().finally(() => {
      setLoading(false);
      setStatus("공시 소스 폴더를 불러왔습니다.");
    });
  }, [fetchSettings, setStatus]);

  const updateCondition = (index: number, patch: Partial<ConditionBlock>) => {
    setConditions((previous) => {
      const next = previous.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row);
      if (next[0]) next[0].connector = "";
      return next;
    });
  };

  const removeCondition = (index: number) => {
    setConditions((previous) => {
      const next = previous.filter((_, rowIndex) => rowIndex !== index);
      if (!next.length) return [makeEmptyCondition()];
      next[0].connector = "";
      return next;
    });
  };

  const conditionPreview = useMemo(() => {
    return conditions.filter((row) => row.value.trim() || row.operator === "exists" || row.operator === "empty");
  }, [conditions]);

  const pageCount = Math.max(1, Math.ceil((result?.disclosures?.length || 0) / PAGE_SIZE));
  const pageRows = useMemo(() => {
    const rows = result?.disclosures || [];
    const safeIndex = Math.min(Math.max(pageIndex, 0), pageCount - 1);
    return rows.slice(safeIndex * PAGE_SIZE, (safeIndex + 1) * PAGE_SIZE);
  }, [pageCount, pageIndex, result]);

  const companyCount = useMemo(() => {
    const rows = result?.disclosures || [];
    return new Set(rows.map((item) => item.company_key || item.company_name).filter(Boolean)).size;
  }, [result]);

  const jsonPreview = useMemo(() => {
    if (!result) return "결과 없음";
    return JSON.stringify({
      ...result,
      summary: {
        ...(result.summary || {}),
        json_preview: true,
        preview_page: pageIndex + 1,
        preview_page_size: PAGE_SIZE,
        preview_disclosures: pageRows.length,
      },
      disclosures: pageRows,
    }, null, 2);
  }, [pageIndex, pageRows, result]);

  const buildPayload = () => ({
    root_directory: rootDirectory,
    html_transfer_path: htmlTransferPath,
    filter_blocks: normalizeConditionBlocks(conditions),
    title_expression: "",
    limit: limitUnlimited ? null : Number(limit || 1000),
    limit_unlimited: limitUnlimited,
    return_limit: Number(limit || 1000),
    include_html_download_acpt_numbers: true,
    filter_workers: Number(filterWorkers || 8),
    progress_interval: Number(progressInterval || 100),
  });

  const handleFilter = async () => {
    if (!rootDirectory?.trim()) {
      setStatus("입력 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }

    setResult(null);
    setPageIndex(0);

    await streamJob("/api/disclosures/filter", buildPayload(), (payload: FilterResult) => {
      setResult(payload);
      const transferPath = String(payload.html_download_transfer?.path || "").trim();
      if (transferPath) {
        sessionStorage.setItem(TRANSFER_STORAGE_KEY, JSON.stringify({
          source_json_path: transferPath,
          acpt_numbers: Number(payload.html_download_transfer?.acpt_numbers || 0),
        }));
      } else {
        sessionStorage.removeItem(TRANSFER_STORAGE_KEY);
      }
      const saved = transferPath ? `접수번호 ${payload.html_download_transfer?.acpt_numbers || 0}개를 저장했습니다: ${transferPath}` : "저장 파일을 만들지 못했습니다.";
      appendStatus(`매칭 ${payload.summary?.matched_disclosures || 0}건 중 ${payload.summary?.returned_disclosures || 0}건을 표시했고, ${saved}`, !transferPath);
    });
  };

  const savePreset = () => {
    const name = presetName.trim();
    if (!name) {
      setStatus("저장할 프리셋 이름을 입력하세요.");
      setIsErrorStatus(true);
      return;
    }
    const next = (presets || []).filter((item: any) => item.name !== name);
    next.push({ name, condition_blocks: normalizeConditionBlocks(conditions) });
    next.sort((a: any, b: any) => a.name.localeCompare(b.name, "ko"));
    
    saveSetting("condition_presets", next);
    setSelectedPreset(name);
    setStatus(`조건검색 프리셋을 저장했습니다: ${name}`);
    setIsErrorStatus(false);
  };

  const loadPreset = () => {
    const preset = (presets || []).find((item: any) => item.name === selectedPreset);
    if (!preset) {
      setStatus("선택한 프리셋을 찾을 수 없습니다.");
      setIsErrorStatus(true);
      return;
    }
    setConditions(normalizeConditionBlocks(preset.condition_blocks));
    setPresetName(preset.name);
    setStatus(`조건검색 프리셋을 불러왔습니다: ${preset.name}`);
    setIsErrorStatus(false);
  };

  const deletePreset = () => {
    if (!selectedPreset) return;
    const next = (presets || []).filter((item: any) => item.name !== selectedPreset);
    saveSetting("condition_presets", next);
    setPresetName((value) => value === selectedPreset ? "" : value);
    setSelectedPreset("");
    setStatus(`조건검색 프리셋을 삭제했습니다: ${selectedPreset}`);
    setIsErrorStatus(false);
  };

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  return (
    <WorkflowPageShell workflowId="disclosure-build">
      <div className="grid lg:grid-cols-[minmax(0,2fr)_minmax(260px,0.85fr)] gap-6">
        <section className="min-w-0 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Source</p>
          <CardTitle className="dark:text-white">분류 JSON</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-2">
            <Label className="dark:text-slate-300">입력 경로</Label>
            <PathPickerInput 
              mode="folder"
              value={rootDirectory || ""}
              onChange={(val) => saveSetting("output_root", val)}
              onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
            />
          </div>
          <div className="grid gap-2">
            <Label className="dark:text-slate-300">저장 경로</Label>
            <PathPickerInput 
              mode="folder"
              value={htmlTransferPath || ""}
              onChange={(val) => saveSetting("html_transfer_directory", val)}
              onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
            />
          </div>
        </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Filters</p>
          <CardTitle className="dark:text-white">공시 조건</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-2">
            <Label className="dark:text-slate-300">조건검색 프리셋</Label>
            <div className="grid gap-2 md:grid-cols-[minmax(180px,1.2fr)_minmax(180px,1fr)_auto_auto_auto]">
              <select
                value={selectedPreset}
                onChange={(event) => {
                  setSelectedPreset(event.target.value);
                  setPresetName(event.target.value);
                }}
                className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm font-semibold dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                aria-label="조건검색 프리셋 선택"
              >
                <option value="">프리셋 선택</option>
                {(presets || []).map((preset: any) => (
                  <option key={preset.name} value={preset.name}>{preset.name}</option>
                ))}
              </select>
              <Input value={presetName} onChange={(event) => setPresetName(event.target.value)} onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  savePreset();
                }
              }} placeholder="프리셋 이름" className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
              <Button variant="outline" onClick={loadPreset} disabled={!selectedPreset}>불러오기</Button>
              <Button onClick={savePreset}><Save className="mr-2 h-4 w-4" />저장</Button>
              <Button variant="outline" onClick={deletePreset} disabled={!selectedPreset}><Trash2 className="mr-2 h-4 w-4" />삭제</Button>
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
                    onChange={(event) => updateCondition(index, { connector: event.target.value as Connector })}
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
                    <select value={condition.field} onChange={(event) => updateCondition(index, { field: event.target.value as FieldKey })} aria-label="필드" className="h-9 rounded-md border border-slate-200 bg-white px-2 text-xs font-bold text-slate-500 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-300">
                      {FIELD_OPTIONS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                    </select>
                    <select value={condition.operator} onChange={(event) => updateCondition(index, { operator: event.target.value as OperatorKey })} aria-label="연산자" className="h-9 rounded-md border border-slate-200 bg-white px-2 text-xs font-bold text-slate-500 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-300">
                      {OPERATOR_OPTIONS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                    </select>
                    <Input value={condition.value} onChange={(event) => updateCondition(index, { value: event.target.value })} placeholder="값" className="h-9 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                    <Input value={")".repeat(condition.close_count)} onChange={(event) => updateCondition(index, { close_count: countParens(event.target.value, ")") })} aria-label="그룹 끝" className={cn("h-9 text-center font-bold dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200", condition.close_count ? "bg-cyan-50 border-cyan-300 dark:bg-cyan-900/20" : "")} />
                  </div>
                  <Button variant="ghost" onClick={() => removeCondition(index)} className="h-8 px-2 text-xs text-slate-500 hover:text-red-600 dark:text-slate-400 dark:hover:bg-red-900/20 dark:hover:text-red-300">삭제</Button>
                </div>
              ))}
            </div>

            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => setConditions((previous) => [...previous, makeEmptyCondition(previous.length ? "AND" : "")])}>
                <Plus className="mr-2 h-4 w-4" />
                조건 추가
              </Button>
              <Button
                variant="outline"
                onClick={() => setConditions((previous) => [
                  ...previous,
                  {
                    ...makeEmptyCondition(previous.length ? "OR" : ""),
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

          <div className="grid gap-4 md:grid-cols-[minmax(270px,1.35fr)_minmax(120px,.75fr)_minmax(130px,.8fr)]">
            <Label className="grid gap-2 dark:text-slate-300">
              최대 반환
              <div className="flex min-h-9 items-center gap-3">
                <label className="flex h-9 shrink-0 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-xs font-bold text-slate-500 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-300">
                  <input type="checkbox" checked={limitUnlimited} onChange={(event) => setLimitUnlimited(event.target.checked)} />
                  제한 없음
                </label>
                <Input type="number" min="1" max="10000" step="1" value={limit} disabled={limitUnlimited} onChange={(event) => setLimit(event.target.value)} className="h-9 min-w-0 max-w-[120px] dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 disabled:opacity-50" />
              </div>
            </Label>
            <Label className="grid gap-2 dark:text-slate-300">
              파싱 worker 수
              <Input type="number" min="1" max="32" step="1" value={filterWorkers} onChange={(event) => setFilterWorkers(event.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
            </Label>
            <Label className="grid gap-2 dark:text-slate-300">
              진행 표시 간격
              <Input type="number" min="1" max="10000" step="1" value={progressInterval} onChange={(event) => setProgressInterval(event.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
            </Label>
          </div>
          </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Result</p>
          <CardTitle className="dark:text-white">필터 결과</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["매칭", result?.summary?.matched_disclosures || 0],
              ["반환", result?.summary?.returned_disclosures || 0],
              ["회사", companyCount],
              ["접수번호", result?.summary?.unique_acpt_numbers || 0],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:bg-[#0d1117] dark:border-[#30363d]">
                <span className="text-xs font-bold text-slate-500 dark:text-slate-400">{label}</span>
                <strong className="mt-1 block text-2xl font-bold text-slate-950 dark:text-slate-100">{Number(value).toLocaleString("ko-KR")}</strong>
              </div>
            ))}
          </div>
          <div className="mb-2 flex items-center justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setPageIndex((value) => Math.max(0, value - 1))} disabled={!result?.disclosures?.length || pageIndex <= 0}>이전</Button>
            <span className="min-w-[72px] text-center text-sm font-bold text-slate-500 dark:text-slate-400">{result?.disclosures?.length ? `${Math.min(pageIndex + 1, pageCount)} / ${pageCount}` : "0 / 0"}</span>
            <Button variant="outline" size="sm" onClick={() => setPageIndex((value) => Math.min(pageCount - 1, value + 1))} disabled={!result?.disclosures?.length || pageIndex >= pageCount - 1}>다음</Button>
          </div>
          <div className="h-[460px] overflow-auto rounded-lg border border-slate-200 bg-white dark:bg-[#0d1117] dark:border-[#30363d]">
            <table className="w-full border-collapse text-sm">
              <thead className="sticky top-0 bg-white text-left text-slate-500 dark:bg-[#161b22] dark:text-slate-400">
                <tr>
                  <th className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">공시일</th>
                  <th className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">회사</th>
                  <th className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">시장</th>
                  <th className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">제목</th>
                  <th className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">제출인</th>
                  <th className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">접수번호</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
                {pageRows.length ? pageRows.map((row, index) => {
                  const acptNo = String(row.acpt_no || row.acptno || "");
                  const title = row.title || "";
                  return (
                    <tr key={`${acptNo}-${index}`} className="hover:bg-slate-50 dark:hover:bg-[#161b22] dark:text-slate-300">
                      <td className="px-3 py-2 whitespace-nowrap">{String(row.disclosed_at || row.disclosed_date || "").split(" ")[0]}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{row.company_name || ""}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{row.market || ""}</td>
                      <td className="px-3 py-2 min-w-[320px]">
                        {acptNo ? (
                          <a className="font-bold text-teal-700 hover:underline dark:text-teal-300" href={getKindDisclosureUrl(acptNo)} target="_blank" rel="noreferrer">{title}</a>
                        ) : title}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">{row.submitter || ""}</td>
                      <td className="px-3 py-2 whitespace-nowrap font-mono text-xs">{acptNo}</td>
                    </tr>
                  );
                }) : (
                  <tr>
                    <td className="px-3 py-10 text-center text-slate-500 dark:text-slate-400" colSpan={6}>필터 결과가 없습니다.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <pre className="mt-4 max-h-[420px] overflow-auto rounded-lg border border-slate-200 bg-slate-950 p-4 font-mono text-xs leading-relaxed text-blue-100 dark:border-[#30363d]">{jsonPreview}</pre>
        </CardContent>
          </Card>
        </section>

        <section className="space-y-6">
          <Card className="sticky top-6 dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col gap-2">
                <Button onClick={handleFilter} disabled={isStreaming} className="w-full">
                  {isStreaming ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
              </div>
              <div className="space-y-2">
                <Label className="dark:text-slate-300">작업 상태</Label>
                <JobStatusLogger 
                  status={status} 
                  isErrorStatus={isErrorStatus} 
                  isCancellable={isStreaming} 
                  onCancel={abortJob} 
                />
              </div>
            </CardContent>
          </Card>
        </section>
      </div>
    </WorkflowPageShell>
  );
}
