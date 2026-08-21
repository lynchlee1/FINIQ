"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Filter, Play, Loader2, Search } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Label } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import {
  WorkflowModeSwitch,
  type WorkflowModeOption,
} from "@/components/layout/WorkflowModeSwitch";
import { DATA_PATH_LABELS, type DataPathField } from "@/components/data-path/DataPathCard";
import { JobStatusLogger, PageLoadingSpinner, ActionDock } from "@finiq/web-app/status";
import { useSettingsStore } from "@/store/useSettingsStore";
import { apiPost } from "@/api/client";
import { useJobPolling } from "@/hooks/useJobPolling";
import { useJobStreaming } from "@/hooks/useJobStreaming";
import { SETTINGS_LABELS, UI_TEXT } from "@/config/uiText";
import { formatInteger } from "@/lib/format";
import {
  DisclosureConditionFilterCard,
  makeEmptyDisclosureCondition,
  normalizeDisclosureConditionBlocks,
  type DisclosureConditionBlock,
  type DisclosureConditionPreset,
} from "@/components/disclosures/DisclosureConditionFilterCard";
import { WorkflowPathSettings } from "@/components/data-path/WorkflowPathSettings";
import { HtmlInspectorField, HtmlInspectorToggle, htmlInspectorControlClassName } from "@/components/html-workflow/HtmlWorkflowTemplate";
import {
  deleteDisclosureConditionPreset,
  listDisclosureConditionPresets,
  saveDisclosureConditionPreset,
} from "@/lib/disclosureConditionPresets";
import { DataIntegrityInspectionCard } from "@/components/data-integrity/DataIntegrityInspectionCard";
import type {
  DataIntegrityInspectionStep,
  DataIntegrityInspectionVerdict,
} from "@/components/data-integrity/DataIntegrityInspectionPanel";

const FILTER_PAGE_SIZE = 20;
const TITLE_PAGE_SIZE = 50;

type FilterResult = {
  summary?: {
    matched_disclosures?: number;
    returned_disclosures?: number;
    unique_acpt_numbers?: number;
  };
  disclosures?: any[];
  external_html_download_transfer?: {
    path?: string;
    acpt_numbers?: number;
  };
};

type TitleSearchResult = {
  summary: {
    source_disclosures: number;
    matched_disclosures: number;
    matched_titles: number;
  };
  titles: Array<{
    title: string;
    disclosures: number;
  }>;
};

type FilterTaskMode = "title-search" | "filter";
type FilterLevel = "top-level" | "derived";

const presetIdentity = (preset: DisclosureConditionPreset) => (
  preset.id || (preset.parent_mode ? `${preset.parent_mode}/${preset.mode}` : preset.mode)
);

const presetLabel = (preset: DisclosureConditionPreset) => (
  preset.parent_mode ? `${preset.parent_mode} › ${preset.mode}` : preset.mode
);

const filterPagePresetLabel = (preset: DisclosureConditionPreset) => preset.mode;

const FILTER_TASK_MODE_OPTIONS: readonly WorkflowModeOption<FilterTaskMode>[] = [
  { value: "title-search", label: "공시내역 제목 검색", icon: Search },
  { value: "filter", label: "공시내역 필터링", icon: Filter },
];

const describeFilterInspectionIssue = (preset: DisclosureConditionPreset) => {
  const folder = presetLabel(preset);
  const query = preset.steps.database_query;
  const record = preset.steps.record;
  if (preset.status === "failed") {
    const failedStep = query.status === "failed" ? query : record;
    const error = failedStep.error?.trim();
    const reason = query.status === "failed"
      ? "검색에 실패했습니다"
      : "검색 결과를 저장하지 못했습니다";
    return error ? `${folder}: ${reason}. ${error}` : `${folder}: ${reason}.`;
  }
  if (preset.status === "interrupted") {
    return query.status === "interrupted"
      ? `${folder}: 검색이 중단되었습니다.`
      : `${folder}: 검색 결과를 저장하지 못하고 중단되었습니다.`;
  }
  if (preset.status === "running") {
    return `${folder}: 검색을 실행하는 중입니다.`;
  }
  return `${folder}: 조건만 저장되어 있고 검색은 아직 실행하지 않았습니다.`;
};


function getKindDisclosureUrl(acptNo: string) {
  return `https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno=${encodeURIComponent(acptNo)}&docno=&viewerhost=&viewerport=`;
}

export default function FilterPage() {
  const {
    output_root: rootDirectory,
    parallel_worker_count: parallelWorkerCount,
    external_html_transfer_directory: htmlTransferPath,
    disclosure_separate_output_directory: useSeparateOutputDirectory,
    fetchSettings,
    saveSetting,
  } = useSettingsStore();

  const [loading, setLoading] = useState(true);
  const [taskMode, setTaskMode] = useState<FilterTaskMode>("title-search");
  const [mode, setMode] = useState("");
  const [conditions, setConditions] = useState<DisclosureConditionBlock[]>([makeEmptyDisclosureCondition()]);
  const [selectedPreset, setSelectedPreset] = useState("");
  const [presets, setPresets] = useState<DisclosureConditionPreset[]>([]);
  const [filterLevel, setFilterLevel] = useState<FilterLevel>("top-level");
  const [parentMode, setParentMode] = useState("");
  const [limitUnlimited, setLimitUnlimited] = useState(true);
  const [limit, setLimit] = useState("1000");
  const [filterWorkers, setFilterWorkers] = useState("1");
  const [progressInterval, setProgressInterval] = useState("1000");
  const [result, setResult] = useState<FilterResult | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [titleResult, setTitleResult] = useState<TitleSearchResult | null>(null);
  const [titlePageIndex, setTitlePageIndex] = useState(0);
  const [inspectionRunning, setInspectionRunning] = useState(false);
  const [inspectionError, setInspectionError] = useState("");
  const [inspectionSummary, setInspectionSummary] = useState<{
    total: number;
    completed: number;
    issues: string[];
  } | null>(null);
  const {
    status: filterStatus,
    setStatus: setFilterStatus,
    isErrorStatus: isFilterErrorStatus,
    setIsErrorStatus: setIsFilterErrorStatus,
    isStreaming,
    streamJob,
    abortJob,
    appendStatus,
  } = useJobStreaming();
  const {
    status: titleStatus,
    setStatus: setTitleStatus,
    isErrorStatus: isTitleErrorStatus,
    setIsErrorStatus: setIsTitleErrorStatus,
    activeJobId: titleJobId,
    startPolling: startTitlePolling,
    cancelJob: cancelTitleSearch,
  } = useJobPolling({
    pollingEndpoint: "/api/disclosures/titles/jobs/{jobId}",
    cancelEndpoint: "/api/disclosures/titles/search/cancel",
    onSuccess: (response: TitleSearchResult) => {
      setTitleResult(response);
      setTitlePageIndex(0);
    },
  });
  const setStatus = useCallback((message: string) => {
    setFilterStatus(message);
    setTitleStatus(message);
  }, [setFilterStatus, setTitleStatus]);
  const setIsErrorStatus = useCallback((isError: boolean) => {
    setIsFilterErrorStatus(isError);
    setIsTitleErrorStatus(isError);
  }, [setIsFilterErrorStatus, setIsTitleErrorStatus]);
  const handlePathError = useCallback((message: string) => {
    setStatus(message);
    setIsErrorStatus(true);
  }, [setIsErrorStatus, setStatus]);
  const activeStatusMode: FilterTaskMode = titleJobId
    ? "title-search"
    : isStreaming
      ? "filter"
      : taskMode;
  const status = activeStatusMode === "title-search" ? titleStatus : filterStatus;
  const isErrorStatus = activeStatusMode === "title-search"
    ? isTitleErrorStatus
    : isFilterErrorStatus;
  const isJobActive = isStreaming || !!titleJobId;
  const presetListRequestIdRef = useRef(0);
  const inspectionRequestIdRef = useRef(0);
  const currentDataRootRef = useRef(rootDirectory);
  currentDataRootRef.current = rootDirectory;

  useEffect(() => {
    if (titleJobId) {
      setTaskMode("title-search");
    }
  }, [titleJobId]);

  useEffect(() => {
    fetchSettings().then((config) => {
      const workerCount = Number(config?.parallel_worker_count);
      if (!Number.isInteger(workerCount) || workerCount < 1) {
        throw new Error("parallel_worker_count must be a positive integer");
      }
      setFilterWorkers(String(workerCount));
      setStatus("공시 소스 폴더를 불러왔습니다.");
    }).catch((error) => {
      setStatus(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    }).finally(() => {
      setLoading(false);
    });
  }, [fetchSettings, setIsErrorStatus, setStatus]);

  useEffect(() => {
    const requestId = ++presetListRequestIdRef.current;
    setPresets([]);
    setSelectedPreset("");
    if (!rootDirectory?.trim()) {
      return;
    }
    listDisclosureConditionPresets(rootDirectory).then((response) => {
      if (requestId !== presetListRequestIdRef.current) return;
      setPresets(response.presets);
    }).catch((error) => {
      if (requestId !== presetListRequestIdRef.current) return;
      setPresets([]);
      setStatus(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    });
  }, [rootDirectory, setIsErrorStatus, setStatus]);

  useEffect(() => {
    inspectionRequestIdRef.current += 1;
    setInspectionRunning(false);
    setInspectionError("");
    setInspectionSummary(null);
  }, [rootDirectory]);

  const applyPreset = useCallback((preset: DisclosureConditionPreset, statusMessage: string) => {
    setConditions(normalizeDisclosureConditionBlocks(preset.condition_blocks));
    setMode(preset.mode);
    setFilterLevel(preset.parent_mode ? "derived" : "top-level");
    setParentMode(preset.parent_mode || "");
    setStatus(statusMessage);
    setIsErrorStatus(false);
  }, [setIsErrorStatus, setStatus]);

  const selectedPresetEntry = useMemo(
    () => presets.find((preset) => {
      if (presetIdentity(preset) !== selectedPreset) return false;
      return filterLevel === "derived" ? Boolean(preset.parent_mode) : !preset.parent_mode;
    }),
    [filterLevel, presets, selectedPreset],
  );
  const completedTopLevelPresets = useMemo(
    () => presets.filter((preset) => !preset.parent_mode && preset.status === "completed"),
    [presets],
  );
  const identityPresets = useMemo(() => {
    if (filterLevel !== "derived") {
      return presets.filter((preset) => !preset.parent_mode);
    }
    return presets.filter((preset) => (
      preset.parent_mode && (!parentMode || preset.parent_mode === parentMode)
    ));
  }, [filterLevel, parentMode, presets]);
  const currentFilterMode = selectedPresetEntry?.mode || selectedPreset.trim() || mode;
  const currentParentMode = selectedPresetEntry?.parent_mode
    || (filterLevel === "derived" ? parentMode : "");
  const hasCompletedParent = completedTopLevelPresets.some(
    (preset) => preset.mode === currentParentMode,
  );
  const beginNewFilter = (nextLevel: FilterLevel) => {
    setFilterLevel(nextLevel);
    setParentMode("");
    if (selectedPresetEntry) {
      setSelectedPreset("");
      setMode("");
    }
  };

  const pageCount = Math.max(1, Math.ceil((result?.disclosures?.length || 0) / FILTER_PAGE_SIZE));
  const pageRows = useMemo(() => {
    const rows = result?.disclosures || [];
    const safeIndex = Math.min(Math.max(pageIndex, 0), pageCount - 1);
    return rows.slice(safeIndex * FILTER_PAGE_SIZE, (safeIndex + 1) * FILTER_PAGE_SIZE);
  }, [pageCount, pageIndex, result]);

  const titlePageCount = Math.max(1, Math.ceil((titleResult?.titles.length || 0) / TITLE_PAGE_SIZE));
  const titlePageRows = useMemo(() => {
    const rows = titleResult?.titles || [];
    const safeIndex = Math.min(Math.max(titlePageIndex, 0), titlePageCount - 1);
    return rows.slice(safeIndex * TITLE_PAGE_SIZE, (safeIndex + 1) * TITLE_PAGE_SIZE);
  }, [titlePageCount, titlePageIndex, titleResult]);

  const buildPayload = () => {
    const configuredLimit = Number(limit);
    const configuredWorkers = Number(filterWorkers);
    const configuredProgressInterval = Number(progressInterval);
    if (!Number.isInteger(configuredLimit) || configuredLimit < 1) {
      throw new Error("limit must be a positive integer");
    }
    if (!Number.isInteger(configuredWorkers) || configuredWorkers < 1) {
      throw new Error("filter_workers must be a positive integer");
    }
    if (!Number.isInteger(configuredProgressInterval) || configuredProgressInterval < 1) {
      throw new Error("progress_interval must be a positive integer");
    }
    return {
      data_root: rootDirectory,
      mode: currentFilterMode,
      ...(currentParentMode ? { parent_mode: currentParentMode } : {}),
      ...(useSeparateOutputDirectory ? {
        external_html_transfer_path: htmlTransferPath,
      } : {}),
      filter_blocks: normalizeDisclosureConditionBlocks(conditions),
      title_expression: "",
      limit: limitUnlimited ? null : configuredLimit,
      limit_unlimited: limitUnlimited,
      return_limit: configuredLimit,
      include_external_html_download_acpt_numbers: true,
      filter_workers: configuredWorkers,
      progress_interval: configuredProgressInterval,
    };
  };

  const isCurrentPresetWorkspace = (dataRoot: string, requestId: number) => (
    currentDataRootRef.current === dataRoot
    && presetListRequestIdRef.current === requestId
  );

  const handleTitleSearch = async () => {
    setTaskMode("title-search");
    if (!rootDirectory?.trim()) {
      setTitleStatus("작업공간 디렉토리를 선택하세요.");
      setIsTitleErrorStatus(true);
      return;
    }
    const configuredWorkers = Number(filterWorkers);
    if (!Number.isInteger(configuredWorkers) || configuredWorkers < 1) {
      setTitleStatus("filter_workers must be a positive integer");
      setIsTitleErrorStatus(true);
      return;
    }
    setTitleResult(null);
    setTitlePageIndex(0);
    try {
      const response = await apiPost<{ job_id: string }>("/api/disclosures/titles/search/start", {
        data_root: rootDirectory,
        filter_blocks: normalizeDisclosureConditionBlocks(conditions),
        filter_workers: configuredWorkers,
      });
      startTitlePolling(response.job_id);
    } catch (error) {
      setTitleStatus(error instanceof Error ? error.message : String(error));
      setIsTitleErrorStatus(true);
    }
  };

  const handleCancel = () => {
    if (titleJobId) {
      void cancelTitleSearch();
      return;
    }
    abortJob();
  };

  const refreshPresetsAfterRun = async (
    dataRoot: string,
    filterMode: string,
    filterParentMode: string,
    requestId: number,
    waitForTerminalStatus: boolean,
  ) => {
    let retryDelay = 100;
    for (;;) {
      if (!isCurrentPresetWorkspace(dataRoot, requestId)) return;
      const response = await listDisclosureConditionPresets(dataRoot, { force: true });
      if (!isCurrentPresetWorkspace(dataRoot, requestId)) return;
      setPresets(response.presets);
      const workflow = response.presets.find((preset) => (
        preset.mode === filterMode && (preset.parent_mode || "") === filterParentMode
      ));
      if (!waitForTerminalStatus || workflow?.status !== "running") return;
      await new Promise((resolve) => setTimeout(resolve, retryDelay));
      retryDelay = Math.min(retryDelay * 2, 1000);
    }
  };

  const handleFilter = async () => {
    setTaskMode("filter");
    if (!rootDirectory?.trim()) {
      setStatus(`${DATA_PATH_LABELS.workspace}를 선택하세요.`);
      setIsErrorStatus(true);
      return;
    }
    const filterMode = currentFilterMode;
    const filterParentMode = currentParentMode;
    if (!filterMode) {
      setStatus("조건검색 필터를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (filterLevel === "derived" && (!filterParentMode || !hasCompletedParent)) {
      setStatus("완료된 상위 필터를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (useSeparateOutputDirectory && !htmlTransferPath.trim()) {
      setStatus(`${DATA_PATH_LABELS.workspace}를 선택하세요.`);
      setIsErrorStatus(true);
      return;
    }

    setResult(null);
    setPageIndex(0);
    const dataRoot = rootDirectory;
    const requestId = presetListRequestIdRef.current;
    let streamOutcome: "completed" | "aborted" | "failed" | null = null;

    try {
      const filterPayload = { ...buildPayload(), mode: filterMode };
      const saved = await saveDisclosureConditionPreset(dataRoot, {
        mode: filterMode,
        ...(filterParentMode ? { parent_mode: filterParentMode } : {}),
        condition_blocks: normalizeDisclosureConditionBlocks(conditions),
      });
      if (!isCurrentPresetWorkspace(dataRoot, requestId)) return;
      setMode(filterMode);
      const savedPreset = saved.presets.find((preset) => (
        preset.mode === filterMode && (preset.parent_mode || "") === filterParentMode
      ));
      setSelectedPreset(savedPreset ? presetIdentity(savedPreset) : filterMode);
      setPresets(saved.presets);
      inspectionRequestIdRef.current += 1;
      setInspectionRunning(false);
      setInspectionError("");
      setInspectionSummary(null);
      setPresets((items) => items.map((preset) => (
        preset.mode === filterMode && (preset.parent_mode || "") === filterParentMode
      ) ? {
        ...preset,
        status: "running",
        steps: {
          ...preset.steps,
          database_query: { status: "running" },
          record: { status: "pending" },
        },
      } : preset));
      streamOutcome = await streamJob("/api/disclosures/filter", filterPayload, (payload: FilterResult) => {
        if (!isCurrentPresetWorkspace(dataRoot, requestId)) return;
        setResult(payload);
        const transferPath = String(payload.external_html_download_transfer?.path || "").trim();
        const saved = transferPath ? `접수번호 ${formatInteger(payload.external_html_download_transfer?.acpt_numbers)}개를 저장했습니다: ${transferPath}` : "저장 파일을 만들지 못했습니다.";
        appendStatus(`매칭 ${formatInteger(payload.summary?.matched_disclosures)}건 중 ${formatInteger(payload.summary?.returned_disclosures)}건을 표시했고, ${saved}`, !transferPath);
      });
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    } finally {
      try {
        await refreshPresetsAfterRun(
          dataRoot,
          filterMode,
          filterParentMode,
          requestId,
          streamOutcome === "aborted",
        );
      } catch (error) {
        if (!isCurrentPresetWorkspace(dataRoot, requestId)) return;
        setStatus(error instanceof Error ? error.message : String(error));
        setIsErrorStatus(true);
      }
    }
  };

  const savePreset = async () => {
    const filterMode = currentFilterMode;
    const filterParentMode = currentParentMode;
    if (!rootDirectory?.trim() || !filterMode) {
      setStatus(!rootDirectory?.trim() ? "작업공간 디렉토리를 선택하세요." : "조건검색 필터 이름을 입력하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (filterLevel === "derived" && (!filterParentMode || !hasCompletedParent)) {
      setStatus("완료된 상위 필터를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const dataRoot = rootDirectory;
    const requestId = presetListRequestIdRef.current;
    try {
      const response = await saveDisclosureConditionPreset(dataRoot, {
        mode: filterMode,
        ...(filterParentMode ? { parent_mode: filterParentMode } : {}),
        condition_blocks: normalizeDisclosureConditionBlocks(conditions),
      });
      if (!isCurrentPresetWorkspace(dataRoot, requestId)) return;
      setPresets(response.presets);
      inspectionRequestIdRef.current += 1;
      setInspectionRunning(false);
      setInspectionError("");
      setInspectionSummary(null);
      setMode(filterMode);
      const savedPreset = response.presets.find((preset) => (
        preset.mode === filterMode && (preset.parent_mode || "") === filterParentMode
      ));
      setSelectedPreset(savedPreset ? presetIdentity(savedPreset) : filterMode);
      setStatus(`조건검색 필터를 저장했습니다: ${filterParentMode ? `${filterParentMode} › ` : ""}${filterMode}`);
      setIsErrorStatus(false);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    }
  };

  const loadPreset = (name: string) => {
    const preset = (presets || []).find((item) => presetIdentity(item) === name);
    if (!preset) {
      setStatus("선택한 필터를 찾을 수 없습니다.");
      setIsErrorStatus(true);
      return;
    }
    applyPreset(preset, `조건검색 필터를 불러왔습니다: ${presetLabel(preset)}`);
  };

  const deletePreset = async () => {
    if (!selectedPreset) return;
    if (!rootDirectory?.trim()) {
      setStatus("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const dataRoot = rootDirectory;
    const requestId = presetListRequestIdRef.current;
    try {
      if (!selectedPresetEntry) {
        setStatus("선택한 필터를 찾을 수 없습니다.");
        setIsErrorStatus(true);
        return;
      }
      const response = await deleteDisclosureConditionPreset(
        dataRoot,
        selectedPresetEntry.mode,
        selectedPresetEntry.parent_mode,
      );
      if (!isCurrentPresetWorkspace(dataRoot, requestId)) return;
      setPresets(response.presets);
      inspectionRequestIdRef.current += 1;
      setInspectionRunning(false);
      setInspectionError("");
      setInspectionSummary(null);
      setSelectedPreset("");
      setStatus(`조건검색 필터를 삭제했습니다: ${presetLabel(selectedPresetEntry)}`);
      setIsErrorStatus(false);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
      setIsErrorStatus(true);
    }
  };

  const handleInspectExistingFilter = async () => {
    if (!rootDirectory?.trim()) {
      setStatus("작업공간 디렉토리를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    const dataRoot = rootDirectory;
    const requestId = presetListRequestIdRef.current;
    const inspectionRequestId = ++inspectionRequestIdRef.current;
    setInspectionRunning(true);
    setInspectionError("");
    setInspectionSummary(null);
    try {
      const response = await apiPost<{
        presets: DisclosureConditionPreset[];
      }>("/api/disclosures/filter/presets", {
        data_root: dataRoot,
        action: "inspect",
      });
      if (!isCurrentPresetWorkspace(dataRoot, requestId)
        || inspectionRequestIdRef.current !== inspectionRequestId) return;
      setPresets(response.presets);
      const issues = response.presets
        .filter((preset) => preset.status !== "completed")
        .map(describeFilterInspectionIssue);
      const summary = {
        total: response.presets.length,
        completed: response.presets.length - issues.length,
        issues,
      };
      setInspectionSummary(summary);
      setStatus(issues.length
        ? `조건검색 폴더 ${issues.length}개에 문제가 있습니다.`
        : `조건검색 폴더 ${summary.total}개를 모두 확인했습니다.`);
      setIsErrorStatus(issues.length > 0);
    } catch (error) {
      if (!isCurrentPresetWorkspace(dataRoot, requestId)
        || inspectionRequestIdRef.current !== inspectionRequestId) return;
      const message = error instanceof Error ? error.message : String(error);
      setInspectionError(message);
      setStatus(message);
      setIsErrorStatus(true);
    } finally {
      if (isCurrentPresetWorkspace(dataRoot, requestId)
        && inspectionRequestIdRef.current === inspectionRequestId) {
        setInspectionRunning(false);
      }
    }
  };

  const pathFields: DataPathField[] = [
    {
      id: "workspace",
      label: DATA_PATH_LABELS.workspace,
      value: rootDirectory || "",
      onChange: (val) => saveSetting("output_root", val),
    },
    ...(taskMode === "filter" ? [{
      id: "output",
      label: DATA_PATH_LABELS.output,
      value: htmlTransferPath || "",
      onChange: (val: string) => saveSetting("external_html_transfer_directory", val),
      separateOutputOnly: true,
    }] : []),
  ];

  if (loading) {
    return <PageLoadingSpinner message="설정을 불러오는 중입니다..." />;
  }

  let inspectionVerdict: DataIntegrityInspectionVerdict;
  if (!rootDirectory?.trim()) {
    inspectionVerdict = {
      label: "대기",
      title: "작업공간 디렉토리를 선택하세요",
      description: "작업공간 디렉토리를 선택한 다음 조건검색 폴더를 모두 검사하세요.",
      tone: "neutral",
    };
  } else if (inspectionRunning) {
    inspectionVerdict = {
      label: "검사 중",
      title: "조건검색 폴더 전체를 확인하고 있습니다",
      description: "각 폴더의 저장 설정과 처리 단계를 확인하고 결과에 문제가 없는지 검사합니다.",
      tone: "neutral",
    };
  } else if (inspectionError || inspectionSummary?.issues.length) {
    inspectionVerdict = {
      label: "사용 불가",
      title: "조건검색 폴더에 문제가 있습니다",
      description: inspectionError || `${inspectionSummary?.issues.length || 0}개 폴더의 처리가 완료되지 않았습니다.`,
      tone: "error",
    };
  } else if (inspectionSummary) {
    inspectionVerdict = {
      label: "정상",
      title: "모든 조건검색 폴더가 정상입니다",
      description: `조건검색 폴더 ${inspectionSummary.total}개의 저장 설정과 처리 단계, 결과를 모두 확인했습니다.`,
      tone: "success",
    };
  } else {
    inspectionVerdict = {
      label: "대기",
      title: "검사를 시작하지 않았습니다",
      description: "검사하기를 누르면 현재 선택한 필터와 관계없이 조건검색 폴더를 모두 확인합니다.",
      tone: "neutral",
    };
  }
  const inspectionSteps: DataIntegrityInspectionStep[] = [
    {
      key: "filter-folders",
      title: "조건검색 폴더 전체 검사",
      summary: inspectionError
        || (inspectionSummary
          ? `전체 ${inspectionSummary.total}개 중 ${inspectionSummary.completed}개가 정상입니다.`
          : "각 조건검색 폴더의 저장 설정과 처리 단계를 확인하고 결과에 문제가 없는지 검사합니다."),
      status: inspectionRunning
        ? "running"
        : inspectionError || inspectionSummary?.issues.length
          ? "failed"
          : inspectionSummary
          ? "complete"
          : "waiting",
      statusLabel: inspectionRunning
        ? "검사 중"
        : inspectionError || inspectionSummary?.issues.length
          ? "사용 불가"
          : inspectionSummary
          ? "정상"
          : "대기",
      detail: inspectionSummary?.issues.length ? (
        <ul className="space-y-1 text-[13px] leading-5 text-[var(--tv-down-text)]">
          {inspectionSummary.issues.map((issue) => <li key={issue}>{issue}</li>)}
        </ul>
      ) : undefined,
      action: rootDirectory?.trim() ? {
        label: inspectionRunning ? "검사 중..." : "검사하기",
        onClick: handleInspectExistingFilter,
        disabled: inspectionRunning || isJobActive,
        loading: inspectionRunning,
        showResultStatus: true,
      } : undefined,
    },
  ];

  return (
    <WorkflowPageShell workflowId="disclosure-build">
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          <WorkflowModeSwitch
            ariaLabel="공시 작업 모드"
            value={taskMode}
            options={FILTER_TASK_MODE_OPTIONS}
            onValueChange={setTaskMode}
            testId="filter-mode-control"
          />

          {taskMode === "filter" && (
            <DataIntegrityInspectionCard
              description="실행 전에 저장된 조건검색 설정과 처리 단계를 확인하고 결과에 문제가 없는지 검사합니다."
              verdict={inspectionVerdict}
              steps={inspectionSteps}
            />
          )}

          {/* LEGACY: 본문 데이터 경로 카드. 경로 입력은 우측 설정 패널(WorkflowPathSettings)로 옮겼다.
              <DataPathCard onError={handlePathError} fields={pathFields} /> */}

          <DisclosureConditionFilterCard
            conditions={conditions}
            onConditionsChange={setConditions}
            presets={identityPresets}
            libraryPresets={presets}
            selectedPreset={selectedPreset}
            onSelectedPresetChange={setSelectedPreset}
            onLoadPreset={loadPreset}
            onSavePreset={savePreset}
            onDeletePreset={deletePreset}
            getPresetIdentity={presetIdentity}
            getPresetLabel={filterPagePresetLabel}
            getLibraryPresetLabel={presetLabel}
            presetSelectorLabel={filterLevel === "derived" ? "파생 필터" : "조건검색 필터"}
            showPresetActions={taskMode === "filter"}
            showEyebrow={false}
            presetSelectorHelpDescription={filterLevel === "derived"
              ? "파생 필터는 완료된 상위 필터 결과에만 조건을 추가하며, 한 단계까지만 만들 수 있습니다."
              : undefined}
            identityControls={(
              <div className="grid gap-4">
                <div className="flex w-fit gap-1 rounded-lg border border-slate-200 p-1 dark:border-[#30363d]">
                  {([
                    ["top-level", "기본 필터"],
                    ["derived", "파생 필터"],
                  ] as const).map(([value, label]) => (
                    <Button
                      key={value}
                      type="button"
                      size="sm"
                      variant={filterLevel === value ? "default" : "ghost"}
                      aria-pressed={filterLevel === value}
                      onClick={() => {
                        if (filterLevel !== value) beginNewFilter(value);
                      }}
                    >
                      {label}
                    </Button>
                  ))}
                </div>
                {filterLevel === "derived" && (
                  <div className="grid gap-2">
                    <Label htmlFor="parent-filter" className="dark:text-slate-300">상위 필터</Label>
                    <select
                      id="parent-filter"
                      value={parentMode}
                      onChange={(event) => {
                        const nextParent = event.target.value;
                        setParentMode(nextParent);
                        if (selectedPresetEntry?.parent_mode && selectedPresetEntry.parent_mode !== nextParent) {
                          setSelectedPreset("");
                          setMode("");
                        }
                      }}
                      className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm font-semibold dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-200"
                    >
                      <option value="">완료된 상위 필터 선택</option>
                      {completedTopLevelPresets.map((preset) => (
                        <option key={presetIdentity(preset)} value={preset.mode}>{preset.mode}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            )}
          />

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <Button
                  onClick={taskMode === "title-search" ? handleTitleSearch : handleFilter}
                  disabled={isJobActive}
                  className="h-10 w-full"
                >
                  {isJobActive ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : taskMode === "title-search" ? (
                    <Search className="mr-2 h-4 w-4" />
                  ) : (
                    <Play className="mr-2 h-4 w-4" />
                  )}
                  실행
                </Button>
                <Button variant="outline" onClick={handleCancel} disabled={!isJobActive} className="h-10 w-full">
                  {UI_TEXT.actions.cancelJob}
                </Button>
              </div>
            </CardContent>
          </Card>

          {taskMode === "title-search" ? (
            <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
              <CardHeader>
                <CardTitle className="dark:text-white">제목 검색 결과</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500 dark:text-slate-400">
                  <span>공시 {formatInteger(titleResult?.summary.matched_disclosures)}건 · 제목 {formatInteger(titleResult?.summary.matched_titles)}개</span>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={() => setTitlePageIndex((value) => Math.max(0, value - 1))} disabled={!titleResult?.titles.length || titlePageIndex <= 0}>이전</Button>
                    <span className="min-w-[72px] text-center font-bold">{titleResult?.titles.length ? `${titlePageIndex + 1} / ${titlePageCount}` : "0 / 0"}</span>
                    <Button variant="outline" size="sm" onClick={() => setTitlePageIndex((value) => Math.min(titlePageCount - 1, value + 1))} disabled={!titleResult?.titles.length || titlePageIndex >= titlePageCount - 1}>다음</Button>
                  </div>
                </div>
                <div className="h-[460px] overflow-auto rounded-lg border border-slate-200 bg-white dark:bg-[#0d1117] dark:border-[#30363d]">
                  <table className="w-full border-collapse text-sm">
                    <thead className="sticky top-0 bg-white text-left text-slate-500 dark:bg-[#161b22] dark:text-slate-400">
                      <tr>
                        <th className="w-24 border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">번호</th>
                        <th className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">공시 제목</th>
                        <th className="w-32 border-b border-slate-200 px-3 py-2 text-right dark:border-[#30363d]">공시 건수</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
                      {titlePageRows.length ? titlePageRows.map((row, index) => (
                        <tr key={row.title} className="hover:bg-slate-50 dark:hover:bg-[#161b22] dark:text-slate-300">
                          <td className="px-3 py-2 text-slate-500 dark:text-slate-400">{titlePageIndex * TITLE_PAGE_SIZE + index + 1}</td>
                          <td className="px-3 py-2 font-medium">{row.title}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{formatInteger(row.disclosures)}</td>
                        </tr>
                      )) : (
                        <tr>
                          <td className="px-3 py-10 text-center text-slate-500 dark:text-slate-400" colSpan={3}>제목 검색 결과가 없습니다.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          ) : (
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
          <CardTitle className="dark:text-white">필터 결과</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-2 flex items-center justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setPageIndex((value) => Math.max(0, value - 1))} disabled={!result?.disclosures?.length || pageIndex <= 0}>이전</Button>
            <span className="min-w-[72px] text-center text-sm font-bold text-slate-500 dark:text-slate-400">{result?.disclosures?.length ? `${Math.min(pageIndex + 1, pageCount)} / ${pageCount}` : "0 / 0"}</span>
            <Button variant="outline" size="sm" onClick={() => setPageIndex((value) => Math.min(pageCount - 1, value + 1))} disabled={!result?.disclosures?.length || pageIndex >= pageCount - 1}>다음</Button>
          </div>
          <div className="h-[460px] overflow-auto rounded-lg border border-slate-200 bg-white dark:bg-[#0d1117] dark:border-[#30363d]">
            <table className="w-full border-collapse text-sm">
              <thead className="sticky top-0 bg-white text-left text-slate-500 dark:bg-[#161b22] dark:text-slate-400">
                <tr>
                  <th className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">공시일</th>
                  <th className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">회사</th>
                  <th className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">시장</th>
                  <th className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">제목</th>
                  <th className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">제출인</th>
                  <th className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">접수번호</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
                {pageRows.length ? pageRows.map((row, index) => {
                  const acptNo = String(row.acpt_no || "");
                  const title = row.title || "";
                  return (
                    <tr key={`${acptNo}-${index}`} className="hover:bg-slate-50 dark:hover:bg-[#161b22] dark:text-slate-300">
                      <td className="px-3 py-2 whitespace-nowrap">{String(row.disclosed_at || "").split(" ")[0]}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{row.company_name || ""}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{row.market || ""}</td>
                      <td className="px-3 py-2 min-w-[320px]">
                        {acptNo ? (
                          <a className="font-bold text-[var(--tv-accent)] hover:underline" href={getKindDisclosureUrl(acptNo)} target="_blank" rel="noreferrer">{title}</a>
                        ) : title}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">{row.submitter || ""}</td>
                      <td className="px-3 py-2 whitespace-nowrap font-mono text-xs">{acptNo}</td>
                    </tr>
                  );
                }) : (
                  <tr>
                    <td className="px-3 py-10 text-center text-slate-500 dark:text-slate-400" colSpan={6}>필터 결과가 없습니다.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
          </Card>
          )}

        </section>

        <ActionDock
          activityActive={isJobActive}
          activityContent={
            <JobStatusLogger 
              status={status} 
              isErrorStatus={isErrorStatus} 
              isCancellable={isJobActive}
              onCancel={handleCancel}
            />
          }
          notificationActive={isErrorStatus}
          notificationTone="error"
          notificationContent={<div className={isErrorStatus ? "whitespace-pre-wrap text-sm text-[var(--tv-down-text)]" : "text-sm text-[var(--tv-muted)]"}>{isErrorStatus ? status : "알림 없음"}</div>}
          settingsTitle="시스템 설정"
          settingsContent={
            <div className="space-y-5">
              <WorkflowPathSettings id="filter-separate-output-directory" fields={pathFields} onError={handlePathError} />
              {taskMode === "filter" && <div className="space-y-3">
                <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">결과 범위</p>
                </div>
              <div className="space-y-2">
                <HtmlInspectorField label="제한 없음">
                  <HtmlInspectorToggle checked={limitUnlimited} onCheckedChange={setLimitUnlimited} />
                </HtmlInspectorField>
                <HtmlInspectorField label={SETTINGS_LABELS.maxItems}>
                  <Input type="number" min="1" max="10000" step="1" value={limit} disabled={limitUnlimited} onChange={(event) => setLimit(event.target.value)} className={`${htmlInspectorControlClassName} disabled:opacity-50`} />
                </HtmlInspectorField>
              </div>
              </div>}
              <div className="space-y-3">
                <div className="border-b border-slate-200 pb-2 dark:border-[#30363d]">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">실행 옵션</p>
                </div>
              <div className="space-y-2">
              <HtmlInspectorField label={SETTINGS_LABELS.workerCount}>
                <Input type="number" min="1" max={parallelWorkerCount} step="1" value={filterWorkers} onChange={(event) => setFilterWorkers(event.target.value)} className={htmlInspectorControlClassName} />
              </HtmlInspectorField>
              {taskMode === "filter" && <HtmlInspectorField label={SETTINGS_LABELS.progressInterval}>
                <Input type="number" min="1" max="10000" step="1" value={progressInterval} onChange={(event) => setProgressInterval(event.target.value)} className={htmlInspectorControlClassName} />
              </HtmlInspectorField>}
              </div>
              </div>
            </div>
          }
        />
      </div>
    </WorkflowPageShell>
  );
}
