"use client";

import { useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CircleCheck,
  Database,
  FileText,
  FlaskConical,
  GitBranch,
  History,
  LineChart,
  PieChart,
  ShieldCheck,
  Target,
} from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import {
  quantPlatformDataSets,
  quantPlatformFeatures,
  quantPlatformOverview,
  quantPlatformResearchRuns,
  quantPlatformTestDataNotice,
  type QuantFeatureIcon,
  type QuantPlatformFeature,
} from "./test-data/quantPlatformFeatures";

const featureIconMap: Record<QuantFeatureIcon, typeof Database> = {
  database: Database,
  lineChart: LineChart,
  history: History,
  pieChart: PieChart,
  fileText: FileText,
};

const toneClasses: Record<string, string> = {
  slate: "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-200",
  cyan: "border-cyan-200 bg-cyan-50 text-cyan-700 dark:border-cyan-900/60 dark:bg-cyan-950/30 dark:text-cyan-200",
  emerald:
    "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-200",
  amber:
    "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200",
  indigo:
    "border-indigo-200 bg-indigo-50 text-indigo-700 dark:border-indigo-900/60 dark:bg-indigo-950/30 dark:text-indigo-200",
  rose: "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200",
};

function TestDataBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs font-semibold uppercase tracking-wide text-amber-800 dark:border-amber-700/70 dark:bg-amber-950/40 dark:text-amber-200",
        className,
      )}
    >
      <FlaskConical className="h-3.5 w-3.5" />
      {quantPlatformTestDataNotice.badge}
    </span>
  );
}

function MetricChip({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className={cn("rounded-lg border px-3 py-2", toneClasses[tone] ?? toneClasses.slate)}>
      <p className="text-[11px] font-medium uppercase tracking-wide opacity-75">{label}</p>
      <p className="mt-1 text-xl font-semibold tracking-normal">{value}</p>
    </div>
  );
}

function FeatureButton({
  feature,
  active,
  onSelect,
}: {
  feature: QuantPlatformFeature;
  active: boolean;
  onSelect: () => void;
}) {
  const Icon = featureIconMap[feature.icon];

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex min-h-36 w-full flex-col rounded-lg border bg-white p-4 text-left shadow-sm transition-colors dark:bg-[#161b22]",
        active
          ? "border-slate-900 ring-2 ring-slate-900/10 dark:border-slate-100 dark:ring-slate-100/10"
          : "border-slate-200 hover:border-slate-400 dark:border-[#30363d] dark:hover:border-slate-500",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-200">
          <Icon className="h-4 w-4" />
        </span>
        <span className="rounded-md border border-slate-200 px-2 py-1 text-[11px] font-medium text-slate-600 dark:border-[#30363d] dark:text-slate-300">
          {feature.status}
        </span>
      </div>
      <h3 className="mt-4 text-base font-semibold leading-snug text-slate-950 dark:text-slate-100">
        {feature.title}
      </h3>
      <p className="mt-2 line-clamp-3 text-sm leading-6 text-slate-600 dark:text-slate-400">
        {feature.summary}
      </p>
      <div className="mt-auto grid grid-cols-2 gap-2 pt-4">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-500">
            {feature.primaryMetricLabel}
          </p>
          <p className="mt-1 text-lg font-semibold text-slate-950 dark:text-slate-100">
            {feature.primaryMetricValue}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-500">
            {feature.secondaryMetricLabel}
          </p>
          <p className="mt-1 text-lg font-semibold text-slate-950 dark:text-slate-100">
            {feature.secondaryMetricValue}
          </p>
        </div>
      </div>
    </button>
  );
}

export function OntologyQuantPlatformPanel() {
  const [activeFeatureId, setActiveFeatureId] = useState(quantPlatformFeatures[0].id);
  const activeFeature = useMemo(
    () => quantPlatformFeatures.find((feature) => feature.id === activeFeatureId) ?? quantPlatformFeatures[0],
    [activeFeatureId],
  );
  const ActiveIcon = featureIconMap[activeFeature.icon];

  return (
    <div className="space-y-6">
      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm dark:border-[#30363d] dark:bg-[#161b22]">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <TestDataBadge />
                <span className="rounded-md border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 dark:border-[#30363d] dark:text-slate-300">
                  Ontology
                </span>
              </div>
              <h2 className="mt-4 text-2xl font-semibold tracking-normal text-slate-950 dark:text-slate-100">
                {quantPlatformOverview.title}
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-400">
                {quantPlatformOverview.subtitle}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600 dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-300">
              <div className="flex items-center gap-2 font-semibold text-slate-900 dark:text-slate-100">
                <ShieldCheck className="h-4 w-4" />
                Data boundary
              </div>
              <p className="mt-2 break-all">{quantPlatformTestDataNotice.sourcePath}</p>
              <p className="mt-1 font-medium text-amber-700 dark:text-amber-300">
                {quantPlatformTestDataNotice.resourceBoundary}
              </p>
            </div>
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {quantPlatformOverview.metrics.map((metric) => (
              <MetricChip key={metric.label} label={metric.label} value={metric.value} tone={metric.tone} />
            ))}
          </div>

          <div className="mt-6 rounded-lg border border-slate-200 p-4 dark:border-[#30363d]">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
              <GitBranch className="h-4 w-4" />
              Research pipeline
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              {quantPlatformOverview.pipeline.map((stage, index) => (
                <div key={stage.label} className="min-w-0">
                  <div className={cn("rounded-lg border px-3 py-2", toneClasses[stage.tone] ?? toneClasses.slate)}>
                    <p className="text-sm font-semibold leading-snug">{stage.label}</p>
                    <p className="mt-1 text-[11px] font-medium uppercase tracking-wide opacity-75">
                      {stage.state}
                    </p>
                  </div>
                  {index < quantPlatformOverview.pipeline.length - 1 ? (
                    <div className="mx-auto hidden h-px w-full bg-slate-200 md:block dark:bg-[#30363d]" />
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        </div>

        <Card className="rounded-lg dark:bg-[#161b22] dark:border-[#30363d]">
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2 text-lg dark:text-white">
                  <Activity className="h-5 w-5" />
                  Test Data Snapshot
                </CardTitle>
                <CardDescription className="dark:text-slate-400">
                  {quantPlatformTestDataNotice.scope}
                </CardDescription>
              </div>
              <TestDataBadge className="shrink-0" />
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2">
              {quantPlatformDataSets.map((dataset) => (
                <div key={dataset.name} className="rounded-lg border border-slate-200 px-3 py-3 text-sm dark:border-[#30363d]">
                  <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold leading-snug text-slate-950 dark:text-slate-100">{dataset.name}</p>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{dataset.storage}</p>
                    <p className="mt-2 text-slate-700 dark:text-slate-300">
                      <span className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-500">
                        {dataset.domain}
                      </span>
                      <span className="mx-2 text-slate-300 dark:text-slate-600">/</span>
                      <span>{dataset.coverage}</span>
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-500">
                      Quality
                    </p>
                    <p className="mt-1 font-semibold text-slate-950 dark:text-slate-100">{dataset.quality}</p>
                  </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/70 dark:bg-amber-950/30 dark:text-amber-200">
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <p>
                  Values on this panel are synthetic UI fixtures. They are not loaded from FINIQ production resources.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {quantPlatformFeatures.map((feature) => (
            <FeatureButton
              key={feature.id}
              feature={feature}
              active={feature.id === activeFeature.id}
              onSelect={() => setActiveFeatureId(feature.id)}
            />
          ))}
        </div>

        <Card className="rounded-lg dark:bg-[#161b22] dark:border-[#30363d]">
          <CardHeader>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <CardTitle className="flex items-center gap-2 text-lg dark:text-white">
                  <ActiveIcon className="h-5 w-5" />
                  <span className="min-w-0 truncate">{activeFeature.title}</span>
                </CardTitle>
                <CardDescription className="mt-2 leading-6 dark:text-slate-400">
                  {activeFeature.summary}
                </CardDescription>
              </div>
              <TestDataBadge className="shrink-0" />
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid grid-cols-2 gap-3">
              <MetricChip
                label={activeFeature.primaryMetricLabel}
                value={activeFeature.primaryMetricValue}
                tone="emerald"
              />
              <MetricChip
                label={activeFeature.secondaryMetricLabel}
                value={activeFeature.secondaryMetricValue}
                tone="cyan"
              />
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
                <CircleCheck className="h-4 w-4" />
                Test model coverage
              </div>
              <ul className="space-y-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                {activeFeature.testEvidence.map((item) => (
                  <li key={item} className="flex gap-2">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
                <Target className="h-4 w-4" />
                Production work
              </div>
              <ul className="space-y-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                {activeFeature.productionWork.map((item) => (
                  <li key={item} className="flex gap-2">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-500" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>
      </section>

      <Card className="rounded-lg dark:bg-[#161b22] dark:border-[#30363d]">
        <CardHeader>
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-lg dark:text-white">
                <BarChart3 className="h-5 w-5" />
                Research Runs & Reports
              </CardTitle>
              <CardDescription className="dark:text-slate-400">
                Saved experiment model using frontend-only synthetic rows.
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" disabled className="justify-start md:justify-center">
              <FileText className="h-4 w-4" />
              Export disabled for test data
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500 dark:border-[#30363d] dark:text-slate-500">
                  <th className="py-3 pr-4 font-semibold">Run</th>
                  <th className="py-3 pr-4 font-semibold">Signal</th>
                  <th className="py-3 pr-4 font-semibold">Result</th>
                  <th className="py-3 pr-4 font-semibold">Risk</th>
                  <th className="py-3 text-right font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {quantPlatformResearchRuns.map((run) => (
                  <tr key={run.name} className="border-b border-slate-100 last:border-0 dark:border-[#30363d]">
                    <td className="py-3 pr-4 font-semibold text-slate-950 dark:text-slate-100">{run.name}</td>
                    <td className="py-3 pr-4 text-slate-600 dark:text-slate-300">{run.signal}</td>
                    <td className="py-3 pr-4 text-slate-900 dark:text-slate-100">{run.result}</td>
                    <td className="py-3 pr-4 text-slate-600 dark:text-slate-300">{run.risk}</td>
                    <td className="py-3 text-right">
                      <span className="rounded-md border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 dark:border-[#30363d] dark:text-slate-300">
                        {run.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
