"use client"

import { useState, useEffect, useCallback, useMemo } from "react";
import { FileJson, Search, Loader2, Info, ExternalLink } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { WorkflowTabs } from "@/components/layout/WorkflowTabs";
import { cn } from "@finiq/ui/utils";

const HTML_PROCESS_TABS = [
  { href: "/html-download", step: 4, label: "HTML 저장" },
  { href: "/html-parse", step: 5, label: "HTML 파싱" },
  { href: "/html-change-log", step: 6, label: "변동기록조회" },
  { href: "/html-bond-summary", step: 7, label: "사채 발행 요약" },
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
  const [outputPath, setOutputPath] = useState("");
  const [bondSearch, setBondSearch] = useState("");
  const [bondCorrectionFilter, setBondCorrectionFilter] = useState("all");
  const [bondLimit, setBondLimit] = useState("20");

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
      
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <div>
            <CardTitle>사채 발행 요약</CardTitle>
            <CardDescription>파싱된 사채 발행 데이터를 조회하고 정정 이력을 확인합니다.</CardDescription>
          </div>
          <Button onClick={loadBondSummary} disabled={isFetching}>
            결과 불러오기
          </Button>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid md:grid-cols-4 gap-4">
            <div className="md:col-span-2 space-y-2">
              <Label>파싱 결과 경로</Label>
              <div className="flex gap-2">
                <Input value={outputPath} onChange={(e) => setOutputPath(e.target.value)} />
                <Button variant="outline" size="icon" onClick={() => handlePickPath('file', setOutputPath, outputPath)}>
                  <FileJson className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label>정정 상태</Label>
              <Select value={bondCorrectionFilter} onValueChange={setBondCorrectionFilter}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">전체</SelectItem>
                  <SelectItem value="corrected">정정 이력 있음</SelectItem>
                  <SelectItem value="current">현재가 정정공시</SelectItem>
                  <SelectItem value="latest">최신 공시</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>표시 건수</Label>
              <Select value={bondLimit} onValueChange={setBondLimit}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
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
              className="pl-9" 
              placeholder="제목, 접수번호, 대상자 검색..." 
              value={bondSearch} 
              onChange={(e) => setBondSearch(e.target.value)} 
            />
          </div>

          <div className="grid lg:grid-cols-2 gap-6 min-h-[500px]">
            {/* Table Area */}
            <div className="border rounded-xl overflow-hidden bg-white">
              <div className="overflow-auto max-h-[600px]">
                <table className="w-full text-sm border-collapse">
                  <thead className="bg-slate-50 sticky top-0 z-10">
                    <tr className="border-b border-slate-200">
                      <th className="px-4 py-3 text-left font-semibold text-slate-900">제목</th>
                      <th className="px-4 py-3 text-left font-semibold text-slate-900 w-16">회차</th>
                      <th className="px-4 py-3 text-right font-semibold text-slate-900 w-32">금액(억원)</th>
                      <th className="px-4 py-3 text-left font-semibold text-slate-900 w-32">접수번호</th>
                      <th className="px-4 py-3 text-center font-semibold text-slate-900 w-16">원문</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredRecords.length > 0 ? (
                      filteredRecords.map((record: any) => {
                        const key = getRecordKey(record);
                        const isSelected = (selectedRecord && getRecordKey(selectedRecord) === key);
                        const url = getKindDisclosureUrl(record);
                        return (
                          <tr 
                            key={key} 
                            className={cn(
                              "cursor-pointer hover:bg-slate-50 transition-colors",
                              isSelected ? "bg-blue-50/50" : ""
                            )}
                            onClick={() => setSelectedBondKey(key)}
                          >
                            <td className="px-4 py-3 font-medium text-slate-900">{record.title || "-"}</td>
                            <td className="px-4 py-3 text-slate-600">{getField(record, "회차") || "-"}</td>
                            <td className="px-4 py-3 text-right text-slate-600 tabular-nums">{formatHundredMillion(getField(record, "발행금액"))}</td>
                            <td className="px-4 py-3 text-slate-400 font-mono text-[11px]">{record.rcept_no || "-"}</td>
                            <td className="px-4 py-3 text-center">
                              {url ? (
                                <a 
                                  href={url} 
                                  target="_blank" 
                                  rel="noopener noreferrer" 
                                  className="inline-flex items-center justify-center p-1.5 rounded-md hover:bg-slate-200 text-slate-500 transition-colors"
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
                        <td colSpan={5} className="px-4 py-12 text-center text-slate-400">
                          {bondSummary ? "검색 결과가 없습니다." : "파싱 결과를 불러오면 채권 정보가 표시됩니다."}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Detail Area */}
            <div className="border rounded-xl bg-slate-50/50 p-6 space-y-6 overflow-auto max-h-[600px]">
              {selectedRecord ? (
                <>
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-700 text-[10px] font-bold">
                        {getCorrectionLabel(selectedRecord)}
                      </span>
                      <code className="text-[11px] text-slate-400 font-mono">
                        {selectedRecord.family_id || selectedRecord.rcept_no}
                      </code>
                    </div>
                    <h3 className="text-lg font-bold text-slate-900">{selectedRecord.title}</h3>
                  </div>

                  <div className="grid grid-cols-2 gap-x-8 gap-y-3 border-y border-slate-200 py-4">
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
                        <span className="text-[11px] text-slate-400 font-medium">{label}</span>
                        <span className="text-sm text-slate-700 font-semibold">{String(value || "-")}</span>
                      </div>
                    ))}
                  </div>

                  <div className="space-y-3">
                    <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">정정공시 기록</h4>
                    <div className="space-y-2">
                      {(() => {
                        const family = bondSummary?.families?.[selectedRecord.family_id];
                        const members = Array.isArray(family?.members) ? family.members : [];
                        if (members.length === 0) return <p className="text-xs text-slate-400">정정 기록이 없습니다.</p>;
                        return members.map((member: any) => (
                          <div 
                            key={member.rcept_no} 
                            className={cn(
                              "flex items-center gap-3 p-2 rounded-lg border",
                              member.sequence === selectedRecord.current_sequence 
                                ? "bg-white border-blue-200 shadow-sm" 
                                : "bg-slate-100/50 border-slate-200 opacity-60"
                            )}
                          >
                            <span className="w-5 h-5 flex items-center justify-center rounded-full bg-slate-900 text-white text-[10px] font-bold">
                              {Number(member.sequence || 0) + 1}
                            </span>
                            <div className="flex flex-col">
                              <code className="text-[11px] font-mono font-bold text-slate-700">{member.rcept_no}</code>
                              <span className="text-[9px] text-slate-400">acpt_no: {member.acpt_no}</span>
                            </div>
                          </div>
                        ));
                      })()}
                    </div>
                  </div>

                  <div className="space-y-3">
                    <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">발행 대상자</h4>
                    <div className="space-y-1.5">
                      {(() => {
                        const targets = getField(selectedRecord, "발행대상자");
                        if (!Array.isArray(targets) || targets.length === 0) return <p className="text-xs text-slate-400">대상자 정보가 없습니다.</p>;
                        return targets.map((target: any, idx: number) => {
                          const name = Array.isArray(target) ? target[0] : target;
                          const amount = Array.isArray(target) ? target[target.length - 1] : "";
                          return (
                            <div key={idx} className="flex justify-between items-center p-2 rounded-lg bg-white border border-slate-200">
                              <span className="text-xs text-slate-700 font-medium">{String(name || "-")}</span>
                              <strong className="text-xs text-slate-900 tabular-nums">{formatNumber(amount)}</strong>
                            </div>
                          );
                        });
                      })()}
                    </div>
                  </div>
                </>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-center space-y-3 opacity-40 py-24">
                  <div className="p-4 rounded-full bg-slate-200">
                    <Info className="h-8 w-8 text-slate-400" />
                  </div>
                  <p className="text-sm font-medium text-slate-500">행을 선택하면 채권 상세 정보가 표시됩니다.</p>
                </div>
              )}
            </div>
          </div>
        </CardContent>
        {status && (
          <div className={cn(
            "mx-6 mb-6 p-3 rounded-lg border text-xs font-medium",
            isErrorStatus ? "bg-red-50 border-red-200 text-red-700" : "bg-slate-50 border-slate-200 text-slate-700"
          )}>
            {status}
          </div>
        )}
      </Card>
    </main>
  );
}
