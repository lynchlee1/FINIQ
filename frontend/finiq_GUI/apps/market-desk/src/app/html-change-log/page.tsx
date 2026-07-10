"use client"

import { useState, useEffect, useMemo } from "react";
import { Loader2, FileSpreadsheet } from "lucide-react";
import { Button, Label, Checkbox } from "@finiq/ui";
import { JobStatusLogger, PageLoadingSpinner, ActionDock } from "@finiq/web-app/status";
import { useSettingsStore } from "@/store/useSettingsStore";
import { ChangeLogSidebar } from "@/components/html-change-log/ChangeLogSidebar";
import { ChangeLogMatrix } from "@/components/html-change-log/ChangeLogMatrix";
import { getChangedFields } from "@/utils/matrixUtils";
import {
  HtmlSearchInput,
  HtmlWorkflowForm,
  HtmlWorkflowCard,
  HtmlWorkflowPage,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import { formatInteger } from "@/lib/format";

const PARSE_MODES = [
  { key: "bond_issuance", label: "사채발행파싱" },
  { key: "rights_issuance", label: "유무상증자파싱" },
];

const HTML_CHANGE_LOG_RELATED_ROUTE = "/html-bond-summary";

export default function HtmlChangeLogPage() {
  const [loading, setLoading] = useState(true);
  const [isFetching, setIsFetching] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [isErrorStatus, setIsErrorStatus] = useState(false);

  const [changeLog, setChangeLog] = useState<any>(null);
  const [selectedFamilyId, setSelectedFamilyId] = useState<string>("");
  const [familyDetails, setFamilyDetails] = useState<Record<string, any>>({});

  const { html_parse_output_directory: outputPath, html_parse_mode: changeMode, fetchSettings, saveSetting } = useSettingsStore();
  const [changeSearch, setChangeSearch] = useState("");
  const [showOnlyChanges, setShowOnlyChanges] = useState(false);
  const [changeLimit, setChangeLimit] = useState("50");
  const [exportLatestOnly, setExportLatestOnly] = useState(false);


  useEffect(() => {
    fetchSettings().finally(() => setLoading(false));
  }, [fetchSettings]);

  const loadChangeLog = async () => {
    if (!outputPath) {
      setStatus("파싱 결과 데이터 경로가 필요합니다.");
      setIsErrorStatus(true);
      return;
    }

    setIsFetching(true);
    setStatus("변동 기록을 불러오는 중...");
    setIsErrorStatus(false);
    setChangeLog(null);
    setSelectedFamilyId("");
    setFamilyDetails({});

    try {
      const response = await fetch("/api/disclosures/html/parse/change-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          output_path: outputPath,
          mode: changeMode || "bond_issuance",
          summary_only: true,
          limit: changeLimit === "" ? null : Number(changeLimit),
        }),
      });
      
      if (!response.ok) throw new Error("Failed to load change log");
      const data = await response.json();
      setChangeLog(data);
      setStatus(`${formatInteger(data.families.length)}건의 목록을 불러왔습니다.`);
      
      if (data.families.length > 0) {
        handleSelectFamily(data.families[0].family_id);
      }
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setIsFetching(false);
    }
  };

  const handleSelectFamily = async (familyId: string) => {
    setSelectedFamilyId(familyId);
    if (familyDetails[familyId]) return;

    try {
      const response = await fetch("/api/disclosures/html/parse/change-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          output_path: outputPath,
          mode: changeMode || "bond_issuance",
          family_id: familyId,
        }),
      });
      if (!response.ok) throw new Error("Failed to load family detail");
      const data = await response.json();
      const detailedFamily = data.families.find((f: any) => f.family_id === familyId);
      if (detailedFamily) {
        setFamilyDetails(prev => ({ ...prev, [familyId]: detailedFamily }));
      }
    } catch (err: any) {
      console.error(err);
    }
  };

  const handleExport = () => {
    if (!outputPath) {
      setStatus("파싱 결과 데이터 경로가 필요합니다.");
      setIsErrorStatus(true);
      return;
    }
    const params = new URLSearchParams({
      output_path: outputPath,
      mode: changeMode || "bond_issuance",
      latest_only: String(exportLatestOnly),
    });
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
      label: "파싱 모드",
      value: changeMode || "bond_issuance",
      onChange: (val) => saveSetting("html_parse_mode", val),
      options: PARSE_MODES.map((mode) => ({ value: mode.key, label: mode.label })),
    },
    {
      id: "outputPath",
      kind: "path",
      label: "파싱 결과 데이터 경로",
      mode: "folder",
      value: outputPath || "",
      onChange: (val) => saveSetting("html_parse_output_directory", val),
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
          <Button variant="outline" onClick={handleExport} disabled={!outputPath} className="h-10 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200">
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
          description="모든 조회형 원문 처리 화면은 같은 필드 높이와 열 규칙을 사용합니다."
          actions={
            <Button onClick={loadChangeLog} disabled={isFetching} className="h-10 dark:bg-slate-200 dark:text-slate-900 dark:hover:bg-white transition-colors">
              {isFetching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              변동 불러오기
            </Button>
          }
        >

          <HtmlWorkflowForm fields={pathFields} />

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
          notificationContent={<div className={isErrorStatus ? "whitespace-pre-wrap text-sm text-red-600 dark:text-red-300" : "text-sm text-slate-500 dark:text-slate-400"}>{isErrorStatus ? status : "알림 없음"}</div>}
          settingsTitle="시스템 설정"
          settingsContent={
            <div className="space-y-5">
              <div className="space-y-3">
                <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">결과 범위</p>
                </div>
                <HtmlWorkflowForm fields={optionFields} />
              </div>
              <div className="space-y-3">
                <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">필터</p>
                </div>
                <HtmlWorkflowForm fields={filterOnlyFields} />
              </div>
              <div className="space-y-3">
                <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">내보내기</p>
                </div>
                <HtmlWorkflowForm fields={exportFields} />
              </div>
            </div>
          }
        />
      </div>
    </HtmlWorkflowPage>
  );
}
