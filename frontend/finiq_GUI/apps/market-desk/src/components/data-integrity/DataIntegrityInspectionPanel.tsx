import type { ReactNode } from "react";
import { AlertTriangle, Check, CircleDashed, Clock3, Loader2 } from "lucide-react";
import { Button } from "@finiq/ui";

export type DataIntegrityInspectionTone = "success" | "warning" | "error" | "neutral";
export type DataIntegrityInspectionStepStatus = "complete" | "failed" | "ready" | "waiting" | "running";

export type DataIntegrityInspectionVerdict = {
  label: string;
  title: ReactNode;
  description: ReactNode;
  tone: DataIntegrityInspectionTone;
};

export type DataIntegrityInspectionStep = {
  key: string;
  numbered?: boolean;
  title: ReactNode;
  summary: ReactNode;
  status: DataIntegrityInspectionStepStatus;
  statusLabel: string;
  detail?: ReactNode;
  action?: {
    label: string;
    onClick: () => void;
    disabled?: boolean;
    loading?: boolean;
    showResultStatus?: boolean;
    resultStatus?: {
      status: "complete" | "failed";
      label: string;
    };
  };
};

type DataIntegrityInspectionPanelProps = {
  verdict: DataIntegrityInspectionVerdict;
  steps: DataIntegrityInspectionStep[];
};

const verdictClassNames: Record<DataIntegrityInspectionTone, string> = {
  success: "border-[color:var(--tv-up)] bg-[var(--tv-up-soft)] text-[var(--tv-up-text)]",
  warning: "border-[color:var(--tv-warning)] bg-[var(--tv-warning-soft)] text-[var(--tv-warning-text)]",
  error: "border-[color:var(--tv-down)] bg-[var(--tv-down-soft)] text-[var(--tv-down-text)]",
  neutral: "border-[color:var(--tv-border)] bg-[var(--tv-control)] text-[var(--tv-text)]",
};

const stepStatusClassNames: Record<DataIntegrityInspectionStepStatus, string> = {
  complete: "border-[color:var(--tv-up)] bg-[var(--tv-up-soft)] text-[var(--tv-up-text)]",
  failed: "border-[color:var(--tv-down)] bg-[var(--tv-down-soft)] text-[var(--tv-down-text)]",
  ready: "border-[color:var(--tv-warning)] bg-[var(--tv-warning-soft)] text-[var(--tv-warning-text)]",
  waiting: "border-[color:var(--tv-border)] bg-[var(--tv-control)] text-[var(--tv-muted)]",
  running: "border-[color:var(--tv-accent)] bg-[var(--tv-accent-soft)] text-[var(--tv-accent)]",
};

const stepControlClassName = "h-8 w-28 shrink-0 self-start justify-center whitespace-nowrap";

function StepStatusIcon({ status }: { status: DataIntegrityInspectionStepStatus }) {
  if (status === "complete") return <Check className="h-4 w-4" />;
  if (status === "failed") return <AlertTriangle className="h-4 w-4" />;
  if (status === "running") return <Loader2 className="h-4 w-4 animate-spin" />;
  if (status === "ready") return <Clock3 className="h-4 w-4" />;
  return <CircleDashed className="h-4 w-4" />;
}

export function DataIntegrityInspectionPanel({ verdict, steps }: DataIntegrityInspectionPanelProps) {
  let sequenceNumber = 0;
  return (
    <div className="space-y-4">
      <section
        className={`rounded-md border p-4 ${verdictClassNames[verdict.tone]}`}
        role={verdict.tone === "error" ? "alert" : "status"}
        aria-live="polite"
      >
        <div className="min-w-0 space-y-1.5">
          <p className="text-[12px] font-semibold leading-4">{verdict.label}</p>
          <p className="text-[16px] font-semibold leading-6">{verdict.title}</p>
          <div className="break-words text-[13px] leading-5 opacity-90">{verdict.description}</div>
        </div>
      </section>

      <ol className="overflow-hidden rounded-md border border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
        {steps.map((step) => {
          const stepNumber = step.numbered === false ? null : ++sequenceNumber;
          const resultStatus = step.action?.resultStatus;
          const displayedStatus = resultStatus?.status ?? step.status;
          const displayedStatusLabel = resultStatus?.label ?? step.statusLabel;
          const showResultStatus = !!step.action?.showResultStatus && (displayedStatus === "complete" || displayedStatus === "failed");
          return (
            <li key={step.key} className="border-b border-[color:var(--tv-border)] last:border-b-0">
              <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex min-w-0 gap-3">
                  <span className={`mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-[13px] font-semibold ${stepStatusClassNames[step.status]}`}>
                    {step.status === "waiting" || step.status === "ready" ? stepNumber : <StepStatusIcon status={step.status} />}
                  </span>
                  <div className="min-w-0 space-y-1">
                    <p className="text-[15px] font-semibold leading-6 text-[var(--tv-text)]">{step.title}</p>
                    <div className="text-[13px] leading-5 text-[var(--tv-muted)]">{step.summary}</div>
                  </div>
                </div>
                {step.action ? (
                  <Button
                    type="button"
                    size="sm"
                    variant={showResultStatus ? "outline" : undefined}
                    className={`${stepControlClassName} px-3 text-[13px] ${showResultStatus ? stepStatusClassNames[displayedStatus] : ""}`}
                    onClick={step.action.onClick}
                    disabled={step.action.disabled}
                    aria-label={showResultStatus ? `${displayedStatusLabel}, 검사하기` : undefined}
                  >
                    {showResultStatus ? (
                      <>
                        <StepStatusIcon status={displayedStatus} />
                        {displayedStatusLabel}
                      </>
                    ) : (
                      <>
                        {step.action.loading && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                        {step.action.label}
                      </>
                    )}
                  </Button>
                ) : (
                  <span className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 text-[12px] font-semibold leading-4 ${stepControlClassName} ${stepStatusClassNames[step.status]}`}>
                    <StepStatusIcon status={step.status} />
                    {step.statusLabel}
                  </span>
                )}
              </div>
              {step.status === "failed" && step.detail && (
                <div className="border-t border-[color:var(--tv-border)] bg-[var(--tv-control)] px-4 py-4 sm:pl-14">
                  {step.detail}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
