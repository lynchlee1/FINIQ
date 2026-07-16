"use client";

import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Check, Loader2, Play, RefreshCw, Save, Square } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Label,
} from "@finiq/ui";
import { ActionDock, JobStatusLogger, PageLoadingSpinner } from "@finiq/web-app/status";
import { apiPost } from "@/api/client";
import {
  DisclosureConditionFilterCard,
  makeEmptyDisclosureCondition,
  normalizeDisclosureConditionBlocks,
  type DisclosureConditionBlock,
  type DisclosureConditionPreset,
  type DisclosureConditionPresetPayload,
} from "@/components/disclosures/DisclosureConditionFilterCard";
import {
  DisclosureSearchConditionCard,
  DisclosureTypeSelectionCard,
} from "@/components/disclosures/DisclosureSearchSettingsCards";
import { DisclosureLockedSettingsCard } from "@/components/disclosures/DisclosureLockedSettingsCard";
import {
  HtmlSectionPatternCard,
  type SectionPattern,
} from "@/components/disclosures/HtmlSectionPatternCard";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { useJobPolling } from "@/hooks/useJobPolling";
import { formatInteger } from "@/lib/format";
import { useSettingsStore } from "@/store/useSettingsStore";
import type { DownloadOptions } from "@/features/download/types";
import { pickPath } from "@/lib/fileDialog";
import {
  deleteDisclosureConditionPreset,
  listDisclosureConditionPresets,
  renameDisclosureConditionPreset,
  saveDisclosureConditionPreset,
} from "@/lib/disclosureConditionPresets";

const PROFILE_STORAGE_KEY = "finiq.disclosureAutomation.profile.v1";
const PROFILE_FORMAT = "finiq_disclosure_automation_profile_v1";
const REVIEW_STORAGE_KEY = "finiq.disclosureAutomation.review.v1";

const STAGES = [
  { number: 1, key: "s1_download", label: "공시내역 다운로드", target: "search" },
  { number: 2, key: "s2_table", label: "공시내역 변환", target: null },
  { number: 3, key: "s3_filter", label: "공시내역 필터링", target: "filter" },
  { number: 4, key: "s4_external_html_download", label: "공시원문 외부 저장", target: null },
  { number: 5, key: "s5_internal_html_download", label: "공시원문 내부 저장", target: null },
  { number: 6, key: "s6_sections", label: "공시원문 목차 분리", target: "sections" },
  { number: 7, key: "s7_parse", label: "공시원문 변환", target: null },
] as const;

type StageKey = (typeof STAGES)[number]["key"];
type StageToggleState = Record<StageKey, boolean>;
type PlanAction = "disabled" | "reuse" | "process" | "review" | "blocked";
type RunStageStatus = "disabled" | "reused" | "succeeded" | "needs_download_confirmation" | "needs_review" | "failed";

type PlanStage = {
  stage: number;
  label: string;
  enabled: boolean;
  selected: boolean;
  plan_action: PlanAction;
  reason: string;
  last_success_at?: string | null;
};

type AutomationPlan = {
  execution_allowed: boolean;
  stages: PlanStage[];
  kind_limit: { max_requests_per_minute: number; max_in_flight: number };
};

type InspectionStage = {
  stage: number;
  label: string;
  confirmed: boolean;
  reason: string;
  details?: Record<string, unknown>;
  updated_at?: string | null;
};
type WorkspaceInspection = { stage: InspectionStage };

type ReviewPattern = SectionPattern;

type DownloadConflict = {
  range: string;
  saved_pages?: number | null;
  kind_pages?: number | null;
  reason: string;
};

type AutomationRunResult = {
  workflow_status: "completed" | "needs_download_confirmation" | "needs_review";
  stages: { stage: number; label: string; status: RunStageStatus; completed_at?: string }[];
  download_conflicts?: DownloadConflict[];
  download_confirmation?: string;
  review_patterns?: ReviewPattern[];
  output_path?: string;
};

type StoredProfile = {
  format: typeof PROFILE_FORMAT;
  name?: string;
  startDate?: string;
  endDate?: string;
  companyName?: string;
  submitterName?: string;
  marketLabel?: string;
  securitiesLabel?: string;
  disclosureTypeGroups?: Record<string, string[]>;
  conditions?: DisclosureConditionBlock[];
  sectionRules?: Record<string, string[]>;
  rangeStart?: number;
  rangeEnd?: number;
  parserMode?: string;
  pageSize?: number;
  localWorkers?: number;
  timeout?: number;
};

function localDateString() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

function firstDayOfYear() {
  return `${new Date().getFullYear()}-01-01`;
}

function loadJson<T>(key: string): T | null {
  const raw = window.localStorage.getItem(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    throw new Error(`브라우저 저장값을 읽지 못했습니다: ${key}`);
  }
}

function loadStoredProfile(): StoredProfile | null {
  const stored = loadJson<unknown>(PROFILE_STORAGE_KEY);
  if (stored === null) return null;
  if (
    typeof stored !== "object"
    || Array.isArray(stored)
    || stored === null
    || !("format" in stored)
    || stored.format !== PROFILE_FORMAT
  ) {
    throw new Error("저장된 공시 자동화 설정 형식을 지원하지 않습니다.");
  }
  return stored as StoredProfile;
}

function planLabel(action?: PlanAction | "confirmed" | "mismatch") {
  if (action === "confirmed") return "확인됨";
  if (action === "mismatch") return "확인 필요";
  if (action === "disabled") return "사용 안 함";
  if (action === "reuse") return "재사용";
  if (action === "process") return "실행 예정";
  if (action === "review") return "Pending";
  if (action === "blocked") return "차단됨";
  return "확인 전";
}

function planTone(action?: PlanAction | "confirmed" | "mismatch") {
  if (action === "blocked" || action === "review" || action === "mismatch") return "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200";
  if (action === "process") return "border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-200";
  if (action === "reuse" || action === "confirmed") return "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200";
  return "border-[color:var(--tv-border)] bg-[var(--tv-control)] text-[var(--tv-muted)]";
}

function runStatusLabel(status?: RunStageStatus) {
  if (status === "disabled") return "사용 안 함";
  if (status === "reused") return "완료 · 재사용";
  if (status === "succeeded") return "완료";
  if (status === "needs_download_confirmation") return "확인 필요";
  if (status === "needs_review") return "Pending";
  if (status === "failed") return "실패";
  return "대기 중";
}

function formatCompletedAt(value?: string | null) {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("ko-KR");
}

export default function DisclosureAutomationPage() {
  const {
    output_root: storedRoot,
    html_parse_mode: storedMode,
    parallel_worker_count: parallelWorkerCount,
    fetchSettings,
    saveSetting,
  } = useSettingsStore();
  const [loading, setLoading] = useState(true);
  const [initializationError, setInitializationError] = useState<Error | null>(null);
  const [name, setName] = useState("공시 자동화");
  const [dataRoot, setDataRoot] = useState("");
  const [startDate, setStartDate] = useState(firstDayOfYear());
  const [endDate, setEndDate] = useState(localDateString());
  const [companyName, setCompanyName] = useState("");
  const [submitterName, setSubmitterName] = useState("");
  const [marketLabel, setMarketLabel] = useState("전체");
  const [securitiesLabel, setSecuritiesLabel] = useState("전체");
  const [disclosureTypeGroups, setDisclosureTypeGroups] = useState<Record<string, string[]>>({});
  const [conditions, setConditions] = useState<DisclosureConditionBlock[]>([makeEmptyDisclosureCondition()]);
  const [sectionRules, setSectionRules] = useState<Record<string, string[]>>({});
  const [rangeStart, setRangeStart] = useState(1);
  const [rangeEnd, setRangeEnd] = useState(7);
  const [parserMode, setParserMode] = useState("bond_issuance");
  const [pageSize, setPageSize] = useState("100");
  const [localWorkers, setLocalWorkers] = useState("1");
  const [timeout, setTimeoutValue] = useState("20");
  const [downloadOptions, setDownloadOptions] = useState<DownloadOptions | null>(null);
  const [plan, setPlan] = useState<AutomationPlan | null>(null);
  const [workspaceInspections, setWorkspaceInspections] = useState<Record<number, InspectionStage>>({});
  const [inspectingStage, setInspectingStage] = useState<number | null>(null);
  const [runResult, setRunResult] = useState<AutomationRunResult | null>(null);
  const [downloadConflicts, setDownloadConflicts] = useState<DownloadConflict[]>([]);
  const [downloadConfirmation, setDownloadConfirmation] = useState("");
  const [reviewPatterns, setReviewPatterns] = useState<ReviewPattern[]>([]);
  const [reviewSelections, setReviewSelections] = useState<Record<string, string[]>>({});
  const [reviewDecided, setReviewDecided] = useState<Record<string, boolean>>({});
  const [presetName, setPresetName] = useState("");
  const [selectedPreset, setSelectedPreset] = useState("");
  const [presets, setPresets] = useState<DisclosureConditionPreset[]>([]);
  const [filterPresetPath, setFilterPresetPath] = useState("");
  const [notification, setNotification] = useState("");
  const searchSettingsRef = useRef<HTMLDivElement | null>(null);
  const filterSettingsRef = useRef<HTMLDivElement | null>(null);
  const sectionSettingsRef = useRef<HTMLDivElement | null>(null);
  const rangeDragAnchorRef = useRef<number | null>(null);
  const lastRangeDragValueRef = useRef<number | null>(null);

  const formatStatus = (snapshot: any) => {
    const lines = [`작업 상태: ${snapshot.status === "running" ? "실행 중" : snapshot.status === "completed" ? "완료" : snapshot.status === "failed" ? "실패" : snapshot.status === "cancelled" ? "취소됨" : "대기 중"}`];
    if (snapshot.error) lines.push(`오류: ${snapshot.error}`);
    if (Array.isArray(snapshot.progress_log) && snapshot.progress_log.length) {
      lines.push("", "최근 로그", ...snapshot.progress_log.slice(-30));
    }
    return lines;
  };

  const {
    status,
    isErrorStatus,
    activeJobId,
    startPolling,
    setStatus,
    setIsErrorStatus,
    cancelJob,
  } = useJobPolling({
    pollingEndpoint: "/api/disclosure-workflows/jobs/{jobId}",
    cancelEndpoint: "/api/disclosure-workflows/run/cancel",
    formatStatus,
    onSuccess: (result: AutomationRunResult) => {
      setRunResult(result);
      if (result.workflow_status === "needs_download_confirmation") {
        const conflicts = result.download_conflicts || [];
        setDownloadConflicts(conflicts);
        setDownloadConfirmation(result.download_confirmation || "");
        setNotification(`페이지 수 충돌 ${formatInteger(conflicts.length)}개를 확인하세요.`);
        setIsErrorStatus(true);
        return;
      }
      setDownloadConflicts([]);
      setDownloadConfirmation("");
      if (result.workflow_status === "needs_review") {
        const patterns = result.review_patterns || [];
        setReviewPatterns(patterns);
        setReviewSelections({});
        setReviewDecided({});
        window.localStorage.setItem(REVIEW_STORAGE_KEY, JSON.stringify(patterns));
        setNotification(`Pending · 목차 조합 ${formatInteger(patterns.length)}개에 입력이 필요합니다.`);
      } else {
        setReviewPatterns([]);
        window.localStorage.removeItem(REVIEW_STORAGE_KEY);
        setNotification("공시 자동화가 완료되었습니다.");
      }
      void refreshPlan(result.workflow_status === "needs_review" ? "review" : "resume");
    },
    onError: (error) => setNotification(error.message),
    onCancel: () => setNotification("실행을 취소했습니다. 완료된 단계는 다음 실행에서 재사용됩니다."),
  });

  useEffect(() => {
    Promise.all([
      fetchSettings(),
      fetch("/api/download/options", { cache: "no-store" }).then(
        (response): Promise<DownloadOptions | null> => response.ok ? response.json() : Promise.resolve(null),
      ),
    ]).then(([config, options]) => {
      const stored = loadStoredProfile();
      setDownloadOptions(options);
      setDataRoot(config?.output_root || "");
      setName(stored?.name || "공시 자동화");
      setStartDate(stored?.startDate || firstDayOfYear());
      setEndDate(stored?.endDate || localDateString());
      setCompanyName(stored?.companyName || "");
      setSubmitterName(stored?.submitterName || "");
      setMarketLabel(stored?.marketLabel || "전체");
      setSecuritiesLabel(stored?.securitiesLabel || "전체");
      setDisclosureTypeGroups(stored?.disclosureTypeGroups || {});
      setConditions(normalizeDisclosureConditionBlocks(stored?.conditions));
      setSectionRules(stored?.sectionRules || {});
      setRangeStart(stored?.rangeStart ?? 1);
      setRangeEnd(stored?.rangeEnd ?? 7);
      setParserMode(stored?.parserMode || config?.html_parse_mode || "bond_issuance");
      setPageSize(String(stored?.pageSize || 100));
      const workerLimit = Number(config?.parallel_worker_count || 1);
      setLocalWorkers(String(Math.min(stored?.localWorkers || workerLimit, workerLimit)));
      setTimeoutValue(String(stored?.timeout || 20));
      const storedReview = loadJson<ReviewPattern[]>(REVIEW_STORAGE_KEY) || [];
      setReviewPatterns(storedReview);
    }).catch((error) => {
      setInitializationError(error instanceof Error ? error : new Error(String(error)));
    }).finally(() => setLoading(false));
  }, [fetchSettings]);

  useEffect(() => {
    if (!dataRoot.trim()) {
      setPresets([]);
      return;
    }
    listDisclosureConditionPresets(dataRoot).then((response) => {
      setPresets(response.presets);
    }).catch((error) => {
      setPresets([]);
      setNotification(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    });
  }, [dataRoot, setIsErrorStatus]);

  useEffect(() => {
    setWorkspaceInspections({});
  }, [
    companyName,
    conditions,
    dataRoot,
    disclosureTypeGroups,
    endDate,
    marketLabel,
    pageSize,
    parserMode,
    sectionRules,
    securitiesLabel,
    startDate,
    submitterName,
  ]);

  const normalizedConditions = useMemo(() => normalizeDisclosureConditionBlocks(conditions), [conditions]);
  const executionMask = useMemo(
    () => STAGES.filter((stage) => stage.number >= rangeStart && stage.number <= rangeEnd).map((stage) => stage.number),
    [rangeEnd, rangeStart],
  );
  const steps = useMemo(
    () => Object.fromEntries(STAGES.map((stage) => [stage.key, true])) as StageToggleState,
    [],
  );
  const searchSettingsSelected = executionMask.includes(1);
  const filterSettingsSelected = executionMask.includes(3);
  const sectionSettingsSelected = executionMask.includes(6);

  const buildProfile = (
    trigger: "sync" | "resume" | "review",
    sectionRulesOverride: Record<string, string[]> = sectionRules,
    confirmedDownload = "",
  ) => ({
    name,
    data_root: dataRoot,
    trigger,
    steps,
    execution_mask: executionMask,
    decisions: {
      s1_search: {
        start_date: startDate,
        end_date: endDate,
        company_name: companyName,
        submitter_name: submitterName,
        market_label: marketLabel,
        securities_label: securitiesLabel,
        disclosure_type_groups: disclosureTypeGroups,
        last_report_only: false,
      },
      s3_selection: { filter_blocks: normalizedConditions },
      s6_sections: { unmatched_policy: "needs_review", section_save_rules: sectionRulesOverride },
    },
    execution: {
      parser_mode: parserMode,
      page_size: Number(pageSize || 100),
      local_workers: Number(localWorkers || parallelWorkerCount || 1),
      timeout: Number(timeout || 20),
    },
    download_confirmation: confirmedDownload,
  });

  const saveProfile = async (
    sectionRulesOverride: Record<string, string[]> = sectionRules,
  ) => {
    const stored: StoredProfile = {
      format: PROFILE_FORMAT,
      name,
      startDate,
      endDate,
      companyName,
      submitterName,
      marketLabel,
      securitiesLabel,
      disclosureTypeGroups,
      conditions: normalizedConditions,
      sectionRules: sectionRulesOverride,
      rangeStart,
      rangeEnd,
      parserMode,
      pageSize: Number(pageSize || 100),
      localWorkers: Number(localWorkers || parallelWorkerCount || 1),
      timeout: Number(timeout || 20),
    };
    window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(stored));
    const rootSaved = dataRoot === storedRoot || await saveSetting("output_root", dataRoot);
    const modeSaved = parserMode === storedMode || await saveSetting("html_parse_mode", parserMode);
    if (!rootSaved || !modeSaved) throw new Error("공시 자동화 설정을 저장하지 못했습니다.");
  };

  async function refreshPlan(trigger: "sync" | "resume" | "review" = "sync") {
    try {
      const next = await apiPost<AutomationPlan>("/api/disclosure-workflows/plan", buildProfile(trigger));
      setPlan(next);
      setNotification(next.execution_allowed ? "실행 계획을 확인했습니다." : "차단된 단계의 선행 결과를 확인하세요.");
      setIsErrorStatus(!next.execution_allowed);
      return next;
    } catch (error) {
      setNotification(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
      return null;
    }
  }

  async function inspectStage(stage: number) {
    if (!dataRoot.trim()) {
      setNotification("데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    setInspectingStage(stage);
    try {
      const result = await apiPost<WorkspaceInspection>("/api/disclosure-workflows/inspect", {
        ...buildProfile("resume"),
        stage,
      });
      setWorkspaceInspections((current) => ({ ...current, [stage]: result.stage }));
      setNotification(`${result.stage.label} 작업 결과를 검사했습니다.`);
      setIsErrorStatus(false);
    } catch (error) {
      setNotification(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    } finally {
      setInspectingStage(null);
    }
  }

  const startRun = async (
    trigger: "sync" | "resume" | "review",
    sectionRulesOverride: Record<string, string[]> = sectionRules,
    confirmedDownload = "",
  ) => {
    try {
      await saveProfile(sectionRulesOverride);
      const nextPlan = await apiPost<AutomationPlan>(
        "/api/disclosure-workflows/plan",
        buildProfile(trigger, sectionRulesOverride, confirmedDownload),
      );
      setPlan(nextPlan);
      if (!nextPlan?.execution_allowed) {
        setNotification("차단된 단계의 선행 결과를 확인하세요.");
        setIsErrorStatus(true);
        return;
      }
      setRunResult(null);
      setStatus("공시 자동화를 시작하는 중...");
      setIsErrorStatus(false);
      const started = await apiPost<{ job_id: string }>(
        "/api/disclosure-workflows/run/start",
        buildProfile(trigger, sectionRulesOverride, confirmedDownload),
      );
      startPolling(started.job_id);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setStatus(message);
      setNotification(message);
      setIsErrorStatus(true);
    }
  };

  const changeRange = (start: number, end: number) => {
    setRangeStart(start);
    setRangeEnd(end);
    setPlan(null);
  };

  const rangeSelectionDisabled = !!activeJobId || !!downloadConflicts.length || !!reviewPatterns.length;

  const selectRangeThrough = (value: number) => {
    const anchor = rangeDragAnchorRef.current;
    if (anchor === null || lastRangeDragValueRef.current === value) return;
    lastRangeDragValueRef.current = value;
    changeRange(Math.min(anchor, value), Math.max(anchor, value));
  };

  const rangeValueAtPointer = (event: ReactPointerEvent<HTMLTableSectionElement>) => {
    const element = document.elementFromPoint(event.clientX, event.clientY);
    const taskElement = element?.closest<HTMLElement>("[data-workflow-task-value]");
    const value = Number(taskElement?.dataset.workflowTaskValue);
    return STAGES.some((stage) => stage.number === value) ? value : null;
  };

  const handleRangePointerDown = (event: ReactPointerEvent<HTMLTableSectionElement>) => {
    if (rangeSelectionDisabled || event.button !== 0) return;
    const value = rangeValueAtPointer(event);
    if (value === null) return;
    rangeDragAnchorRef.current = value;
    lastRangeDragValueRef.current = null;
    event.currentTarget.setPointerCapture(event.pointerId);
    selectRangeThrough(value);
  };

  const handleRangePointerMove = (event: ReactPointerEvent<HTMLTableSectionElement>) => {
    if (rangeDragAnchorRef.current === null) return;
    const value = rangeValueAtPointer(event);
    if (value !== null) selectRangeThrough(value);
  };

  const finishRangeDrag = (event: ReactPointerEvent<HTMLTableSectionElement>) => {
    rangeDragAnchorRef.current = null;
    lastRangeDragValueRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const applyPreset = (preset: DisclosureConditionPresetPayload, message: string) => {
    setConditions(normalizeDisclosureConditionBlocks(preset.condition_blocks));
    if (preset.mode) setParserMode(preset.mode);
    if (preset.name) setPresetName(preset.name);
    setNotification(message);
    setIsErrorStatus(false);
    setPlan(null);
  };

  const loadPreset = (presetNameToLoad: string) => {
    const preset = (presets || []).find((item: any) => item.name === presetNameToLoad);
    if (!preset) {
      setNotification("선택한 프리셋을 찾을 수 없습니다.");
      setIsErrorStatus(true);
      return;
    }
    applyPreset(preset, `조건검색 프리셋을 불러왔습니다: ${preset.name}`);
  };

  const savePreset = async () => {
    const nextName = presetName.trim();
    if (!nextName) {
      setNotification("저장할 프리셋 이름을 입력하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (!dataRoot.trim()) {
      setNotification("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      const response = await saveDisclosureConditionPreset(dataRoot, {
        name: nextName,
        mode: parserMode,
        condition_blocks: normalizedConditions,
      });
      setPresets(response.presets);
      setSelectedPreset(nextName);
      setNotification(`조건검색 프리셋을 저장했습니다: ${nextName}`);
      setIsErrorStatus(false);
    } catch (error) {
      setNotification(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    }
  };

  const renamePreset = async () => {
    if (!selectedPreset) return;
    const nextName = presetName.trim();
    if (!nextName) {
      setNotification("수정할 프리셋 이름을 입력하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (nextName !== selectedPreset && (presets || []).some((item: any) => item.name === nextName)) {
      setNotification(`이미 같은 이름의 프리셋이 있습니다: ${nextName}`);
      setIsErrorStatus(true);
      return;
    }
    if (!dataRoot.trim()) {
      setNotification("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      const response = await renameDisclosureConditionPreset(dataRoot, selectedPreset, nextName);
      setPresets(response.presets);
      setSelectedPreset(nextName);
      setPresetName(nextName);
      setNotification(`조건검색 프리셋 이름을 수정했습니다: ${selectedPreset} -> ${nextName}`);
      setIsErrorStatus(false);
    } catch (error) {
      setNotification(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    }
  };

  const loadFilterPresetFromJson = async () => {
    try {
      const sourceJsonPath = await pickPath({
        mode: "file",
        title: "필터 결과 JSON 선택",
        defaultPath: filterPresetPath,
      });
      if (!sourceJsonPath) return;
      setFilterPresetPath(sourceJsonPath);
      const preset = await apiPost<DisclosureConditionPresetPayload>("/api/disclosures/filter/preset", {
        source_json_path: sourceJsonPath,
      });
      setSelectedPreset("");
      applyPreset(preset, `필터 결과 JSON에서 조건을 불러왔습니다: ${preset.source_json_path || sourceJsonPath}`);
    } catch (error) {
      setNotification(error instanceof Error ? error.message : "필터 결과 JSON을 불러오지 못했습니다.");
      setIsErrorStatus(true);
    }
  };

  const deletePreset = async () => {
    if (!selectedPreset) return;
    if (!dataRoot.trim()) {
      setNotification("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      const response = await deleteDisclosureConditionPreset(dataRoot, selectedPreset);
      setPresets(response.presets);
      setPresetName((value) => value === selectedPreset ? "" : value);
      setSelectedPreset("");
      setNotification(`조건검색 프리셋을 삭제했습니다: ${selectedPreset}`);
      setIsErrorStatus(false);
    } catch (error) {
      setNotification(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    }
  };

  const decideReviewPattern = (pattern: ReviewPattern, tocIds: string[]) => {
    setReviewSelections((current) => ({ ...current, [pattern.signature]: tocIds }));
    setReviewDecided((current) => ({ ...current, [pattern.signature]: true }));
  };

  const confirmDownloadConflicts = () => {
    if (!downloadConfirmation) return;
    void startRun("sync", sectionRules, downloadConfirmation);
  };

  const runAfterReview = async () => {
    const unresolved = reviewPatterns.filter((pattern) => !reviewDecided[pattern.signature]);
    if (unresolved.length) {
      setNotification(`Pending · 목차 조합 ${formatInteger(unresolved.length)}개가 아직 결정되지 않았습니다.`);
      setIsErrorStatus(true);
      return;
    }
    const nextRules = { ...sectionRules, ...reviewSelections };
    setSectionRules(nextRules);
    const stored = loadStoredProfile();
    window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify({ ...stored, format: PROFILE_FORMAT, sectionRules: nextRules }));
    void startRun("review", nextRules);
  };

  const runStageStatus = (stage: number) => runResult?.stages.find((item) => item.stage === stage)?.status;
  const planForStage = (stage: number) => plan?.stages.find((item) => item.stage === stage);
  const inspectionForStage = (stage: number) => workspaceInspections[stage];

  if (initializationError) throw initializationError;
  if (loading) return <PageLoadingSpinner message="공시 자동화 설정을 불러오는 중입니다..." />;

  return (
    <WorkflowPageShell workflowId="disclosure-build">
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          <Card className="border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
            <CardHeader className="pb-4">
              <CardTitle className="text-[var(--tv-text)]">작업표</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="overflow-x-auto rounded-md border border-[color:var(--tv-border)]">
                <table className="w-full min-w-[920px] border-collapse text-left text-sm">
                  <thead className="bg-[var(--tv-control)] text-sm font-semibold text-[var(--tv-muted)]">
                    <tr>
                      <th className="px-5 py-3.5">작업</th>
                      <th className="px-5 py-3.5">실행 계획</th>
                      <th className="px-5 py-3.5">작업 상태</th>
                      <th className="px-5 py-3.5">마지막 성공</th>
                      <th className="w-32 px-5 py-3.5"><span className="sr-only">설정</span></th>
                    </tr>
                  </thead>
                  <tbody
                    className="divide-y divide-[color:var(--tv-border)]"
                    onPointerDown={handleRangePointerDown}
                    onPointerMove={handleRangePointerMove}
                    onPointerUp={finishRangeDrag}
                    onPointerCancel={finishRangeDrag}
                    onLostPointerCapture={() => {
                      rangeDragAnchorRef.current = null;
                      lastRangeDragValueRef.current = null;
                    }}
                  >
                    {STAGES.map((stage) => {
                      const stagePlan = planForStage(stage.number);
                      const statusValue = runStageStatus(stage.number)
                        || (stage.number === 6 && reviewPatterns.length ? "needs_review" : undefined);
                      const planAction = stage.number === 6 && reviewPatterns.length
                        ? "review"
                        : stagePlan?.plan_action;
                      const stageInspection = inspectionForStage(stage.number);
                      const displayedPlanAction = stage.number === 6 && reviewPatterns.length
                        ? "review"
                        : stageInspection
                          ? stageInspection.confirmed ? "confirmed" : "mismatch"
                          : planAction;
                      const inRange = executionMask.includes(stage.number);
                      const isRangeStart = stage.number === rangeStart;
                      const isRangeEnd = stage.number === rangeEnd;
                      const rangePositionLabel = isRangeStart && isRangeEnd
                        ? "선택 범위"
                        : isRangeStart
                          ? "선택 범위 시작"
                          : isRangeEnd
                            ? "선택 범위 끝"
                            : inRange ? "선택 범위 안" : "선택 범위 밖";
                      const settingsTarget = stage.target === "search"
                        ? searchSettingsRef
                        : stage.target === "filter"
                          ? filterSettingsRef
                          : stage.target === "sections"
                            ? sectionSettingsRef
                            : null;
                      return (
                        <tr key={stage.key} className={inRange ? "text-[var(--tv-text)]" : "bg-[var(--tv-control)]/30 text-[var(--tv-muted)]"}>
                          <td className="px-5 py-2 align-middle">
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                data-workflow-task-value={stage.number}
                                disabled={rangeSelectionDisabled}
                                aria-pressed={inRange}
                                aria-label={`${stage.label}, ${rangePositionLabel}`}
                                title="드래그하여 시작·종료 작업 선택"
                                className={`flex h-4 w-4 shrink-0 touch-none select-none items-center justify-center rounded-sm border outline-none focus-visible:ring-2 focus-visible:ring-[var(--tv-accent)] ${inRange ? "border-[color:var(--tv-accent)] bg-[var(--tv-accent)] text-[var(--tv-surface)]" : "border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-muted)]"} ${rangeSelectionDisabled ? "cursor-not-allowed" : "cursor-grab active:cursor-grabbing"}`}
                                onKeyDown={(event) => {
                                  if (event.key !== "Enter" && event.key !== " ") return;
                                  event.preventDefault();
                                  changeRange(stage.number, stage.number);
                                }}
                              >
                                {inRange ? <Check className="h-2.5 w-2.5" aria-hidden="true" /> : null}
                              </button>
                              <span className="text-sm font-medium">{stage.label}</span>
                            </div>
                          </td>
                          <td className="px-5 py-2 align-middle">
                            <span className={`inline-flex rounded-full border px-3 py-1.5 text-sm font-semibold ${planTone(displayedPlanAction)}`}>{planLabel(displayedPlanAction)}</span>
                            {stageInspection?.reason || stagePlan?.reason ? <p className="mt-2 max-w-[260px] text-sm leading-5 text-[var(--tv-muted)]">{stageInspection?.reason || stagePlan?.reason}</p> : null}
                          </td>
                          <td className="px-5 py-2 align-middle text-sm text-[var(--tv-muted)]">{activeJobId && stagePlan?.plan_action === "process" && !statusValue ? "대기 중" : runStatusLabel(statusValue)}</td>
                          <td className="px-5 py-2 align-middle text-sm text-[var(--tv-muted)]">{formatCompletedAt(stagePlan?.last_success_at)}</td>
                          <td className="px-5 py-2 align-middle">
                            <div className="flex justify-end gap-2">
                              {settingsTarget ? (
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  className="h-8 border-[color:var(--tv-border)] bg-[var(--tv-surface)] px-3 text-sm text-[var(--tv-text)]"
                                  onClick={() => settingsTarget.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
                                >
                                  설정
                                </Button>
                              ) : null}
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-8 border-[color:var(--tv-border)] bg-[var(--tv-surface)] px-3 text-sm text-[var(--tv-text)]"
                                onClick={() => void inspectStage(stage.number)}
                                disabled={!!activeJobId || inspectingStage !== null}
                              >
                                검사
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          <div ref={searchSettingsRef} className="scroll-mt-6 space-y-6">
            {searchSettingsSelected ? <>
              <DisclosureSearchConditionCard
              options={downloadOptions}
              startDate={startDate}
              endDate={endDate}
              companyName={companyName}
              submitterName={submitterName}
              marketLabel={marketLabel}
              securitiesLabel={securitiesLabel}
              onStartDateChange={(value) => { setStartDate(value); setPlan(null); }}
              onEndDateChange={(value) => { setEndDate(value); setPlan(null); }}
              onCompanyNameChange={(value) => { setCompanyName(value); setPlan(null); }}
              onSubmitterNameChange={(value) => { setSubmitterName(value); setPlan(null); }}
              onMarketLabelChange={(value) => { setMarketLabel(value); setPlan(null); }}
              onSecuritiesLabelChange={(value) => { setSecuritiesLabel(value); setPlan(null); }}
              beforeFields={(
                <div className="grid gap-2">
                  <Label className="dark:text-slate-300">데이터 경로</Label>
                  <PathPickerInput
                    mode="folder"
                    value={dataRoot}
                    onChange={(value) => { setDataRoot(value); setPlan(null); }}
                    onError={(error) => { setNotification(error.message); setIsErrorStatus(true); }}
                  />
                </div>
              )}
              />
              <DisclosureTypeSelectionCard
                options={downloadOptions}
                selectedDisclosures={disclosureTypeGroups}
                onSelectedDisclosuresChange={(value) => { setDisclosureTypeGroups(value); setPlan(null); }}
              />
            </> : <>
              <DisclosureLockedSettingsCard title="검색 조건" />
              <DisclosureLockedSettingsCard title="공시 종류" />
            </>}
          </div>

          <div ref={filterSettingsRef} className="scroll-mt-6">
            {filterSettingsSelected ? <DisclosureConditionFilterCard
              conditions={conditions}
              onConditionsChange={(value) => { setConditions(value); setPlan(null); }}
              presets={presets || []}
              presetName={presetName}
              selectedPreset={selectedPreset}
              onPresetNameChange={setPresetName}
              onSelectedPresetChange={setSelectedPreset}
              onLoadPreset={loadPreset}
              onLoadPresetFromJson={loadFilterPresetFromJson}
              onSavePreset={savePreset}
              onRenamePreset={renamePreset}
              onDeletePreset={deletePreset}
            /> : <DisclosureLockedSettingsCard title="공시 조건" />}
          </div>

          <div ref={sectionSettingsRef} className="scroll-mt-6 space-y-4">
            {sectionSettingsSelected || reviewPatterns.length ? <HtmlSectionPatternCard
              inputDirectory={`${dataRoot}/05-internal-html-download/${parserMode}/.automation-current`}
              sectionPatterns={reviewPatterns}
              selectedPatternTocIds={reviewSelections}
              isLoading={false}
              onTogglePatternSection={(signature, tocId) => {
                const pattern = reviewPatterns.find((item) => item.signature === signature);
                if (!pattern) return;
                const selection = reviewSelections[signature] || [];
                decideReviewPattern(pattern, selection.includes(tocId) ? selection.filter((item) => item !== tocId) : [...selection, tocId]);
              }}
              onSetPatternSelection={(signature, tocIds) => {
                const pattern = reviewPatterns.find((item) => item.signature === signature);
                if (pattern) decideReviewPattern(pattern, tocIds);
              }}
              decidedPatterns={reviewDecided}
              pending={!runResult || !!activeJobId || !!reviewPatterns.length}
              emptyText="판단이 필요한 새 목차 조합이 없습니다."
            /> : <DisclosureLockedSettingsCard title="목차 조합 모아보기" />}
            <div>
              {reviewPatterns.length ? <Button onClick={runAfterReview} disabled={!!activeJobId}><RefreshCw className="mr-2 h-4 w-4" />후속 실행</Button> : null}
            </div>
          </div>

          <Card className="border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
            <CardHeader><CardTitle className="text-[var(--tv-text)]">작업 실행</CardTitle></CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
              <Button variant="outline" onClick={() => void saveProfile().then(() => setNotification("공시 자동화 설정을 저장했습니다.")).catch((error) => setNotification(error.message))} disabled={!!activeJobId}><Save className="mr-2 h-4 w-4" />설정 저장</Button>
              <Button variant="outline" onClick={() => void refreshPlan("sync")} disabled={!!activeJobId}><RefreshCw className="mr-2 h-4 w-4" />실행 계획</Button>
              <Button onClick={() => void startRun("sync")} disabled={!!activeJobId || !!downloadConflicts.length || !!reviewPatterns.length}>{activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}동기화</Button>
              <Button variant="outline" onClick={() => void startRun("resume")} disabled={!!activeJobId || !!downloadConflicts.length || !!reviewPatterns.length}><Play className="mr-2 h-4 w-4" />이어서 실행</Button>
              <Button variant="outline" onClick={cancelJob} disabled={!activeJobId}><Square className="mr-2 h-4 w-4" />취소</Button>
            </CardContent>
          </Card>
        </section>

        <ActionDock
          activityActive={!!activeJobId}
          activityContent={<JobStatusLogger status={status} isErrorStatus={isErrorStatus} isCancellable={!!activeJobId} onCancel={cancelJob} />}
          notificationActive={isErrorStatus || !!downloadConflicts.length || !!reviewPatterns.length || !!notification}
          notificationDismissible={!downloadConflicts.length}
          notificationResetKey={`${notification}:${downloadConfirmation}:${reviewPatterns.length}`}
          notificationContent={
            <div className="space-y-3 text-sm text-[var(--tv-text)]">
              <p className="whitespace-pre-wrap">{notification || "알림 없음"}</p>
              {downloadConflicts.length ? <>
                <ul className="space-y-2">
                  {downloadConflicts.map((conflict) => <li key={conflict.range} className="rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
                    <p className="font-medium">{conflict.range}</p>
                    <p>{conflict.reason}</p>
                    {conflict.saved_pages != null || conflict.kind_pages != null ? <p>저장 {conflict.saved_pages ?? "확인 불가"}페이지 · KIND {conflict.kind_pages ?? "확인 불가"}페이지</p> : null}
                  </li>)}
                </ul>
                <Button onClick={confirmDownloadConflicts} disabled={!!activeJobId || !downloadConfirmation}>
                  <RefreshCw className="mr-2 h-4 w-4" />전체 다시 받기
                </Button>
              </> : null}
              {reviewPatterns.length ? <p className="font-medium text-amber-700 dark:text-amber-300">Pending · 목차 조합 {formatInteger(reviewPatterns.length)}개를 결정하세요.</p> : null}
            </div>
          }
          settingsTitle="실행 설정"
          settingsContent={
            <div className="space-y-4">
              <Label className="grid gap-2 text-[var(--tv-text)]">이름
                <Input value={name} onChange={(event) => { setName(event.target.value); setPlan(null); }} />
              </Label>
              <Label className="grid gap-2 text-[var(--tv-text)]">파싱 모드
                <select value={parserMode} onChange={(event) => { setParserMode(event.target.value); setPlan(null); }} className="h-9 rounded-md border border-[color:var(--tv-border)] bg-[var(--tv-surface)] px-3 text-sm">
                  <option value="bond_issuance">bond_issuance</option>
                  <option value="rights_issuance">rights_issuance</option>
                  <option value="shareholder_meeting">shareholder_meeting</option>
                </select>
              </Label>
              <Label className="grid gap-2 text-[var(--tv-text)]">페이지당 공시 수<Input type="number" min="1" max="100" value={pageSize} onChange={(event) => { setPageSize(event.target.value); setPlan(null); }} /></Label>
              <Label className="grid gap-2 text-[var(--tv-text)]">로컬 worker 수<Input type="number" min="1" max={parallelWorkerCount} value={localWorkers} onChange={(event) => { setLocalWorkers(event.target.value); setPlan(null); }} /></Label>
              <Label className="grid gap-2 text-[var(--tv-text)]">요청 timeout(초)<Input type="number" min="1" max="120" value={timeout} onChange={(event) => { setTimeoutValue(event.target.value); setPlan(null); }} /></Label>
              <div className="rounded-lg border border-[color:var(--tv-border)] bg-[var(--tv-control)] p-3 text-xs leading-5 text-[var(--tv-muted)]">
                KIND 검색·외부 HTML은 분당 최대 45회, 내부 HTML의 실제 HTTP 요청은 분당 최대 30회, 동시 요청은 1개로 고정합니다.
              </div>
            </div>
          }
        />
      </div>
    </WorkflowPageShell>
  );
}
