"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { AlertTriangle, FileText, LineChart, Loader2, Maximize2, RefreshCw, Search, SlidersHorizontal, X } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import { apiGet } from "@/api/client";
import { ActionDock } from "@/components/ui/ActionDock";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import type { OntologyCompany, OntologyPanel } from "../OntologyGraphWorkspace";

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
  disclosure_groups: string[];
  messages: string[];
};

type OntologyCompaniesPayload = {
  companies: OntologyCompany[];
  total: number;
};

const DISPLAY_FREQUENCY_OPTIONS = ["일봉", "3일봉", "5일봉", "7일봉", "20일봉", "월봉"] as const;
const DISCLOSURE_GROUP_ALL = "전체";
const MARKER_STYLE_GROUP_ALL = "전체";
const CHART_TYPE_OPTIONS = [
  { value: "candlestick", label: "캔들" },
  { value: "line", label: "종가선" },
] as const;
const MARKER_PLACEMENT_OPTIONS = [
  { value: "default", label: "공시별 기본" },
  { value: "paneTop", label: "차트 상단" },
  { value: "paneBottom", label: "차트 하단" },
  { value: "aboveBar", label: "캔들 위" },
  { value: "belowBar", label: "캔들 아래" },
  { value: "inBar", label: "캔들 안" },
] as const;
const MARKER_SHAPE_OPTIONS = [
  { value: "default", label: "공시별 기본" },
  { value: "circle", label: "원" },
  { value: "square", label: "사각형" },
  { value: "arrowUp", label: "위 삼각형" },
  { value: "arrowDown", label: "아래 삼각형" },
] as const;

type MarkerPlacementOverride = (typeof MARKER_PLACEMENT_OPTIONS)[number]["value"];
type MarkerShapeOverride = (typeof MARKER_SHAPE_OPTIONS)[number]["value"];
type MarkerStyleConfig = {
  position: MarkerPlacementOverride;
  shape: MarkerShapeOverride;
  color: string;
  size: number;
  lineWidth: number;
};

const DEFAULT_MARKER_STYLE: MarkerStyleConfig = {
  position: "default",
  shape: "default",
  color: "#94a3b8",
  size: 4,
  lineWidth: 1,
};

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

function isStockCodeKeyword(value: string) {
  return /^A\d{6}$/.test(value.trim().toUpperCase());
}

function isAbortError(err: unknown) {
  return err instanceof DOMException && err.name === "AbortError";
}

export function OntologyChartWorkspace() {
  const statusAbortControllerRef = useRef<AbortController | null>(null);
  const companiesAbortControllerRef = useRef<AbortController | null>(null);
  const panelAbortControllerRef = useRef<AbortController | null>(null);
  const [status, setStatus] = useState<OntologyStatus | null>(null);
  const [selectedCompany, setSelectedCompany] = useState<OntologyCompany | null>(null);
  const [panel, setPanel] = useState<OntologyPanel | null>(null);
  const [keyword, setKeyword] = useState("");
  const [disclosureGroup, setDisclosureGroup] = useState(DISCLOSURE_GROUP_ALL);
  const [displayFrequency, setDisplayFrequency] = useState<(typeof DISPLAY_FREQUENCY_OPTIONS)[number]>("일봉");
  const [chartType, setChartType] = useState<(typeof CHART_TYPE_OPTIONS)[number]["value"]>("candlestick");
  const [requestedPanelKey, setRequestedPanelKey] = useState("");
  const [chartZoomSensitivity, setChartZoomSensitivity] = useState(0.55);
  const [activeMarkerStyleGroup, setActiveMarkerStyleGroup] = useState(MARKER_STYLE_GROUP_ALL);
  const [markerStyleDefault, setMarkerStyleDefault] = useState<MarkerStyleConfig>(DEFAULT_MARKER_STYLE);
  const [markerStylesByGroup, setMarkerStylesByGroup] = useState<Record<string, MarkerStyleConfig>>({});
  const [chartFullscreen, setChartFullscreen] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [loadingCompanies, setLoadingCompanies] = useState(false);
  const [loadingPanel, setLoadingPanel] = useState(false);
  const [error, setError] = useState("");

  const loadStatus = useCallback(async () => {
    statusAbortControllerRef.current?.abort();
    const controller = new AbortController();
    statusAbortControllerRef.current = controller;
    setLoadingStatus(true);
    try {
      const data = await apiGet<OntologyStatus>("/api/ontology/status", { signal: controller.signal });
      if (controller.signal.aborted) return;
      setStatus(data);
    } catch (err) {
      if (isAbortError(err)) return;
      setError(err instanceof Error ? err.message : "원천 정보를 불러오지 못했습니다.");
    } finally {
      if (statusAbortControllerRef.current === controller) {
        statusAbortControllerRef.current = null;
      }
      if (!controller.signal.aborted) {
        setLoadingStatus(false);
      }
    }
  }, []);

  const loadCompanies = useCallback(async () => {
    companiesAbortControllerRef.current?.abort();
    if (!keyword.trim()) {
      setSelectedCompany(null);
      setPanel(null);
      setRequestedPanelKey("");
      setLoadingCompanies(false);
      return;
    }
    const controller = new AbortController();
    companiesAbortControllerRef.current = controller;
    setLoadingCompanies(true);
    try {
      const keywordText = keyword.trim().toUpperCase();
      const query = new URLSearchParams({
        keyword: isStockCodeKeyword(keywordText) ? normalizeStockCode(keywordText).slice(1) : keyword.trim(),
        market: "전체",
        limit: "30",
      });
      const data = await apiGet<OntologyCompaniesPayload>(`/api/ontology/companies?${query.toString()}`, {
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setSelectedCompany((current) => {
        if (current && data.companies.some((company) => company.stock_code === current.stock_code)) {
          return current;
        }
        return data.companies[0] ?? null;
      });
    } catch (err) {
      if (isAbortError(err)) return;
      setError(err instanceof Error ? err.message : "회사 목록을 불러오지 못했습니다.");
    } finally {
      if (companiesAbortControllerRef.current === controller) {
        companiesAbortControllerRef.current = null;
      }
      if (!controller.signal.aborted) {
        setLoadingCompanies(false);
      }
    }
  }, [keyword]);

  const loadPanel = useCallback(async () => {
    panelAbortControllerRef.current?.abort();
    if (!selectedCompany) {
      setPanel(null);
      setLoadingPanel(false);
      return;
    }
    const controller = new AbortController();
    panelAbortControllerRef.current = controller;
    setLoadingPanel(true);
    const requestKey = `${selectedCompany.stock_code}:${displayFrequency}:${disclosureGroup}`;
    setRequestedPanelKey(requestKey);
    try {
      const query = new URLSearchParams({
        company_id: selectedCompany.stock_code,
        market: "전체",
        display_frequency: displayFrequency,
        disclosure_group: disclosureGroup,
      });
      const data = await apiGet<OntologyPanel>(`/api/ontology/company-panel?${query.toString()}`, {
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setPanel(data);
    } catch (err) {
      if (isAbortError(err)) return;
      setError(err instanceof Error ? err.message : "분석 데이터를 불러오지 못했습니다.");
    } finally {
      if (panelAbortControllerRef.current === controller) {
        panelAbortControllerRef.current = null;
      }
      if (!controller.signal.aborted) {
        setLoadingPanel(false);
      }
    }
  }, [disclosureGroup, displayFrequency, selectedCompany]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    loadPanel();
  }, [loadPanel]);

  useEffect(() => {
    return () => {
      statusAbortControllerRef.current?.abort();
      companiesAbortControllerRef.current?.abort();
      panelAbortControllerRef.current?.abort();
    };
  }, []);

  const selectedCompanyLabel = selectedCompany
    ? `${selectedCompany.company_name} (${selectedCompany.stock_code})`
    : "검색한 종목이 없습니다.";
  const statusMessages = useMemo(() => [...(status?.messages ?? []), ...(error ? [error] : [])], [error, status]);
  const disclosureGroups = useMemo(() => status?.disclosure_groups ?? [], [status?.disclosure_groups]);
  const markerStyleGroups = useMemo(() => [MARKER_STYLE_GROUP_ALL, ...disclosureGroups], [disclosureGroups]);
  const activeMarkerStyle =
    activeMarkerStyleGroup === MARKER_STYLE_GROUP_ALL
      ? markerStyleDefault
      : (markerStylesByGroup[activeMarkerStyleGroup] ?? markerStyleDefault);
  const chartRangeText = panel ? `${panel.range_start} - ${panel.range_end} / ${panel.display_frequency}` : "전체 기간";
  const chartDisclosureText = disclosureGroup === DISCLOSURE_GROUP_ALL ? DISCLOSURE_GROUP_ALL : disclosureGroup;
  const chartMetaText = `${selectedCompanyLabel} ${chartRangeText} · ${chartDisclosureText}`;
  const chartIsLoading =
    loadingCompanies ||
    loadingPanel ||
    (!!selectedCompany && requestedPanelKey !== `${selectedCompany.stock_code}:${displayFrequency}:${disclosureGroup}`);
  const handleChartZoomSensitivityChange = (event: ChangeEvent<HTMLInputElement> | FormEvent<HTMLInputElement>) => {
    setChartZoomSensitivity(clampChartZoomSensitivity(Number(event.currentTarget.value)));
  };
  const handleChartZoomSensitivityPercentChange = (event: ChangeEvent<HTMLInputElement>) => {
    setChartZoomSensitivity(clampChartZoomSensitivity(Number(event.currentTarget.value) / 100));
  };
  const updateActiveMarkerStyle = <Key extends keyof MarkerStyleConfig>(key: Key, value: MarkerStyleConfig[Key]) => {
    if (activeMarkerStyleGroup === MARKER_STYLE_GROUP_ALL) {
      setMarkerStyleDefault((current) => ({ ...current, [key]: value }));
      return;
    }
    setMarkerStylesByGroup((current) => ({
      ...current,
      [activeMarkerStyleGroup]: {
        ...(current[activeMarkerStyleGroup] ?? markerStyleDefault),
        [key]: value,
      },
    }));
  };

  const renderChartControls = () => (
    <div className="ontology-form-grid xl:grid-cols-[auto_minmax(7rem,9rem)_minmax(8rem,10rem)] xl:items-start xl:justify-end">
      <div className="ontology-action-row">
        <Button variant="outline" size="sm" onClick={() => setChartFullscreen(true)} disabled={chartIsLoading}>
          <Maximize2 className="h-4 w-4" />
          전체화면
        </Button>
        <Button variant="outline" size="sm" onClick={loadPanel} disabled={!selectedCompany || chartIsLoading}>
          {chartIsLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          새로고침
        </Button>
      </div>
      <select
        aria-label="캔들/종가선"
        value={chartType}
        onChange={(event) => setChartType(event.target.value as (typeof CHART_TYPE_OPTIONS)[number]["value"])}
        className="ontology-control h-9 w-full px-3 text-sm shadow-sm"
      >
        {CHART_TYPE_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <select
        aria-label="일봉/3일봉/5일봉/7일봉/20일봉/월봉"
        value={displayFrequency}
        onChange={(event) => setDisplayFrequency(event.target.value as (typeof DISPLAY_FREQUENCY_OPTIONS)[number])}
        className="ontology-control h-9 w-full px-3 text-sm shadow-sm"
      >
        {DISPLAY_FREQUENCY_OPTIONS.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );

  const renderPriceChart = (expanded = false) => (
    <div
      className={cn(
        "ontology-panel ontology-panel-section",
        expanded ? "h-full min-h-0" : "h-[min(70vh,760px)] min-h-[540px]",
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
          chartType={chartType}
          markerStyleDefault={markerStyleDefault}
          markerStylesByGroup={markerStylesByGroup}
        />
      ) : (
        <div className="flex h-full min-h-[420px] items-center justify-center text-center">
          <div>
            <LineChart className="mx-auto h-8 w-8 text-slate-400" />
            <p className="mt-3 font-semibold text-slate-900 dark:text-slate-100">표시할 차트 데이터가 없습니다.</p>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">종목명 또는 A000000 형식으로 검색하세요.</p>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="relative action-dock-host flex w-full flex-col gap-4 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
      <div className="flex w-full flex-col gap-4">
        <section>
          <Card className="ontology-card">
            <CardHeader className="ontology-page-card-header">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">
                FILTERS
              </p>
              <div className="flex items-center gap-2">
                <SlidersHorizontal className="h-4 w-4 text-slate-500 dark:text-slate-400" />
                <CardTitle className="ontology-card-title">공시 조건</CardTitle>
              </div>
              <CardDescription className="ontology-card-description">Chart View · {chartMetaText}</CardDescription>
            </CardHeader>
            <CardContent className="ontology-page-card-content space-y-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(280px,0.9fr)_minmax(320px,0.8fr)_minmax(0,1.2fr)] xl:items-end">
                <div className="ontology-form-field">
                  <Label htmlFor="ontology-chart-stock-keyword" className="font-semibold dark:text-slate-200">
                    회사명
                  </Label>
                  <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                  <Input
                    id="ontology-chart-stock-keyword"
                    aria-label="종목 선택"
                    value={keyword}
                    onChange={(event) => setKeyword(event.target.value)}
                    placeholder="종목명 또는 A000000"
                    className="h-9 min-w-0"
                  />
                  <Button variant="outline" size="sm" className="h-9" onClick={loadCompanies} disabled={loadingCompanies}>
                    {loadingCompanies ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                    검색
                  </Button>
                  </div>
                </div>
                <div className="ontology-form-field">
                    <Label
                      htmlFor="ontology-chart-disclosure-group"
                    className="font-semibold dark:text-slate-200"
                    >
                      공시 선택
                    </Label>
                    <select
                      id="ontology-chart-disclosure-group"
                      value={disclosureGroup}
                      onChange={(event) => setDisclosureGroup(event.target.value)}
                      className="ontology-control h-9 w-full px-3 text-sm shadow-sm"
                    >
                      <option value={DISCLOSURE_GROUP_ALL}>{DISCLOSURE_GROUP_ALL}</option>
                      {disclosureGroups.map((group) => (
                        <option key={group} value={group}>
                          {group}
                        </option>
                      ))}
                    </select>
                </div>
                {renderChartControls()}
              </div>
              <div className="border-t border-slate-200 pt-4 dark:border-[#30363d]">
                <div className="ontology-panel ontology-panel-section">
                  <div className="mb-3 grid gap-2 lg:grid-cols-[minmax(0,1fr)_16rem] lg:items-end">
                    <div>
                      <Label htmlFor="ontology-chart-marker-style-group" className="font-semibold dark:text-slate-200">
                        공시 마커 스타일
                      </Label>
                    </div>
                    <select
                      id="ontology-chart-marker-style-group"
                      value={activeMarkerStyleGroup}
                      onChange={(event) => setActiveMarkerStyleGroup(event.target.value)}
                      aria-label="스타일 대상"
                      className="ontology-control h-8 w-full px-2.5 text-sm shadow-sm sm:w-48"
                    >
                      {markerStyleGroups.map((group) => (
                        <option key={group} value={group}>
                          {group}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="ontology-form-grid sm:grid-cols-2 lg:grid-cols-[minmax(140px,1fr)_minmax(140px,1fr)_112px_96px_96px]">
                    <div className="ontology-form-field">
                      <Label htmlFor="ontology-chart-marker-shape" className="text-slate-600 dark:text-slate-300">
                        모양
                      </Label>
                      <select
                        id="ontology-chart-marker-shape"
                        value={activeMarkerStyle.shape}
                        onChange={(event) => updateActiveMarkerStyle("shape", event.target.value as MarkerShapeOverride)}
                        className="ontology-control h-8 w-full px-2.5 text-sm shadow-sm"
                      >
                        {MARKER_SHAPE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="ontology-form-field">
                      <Label htmlFor="ontology-chart-marker-placement" className="text-slate-600 dark:text-slate-300">
                        위치
                      </Label>
                      <select
                        id="ontology-chart-marker-placement"
                        value={activeMarkerStyle.position}
                        onChange={(event) => updateActiveMarkerStyle("position", event.target.value as MarkerPlacementOverride)}
                        className="ontology-control h-8 w-full px-2.5 text-sm shadow-sm"
                      >
                        {MARKER_PLACEMENT_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="ontology-form-field">
                      <Label htmlFor="ontology-chart-marker-color" className="text-slate-600 dark:text-slate-300">
                        색상
                      </Label>
                      <div className="ontology-control flex h-8 items-center gap-2 px-2 shadow-sm">
                        <span
                          aria-label="공시 마커 스타일 미리보기"
                          className="h-4 w-4 rounded-full border border-slate-300 dark:border-slate-600"
                          style={{ backgroundColor: activeMarkerStyle.color }}
                        />
                        <Input
                          id="ontology-chart-marker-color"
                          type="color"
                          value={activeMarkerStyle.color}
                          onChange={(event) => updateActiveMarkerStyle("color", event.target.value)}
                          className="h-5 w-10 border-0 bg-transparent p-0 shadow-none"
                        />
                      </div>
                    </div>
                    <div className="ontology-form-field">
                      <Label htmlFor="ontology-chart-marker-size" className="text-slate-600 dark:text-slate-300">
                        크기
                      </Label>
                      <Input
                        id="ontology-chart-marker-size"
                        type="number"
                        min="2"
                        max="14"
                        step="1"
                        value={activeMarkerStyle.size}
                        onChange={(event) => updateActiveMarkerStyle("size", Number(event.target.value))}
                        className="h-8 rounded-md text-sm"
                      />
                    </div>
                    <div className="ontology-form-field">
                      <Label htmlFor="ontology-chart-marker-line-width" className="text-slate-600 dark:text-slate-300">
                        선 두께
                      </Label>
                      <Input
                        id="ontology-chart-marker-line-width"
                        type="number"
                        min="1"
                        max="6"
                        step="1"
                        value={activeMarkerStyle.lineWidth}
                        onChange={(event) => updateActiveMarkerStyle("lineWidth", Number(event.target.value))}
                        className="h-8 rounded-md text-sm"
                      />
                    </div>
                  </div>
                </div>
              </div>
              <MessageBox messages={statusMessages} />
            </CardContent>
          </Card>
        </section>

        <section>
          <Card className="ontology-card">
            <CardHeader className="ontology-page-card-header">
              <CardTitle className="ontology-card-title flex items-center gap-2">
                <LineChart className="h-5 w-5" />
                주가-공시 차트
              </CardTitle>
              <CardDescription className="ontology-card-description mt-2">
                {chartMetaText}
              </CardDescription>
            </CardHeader>
            <CardContent className="ontology-page-card-content">
              {renderPriceChart()}
            </CardContent>
          </Card>
        </section>

        <section>
          <Card className="ontology-card">
            <CardHeader className="ontology-page-card-header">
              <CardTitle className="ontology-card-title flex items-center gap-2">
                <FileText className="h-5 w-5" />
                공시 타임라인
              </CardTitle>
              <CardDescription className="ontology-card-description">차트에 표시된 전체 기간 공시</CardDescription>
            </CardHeader>
            <CardContent className="ontology-page-card-content">
              <div className="max-h-[460px] overflow-y-auto">
                {panel?.timeline.length ? (
                  <div className="divide-y divide-slate-100 dark:divide-[#30363d]">
                    {panel.timeline.map((item) => (
                      <div key={item.acpt_no} className="grid gap-3 px-3 py-3 lg:grid-cols-[10rem_minmax(0,1fr)_14rem]">
                        <div className="text-sm text-slate-500 dark:text-slate-400">
                          <p className="font-medium text-slate-700 dark:text-slate-300">{item.disclosed_at}</p>
                          <p className="mt-1 text-xs">마커 {item.trade_day || "-"}</p>
                          <p className="mt-1 text-xs">최종보고서 {item.final_report || "-"}</p>
                        </div>
                        <div className="min-w-0">
                          <p className="ontology-text-wrap font-semibold leading-snug text-slate-950 dark:text-slate-100">{item.title}</p>
                          <p className="ontology-text-wrap mt-1 text-sm text-slate-500 dark:text-slate-400">{item.submitter}</p>
                        </div>
                        <div className="text-left lg:text-right">
                          <span className="ontology-text-wrap inline-block max-w-full rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 dark:border-[#30363d] dark:text-slate-300">
                            {item.group}
                          </span>
                          <p className="ontology-mono-wrap mt-2 font-mono text-xs text-slate-400">{item.acpt_no}</p>
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
          <div className="ontology-fullscreen fixed inset-0 z-50 flex flex-col bg-white p-4 dark:bg-[#0d1117]">
            <div className="mb-3 flex flex-col gap-3 border-b border-slate-200 pb-3 sm:flex-row sm:items-center sm:justify-between dark:border-[#30363d]">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">주가-공시 차트</p>
                <h2 className="ontology-text-wrap text-xl font-bold text-slate-950 dark:text-slate-100">{selectedCompanyLabel}</h2>
                <p className="ontology-text-wrap text-sm text-slate-500 dark:text-slate-400">
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
                <select
                  aria-label="캔들/종가선"
                  value={chartType}
                  onChange={(event) => setChartType(event.target.value as (typeof CHART_TYPE_OPTIONS)[number]["value"])}
                  className="ontology-control h-9 w-full px-3 text-sm shadow-sm sm:w-32"
                >
                  {CHART_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="일봉/3일봉/5일봉/7일봉/20일봉/월봉"
                  value={displayFrequency}
                  onChange={(event) => setDisplayFrequency(event.target.value as (typeof DISPLAY_FREQUENCY_OPTIONS)[number])}
                  className="ontology-control h-9 w-full px-3 text-sm shadow-sm sm:w-40"
                >
                  {DISPLAY_FREQUENCY_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
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
