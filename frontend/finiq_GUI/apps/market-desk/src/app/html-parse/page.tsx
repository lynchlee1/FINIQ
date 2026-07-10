"use client"

import { useState, useEffect, useCallback } from "react";
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
  type DisclosureConditionPresetPayload,
} from "@/components/disclosures/DisclosureConditionFilterCard";
import {
  HtmlWorkflowForm,
  HtmlWorkflowCard,
  HtmlWorkflowPage,
  type HtmlWorkflowField,
} from "@/components/html-workflow/HtmlWorkflowTemplate";
import { UI_TEXT } from "@/config/uiText";
import { formatInteger } from "@/lib/format";
import { apiPost } from "@/api/client";
import { pickPath } from "@/lib/fileDialog";

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

const HTML_PARSE_RELATED_ROUTES = "/html-content-download /html-parse /html-change-log";
const PARSE_MODE_CONFIGS = Object.fromEntries(DISCLOSURE_PARSE_MODES.map((mode) => [mode.key, mode])) as Record<string, ParseModeConfig>;
const WARNING_OPEN_PAGE_SIZE = 20;
type FilterCandidate = DisclosureFilterCandidate & {
  examples?: Array<string | FilterCandidateExample>;
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
  acpt_no?: string;
  warning?: string;
  level?: string;
  warning_code?: string;
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

const normalizeWarningLevel = (level?: string): WarningLevel => (
  WARNING_LEVELS.includes(level as WarningLevel) ? level as WarningLevel : "medium_warning"
);

const normalizeWarningCode = (code?: string) => String(code || "parse_warning").trim() || "parse_warning";

const buildWarningReports = (warnings: ParseWarningItem[]): WarningReport[] => {
  const reportMap = new Map<string, WarningReport>();

  warnings.forEach((item) => {
    const warning = String(item.warning || "").trim();
    const acptNo = String(item.acpt_no || "").trim();
    if (!warning || !acptNo) return;

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
  if (!Array.isArray(examples)) return [];
  return examples.map((example) => {
    if (typeof example === "string") {
      return { acpt_no: example };
    }
    return {
      acpt_no: String(example.acpt_no || "").trim(),
    };
  }).filter((example) => example.acpt_no);
};

export default function HtmlParsePage() {
  const {
    condition_presets: presets,
    fetchSettings,
    parallel_worker_count: defaultParallelWorkers,
    saveSetting,
  } = useSettingsStore();

  const [loading, setLoading] = useState(true);
  const [latestParseResult, setLatestParseResult] = useState<any>(null);
  const [warningOpenPages, setWarningOpenPages] = useState<Record<string, number>>({});

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
    onSuccess: (result) => {
      setLatestParseResult(result);
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
  const [conditions, setConditions] = useState<DisclosureConditionBlock[]>([makeEmptyDisclosureCondition()]);
  const [presetName, setPresetName] = useState("");
  const [selectedPreset, setSelectedPreset] = useState("");
  const [filterPresetPath, setFilterPresetPath] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);
  const selectedParseMode = PARSE_MODE_CONFIGS[parseMode] || DISCLOSURE_PARSE_MODES[0];
  const executionOptionConfig = selectedParseMode.executionOptions[0] || null;

  const startJob = useCallback(async (endpoint: string, payload: any) => {
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("Job start failed");
      const data = await response.json();
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

      const configuredParallelWorkers = Number(config.parallel_worker_count || defaultParallelWorkers || 1);
      setParallelWorkers(String(configuredParallelWorkers));
    }).catch(err => {
      setStatus(err.message);
      setIsErrorStatus(true);
    }).finally(() => {
      setLoading(false);
    });
  }, [defaultParallelWorkers, fetchSettings, setStatus, setIsErrorStatus]);

  const handleInputDirectoryChange = (val: string) => {
    setInputDirectory(val);
    setSelectedExecutionOptionValues([]);
    setExecutionOptionCandidates([]);
    setExecutionOptionInputDirectory("");
    setExecutionOptionExampleNotice(null);
    saveSetting("html_section_split_output_directory", val);
  };

  const handleOutputDirectoryChange = (val: string) => {
    setOutputDirectory(val);
    saveSetting("html_parse_output_directory", val);
  };

  const handleParseModeChange = (val: string) => {
    setParseMode(val);
    setSelectedExecutionOptionValues([]);
    setExecutionOptionCandidates([]);
    setExecutionOptionInputDirectory("");
    setExecutionOptionExampleNotice(null);
    saveSetting("html_parse_mode", val);
  };

  const applyPreset = useCallback((preset: DisclosureConditionPresetPayload, statusMessage: string) => {
    setConditions(normalizeDisclosureConditionBlocks(preset.condition_blocks));
    if (preset.name) setPresetName(preset.name);
    setStatus(statusMessage);
    setIsErrorStatus(false);
  }, [setIsErrorStatus, setStatus]);

  const savePreset = () => {
    const name = presetName.trim();
    if (!name) {
      setStatus("저장할 프리셋 이름을 입력하세요.");
      setIsErrorStatus(true);
      return;
    }
    const next = (presets || []).filter((item: any) => item.name !== name);
    next.push({ name, condition_blocks: normalizeDisclosureConditionBlocks(conditions) });
    next.sort((a: any, b: any) => a.name.localeCompare(b.name, "ko"));

    saveSetting("condition_presets", next);
    setSelectedPreset(name);
    setStatus(`조건검색 프리셋을 저장했습니다: ${name}`);
    setIsErrorStatus(false);
  };

  const loadPreset = (name: string) => {
    const preset = (presets || []).find((item: any) => item.name === name);
    if (!preset) {
      setStatus("선택한 프리셋을 찾을 수 없습니다.");
      setIsErrorStatus(true);
      return;
    }
    applyPreset(preset, `조건검색 프리셋을 불러왔습니다: ${preset.name}`);
  };

  const renamePreset = () => {
    if (!selectedPreset) return;
    const name = presetName.trim();
    if (!name) {
      setStatus("수정할 프리셋 이름을 입력하세요.");
      setIsErrorStatus(true);
      return;
    }
    const preset = (presets || []).find((item: any) => item.name === selectedPreset);
    if (!preset) {
      setStatus("선택한 프리셋을 찾을 수 없습니다.");
      setIsErrorStatus(true);
      return;
    }
    if (name !== selectedPreset && (presets || []).some((item: any) => item.name === name)) {
      setStatus(`이미 같은 이름의 프리셋이 있습니다: ${name}`);
      setIsErrorStatus(true);
      return;
    }
    const next = (presets || []).map((item: any) => item.name === selectedPreset ? { ...item, name } : item);
    next.sort((a: any, b: any) => a.name.localeCompare(b.name, "ko"));

    saveSetting("condition_presets", next);
    setSelectedPreset(name);
    setPresetName(name);
    setStatus(`조건검색 프리셋 이름을 수정했습니다: ${selectedPreset} -> ${name}`);
    setIsErrorStatus(false);
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
    } catch (err: any) {
      setStatus(err.message || "필터 결과 JSON을 불러오지 못했습니다.");
      setIsErrorStatus(true);
    }
  };

  const deletePreset = () => {
    if (!selectedPreset) return;
    const next = (presets || []).filter((item: any) => item.name !== selectedPreset);
    saveSetting("condition_presets", next);
    setPresetName((value) => value === selectedPreset ? "" : value);
    setSelectedPreset("");
    setStatus(`조건검색 프리셋을 삭제했습니다: ${selectedPreset}`);
    setIsErrorStatus(false);
  };

  useEffect(() => {
    if (!isJobActive) {
      setActiveCancelToken(null);
    }
  }, [isJobActive]);

  const handleRun = async () => {
    if (!inputDirectory) {
      setStatus("입력 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (!outputDirectory) {
      setStatus("결과 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const activeRecordFilters = executionOptionConfig && selectedExecutionOptionValues.length ? [
      {
        field: executionOptionConfig.field,
        operator: "in",
        value: selectedExecutionOptionValues,
      },
    ] : [];
    const cancelToken = window.crypto.randomUUID();
    setActiveCancelToken(cancelToken);
    setLatestParseResult(null);
    setWarningOpenPages({});

    const payload = {
      input_directory: inputDirectory,
      output_directory: outputDirectory,
      mode: parseMode,
      limit: limit ? Number(limit) : null,
      skip_errors: skipErrors,
      progress_interval: Number(progressInterval),
      parallel_workers: parallelWorkers ? Number(parallelWorkers) : null,
      filter_blocks: normalizeDisclosureConditionBlocks(conditions),
      record_filters: activeRecordFilters,
      cancel_token: cancelToken,
    };

    startJob("/api/disclosures/html/parse/start", payload);
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
    const resultInputDirectory = String(latestParseResult?.input_directory || "").trim();
    pageInfo.acptNumbers.forEach((acptNo) => {
      window.open(warningSourceUrl(acptNo, resultInputDirectory), "_blank", "noopener,noreferrer");
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
      setStatus("입력 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    setFilterCandidatesLoading(true);
    setIsErrorStatus(false);
    try {
      const response = await fetch("/api/disclosures/html/parse/filter-candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
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
      setExecutionOptionCandidates(Array.isArray(data.candidates) ? data.candidates : []);
      setExecutionOptionInputDirectory(String(data.input_directory || ""));
      setExecutionOptionExampleNotice(null);
      setStatus(`${executionOptionConfig.statusLabel} 후보 ${formatInteger(data.summary?.candidates || 0)}개를 불러왔습니다.`);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setFilterCandidatesLoading(false);
    }
  };

  const handleLoadPreview = async () => {
    if (!inputDirectory) {
      setStatus("입력 데이터 경로를 선택하세요.");
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

  const parseSettingFields: HtmlWorkflowField[] = [
    {
      id: "inputDirectory",
      kind: "path",
      label: "입력 데이터 경로 (HTML)",
      mode: "folder",
      value: inputDirectory,
      onChange: handleInputDirectoryChange,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 4,
    },
    {
      id: "outputDirectory",
      kind: "path",
      label: "결과 데이터 경로",
      mode: "folder",
      value: outputDirectory,
      onChange: handleOutputDirectoryChange,
      onError: (err) => { setStatus(err.message); setIsErrorStatus(true); },
      span: 4,
    },
    {
      id: "limit",
      kind: "input",
      type: "number",
      label: "최대 처리 건수",
      placeholder: "전체",
      value: limit,
      onChange: setLimit,
      span: 2,
    },
    {
      id: "progressInterval",
      kind: "input",
      type: "number",
      label: "진행 확인 간격 (건)",
      value: progressInterval,
      onChange: setProgressInterval,
      span: 2,
    },
    {
      id: "parallelWorkers",
      kind: "input",
      type: "number",
      label: "병렬 워커 수",
      help: "앱 최초 접속 시 확인한 CPU 기준 기본값을 사용합니다.",
      placeholder: String(defaultParallelWorkers || 1),
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
  const parsePathFields = parseSettingFields.filter((field) => field.id === "inputDirectory" || field.id === "outputDirectory");
  const parseOptionFields = parseSettingFields.filter((field) => field.id !== "inputDirectory" && field.id !== "outputDirectory");
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

  return (
    <HtmlWorkflowPage
      eyebrow="HTML Parse Guide"
      title="공시원문 변환"
      description="저장된 KIND HTML을 모드별 파서로 읽어 핵심 필드, 오류, 경고를 하나의 JSON에 남깁니다. 결과 파일은 공시 정정내역 한눈에, 발행내역 한눈에, Excel 내보내기의 기준 데이터가 됩니다."
    >
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          <HtmlWorkflowCard
            title="데이터 경로"
          >
            <HtmlWorkflowForm fields={parsePathFields} />
          </HtmlWorkflowCard>

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
            presetName={presetName}
            selectedPreset={selectedPreset}
            onPresetNameChange={setPresetName}
            onSelectedPresetChange={setSelectedPreset}
            onLoadPreset={loadPreset}
            onLoadPresetFromJson={loadFilterPresetFromJson}
            onSavePreset={savePreset}
            onRenamePreset={renamePreset}
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
          notificationResetKey={notificationResetKey}
          notificationContent={
            <div className="space-y-3">
              {isErrorStatus ? (
                <div className="whitespace-pre-wrap text-sm text-red-600 dark:text-red-300">{status || "오류 내용을 확인할 수 없습니다."}</div>
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
                  <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
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
              <div className="space-y-3">
                <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">실행 옵션</p>
                </div>
                <HtmlWorkflowForm fields={parseOptionFields} />
              </div>
            </>
          }
        />
      </div>
    </HtmlWorkflowPage>
  );
}
