export type QuantFeatureIcon =
  | "database"
  | "lineChart"
  | "history"
  | "pieChart"
  | "fileText";

export type QuantFeatureId =
  | "research-data-store"
  | "factor-signal-research"
  | "point-in-time-backtesting"
  | "portfolio-risk"
  | "research-runs-reports";

export type QuantPlatformFeature = {
  id: QuantFeatureId;
  icon: QuantFeatureIcon;
  title: string;
  shortLabel: string;
  status: string;
  summary: string;
  primaryMetricLabel: string;
  primaryMetricValue: string;
  secondaryMetricLabel: string;
  secondaryMetricValue: string;
  testEvidence: string[];
  productionWork: string[];
};

export const quantPlatformTestDataNotice = {
  badge: "TEST DATA",
  scope: "Synthetic Ontology sample data",
  sourcePath:
    "frontend/finiq_GUI/apps/market-desk/src/app/graph/test-data/quantPlatformFeatures.ts",
  resourceBoundary: "Does not read from or write to resources/",
  snapshotDate: "2026-06-17",
};

export const quantPlatformOverview = {
  title: "Quant Platform Workspace",
  subtitle: "Professional quant analyst feature surface",
  testDataLabel: "TEST DATA - synthetic feature model",
  metrics: [
    { label: "Feature areas", value: "5", tone: "slate" },
    { label: "Test datasets", value: "12", tone: "cyan" },
    { label: "Signal checks", value: "28", tone: "emerald" },
    { label: "Risk views", value: "9", tone: "amber" },
  ],
  pipeline: [
    { label: "Data Store", state: "Modeled", tone: "cyan" },
    { label: "Signals", state: "Modeled", tone: "emerald" },
    { label: "Backtests", state: "Modeled", tone: "indigo" },
    { label: "Portfolio Risk", state: "Modeled", tone: "rose" },
    { label: "Reports", state: "Modeled", tone: "amber" },
  ],
};

export const quantPlatformFeatures: QuantPlatformFeature[] = [
  {
    id: "research-data-store",
    icon: "database",
    title: "Research Data Store",
    shortLabel: "Data Store",
    status: "Feature model",
    summary:
      "Versioned catalog for disclosures, Quantiwise Parquet, prices, market history, calendars, lineage, and data quality.",
    primaryMetricLabel: "Quality pass",
    primaryMetricValue: "97.4%",
    secondaryMetricLabel: "Catalog rows",
    secondaryMetricValue: "12",
    testEvidence: [
      "Dataset registry separates source, schema, coverage, and lineage.",
      "Coverage checks include date ranges, entity counts, and missing values.",
      "Delisting and market-history fields are modeled as first-class metadata.",
    ],
    productionWork: [
      "Connect the registry to existing manifest readers.",
      "Add dataset version fingerprints for each Parquet and SQLite artifact.",
      "Expose query APIs for point-in-time research pulls.",
    ],
  },
  {
    id: "factor-signal-research",
    icon: "lineChart",
    title: "Factor & Signal Research",
    shortLabel: "Signals",
    status: "Feature model",
    summary:
      "Signal workspace for returns, momentum, liquidity, event signals, disclosure-derived features, graph features, IC, decay, and turnover.",
    primaryMetricLabel: "Signals",
    primaryMetricValue: "28",
    secondaryMetricLabel: "Rank IC",
    secondaryMetricValue: "0.064",
    testEvidence: [
      "Signal diagnostics include coverage, missingness, IC, and quantile spread.",
      "Disclosure-event signals and graph-derived signals share the same panel.",
      "Turnover and decay are visible before any backtest is promoted.",
    ],
    productionWork: [
      "Create reusable signal definitions with parameters.",
      "Persist computed factor panels by dataset version.",
      "Add neutralization and winsorization controls.",
    ],
  },
  {
    id: "point-in-time-backtesting",
    icon: "history",
    title: "Point-in-Time Backtesting",
    shortLabel: "Backtesting",
    status: "Feature model",
    summary:
      "No-lookahead backtesting with universe rules, rebalance schedules, transaction costs, liquidity limits, benchmarks, and holdings logs.",
    primaryMetricLabel: "CAGR",
    primaryMetricValue: "14.8%",
    secondaryMetricLabel: "Max DD",
    secondaryMetricValue: "-8.7%",
    testEvidence: [
      "Trade-date alignment separates disclosure time from investable date.",
      "Costs, slippage, and liquidity limits are included in the result model.",
      "Holdings and trades are treated as auditable artifacts.",
    ],
    productionWork: [
      "Implement calendar-aware portfolio simulation.",
      "Add survivorship-safe universe construction.",
      "Store benchmark-relative performance and attribution outputs.",
    ],
  },
  {
    id: "portfolio-risk",
    icon: "pieChart",
    title: "Portfolio Construction & Risk",
    shortLabel: "Portfolio Risk",
    status: "Feature model",
    summary:
      "Portfolio construction with constraints, factor exposure, beta, volatility, drawdown, stress scenarios, concentration, and active risk.",
    primaryMetricLabel: "Active risk",
    primaryMetricValue: "5.2%",
    secondaryMetricLabel: "Stress loss",
    secondaryMetricValue: "-3.4%",
    testEvidence: [
      "Risk views separate exposure, concentration, and stress diagnostics.",
      "Optimizer constraints are visible before portfolio promotion.",
      "Attribution connects performance back to factor and event buckets.",
    ],
    productionWork: [
      "Add optimizer service and constraint schema.",
      "Connect exposures to canonical sector, market, and factor data.",
      "Persist risk snapshots for each rebalance date.",
    ],
  },
  {
    id: "research-runs-reports",
    icon: "fileText",
    title: "Research Runs & Reports",
    shortLabel: "Research Runs",
    status: "Feature model",
    summary:
      "Reproducible research runs with dataset version, parameters, signal definitions, backtest outputs, logs, charts, and exportable reports.",
    primaryMetricLabel: "Runs",
    primaryMetricValue: "7",
    secondaryMetricLabel: "Reproducible",
    secondaryMetricValue: "100%",
    testEvidence: [
      "Run records include dataset, config, code path, outputs, and logs.",
      "Reports link signals, portfolios, trades, and risk in one artifact.",
      "Promotion status distinguishes drafts from reviewed research.",
    ],
    productionWork: [
      "Create a run manifest format for quant experiments.",
      "Add report export with chart images and tables.",
      "Add compare mode for multiple saved experiments.",
    ],
  },
];

export const quantPlatformDataSets = [
  {
    name: "KIND disclosure events",
    domain: "Events",
    coverage: "200 synthetic filings",
    quality: "98.1%",
    storage: "SQLite manifest model",
  },
  {
    name: "Quantiwise daily items",
    domain: "Market data",
    coverage: "1,250 synthetic securities",
    quality: "96.8%",
    storage: "Wide Parquet model",
  },
  {
    name: "Market membership history",
    domain: "Reference data",
    coverage: "18 synthetic intervals",
    quality: "100.0%",
    storage: "Interval Parquet model",
  },
  {
    name: "Disclosure graph features",
    domain: "Graph factors",
    coverage: "34 synthetic nodes",
    quality: "94.7%",
    storage: "Ontology fixture model",
  },
];

export const quantPlatformResearchRuns = [
  {
    name: "Disclosure momentum long-short",
    signal: "Event intensity + liquidity filter",
    result: "14.8% CAGR",
    risk: "8.7% max drawdown",
    status: "Draft",
  },
  {
    name: "Governance risk screen",
    signal: "Graph centrality + issuance activity",
    result: "0.064 rank IC",
    risk: "5.2% active risk",
    status: "Review",
  },
  {
    name: "Post-CB issuance drift",
    signal: "CB event window + volume anomaly",
    result: "2.1% 20D spread",
    risk: "3.4% stress loss",
    status: "Draft",
  },
];
