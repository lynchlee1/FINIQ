"use client"

import { useCallback, useEffect, useMemo, useState } from "react";
import { Play, Loader2, RefreshCw } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Label } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { cn } from "@finiq/ui/utils";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { JobStatusLogger, PageLoadingSpinner, ActionDock } from "@finiq/web-app/status";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobStreaming } from "@/hooks/useJobStreaming";
import { UI_TEXT } from "@/config/uiText";
import { formatInteger } from "@/lib/format";
import { apiPost } from "@/api/client";
import { pickPath } from "@/lib/fileDialog";
import {
  DisclosureConditionFilterCard,
  makeEmptyDisclosureCondition,
  normalizeDisclosureConditionBlocks,
  type DisclosureConditionBlock,
  type DisclosureConditionPresetPayload,
} from "@/components/disclosures/DisclosureConditionFilterCard";

const TRANSFER_STORAGE_KEY = "finiq.kind.filteredDisclosures";
const PAGE_SIZE = 20;

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
  const [conditions, setConditions] = useState<DisclosureConditionBlock[]>([makeEmptyDisclosureCondition()]);
  const [presetName, setPresetName] = useState("");
  const [selectedPreset, setSelectedPreset] = useState("");
  const [filterPresetPath, setFilterPresetPath] = useState("");
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

  const applyPreset = useCallback((preset: DisclosureConditionPresetPayload, statusMessage: string) => {
    setConditions(normalizeDisclosureConditionBlocks(preset.condition_blocks));
    if (preset.name) setPresetName(preset.name);
    setStatus(statusMessage);
    setIsErrorStatus(false);
  }, [setIsErrorStatus, setStatus]);

  const pageCount = Math.max(1, Math.ceil((result?.disclosures?.length || 0) / PAGE_SIZE));
  const pageRows = useMemo(() => {
    const rows = result?.disclosures || [];
    const safeIndex = Math.min(Math.max(pageIndex, 0), pageCount - 1);
    return rows.slice(safeIndex * PAGE_SIZE, (safeIndex + 1) * PAGE_SIZE);
  }, [pageCount, pageIndex, result]);

  const buildPayload = () => ({
    root_directory: rootDirectory,
    html_transfer_path: htmlTransferPath,
    filter_blocks: normalizeDisclosureConditionBlocks(conditions),
    title_expression: "",
    limit: limitUnlimited ? null : Number(limit || 1000),
    limit_unlimited: limitUnlimited,
    return_limit: Number(limit || 1000),
    include_html_download_acpt_numbers: true,
    filter_workers: Number(filterWorkers || 8),
    progress_interval: Number(progressInterval || 100),
  });

  const handleRefresh = async () => {
    const config = await fetchSettings();
    if (!config) {
      setStatus("공시 소스 폴더 새로고침에 실패했습니다.");
      setIsErrorStatus(true);
      return;
    }
    setStatus("공시 소스 폴더를 새로고침했습니다.");
    setIsErrorStatus(false);
  };

  const handleFilter = async () => {
    if (!rootDirectory?.trim()) {
      setStatus("입력 데이터 경로를 선택하세요.");
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
      const saved = transferPath ? `접수번호 ${formatInteger(payload.html_download_transfer?.acpt_numbers)}개를 저장했습니다: ${transferPath}` : "저장 파일을 만들지 못했습니다.";
      appendStatus(`매칭 ${formatInteger(payload.summary?.matched_disclosures)}건 중 ${formatInteger(payload.summary?.returned_disclosures)}건을 표시했고, ${saved}`, !transferPath);
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
    next.push({ name, condition_blocks: normalizeDisclosureConditionBlocks(conditions) });
    next.sort((a: any, b: any) => a.name.localeCompare(b.name, "ko"));
    
    saveSetting("condition_presets", next);
    setSelectedPreset(name);
    setStatus(`조건검색 프리셋을 저장했습니다: ${name}`);
    setIsErrorStatus(false);
  };

  const loadPreset = (name: string) => {
    const preset = (presets || []).find((item: any) => item.name === name);
    if (!preset) {
      setStatus("선택한 프리셋을 찾을 수 없습니다.");
      setIsErrorStatus(true);
      return;
    }
    applyPreset(preset, `조건검색 프리셋을 불러왔습니다: ${preset.name}`);
  };

  const renamePreset = () => {
    if (!selectedPreset) return;
    const name = presetName.trim();
    if (!name) {
      setStatus("수정할 프리셋 이름을 입력하세요.");
      setIsErrorStatus(true);
      return;
    }
    const preset = (presets || []).find((item: any) => item.name === selectedPreset);
    if (!preset) {
      setStatus("선택한 프리셋을 찾을 수 없습니다.");
      setIsErrorStatus(true);
      return;
    }
    if (name !== selectedPreset && (presets || []).some((item: any) => item.name === name)) {
      setStatus(`이미 같은 이름의 프리셋이 있습니다: ${name}`);
      setIsErrorStatus(true);
      return;
    }
    const next = (presets || []).map((item: any) => item.name === selectedPreset ? { ...item, name } : item);
    next.sort((a: any, b: any) => a.name.localeCompare(b.name, "ko"));

    saveSetting("condition_presets", next);
    setSelectedPreset(name);
    setPresetName(name);
    setStatus(`조건검색 프리셋 이름을 수정했습니다: ${selectedPreset} -> ${name}`);
    setIsErrorStatus(false);
  };

  const loadFilterPresetFromJson = async () => {
    try {
      const sourceJsonPath = await pickPath({
        mode: "file",
        title: "필터 결과 JSON 선택",
        defaultPath: filterPresetPath,
      });
      if (!sourceJsonPath) return;
      setFilterPresetPath(sourceJsonPath);
      const preset = await apiPost<DisclosureConditionPresetPayload>("/api/disclosures/filter/preset", {
        source_json_path: sourceJsonPath,
      });
      setSelectedPreset("");
      applyPreset(preset, `필터 결과 JSON에서 조건을 불러왔습니다: ${preset.source_json_path || sourceJsonPath}`);
    } catch (err: any) {
      setStatus(err.message || "필터 결과 JSON을 불러오지 못했습니다.");
      setIsErrorStatus(true);
    }
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
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
          <CardTitle className="dark:text-white">데이터 경로</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-2">
            <Label className="dark:text-slate-300">입력 데이터 경로</Label>
            <PathPickerInput 
              mode="folder"
              value={rootDirectory || ""}
              onChange={(val) => saveSetting("output_root", val)}
              onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
            />
          </div>
          <div className="grid gap-2">
            <Label className="dark:text-slate-300">결과 데이터 경로</Label>
            <PathPickerInput 
              mode="folder"
              value={htmlTransferPath || ""}
              onChange={(val) => saveSetting("html_transfer_directory", val)}
              onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
            />
          </div>
        </CardContent>
          </Card>

          <DisclosureConditionFilterCard
            conditions={conditions}
            onConditionsChange={setConditions}
            presets={presets || []}
            presetName={presetName}
            selectedPreset={selectedPreset}
            onPresetNameChange={setPresetName}
            onSelectedPresetChange={setSelectedPreset}
            onLoadPreset={loadPreset}
            onLoadPresetFromJson={loadFilterPresetFromJson}
            onSavePreset={savePreset}
            onRenamePreset={renamePreset}
            onDeletePreset={deletePreset}
          />

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <Button variant="outline" onClick={handleRefresh} disabled={isStreaming} className="w-full">
                  <RefreshCw className={cn("mr-2 h-4 w-4", isStreaming ? "animate-spin" : "")} />
                  소스 새로고침
                </Button>
                <Button onClick={handleFilter} disabled={isStreaming} className="w-full">
                  {isStreaming ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                <Button variant="outline" onClick={abortJob} disabled={!isStreaming} className="w-full">
                  {UI_TEXT.actions.cancelJob}
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Result</p>
          <CardTitle className="dark:text-white">필터 결과</CardTitle>
        </CardHeader>
        <CardContent>
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
        </CardContent>
          </Card>

        </section>

        <ActionDock
          activityActive={isStreaming}
          activityContent={
            <JobStatusLogger 
              status={status} 
              isErrorStatus={isErrorStatus} 
              isCancellable={isStreaming} 
              onCancel={abortJob} 
            />
          }
          notificationActive={isErrorStatus}
          notificationContent={<div className={isErrorStatus ? "whitespace-pre-wrap text-sm text-red-600 dark:text-red-300" : "text-sm text-slate-500 dark:text-slate-400"}>{isErrorStatus ? status : "알림 없음"}</div>}
          settingsTitle="시스템 설정"
          settingsContent={
            <div className="space-y-5">
              <div className="space-y-3">
                <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">결과 범위</p>
                </div>
              <div className="space-y-2">
                <Label className="dark:text-slate-300">최대 반환</Label>
                <label className="flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-xs font-bold text-slate-500 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-300">
                  <input type="checkbox" checked={limitUnlimited} onChange={(event) => setLimitUnlimited(event.target.checked)} />
                  제한 없음
                </label>
                <Input type="number" min="1" max="10000" step="1" value={limit} disabled={limitUnlimited} onChange={(event) => setLimit(event.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 disabled:opacity-50" />
              </div>
              </div>
              <div className="space-y-3">
                <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">실행 옵션</p>
                </div>
              <Label className="grid gap-2 dark:text-slate-300">
                파싱 worker 수
                <Input type="number" min="1" max="32" step="1" value={filterWorkers} onChange={(event) => setFilterWorkers(event.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
              </Label>
              <Label className="grid gap-2 dark:text-slate-300">
                진행 표시 간격
                <Input type="number" min="1" max="10000" step="1" value={progressInterval} onChange={(event) => setProgressInterval(event.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
              </Label>
              </div>
            </div>
          }
        />
      </div>
    </WorkflowPageShell>
  );
}
