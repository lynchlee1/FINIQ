"use client"

import { useState, useEffect, useCallback, useMemo } from "react";
import { Search, Loader2, Info, ExternalLink } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, CardDescription, Input, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { WorkflowTabs } from "@/components/layout/WorkflowTabs";
import { cn } from "@finiq/ui/utils";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { useSettingsStore } from "@/store/useSettingsStore";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";

const HTML_PROCESS_TABS = [
  { href: "/html-download", step: 1, label: "HTML 외부 저장" },
  { href: "/html-content-download", step: 2, label: "HTML 내부 저장" },
  { href: "/html-parse", step: 3, label: "HTML 파싱" },
  { href: "/html-change-log", step: 4, label: "변동기록조회" },
  { href: "/html-bond-summary", step: 5, label: "사채 발행 요약" },
];

export default function HtmlBondSummaryPage() {
  const [loading, setLoading] = useState(true);
  const [isFetching, setIsFetching] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [isErrorStatus, setIsErrorStatus] = useState(false);
  
  // Data State
  const [bondSummary, setBondSummary] = useState<any>(null);
  const [selectedBondKey, setSelectedBondKey] = useState<string>("");

  // Form State
  const { html_parse_result_path: outputPath, fetchSettings, saveSetting } = useSettingsStore();
  const [bondSearch, setBondSearch] = useState("");
  const [bondCorrectionFilter, setBondCorrectionFilter] = useState("all");
  const [bondLimit, setBondLimit] = useState("20");

  useEffect(() => {
    fetchSettings().finally(() => setLoading(false));
  }, [fetchSettings]);

  const loadBondSummary = async () => {
    if (!outputPath) {
      setStatus("파싱 결과 경로가 필요합니다.");
      setIsErrorStatus(true);
      return;
    }

    setIsFetching(true);
    setStatus("채권 요약을 불러오는 중...");
    setIsErrorStatus(false);

    try {
      const response = await fetch("/api/disclosures/html/parse/bond-summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          output_path: outputPath,
          limit: bondLimit === "all" ? null : Number(bondLimit),
        }),
      });
      
      if (!response.ok) throw new Error("Failed to load bond summary");
      const data = await response.json();
      setBondSummary(data);
      setSelectedBondKey("");
      setStatus("채권 요약을 불러왔습니다.");
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setIsFetching(false);
    }
  };

  const formatNumber = (value: any) => {
    if (value === null || value === undefined || value === "") return "-";
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString("ko-KR") : String(value);
  };

  const formatHundredMillion = (value: any) => {
    if (value === null || value === undefined || value === "") return "-";
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    return (number / 100000000).toLocaleString("ko-KR", { maximumFractionDigits: 2 });
  };

  const getField = (record: any, key: string) => record?.fields?.[key] ?? "";

  const getRecordKey = (record: any) => `${record.rcept_no || ""}:${record.acpt_no || ""}:${record.index || ""}`;

  const getKindDisclosureUrl = (record: any) => {
    const acptNo = String(record?.acpt_no || "").trim();
    const docNo = String(record?.rcept_no || "").trim();
    if (!acptNo) return "";
    return `https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno=${encodeURIComponent(acptNo)}&docno=${encodeURIComponent(docNo)}&viewerhost=&viewerport=`;
  };

  const getCorrectionLabel = (record: any) => {
    const current = Number(record.current_sequence ?? 0);
    const total = Number(record.family_member_count || 0);
    if (!total || total <= 1) return "-";
    return `${current + 1}/${total}`;
  };

  const getTargetText = (record: any) => {
    const targets = getField(record, "발행대상자");
    if (!Array.isArray(targets)) return "";
    return targets.map((target) => Array.isArray(target) ? target.join(" ") : String(target || "")).join(" ");
  };

  const filteredRecords = useMemo(() => {
    if (!bondSummary?.records) return [];
    
    const keyword = bondSearch.trim().toLowerCase();
    
    return bondSummary.records.filter((record: any) => {
      // Keyword match
      if (keyword) {
        const haystack = [
          record.title,
          record.acpt_no,
          record.rcept_no,
          record.family_id,
          getField(record, "회차"),
          getField(record, "납입일"),
          getTargetText(record),
        ].join(" ").toLowerCase();
        if (!haystack.includes(keyword)) return false;
      }

      // Correction filter
      const current = Number(record.current_sequence ?? 0);
      const total = Number(record.family_member_count || 0);
      if (bondCorrectionFilter === "corrected" && total <= 1) return false;
      if (bondCorrectionFilter === "current" && current === 0) return false;
      if (bondCorrectionFilter === "latest" && (total === 0 || current !== total - 1)) return false;

      return true;
    });
  }, [bondSummary, bondSearch, bondCorrectionFilter]);

  const selectedRecord = useMemo(() => {
    if (!selectedBondKey) return filteredRecords[0] || null;
    return filteredRecords.find((r: any) => getRecordKey(r) === selectedBondKey) || filteredRecords[0] || null;
  }, [filteredRecords, selectedBondKey]);

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  return (
    <main className="flex flex-col gap-6 w-full">
      <WorkflowTabs tabs={HTML_PROCESS_TABS} />
      
      <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <div>
            <CardTitle className="dark:text-white">사채 발행 요약</CardTitle>
            <CardDescription className="dark:text-slate-400">파싱된 사채 발행 데이터를 조회하고 정정 이력을 확인합니다.</CardDescription>
          </div>
          <Button onClick={loadBondSummary} disabled={isFetching}>
            {isFetching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            결과 불러오기
          </Button>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid md:grid-cols-4 gap-4">
            <div className="md:col-span-2 space-y-2">
              <Label className="dark:text-slate-300">파싱 결과 경로</Label>
              <PathPickerInput 
                mode="file"
                value={outputPath || ""}
                onChange={(val) => saveSetting("html_parse_result_path", val)}
                onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
              />
            </div>
            <div className="space-y-2">
              <Label className="dark:text-slate-300">정정 상태</Label>
              <Select value={bondCorrectionFilter} onValueChange={setBondCorrectionFilter}>
                <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                  <SelectItem value="all">전체</SelectItem>
                  <SelectItem value="corrected">정정 이력 있음</SelectItem>
                  <SelectItem value="current">현재가 정정공시</SelectItem>
                  <SelectItem value="latest">최신 공시</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="dark:text-slate-300">표시 건수</Label>
              <Select value={bondLimit} onValueChange={setBondLimit}>
                <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                  <SelectItem value="20">20건</SelectItem>
                  <SelectItem value="100">100건</SelectItem>
                  <SelectItem value="300">300건</SelectItem>
                  <SelectItem value="1000">1000건</SelectItem>
                  <SelectItem value="all">전체</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input 
              className="pl-9 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" 
              placeholder="제목, 접수번호, 대상자 검색..." 
              value={bondSearch} 
              onChange={(e) => setBondSearch(e.target.value)} 
            />
          </div>

          <div className="grid lg:grid-cols-2 gap-6 min-h-[500px]">
            {/* Table Area */}
            <div className="border rounded-xl overflow-hidden bg-white dark:bg-[#161b22] dark:border-[#30363d]">
              <div className="overflow-auto max-h-[600px]">
                <table className="w-full text-sm border-collapse">
                  <thead className="bg-slate-50 dark:bg-[#0d1117] sticky top-0 z-10">
                    <tr className="border-b border-slate-200 dark:border-[#30363d]">
                      <th className="px-4 py-3 text-left font-semibold text-slate-900 dark:text-slate-100">제목</th>
                      <th className="px-4 py-3 text-left font-semibold text-slate-900 dark:text-slate-100 w-16">회차</th>
                      <th className="px-4 py-3 text-right font-semibold text-slate-900 dark:text-slate-100 w-32">금액(억원)</th>
                      <th className="px-4 py-3 text-left font-semibold text-slate-900 dark:text-slate-100 w-32">접수번호</th>
                      <th className="px-4 py-3 text-center font-semibold text-slate-900 dark:text-slate-100 w-16">원문</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-[#30363d]">
                    {filteredRecords.length > 0 ? (
                      filteredRecords.map((record: any) => {
                        const key = getRecordKey(record);
                        const isSelected = (selectedRecord && getRecordKey(selectedRecord) === key);
                        const url = getKindDisclosureUrl(record);
                        return (
                          <tr 
                            key={key} 
                            className={cn(
                              "cursor-pointer hover:bg-slate-50 dark:hover:bg-[#21262d] transition-colors",
                              isSelected ? "bg-blue-50/50 dark:bg-[#1f2937]/50" : ""
                            )}
                            onClick={() => setSelectedBondKey(key)}
                          >
                            <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-200">{record.title || "-"}</td>
                            <td className="px-4 py-3 text-slate-600 dark:text-slate-400">{getField(record, "회차") || "-"}</td>
                            <td className="px-4 py-3 text-right text-slate-600 dark:text-slate-400 tabular-nums">{formatHundredMillion(getField(record, "발행금액"))}</td>
                            <td className="px-4 py-3 text-slate-600 dark:text-slate-400">{record.rcept_no || "-"}</td>
                            <td className="px-4 py-3 text-center">
                              {url ? (
                                <a 
                                  href={url} 
                                  target="_blank" 
                                  rel="noopener noreferrer" 
                                  className="inline-flex items-center justify-center p-1.5 rounded-md hover:bg-slate-200 dark:hover:bg-[#30363d] text-slate-500 dark:text-slate-400 transition-colors"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <ExternalLink className="h-4 w-4" />
                                </a>
                              ) : "-"}
                            </td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td colSpan={5} className="px-4 py-12 text-center text-slate-400 dark:text-slate-600">
                          {bondSummary ? "검색 결과가 없습니다." : "파싱 결과를 불러오면 채권 정보가 표시됩니다."}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Detail Area */}
            <div className="border rounded-xl bg-slate-50/50 dark:bg-[#0d1117]/50 dark:border-[#30363d] p-6 space-y-6 overflow-auto max-h-[600px]">
              {selectedRecord ? (
                <>
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 text-[10px] font-bold">
                        {getCorrectionLabel(selectedRecord)}
                      </span>
                      <span className="text-xs text-slate-400 dark:text-slate-500 font-medium">
                        {selectedRecord.family_id || selectedRecord.rcept_no}
                      </span>
                    </div>
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white">{selectedRecord.title}</h3>
                  </div>

                  <div className="grid grid-cols-2 gap-x-8 gap-y-3 border-y border-slate-200 dark:border-[#30363d] py-4">
                    {[
                      ["상장시장", getField(selectedRecord, "상장시장")],
                      ["회차", getField(selectedRecord, "회차")],
                      ["발행금액(억원)", formatHundredMillion(getField(selectedRecord, "발행금액"))],
                      ["발행목적", getField(selectedRecord, "발행목적")],
                      ["표면이자율", getField(selectedRecord, "표면이자율")],
                      ["만기이자율", getField(selectedRecord, "만기이자율")],
                      ["만기일", getField(selectedRecord, "만기일")],
                      ["할증률(%)", getField(selectedRecord, "할증률(%)")],
                      ["행사가액", formatNumber(getField(selectedRecord, "행사가액"))],
                      ["행사대상", getField(selectedRecord, "행사대상")],
                      ["전환시작일", getField(selectedRecord, "전환시작일")],
                      ["전환종료일", getField(selectedRecord, "전환종료일")],
                      ["리픽싱(%)", getField(selectedRecord, "리픽싱(%)")],
                      ["청약일", getField(selectedRecord, "청약일")],
                      ["납입일", getField(selectedRecord, "납입일")],
                      ["납입방법", getField(selectedRecord, "납입방법")],
                    ].map(([label, value]) => (
                      <div key={label} className="flex flex-col gap-0.5">
                        <span className="text-xs text-slate-400 dark:text-slate-500 font-medium">{label}</span>
                        <span className="text-sm text-slate-700 dark:text-slate-300 font-semibold">{String(value || "-")}</span>
                      </div>
                    ))}
                  </div>

                  <div className="space-y-3">
                    <h4 className="text-xs font-bold text-slate-900 dark:text-slate-400 uppercase tracking-wider">정정공시 기록</h4>
                    <div className="space-y-2">
                      {(() => {
                        const family = bondSummary?.families?.[selectedRecord.family_id];
                        const members = Array.isArray(family?.members) ? family.members : [];
                        if (members.length === 0) return <p className="text-xs text-slate-400 dark:text-slate-600">정정 기록이 없습니다.</p>;
                        return members.map((member: any) => (
                          <div 
                            key={member.rcept_no} 
                            className={cn(
                              "flex items-center gap-3 p-2 rounded-lg border",
                              member.sequence === selectedRecord.current_sequence 
                                ? "bg-white dark:bg-[#161b22] border-blue-200 dark:border-blue-900 shadow-sm" 
                                : "bg-slate-100/50 dark:bg-[#0d1117]/50 border-slate-200 dark:border-[#30363d] opacity-60 dark:opacity-40"
                            )}
                          >
                            <span className="w-5 h-5 flex items-center justify-center rounded-full bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 text-[10px] font-bold">
                              {Number(member.sequence || 0) + 1}
                            </span>
                            <div className="flex flex-col">
                              <span className="text-xs font-bold text-slate-700 dark:text-slate-300">{member.rcept_no}</span>
                              <span className="text-[9px] text-slate-400 dark:text-slate-500">acpt_no: {member.acpt_no}</span>
                            </div>
                          </div>
                        ));
                      })()}
                    </div>
                  </div>

                  <div className="space-y-3">
                    <h4 className="text-xs font-bold text-slate-900 dark:text-slate-400 uppercase tracking-wider">발행 대상자</h4>
                    <div className="space-y-1.5">
                      {(() => {
                        const targets = getField(selectedRecord, "발행대상자");
                        if (!Array.isArray(targets) || targets.length === 0) return <p className="text-xs text-slate-400 dark:text-slate-600">대상자 정보가 없습니다.</p>;
                        return targets.map((target: any, idx: number) => {
                          const name = Array.isArray(target) ? target[0] : target;
                          const amount = Array.isArray(target) ? target[target.length - 1] : "";
                          return (
                            <div key={idx} className="flex justify-between items-center p-2 rounded-lg bg-white dark:bg-[#161b22] border border-slate-200 dark:border-[#30363d]">
                              <span className="text-xs text-slate-700 dark:text-slate-300 font-medium">{String(name || "-")}</span>
                              <strong className="text-xs text-slate-900 dark:text-slate-100 tabular-nums">{formatNumber(amount)}</strong>
                            </div>
                          );
                        });
                      })()}
                    </div>
                  </div>
                </>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-center space-y-3 py-24">
                  <div className="p-4 rounded-full bg-slate-200 dark:bg-[#21262d]">
                    <Info className="h-8 w-8 text-slate-400 dark:text-slate-500" />
                  </div>
                  <p className="text-sm font-medium text-slate-500 dark:text-slate-400">행을 선택하면 채권 상세 정보가 표시됩니다.</p>
                </div>
              )}
            </div>
          </div>
        </CardContent>
        {status && (
          <JobStatusLogger status={status} isErrorStatus={isErrorStatus} />
        )}
      </Card>
    </main>
  );
}
