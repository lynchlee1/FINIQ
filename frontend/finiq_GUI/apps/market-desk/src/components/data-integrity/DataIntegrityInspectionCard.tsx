import { ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@finiq/ui";
import {
  DataIntegrityInspectionPanel,
  type DataIntegrityInspectionStep,
  type DataIntegrityInspectionVerdict,
} from "./DataIntegrityInspectionPanel";

type DataIntegrityInspectionCardProps = {
  description: string;
  steps: DataIntegrityInspectionStep[];
  verdict: DataIntegrityInspectionVerdict;
};

export type SingleCheckDataIntegrityInspectionState =
  | "waiting"
  | "ready"
  | "running"
  | "action-required"
  | "success"
  | "failed";

type SingleCheckDataIntegrityInspectionCardProps = {
  action?: DataIntegrityInspectionStep["action"];
  description: string;
  numbered?: boolean;
  /**
   * Follow-up steps listed under the main check. An incomplete extra step keeps
   * the overall verdict off `정상`; completed rows may still show `정상`.
   */
  extraSteps?: DataIntegrityInspectionStep[];
  state: SingleCheckDataIntegrityInspectionState;
  /**
   * Status of the main check row. Defaults to `state`. Pass `success` while
   * `state` is still `running` when later steps remain.
   */
  stepState?: SingleCheckDataIntegrityInspectionState;
  stepSummary: string;
  stepTitle: string;
  verdictDescription: string;
  verdictTitle: string;
};

const singleCheckState = {
  waiting: { label: "대기", tone: "neutral", stepStatus: "waiting", stepLabel: "대기" },
  ready: { label: "대기", tone: "neutral", stepStatus: "waiting", stepLabel: "대기" },
  running: { label: "검사 중", tone: "neutral", stepStatus: "running", stepLabel: "검사 중" },
  "action-required": { label: "다운로드 필요", tone: "warning", stepStatus: "ready", stepLabel: "다운로드 필요" },
  success: { label: "정상", tone: "success", stepStatus: "complete", stepLabel: "정상" },
  failed: { label: "사용 불가", tone: "error", stepStatus: "failed", stepLabel: "사용 불가" },
} as const;

export function DataIntegrityInspectionCard({
  description,
  steps,
  verdict,
}: DataIntegrityInspectionCardProps) {
  return (
    <Card className="border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
      <CardHeader className="gap-1.5">
        <div className="space-y-1.5">
          <CardTitle className="flex items-center gap-2 text-[16px] leading-6 dark:text-white">
            <ShieldCheck className="h-5 w-5 text-[var(--tv-accent)]" />
            기존 데이터 검토
          </CardTitle>
          <p className="text-[13px] leading-5 text-[var(--tv-muted)]">{description}</p>
        </div>
      </CardHeader>
      <CardContent>
        <DataIntegrityInspectionPanel verdict={verdict} steps={steps} />
      </CardContent>
    </Card>
  );
}

export function SingleCheckDataIntegrityInspectionCard({
  action,
  description,
  extraSteps,
  numbered,
  state,
  stepState = state,
  stepSummary,
  stepTitle,
  verdictDescription,
  verdictTitle,
}: SingleCheckDataIntegrityInspectionCardProps) {
  const display = singleCheckState[state];
  const stepDisplay = singleCheckState[stepState];
  return (
    <DataIntegrityInspectionCard
      description={description}
      verdict={{
        label: display.label,
        title: verdictTitle,
        description: verdictDescription,
        tone: display.tone,
      }}
      steps={[
        {
          key: "integrity",
          numbered,
          title: stepTitle,
          summary: stepSummary,
          status: stepDisplay.stepStatus,
          statusLabel: stepDisplay.stepLabel,
          action,
        },
        ...(extraSteps ?? []),
      ]}
    />
  );
}
