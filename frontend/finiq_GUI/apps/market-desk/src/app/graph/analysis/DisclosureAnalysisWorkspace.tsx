"use client";

import { useCallback, useEffect, useState } from "react";
import { FileText, Loader2, Search } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@finiq/ui";
import { apiGet, apiPost } from "@/api/client";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { formatInteger } from "@/lib/format";

type OntologyCompany = {
  company_id: string;
  stock_code: string;
  company_name: string;
  market: string;
};

type OntologyCompaniesPayload = {
  companies: OntologyCompany[];
};

type OntologyStatusPayload = {
  disclosure_groups: string[];
};

type AnalysisMarker = {
  time: string;
  group?: string;
  title?: string;
  submitter?: string;
  disclosed_at?: string;
  acpt_no?: string;
};

type AnalysisCandle = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
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
    candles: AnalysisCandle[];
    markers: AnalysisMarker[];
  };
  messages: string[];
};

type TripleBarrierRow = {
  id?: number | null;
  disclosure_id: string;
  ticker: string;
  company_name: string;
  event_datetime: string;
  event_price: number | null;
  upper_pct: number;
  lower_pct: number;
  vertical_days: number;
  upper_price: number | null;
  lower_price: number | null;
  vertical_datetime: string;
  touched_barrier: string;
  touched_datetime: string;
  touched_price: number | null;
  return_pct: number | null;
  label: number | null;
  status: string;
  error_message: string;
  parameter_hash: string;
};

type TripleBarrierPayload = {
  summary: {
    total: number;
    completed: number;
    failed: number;
    created?: number;
    reused?: number;
  };
  result_db_path: string;
  parameter_hash?: string;
  rows: TripleBarrierRow[];
};

const DISCLOSURE_GROUP_ALL = "전체";
const DISCLOSURE_GROUP_LABELS: Record<string, string> = {
  shareholder_meeting: "주주총회",
  bond_issuance: "CB/EB/BW",
  rights_issuance: "유상증자",
};

function normalizeStockCode(value: string) {
  const digits = value.replace(/\D/g, "");
  return digits ? `A${digits.padStart(6, "0").slice(-6)}` : "";
}

function isStockCodeKeyword(value: string) {
  return /^A\d{6}$/.test(value.trim().toUpperCase());
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("ko-KR", { maximumFractionDigits: 4 });
}

function formatDisclosureGroupLabel(value: string) {
  return DISCLOSURE_GROUP_LABELS[value] ?? value;
}

export function DisclosureAnalysisWorkspace() {
  const [runKeyword, setRunKeyword] = useState("");
  const [runCompanies, setRunCompanies] = useState<OntologyCompany[]>([]);
  const [selectedRunCompany, setSelectedRunCompany] = useState<OntologyCompany | null>(null);
  const [resultKeyword, setResultKeyword] = useState("");
  const [resultCompanies, setResultCompanies] = useState<OntologyCompany[]>([]);
  const [selectedResultCompany, setSelectedResultCompany] = useState<OntologyCompany | null>(null);
  const [status, setStatus] = useState<OntologyStatusPayload | null>(null);
  const [panel, setPanel] = useState<OntologyPanel | null>(null);
  const [selectedAnalysisMode, setSelectedAnalysisMode] = useState<"run" | "results">("run");
  const [disclosureGroup, setDisclosureGroup] = useState(DISCLOSURE_GROUP_ALL);
  const [eventTimeBasis, setEventTimeBasis] = useState("disclosed_date");
  const [priceBasis, setPriceBasis] = useState("intraday");
  const [upperPct, setUpperPct] = useState("5");
  const [lowerPct, setLowerPct] = useState("3");
  const [verticalDays, setVerticalDays] = useState("20");
  const [selectedDisclosureIds, setSelectedDisclosureIds] = useState<string[]>([]);
  const [tripleBarrierResult, setTripleBarrierResult] = useState<TripleBarrierPayload | null>(null);
  const [loadingRunCompanies, setLoadingRunCompanies] = useState(false);
  const [loadingResultCompanies, setLoadingResultCompanies] = useState(false);
  const [loadingPanel, setLoadingPanel] = useState(false);
  const [runningTripleBarrier, setRunningTripleBarrier] = useState(false);
  const [error, setError] = useState("");

  const loadStatus = useCallback(async () => {
    try {
      const data = await apiGet<OntologyStatusPayload>("/api/ontology/status");
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "공시 분류를 불러오지 못했습니다.");
    }
  }, []);

  const loadRunCompanies = useCallback(async () => {
    if (!runKeyword.trim()) {
      setRunCompanies([]);
      setSelectedRunCompany(null);
      setPanel(null);
      setTripleBarrierResult(null);
      setLoadingRunCompanies(false);
      return;
    }
    setLoadingRunCompanies(true);
    try {
      const keywordText = runKeyword.trim().toUpperCase();
      const query = new URLSearchParams({
        keyword: isStockCodeKeyword(keywordText) ? normalizeStockCode(keywordText).slice(1) : runKeyword.trim(),
        market: "전체",
        limit: "30",
      });
      const data = await apiGet<OntologyCompaniesPayload>(`/api/ontology/companies?${query.toString()}`);
      setRunCompanies(data.companies);
      setSelectedRunCompany((current) => {
        if (current && data.companies.some((company) => company.stock_code === current.stock_code)) {
          return current;
        }
        return data.companies[0] ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "종목을 불러오지 못했습니다.");
    } finally {
      setLoadingRunCompanies(false);
    }
  }, [runKeyword]);

  const loadResultCompanies = useCallback(async () => {
    if (!resultKeyword.trim()) {
      setResultCompanies([]);
      setSelectedResultCompany(null);
      setTripleBarrierResult(null);
      setLoadingResultCompanies(false);
      return;
    }
    setLoadingResultCompanies(true);
    try {
      const keywordText = resultKeyword.trim().toUpperCase();
      const query = new URLSearchParams({
        keyword: isStockCodeKeyword(keywordText) ? normalizeStockCode(keywordText).slice(1) : resultKeyword.trim(),
        market: "전체",
        limit: "30",
      });
      const data = await apiGet<OntologyCompaniesPayload>(`/api/ontology/companies?${query.toString()}`);
      setResultCompanies(data.companies);
      setSelectedResultCompany((current) => {
        if (current && data.companies.some((company) => company.stock_code === current.stock_code)) {
          return current;
        }
        return data.companies[0] ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "결과 조회 종목을 불러오지 못했습니다.");
    } finally {
      setLoadingResultCompanies(false);
    }
  }, [resultKeyword]);

  const loadPanel = useCallback(async () => {
    if (!selectedRunCompany) {
      setPanel(null);
      return;
    }
    setLoadingPanel(true);
    try {
      const query = new URLSearchParams({
        company_id: selectedRunCompany.stock_code,
        market: "전체",
        disclosure_group: disclosureGroup,
        display_frequency: "일봉",
      });
      const data = await apiGet<OntologyPanel>(`/api/ontology/company-panel?${query.toString()}`);
      setPanel(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "분석 데이터를 불러오지 못했습니다.");
    } finally {
      setLoadingPanel(false);
    }
  }, [disclosureGroup, selectedRunCompany]);

  const loadTripleBarrierResults = useCallback(async (company: OntologyCompany | null = selectedResultCompany) => {
    if (!company) {
      setTripleBarrierResult(null);
      return;
    }
    const query = new URLSearchParams({
      company_id: company.stock_code,
    });
    const data = await apiGet<TripleBarrierPayload>(`/api/ontology/triple-barrier/results?${query.toString()}`);
    setTripleBarrierResult(data);
  }, [selectedResultCompany]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    loadPanel();
  }, [loadPanel]);

  useEffect(() => {
    setSelectedDisclosureIds([]);
    setTripleBarrierResult(null);
  }, [disclosureGroup, selectedRunCompany]);

  useEffect(() => {
    if (selectedAnalysisMode !== "results") return;
    loadTripleBarrierResults().catch((err) => {
      setError(err instanceof Error ? err.message : "Triple Barrier 결과를 불러오지 못했습니다.");
    });
  }, [loadTripleBarrierResults, selectedAnalysisMode]);

  const runTripleBarrier = useCallback(async () => {
    if (!selectedRunCompany) return;
    setRunningTripleBarrier(true);
    setError("");
    try {
      const data = await apiPost<TripleBarrierPayload>("/api/ontology/triple-barrier/run", {
        company_id: selectedRunCompany.stock_code,
        market: "전체",
        disclosure_group: disclosureGroup,
        disclosure_ids: selectedDisclosureIds,
        event_time_basis: eventTimeBasis,
        price_basis: priceBasis,
        upper_pct: Number(upperPct),
        lower_pct: Number(lowerPct),
        vertical_days: Number(verticalDays),
      });
      setTripleBarrierResult(data);
      setSelectedResultCompany(selectedRunCompany);
      setResultKeyword(selectedRunCompany.stock_code);
      setResultCompanies((current) => (
        current.some((company) => company.stock_code === selectedRunCompany.stock_code)
          ? current
          : [selectedRunCompany, ...current]
      ));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Triple Barrier 실행에 실패했습니다.");
    } finally {
      setRunningTripleBarrier(false);
    }
  }, [disclosureGroup, eventTimeBasis, lowerPct, priceBasis, selectedDisclosureIds, selectedRunCompany, upperPct, verticalDays]);

  const toggleDisclosure = useCallback((disclosureId: string) => {
    setSelectedDisclosureIds((current) => (
      current.includes(disclosureId)
        ? current.filter((value) => value !== disclosureId)
        : [...current, disclosureId]
    ));
  }, []);

  const selectedRunCompanyLabel = selectedRunCompany ? `${selectedRunCompany.company_name} (${selectedRunCompany.stock_code})` : "실행할 종목이 없습니다.";
  const selectedResultCompanyLabel = selectedResultCompany ? `${selectedResultCompany.company_name} (${selectedResultCompany.stock_code})` : "조회할 종목이 없습니다.";
  const markers = panel?.chart.markers ?? [];
  const rows = tripleBarrierResult?.rows ?? [];
  const disclosureGroupOptions = [DISCLOSURE_GROUP_ALL, ...(status?.disclosure_groups ?? [])];
  const isResultsMode = selectedAnalysisMode === "results";

  return (
    <div className="flex w-full flex-col gap-4">
      <section>
        <Card className="ontology-card">
          <CardHeader className="ontology-page-card-header">
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
              <div>
                <CardTitle className="ontology-card-title flex items-center gap-2">
                  <FileText className="h-5 w-5" />
                  공시 분석
                </CardTitle>
                <CardDescription className="ontology-card-description mt-2">
                  공시 이벤트 기준 Triple Barrier 라벨을 생성하고 저장합니다.
                </CardDescription>
              </div>
              <div className="ontology-toolbar inline-flex p-1">
                {[
                  ["run", "실행 설정"],
                  ["results", "저장 결과"],
                ].map(([mode, label]) => (
                  <Button
                    key={mode}
                    type="button"
                    variant={selectedAnalysisMode === mode ? "default" : "ghost"}
                    size="sm"
                    className="h-8"
                    aria-pressed={selectedAnalysisMode === mode}
                    onClick={() => setSelectedAnalysisMode(mode as "run" | "results")}
                  >
                    {label}
                  </Button>
                ))}
              </div>
            </div>
          </CardHeader>
          {error ? (
            <CardContent className="ontology-page-card-content">
              <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">{error}</p>
            </CardContent>
          ) : null}
        </Card>
      </section>

      <section>
        <Card className="ontology-card">
          <CardHeader className="ontology-page-card-header">
            <CardTitle className="ontology-card-title">
              {isResultsMode ? "Triple Barrier 저장 결과" : "Triple Barrier 실행"}
            </CardTitle>
            <CardDescription className="ontology-card-description">
              {isResultsMode
                ? `${selectedResultCompanyLabel} · 저장된 Triple Barrier 라벨을 검토합니다.`
                : `${selectedRunCompanyLabel} · ${panel ? `${panel.range_start} - ${panel.range_end}` : "전체 기간"} · 공시 이벤트 기준 라벨을 계산해 저장합니다.`}
            </CardDescription>
          </CardHeader>
          <CardContent className="ontology-page-card-content space-y-4">
            {selectedAnalysisMode === "run" && loadingPanel ? (
              <PageLoadingSpinner message="공시 목록을 준비하는 중입니다..." />
            ) : (
              <>
                {selectedAnalysisMode === "run" ? (
                  <>
                    <div className="ontology-panel space-y-3 p-3">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">1. 실행 대상</h3>
                        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Triple Barrier 라벨을 계산할 종목을 먼저 고릅니다.</p>
                      </div>
                      <div className="grid gap-3 lg:grid-cols-[minmax(220px,1fr)_auto_minmax(220px,0.8fr)] lg:items-end">
                        <div className="min-w-0 flex-1 space-y-1.5">
                          <Label htmlFor="disclosure-analysis-run-keyword">실행 종목 선택</Label>
                          <Input
                            id="disclosure-analysis-run-keyword"
                            value={runKeyword}
                            onChange={(event) => setRunKeyword(event.target.value)}
                            placeholder="종목명 또는 A000000"
                            className="h-9"
                          />
                        </div>
                        <Button variant="outline" size="sm" className="h-9" onClick={loadRunCompanies} disabled={loadingRunCompanies}>
                          {loadingRunCompanies ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                          실행 대상 검색
                        </Button>
                        <select
                          value={selectedRunCompany?.stock_code ?? ""}
                          onChange={(event) => {
                            const nextStockCode = normalizeStockCode(event.target.value);
                            setSelectedRunCompany(runCompanies.find((company) => company.stock_code === nextStockCode) ?? null);
                          }}
                          className="ontology-control h-9 px-2 text-sm"
                        >
                          <option value="">실행 종목 없음</option>
                          {runCompanies.map((company) => (
                            <option key={`${company.stock_code}-${company.company_name}-${company.market}`} value={company.stock_code}>
                              {company.company_name} ({company.stock_code})
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div className="ontology-panel space-y-3 p-3">
                      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">2. 공시 범위</h3>
                          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">분류와 개별 이벤트를 같은 흐름에서 좁힙니다.</p>
                        </div>
                        <p className="text-xs tabular-nums text-slate-500 dark:text-slate-400">
                          선택 {formatInteger(selectedDisclosureIds.length)}건
                        </p>
                      </div>
                      <div className="space-y-2">
                        <div className="text-xs font-medium text-slate-500 dark:text-slate-400">공시 선택</div>
                        <div className="flex flex-wrap gap-2">
                          {disclosureGroupOptions.map((group) => (
                            <button
                              key={group}
                              type="button"
                              aria-pressed={disclosureGroup === group}
                              onClick={() => setDisclosureGroup(group)}
                              className={[
                                "h-8 rounded-md border px-3 text-sm font-medium transition",
                                disclosureGroup === group
                                  ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                                  : "border-slate-200 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-950 dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-300 dark:hover:text-white",
                              ].join(" ")}
                            >
                              {formatDisclosureGroupLabel(group)}
                            </button>
                          ))}
                        </div>
                      </div>

                      <div className="ontology-panel overflow-hidden">
                        <div className="border-b px-3 py-2 text-sm font-semibold">검사 대상 이벤트</div>
                        <div className="max-h-44 overflow-y-auto divide-y divide-slate-100 dark:divide-[#30363d]">
                          {markers.length ? markers.map((marker) => {
                            const disclosureId = marker.acpt_no || `${marker.time}-${marker.title}`;
                            return (
                              <label key={disclosureId} className="flex items-center gap-2 px-3 py-2 text-sm dark:text-slate-200">
                                <input type="checkbox" checked={selectedDisclosureIds.includes(disclosureId)} onChange={() => toggleDisclosure(disclosureId)} />
                                <span className="min-w-[9rem] font-mono text-xs">{disclosureId}</span>
                                <span className="truncate">{marker.disclosed_at || marker.time} · {marker.title || "-"}</span>
                              </label>
                            );
                          }) : (
                            <p className="px-3 py-3 text-sm text-slate-500 dark:text-slate-400">분석할 공시 이벤트가 없습니다.</p>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="ontology-panel space-y-3 p-3">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">3. Triple Barrier 설정</h3>
                        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">이벤트 기준, 가격 판정 방식, barrier 값을 한 번에 확인한 뒤 실행합니다.</p>
                      </div>
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(140px,1fr)_minmax(170px,1fr)_120px_120px_140px_minmax(160px,0.8fr)]">
                        <label className="space-y-1.5 text-sm">
                          <span className="font-medium text-slate-700 dark:text-slate-300">이벤트 기준일</span>
                          <select value={eventTimeBasis} onChange={(event) => setEventTimeBasis(event.target.value)} className="ontology-control h-9 w-full px-2 text-sm">
                            <option value="disclosed_date">공시일</option>
                            <option value="disclosed_at">공시시각</option>
                          </select>
                        </label>
                        <label className="space-y-1.5 text-sm">
                          <span className="font-medium text-slate-700 dark:text-slate-300">가격 기준</span>
                          <select value={priceBasis} onChange={(event) => setPriceBasis(event.target.value)} className="ontology-control h-9 w-full px-2 text-sm">
                            <option value="close">종가 기준</option>
                            <option value="intraday">장중 고가/저가 기준</option>
                          </select>
                        </label>
                        <label className="space-y-1.5 text-sm">
                          <span className="font-medium text-slate-700 dark:text-slate-300">Upper barrier</span>
                          <Input value={upperPct} onChange={(event) => setUpperPct(event.target.value)} type="number" step="0.1" className="h-9" />
                        </label>
                        <label className="space-y-1.5 text-sm">
                          <span className="font-medium text-slate-700 dark:text-slate-300">Lower barrier</span>
                          <Input value={lowerPct} onChange={(event) => setLowerPct(event.target.value)} type="number" step="0.1" className="h-9" />
                        </label>
                        <label className="space-y-1.5 text-sm">
                          <span className="font-medium text-slate-700 dark:text-slate-300">Vertical barrier</span>
                          <select value={verticalDays} onChange={(event) => setVerticalDays(event.target.value)} className="ontology-control h-9 w-full px-2 text-sm">
                            <option value="5">5거래일</option>
                            <option value="10">10거래일</option>
                            <option value="20">20거래일</option>
                          </select>
                        </label>
                        <div className="flex items-end">
                          <Button className="h-9 w-full" onClick={runTripleBarrier} disabled={!selectedRunCompany || runningTripleBarrier}>
                            {runningTripleBarrier ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                            Triple Barrier 실행
                          </Button>
                        </div>
                      </div>
                    </div>
                  </>
                ) : null}

                {selectedAnalysisMode === "results" ? (
                  <div className="ontology-panel p-3">
                    <div className="space-y-3">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">저장 결과 조회</h3>
                        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                          {selectedResultCompany
                            ? `${selectedResultCompany.company_name} (${selectedResultCompany.stock_code}) 저장 결과를 표시합니다.`
                            : "결과 조회용 종목을 검색하고 선택하면 저장된 Triple Barrier 결과를 확인합니다."}
                        </p>
                      </div>
                      <div className="grid gap-3 lg:grid-cols-[minmax(220px,1fr)_auto_minmax(220px,0.8fr)_auto] lg:items-end">
                        <div className="min-w-0 flex-1 space-y-1.5">
                          <Label htmlFor="disclosure-analysis-result-keyword">결과 종목 선택</Label>
                          <Input
                            id="disclosure-analysis-result-keyword"
                            value={resultKeyword}
                            onChange={(event) => setResultKeyword(event.target.value)}
                            placeholder="종목명 또는 A000000"
                            className="h-9"
                          />
                        </div>
                        <Button variant="outline" size="sm" className="h-9" onClick={loadResultCompanies} disabled={loadingResultCompanies}>
                          {loadingResultCompanies ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                          저장 결과 검색
                        </Button>
                        <select
                          value={selectedResultCompany?.stock_code ?? ""}
                          onChange={(event) => {
                            const nextStockCode = normalizeStockCode(event.target.value);
                            setSelectedResultCompany(resultCompanies.find((company) => company.stock_code === nextStockCode) ?? null);
                          }}
                          className="ontology-control h-9 px-2 text-sm"
                        >
                          <option value="">조회 종목 없음</option>
                          {resultCompanies.map((company) => (
                            <option key={`${company.stock_code}-${company.company_name}-${company.market}`} value={company.stock_code}>
                              {company.company_name} ({company.stock_code})
                            </option>
                          ))}
                        </select>
                        <Button variant="outline" size="sm" className="h-9" onClick={() => loadTripleBarrierResults()} disabled={!selectedResultCompany}>
                          선택 종목 결과 조회
                        </Button>
                      </div>
                    </div>
                    <div className="mt-3 grid gap-2 text-xs text-slate-500 dark:text-slate-400 sm:grid-cols-3">
                      <div className="ontology-metric px-3 py-2">
                        조회 종목: <span className="font-medium text-slate-900 dark:text-slate-100">{selectedResultCompany?.stock_code ?? "-"}</span>
                      </div>
                      <div className="ontology-metric px-3 py-2">
                        결과 행: <span className="font-medium text-slate-900 dark:text-slate-100">{formatInteger(rows.length)}</span>
                      </div>
                      <div className="ontology-metric px-3 py-2">
                        DB: <span className="font-medium text-slate-900 dark:text-slate-100">{tripleBarrierResult?.result_db_path ? "연결됨" : "-"}</span>
                      </div>
                    </div>
                  </div>
                ) : null}

                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">저장 결과 요약</h3>
                    {selectedAnalysisMode === "run" ? (
                      <Button variant="outline" size="sm" className="h-8" onClick={() => setSelectedAnalysisMode("results")}>
                        저장 결과 보기
                      </Button>
                    ) : null}
                  </div>

                  <div className="grid gap-2 sm:grid-cols-5">
                    {[
                      ["전체", tripleBarrierResult?.summary.total ?? 0],
                      ["완료", tripleBarrierResult?.summary.completed ?? 0],
                      ["실패", tripleBarrierResult?.summary.failed ?? 0],
                      ["신규 저장", tripleBarrierResult?.summary.created ?? 0],
                      ["중복 제외", tripleBarrierResult?.summary.reused ?? 0],
                    ].map(([label, value]) => (
                      <div key={label} className="ontology-metric px-3 py-2">
                        <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
                        <p className="mt-1 font-semibold tabular-nums text-slate-950 dark:text-slate-100">{formatInteger(Number(value))}</p>
                      </div>
                    ))}
                  </div>

                  <div className="ontology-panel overflow-x-auto">
                    <div className="border-b px-3 py-2 text-sm font-semibold">결과 테이블</div>
                    <table className="min-w-[1280px] text-left text-xs">
                      <thead className="ontology-muted">
                        <tr>
                          {["공시 ID", "종목코드", "종목명", "공시일", "이벤트 가격", "upper barrier 가격", "lower barrier 가격", "vertical barrier 날짜", "최초 도달 barrier", "최초 도달 날짜", "최초 도달 가격", "수익률", "label", "계산 상태", "에러 메시지"].map((header) => (
                            <th key={header} className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">{header}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-[#30363d]">
                        {rows.map((row) => (
                          <tr key={`${row.disclosure_id}-${row.parameter_hash}`} className="dark:text-slate-200">
                            <td className="px-3 py-2 font-mono">{row.disclosure_id}</td>
                            <td className="px-3 py-2">{row.ticker}</td>
                            <td className="px-3 py-2">{row.company_name}</td>
                            <td className="px-3 py-2">{row.event_datetime}</td>
                            <td className="px-3 py-2 tabular-nums">{formatNumber(row.event_price)}</td>
                            <td className="px-3 py-2 tabular-nums">{formatNumber(row.upper_price)}</td>
                            <td className="px-3 py-2 tabular-nums">{formatNumber(row.lower_price)}</td>
                            <td className="px-3 py-2">{row.vertical_datetime || "-"}</td>
                            <td className="px-3 py-2">{row.touched_barrier}</td>
                            <td className="px-3 py-2">{row.touched_datetime || "-"}</td>
                            <td className="px-3 py-2 tabular-nums">{formatNumber(row.touched_price)}</td>
                            <td className="px-3 py-2 tabular-nums">{formatNumber(row.return_pct)}</td>
                            <td className="px-3 py-2 tabular-nums">{row.label ?? "-"}</td>
                            <td className="px-3 py-2">{row.status}</td>
                            <td className="px-3 py-2">{row.error_message || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {tripleBarrierResult && !rows.length ? (
                      <p className="p-4 text-sm text-slate-500 dark:text-slate-400">저장된 결과가 없습니다.</p>
                    ) : null}
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
