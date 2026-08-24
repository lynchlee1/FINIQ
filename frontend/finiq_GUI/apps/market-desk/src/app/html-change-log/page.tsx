"use client"

import { useState, useEffect, useMemo, useRef } from "react";
import { Loader2, FileSpreadsheet } from "lucide-react";
import { Button, Label, Checkbox } from "@finiq/ui";
import { JobStatusLogger, PageLoadingSpinner, ActionDock } from "@finiq/web-app/status";
import { useSettingsStore } from "@/store/useSettingsStore";
import { ChangeLogSidebar } from "@/components/html-change-log/ChangeLogSidebar";
import { ChangeLogMatrix } from "@/components/html-change-log/ChangeLogMatrix";
import { ChangeLogSettings } from "@/components/html-change-log/ChangeLogSettings";
import { getChangedFields } from "@/utils/matrixUtils";
import {
  HtmlSearchInput,
  HtmlWorkflowForm,
  HtmlWorkflowCard,
  HtmlWorkflowPage,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import { DATA_PATH_LABELS } from "@/components/data-path/DataPathCard";
import { formatInteger } from "@/lib/format";
import type { DisclosureConditionPreset } from "@/components/disclosures/DisclosureConditionFilterCard";
import { listDisclosureConditionPresets } from "@/lib/disclosureConditionPresets";

const presetIdentity = (preset: DisclosureConditionPreset) => (
  preset.id || (preset.parent_mode ? `${preset.parent_mode}/${preset.mode}` : preset.mode)
);

const presetLabel = (preset: DisclosureConditionPreset) => (
  preset.parent_mode ? `${preset.parent_mode} › ${preset.mode}` : preset.mode
);

const HTML_CHANGE_LOG_RELATED_ROUTE = "/html-bond-summary";

export default function HtmlChangeLogPage() {
  const [loading, setLoading] = useState(true);
  const [isFetching, setIsFetching] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [isErrorStatus, setIsErrorStatus] = useState(false);

  const [changeLog, setChangeLog] = useState<any>(null);
  const [selectedFamilyId, setSelectedFamilyId] = useState<string>("");
  const [familyDetails, setFamilyDetails] = useState<Record<string, any>>({});

  const {
    html_parse_output_directory: outputPath,
    html_parse_mode: storedMode,
    output_root: dataRoot,
    disclosure_separate_output_directory: useSeparateOutputDirectory,
    fetchSettings,
    saveSetting,
  } = useSettingsStore();
  const summaryAbortControllerRef = useRef<AbortController | null>(null);
  const detailAbortControllerRef = useRef<AbortController | null>(null);
  const currentRequestKeyRef = useRef("");
  const [presets, setPresets] = useState<DisclosureConditionPreset[]>([]);
  const [selectedPreset, setSelectedPreset] = useState("");
  const [changeSearch, setChangeSearch] = useState("");
  const [showOnlyChanges, setShowOnlyChanges] = useState(false);
  const [changeLimit, setChangeLimit] = useState("50");
  const [exportLatestOnly, setExportLatestOnly] = useState(false);
  const selectedPresetEntry = useMemo(
    () => presets.find((preset) => presetIdentity(preset) === selectedPreset),
    [presets, selectedPreset],
  );
  const currentFilterMode = selectedPresetEntry?.mode || "";
  const currentParentMode = selectedPresetEntry?.parent_mode || "";
  const currentRequestKey = JSON.stringify({
    dataRoot,
    outputPath,
    useSeparateOutputDirectory,
    currentFilterMode,
    currentParentMode,
  });
  currentRequestKeyRef.current = currentRequestKey;

  const resultSourcePayload = () => ({
    data_root: dataRoot,
    mode: currentFilterMode,
    ...(currentParentMode ? { parent_mode: currentParentMode } : {}),
    ...(useSeparateOutputDirectory ? { output_path: outputPath } : {}),
  });

  const clearLoadedResults = () => {
    setChangeLog(null);
    setSelectedFamilyId("");
    setFamilyDetails({});
  };

  useEffect(() => {
    fetchSettings().finally(() => setLoading(false));
  }, [fetchSettings]);

  useEffect(() => () => {
    summaryAbortControllerRef.current?.abort();
    detailAbortControllerRef.current?.abort();
  }, []);

  useEffect(() => {
    if (!dataRoot?.trim()) {
      setPresets([]);
      return;
    }
    listDisclosureConditionPresets(dataRoot).then((response) => {
      setPresets(response.presets);
    }).catch((error) => {
      setPresets([]);
      setStatus(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    });
  }, [dataRoot]);

  useEffect(() => {
    if (selectedPreset || !storedMode) return;
    const match = presets.find((preset) => !preset.parent_mode && preset.mode === storedMode);
    if (match) setSelectedPreset(presetIdentity(match));
  }, [presets, selectedPreset, storedMode]);

  const loadChangeLog = async () => {
    if (!dataRoot || (useSeparateOutputDirectory && !outputPath)) {
      setStatus(`${DATA_PATH_LABELS.workspace}가 필요합니다.`);
      setIsErrorStatus(true);
      return;
    }
    if (!currentFilterMode) {
      setStatus("모드를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }

    setIsFetching(true);
    setStatus("변동 기록을 불러오는 중...");
    setIsErrorStatus(false);
    clearLoadedResults();
    summaryAbortControllerRef.current?.abort();
    detailAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    summaryAbortControllerRef.current = abortController;
    const requestKey = currentRequestKey;

    try {
      const response = await fetch("/api/disclosures/html/parse/change-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortController.signal,
        body: JSON.stringify({
          ...resultSourcePayload(),
          summary_only: true,
          limit: changeLimit === "" ? null : Number(changeLimit),
        }),
      });
      
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "변동 기록을 불러오지 못했습니다.");
      if (requestKey !== currentRequestKeyRef.current) return;
      setChangeLog(data);
      setStatus(`${formatInteger(data.families.length)}건의 목록을 불러왔습니다.`);
      
      if (data.families.length > 0) {
        void handleSelectFamily(data.families[0].family_id, requestKey);
      }
    } catch (err: any) {
      if (err?.name === "AbortError") return;
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      if (summaryAbortControllerRef.current === abortController) {
        summaryAbortControllerRef.current = null;
        setIsFetching(false);
      }
    }
  };

  const handleSelectFamily = async (familyId: string, requestKey = currentRequestKey) => {
    setSelectedFamilyId(familyId);
    if (familyDetails[familyId]) return;
    detailAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    detailAbortControllerRef.current = abortController;

    try {
      const response = await fetch("/api/disclosures/html/parse/change-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortController.signal,
        body: JSON.stringify({
          ...resultSourcePayload(),
          family_id: familyId,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "상세 변동 기록을 불러오지 못했습니다.");
      if (requestKey !== currentRequestKeyRef.current) return;
      const detailedFamily = data.families.find((f: any) => f.family_id === familyId);
      if (detailedFamily) {
        setFamilyDetails(prev => ({ ...prev, [familyId]: detailedFamily }));
      }
    } catch (err: any) {
      if (err?.name === "AbortError") return;
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      if (detailAbortControllerRef.current === abortController) {
        detailAbortControllerRef.current = null;
      }
    }
  };

  const handleExport = () => {
    if (!dataRoot || (useSeparateOutputDirectory && !outputPath)) {
      setStatus(`${DATA_PATH_LABELS.workspace}가 필요합니다.`);
      setIsErrorStatus(true);
      return;
    }
    if (!currentFilterMode) {
      setStatus("모드를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const params = new URLSearchParams({
      data_root: dataRoot,
      mode: currentFilterMode,
      latest_only: String(exportLatestOnly),
    });
    if (currentParentMode) params.set("parent_mode", currentParentMode);
    if (useSeparateOutputDirectory) params.set("output_path", outputPath);
    window.location.href = `/api/disclosures/html/parse/export.xlsx?${params.toString()}`;
  };

  const filteredFamilies = useMemo(() => {
    if (!changeLog?.families) return [];
    const keyword = changeSearch.trim().toLowerCase();
    
    return changeLog.families
      .filter((family: any) => {
        const displayFields = getChangedFields(family);
        const displayChangedCount = displayFields.length;

        if (showOnlyChanges && displayChangedCount === 0) return false;
        
        if (keyword) {
          const haystack = [
            family.family_id,
            family.title || "",
            ...(family.records || []).flatMap((r: any) => [r.title, r.acpt_no]),
            ...displayFields,
          ].join(" ").toLowerCase();
          if (!haystack.includes(keyword)) return false;
        }
        return true;
      })
      .sort((a: any, b: any) => {
        const aFields = getChangedFields(a).length;
        const bFields = getChangedFields(b).length;
        if (Boolean(bFields) !== Boolean(aFields)) return Number(Boolean(bFields)) - Number(Boolean(aFields));
        if (bFields !== aFields) return bFields - aFields;
        return String(b.family_id || "").localeCompare(String(a.family_id || ""), "ko-KR");
      });
  }, [changeLog, changeSearch, showOnlyChanges]);

  const selectedFamily = useMemo(() => {
    return familyDetails[selectedFamilyId] || changeLog?.families.find((f: any) => f.family_id === selectedFamilyId);
  }, [changeLog, selectedFamilyId, familyDetails]);

  const conditionFields: HtmlWorkflowField[] = [
    {
      id: "changeMode",
      kind: "select",
      label: "모드",
      value: selectedPreset,
      onChange: (val) => {
        summaryAbortControllerRef.current?.abort();
        detailAbortControllerRef.current?.abort();
        setSelectedPreset(val);
        clearLoadedResults();
        const preset = presets.find((item) => presetIdentity(item) === val);
        if (!preset || preset.parent_mode) return;
        void saveSetting("html_parse_mode", preset.mode);
      },
      options: presets.map((preset) => ({ value: presetIdentity(preset), label: presetLabel(preset) })),
    },
    {
      id: "outputPath",
      kind: "path",
      label: useSeparateOutputDirectory ? DATA_PATH_LABELS.output : DATA_PATH_LABELS.workspace,
      mode: "folder",
      value: useSeparateOutputDirectory ? outputPath || "" : dataRoot || "",
      onChange: (val) => saveSetting(
        useSeparateOutputDirectory ? "html_parse_output_directory" : "output_root",
        val,
      ),
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 2,
    },
    {
      id: "changeLimit",
      kind: "input",
      type: "number",
      label: "로딩 건수",
      value: changeLimit,
      onChange: setChangeLimit,
      trailing: <Button variant="outline" onClick={() => setChangeLimit("")} className="h-10 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200">전체</Button>,
    },
  ];

  const filterFields: HtmlWorkflowField[] = [
    {
      id: "changeSearch",
      kind: "custom",
      span: 2,
      content: (
        <HtmlSearchInput
          placeholder="제목, 접수번호, 필드명 검색..."
          value={changeSearch}
          onChange={setChangeSearch}
        />
      ),
    },
    {
      id: "showOnlyChanges",
      kind: "checkbox",
      checked: showOnlyChanges,
      onChange: setShowOnlyChanges,
      checkboxLabel: "변경사항만 보기",
    },
    {
      id: "exportControls",
      kind: "custom",
      content: (
        <div className="flex h-10 items-center justify-between gap-3 md:justify-end">
          <div className="flex items-center space-x-2">
            <Checkbox id="exportLatestOnly" checked={exportLatestOnly} onCheckedChange={(v) => setExportLatestOnly(!!v)} className="dark:border-[#30363d]" />
            <Label htmlFor="exportLatestOnly" className="cursor-pointer text-xs text-slate-500 dark:text-slate-400">최신버전만</Label>
          </div>
          <Button
            variant="outline"
            onClick={handleExport}
            disabled={!dataRoot || (useSeparateOutputDirectory && !outputPath) || !currentFilterMode}
            className="h-10 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200"
          >
            <FileSpreadsheet className="mr-2 h-3.5 w-3.5" />
            Export
          </Button>
        </div>
      ),
    },
  ];
  const pathFields = conditionFields.filter((field) => field.id === "outputPath");
  const optionFields = conditionFields.filter((field) => field.id !== "outputPath");
  const filterOnlyFields = filterFields.filter((field) => field.id !== "exportControls");
  const exportFields = filterFields.filter((field) => field.id === "exportControls");

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  return (
    <HtmlWorkflowPage
      eyebrow="Change Log"
      title="공시 정정내역 한눈에"
      description="정정공시 전후의 필드 값 변화를 매트릭스 형태로 비교합니다. 파싱 결과 JSON을 기준으로 목록, 상세 변경 필드, Excel 내보내기를 한 화면에서 처리합니다."
    >
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <HtmlWorkflowCard
          title="조회 조건"
          description="조회할 변환 결과와 표시 범위를 정하고, 불러온 정정 내역을 검색하거나 Excel로 내보냅니다."
          actions={
            <Button onClick={loadChangeLog} disabled={isFetching} className="h-10 dark:bg-slate-200 dark:text-slate-900 dark:hover:bg-white transition-colors">
              {isFetching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              변동 불러오기
            </Button>
          }
        >

          <HtmlWorkflowForm fields={pathFields} />
          <HtmlWorkflowForm fields={optionFields} />
          <HtmlWorkflowForm fields={filterOnlyFields} />
          <HtmlWorkflowForm fields={exportFields} />

          <div className="grid lg:grid-cols-10 gap-6 min-h-[500px]">
            <ChangeLogSidebar 
              families={filteredFamilies} 
              selectedFamilyId={selectedFamilyId} 
              onSelectFamily={handleSelectFamily} 
              hasSearchKeyword={!!changeSearch.trim()} 
            />
            <ChangeLogMatrix selectedFamily={selectedFamily} />
          </div>

        </HtmlWorkflowCard>
        <ActionDock
          activityActive={isFetching}
          activityContent={<JobStatusLogger status={status || "조회 전"} isErrorStatus={isErrorStatus} />}
          notificationActive={isErrorStatus}
          notificationTone="error"
          notificationContent={<div className={isErrorStatus ? "whitespace-pre-wrap text-sm text-[var(--tv-down-text)]" : "text-sm text-[var(--tv-muted)]"}>{isErrorStatus ? status : "알림 없음"}</div>}
          settingsTitle="설정"
          settingsContent={
            <ChangeLogSettings />
          }
        />
      </div>
    </HtmlWorkflowPage>
  );
}
