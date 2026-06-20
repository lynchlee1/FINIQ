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

export function DisclosureAnalysisWorkspace() {
  const [keyword, setKeyword] = useState("");
  const [companies, setCompanies] = useState<OntologyCompany[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<OntologyCompany | null>(null);
  const [panel, setPanel] = useState<OntologyPanel | null>(null);
  const [eventTimeBasis, setEventTimeBasis] = useState("disclosed_date");
  const [priceBasis, setPriceBasis] = useState("intraday");
  const [upperPct, setUpperPct] = useState("5");
  const [lowerPct, setLowerPct] = useState("3");
  const [verticalDays, setVerticalDays] = useState("20");
  const [selectedDisclosureIds, setSelectedDisclosureIds] = useState<string[]>([]);
  const [tripleBarrierResult, setTripleBarrierResult] = useState<TripleBarrierPayload | null>(null);
  const [loadingCompanies, setLoadingCompanies] = useState(false);
  const [loadingPanel, setLoadingPanel] = useState(false);
  const [runningTripleBarrier, setRunningTripleBarrier] = useState(false);
  const [error, setError] = useState("");

  const loadCompanies = useCallback(async () => {
    if (!keyword.trim()) {
      setCompanies([]);
      setSelectedCompany(null);
      setPanel(null);
      setTripleBarrierResult(null);
      setLoadingCompanies(false);
      return;
    }
    setLoadingCompanies(true);
    try {
      const keywordText = keyword.trim().toUpperCase();
      const query = new URLSearchParams({
        keyword: isStockCodeKeyword(keywordText) ? normalizeStockCode(keywordText).slice(1) : keyword.trim(),
        market: "전체",
        limit: "30",
      });
      const data = await apiGet<OntologyCompaniesPayload>(`/api/ontology/companies?${query.toString()}`);
      setCompanies(data.companies);
      setSelectedCompany((current) => {
        if (current && data.companies.some((company) => company.stock_code === current.stock_code)) {
          return current;
        }
        return data.companies[0] ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "종목을 불러오지 못했습니다.");
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
    try {
      const query = new URLSearchParams({
        company_id: selectedCompany.stock_code,
        market: "전체",
        display_frequency: "일봉",
      });
      const data = await apiGet<OntologyPanel>(`/api/ontology/company-panel?${query.toString()}`);
      setPanel(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "분석 데이터를 불러오지 못했습니다.");
    } finally {
      setLoadingPanel(false);
    }
  }, [selectedCompany]);

  const loadTripleBarrierResults = useCallback(async () => {
    if (!selectedCompany) {
      setTripleBarrierResult(null);
      return;
    }
    const query = new URLSearchParams({
      company_id: selectedCompany.stock_code,
    });
    const data = await apiGet<TripleBarrierPayload>(`/api/ontology/triple-barrier/results?${query.toString()}`);
    setTripleBarrierResult(data);
  }, [selectedCompany]);

  useEffect(() => {
    loadPanel();
  }, [loadPanel]);

  useEffect(() => {
    setSelectedDisclosureIds([]);
    loadTripleBarrierResults().catch((err) => {
      setError(err instanceof Error ? err.message : "Triple Barrier 결과를 불러오지 못했습니다.");
    });
  }, [loadTripleBarrierResults]);

  const runTripleBarrier = useCallback(async () => {
    if (!selectedCompany) return;
    setRunningTripleBarrier(true);
    setError("");
    try {
      const data = await apiPost<TripleBarrierPayload>("/api/ontology/triple-barrier/run", {
        company_id: selectedCompany.stock_code,
        market: "전체",
        disclosure_group: "전체",
        disclosure_ids: selectedDisclosureIds,
        event_time_basis: eventTimeBasis,
        price_basis: priceBasis,
        upper_pct: Number(upperPct),
        lower_pct: Number(lowerPct),
        vertical_days: Number(verticalDays),
      });
      setTripleBarrierResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Triple Barrier 실행에 실패했습니다.");
    } finally {
      setRunningTripleBarrier(false);
    }
  }, [eventTimeBasis, lowerPct, priceBasis, selectedCompany, selectedDisclosureIds, upperPct, verticalDays]);

  const toggleDisclosure = useCallback((disclosureId: string) => {
    setSelectedDisclosureIds((current) => (
      current.includes(disclosureId)
        ? current.filter((value) => value !== disclosureId)
        : [...current, disclosureId]
    ));
  }, []);

  const selectedCompanyLabel = selectedCompany ? `${selectedCompany.company_name} (${selectedCompany.stock_code})` : "검색한 종목이 없습니다.";
  const markers = panel?.chart.markers ?? [];
  const rows = tripleBarrierResult?.rows ?? [];

  return (
    <div className="flex w-full flex-col gap-5">
      <section>
        <Card className="rounded-lg dark:border-[#30363d] dark:bg-[#161b22]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-xl dark:text-white">
              <FileText className="h-5 w-5" />
              공시 분석
            </CardTitle>
            <CardDescription className="dark:text-slate-400">
              공시 이벤트 기준 Triple Barrier 라벨을 생성하고 저장합니다.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <div className="min-w-0 flex-1 space-y-1.5">
                <Label htmlFor="disclosure-analysis-keyword">종목 선택</Label>
                <Input
                  id="disclosure-analysis-keyword"
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  placeholder="종목명 또는 A000000"
                  className="h-9"
                />
              </div>
              <Button variant="outline" size="sm" className="h-9" onClick={loadCompanies} disabled={loadingCompanies}>
                {loadingCompanies ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                검색
              </Button>
              <select
                value={selectedCompany?.stock_code ?? ""}
                onChange={(event) => {
                  const nextStockCode = normalizeStockCode(event.target.value);
                  setSelectedCompany(companies.find((company) => company.stock_code === nextStockCode) ?? null);
                }}
                className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-100"
              >
                <option value="">종목 없음</option>
                {companies.map((company) => (
                  <option key={`${company.stock_code}-${company.company_name}-${company.market}`} value={company.stock_code}>
                    {company.company_name} ({company.stock_code})
                  </option>
                ))}
              </select>
            </div>
            {error ? <p className="mt-3 text-sm text-red-600 dark:text-red-300">{error}</p> : null}
          </CardContent>
        </Card>
      </section>

      <section>
        <Card className="rounded-lg dark:border-[#30363d] dark:bg-[#161b22]">
          <CardHeader>
            <CardTitle className="text-lg dark:text-white">Triple Barrier 실행</CardTitle>
            <CardDescription className="dark:text-slate-400">
              {selectedCompanyLabel} · {panel ? `${panel.range_start} - ${panel.range_end}` : "전체 기간"} · 공시 이벤트 기준 라벨을 계산해 저장합니다.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {loadingPanel ? (
              <PageLoadingSpinner message="공시 목록을 준비하는 중입니다..." />
            ) : (
              <>
                <div className="grid gap-3 md:grid-cols-6">
                  <label className="space-y-1.5 text-sm">
                    <span className="font-medium text-slate-700 dark:text-slate-300">이벤트 기준일</span>
                    <select value={eventTimeBasis} onChange={(event) => setEventTimeBasis(event.target.value)} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-100">
                      <option value="disclosed_date">공시일</option>
                      <option value="disclosed_at">공시시각</option>
                    </select>
                  </label>
                  <label className="space-y-1.5 text-sm">
                    <span className="font-medium text-slate-700 dark:text-slate-300">가격 기준</span>
                    <select value={priceBasis} onChange={(event) => setPriceBasis(event.target.value)} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-100">
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
                    <select value={verticalDays} onChange={(event) => setVerticalDays(event.target.value)} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-100">
                      <option value="5">5거래일</option>
                      <option value="10">10거래일</option>
                      <option value="20">20거래일</option>
                    </select>
                  </label>
                  <div className="flex items-end">
                    <Button className="h-9 w-full" onClick={runTripleBarrier} disabled={!selectedCompany || runningTripleBarrier}>
                      {runningTripleBarrier ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                      Triple Barrier 실행
                    </Button>
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 dark:border-[#30363d]">
                  <div className="border-b border-slate-200 px-3 py-2 text-sm font-semibold dark:border-[#30363d] dark:text-slate-100">공시 목록 선택</div>
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

                <div className="grid gap-2 sm:grid-cols-5">
                  {[
                    ["전체", tripleBarrierResult?.summary.total ?? 0],
                    ["완료", tripleBarrierResult?.summary.completed ?? 0],
                    ["실패", tripleBarrierResult?.summary.failed ?? 0],
                    ["신규 저장", tripleBarrierResult?.summary.created ?? 0],
                    ["중복 제외", tripleBarrierResult?.summary.reused ?? 0],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-lg border border-slate-200 px-3 py-2 dark:border-[#30363d]">
                      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
                      <p className="mt-1 font-semibold tabular-nums text-slate-950 dark:text-slate-100">{formatInteger(Number(value))}</p>
                    </div>
                  ))}
                </div>

                <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-[#30363d]">
                  <div className="border-b border-slate-200 px-3 py-2 text-sm font-semibold dark:border-[#30363d] dark:text-slate-100">결과 테이블</div>
                  <table className="min-w-[1280px] text-left text-xs">
                    <thead className="bg-slate-50 text-slate-500 dark:bg-[#0d1117] dark:text-slate-400">
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
              </>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
