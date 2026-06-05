"use client"

import { useState, useEffect, useMemo } from "react";
import { Search, Loader2, FileSpreadsheet, Settings } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, CardDescription, Input, Label, Checkbox, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { WorkflowTabs } from "@/components/layout/WorkflowTabs";
import { cn } from "@finiq/ui/utils";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { useSettingsStore } from "@/store/useSettingsStore";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { ChangeLogSettings } from "@/components/html-change-log/ChangeLogSettings";
import { ChangeLogSidebar } from "@/components/html-change-log/ChangeLogSidebar";
import { ChangeLogMatrix } from "@/components/html-change-log/ChangeLogMatrix";
import { getChangedFields } from "@/utils/matrixUtils";

const HTML_PROCESS_TABS = [
  { href: "/html-download", step: 1, label: "HTML 외부 저장" },
  { href: "/html-content-download", step: 2, label: "HTML 내부 저장" },
  { href: "/html-parse", step: 3, label: "HTML 파싱" },
  { href: "/html-change-log", step: 4, label: "변동기록조회" },
  { href: "/html-bond-summary", step: 5, label: "사채 발행 요약" },
];

const PARSE_MODES = [
  { key: "bond_issuance", label: "사채발행파싱" },
  { key: "rights_issuance", label: "유무상증자파싱" },
];

export default function HtmlChangeLogPage() {
  const [loading, setLoading] = useState(true);
  const [isFetching, setIsFetching] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [isErrorStatus, setIsErrorStatus] = useState(false);

  const [changeLog, setChangeLog] = useState<any>(null);
  const [selectedFamilyId, setSelectedFamilyId] = useState<string>("");
  const [familyDetails, setFamilyDetails] = useState<Record<string, any>>({});

  const { html_parse_result_path: outputPath, html_parse_mode: changeMode, fetchSettings, saveSetting } = useSettingsStore();
  const [changeSearch, setChangeSearch] = useState("");
  const [showOnlyChanges, setShowOnlyChanges] = useState(false);
  const [changeLimit, setChangeLimit] = useState("50");
  const [exportLatestOnly, setExportLatestOnly] = useState(false);

  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    fetchSettings().finally(() => setLoading(false));
  }, [fetchSettings]);

  const loadChangeLog = async () => {
    if (!outputPath) {
      setStatus("파싱 결과 경로가 필요합니다.");
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
      setStatus(`${data.families.length}건의 목록을 불러왔습니다.`);
      
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
      setStatus("파싱 결과 경로가 필요합니다.");
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
            ...(family.records || []).flatMap((r: any) => [r.title, r.acpt_no, r.rcept_no]),
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

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  return (
    <main className="flex flex-col gap-6 w-full">
      <WorkflowTabs tabs={HTML_PROCESS_TABS} />
      
      <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <div>
            <CardTitle className="dark:text-white">변동기록조회</CardTitle>
            <CardDescription className="dark:text-slate-400">정정공시 전후의 필드 값 변화를 매트릭스 형태로 비교합니다.</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="icon" onClick={() => setShowSettings(!showSettings)} className={cn(showSettings ? "bg-slate-100 border-slate-300 dark:bg-[#21262d] dark:border-[#30363d]" : "dark:border-[#30363d] dark:hover:bg-[#21262d]")}>
              <Settings className={cn("h-4 w-4", showSettings ? "text-blue-600 dark:text-blue-400" : "text-slate-400 dark:text-slate-500")} />
            </Button>
            <Button onClick={loadChangeLog} disabled={isFetching} className="dark:bg-slate-200 dark:text-slate-900 dark:hover:bg-white transition-colors">
              {isFetching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              변동 불러오기
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {showSettings && <ChangeLogSettings onClose={() => setShowSettings(false)} />}

          <div className="grid md:grid-cols-4 gap-4">
            <div className="space-y-2">
              <Label className="dark:text-slate-300">파싱 모드</Label>
              <Select 
                value={changeMode || "bond_issuance"} 
                onValueChange={(val) => saveSetting("html_parse_mode", val)}
              >
                <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                  {PARSE_MODES.map((m: any) => (
                    <SelectItem key={m.key} value={m.key}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="md:col-span-2 space-y-2">
              <Label className="dark:text-slate-300">파싱 결과 파일</Label>
              <PathPickerInput 
                mode="file"
                value={outputPath || ""}
                onChange={(val) => saveSetting("html_parse_result_path", val)}
                onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
              />
            </div>
            <div className="space-y-2">
              <Label className="dark:text-slate-300">로딩 건수</Label>
              <div className="flex gap-2">
                <Input type="number" value={changeLimit} onChange={(e) => setChangeLimit(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                <Button variant="outline" onClick={() => setChangeLimit("")} className="dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200">전체</Button>
              </div>
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-4 items-end">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 dark:text-slate-500" />
              <Input 
                className="pl-9 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 dark:placeholder:text-slate-600" 
                placeholder="제목, 접수번호, 필드명 검색..." 
                value={changeSearch} 
                onChange={(e) => setChangeSearch(e.target.value)} 
              />
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Checkbox id="showOnlyChanges" checked={showOnlyChanges} onCheckedChange={(v) => setShowOnlyChanges(!!v)} className="dark:border-[#30363d]" />
                <Label htmlFor="showOnlyChanges" className="cursor-pointer dark:text-slate-300">변경사항만 보기</Label>
              </div>
              <div className="flex items-center gap-4">
                <div className="flex items-center space-x-2">
                  <Checkbox id="exportLatestOnly" checked={exportLatestOnly} onCheckedChange={(v) => setExportLatestOnly(!!v)} className="dark:border-[#30363d]" />
                  <Label htmlFor="exportLatestOnly" className="cursor-pointer text-xs text-slate-500 dark:text-slate-400">최신버전만</Label>
                </div>
                <Button size="sm" variant="outline" onClick={handleExport} disabled={!outputPath} className="dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200">
                  <FileSpreadsheet className="mr-2 h-3.5 w-3.5" />
                  Export
                </Button>
              </div>
            </div>
          </div>

          <div className="grid lg:grid-cols-10 gap-6 min-h-[500px]">
            <ChangeLogSidebar 
              families={filteredFamilies} 
              selectedFamilyId={selectedFamilyId} 
              onSelectFamily={handleSelectFamily} 
              hasSearchKeyword={!!changeSearch.trim()} 
            />
            <ChangeLogMatrix selectedFamily={selectedFamily} />
          </div>

          {status && (
            <JobStatusLogger status={status} isErrorStatus={isErrorStatus} />
          )}
        </CardContent>
      </Card>
    </main>
  );
}
