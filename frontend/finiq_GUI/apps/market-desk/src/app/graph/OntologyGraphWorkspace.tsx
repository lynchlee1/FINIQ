"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import {
  AlertTriangle,
  Building2,
  Calendar,
  FileText,
  LineChart,
  Loader2,
  Maximize2,
  RefreshCw,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import { apiGet } from "@/api/client";
import { ActionDock } from "@/components/ui/ActionDock";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { formatInteger } from "@/lib/format";

const PriceChart = dynamic(() => import("@/components/PriceChart").then((mod) => mod.PriceChart), {
  ssr: false,
  loading: () => <PageLoadingSpinner message="차트를 준비하는 중입니다..." />,
});

type OntologyStatus = {
  kind: {
    manifest_path: string;
    summary: {
      companies?: number;
      disclosures?: number;
      shards?: number;
    };
    shard_years: string[];
  };
  quantiwise: {
    directory: string;
    available_items: string[];
    mapped_companies: number;
  };
  messages: string[];
};

type OntologyCompany = {
  company_id: string;
  company_name: string;
  market: string;
  disclosure_count: number;
  first_disclosed_date: string;
  last_disclosed_date: string;
  has_price_data: boolean;
};

type OntologyCompaniesPayload = {
  companies: OntologyCompany[];
  total: number;
};

type ChartGroup = {
  name: string;
  color: string;
  count: number;
  default_visible: boolean;
};

type TimelineItem = {
  disclosed_at: string;
  group: string;
  title: string;
  submitter: string;
  acpt_no: string;
  trade_day: string;
};

type OntologyPanel = {
  company: {
    company_id: string;
    stock_code: string;
    company_name: string;
    market: string;
  };
  range_start: string;
  range_end: string;
  display_frequency: string;
  chart: {
    candles: any[];
    markers: any[];
    groups: ChartGroup[];
  };
  timeline: TimelineItem[];
  summary: {
    visible_candles: number;
    visible_disclosures: number;
    after_close_disclosures: number;
    first_disclosure: string;
    last_disclosure: string;
    top_groups: Array<{ name: string; count: number }>;
  };
  messages: string[];
};

type ChartViewMode = "chart" | "timeline";

const CHART_VIEW_MODES = [
  { id: "chart", label: "차트", icon: LineChart },
  { id: "timeline", label: "공시 타임라인", icon: FileText },
] as const;

function dateInputValue(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function currentYearStart() {
  const now = new Date();
  return `${now.getFullYear()}-01-01`;
}

function todayInputValue() {
  return dateInputValue(new Date());
}

function clampChartZoomSensitivity(value: number) {
  if (!Number.isFinite(value)) {
    return 0.55;
  }
  return Math.min(Math.max(value, 0.2), 1.5);
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 py-2 text-sm last:border-0 dark:border-[#30363d]">
      <span className="shrink-0 font-medium text-slate-500 dark:text-slate-400">{label}</span>
      <span className="min-w-0 break-all text-right font-semibold text-slate-950 dark:text-slate-100" title={value}>
        {value || "-"}
      </span>
    </div>
  );
}

function MessageBox({ messages }: { messages: string[] }) {
  if (messages.length === 0) return null;
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/70 dark:bg-amber-950/30 dark:text-amber-200">
      <div className="flex gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="space-y-1">
          {messages.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      </div>
    </div>
  );
}

export function OntologyGraphWorkspace() {
  const [status, setStatus] = useState<OntologyStatus | null>(null);
  const [companies, setCompanies] = useState<OntologyCompany[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<OntologyCompany | null>(null);
  const [panel, setPanel] = useState<OntologyPanel | null>(null);
  const [keyword, setKeyword] = useState("");
  const [market, setMarket] = useState("전체");
  const [startDate, setStartDate] = useState(currentYearStart());
  const [endDate, setEndDate] = useState(todayInputValue());
  const [titleKeyword, setTitleKeyword] = useState("");
  const [displayFrequency, setDisplayFrequency] = useState("자동");
  const [chartZoomSensitivity, setChartZoomSensitivity] = useState(0.55);
  const [activeChartView, setActiveChartView] = useState<ChartViewMode>("chart");
  const [chartFullscreen, setChartFullscreen] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [loadingCompanies, setLoadingCompanies] = useState(false);
  const [loadingPanel, setLoadingPanel] = useState(false);
  const [error, setError] = useState("");

  const loadStatus = useCallback(async () => {
    setLoadingStatus(true);
    try {
      const data = await apiGet<OntologyStatus>("/api/ontology/status");
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "원천 정보를 불러오지 못했습니다.");
    } finally {
      setLoadingStatus(false);
    }
  }, []);

  const loadCompanies = useCallback(async () => {
    setLoadingCompanies(true);
    try {
      const query = new URLSearchParams({
        keyword,
        market,
        limit: "30",
      });
      const data = await apiGet<OntologyCompaniesPayload>(`/api/ontology/companies?${query.toString()}`);
      setCompanies(data.companies);
      setSelectedCompany((current) => {
        if (current && data.companies.some((company) => company.company_id === current.company_id)) {
          return current;
        }
        return data.companies[0] ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "회사 목록을 불러오지 못했습니다.");
    } finally {
      setLoadingCompanies(false);
    }
  }, [keyword, market]);

  const loadPanel = useCallback(async () => {
    if (!selectedCompany) {
      setPanel(null);
      return;
    }
    setLoadingPanel(true);
    try {
      const query = new URLSearchParams({
        company_id: selectedCompany.company_id,
        start_date: startDate,
        end_date: endDate,
        title_keyword: titleKeyword,
        market,
        display_frequency: displayFrequency,
      });
      const data = await apiGet<OntologyPanel>(`/api/ontology/company-panel?${query.toString()}`);
      setPanel(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "분석 데이터를 불러오지 못했습니다.");
    } finally {
      setLoadingPanel(false);
    }
  }, [displayFrequency, endDate, market, selectedCompany, startDate, titleKeyword]);

  useEffect(() => {
    loadStatus();
    loadCompanies();
  }, [loadCompanies, loadStatus]);

  useEffect(() => {
    loadPanel();
  }, [loadPanel]);

  const selectedCompanyLabel = selectedCompany
    ? `${selectedCompany.company_name} (${selectedCompany.company_id})`
    : "선택된 회사 없음";
  const statusMessages = useMemo(() => [...(status?.messages ?? []), ...(error ? [error] : [])], [error, status]);
  const handleChartZoomSensitivityChange = (event: ChangeEvent<HTMLInputElement> | FormEvent<HTMLInputElement>) => {
    setChartZoomSensitivity(clampChartZoomSensitivity(Number(event.currentTarget.value)));
  };
  const handleChartZoomSensitivityPercentChange = (event: ChangeEvent<HTMLInputElement>) => {
    setChartZoomSensitivity(clampChartZoomSensitivity(Number(event.currentTarget.value) / 100));
  };

  const renderPriceChart = (expanded = false) => (
    <div
      className={cn(
        "rounded-lg border border-slate-200 bg-white p-4 dark:border-[#30363d] dark:bg-[#0d1117]",
        expanded ? "h-full min-h-0" : "h-[min(68vh,720px)] min-h-[520px]",
      )}
    >
      {loadingPanel ? (
        <PageLoadingSpinner message="공시와 주가를 맞추는 중입니다..." />
      ) : panel && panel.chart.candles.length > 0 ? (
        <PriceChart
          data={panel.chart.candles}
          markers={panel.chart.markers}
          title={selectedCompanyLabel}
          subtitle={`${panel.range_start} - ${panel.range_end} / ${panel.display_frequency}`}
          zoomSensitivity={chartZoomSensitivity}
        />
      ) : (
        <div className="flex h-full min-h-[420px] items-center justify-center text-center">
          <div>
            <LineChart className="mx-auto h-8 w-8 text-slate-400" />
            <p className="mt-3 font-semibold text-slate-900 dark:text-slate-100">표시할 차트 데이터가 없습니다.</p>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">회사와 기간을 선택한 뒤 새로고침하세요.</p>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="relative action-dock-host flex w-full flex-col gap-5 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
      <div className="flex w-full flex-col gap-5">
        <section>
          <Card className="rounded-lg dark:border-[#30363d] dark:bg-[#161b22]">
            <CardHeader className="pb-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-xl dark:text-white">
                    <LineChart className="h-5 w-5" />
                    Graph View
                  </CardTitle>
                  <CardDescription className="mt-2 dark:text-slate-400">
                    {selectedCompanyLabel} · {startDate} - {endDate}
                  </CardDescription>
                </div>
                <div className="inline-flex self-start rounded-md border border-slate-200 p-1 dark:border-[#30363d]">
                  {CHART_VIEW_MODES.map((mode) => {
                    const Icon = mode.icon;
                    return (
                      <Button
                        key={mode.id}
                        type="button"
                        variant={activeChartView === mode.id ? "default" : "ghost"}
                        size="sm"
                        className="h-8"
                        onClick={() => setActiveChartView(mode.id)}
                      >
                        <Icon className="mr-2 h-4 w-4" />
                        {mode.label}
                      </Button>
                    );
                  })}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <MessageBox messages={statusMessages} />
            </CardContent>
          </Card>
        </section>

        {activeChartView === "chart" ? (
          <>
            <section>
            <Card className="rounded-lg dark:border-[#30363d] dark:bg-[#161b22]">
              <CardHeader className="pb-3">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2 text-lg dark:text-white">
                      <LineChart className="h-5 w-5" />
                      주가-공시 차트
                    </CardTitle>
                    <CardDescription className="mt-2 dark:text-slate-400">
                      KIND 공시 이벤트와 Quantiwise 가격 데이터를 같은 기간 축에서 비교합니다.
                    </CardDescription>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={() => setChartFullscreen(true)} disabled={loadingPanel}>
                      <Maximize2 className="h-4 w-4" />
                      전체화면
                    </Button>
                    <Button variant="outline" size="sm" onClick={loadPanel} disabled={!selectedCompany || loadingPanel}>
                      {loadingPanel ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                      새로고침
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-lg border border-slate-200 p-3 dark:border-[#30363d]">
                  <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                    <SlidersHorizontal className="h-4 w-4" />
                    분석 조건
                  </div>
                  <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                    <div className="min-w-[140px] flex-1 space-y-1.5">
                      <Label htmlFor="ontology-start-date">시작일</Label>
                      <Input id="ontology-start-date" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
                    </div>
                    <div className="min-w-[140px] flex-1 space-y-1.5">
                      <Label htmlFor="ontology-end-date">종료일</Label>
                      <Input id="ontology-end-date" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
                    </div>
                    <div className="min-w-[180px] flex-[2] space-y-1.5">
                      <Label htmlFor="ontology-title-keyword">공시 제목</Label>
                      <Input
                        id="ontology-title-keyword"
                        value={titleKeyword}
                        onChange={(event) => setTitleKeyword(event.target.value)}
                        placeholder="예: 전환사채"
                      />
                    </div>
                    <div className="min-w-[120px] flex-1 space-y-1.5">
                      <Label htmlFor="ontology-frequency">빈도</Label>
                      <select
                        id="ontology-frequency"
                        value={displayFrequency}
                        onChange={(event) => setDisplayFrequency(event.target.value)}
                        className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-100"
                      >
                        <option value="자동">자동</option>
                        <option value="일봉">일봉</option>
                        <option value="주봉">주봉</option>
                        <option value="월봉">월봉</option>
                      </select>
                    </div>
                  </div>
                </div>

                {renderPriceChart()}
              </CardContent>
            </Card>
            </section>

            <section>
            <Card className="rounded-lg dark:border-[#30363d] dark:bg-[#161b22]">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg dark:text-white">
                  <Building2 className="h-5 w-5" />
                  분석 요약
                </CardTitle>
                <CardDescription className="dark:text-slate-400">{selectedCompanyLabel}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-lg border border-slate-200 px-4 py-2 dark:border-[#30363d]">
                  <DetailRow label="캔들" value={formatInteger(panel?.summary.visible_candles)} />
                  <DetailRow label="공시" value={formatInteger(panel?.summary.visible_disclosures)} />
                  <DetailRow label="장후 공시" value={formatInteger(panel?.summary.after_close_disclosures)} />
                  <DetailRow label="마커" value={formatInteger(panel?.chart.markers.length)} />
                </div>
                <div className="space-y-2 text-sm text-slate-600 dark:text-slate-300">
                  <div className="flex items-center gap-2">
                    <Calendar className="h-4 w-4 text-slate-400" />
                    <span>{panel?.summary.first_disclosure || "-"} - {panel?.summary.last_disclosure || "-"}</span>
                  </div>
                  {(panel?.summary.top_groups ?? []).map((group) => (
                    <div key={group.name} className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2 dark:border-[#30363d]">
                      <span>{group.name}</span>
                      <span className="font-semibold tabular-nums">{formatInteger(group.count)}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
            </section>

          </>
        ) : null}

        {activeChartView === "timeline" ? (
          <section>
          <Card className="rounded-lg dark:border-[#30363d] dark:bg-[#161b22]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg dark:text-white">
                <FileText className="h-5 w-5" />
                공시 타임라인
              </CardTitle>
              <CardDescription className="dark:text-slate-400">차트에 표시된 기간과 같은 범위</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="max-h-[calc(100vh-18rem)] overflow-y-auto pr-1">
                {panel?.timeline.length ? (
                  <div className="divide-y divide-slate-100 dark:divide-[#30363d]">
                    {panel.timeline.map((item) => (
                      <div key={item.acpt_no} className="space-y-2 py-3">
                        <div className="text-sm text-slate-500 dark:text-slate-400">
                          <p className="font-medium text-slate-700 dark:text-slate-300">{item.disclosed_at}</p>
                          <p className="mt-1 text-xs">마커 {item.trade_day || "-"}</p>
                        </div>
                        <div className="min-w-0">
                          <p className="font-semibold leading-snug text-slate-950 dark:text-slate-100">{item.title}</p>
                          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{item.submitter}</p>
                        </div>
                        <div className="text-left">
                          <span className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 dark:border-[#30363d] dark:text-slate-300">
                            {item.group}
                          </span>
                          <p className="mt-2 text-xs text-slate-400">{item.acpt_no}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="rounded-lg border border-slate-200 p-4 text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
                    표시할 공시가 없습니다.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
          </section>
        ) : null}

        {chartFullscreen ? (
          <div className="fixed inset-0 z-50 flex flex-col bg-white p-4 dark:bg-[#0d1117]">
            <div className="mb-3 flex flex-col gap-3 border-b border-slate-200 pb-3 sm:flex-row sm:items-center sm:justify-between dark:border-[#30363d]">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">주가-공시 차트</p>
                <h2 className="truncate text-xl font-bold text-slate-950 dark:text-slate-100">{selectedCompanyLabel}</h2>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  {panel ? `${panel.range_start} - ${panel.range_end} / ${panel.display_frequency}` : `${startDate} - ${endDate}`}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={loadPanel} disabled={!selectedCompany || loadingPanel}>
                  {loadingPanel ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  새로고침
                </Button>
                <Button variant="outline" size="sm" onClick={() => setChartFullscreen(false)}>
                  <X className="h-4 w-4" />
                  전체화면 닫기
                </Button>
              </div>
            </div>
            <div className="min-h-0 flex-1">{renderPriceChart(true)}</div>
          </div>
        ) : null}
      </div>

      <ActionDock
        activityActive={loadingStatus || loadingCompanies || loadingPanel}
        activityContent={
          <div className="text-sm text-slate-600 dark:text-slate-300">
            {loadingPanel ? "분석 데이터를 불러오는 중입니다." : loadingCompanies ? "회사 목록을 불러오는 중입니다." : "대기 중입니다."}
          </div>
        }
        notificationActive={!!error}
        notificationContent={
          <div className={error ? "text-sm text-red-600 dark:text-red-300" : "text-sm text-slate-600 dark:text-slate-300"}>
            {error || "알림 없음"}
          </div>
        }
        settingsTitle="설정"
        settingsContent={
          <div className="space-y-4">
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                <Search className="h-4 w-4" />
                회사 선택
              </div>
              <Input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="회사명 또는 코드" />
              <div className="flex gap-2">
                <select
                  value={market}
                  onChange={(event) => setMarket(event.target.value)}
                  className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-100"
                >
                  <option value="전체">전체</option>
                  <option value="코스피">코스피</option>
                  <option value="코스닥">코스닥</option>
                  <option value="코넥스">코넥스</option>
                </select>
                <Button className="flex-1" onClick={loadCompanies} disabled={loadingCompanies}>
                  {loadingCompanies ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                  검색
                </Button>
              </div>
              <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
                {companies.length === 0 ? (
                  <p className="rounded-lg border border-slate-200 p-3 text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
                    조건에 맞는 회사가 없습니다.
                  </p>
                ) : (
                  companies.map((company) => {
                    const active = selectedCompany?.company_id === company.company_id;
                    return (
                      <button
                        key={`${company.company_id}-${company.company_name}-${company.market}`}
                        type="button"
                        onClick={() => {
                          setSelectedCompany(company);
                          setActiveChartView("chart");
                        }}
                        className={cn(
                          "w-full rounded-lg border p-3 text-left transition-colors",
                          active
                            ? "border-slate-900 bg-slate-100 dark:border-slate-100 dark:bg-[#21262d]"
                            : "border-slate-200 bg-white hover:border-slate-400 dark:border-[#30363d] dark:bg-[#0d1117]",
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate font-semibold text-slate-950 dark:text-slate-100">{company.company_name}</p>
                            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                              {company.company_id} · {company.market}
                            </p>
                          </div>
                          <span
                            className={cn(
                              "rounded-md border px-2 py-1 text-[11px] font-medium",
                              company.has_price_data
                                ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-200"
                                : "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200",
                            )}
                          >
                            {company.has_price_data ? "가격 있음" : "가격 없음"}
                          </span>
                        </div>
                        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                          공시 {formatInteger(company.disclosure_count)}건 · {company.first_disclosed_date} - {company.last_disclosed_date}
                        </p>
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor="ontology-chart-zoom-sensitivity" className="font-semibold dark:text-slate-200">
                  확대/축소 민감도
                </Label>
                <div className="flex items-center gap-1">
                  <Input
                    id="ontology-chart-zoom-sensitivity-value"
                    type="number"
                    min="20"
                    max="150"
                    step="5"
                    value={Math.round(chartZoomSensitivity * 100)}
                    onChange={handleChartZoomSensitivityPercentChange}
                    className="h-8 w-20 text-right tabular-nums dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                  />
                  <span className="text-sm text-slate-500 dark:text-slate-400">%</span>
                </div>
              </div>
              <Input
                id="ontology-chart-zoom-sensitivity"
                type="range"
                min="0.2"
                max="1.5"
                step="0.05"
                value={chartZoomSensitivity}
                onInput={handleChartZoomSensitivityChange}
                onChange={handleChartZoomSensitivityChange}
              />
              <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
                <span>느림</span>
                <span>빠름</span>
              </div>
            </div>
          </div>
        }
      />
    </div>
  );
}
