"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FileText, Loader2, Search } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@finiq/ui";
import { apiGet } from "@/api/client";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { BACKTEST_METHODS, runDisclosureBacktest, type BacktestCandle, type BacktestMarker } from "@/lib/disclosureBacktests";
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
    candles: BacktestCandle[];
    markers: BacktestMarker[];
  };
  messages: string[];
};

function normalizeStockCode(value: string) {
  const digits = value.replace(/\D/g, "");
  return digits ? `A${digits.padStart(6, "0").slice(-6)}` : "";
}

export function DisclosureAnalysisWorkspace() {
  const [keyword, setKeyword] = useState("");
  const [companies, setCompanies] = useState<OntologyCompany[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<OntologyCompany | null>(null);
  const [panel, setPanel] = useState<OntologyPanel | null>(null);
  const [methodId, setMethodId] = useState(BACKTEST_METHODS[0].id);
  const [loadingCompanies, setLoadingCompanies] = useState(false);
  const [loadingPanel, setLoadingPanel] = useState(false);
  const [error, setError] = useState("");

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

  useEffect(() => {
    loadCompanies();
  }, [loadCompanies]);

  useEffect(() => {
    loadPanel();
  }, [loadPanel]);

  const selectedMethod = BACKTEST_METHODS.find((method) => method.id === methodId) ?? BACKTEST_METHODS[0];
  const result = useMemo(
    () => runDisclosureBacktest(methodId, { candles: panel?.chart.candles ?? [], markers: panel?.chart.markers ?? [] }),
    [methodId, panel],
  );
  const selectedCompanyLabel = selectedCompany ? `${selectedCompany.company_name} (${selectedCompany.stock_code})` : "선택된 종목 없음";

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
              공시 이벤트 기반 퀀트 방법을 선택해 백테스팅합니다.
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
              <select
                value={methodId}
                onChange={(event) => setMethodId(event.target.value)}
                className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-100"
              >
                {BACKTEST_METHODS.map((method) => (
                  <option key={method.id} value={method.id}>
                    {method.label}
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
            <CardTitle className="text-lg dark:text-white">{selectedMethod.label}</CardTitle>
            <CardDescription className="dark:text-slate-400">
              {selectedCompanyLabel} · {panel ? `${panel.range_start} - ${panel.range_end}` : "전체 기간"} · {selectedMethod.description}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {loadingPanel ? (
              <PageLoadingSpinner message="백테스트 데이터를 준비하는 중입니다..." />
            ) : (
              <>
                <div className="grid gap-2 sm:grid-cols-5">
                  {[
                    ["분석 이벤트", result.summary.total],
                    ["상승 돌파", result.summary.upper],
                    ["하락 돌파", result.summary.lower],
                    ["기간 만료", result.summary.timeout],
                    ["가격 없음", result.summary.noPrice],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-lg border border-slate-200 px-3 py-2 dark:border-[#30363d]">
                      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
                      <p className="mt-1 font-semibold tabular-nums text-slate-950 dark:text-slate-100">{formatInteger(Number(value))}</p>
                    </div>
                  ))}
                </div>
                <div className="max-h-[calc(100vh-18rem)] overflow-y-auto rounded-lg border border-slate-200 dark:border-[#30363d]">
                  {result.rows.length ? (
                    <div className="divide-y divide-slate-100 dark:divide-[#30363d]">
                      {result.rows.map((row) => (
                        <div key={row.key} className="grid gap-2 p-3 text-sm md:grid-cols-[minmax(0,1.5fr)_7rem_7rem_6rem]">
                          <div className="min-w-0">
                            <p className="truncate font-semibold text-slate-950 dark:text-slate-100">{row.title}</p>
                            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                              {row.disclosedAt} · {row.group}
                            </p>
                          </div>
                          <div className="text-slate-500 dark:text-slate-400">
                            <p className="text-xs">진입/종료</p>
                            <p className="font-medium text-slate-700 dark:text-slate-300">{row.entryDate || "-"} / {row.exitDate || "-"}</p>
                          </div>
                          <div>
                            <p className="text-xs text-slate-500 dark:text-slate-400">결과</p>
                            <p className="font-semibold text-slate-950 dark:text-slate-100">{row.outcome}</p>
                          </div>
                          <div className="text-left md:text-right">
                            <p className="text-xs text-slate-500 dark:text-slate-400">수익률</p>
                            <p className="font-semibold tabular-nums text-slate-950 dark:text-slate-100">{row.returnPct.toFixed(2)}%</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="rounded-lg border border-slate-200 p-4 text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
                      분석할 공시 이벤트가 없습니다.
                    </p>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
