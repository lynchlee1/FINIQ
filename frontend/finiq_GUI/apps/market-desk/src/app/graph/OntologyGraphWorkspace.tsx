"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Database, LineChart, Loader2, Search } from "lucide-react";
import { Button, Card, CardContent, Input } from "@finiq/ui";
import { apiGet } from "@/api/client";
import { PageLoadingSpinner } from "@finiq/web-app/status";

type OntologyNodeGraphProps = {
  selectedCompany: OntologyCompany | null;
  panel: OntologyPanel | null;
  selectedCompanyLabel: string;
  loading: boolean;
};

const OntologyNodeGraph = dynamic<OntologyNodeGraphProps>(
  () => import("./OntologyNodeGraph").then((mod) => mod.OntologyNodeGraph),
  {
    ssr: false,
    loading: () => (
      <Card className="ontology-card min-h-[620px]">
        <CardContent className="flex h-[620px] items-center justify-center">
          <PageLoadingSpinner message="관계 그래프를 준비하는 중입니다..." />
        </CardContent>
      </Card>
    ),
  },
);

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

export type OntologyCompany = {
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
  final_report?: string;
};

type TimelineItem = {
  disclosed_at: string;
  group: string;
  title: string;
  submitter: string;
  acpt_no: string;
  trade_day: string;
  final_report?: string;
};

export type OntologyPanel = {
  company: {
    company_id: string;
    stock_code: string;
    company_name: string;
    market: string;
  };
  range_start: string;
  range_end: string;
  display_frequency: string;
  selected_disclosure_group?: string;
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

const GRAPH_DISPLAY_FREQUENCY = "일봉";

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

export function OntologyGraphWorkspace() {
  const statusAbortControllerRef = useRef<AbortController | null>(null);
  const companiesAbortControllerRef = useRef<AbortController | null>(null);
  const panelAbortControllerRef = useRef<AbortController | null>(null);
  const [status, setStatus] = useState<OntologyStatus | null>(null);
  const [selectedCompany, setSelectedCompany] = useState<OntologyCompany | null>(null);
  const [panel, setPanel] = useState<OntologyPanel | null>(null);
  const [keyword, setKeyword] = useState("");
  const [requestedPanelKey, setRequestedPanelKey] = useState("");
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
    const requestKey = `${selectedCompany.stock_code}:${GRAPH_DISPLAY_FREQUENCY}`;
    setRequestedPanelKey(requestKey);
    try {
      const query = new URLSearchParams({
        company_id: selectedCompany.stock_code,
        market: "전체",
        display_frequency: GRAPH_DISPLAY_FREQUENCY,
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
  }, [selectedCompany]);

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
  const graphRangeText = panel ? `${panel.range_start} - ${panel.range_end} / ${panel.display_frequency}` : "전체 기간";
  const graphIsLoading =
    loadingCompanies ||
    loadingPanel ||
    (!!selectedCompany && requestedPanelKey !== `${selectedCompany.stock_code}:${GRAPH_DISPLAY_FREQUENCY}`);

  return (
    <div className="flex w-full flex-col gap-4">
      <section className="ontology-card ontology-page-card-content">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0 sm:flex-1">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-500 dark:text-slate-400">
              <LineChart className="h-4 w-4" />
              Graph View
            </div>
            <h1 className="ontology-text-wrap mt-1 text-base font-semibold text-slate-950 dark:text-slate-50">{selectedCompanyLabel}</h1>
            <p className="ontology-text-wrap mt-1 flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <Database className="h-4 w-4" />
              <span>{graphRangeText}</span>
            </p>
          </div>
          <div className="flex min-w-0 flex-col gap-2 sm:w-[min(28rem,45%)]">
            <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
              <Input
                id="ontology-stock-keyword"
                aria-label="종목 선택"
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="종목명 또는 A000000"
                className="h-10 min-w-0"
              />
              <Button variant="outline" size="sm" className="h-10" onClick={loadCompanies} disabled={loadingCompanies}>
                {loadingCompanies ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                검색
              </Button>
            </div>
            <MessageBox messages={statusMessages} />
          </div>
        </div>
      </section>

      <section>
        <OntologyNodeGraph
          selectedCompany={selectedCompany}
          panel={panel}
          selectedCompanyLabel={selectedCompanyLabel}
          loading={graphIsLoading || loadingStatus}
        />
      </section>
    </div>
  );
}
