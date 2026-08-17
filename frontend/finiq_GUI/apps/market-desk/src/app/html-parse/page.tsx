"use client"

import { useState, useEffect, useCallback, useRef } from "react";
import { ExternalLink, Eye, Loader2, Play, Square } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import { JobStatusLogger, PageLoadingSpinner, ActionDock } from "@finiq/web-app/status";
import { useSettingsStore } from "@/store/useSettingsStore";
import { useJobPolling } from "@/hooks/useJobPolling";
import {
  DisclosureFilterCandidateCard,
  type DisclosureFilterCandidate,
} from "@/components/disclosures/DisclosureFilterCandidateCard";
import {
  DisclosureConditionFilterCard,
  makeEmptyDisclosureCondition,
  normalizeDisclosureConditionBlocks,
  type DisclosureConditionBlock,
  type DisclosureConditionPreset,
  type DisclosureConditionPresetPayload,
} from "@/components/disclosures/DisclosureConditionFilterCard";
import { WorkflowPathSettings } from "@/components/data-path/WorkflowPathSettings";
import {
  HtmlWorkflowForm,
  HtmlWorkflowPage,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import {
  DATA_PATH_LABELS,
  type DataPathField,
} from "@/components/data-path/DataPathCard";
import { SETTINGS_LABELS, UI_TEXT } from "@/config/uiText";
import { formatInteger } from "@/lib/format";
import { apiPost } from "@/api/client";
import { pickPath } from "@/lib/fileDialog";
import {
  deleteDisclosureConditionPreset,
  listDisclosureConditionPresets,
  saveDisclosureConditionPreset,
} from "@/lib/disclosureConditionPresets";
import {
  SingleCheckDataIntegrityInspectionCard,
  type SingleCheckDataIntegrityInspectionState,
} from "@/components/data-integrity/DataIntegrityInspectionCard";
import { useDataIntegrityInspection } from "@/hooks/useDataIntegrityInspection";

type ParseInspectionResult = {
  format: "finiq_disclosure_html_parse_inspection_v1";
  confirmed: boolean;
  reason: string;
  result_path: string;
  summary?: {
    found_files?: number;
    parsed_files?: number;
    failed_files?: number;
  };
};

type ParseExecutionOptionConfig = {
  field: string;
  statusLabel: string;
};

type ParseModeConfig = {
  key: string;
  label: string;
  status: string;
  description: string;
  executionOptions: ParseExecutionOptionConfig[];
};

const DISCLOSURE_PARSE_MODES: ParseModeConfig[] = [
  {
    key: "bond_issuance",
    label: "사채발행파싱",
    status: "상세 필드 지원",
    description: "메자닌 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
    executionOptions: [{ field: "사채발행방법", statusLabel: "사채발행방법" }],
  },
  {
    key: "rights_issuance",
    label: "유무상증자파싱",
    status: "상세 필드 지원",
    description: "유상증자 및 무상증자 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
    executionOptions: [{ field: "증자방식", statusLabel: "증자방식" }],
  },
  {
    key: "shareholder_meeting",
    label: "주주총회파싱",
    status: "원본 테이블 구조 지원",
    description: "주주총회 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
    executionOptions: [],
  },
  {
    key: "asset_transaction",
    label: "유무형자산거래파싱",
    status: "원본 테이블 구조 지원",
    description: "유형자산 및 무형자산 거래 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
    executionOptions: [],
  },
  {
    key: "security_transaction",
    label: "발행증권거래파싱",
    status: "원본 테이블 구조 지원",
    description: "발행증권 거래 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
    executionOptions: [],
  },
];

const HTML_PARSE_RELATED_ROUTES = "/internal-html-download /html-parse /html-change-log";
const PARSE_MODE_CONFIGS = Object.fromEntries(DISCLOSURE_PARSE_MODES.map((mode) => [mode.key, mode])) as Record<string, ParseModeConfig>;
const WARNING_OPEN_PAGE_SIZE = 20;
type FilterCandidate = DisclosureFilterCandidate & {
  examples: FilterCandidateExample[];
};

type FilterCandidateExample = {
  acpt_no: string;
};

type ExecutionOptionExampleNotice = {
  title: string;
  count: number;
  examples: FilterCandidateExample[];
};

type ParseWarningItem = {
  acpt_no: string;
  warning: string;
  level: string;
  warning_code: string;
};

type WarningLevel = "weak_warning" | "medium_warning" | "strong_warning";

type WarningDetail = {
  warning: string;
  warningCode: string;
};

type WarningReport = {
  acptNo: string;
  warningsByLevel: Record<WarningLevel, WarningDetail[]>;
};

const WARNING_LEVEL_LABELS: Record<WarningLevel, string> = {
  weak_warning: "약한 에러",
  medium_warning: "일반 에러",
  strong_warning: "강한 에러",
};

const WARNING_LEVELS: WarningLevel[] = ["weak_warning", "medium_warning", "strong_warning"];

const normalizeWarningLevel = (level: string): WarningLevel => {
  if (!WARNING_LEVELS.includes(level as WarningLevel)) {
    throw new Error(`Unknown parse warning level: ${level}`);
  }
  return level as WarningLevel;
};

const normalizeWarningCode = (code: string) => {
  const normalized = code.trim();
  if (!normalized) throw new Error("parse warning code is required");
  return normalized;
};

const buildWarningReports = (warnings: ParseWarningItem[]): WarningReport[] => {
  const reportMap = new Map<string, WarningReport>();

  warnings.forEach((item) => {
    const warning = item.warning.trim();
    const acptNo = item.acpt_no.trim();
    if (!warning || !acptNo) throw new Error("parse warning requires acpt_no and warning");

    const report = reportMap.get(acptNo) || {
      acptNo,
      warningsByLevel: {
        weak_warning: [],
        medium_warning: [],
        strong_warning: [],
      },
    };

    report.warningsByLevel[normalizeWarningLevel(item.level)].push({
      warning,
      warningCode: normalizeWarningCode(item.warning_code),
    });
    reportMap.set(acptNo, report);
  });

  return Array.from(reportMap.values());
};

const warningSourceUrl = (acptNo: string, inputDirectory: string) => {
  const params = new URLSearchParams({
    input_directory: inputDirectory,
    acpt_no: acptNo,
  });
  return `/api/disclosures/html/sections/source?${params.toString()}`;
};

const executionOptionExampleUrl = (example: FilterCandidateExample, inputDirectory: string) => {
  return warningSourceUrl(example.acpt_no, inputDirectory);
};

const normalizeFilterCandidateExamples = (
  examples: FilterCandidate["examples"],
): FilterCandidateExample[] => {
  if (!Array.isArray(examples)) throw new Error("filter candidate examples must be an array");
  return examples.map((example, index) => {
    if (!example || typeof example !== "object") {
      throw new Error(`filter candidate examples[${index}] must be an object`);
    }
    if (typeof example.acpt_no !== "string") {
      throw new Error(`filter candidate examples[${index}].acpt_no must be a string`);
    }
    const acptNo = example.acpt_no.trim();
    if (!acptNo) throw new Error(`filter candidate examples[${index}].acpt_no is required`);
    return { acpt_no: acptNo };
  });
};

export default function HtmlParsePage() {
  const {
    output_root: dataRoot,
    disclosure_separate_output_directory: useSeparateOutputDirectory,
    fetchSettings,
    parallel_worker_count: defaultParallelWorkers,
    saveSetting,
  } = useSettingsStore();
  const activeParseInspectionRef = useRef<{ jobId: string; key: string } | null>(null);
  const currentParseInspectionKeyRef = useRef("");

  const [loading, setLoading] = useState(true);
  const [latestParseResult, setLatestParseResult] = useState<any>(null);
  const [warningOpenPages, setWarningOpenPages] = useState<Record<string, number>>({});
  const {
    result: inspectionResult,
    error: inspectionError,
    isChecking: inspectionRunning,
    runInspection,
    acceptResult: acceptInspectionResult,
    clear: clearInspection,
  } = useDataIntegrityInspection<Record<string, unknown>, ParseInspectionResult>({
    inspect: (payload) => apiPost<ParseInspectionResult>("/api/disclosures/html/parse/inspect", payload),
    onError: (message) => {
      setStatus(message);
      setIsErrorStatus(true);
    },
  });

  const formatStatus = useCallback((data: any) => {
    const statusLbl = (s: string) => {
      if (s === "queued") return "대기 중";
      if (s === "running") return "실행 중";
      if (s === "completed") return "완료";
      if (s === "failed") return "실패";
      return s || "-";
    };

    const res = data.result || {};
    const summary = res.summary || {};
    const warningCount = Array.isArray(res.warnings) ? res.warnings.length : 0;
    const lines = [`작업 상태: ${statusLbl(data.status)}`];
    if (data.error) lines.push(`오류: ${data.error}`);

    if (summary.found_files !== undefined) {
      lines.push(`대상 HTML: ${formatInteger(summary.found_files)}`);
      lines.push(`파싱 성공: ${formatInteger(summary.parsed_files)}`);
      lines.push(`파싱 경고: ${formatInteger(warningCount)}`);
      lines.push(`파싱 실패: ${formatInteger(summary.failed_files)}`);
    }

    if (Array.isArray(data.progress_log) && data.progress_log.length) {
      lines.push("", "최근 로그", ...data.progress_log);
    }
    return lines;
  }, []);

  const {
    status,
    isErrorStatus,
    activeJobId,
    startPolling,
    setStatus,
    setIsErrorStatus,
  } = useJobPolling({
    pollingEndpoint: "/api/disclosures/html/jobs/{jobId}",
    formatStatus,
    onSuccess: (result, jobId) => {
      setLatestParseResult(result);
      const context = activeParseInspectionRef.current;
      if (!context || context.jobId !== jobId) return;
      activeParseInspectionRef.current = null;
      if (context.key !== currentParseInspectionKeyRef.current) return;
      const failedFiles = Number(result?.summary?.failed_files || 0);
      acceptInspectionResult({
        format: "finiq_disclosure_html_parse_inspection_v1",
        confirmed: result?.cancelled !== true && failedFiles === 0,
        reason: result?.cancelled === true
          ? "변환 작업이 취소되었습니다."
          : failedFiles > 0
            ? `변환에 실패한 파일이 ${failedFiles}개 있습니다.`
            : "변환 과정에서 현재 설정으로 입력 HTML을 처리한 내용과 저장된 결과를 확인했습니다.",
        result_path: "",
        summary: result?.summary,
      });
    },
    onError: (_error, jobId) => {
      if (activeParseInspectionRef.current?.jobId === jobId) {
        activeParseInspectionRef.current = null;
      }
    },
    onCancel: (jobId) => {
      if (activeParseInspectionRef.current?.jobId === jobId) {
        activeParseInspectionRef.current = null;
      }
    },
  });

  const isJobActive = !!activeJobId;

  const [activeCancelToken, setActiveCancelToken] = useState<string | null>(null);

  // Form State
  const [inputDirectory, setInputDirectory] = useState("");
  const [outputDirectory, setOutputDirectory] = useState("");
  const [parseMode, setParseMode] = useState("bond_issuance");
  const [limit, setLimit] = useState("");
  const [skipErrors, setSkipErrors] = useState(true);
  const [progressInterval, setProgressInterval] = useState("1000");
  const [parallelWorkers, setParallelWorkers] = useState("");
  const [selectedExecutionOptionValues, setSelectedExecutionOptionValues] = useState<string[]>([]);
  const [executionOptionCandidates, setExecutionOptionCandidates] = useState<FilterCandidate[]>([]);
  const [executionOptionInputDirectory, setExecutionOptionInputDirectory] = useState("");
  const [executionOptionExampleNotice, setExecutionOptionExampleNotice] = useState<ExecutionOptionExampleNotice | null>(null);
  const [notificationResetKey, setNotificationResetKey] = useState(0);
  const [filterCandidatesLoading, setFilterCandidatesLoading] = useState(false);
  const filterCandidatesRequestIdRef = useRef(0);
  const [conditions, setConditions] = useState<DisclosureConditionBlock[]>([makeEmptyDisclosureCondition()]);
  const [selectedPreset, setSelectedPreset] = useState("");
  const [presets, setPresets] = useState<DisclosureConditionPreset[]>([]);
  const [filterPresetPath, setFilterPresetPath] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);
  const selectedParseMode = PARSE_MODE_CONFIGS[parseMode] || DISCLOSURE_PARSE_MODES[0];
  const executionOptionConfig = selectedParseMode.executionOptions[0] || null;
  const activeRecordFilters = executionOptionConfig && selectedExecutionOptionValues.length ? [
    {
      field: executionOptionConfig.field,
      operator: "in",
      value: selectedExecutionOptionValues,
    },
  ] : [];

  const startJob = useCallback(async (endpoint: string, payload: any, inspectionKey?: string) => {
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("Job start failed");
      const data = await response.json();
      if (inspectionKey) {
        activeParseInspectionRef.current = { jobId: data.job_id, key: inspectionKey };
      }
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
      if (payload.cancel_token) {
         setActiveCancelToken(null);
      }
    }
  }, [setStatus, setIsErrorStatus, startPolling, setActiveCancelToken]);

  useEffect(() => {
    fetchSettings().then((config) => {
      setInputDirectory(config.html_section_split_output_directory || "");
      setOutputDirectory(config.html_parse_output_directory || "");

      if (config.html_parse_mode) {
        setParseMode(config.html_parse_mode);
      }

      const configuredParallelWorkers = Number(config.parallel_worker_count);
      if (!Number.isInteger(configuredParallelWorkers) || configuredParallelWorkers < 1) {
        throw new Error("parallel_worker_count must be a positive integer");
      }
      setParallelWorkers(String(configuredParallelWorkers));
    }).catch(err => {
      setStatus(err.message);
      setIsErrorStatus(true);
    }).finally(() => {
      setLoading(false);
    });
  }, [fetchSettings, setStatus, setIsErrorStatus]);

  const handlePathError = useCallback((message: string) => {
    setStatus(message);
    setIsErrorStatus(true);
  }, [setIsErrorStatus, setStatus]);

  useEffect(() => {
    if (!dataRoot?.trim()) {
      setPresets([]);
      return;
    }
    listDisclosureConditionPresets(dataRoot).then((response) => {
      setPresets(response.presets);
    }).catch((error) => {
      setPresets([]);
      setStatus(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    });
  }, [dataRoot, setIsErrorStatus, setStatus]);

  useEffect(() => {
    clearInspection();
  }, [
    clearInspection,
    conditions,
    dataRoot,
    inputDirectory,
    limit,
    outputDirectory,
    parallelWorkers,
    parseMode,
    progressInterval,
    selectedExecutionOptionValues,
    skipErrors,
    useSeparateOutputDirectory,
  ]);

  const handleWorkspaceDirectoryChange = async (val: string) => {
    filterCandidatesRequestIdRef.current += 1;
    setFilterCandidatesLoading(false);
    if (await saveSetting("output_root", val)) {
      const settings = useSettingsStore.getState();
      setInputDirectory(settings.html_section_split_output_directory || "");
      setOutputDirectory(settings.html_parse_output_directory || "");
    }
    setSelectedExecutionOptionValues([]);
    setExecutionOptionCandidates([]);
    setExecutionOptionInputDirectory("");
    setExecutionOptionExampleNotice(null);
  };

  const handleOutputDirectoryChange = (val: string) => {
    setOutputDirectory(val);
    saveSetting("html_parse_output_directory", val);
  };

  const handleParseModeChange = (val: string) => {
    filterCandidatesRequestIdRef.current += 1;
    setFilterCandidatesLoading(false);
    setParseMode(val);
    setSelectedExecutionOptionValues([]);
    setExecutionOptionCandidates([]);
    setExecutionOptionInputDirectory("");
    setExecutionOptionExampleNotice(null);
    void saveSetting("html_parse_mode", val).then(() => {
      const settings = useSettingsStore.getState();
      setParseMode(settings.html_parse_mode || "");
      setOutputDirectory(settings.html_parse_output_directory || "");
    });
  };

  const applyPreset = useCallback((preset: DisclosureConditionPresetPayload, statusMessage: string) => {
    setConditions(normalizeDisclosureConditionBlocks(preset.condition_blocks));
    if (preset.mode && PARSE_MODE_CONFIGS[preset.mode]) {
      setParseMode(preset.mode);
      void saveSetting("html_parse_mode", preset.mode);
    }
    setStatus(statusMessage);
    setIsErrorStatus(false);
  }, [saveSetting, setIsErrorStatus, setStatus]);

  const savePreset = async () => {
    if (!dataRoot?.trim()) {
      setStatus("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      const filterMode = selectedPreset.trim() || parseMode;
      const response = await saveDisclosureConditionPreset(dataRoot, {
        mode: filterMode,
        condition_blocks: normalizeDisclosureConditionBlocks(conditions),
      });
      setPresets(response.presets);
      setSelectedPreset(filterMode);
      setStatus(`조건검색 필터를 저장했습니다: ${filterMode}`);
      setIsErrorStatus(false);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    }
  };

  const loadPreset = (name: string) => {
    const preset = (presets || []).find((item: any) => item.name === name);
    if (!preset) {
      setStatus("선택한 프리셋을 찾을 수 없습니다.");
      setIsErrorStatus(true);
      return;
    }
    applyPreset(preset, `조건검색 필터를 불러왔습니다: ${preset.name}`);
  };

  const loadFilterPresetFromJson = async () => {
    try {
      const sourceJsonPath = await pickPath({
        mode: "file",
        title: "필터 JSON 선택",
        defaultPath: filterPresetPath,
      });
      if (!sourceJsonPath) return;
      setFilterPresetPath(sourceJsonPath);
      const preset = await apiPost<DisclosureConditionPresetPayload>("/api/disclosures/filter/preset", {
        source_json_path: sourceJsonPath,
      });
      setSelectedPreset("");
      applyPreset(preset, `필터 JSON에서 조건을 불러왔습니다: ${preset.source_json_path || sourceJsonPath}`);
    } catch (err: any) {
      setStatus(err.message || "필터 JSON을 불러오지 못했습니다.");
      setIsErrorStatus(true);
    }
  };

  const deletePreset = async () => {
    if (!selectedPreset) return;
    if (!dataRoot?.trim()) {
      setStatus("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      const response = await deleteDisclosureConditionPreset(dataRoot, selectedPreset);
      setPresets(response.presets);
      setSelectedPreset("");
      setStatus(`조건검색 필터를 삭제했습니다: ${selectedPreset}`);
      setIsErrorStatus(false);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    }
  };

  useEffect(() => {
    if (!isJobActive) {
      setActiveCancelToken(null);
    }
  }, [isJobActive]);

  const buildParseInspectionPayload = () => ({
    data_root: dataRoot,
    input_directory: useSeparateOutputDirectory ? inputDirectory : "",
    output_directory: useSeparateOutputDirectory ? outputDirectory : "",
    mode: parseMode,
    limit: limit ? Number(limit) : null,
    skip_errors: skipErrors,
    progress_interval: Number(progressInterval),
    parallel_workers: parallelWorkers ? Number(parallelWorkers) : null,
    filter_blocks: normalizeDisclosureConditionBlocks(conditions),
    record_filters: activeRecordFilters,
  });
  const currentParseInspectionKey = JSON.stringify({
    dataRoot,
    inputDirectory,
    outputDirectory,
    useSeparateOutputDirectory,
    parseMode,
    limit,
    skipErrors,
    progressInterval,
    parallelWorkers,
    conditions,
    activeRecordFilters,
  });
  currentParseInspectionKeyRef.current = currentParseInspectionKey;

  const handleRun = async () => {
    if (!dataRoot) {
      setStatus("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (useSeparateOutputDirectory && !outputDirectory) {
      setStatus(`${DATA_PATH_LABELS.workspace}를 선택하세요.`);
      setIsErrorStatus(true);
      return;
    }
    const cancelToken = window.crypto.randomUUID();
    setActiveCancelToken(cancelToken);
    setLatestParseResult(null);
    setWarningOpenPages({});

    const inspectionPayload = buildParseInspectionPayload();
    const payload = {
      ...inspectionPayload,
      cancel_token: cancelToken,
    };

    startJob(
      "/api/disclosures/html/parse/start",
      payload,
      currentParseInspectionKey,
    );
  };

  const handleCancel = async () => {
    if (!activeCancelToken) return;
    setStatus("공시원문 변환 중지를 요청했습니다. 현재 파일 처리가 끝나면 멈춥니다.");
    try {
      await fetch("/api/disclosures/html/parse/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cancel_token: activeCancelToken }),
      });
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleOpenWarningFiles = (groupKey: string) => {
    const pageInfo = warningPageInfoByGroup[groupKey];
    if (!pageInfo) return;
    pageInfo.acptNumbers.forEach((acptNo) => {
      window.open(warningSourceUrl(acptNo, inputDirectory), "_blank", "noopener,noreferrer");
    });
    setStatus(`${WARNING_LEVEL_LABELS[pageInfo.level]} ${pageInfo.warningCode} 파일 ${formatInteger(pageInfo.startIndex + 1)}-${formatInteger(pageInfo.endIndex)}번 열기를 요청했습니다.`);
    setIsErrorStatus(false);
  };

  const handleToggleExecutionOptionValue = (value: string, checked: boolean) => {
    setSelectedExecutionOptionValues((current) => {
      if (checked) return current.includes(value) ? current : [...current, value];
      return current.filter((item) => item !== value);
    });
  };

  const handleShowExecutionOptionExamples = (candidate: FilterCandidate) => {
    const examples = normalizeFilterCandidateExamples(candidate.examples);
    const title = `${executionOptionConfig?.field || "실행 옵션"}: ${candidate.value}`;
    setExecutionOptionExampleNotice({
      title,
      count: candidate.count,
      examples,
    });
    setNotificationResetKey((current) => current + 1);
    setIsErrorStatus(false);
  };

  const handleLoadExecutionOptionCandidates = async () => {
    if (!executionOptionConfig) return;
    if (!inputDirectory) {
      setStatus(`${DATA_PATH_LABELS.workspace}를 선택하세요.`);
      setIsErrorStatus(true);
      return;
    }
    const requestId = filterCandidatesRequestIdRef.current + 1;
    filterCandidatesRequestIdRef.current = requestId;
    setFilterCandidatesLoading(true);
    setIsErrorStatus(false);
    try {
      const response = await fetch("/api/disclosures/html/parse/filter-candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data_root: dataRoot,
          input_directory: inputDirectory,
          mode: parseMode,
          field: executionOptionConfig.field,
          parallel_workers: parallelWorkers ? Number(parallelWorkers) : null,
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        let message = text;
        try {
          const detail = JSON.parse(text);
          message = detail.detail || detail.message || text;
        } catch {
          message = text;
        }
        throw new Error(message || "필터 후보를 불러오지 못했습니다.");
      }
      const data = await response.json();
      if (filterCandidatesRequestIdRef.current !== requestId) return;
      setExecutionOptionCandidates(Array.isArray(data.candidates) ? data.candidates : []);
      setExecutionOptionInputDirectory(String(data.input_directory || ""));
      setExecutionOptionExampleNotice(null);
      setStatus(`${executionOptionConfig.statusLabel} 후보 ${formatInteger(data.summary?.candidates || 0)}개를 불러왔습니다.`);
    } catch (err: any) {
      if (filterCandidatesRequestIdRef.current !== requestId) return;
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      if (filterCandidatesRequestIdRef.current === requestId) {
        setFilterCandidatesLoading(false);
      }
    }
  };

  const handleLoadPreview = async () => {
    if (!inputDirectory) {
      setStatus(`${DATA_PATH_LABELS.workspace}를 선택하세요.`);
      setIsErrorStatus(true);
      return;
    }

    setPreviewLoading(true);
    setPreviewData(null);
    setIsErrorStatus(false);
    try {
      const response = await fetch("/api/disclosures/html/parse/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data_root: dataRoot,
          input_directory: inputDirectory,
          mode: parseMode,
          limit: 3,
          filter_blocks: normalizeDisclosureConditionBlocks(conditions),
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        let message = text;
        try {
          const detail = JSON.parse(text);
          message = detail.detail || detail.message || text;
        } catch {
          message = text;
        }
        throw new Error(message || "리포트 미리보기를 불러오지 못했습니다.");
      }
      const data = await response.json();
      setPreviewData(data);
      setStatus(`리포트 미리보기 ${formatInteger(data.summary?.visible_records || 0)}건을 불러왔습니다.`);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleInspectExistingParse = async () => {
    if (!dataRoot || !inputDirectory) {
      setStatus(`${DATA_PATH_LABELS.workspace}를 선택하세요.`);
      setIsErrorStatus(true);
      return;
    }
    if (useSeparateOutputDirectory && !outputDirectory) {
      setStatus(`${DATA_PATH_LABELS.workspace}를 선택하세요.`);
      setIsErrorStatus(true);
      return;
    }
    const payload = buildParseInspectionPayload();
    setStatus("기존 변환 데이터 검사를 시작합니다...");
    setIsErrorStatus(false);
    const result = await runInspection(payload, JSON.stringify(payload));
    if (!result) return;
    setStatus(result.confirmed ? "정상" : result.reason);
    setIsErrorStatus(!result.confirmed);
  };

  const parsePathFields: DataPathField[] = [
    {
      id: "inputDirectory",
      label: DATA_PATH_LABELS.workspace,
      value: dataRoot,
      onChange: handleWorkspaceDirectoryChange,
    },
    {
      id: "outputDirectory",
      label: DATA_PATH_LABELS.output,
      value: outputDirectory,
      onChange: handleOutputDirectoryChange,
      separateOutputOnly: true,
    },
  ];

  const parseOptionFields: HtmlWorkflowField[] = [
    {
      id: "limit",
      kind: "input",
      type: "number",
      label: SETTINGS_LABELS.maxItems,
      placeholder: "전체",
      value: limit,
      onChange: setLimit,
      span: 2,
    },
    {
      id: "progressInterval",
      kind: "input",
      type: "number",
      label: SETTINGS_LABELS.progressInterval,
      value: progressInterval,
      onChange: setProgressInterval,
      span: 2,
    },
    {
      id: "parallelWorkers",
      kind: "input",
      type: "number",
      label: SETTINGS_LABELS.workerCount,
      placeholder: String(defaultParallelWorkers),
      value: parallelWorkers,
      onChange: setParallelWorkers,
      span: 2,
    },
    {
      id: "skipErrors",
      kind: "checkbox",
      checked: skipErrors,
      onChange: setSkipErrors,
      checkboxLabel: "실패 파일 건너뛰기",
      span: 2,
    },
  ];
  const warningReports = buildWarningReports(Array.isArray(latestParseResult?.warnings) ? latestParseResult.warnings : []);
  const warningGroups = WARNING_LEVELS.flatMap((level) => {
    const groupMap = new Map<string, { key: string; level: WarningLevel; warningCode: string; warningCount: number; acptNumbers: string[] }>();
    warningReports.forEach((report) => {
      const codes = new Set<string>();
      report.warningsByLevel[level].forEach((detail) => {
        const warningCode = normalizeWarningCode(detail.warningCode);
        const key = `${level}:${warningCode}`;
        const group = groupMap.get(key) || {
          key,
          level,
          warningCode,
          warningCount: 0,
          acptNumbers: [],
        };
        group.warningCount += 1;
        if (!codes.has(warningCode)) {
          group.acptNumbers.push(report.acptNo);
          codes.add(warningCode);
        }
        groupMap.set(key, group);
      });
    });
    return Array.from(groupMap.values());
  });
  const warningPageInfoByGroup = warningGroups.reduce((infoByGroup, group) => {
    const acptNumbers = Array.from(new Set(group.acptNumbers));
    const pageCount = Math.max(1, Math.ceil(acptNumbers.length / WARNING_OPEN_PAGE_SIZE));
    const safePage = Math.min(warningOpenPages[group.key] || 0, pageCount - 1);
    const startIndex = safePage * WARNING_OPEN_PAGE_SIZE;
    const pageAcptNumbers = acptNumbers.slice(startIndex, startIndex + WARNING_OPEN_PAGE_SIZE);
    infoByGroup[group.key] = {
      level: group.level,
      warningCode: group.warningCode,
      pageCount,
      safePage,
      startIndex,
      endIndex: startIndex + pageAcptNumbers.length,
      acptNumbers: pageAcptNumbers,
      totalAcptNumbers: acptNumbers.length,
    };
    return infoByGroup;
  }, {} as Record<string, {
    level: WarningLevel;
    warningCode: string;
    pageCount: number;
    safePage: number;
    startIndex: number;
    endIndex: number;
    acptNumbers: string[];
    totalAcptNumbers: number;
  }>);
  const warningCount = warningReports.reduce(
    (total, report) => total + WARNING_LEVELS.reduce((levelTotal, level) => levelTotal + report.warningsByLevel[level].length, 0),
    0,
  );
  const parsedValueTableClassName = "w-full table-auto border-collapse text-left text-[11px] leading-5";
  const parsedValueCellClassName = "border-b border-slate-100 px-3 py-2 align-top text-left font-normal text-slate-700 dark:border-[#30363d] dark:text-slate-300";
  const parsedValueHeaderClassName = "w-44 border-b border-slate-200 bg-slate-50 px-3 py-2 align-top text-left text-[11px] font-semibold leading-5 text-slate-600 dark:border-[#30363d] dark:bg-[#161b22] dark:text-slate-300";
  const parsedValueIndexClassName = "w-12 border-b border-slate-200 bg-slate-50 px-3 py-2 align-top text-center text-[11px] font-semibold leading-5 text-slate-500 dark:border-[#30363d] dark:bg-[#161b22] dark:text-slate-400";

  const renderParsedValue = (value: any): any => {
    if (value === null || value === undefined || value === "") {
      return <span className="text-slate-400 dark:text-slate-500">-</span>;
    }
    if (typeof value !== "object") {
      return <span>{String(value)}</span>;
    }
    if (Array.isArray(value)) {
      if (value.length === 0) {
        return <span className="text-slate-400 dark:text-slate-500">-</span>;
      }
      if (value.every((item) => Array.isArray(item))) {
        return (
          <table className={parsedValueTableClassName}>
            <tbody>
              {value.map((row: any[], rowIndex: number) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex} className={parsedValueCellClassName}>{renderParsedValue(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        );
      }
      if (value.every((item) => item && typeof item === "object" && !Array.isArray(item))) {
        const columns = Array.from(new Set(value.flatMap((item) => Object.keys(item))));
        return (
          <table className={parsedValueTableClassName}>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column} className={parsedValueHeaderClassName}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {value.map((item, rowIndex) => (
                <tr key={rowIndex}>
                  {columns.map((column) => (
                    <td key={column} className={parsedValueCellClassName}>{renderParsedValue(item[column])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        );
      }
      return (
        <table className={parsedValueTableClassName}>
          <tbody>
            {value.map((item, index) => (
              <tr key={index}>
                <th className={parsedValueIndexClassName}>{index + 1}</th>
                <td className={parsedValueCellClassName}>{renderParsedValue(item)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      );
    }
    return (
      <table className={parsedValueTableClassName}>
        <tbody>
          {Object.entries(value).map(([key, nestedValue]) => (
            <tr key={key}>
              <th className={parsedValueHeaderClassName}>{key}</th>
              <td className={parsedValueCellClassName}>{renderParsedValue(nestedValue)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  useEffect(() => {
    setWarningOpenPages((current) => {
      let changed = false;
      const next = { ...current };
      const activeKeys = new Set(warningGroups.map((group) => group.key));
      Object.keys(next).forEach((key) => {
        if (!activeKeys.has(key)) {
          delete next[key];
          changed = true;
        }
      });
      warningGroups.forEach((group) => {
        const pageCount = Math.max(1, Math.ceil(group.acptNumbers.length / WARNING_OPEN_PAGE_SIZE));
        const safePage = Math.min(current[group.key] || 0, pageCount - 1);
        if (current[group.key] !== safePage) {
          next[group.key] = safePage;
          changed = true;
        }
      });
      return changed ? next : current;
    });
  }, [
    warningGroups.map((group) => `${group.key}:${group.acptNumbers.length}`).join("|"),
  ]);

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  const hasInspectionInput = !!dataRoot
    && !!inputDirectory
    && (!useSeparateOutputDirectory || !!outputDirectory);
  const inspectionState: SingleCheckDataIntegrityInspectionState = !hasInspectionInput
    ? "waiting"
    : inspectionRunning
      ? "running"
      : inspectionError || inspectionResult?.confirmed === false
        ? "failed"
        : inspectionResult?.confirmed
          ? "success"
          : "ready";
  const inspectionCopy = {
    waiting: ["입력 경로와 결과 경로를 선택하세요", "경로를 선택한 다음 현재 설정으로 변환 결과를 다시 계산해 저장된 결과와 비교하세요."],
    ready: ["기존 변환 결과 검사가 필요합니다", "현재 설정과 입력 HTML을 기준으로 저장된 결과를 확인하세요."],
    running: ["기존 변환 결과를 다시 계산하고 있습니다", "현재 설정으로 입력 HTML을 다시 변환해 저장된 결과와 비교합니다."],
    success: ["기존 변환 결과를 그대로 사용해도 됩니다", inspectionResult?.reason || "정상"],
    failed: ["기존 변환 결과에 문제가 있습니다", inspectionError || inspectionResult?.reason || "검사 결과를 확인하세요."],
  }[inspectionState];
  const inspectionSummary = inspectionResult?.summary;
  const inspectionStepSummary = inspectionSummary
    ? `대상 ${formatInteger(inspectionSummary.found_files)}개 중 ${formatInteger(inspectionSummary.parsed_files)}개를 변환했고 ${formatInteger(inspectionSummary.failed_files)}개는 실패했습니다.`
    : inspectionResult?.reason || "현재 설정으로 다시 계산한 결과와 저장된 결과 전체를 비교합니다.";

  return (
    <HtmlWorkflowPage
      eyebrow="HTML Parse Guide"
      title="공시원문 변환"
      description="저장된 KIND HTML을 모드별 파서로 읽어 핵심 필드, 오류, 경고를 하나의 JSON에 남깁니다. 결과 파일은 공시 정정내역 한눈에, 발행내역 한눈에, Excel 내보내기의 기준 데이터가 됩니다."
    >
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          <SingleCheckDataIntegrityInspectionCard
            description="실행 전에 현재 설정으로 입력 HTML을 다시 변환해 저장된 결과와 비교합니다."
            state={inspectionState}
            verdictTitle={inspectionCopy[0]}
            verdictDescription={inspectionCopy[1]}
            stepTitle="입력 HTML 변환 결과 검사"
            stepSummary={inspectionStepSummary}
            action={hasInspectionInput ? {
              label: inspectionRunning ? "검사 중..." : "검사하기",
              onClick: handleInspectExistingParse,
              disabled: inspectionRunning || isJobActive,
              loading: inspectionRunning,
              showResultStatus: true,
            } : undefined}
          />

          {/* LEGACY: 본문 데이터 경로 카드. 경로 입력은 우측 설정 패널(WorkflowPathSettings)로 옮겼다.
              <DataPathCard onError={handlePathError} fields={parsePathFields} /> */}

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]" data-related-routes={HTML_PARSE_RELATED_ROUTES}>
            <CardHeader className="gap-3 pb-4">
              <div className="min-w-0 space-y-1">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Parsing Modes</p>
                <CardTitle className="dark:text-white">모드별 기능</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3">
                {DISCLOSURE_PARSE_MODES.map(mode => (
                  <div
                    key={mode.key}
                    onClick={() => handleParseModeChange(mode.key)}
                    className={cn(
                      "rounded-md border px-4 py-3 transition-shadow cursor-pointer",
                      parseMode === mode.key
                        ? "bg-slate-900 text-white border-slate-900 dark:bg-slate-100 dark:text-slate-900 dark:border-slate-100 shadow-sm"
                        : "bg-white text-slate-600 border-slate-200 dark:bg-[#0d1117] dark:text-slate-300 dark:border-[#30363d]"
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <strong className="text-sm font-semibold">{mode.label}</strong>
                          <code className={cn(
                            "text-[10px] font-mono opacity-60",
                            parseMode === mode.key ? "text-white/75 dark:text-black/60" : "text-slate-400"
                          )}>{mode.key}</code>
                        </div>
                        <p className="mt-2 text-xs leading-6 opacity-85">{mode.description}</p>
                      </div>
                      <span className={cn(
                        "shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium",
                        parseMode === mode.key ? "bg-white/20 text-white dark:bg-black/10 dark:text-black" : "bg-slate-100 text-slate-500 dark:bg-[#21262d] dark:text-slate-400"
                      )}>{mode.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {executionOptionConfig ? (
            <DisclosureFilterCandidateCard
              title="실행 옵션"
              fieldLabel={executionOptionConfig.field}
              candidates={executionOptionCandidates}
              selectedValues={selectedExecutionOptionValues}
              loading={filterCandidatesLoading}
              onLoadCandidates={handleLoadExecutionOptionCandidates}
              onToggleValue={handleToggleExecutionOptionValue}
              onShowExamples={handleShowExecutionOptionExamples}
            />
          ) : null}

          <DisclosureConditionFilterCard
            conditions={conditions}
            onConditionsChange={setConditions}
            presets={presets || []}
            selectedPreset={selectedPreset}
            onSelectedPresetChange={setSelectedPreset}
            onLoadPreset={loadPreset}
            onLoadPresetFromJson={loadFilterPresetFromJson}
            onSavePreset={savePreset}
            onDeletePreset={deletePreset}
          />

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader className="flex flex-col gap-3 pb-4 md:flex-row md:items-start md:justify-between md:space-y-0">
              <div className="min-w-0 space-y-1">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Report Preview</p>
                <CardTitle className="dark:text-white">리포트 미리보기</CardTitle>
              </div>
              <Button variant="outline" onClick={handleLoadPreview} disabled={previewLoading} className="h-10 shrink-0 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200">
                {previewLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Eye className="mr-2 h-4 w-4" />}
                미리보기 불러오기
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {previewData?.records?.length ? (
                previewData.records.map((record: any) => (
                  <div key={`${record.index}-${record.acpt_no}`} className="rounded-md border border-slate-200 bg-white px-4 py-3 dark:border-[#30363d] dark:bg-[#0d1117]">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{record.title || record.acpt_no || `리포트 ${record.index}`}</p>
                      </div>
                      <code className="rounded bg-slate-100 px-2 py-1 text-[10px] text-slate-500 dark:bg-[#161b22] dark:text-slate-400">
                        {record.acpt_no || `#${record.index}`}
                      </code>
                    </div>

                    <div className="mt-3 min-w-0 rounded-md border border-slate-200 dark:border-[#30363d]">
                      <div className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">
                        <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">파싱 결과</p>
                      </div>
                      <div className="max-h-[34rem] overflow-auto p-3">
                        {renderParsedValue(record.parsed_result)}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-md border border-dashed border-slate-300 p-4 text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
                  미리보기를 불러오면 경로 내 리포트의 파싱 결과가 표시됩니다.
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <Button className="h-10 w-full" onClick={handleRun} disabled={isJobActive}>
                  {isJobActive ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                <Button variant="outline" className="h-10 w-full" onClick={handleCancel} disabled={!activeCancelToken}>
                  <Square className="mr-2 h-4 w-4" />
                  {UI_TEXT.actions.cancelJob}
                </Button>
              </div>
            </CardContent>
          </Card>
        </section>

        <ActionDock
          activityActive={isJobActive}
          activityContent={
            <JobStatusLogger
              status={status}
              isErrorStatus={isErrorStatus}
              isCancellable={!!activeCancelToken}
              onCancel={handleCancel}
            />
          }
          notificationActive={isErrorStatus || !!executionOptionExampleNotice || warningReports.length > 0}
          notificationTone={isErrorStatus ? "error" : warningReports.length > 0 ? "warning" : "neutral"}
          notificationResetKey={notificationResetKey}
          notificationContent={
            <div className="space-y-3">
              {isErrorStatus ? (
                <div className="whitespace-pre-wrap text-sm text-[var(--tv-down-text)]">{status || "오류 내용을 확인할 수 없습니다."}</div>
              ) : executionOptionExampleNotice ? (
                <div className="space-y-3">
                  <div className="rounded-md border border-slate-200 bg-white px-3 py-2 dark:border-[#30363d] dark:bg-[#0d1117]">
                    <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{executionOptionExampleNotice.title}</p>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      {formatInteger(executionOptionExampleNotice.count)}건 중 예시 {formatInteger(executionOptionExampleNotice.examples.length)}건
                    </p>
                  </div>
                  {executionOptionExampleNotice.examples.length ? (
                    <div className="max-h-[60vh] space-y-2 overflow-auto pr-1">
                      {executionOptionExampleNotice.examples.map((example, exampleIndex) => (
                        <div key={`${example.acpt_no}-${exampleIndex}`} className="flex items-center justify-between gap-3 rounded-md border border-slate-200 bg-white px-3 py-2 dark:border-[#30363d] dark:bg-[#0d1117]">
                          <div className="min-w-0">
                            <p className="break-all text-sm font-semibold text-slate-900 dark:text-slate-100">{example.acpt_no}</p>
                            <p className="mt-1 break-all text-[11px] text-slate-500 dark:text-slate-400">{example.acpt_no}.html</p>
                          </div>
                          <Button type="button" variant="outline" size="sm" className="h-8 shrink-0 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200" onClick={() => window.open(executionOptionExampleUrl(example, executionOptionInputDirectory), "_blank", "noopener,noreferrer")}>
                            <ExternalLink className="mr-1 h-3.5 w-3.5" />
                            열기
                          </Button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-md border border-dashed border-slate-300 px-3 py-2 text-sm text-slate-500 dark:border-[#30363d] dark:text-slate-400">
                      표시할 예시 파일이 없습니다.
                    </div>
                  )}
                </div>
              ) : warningReports.length ? (
                <div className="space-y-3">
                  <div className="rounded-md border border-[color:var(--tv-warning)] bg-[var(--tv-warning-soft)] px-3 py-2 text-sm text-[var(--tv-warning-text)]">
                    경고 리포트 {formatInteger(warningReports.length)}건, 경고 {formatInteger(warningCount)}건
                  </div>
                  <div className="space-y-2">
                    {warningGroups.map((group) => {
                      const pageInfo = warningPageInfoByGroup[group.key];
                      return (
                        <div key={group.key} className="rounded-md border border-slate-200 bg-white px-3 py-2 dark:border-[#30363d] dark:bg-[#0d1117]">
                          <div className="flex items-center justify-between gap-3 text-xs">
                            <span className="font-semibold text-slate-700 dark:text-slate-200">
                              {WARNING_LEVEL_LABELS[group.level]} {formatInteger(group.warningCount)}건
                            </span>
                            <span className="text-slate-500 dark:text-slate-400">
                              {pageInfo.totalAcptNumbers ? `${formatInteger(pageInfo.startIndex + 1)}-${formatInteger(pageInfo.endIndex)} / ${formatInteger(pageInfo.totalAcptNumbers)}` : "0 / 0"}
                            </span>
                          </div>
                          <div className="mt-1 break-all text-[11px] text-slate-500 dark:text-slate-400">
                            오류코드 {group.warningCode}
                          </div>
                          <Button type="button" variant="outline" className="mt-2 h-9 w-full justify-center dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200" onClick={() => handleOpenWarningFiles(group.key)} disabled={!pageInfo.acptNumbers.length}>
                            <ExternalLink className="mr-2 h-4 w-4" />
                            현재 페이지 열기
                          </Button>
                          <div className="mt-2 flex items-center justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
                            <Button type="button" variant="outline" size="sm" className="h-8 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200" onClick={() => setWarningOpenPages((pages) => ({ ...pages, [group.key]: Math.max(0, (pages[group.key] || 0) - 1) }))} disabled={pageInfo.safePage === 0}>
                              이전
                            </Button>
                            <span className="text-center">
                              {formatInteger(pageInfo.safePage + 1)} / {formatInteger(pageInfo.pageCount)}
                            </span>
                            <Button type="button" variant="outline" size="sm" className="h-8 dark:border-[#30363d] dark:hover:bg-[#21262d] dark:text-slate-200" onClick={() => setWarningOpenPages((pages) => ({ ...pages, [group.key]: Math.min(pageInfo.pageCount - 1, (pages[group.key] || 0) + 1) }))} disabled={pageInfo.safePage >= pageInfo.pageCount - 1}>
                              다음
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <div className="max-h-[60vh] space-y-3 overflow-auto pr-1">
                    {warningReports.map((report, reportIndex) => (
                      <div key={`${report.acptNo}-${reportIndex}`} className="rounded-md border border-slate-200 bg-white px-3 py-2 dark:border-[#30363d] dark:bg-[#0d1117]">
                        <div className="min-w-0">
                          <p className="break-all text-sm font-semibold text-slate-900 dark:text-slate-100">{report.acptNo}</p>
                        </div>
                        <div className="mt-2 space-y-2">
                          {WARNING_LEVELS.map((level) => {
                            const levelWarnings = report.warningsByLevel[level];
                            if (!levelWarnings.length) return null;
                            return (
                              <div key={level} className="space-y-1">
                                <p className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                                  {WARNING_LEVEL_LABELS[level]} {formatInteger(levelWarnings.length)}건
                                </p>
                                <ul className="space-y-1.5">
                                  {levelWarnings.map((detail, warningIndex) => (
                                    <li key={`${detail.warning}-${warningIndex}`} className="text-xs leading-5 text-slate-700 dark:text-slate-300">
                                      <span className="break-all text-slate-500 dark:text-slate-400">[{detail.warningCode}]</span> {detail.warning}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="text-sm text-slate-500 dark:text-slate-400">알림 없음</div>
              )}
            </div>
          }
          settingsTitle="시스템 설정"
          settingsContent={
            <>
              <div className="space-y-5">
                <WorkflowPathSettings id="parse-separate-output-directory" fields={parsePathFields} onError={handlePathError} />
                <div className="space-y-3">
                <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">실행 옵션</p>
                </div>
                <HtmlWorkflowForm layout="inspector" fields={parseOptionFields} />
                </div>
              </div>
            </>
          }
        />
      </div>
    </HtmlWorkflowPage>
  );
}
