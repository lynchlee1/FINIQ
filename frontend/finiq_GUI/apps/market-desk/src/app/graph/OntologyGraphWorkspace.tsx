"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import {
  AlertTriangle,
  FileText,
  LineChart,
  Loader2,
  Maximize2,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import { apiGet } from "@/api/client";
import { ActionDock } from "@/components/ui/ActionDock";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";

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
  stock_code: string;
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

type CandleItem = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  color?: string;
};

type MarkerItem = {
  time: string;
  group?: string;
  title?: string;
  submitter?: string;
  disclosed_at?: string;
  acpt_no?: string;
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
    candles: CandleItem[];
    markers: MarkerItem[];
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

const DISPLAY_FREQUENCY_OPTIONS = ["일봉", "5일봉", "20일봉", "월봉"] as const;

function clampChartZoomSensitivity(value: number) {
  if (!Number.isFinite(value)) {
    return 0.55;
  }
  return Math.min(Math.max(value, 0.2), 1.5);
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

function normalizeStockCode(value: string) {
  const digits = value.replace(/\D/g, "");
  return digits ? `A${digits.padStart(6, "0").slice(-6)}` : "";
}

export function OntologyGraphWorkspace() {
  const [status, setStatus] = useState<OntologyStatus | null>(null);
  const [selectedCompany, setSelectedCompany] = useState<OntologyCompany | null>(null);
  const [panel, setPanel] = useState<OntologyPanel | null>(null);
  const [keyword, setKeyword] = useState("");
  const [displayFrequency, setDisplayFrequency] = useState<(typeof DISPLAY_FREQUENCY_OPTIONS)[number]>("일봉");
  const [requestedPanelKey, setRequestedPanelKey] = useState("");
  const [chartZoomSensitivity, setChartZoomSensitivity] = useState(0.55);
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
      const keywordText = keyword.trim().toUpperCase();
      const query = new URLSearchParams({
        keyword: keywordText.startsWith("A") ? normalizeStockCode(keywordText).slice(1) : keyword,
        market: "전체",
        limit: "30",
      });
      const data = await apiGet<OntologyCompaniesPayload>(`/api/ontology/companies?${query.toString()}`);
      setSelectedCompany((current) => {
        if (current && data.companies.some((company) => company.stock_code === current.stock_code)) {
          return current;
        }
        return data.companies[0] ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "회사 목록을 불러오지 못했습니다.");
    } finally {
      setLoadingCompanies(false);
    }
  }, [keyword]);

  const loadPanel = useCallback(async () => {
    if (!selectedCompany) {
      setPanel(null);
      return;
    }
    setLoadingPanel(true);
    const requestKey = `${selectedCompany.stock_code}:${displayFrequency}`;
    setRequestedPanelKey(requestKey);
    try {
      const query = new URLSearchParams({
        company_id: selectedCompany.stock_code,
        market: "전체",
        display_frequency: displayFrequency,
      });
      const data = await apiGet<OntologyPanel>(`/api/ontology/company-panel?${query.toString()}`);
      setPanel(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "분석 데이터를 불러오지 못했습니다.");
    } finally {
      setLoadingPanel(false);
    }
  }, [displayFrequency, selectedCompany]);

  useEffect(() => {
    loadStatus();
    loadCompanies();
  }, [loadCompanies, loadStatus]);

  useEffect(() => {
    loadPanel();
  }, [loadPanel]);

  const selectedCompanyLabel = selectedCompany
    ? `${selectedCompany.company_name} (${selectedCompany.stock_code})`
    : "선택된 회사 없음";
  const statusMessages = useMemo(() => [...(status?.messages ?? []), ...(error ? [error] : [])], [error, status]);
  const chartRangeText = panel ? `${panel.range_start} - ${panel.range_end} / ${panel.display_frequency}` : "전체 기간";
  const chartMetaText = `${selectedCompanyLabel} ${chartRangeText}`;
  const chartIsLoading =
    loadingCompanies ||
    loadingPanel ||
    (!!selectedCompany && requestedPanelKey !== `${selectedCompany.stock_code}:${displayFrequency}`);
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
      {chartIsLoading ? (
        <PageLoadingSpinner message="공시와 주가를 맞추는 중입니다..." />
      ) : panel && panel.chart.candles.length > 0 ? (
        <PriceChart
          data={panel.chart.candles}
          markers={panel.chart.markers}
          title={selectedCompanyLabel}
          subtitle={`${panel.range_start} - ${panel.range_end} / ${panel.display_frequency}`}
          showHeader={false}
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
            <CardContent className="pt-6">
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input
                  id="ontology-stock-keyword"
                  aria-label="종목 선택"
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  placeholder="종목명 또는 A000000"
                  className="h-9 sm:max-w-sm"
                />
                <Button variant="outline" size="sm" className="h-9" onClick={loadCompanies} disabled={loadingCompanies}>
                  {loadingCompanies ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                  검색
                </Button>
              </div>
              <MessageBox messages={statusMessages} />
            </CardContent>
          </Card>
        </section>

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
                      {chartMetaText}
                    </CardDescription>
                  </div>
                  <div className="flex flex-col gap-2 sm:items-end">
                    <div className="flex flex-wrap gap-2">
                      <Button variant="outline" size="sm" onClick={() => setChartFullscreen(true)} disabled={chartIsLoading}>
                        <Maximize2 className="h-4 w-4" />
                        전체화면
                      </Button>
                      <Button variant="outline" size="sm" onClick={loadPanel} disabled={!selectedCompany || chartIsLoading}>
                        {chartIsLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                        새로고침
                      </Button>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {DISPLAY_FREQUENCY_OPTIONS.map((option) => (
                        <Button
                          key={option}
                          type="button"
                          variant={displayFrequency === option ? "default" : "outline"}
                          size="sm"
                          className="h-8"
                          onClick={() => setDisplayFrequency(option)}
                        >
                          {option}
                        </Button>
                      ))}
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {renderPriceChart()}
              </CardContent>
            </Card>
        </section>

        <section>
            <Card className="rounded-lg dark:border-[#30363d] dark:bg-[#161b22]">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg dark:text-white">
                  <FileText className="h-5 w-5" />
                  공시 타임라인
                </CardTitle>
                <CardDescription className="dark:text-slate-400">차트에 표시된 전체 기간 공시</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="max-h-[460px] overflow-y-auto pr-1">
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

        {chartFullscreen ? (
          <div className="fixed inset-0 z-50 flex flex-col bg-white p-4 dark:bg-[#0d1117]">
            <div className="mb-3 flex flex-col gap-3 border-b border-slate-200 pb-3 sm:flex-row sm:items-center sm:justify-between dark:border-[#30363d]">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">주가-공시 차트</p>
                <h2 className="truncate text-xl font-bold text-slate-950 dark:text-slate-100">{selectedCompanyLabel}</h2>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  {chartRangeText}
                </p>
              </div>
              <div className="flex flex-col gap-2 sm:items-end">
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" onClick={loadPanel} disabled={!selectedCompany || chartIsLoading}>
                    {chartIsLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                    새로고침
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setChartFullscreen(false)}>
                    <X className="h-4 w-4" />
                    전체화면 닫기
                  </Button>
                </div>
                <div className="flex flex-wrap gap-1">
                  {DISPLAY_FREQUENCY_OPTIONS.map((option) => (
                    <Button
                      key={option}
                      type="button"
                      variant={displayFrequency === option ? "default" : "outline"}
                      size="sm"
                      className="h-8"
                      onClick={() => setDisplayFrequency(option)}
                    >
                      {option}
                    </Button>
                  ))}
                </div>
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
