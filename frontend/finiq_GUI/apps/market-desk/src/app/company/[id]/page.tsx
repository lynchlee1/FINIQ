"use client"

import { useState, useEffect, useCallback, useMemo } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { ArrowLeft, Calendar, Filter, FileText, BadgeCheck, Loader2 } from "lucide-react";
import { Button } from "@finiq/ui";
import { Card, CardContent, CardHeader, CardTitle } from "@finiq/ui";
import { Input } from "@finiq/ui";
import { Label } from "@finiq/ui";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import dynamic from "next/dynamic";
import { cn } from "@finiq/ui/utils";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@finiq/ui";
import { Suspense } from "react";

const PriceChart = dynamic(() => import("@/components/PriceChart").then(mod => mod.PriceChart), { ssr: false });
const CompanyGraphViewer = dynamic(() => import("./CompanyGraphViewer").then(mod => mod.CompanyGraphViewer), { ssr: false });

interface TimelineItem {
  disclosed_at: string;
  group: string;
  title: string;
  submitter: string;
  acpt_no: string;
  trade_day: string;
}

interface ChartGroup {
  name: string;
  color: string;
  count: number;
  default_visible: boolean;
}

interface Insight {
  company: {
    company_name: string;
    market: string;
    disclosure_count: number;
    badges: string[];
  };
  chart: {
    candles: any[];
    markers: any[];
    groups: ChartGroup[];
  };
  timeline: TimelineItem[];
  display_frequency_label: string;
  range_start: string;
  range_end: string;
  visible_range_end: string;
  manual_start: string;
  manual_end: string;
  stock_code: string;
  inferred_stock_code: string;
  messages: string[];
}


function CompanyDetailContent() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const id = params.id as string;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [insight, setInsight] = useState<Insight | null>(null);
  const [groupVisibility, setGroupVisibility] = useState<Record<string, boolean>>({});
  const [crosshairData, setCrosshairData] = useState<any>(null);

  // Filters state
  const [startDate, setStartDate] = useState(searchParams.get("start_date") || "");
  const [endDate, setEndDate] = useState(searchParams.get("end_date") || "");
  const [rangeLabel, setRangeLabel] = useState(searchParams.get("range_label") || "검색기간");
  const [displayFrequency, setDisplayFrequency] = useState(searchParams.get("display_frequency") || "자동");
  const [stockCode, setStockCode] = useState(searchParams.get("stock_code") || "");

  const fetchInsight = useCallback(async () => {
    const classificationPath = searchParams.get("classification_path") || "";
    if (!classificationPath) {
      setLoading(false);
      return;
    }
    
    try {
      setLoading(true);
      const query = new URLSearchParams({
        classification_path: classificationPath,
        company_key: id,
        start_date: startDate,
        end_date: endDate,
        range_label: rangeLabel,
        display_frequency: displayFrequency,
        price_source: "quanti",
        quanti_dir: searchParams.get("price_dir") || "",
        stock_code: stockCode,
      });

      const response = await fetch(`/api/insight?${query.toString()}`);
      if (!response.ok) throw new Error("Failed to fetch insight");
      const data: Insight = await response.json();
      setInsight(data);
      setStartDate(data.manual_start);
      setEndDate(data.manual_end);
      setStockCode(data.stock_code || data.inferred_stock_code || "");

      // Initialize group visibility if not set
      if (Object.keys(groupVisibility).length === 0) {
        const visibility: Record<string, boolean> = {};
        const hasDefaultVisible = data.chart.groups.some(g => g.default_visible);
        data.chart.groups.forEach(g => {
          visibility[g.name] = hasDefaultVisible ? !!g.default_visible : true;
        });
        setGroupVisibility(visibility);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [id, searchParams, startDate, endDate, rangeLabel, displayFrequency, stockCode]);

  useEffect(() => {
    fetchInsight();
  }, [id]); // Initial load only

  const handleApplyFilters = () => {
    fetchInsight();
  };

  const filteredMarkers = useMemo(() => {
    if (!insight) return [];
    return insight.chart.markers.filter(m => groupVisibility[m.group]);
  }, [insight, groupVisibility]);

  const filteredTimeline = useMemo(() => {
    if (!insight) return [];
    return insight.timeline.filter(item => groupVisibility[item.group]);
  }, [insight, groupVisibility]);

  const toggleGroup = (name: string) => {
    setGroupVisibility(prev => ({ ...prev, [name]: !prev[name] }));
  };

  const formatNumber = (val: number) => new Intl.NumberFormat("ko-KR").format(val);

  const getToneClass = (open: number, close: number) => {
    const delta = close - open;
    if (delta > 0) return "text-red-500";
    if (delta < 0) return "text-blue-500";
    return "text-slate-500";
  };

  if (loading && !insight) {
    return <PageLoadingSpinner message="데이터를 불러오는 중입니다..." />;
  }

  return (
    <main className="flex flex-col gap-6 w-full">
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <Button variant="outline" size="icon" onClick={() => router.back()} className="dark:border-[#30363d] dark:text-slate-400 dark:hover:bg-[#21262d] dark:hover:text-slate-200">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white">{insight?.company?.company_name || '회사 정보 없음'}</h2>
              {insight?.company?.market && (
                <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-[#21262d] text-xs font-bold text-slate-600 dark:text-slate-400">
                  {insight.company.market}
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-2 text-sm text-slate-500 dark:text-slate-400 font-medium">
              <span>공시 {formatNumber(insight?.company?.disclosure_count || 0)}건</span>
              {insight?.company?.badges?.map((badge, i) => (
                <span key={i}>· {badge}</span>
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {["1개월", "3개월", "6개월", "1년", "전체"].map((label) => (
            <Button
              key={label}
              variant={rangeLabel === label ? "default" : "outline"}
              size="sm"
              onClick={() => {
                setRangeLabel(label);
              }}
              className={rangeLabel === label ? "dark:bg-slate-100 dark:text-slate-900" : "dark:border-[#30363d] dark:text-slate-400 dark:hover:bg-[#21262d]"}
            >
              {label}
            </Button>
          ))}
        </div>
      </header>

      <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
        <CardContent className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 items-end">
            <div className="space-y-2">
              <Label className="dark:text-slate-300">시작일</Label>
              <Input type="date" value={startDate} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 dark:[color-scheme:dark]" onChange={(e) => {
                setStartDate(e.target.value);
                setRangeLabel("검색기간");
              }} />
            </div>
            <div className="space-y-2">
              <Label className="dark:text-slate-300">종료일</Label>
              <Input type="date" value={endDate} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200 dark:[color-scheme:dark]" onChange={(e) => {
                setEndDate(e.target.value);
                setRangeLabel("검색기간");
              }} />
            </div>
            <div className="space-y-2">
              <Label className="dark:text-slate-300">주기</Label>
              <Select value={displayFrequency} onValueChange={setDisplayFrequency}>
                <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                  <SelectItem value="자동">자동</SelectItem>
                  <SelectItem value="일봉">일봉</SelectItem>
                  <SelectItem value="주봉">주봉</SelectItem>
                  <SelectItem value="월봉">월봉</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="dark:text-slate-300">종목코드 (수동)</Label>
              <Input placeholder="000000" value={stockCode} onChange={(e) => setStockCode(e.target.value)} className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
            </div>
            <Button className="w-full" onClick={handleApplyFilters}>적용</Button>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="analysis" className="w-full">
        <div className="flex items-center justify-between mb-4">
          <TabsList className="dark:bg-[#0d1117] dark:border-[#30363d]">
            <TabsTrigger value="analysis" className="data-[state=active]:bg-[#21262d] data-[state=active]:text-white">공시&주가 차트</TabsTrigger>
            <TabsTrigger value="graph" className="data-[state=active]:bg-[#21262d] data-[state=active]:text-white">관계망 그래프</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="analysis" className="flex flex-col gap-6 m-0">
          <Card className="overflow-hidden dark:bg-[#161b22] dark:border-[#30363d]">
        <CardHeader className="bg-slate-50 dark:bg-[#0d1117] border-b dark:border-[#30363d] py-3 px-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-6">
              {crosshairData ? (
                <div className="flex items-center gap-4 text-xs font-mono">
                  <span className="font-bold dark:text-white">{crosshairData.time}</span>
                  <div className={cn("flex gap-2", getToneClass(crosshairData.open, crosshairData.close))}>
                    <span>O {formatNumber(crosshairData.open)}</span>
                    <span>H {formatNumber(crosshairData.high)}</span>
                    <span>L {formatNumber(crosshairData.low)}</span>
                    <span>C {formatNumber(crosshairData.close)}</span>
                    <span className="text-slate-500 dark:text-slate-500">V {formatNumber(crosshairData.volume)}</span>
                  </div>
                </div>
              ) : (
                <span className="text-xs text-slate-400 dark:text-slate-600">데이터 대기 중</span>
              )}
            </div>
            <div className="flex gap-2">
              {insight?.chart?.groups?.map((group) => (
                <button
                  key={group.name}
                  onClick={() => toggleGroup(group.name)}
                  className={cn(
                    "flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-bold border transition-all",
                    groupVisibility[group.name] 
                      ? "bg-white dark:bg-[#21262d] border-slate-300 dark:border-[#484f58] shadow-sm dark:text-white" 
                      : "bg-slate-100 dark:bg-[#0d1117] border-transparent dark:border-transparent text-slate-400 dark:text-slate-600 opacity-60 dark:opacity-40"
                  )}
                >
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: group.color }} />
                  {group.name}
                  <span className="ml-1 opacity-60">{group.count}</span>
                </button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-6 h-[500px]">
          {insight && (
            <PriceChart
              data={insight.chart.candles}
              markers={filteredMarkers}
              title={`${insight.company.company_name} · ${insight.display_frequency_label}`}
              subtitle={`${insight.range_start} ~ ${insight.visible_range_end || insight.range_end} · Parquet`}
              onCrosshairMove={setCrosshairData}
            />
          )}
        </CardContent>
      </Card>

      <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg dark:text-white">공시 타임라인</CardTitle>
          <div className="px-2 py-1 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 text-xs font-bold">
            {formatNumber(filteredTimeline.length)}건
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 dark:bg-[#0d1117] border-y dark:border-[#30363d] text-slate-500 dark:text-slate-400 font-medium">
                <tr>
                  <th className="px-6 py-3">공시일시</th>
                  <th className="px-6 py-3">그룹</th>
                  <th className="px-6 py-3">보고서명</th>
                  <th className="px-6 py-3">제출인</th>
                  <th className="px-6 py-3">접수번호</th>
                  <th className="px-6 py-3">거래일</th>
                </tr>
              </thead>
              <tbody className="divide-y dark:divide-[#30363d]">
                {filteredTimeline.map((item, i) => (
                  <tr key={i} className="hover:bg-slate-50 dark:hover:bg-[#21262d] transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap text-slate-500 dark:text-slate-400 font-mono text-xs">{item.disclosed_at}</td>
                    <td className="px-6 py-4">
                      <span className="flex items-center gap-1.5 font-bold text-xs dark:text-slate-200">
                        <span 
                          className="w-2 h-2 rounded-full" 
                          style={{ backgroundColor: insight?.chart?.groups?.find(g => g.name === item.group)?.color }} 
                        />
                        {item.group}
                      </span>
                    </td>
                    <td className="px-6 py-4 font-medium text-slate-900 dark:text-slate-100">{item.title}</td>
                    <td className="px-6 py-4 text-slate-600 dark:text-slate-400">{item.submitter}</td>
                    <td className="px-6 py-4 text-slate-400 dark:text-slate-500 font-mono text-xs">{item.acpt_no}</td>
                    <td className="px-6 py-4 text-slate-500 dark:text-slate-400 font-mono text-xs">{item.trade_day || "-"}</td>
                  </tr>
                ))}
                {filteredTimeline.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center text-slate-400 dark:text-slate-600 italic">
                      표시할 공시가 없습니다.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
        </TabsContent>

        <TabsContent value="graph" className="m-0">
          <CompanyGraphViewer />
        </TabsContent>
      </Tabs>
    </main>
  );
}

export default function CompanyDetail() {
  return (
    <Suspense fallback={<PageLoadingSpinner message="데이터를 불러오는 중입니다..." />}>
      <CompanyDetailContent />
    </Suspense>
  );
}
