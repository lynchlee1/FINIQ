"use client"

import { useState, useEffect, useCallback, useMemo } from "react";
import { FileJson, Search, Loader2, Info, FileSpreadsheet, CheckCircle2, AlertCircle, Settings, X, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { Checkbox } from "@finiq/ui";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { WorkflowTabs } from "@/components/layout/WorkflowTabs";
import { cn } from "@finiq/ui/utils";

const HTML_PROCESS_TABS = [
  { href: "/html-download", step: 4, label: "HTML 저장" },
  { href: "/html-parse", step: 5, label: "HTML 파싱" },
  { href: "/html-change-log", step: 6, label: "변동기록조회" },
  { href: "/html-bond-summary", step: 7, label: "사채 발행 요약" },
];

const PARSE_MODES = [
  { key: "bond_issuance", label: "사채발행파싱" },
  { key: "rights_issuance", label: "유무상증자파싱" },
];

const DATE_FIELDS_CONFIG = [
  { field: "만기일", default: 3 },
  { field: "전환시작일", default: 3 },
  { field: "전환종료일", default: 3 },
  { field: "청약일", default: 3 },
  { field: "납입일", default: 3 },
  { field: "신주권교부예정일", default: 3 },
  { field: "상장예정일", default: 3 },
  { field: "기준일", default: 3 },
  { field: "권리배정기준일", default: 3 },
];

const NUMERIC_FIELDS_CONFIG = [
  { field: "발행금액", default: 1 },
  { field: "발행가액", default: 1 },
  { field: "행사가액", default: 1 },
  { field: "기준주가", default: 1 },
  { field: "표면이자율", default: 0.5 },
  { field: "만기이자율", default: 0.5 },
  { field: "리픽싱(%)", default: 0.5 },
  { field: "신주의 종류와 수", default: 1 },
];

export default function HtmlChangeLogPage() {
  const [loading, setLoading] = useState(true);
  const [isFetching, setIsFetching] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [isErrorStatus, setIsErrorStatus] = useState(false);

  // Data State
  const [changeLog, setChangeLog] = useState<any>(null);
  const [selectedFamilyId, setSelectedFamilyId] = useState<string>("");
  const [familyDetails, setFamilyDetails] = useState<Record<string, any>>({});

  // Form State
  const [outputPath, setOutputPath] = useState("");
  const [changeMode, setChangeMode] = useState("bond_issuance");
  const [changeSearch, setChangeSearch] = useState("");
  const [showOnlyChanges, setShowOnlyChanges] = useState(false);
  const [changeLimit, setChangeLimit] = useState("50");
  const [exportLatestOnly, setExportLatestOnly] = useState(false);

  // Settings State
  const [showSettings, setShowSettings] = useState(false);
  const [dateThresholds, setDateThresholds] = useState<Record<string, number>>(
    Object.fromEntries(DATE_FIELDS_CONFIG.map(c => [c.field, c.default]))
  );
  const [numericThresholds, setNumericThresholds] = useState<Record<string, number>>(
    Object.fromEntries(NUMERIC_FIELDS_CONFIG.map(c => [c.field, c.default]))
  );

  const fetchConfig = useCallback(async () => {
    try {
      const response = await fetch("/api/config");
      if (!response.ok) throw new Error("Failed to fetch config");
      const config = await response.json();
      
      if (config.html_parse_result_path) {
        setOutputPath(config.html_parse_result_path);
      } else {
        const defaultInput = config.html_output_directory || `${config.output_root || ""}/viewer_html`;
        setOutputPath(defaultInput ? `${defaultInput}/parsed-bond_issuance.json` : "");
      }
      if (config.html_parse_mode) {
        setChangeMode(config.html_parse_mode);
      }

      // Load thresholds from backend
      if (config.change_log_date_thresholds && Object.keys(config.change_log_date_thresholds).length > 0) {
        setDateThresholds(prev => ({ ...prev, ...config.change_log_date_thresholds }));
      }
      if (config.change_log_numeric_thresholds && Object.keys(config.change_log_numeric_thresholds).length > 0) {
        setNumericThresholds(prev => ({ ...prev, ...config.change_log_numeric_thresholds }));
      }
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const saveSetting = async (key: string, value: string) => {
    try {
      await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: value })
      });
    } catch (err) {
      console.error("Failed to save setting:", err);
    }
  };

  // Automatic saving to backend
  useEffect(() => {
    if (loading) return;

    const timer = setTimeout(async () => {
      try {
        await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            change_log_date_thresholds: dateThresholds,
            change_log_numeric_thresholds: numericThresholds,
          }),
        });
      } catch (e) {
        console.error("Failed to save thresholds to backend:", e);
      }
    }, 1000); // Debounce save

    return () => clearTimeout(timer);
  }, [dateThresholds, numericThresholds, loading]);

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
          mode: changeMode,
          summary_only: true,
          limit: changeLimit === "" ? null : Number(changeLimit),
          changes_only: showOnlyChanges,
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
    if (familyDetails[familyId] && familyDetails[familyId].has_details) return;

    try {
      const response = await fetch("/api/disclosures/html/parse/change-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          output_path: outputPath,
          mode: changeMode,
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

  const handlePickPath = async (type: 'file', setter: (v: string) => void, defaultPath: string) => {
    try {
      const response = await fetch("/api/file-dialog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: type, title: "선택", default_path: defaultPath }),
      });
      const data = await response.json();
      if (data.path) setter(data.path);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
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
      mode: changeMode,
      latest_only: String(exportLatestOnly),
    });
    window.location.href = `/api/disclosures/html/parse/export.xlsx?${params.toString()}`;
  };

  const getChangedFields = (family: any) => {
    const fields: string[] = [];
    const seen = new Set<string>();
    
    // Use changes if available (detailed data)
    if (family.changes && family.changes.length > 0) {
      for (const change of family.changes) {
        for (const fieldChange of change.changes || []) {
          const field = String(fieldChange.field || "").trim();
          if (!field || seen.has(field) || field === "회차") continue;
          seen.add(field);
          fields.push(field);
        }
      }
    }
    
    return fields;
  };

  const filteredFamilies = useMemo(() => {
    if (!changeLog?.families) return [];
    const keyword = changeSearch.trim().toLowerCase();
    
    return changeLog.families
      .filter((family: any) => {
        // Calculate display changed fields count (excluding 회차)
        const displayFields = getChangedFields(family);
        let displayChangedCount = displayFields.length;
        
        // If it's summary data, use the backend-provided changed_fields count
        if (!family.has_details && family.changed_fields !== undefined) {
          displayChangedCount = family.changed_fields;
        }

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
        // We already have some sorting from backend, but let's keep it consistent
        const aCount = a.has_details ? getChangedFields(a).length : (a.changed_fields || 0);
        const bCount = b.has_details ? getChangedFields(b).length : (b.changed_fields || 0);
        
        if (Boolean(bCount) !== Boolean(aCount)) return Number(Boolean(bCount)) - Number(Boolean(aCount));
        if (bCount !== aCount) return bCount - aCount;
        return String(b.family_id || "").localeCompare(String(a.family_id || ""), "ko-KR");
      });
  }, [changeLog, changeSearch, showOnlyChanges]);

  const selectedFamily = useMemo(() => {
    return familyDetails[selectedFamilyId] || changeLog?.families.find((f: any) => f.family_id === selectedFamilyId);
  }, [changeLog, selectedFamilyId, familyDetails]);

  // Matrix Rendering Helpers
  const stableJson = (val: any) => {
    if (val === null || val === undefined) return "null";
    if (typeof val !== "object") return String(val);
    try { return JSON.stringify(val); } catch { return String(val); }
  };

  const formatValueWithField = (value: any, fieldName: string) => {
    if (value === null || value === undefined || value === "") return "-";
    if (fieldName === "발행금액" || fieldName === "발행가액") {
      const num = Number(value);
      return Number.isFinite(num) ? (num / 100000000).toLocaleString("ko-KR", { maximumFractionDigits: 2 }) : String(value);
    }
    if (fieldName === "발행대상자" && Array.isArray(value)) {
      return value.map((target) => {
        if (Array.isArray(target)) {
          const name = target[0];
          const amount = target[target.length - 1];
          return !isNaN(Number(amount)) ? `${name} (${Number(amount).toLocaleString()})` : target.join(" ");
        }
        return String(target);
      }).join("\n");
    }
    if (Array.isArray(value)) return value.join(", ");
    return String(value);
  };

  const parseKoreanDate = (dateStr: any) => {
    if (!dateStr || typeof dateStr !== "string") return NaN;
    const match = dateStr.match(/(\d{4})\s*[년.-]\s*(\d{1,2})\s*[월.-]\s*(\d{1,2})/);
    if (match) return new Date(parseInt(match[1]), parseInt(match[2]) - 1, parseInt(match[3])).getTime();
    const clean = dateStr.replace(/[^\d]/g, "");
    if (clean.length === 8) return new Date(parseInt(clean.substring(0, 4)), parseInt(clean.substring(4, 6)) - 1, parseInt(clean.substring(6, 8))).getTime();
    return NaN;
  };

  const parseNumericValue = (val: any) => {
    if (typeof val === "number") return val;
    if (typeof val !== "string") return NaN;
    const clean = val.replace(/,/g, "").match(/-?\d+\.?\d*/);
    return clean ? parseFloat(clean[0]) : NaN;
  };

  const getMatrixData = (family: any) => {
    if (!family || !family.has_details) return null;
    const records = family.records || [];
    const changes = family.changes || [];
    const fields = getChangedFields(family);
    
    const matrix: Record<string, any[]> = {};
    for (const f of fields) matrix[f] = new Array(records.length).fill(null);

    if (changes.length > 0) {
      const firstChange = changes[0];
      for (const f of fields) {
        const delta = firstChange.changes.find((c: any) => c.field === f);
        if (delta) matrix[f][0] = delta.before;
      }
    }

    for (let i = 0; i < changes.length; i++) {
      const change = changes[i];
      const vIdx = i + 1;
      for (const f of fields) {
        const delta = change.changes.find((c: any) => c.field === f);
        if (delta) matrix[f][vIdx] = delta.after;
        else matrix[f][vIdx] = matrix[f][vIdx - 1];
      }
    }

    for (const f of fields) {
      let firstIdx = matrix[f].findIndex(v => v !== null);
      if (firstIdx > 0) {
        for (let j = 0; j < firstIdx; j++) matrix[f][j] = matrix[f][firstIdx];
      }
    }
    return { fields, records, matrix };
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
        <p className="text-slate-500 font-medium">설정을 불러오는 중입니다...</p>
      </div>
    );
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
            <Button variant="outline" size="icon" onClick={() => setShowSettings(!showSettings)} className={cn(showSettings ? "bg-slate-100 border-slate-300 dark:bg-[#21262d] dark:border-[#484f58]" : "dark:border-[#30363d] dark:hover:bg-[#21262d]")}>
              <Settings className={cn("h-4 w-4", showSettings ? "text-blue-600 dark:text-blue-400" : "text-slate-400")} />
            </Button>
            <Button onClick={loadChangeLog} disabled={isFetching} className="dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-200">
              변동 불러오기
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {showSettings && (
            <div className="p-5 bg-slate-50/80 dark:bg-[#0d1117]/50 border border-slate-200 dark:border-[#30363d] rounded-xl space-y-5 animate-in fade-in slide-in-from-top-2 shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-[#30363d] pb-3">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-white dark:bg-[#161b22] shadow-sm border border-slate-100 dark:border-[#30363d]">
                    <Settings className="h-3.5 w-3.5 text-slate-600 dark:text-slate-400" />
                  </div>
                  <h4 className="text-sm font-bold text-slate-900 dark:text-white">필드별 임계값 상세 설정</h4>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => {
                    setDateThresholds(Object.fromEntries(DATE_FIELDS_CONFIG.map(c => [c.field, c.default])));
                    setNumericThresholds(Object.fromEntries(NUMERIC_FIELDS_CONFIG.map(c => [c.field, c.default])));
                  }} className="h-8 text-[10px] font-bold dark:border-[#30363d] dark:hover:bg-[#21262d]">초기화</Button>
                  <Button variant="ghost" size="icon" onClick={() => setShowSettings(false)} className="h-8 w-8 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              
              <div className="grid lg:grid-cols-2 gap-x-12 gap-y-8 py-2">
                {/* Date Fields Column */}
                <div className="space-y-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-slate-500" />
                    <h5 className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">날짜 필드 (일수 차이)</h5>
                  </div>
                  <div className="grid gap-x-8 gap-y-4">
                    {DATE_FIELDS_CONFIG.map(({ field }) => (
                      <div key={field} className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <Label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">{field}</Label>
                          <div className="flex items-center gap-0.5 text-[10px] font-bold text-slate-700 dark:text-slate-200 bg-slate-100 dark:bg-[#21262d] px-1.5 py-0.5 rounded">
                            <span>{dateThresholds[field]}</span>
                            <span className="text-[9px] text-slate-400 dark:text-slate-500 font-medium ml-0.5">일</span>
                          </div>
                        </div>
                        <Input 
                          type="range" 
                          min="0" 
                          max="30" 
                          step="1" 
                          value={dateThresholds[field]} 
                          onChange={(e) => setDateThresholds(prev => ({ ...prev, [field]: Number(e.target.value) }))}
                          className="h-4 accent-slate-600 dark:accent-slate-400 cursor-pointer"
                        />
                      </div>
                    ))}
                  </div>
                </div>

                {/* Numeric Fields Column */}
                <div className="space-y-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-slate-500" />
                    <h5 className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">수치 필드 (변동폭 %)</h5>
                  </div>
                  <div className="grid gap-x-8 gap-y-4">
                    {NUMERIC_FIELDS_CONFIG.map(({ field }) => (
                      <div key={field} className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <Label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">{field}</Label>
                          <div className="flex items-center gap-0.5 text-[10px] font-bold text-slate-700 dark:text-slate-200 bg-slate-100 dark:bg-[#21262d] px-1.5 py-0.5 rounded">
                            <span>{numericThresholds[field]}</span>
                            <span className="text-[9px] text-slate-400 dark:text-slate-500 font-medium ml-0.5">%</span>
                          </div>
                        </div>
                        <Input 
                          type="range" 
                          min="0" 
                          max="100" 
                          step="0.5" 
                          value={numericThresholds[field]} 
                          onChange={(e) => setNumericThresholds(prev => ({ ...prev, [field]: Number(e.target.value) }))}
                          className="h-4 accent-slate-600 dark:accent-slate-400 cursor-pointer"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              <div className="pt-3 border-t border-slate-100 dark:border-[#30363d] flex items-center justify-between">
                <p className="text-[10px] text-slate-400 italic">※ 임계값 이하의 변동은 '단순변동'으로 처리되어 강조되지 않습니다.</p>
                <code className="text-[9px] text-slate-300 dark:text-slate-600 font-mono">회차 변동: 항상 무시됨</code>
              </div>
            </div>
          )}

          <div className="grid md:grid-cols-4 gap-4">
            <div className="space-y-2">
              <Label className="dark:text-slate-300">파싱 모드</Label>
              <Select 
                value={changeMode} 
                onValueChange={(val) => {
                  setChangeMode(val);
                  saveSetting("html_parse_mode", val);
                }}
              >
                <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                  {PARSE_MODES.map(m => (
                    <SelectItem key={m.key} value={m.key}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="md:col-span-2 space-y-2">
              <Label className="dark:text-slate-300">파싱 결과 파일</Label>
              <div className="flex gap-2">
                <Input 
                  value={outputPath} 
                  onChange={(e) => setOutputPath(e.target.value)} 
                  onBlur={() => saveSetting("html_parse_result_path", outputPath)}
                  className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" 
                />
                <Button variant="outline" size="icon" onClick={() => handlePickPath('file', setOutputPath, outputPath)} className="dark:border-[#30363d] dark:hover:bg-[#21262d]">
                  <FileJson className="h-4 w-4 dark:text-slate-400" />
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label className="dark:text-slate-300">로딩 건수</Label>
              <div className="flex gap-2">
                <Input type="number" value={changeLimit} onChange={(e) => setChangeLimit(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                <Button variant="outline" onClick={() => setChangeLimit("")} className="dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-300">전체</Button>
              </div>
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-4 items-end">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input 
                className="pl-9 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" 
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
                <Button size="sm" variant="outline" onClick={handleExport} disabled={!outputPath} className="dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-300">
                  <FileSpreadsheet className="mr-2 h-3.5 w-3.5" />
                  Export
                </Button>
              </div>
            </div>
          </div>

          <div className="grid lg:grid-cols-4 gap-6 min-h-[500px]">
            {/* Sidebar Rail */}
            <div className="lg:col-span-1 border rounded-xl overflow-hidden bg-white dark:bg-[#161b22] dark:border-[#30363d] flex flex-col">
              <div className="p-3 bg-slate-50 dark:bg-[#0d1117] border-b dark:border-[#30363d] text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                정정 패밀리 목록
              </div>
              <div className="overflow-auto flex-1 divide-y divide-slate-100 dark:divide-[#30363d] max-h-[600px]">
                {filteredFamilies.length > 0 ? (
                  filteredFamilies.map((family: any) => {
                    const isSelected = selectedFamilyId === family.family_id;
                    const displayChangedFields = getChangedFields(family);
                    const displayCount = displayChangedFields.length;
                    
                    return (
                      <button 
                        key={family.family_id}
                        onClick={() => handleSelectFamily(family.family_id)}
                        className={cn(
                          "w-full text-left p-4 hover:bg-slate-50 dark:hover:bg-[#21262d] transition-colors group relative",
                          isSelected ? "bg-blue-50/50 dark:bg-[#1f2937]/50" : ""
                        )}
                      >
                        {isSelected && <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-600 dark:bg-blue-500" />}
                        <div className="flex flex-col gap-1">
                          <strong className={cn(
                            "text-sm line-clamp-2",
                            isSelected ? "text-blue-900 dark:text-blue-100" : "text-slate-700 dark:text-slate-300"
                          )}>
                            {family.title || family.family_id}
                          </strong>
                          <div className="flex items-center gap-2 text-[10px] text-slate-400 dark:text-slate-500 font-medium">
                            <span>문서 {family.record_count}</span>
                            <span>•</span>
                            <span className={cn(displayCount > 0 ? "text-amber-600 dark:text-amber-500" : "")}>
                              필드 {family.has_details ? displayCount : "-"}
                            </span>
                          </div>
                          {family.has_details && displayCount > 0 && (
                            <div className="flex flex-wrap gap-1 mt-2">
                              {displayChangedFields.slice(0, 3).map(f => (
                                <span key={f} className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-[#21262d] text-slate-500 dark:text-slate-400 text-[9px]">{f}</span>
                              ))}
                              {displayChangedFields.length > 3 && (
                                <span className="text-[9px] text-slate-300 dark:text-slate-600">+{displayChangedFields.length - 3}</span>
                              )}
                            </div>
                          )}
                        </div>
                      </button>
                    );
                  })
                ) : (
                  <div className="p-8 text-center text-slate-400 dark:text-slate-600 text-sm">
                    {changeLog ? "검색 결과가 없습니다." : "파싱 결과를 불러오세요."}
                  </div>
                )}
              </div>
            </div>

            {/* Matrix Content Area */}
            <div className="lg:col-span-3 border rounded-xl bg-slate-50/50 dark:bg-[#0d1117]/50 dark:border-[#30363d] overflow-hidden flex flex-col min-h-[600px]">
              {selectedFamily ? (
                <>
                  <div className="p-6 bg-white dark:bg-[#161b22] border-b dark:border-[#30363d] space-y-1">
                    <div className="flex items-center gap-2">
                      <code className="text-[11px] text-slate-400 dark:text-slate-500 font-mono">{selectedFamily.family_id}</code>
                    </div>
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white line-clamp-1">
                      {selectedFamily.records?.at(-1)?.title || selectedFamily.title}
                    </h3>
                  </div>

                  <div className="flex-1 overflow-auto p-6">
                    {!selectedFamily.has_details ? (
                      <div className="h-full flex flex-col items-center justify-center space-y-4 py-12">
                        <Loader2 className="h-8 w-8 animate-spin text-blue-500 dark:text-blue-400" />
                        <div className="text-center">
                          <p className="text-sm font-bold text-slate-900 dark:text-slate-200">상세 변동 내역 분석 중</p>
                          <p className="text-xs text-slate-500 dark:text-slate-400">문서 간 데이터 차이를 대조하고 있습니다...</p>
                        </div>
                      </div>
                    ) : (() => {
                      const data = getMatrixData(selectedFamily);
                      if (!data || data.fields.length === 0) {
                        return (
                          <div className="h-full flex flex-col items-center justify-center text-center space-y-3 opacity-40 py-24">
                            <CheckCircle2 className="h-12 w-12 text-emerald-500 dark:text-emerald-400" />
                            <div>
                              <p className="text-sm font-bold text-slate-900 dark:text-slate-200">변동 사항 없음</p>
                              <p className="text-xs text-slate-500 dark:text-slate-400">모든 비교 필드가 이전 버전과 동일합니다.</p>
                            </div>
                          </div>
                        );
                      }

                      return (
                        <div className="border rounded-lg bg-white dark:bg-[#161b22] dark:border-[#30363d] shadow-sm overflow-hidden">
                          <table className="w-full text-xs border-collapse">
                            <thead className="bg-slate-50 dark:bg-[#0d1117] border-b dark:border-[#30363d]">
                              <tr>
                                <th className="px-4 py-3 text-left font-bold text-slate-500 dark:text-slate-400 w-32 border-r dark:border-[#30363d] bg-slate-50/80 dark:bg-[#0d1117]/80 sticky left-0 z-20">변동 필드</th>
                                {data.records.map((r: any, i: number) => (
                                  <th key={r.rcept_no} className="px-4 py-3 text-left min-w-[180px] border-r dark:border-[#30363d] last:border-r-0">
                                    <div className="flex flex-col gap-0.5">
                                      <span className="text-blue-600 dark:text-blue-400 font-bold">#{i + 1} {i === 0 ? "(Original)" : i === data.records.length - 1 ? "(Latest)" : ""}</span>
                                      <code className="text-[10px] text-slate-400 dark:text-slate-500 font-mono">{r.rcept_no}</code>
                                    </div>
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-[#30363d]">
                              {data.fields.map(field => (
                                <tr key={field} className="group">
                                  <td className="px-4 py-4 font-bold text-slate-700 dark:text-slate-300 border-r dark:border-[#30363d] bg-slate-50/30 dark:bg-[#0d1117]/30 sticky left-0 group-hover:bg-slate-100 dark:group-hover:bg-[#21262d] transition-colors z-10">
                                    {field}
                                  </td>
                                  {data.matrix[field].map((val, i) => {
                                    const prevVal = i > 0 ? data.matrix[field][i-1] : null;
                                    const isChanged = i > 0 && stableJson(val) !== stableJson(prevVal);
                                    
                                    let changeType: 'none' | 'minor' | 'major' = 'none';
                                    if (isChanged) {
                                      changeType = 'major';
                                      
                                      // Get per-field threshold
                                      const dateThreshold = dateThresholds[field];
                                      const numThreshold = numericThresholds[field];

                                      if (dateThreshold !== undefined) {
                                        const d1 = parseKoreanDate(val);
                                        const d2 = parseKoreanDate(prevVal);
                                        if (!isNaN(d1) && !isNaN(d2) && Math.abs(d1 - d2) <= dateThreshold * 24 * 3600 * 1000) changeType = 'minor';
                                      } else if (numThreshold !== undefined) {
                                        const n1 = parseNumericValue(val);
                                        const n2 = parseNumericValue(prevVal);
                                        if (!isNaN(n1) && !isNaN(n2) && n1 !== 0) {
                                          const diffPercent = Math.abs((n1 - n2) / n1) * 100;
                                          if (diffPercent <= numThreshold) changeType = 'minor';
                                        }
                                      }
                                    }

                                    return (
                                      <td 
                                        key={i} 
                                        className={cn(
                                          "px-4 py-4 border-r dark:border-[#30363d] last:border-r-0 align-top transition-colors",
                                          changeType === 'major' ? "bg-amber-50/50 dark:bg-amber-900/20" : changeType === 'minor' ? "bg-slate-50/50 dark:bg-slate-800/20" : ""
                                        )}
                                      >
                                        <div className="space-y-1">
                                          {changeType === 'major' && (
                                            <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 text-[9px] font-bold">정정</span>
                                          )}
                                          {changeType === 'minor' && (
                                            <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 text-[9px] font-bold">단순변동</span>
                                          )}
                                          <div className={cn(
                                            "whitespace-pre-wrap leading-relaxed",
                                            isChanged ? "font-bold text-slate-900 dark:text-slate-50" : "text-slate-500 dark:text-slate-400"
                                          )}>
                                            {formatValueWithField(val, field)}
                                          </div>
                                        </div>
                                      </td>
                                    );
                                  })}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      );
                    })()}
                  </div>
                </>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-center space-y-3 opacity-40 py-24">
                  <div className="p-4 rounded-full bg-slate-200 dark:bg-[#21262d]">
                    <AlertCircle className="h-8 w-8 text-slate-400 dark:text-slate-500" />
                  </div>
                  <p className="text-sm font-medium text-slate-500 dark:text-slate-400">패밀리를 선택하면 상세 변동 내역이 표시됩니다.</p>
                </div>
              )}
            </div>
          </div>
        </CardContent>
        {status && (
          <div className={cn(
            "mx-6 mb-6 p-3 rounded-lg border text-xs font-medium",
            isErrorStatus ? "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-900/40 text-red-700 dark:text-red-300" : "bg-slate-50 dark:bg-[#21262d] border-slate-200 dark:border-[#30363d] text-slate-700 dark:text-slate-300"
          )}>
            {status}
          </div>
        )}
      </Card>
    </main>
  );
}
