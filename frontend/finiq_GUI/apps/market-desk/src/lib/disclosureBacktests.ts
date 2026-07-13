export type BacktestCandle = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

export type BacktestMarker = {
  time: string;
  group?: string;
  title?: string;
  submitter?: string;
  disclosed_at?: string;
  acpt_no?: string;
};

export type BacktestInput = {
  candles: BacktestCandle[];
  markers: BacktestMarker[];
};

export type BacktestResultRow = {
  key: string;
  disclosedAt: string;
  group: string;
  title: string;
  entryDate: string;
  exitDate: string;
  outcome: string;
  returnPct: number | null;
};

export type BacktestResult = {
  rows: BacktestResultRow[];
  summary: {
    total: number;
    upper: number;
    lower: number;
    timeout: number;
    noPrice: number;
  };
};

export type BacktestMethodDefinition = {
  id: string;
  label: string;
  description: string;
  run: (input: BacktestInput) => BacktestResult;
};

const upperBarrier = 0.05;
const lowerBarrier = 0.05;
const barrierHorizon = 20;

function summarize(rows: BacktestResultRow[]): BacktestResult["summary"] {
  return {
    total: rows.length,
    upper: rows.filter((result) => result.outcome === "상승 돌파").length,
    lower: rows.filter((result) => result.outcome === "하락 돌파").length,
    timeout: rows.filter((result) => result.outcome === "기간 만료").length,
    noPrice: rows.filter((result) => result.outcome === "가격 없음").length,
  };
}

export function runTripleBarrierMethod(input: BacktestInput): BacktestResult {
  const rows = input.markers.slice(0, 120).map((marker) => {
    const entryIndex = input.candles.findIndex((candle) => candle.time >= marker.time);
    if (entryIndex < 0) {
      return {
        key: marker.acpt_no || `${marker.time}-${marker.title}`,
        disclosedAt: marker.disclosed_at || marker.time,
        group: marker.group || "기타",
        title: marker.title || "-",
        entryDate: "",
        exitDate: "",
        outcome: "가격 없음",
        returnPct: null,
      };
    }

    const entry = input.candles[entryIndex];
    if (!Number.isFinite(entry.close) || entry.close <= 0) {
      return {
        key: marker.acpt_no || `${marker.time}-${marker.title}`,
        disclosedAt: marker.disclosed_at || marker.time,
        group: marker.group || "기타",
        title: marker.title || "-",
        entryDate: entry.time,
        exitDate: "",
        outcome: "가격 없음",
        returnPct: null,
      };
    }
    const upper = entry.close * (1 + upperBarrier);
    const lower = entry.close * (1 - lowerBarrier);
    const lastIndex = Math.min(input.candles.length - 1, entryIndex + barrierHorizon);
    let exit = input.candles[lastIndex];
    let outcome = "기간 만료";

    for (let index = entryIndex + 1; index <= lastIndex; index += 1) {
      const candle = input.candles[index];
      if (candle.high >= upper) {
        exit = candle;
        outcome = "상승 돌파";
        break;
      }
      if (candle.low <= lower) {
        exit = candle;
        outcome = "하락 돌파";
        break;
      }
    }

    return {
      key: marker.acpt_no || `${marker.time}-${marker.title}`,
      disclosedAt: marker.disclosed_at || marker.time,
      group: marker.group || "기타",
      title: marker.title || "-",
      entryDate: entry.time,
      exitDate: exit.time,
      outcome,
      returnPct: ((exit.close - entry.close) / entry.close) * 100,
    };
  });

  return {
    rows,
    summary: summarize(rows),
  };
}

export const BACKTEST_METHODS: BacktestMethodDefinition[] = [
  {
    id: "triple-barrier",
    label: "Triple Barrier Method",
    description: "공시 이후 20거래일 안에 상단 5% 또는 하단 5% 장벽을 먼저 터치하는지 평가합니다.",
    run: runTripleBarrierMethod,
  },
];

export function runDisclosureBacktest(methodId: string, input: BacktestInput): BacktestResult {
  const method = BACKTEST_METHODS.find((candidate) => candidate.id === methodId);
  if (!method) throw new Error(`Unsupported backtest method: ${methodId}`);
  return method.run(input);
}
