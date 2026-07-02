"use client"

import { type MouseEvent as ReactMouseEvent, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Check, Eye, Loader2, Pencil, Play, Plus, Search, Trash2 } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Checkbox, Input, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { useJobPolling } from "@/hooks/useJobPolling";
import { useSettingsStore } from "@/store/useSettingsStore";
import { ActionDock } from "@/components/ui/ActionDock";
import { htmlTableFrameClassName } from "@/components/html-workflow/HtmlWorkflowTemplate";
import { UI_TEXT } from "@/config/uiText";
import { formatInteger } from "@/lib/format";
import {
  fetchAssetExcelFiles,
  fetchAssetExcelAccountMappings,
  fetchAssetExcelOutput,
  fetchAssetParquetPreview,
  fetchAssetExcelSheets,
  fetchAssetExcelSheet,
  saveAssetExcelAccountMappings,
  startAssetExcelConversion,
  startAssetParquetDuplicateCleanup,
  startAssetParquetMerge,
} from "./api";
import { applyFileSelection, dragSelectionTargetChecked, formatMergeSelectionSummary, selectFirstTwoFilesPerAccount, selectionRowClassName } from "./dragSelection";
import type { AssetAccountMapping, AssetExcelFile, PreviewData, SheetPayload } from "./types";

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function jobStatusLines(data: any): string[] {
  const statusLabel =
    data.status === "completed" ? "완료" :
    data.status === "failed" ? "실패" :
    data.status === "running" ? "실행 중" :
    data.status === "cancelled" ? "중단됨" :
    "대기 중";
  const lines = [`작업 상태: ${statusLabel}`];
  if (data.error) lines.push(`오류: ${data.error}`);
  if (data.progress_log?.length) lines.push("", "최근 로그:", ...data.progress_log.slice(-30));
  if (data.status === "completed" && data.result) {
    if (data.result.operation === "parquet_duplicate_cleanup") {
      lines.push(
        "",
        data.result.dry_run ? "중복 검사 완료" : "중복 삭제 완료",
        `중복 묶음: ${formatInteger(data.result.duplicate_group_count)}개`,
        `삭제 후보: ${formatInteger(data.result.deletion_candidate_count)}개`,
        `삭제 파일: ${formatInteger(data.result.deleted_count)}개`,
        `병합 대상 데이터 경로: ${data.result.target_directory || ""}`,
      );
      return lines;
    }
    if (data.result.operation === "merge_parquet") {
      lines.push(
        "",
        "병합 완료",
        `계정: ${formatInteger(data.result.accounts_processed)}개`,
        `선택 파일: ${formatInteger((data.result.selected_files || []).length)}개`,
        `병합 결과 데이터 경로: ${data.result.output_directory || ""}`,
      );
      return lines;
    }
    const skipped = data.result.skipped || [];
    const resumeSkipped = data.result.resume_skipped || [];
    lines.push(
      "",
      "변환 완료",
      `Sheet Parquet: ${formatInteger(data.result.sheets_processed ?? Object.keys(data.result.outputs || {}).length)}개`,
      `계정: ${formatInteger(data.result.accounts_processed)}개`,
      `건너뛴 Sheet: ${formatInteger(skipped.length)}개`,
      `이어하기 건너뜀: ${formatInteger(resumeSkipped.length)}개`,
      `데이터 경로: ${data.result.output_directory || ""}`,
    );
    if (skipped.length) {
      lines.push(
        "건너뛴 Sheet 상세:",
        ...skipped.map((item: any) => {
          const source = item.relative_path || item.file_name || "-";
          return `${source} / ${item.sheet_name || "-"} - ${item.reason || "-"}`;
        }),
      );
    }
  }
  return lines;
}

function formatPercent(value: number | undefined): string {
  if (!Number.isFinite(value)) return "-";
  return `${((value || 0) * 100).toFixed(2)}%`;
}

function sheetStatusLabel(status: string | undefined): string {
  if (status === "mapped") return "정상";
  if (status === "unmapped") return "미매핑";
  if (status === "format_error") return "형식 오류";
  return "-";
}

function fileNameFromPath(value: string | undefined): string {
  return String(value || "").split(/[\\/]/).filter(Boolean).pop() || "";
}

function accountNameFromParquetFile(fileName: string): string {
  const stem = String(fileName || "").replace(/\.parquet$/i, "");
  const match = stem.match(/^(?<account>.+)_\d{8}_\d{8}(?:_[0-9a-f]{64})?(?:(?:__|_)\d+)?$/);
  if (match?.groups?.account) return match.groups.account;
  return stem;
}

type OutputSortKey = "account_id" | "account_name" | "rows" | "columns" | "missing_ratio" | "non_null_cells" | "total_cells" | "date_start" | "date_end" | "sha256";
type SortDirection = "asc" | "desc";

function outputSortValue(name: string, item: any, key: OutputSortKey): string | number {
  if (key === "account_id") return item?.account_id || "";
  if (key === "account_name") return item?.account_name || "";
  if (key === "rows") return Number(item?.rows) || 0;
  if (key === "columns") return Number(item?.columns) || 0;
  if (key === "missing_ratio") return Number(item?.quality?.missing_ratio) || 0;
  if (key === "non_null_cells") return Number(item?.quality?.non_null_cells) || 0;
  if (key === "total_cells") return Number(item?.quality?.total_cells) || 0;
  if (key === "date_start") return outputDateStartText(name, item);
  if (key === "date_end") return outputDateEndText(name, item);
  return outputSha256Text(name, item);
}

function outputRowsFromInfo(info: any): [string, any][] {
  return mergeCandidateSourceRowsFromInfo(info);
}

function outputFileNameFromRow(name: string, item: any): string {
  const fallbackName = String(name || "");
  return item?.output_file || fileNameFromPath(item?.path) || item?.file_name || (fallbackName.endsWith(".parquet") ? fallbackName : `${fallbackName}.parquet`);
}

function outputAccountNameFromRow(name: string, item: any): string {
  return item?.account_name || accountNameFromParquetFile(outputFileNameFromRow(name, item));
}

function formatCompactOutputDate(value: string | undefined): string {
  return value && value.length === 8 ? `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}` : "";
}

function outputDateStartText(name: string, item: any): string {
  if (item?.date_start) return String(item.date_start);
  const match = outputFileNameFromRow(name, item).match(/^.+_(\d{8})_\d{8}(?:_[0-9a-f]{64})?(?:(?:__|_)\d+)?\.parquet$/i);
  return formatCompactOutputDate(match?.[1]);
}

function outputDateEndText(name: string, item: any): string {
  if (item?.date_end) return String(item.date_end);
  const match = outputFileNameFromRow(name, item).match(/^.+_\d{8}_(\d{8})(?:_[0-9a-f]{64})?(?:(?:__|_)\d+)?\.parquet$/i);
  return formatCompactOutputDate(match?.[1]);
}

function outputSha256Text(name: string, item: any): string {
  const explicitValue = item?.companies_hash || item?.companiesHash || item?.sha256;
  if (explicitValue) return String(explicitValue);
  const match = outputFileNameFromRow(name, item).match(/_([0-9a-f]{64})(?:(?:__|_)\d+)?\.parquet$/i);
  return match?.[1] || "";
}

function formatOutputInteger(value: unknown): string {
  return value === undefined || value === null || value === "" ? "-" : formatInteger(value);
}

function mergeCandidateSourceRowsFromInfo(info: any): [string, any][] {
  const rows: [string, any][] = [];
  const seen = new Set<string>();
  Object.entries(info?.outputs || {}).forEach(([name, item]: [string, any]) => {
    const fileName = outputFileNameFromRow(name, item);
    if (!fileName || seen.has(fileName)) return;
    seen.add(fileName);
    rows.push([name, item]);
  });
  (info?.parquet_files || []).forEach((fileName: string) => {
    if (!fileName || seen.has(fileName)) return;
    seen.add(fileName);
    rows.push([fileName, { file_name: fileName }]);
  });
  return rows;
}

function mergeCandidateRowsFromInfo(info: any): [string, any][] {
  const rows = mergeCandidateSourceRowsFromInfo(info);
  const counts: Record<string, number> = {};
  rows.forEach(([name, item]) => {
    const fileName = outputFileNameFromRow(name, item);
    const accountName = accountNameFromParquetFile(fileName);
    counts[accountName] = (counts[accountName] || 0) + 1;
  });
  return rows.filter(([name, item]) => {
    const fileName = outputFileNameFromRow(name, item);
    return (counts[accountNameFromParquetFile(fileName)] || 0) >= 2;
  });
}

function nextAccountId(mappings: AssetAccountMapping[]): string {
  const maxIndex = mappings.reduce((max, mapping) => {
    const match = String(mapping.account_id || "").match(/^S(\d+)$/);
    return match ? Math.max(max, Number(match[1])) : max;
  }, 0);
  return `S${String(maxIndex + 1).padStart(5, "0")}`;
}

export default function AssetExcelUtilityPage({ mode = "preview" }: { mode?: "preview" | "convert" | "parquet" | "merge" }) {
  const isConvertMode = mode === "convert";
  const isParquetPreviewMode = mode === "parquet";
  const isMergeMode = mode === "merge";
  const [excelFiles, setExcelFiles] = useState<AssetExcelFile[]>([]);
  const [selectedConvertFiles, setSelectedConvertFiles] = useState<string[]>([]);
  const [sourceDirectory, setSourceDirectory] = useState("");
  const [outputDirectory, setOutputDirectory] = useState("");
  const [mergeBaseDirectory, setMergeBaseDirectory] = useState("");
  const [mergeSameDirectory, setMergeSameDirectory] = useState(false);
  const [cleanupMergedItems, setCleanupMergedItems] = useState(true);
  const [duplicateScanRecursive, setDuplicateScanRecursive] = useState(false);
  const duplicateScanRecursiveRef = useRef(false);
  const [selectedMergeFiles, setSelectedMergeFiles] = useState<string[]>([]);
  const [duplicateInspectionResult, setDuplicateInspectionResult] = useState<any>(null);
  const [duplicateDeleteConfirmed, setDuplicateDeleteConfirmed] = useState(false);
  const [duplicateDeleteConfirmationText, setDuplicateDeleteConfirmationText] = useState("");
  const writeMode = "replace";
  const [loading, setLoading] = useState(true);
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [outputInfo, setOutputInfo] = useState<any>(null);
  const [mergeBaseInfo, setMergeBaseInfo] = useState<any>(null);
  const [lastResult, setLastResult] = useState<any>(null);
  const [selectedPreviewFile, setSelectedPreviewFile] = useState("");
  const [selectedSheet, setSelectedSheet] = useState("");
  const [sheetNames, setSheetNames] = useState<string[]>([]);
  const [sheetsLoading, setSheetsLoading] = useState(false);
  const [sheetBodyLoading, setSheetBodyLoading] = useState(false);
  const [sheetPayload, setSheetPayload] = useState<SheetPayload | null>(null);
  const [selectedParquetFile, setSelectedParquetFile] = useState("");
  const [parquetPayload, setParquetPayload] = useState<SheetPayload | null>(null);
  const [parquetLoading, setParquetLoading] = useState(false);
  const [accountMappings, setAccountMappings] = useState<AssetAccountMapping[]>([]);
  const [isAccountMappingEditing, setIsAccountMappingEditing] = useState(false);
  const [mappingsLoading, setMappingsLoading] = useState(false);
  const [mappingsSaving, setMappingsSaving] = useState(false);
  const [outputSort, setOutputSort] = useState<{ key: OutputSortKey; direction: SortDirection } | null>(null);
  const sheetPreviewCache = useRef<Record<string, SheetPayload>>({});
  const sheetBodyRequestToken = useRef(0);
  const convertDragSelection = useRef<{ checked: boolean } | null>(null);
  const mergeDragSelection = useRef<{ checked: boolean } | null>(null);
  const { fetchSettings, saveSetting } = useSettingsStore();

  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus, cancelJob } = useJobPolling({
    pollingEndpoint: "/api/assets/excels/jobs/{jobId}",
    cancelEndpoint: "/api/assets/excels/cancel",
    formatStatus: jobStatusLines,
    onSuccess: (result) => {
      if (result?.operation === "parquet_duplicate_cleanup") {
        setDuplicateInspectionResult(result);
        if (!result.dry_run && mergeBaseDirectory.trim()) {
          setDuplicateDeleteConfirmed(false);
          setDuplicateDeleteConfirmationText("");
          fetchAssetExcelOutput(mergeBaseDirectory)
            .then((data) => setMergeBaseInfo(data))
            .catch(() => setMergeBaseInfo(null));
        }
        return;
      }
      setLastResult(result);
      setPreviewData(null);
      setParquetPayload(null);
      if (result?.output_directory) setOutputDirectory(result.output_directory);
      const firstOutput = Object.values(result?.outputs || {}).find((item: any) => item?.output_file || item?.path) as any;
      setSelectedParquetFile(firstOutput?.output_file || fileNameFromPath(firstOutput?.path));
    },
  });

  useEffect(() => {
    fetchSettings().then((config) => {
      if (!config) return;
      if (!isMergeMode && !isParquetPreviewMode && config.asset_excel_source_directory) {
        setSourceDirectory((current) => current || config.asset_excel_source_directory);
      }
      if ((isConvertMode || isParquetPreviewMode) && config.asset_excel_output_directory) {
        setOutputDirectory((current) => current || config.asset_excel_output_directory);
      }
      if (isMergeMode && config.asset_excel_merge_input_directory) {
        setMergeBaseDirectory((current) => current || config.asset_excel_merge_input_directory);
      }
      if (isMergeMode && config.asset_excel_merge_output_directory) {
        setOutputDirectory((current) => current || config.asset_excel_merge_output_directory);
      }
      if (isMergeMode) {
        setMergeSameDirectory(!!config.asset_excel_merge_same_directory);
        setCleanupMergedItems(config.asset_excel_cleanup_merged_items !== false);
        setDuplicateScanRecursive(!!config.asset_excel_duplicate_scan_recursive);
        duplicateScanRecursiveRef.current = !!config.asset_excel_duplicate_scan_recursive;
      }
    });
  }, [fetchSettings, isConvertMode, isMergeMode, isParquetPreviewMode]);

  useEffect(() => {
    const clearDragSelection = () => {
      convertDragSelection.current = null;
      mergeDragSelection.current = null;
    };
    window.addEventListener("mouseup", clearDragSelection);
    return () => window.removeEventListener("mouseup", clearDragSelection);
  }, []);

  useEffect(() => {
    if (!isConvertMode) return;
    let cancelled = false;
    setMappingsLoading(true);
    fetchAssetExcelAccountMappings()
      .then((data) => {
        if (!cancelled) setAccountMappings(data.items || []);
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus(err.message);
        setIsErrorStatus(true);
      })
      .finally(() => {
        if (!cancelled) setMappingsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isConvertMode, setIsErrorStatus, setStatus]);

  useEffect(() => {
    if (isMergeMode || isParquetPreviewMode) {
      setLoading(false);
      return;
    }
    if (!sourceDirectory.trim()) {
      setExcelFiles([]);
      setSelectedPreviewFile("");
      setSelectedSheet("");
      setSheetNames([]);
      setSheetPayload(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchAssetExcelFiles(sourceDirectory)
      .then((data) => {
        if (cancelled) return;
        const files = data.excel_files || [];
        setExcelFiles(files);
        if (isConvertMode) {
          setSelectedConvertFiles((current) => {
            const available = new Set(files.map((file: AssetExcelFile) => file.relative_path));
            const kept = current.filter((fileName) => available.has(fileName));
            return kept.length ? kept : files.map((file: AssetExcelFile) => file.relative_path);
          });
        }
        setSelectedPreviewFile((current) => current && files.some((file: AssetExcelFile) => file.relative_path === current) ? current : files[0]?.relative_path || "");
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus(err.message);
        setIsErrorStatus(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isConvertMode, isMergeMode, isParquetPreviewMode, sourceDirectory, setIsErrorStatus, setStatus]);

  useEffect(() => {
    if (!outputDirectory.trim()) {
      setOutputInfo(null);
      return;
    }
    let cancelled = false;
    setOutputInfo(null);
    fetchAssetExcelOutput(outputDirectory)
      .then((data) => {
        if (!cancelled) setOutputInfo(data);
      })
      .catch(() => {
        if (!cancelled) setOutputInfo(null);
      });
    return () => {
      cancelled = true;
    };
  }, [outputDirectory]);

  useEffect(() => {
    if (!isMergeMode || !mergeBaseDirectory.trim()) {
      setMergeBaseInfo(null);
      return;
    }
    let cancelled = false;
    setMergeBaseInfo(null);
    fetchAssetExcelOutput(mergeBaseDirectory)
      .then((data) => {
        if (!cancelled) setMergeBaseInfo(data);
      })
      .catch(() => {
        if (!cancelled) setMergeBaseInfo(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isMergeMode, mergeBaseDirectory]);

  useEffect(() => {
    if (!selectedPreviewFile || !sourceDirectory.trim()) return;
    let cancelled = false;
    setSelectedSheet("");
    setSheetNames([]);
    setSheetPayload(null);
    setSheetsLoading(true);
    fetchAssetExcelSheets(selectedPreviewFile, sourceDirectory)
      .then((data) => {
        if (cancelled) return;
        setSheetNames(data.sheet_names || []);
      })
      .catch((err) => {
        if (cancelled) return;
        setSheetPayload({ error: err.message, rows: [], columns: [], sheet_names: [] });
      })
      .finally(() => {
        if (!cancelled) setSheetsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedPreviewFile, sourceDirectory]);

  useEffect(() => {
    if (!selectedPreviewFile || !selectedSheet || !sourceDirectory.trim()) {
      sheetBodyRequestToken.current += 1;
      setSheetBodyLoading(false);
      return;
    }
    if (sheetNames.length && !sheetNames.includes(selectedSheet)) {
      sheetBodyRequestToken.current += 1;
      setSheetPayload(null);
      setSheetBodyLoading(false);
      return;
    }
    let cancelled = false;
    const cacheKey = JSON.stringify({ sourceDirectory, selectedPreviewFile, selectedSheet });
    const requestToken = sheetBodyRequestToken.current + 1;
    sheetBodyRequestToken.current = requestToken;
    const cached = sheetPreviewCache.current[cacheKey];
    if (cached) {
      setSheetPayload(cached);
      setSheetBodyLoading(false);
      return;
    }
    setSheetPayload(null);
    setSheetBodyLoading(true);
    fetchAssetExcelSheet({
      fileName: selectedPreviewFile,
      sourceDirectory,
      sheetName: selectedSheet,
      rowLimit: 20,
    })
      .then((data) => {
        if (cancelled || sheetBodyRequestToken.current !== requestToken) return;
        setSheetPayload(data);
        sheetPreviewCache.current[cacheKey] = data;
      })
      .catch((err) => {
        if (cancelled || sheetBodyRequestToken.current !== requestToken) return;
        setSheetPayload({ error: err.message, rows: [], columns: [], sheet_names: [] });
      })
      .finally(() => {
        if (!cancelled && sheetBodyRequestToken.current === requestToken) setSheetBodyLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceDirectory, selectedPreviewFile, selectedSheet, sheetNames]);

  const conflictCount = useMemo(
    () => Object.values(previewData?.conflicts || {}).reduce((sum, items: any) => sum + (Array.isArray(items) ? items.length : 0), 0),
    [previewData],
  );
  const outputRows = useMemo(() => {
    const resultRows = Object.entries(previewData?.outputs || lastResult?.outputs || {}) as [string, any][];
    return resultRows.length ? resultRows : outputRowsFromInfo(outputInfo);
  }, [previewData, lastResult, outputInfo]);
  const mergeBaseOutputRows = useMemo(() => mergeCandidateRowsFromInfo(mergeBaseInfo), [mergeBaseInfo]);
  const sortOutputRows = (rows: [string, any][]) => {
    if (!outputSort) return rows;
    const direction = outputSort.direction === "asc" ? 1 : -1;
    return rows
      .map((row, index) => ({ row, index }))
      .sort((left, right) => {
        const [leftName, leftItem] = left.row as [string, any];
        const [rightName, rightItem] = right.row as [string, any];
        const leftValue = outputSortValue(leftName, leftItem, outputSort.key);
        const rightValue = outputSortValue(rightName, rightItem, outputSort.key);
        if (typeof leftValue === "number" && typeof rightValue === "number") {
          const diff = leftValue - rightValue;
          return diff === 0 ? left.index - right.index : diff * direction;
        }
        const diff = String(leftValue).localeCompare(String(rightValue), "ko", { numeric: true });
        return diff === 0 ? left.index - right.index : diff * direction;
      })
      .map(({ row }) => row);
  };
  const sortedOutputRows = sortOutputRows(outputRows as [string, any][]);
  const sortedMergeBaseOutputRows = sortOutputRows(mergeBaseOutputRows as [string, any][]);
  useEffect(() => {
    if (!isMergeMode) return;
    const availableFiles = new Set(
      mergeBaseOutputRows.map(([name, item]: [string, any]) => outputFileNameFromRow(name, item)),
    );
    setSelectedMergeFiles((current) => current.filter((fileName) => availableFiles.has(fileName)));
  }, [isMergeMode, mergeBaseOutputRows]);
  const skippedRows = previewData?.skipped || lastResult?.skipped || [];
  const duplicateDeletionCandidates = Array.isArray(duplicateInspectionResult?.deletion_candidates) ? duplicateInspectionResult.deletion_candidates : [];
  const duplicateDeletedFiles = Array.isArray(duplicateInspectionResult?.deleted_files) ? duplicateInspectionResult.deleted_files : [];
  const duplicateMismatchedRows = Array.isArray(duplicateInspectionResult?.mismatched_duplicates) ? duplicateInspectionResult.mismatched_duplicates : [];
  const duplicateDeletionCandidateCount = duplicateInspectionResult?.dry_run ? Number(duplicateInspectionResult?.deletion_candidate_count || duplicateDeletionCandidates.length) : 0;
  const duplicateDeletedCount = !duplicateInspectionResult?.dry_run ? Number(duplicateInspectionResult?.deleted_count || duplicateDeletedFiles.length) : 0;
  const duplicateNotificationActive = isMergeMode && !!duplicateInspectionResult;
  const conflictRows = useMemo(
    () => Object.entries(previewData?.conflicts || {}).flatMap(([accountName, items]: [string, any]) =>
      (Array.isArray(items) ? items : []).map((item: any) => ({ accountName, ...item })),
    ),
    [previewData],
  );
  const parquetOptions = useMemo(
    () => {
      const seen = new Set<string>();
      const resultOptions = outputRows.map(([name, item]: [string, any]) => {
        const fileName = outputFileNameFromRow(name, item);
        return {
          key: name,
          fileName,
          label: item?.account_name || fileName || name,
        };
      });
      const existingOptions = (outputInfo?.parquet_files || []).map((fileName: string) => ({
        key: fileName,
        fileName,
        label: fileName,
      }));
      return [...resultOptions, ...existingOptions].filter((item) => {
        if (!item.fileName || !item.fileName.endsWith(".parquet") || seen.has(item.fileName)) return false;
        seen.add(item.fileName);
        return true;
      });
    },
    [outputRows, outputInfo],
  );
  const updatingAccountCount = useMemo(
    () => outputRows.filter(([, item]: [string, any]) => item?.will_update_existing).length,
    [outputRows],
  );
  const selectedConvertFileSet = useMemo(() => new Set(selectedConvertFiles), [selectedConvertFiles]);
  const selectedConvertFileCount = selectedConvertFiles.length;
  const allConvertFilesSelected = excelFiles.length > 0 && selectedConvertFileCount === excelFiles.length;
  const activityStatus = [
    `작업: ${isMergeMode ? "Parquet 병합" : "Excel에서 Parquet 변환"}`,
    isMergeMode ? null : `대상 파일: ${formatInteger(selectedConvertFileCount)} / ${formatInteger(excelFiles.length)}개`,
    `예상 Sheet Parquet: ${formatInteger(Object.keys(previewData?.outputs || {}).length)}개`,
    `기존 출력 업데이트: ${formatInteger(updatingAccountCount)}개`,
    `Skipped / 충돌: ${formatInteger(skippedRows.length)} / ${formatInteger(conflictCount)}`,
    "확인 상태: 실행 시 자동 확인",
    "",
    status || "실행 전",
  ].filter(Boolean).join("\n");
  const previewColumns = sheetPayload?.preview_columns || sheetPayload?.columns || [];
  const sheetRows = sheetPayload?.rows || [];
  const parquetPreviewColumns = parquetPayload?.preview_columns || parquetPayload?.columns || [];
  const parquetRows = parquetPayload?.rows || [];
  const handleOutputSort = (key: OutputSortKey) => {
    setOutputSort((current) => {
      if (!current || current.key !== key) return { key, direction: "asc" };
      return { key, direction: current.direction === "asc" ? "desc" : "asc" };
    });
  };
  const outputSortMarker = (key: OutputSortKey) => outputSort?.key === key ? (outputSort.direction === "asc" ? "↑" : "↓") : "↕";
  const renderOutputHeader = (key: OutputSortKey, label: string, align: "left" | "right" = "left") => (
    <th className={`whitespace-nowrap px-3 py-2 font-medium ${align === "right" ? "text-right" : ""}`} aria-sort={outputSort?.key === key ? (outputSort.direction === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" className={`inline-flex w-full items-center gap-1 hover:text-slate-900 dark:hover:text-slate-100 ${align === "right" ? "justify-end" : ""}`} onClick={() => handleOutputSort(key)}>
        <span>{label}</span>
        <span className="text-[10px] text-slate-400 dark:text-slate-500">{outputSortMarker(key)}</span>
      </button>
    </th>
  );
  const toggleConvertFile = (fileName: string, checked: boolean) => {
    setSelectedConvertFiles((current) => applyFileSelection(current, fileName, checked));
  };
  const beginConvertFileDrag = (event: ReactMouseEvent, fileName: string, selected: boolean) => {
    if (event.button !== 0 || activeJobId) return;
    event.preventDefault();
    const checked = dragSelectionTargetChecked(selected);
    convertDragSelection.current = { checked };
    toggleConvertFile(fileName, checked);
  };
  const continueConvertFileDrag = (fileName: string) => {
    if (!convertDragSelection.current || activeJobId) return;
    toggleConvertFile(fileName, convertDragSelection.current.checked);
  };
  const selectAllConvertFiles = () => {
    setSelectedConvertFiles(excelFiles.map((file) => file.relative_path));
  };
  const clearConvertFiles = () => {
    setSelectedConvertFiles([]);
  };
  const selectedMergeCountsByAccount = useMemo(() => {
    const counts: Record<string, number> = {};
    selectedMergeFiles.forEach((fileName) => {
      const accountName = accountNameFromParquetFile(fileName);
      counts[accountName] = (counts[accountName] || 0) + 1;
    });
    return counts;
  }, [selectedMergeFiles]);
  const incompleteMergeGroups = useMemo(
    () => Object.entries(selectedMergeCountsByAccount).filter(([, count]) => count !== 2),
    [selectedMergeCountsByAccount],
  );
  const incompleteMergeAccountNames = useMemo(
    () => incompleteMergeGroups.map(([accountName]) => accountName),
    [incompleteMergeGroups],
  );
  const mergePairCount = Object.values(selectedMergeCountsByAccount).filter((count) => count === 2).length;
  const mergeSelectionReady = selectedMergeFiles.length > 0 && incompleteMergeGroups.length === 0;
  const toggleMergeFile = (fileName: string, checked: boolean) => {
    setSelectedMergeFiles((current) => {
      const canAdd = (items: readonly string[], candidate: string) => {
        const accountName = accountNameFromParquetFile(candidate);
        const accountCount = items.filter((item) => accountNameFromParquetFile(item) === accountName).length;
        return accountCount < 2;
      };
      return applyFileSelection(current, fileName, checked, canAdd);
    });
  };
  const beginMergeFileDrag = (event: ReactMouseEvent, fileName: string, selected: boolean, disabled: boolean) => {
    if (event.button !== 0 || disabled) return;
    event.preventDefault();
    const checked = dragSelectionTargetChecked(selected);
    mergeDragSelection.current = { checked };
    toggleMergeFile(fileName, checked);
  };
  const continueMergeFileDrag = (fileName: string, disabled: boolean) => {
    if (!mergeDragSelection.current || disabled) return;
    toggleMergeFile(fileName, mergeDragSelection.current.checked);
  };
  const mergeSelectedCount = selectedMergeFiles.length;
  const selectableMergeFiles = useMemo(
    () => selectFirstTwoFilesPerAccount(
      sortedMergeBaseOutputRows.map(([name, item]: [string, any]) => outputFileNameFromRow(name, item)),
      accountNameFromParquetFile,
    ),
    [sortedMergeBaseOutputRows],
  );
  const allMergeFilesSelected = selectableMergeFiles.length > 0
    && mergeSelectedCount === selectableMergeFiles.length
    && selectableMergeFiles.every((fileName) => selectedMergeFiles.includes(fileName));
  const selectAllMergeFiles = () => {
    setSelectedMergeFiles(selectableMergeFiles);
  };
  const clearMergeFiles = () => {
    setSelectedMergeFiles([]);
  };
  const renderOutputRowsTable = (rows: [string, any][], emptyMessage = "표시할 Parquet 결과가 없습니다.", selectable = false) => (
    <div className={htmlTableFrameClassName}>
      <table className="w-max min-w-full select-none text-sm">
        <thead className="sticky top-0 bg-slate-50 dark:bg-[#0d1117]">
          <tr className="text-left text-slate-500 dark:text-slate-400">
            {selectable ? <th className="min-w-16 whitespace-nowrap px-3 py-2 font-medium">선택</th> : null}
            {renderOutputHeader("account_id", "ID")}
            {renderOutputHeader("account_name", "계정")}
            {renderOutputHeader("rows", "행", "right")}
            {renderOutputHeader("columns", "코드", "right")}
            {renderOutputHeader("missing_ratio", "결측률", "right")}
            {renderOutputHeader("non_null_cells", "값 있음", "right")}
            {renderOutputHeader("total_cells", "전체 셀", "right")}
            {renderOutputHeader("date_start", "구간 시작")}
            {renderOutputHeader("date_end", "구간 종료")}
            {renderOutputHeader("sha256", "SHA256")}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
          {rows.map(([name, item]: [string, any]) => {
            const fileName = outputFileNameFromRow(name, item);
            const selected = selectedMergeFiles.includes(fileName);
            const accountName = item?.account_name || accountNameFromParquetFile(fileName);
            const disabled = selectable && !selected && (selectedMergeCountsByAccount[accountName] || 0) >= 2;
            return (
              <tr
                key={name}
                className={selectionRowClassName(selected)}
                onMouseDown={(event) => selectable ? beginMergeFileDrag(event, fileName, selected, disabled) : undefined}
                onMouseEnter={() => selectable ? continueMergeFileDrag(fileName, disabled) : undefined}
              >
                {selectable ? (
                  <td className="px-3 py-2">
                    <Checkbox
                      checked={selected}
                      disabled={disabled}
                      onMouseDown={(event) => event.stopPropagation()}
                      onCheckedChange={(value) => toggleMergeFile(fileName, !!value)}
                      aria-label={`${fileName} 선택`}
                      className="dark:border-[#30363d]"
                    />
                  </td>
                ) : null}
                <td className="whitespace-nowrap px-3 py-2">{item.account_id || "-"}</td>
                <td className="whitespace-nowrap px-3 py-2">{outputAccountNameFromRow(name, item) || "-"}</td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">{formatOutputInteger(item.rows)}</td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">{formatOutputInteger(item.columns)}</td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">{formatPercent(item.quality?.missing_ratio)}</td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">{formatOutputInteger(item.quality?.non_null_cells)}</td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">{formatOutputInteger(item.quality?.total_cells)}</td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums">{outputDateStartText(name, item) || "-"}</td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums">{outputDateEndText(name, item) || "-"}</td>
                <td className="max-w-96 break-all px-3 py-2 font-mono text-xs">{outputSha256Text(name, item) || "-"}</td>
              </tr>
            );
          })}
          {!rows.length ? (
            <tr>
              <td colSpan={selectable ? 11 : 10} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">
                {emptyMessage}
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
  const normalizedAccountMappings = useMemo(
    () => accountMappings.map((mapping) => ({
      account_id: mapping.account_id.trim(),
      account_name: mapping.account_name.trim(),
      sheet_name: mapping.sheet_name.trim(),
    })),
    [accountMappings],
  );
  const accountMappingIssues = useMemo(() => {
    const issues: string[] = [];
    const sheetNames = new Set<string>();
    const accountIds = new Set<string>();
    const accountNames = new Set<string>();
    normalizedAccountMappings.forEach((mapping, index) => {
      const rowLabel = `${index + 1}행`;
      if (!mapping.sheet_name || !mapping.account_id || !mapping.account_name) {
        issues.push(`${rowLabel}: Sheet, ID, 계정을 입력하세요.`);
      }
      if (mapping.account_id.includes("_")) {
        issues.push(`${rowLabel}: ID에는 _를 사용할 수 없습니다.`);
      }
      if (mapping.account_name.includes("_")) {
        issues.push(`${rowLabel}: 계정에는 _를 사용할 수 없습니다.`);
      }
      if (mapping.sheet_name) {
        if (sheetNames.has(mapping.sheet_name)) issues.push(`${rowLabel}: 중복 Sheet입니다.`);
        sheetNames.add(mapping.sheet_name);
      }
      if (mapping.account_id) {
        if (accountIds.has(mapping.account_id)) issues.push(`${rowLabel}: 중복 ID입니다.`);
        accountIds.add(mapping.account_id);
      }
      if (mapping.account_name) {
        if (accountNames.has(mapping.account_name)) issues.push(`${rowLabel}: 중복 계정입니다.`);
        accountNames.add(mapping.account_name);
      }
    });
    return issues;
  }, [normalizedAccountMappings]);

  useEffect(() => {
    if (!isParquetPreviewMode) return;
    if (!parquetOptions.length) {
      setSelectedParquetFile("");
      setParquetPayload(null);
      return;
    }
    if (!selectedParquetFile || !parquetOptions.some((item) => item.fileName === selectedParquetFile)) {
      setSelectedParquetFile(parquetOptions[0].fileName);
    }
  }, [isParquetPreviewMode, parquetOptions, selectedParquetFile]);

  useEffect(() => {
    if (!isParquetPreviewMode || !selectedParquetFile || !outputDirectory.trim()) {
      setParquetPayload(null);
      setParquetLoading(false);
      return;
    }
    let cancelled = false;
    setParquetPayload(null);
    setParquetLoading(true);
    fetchAssetParquetPreview({
      fileName: selectedParquetFile,
      outputDirectory,
      rowLimit: 20,
    })
      .then((data) => {
        if (!cancelled) setParquetPayload(data);
      })
      .catch((err) => {
        if (!cancelled) setParquetPayload({ error: err.message, rows: [], columns: [], sheet_names: [] });
      })
      .finally(() => {
        if (!cancelled) setParquetLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isParquetPreviewMode, selectedParquetFile, outputDirectory]);

  const handlePreviewFileChange = (value: string) => {
    setSelectedPreviewFile(value);
    setSelectedSheet("");
    setSheetNames([]);
    setSheetPayload(null);
    setSheetBodyLoading(false);
  };

  const handleSourceDirectoryChange = (value: string) => {
    setSourceDirectory(value);
    saveSetting("asset_excel_source_directory", value);
    setPreviewData(null);
    setLastResult(null);
    setSelectedConvertFiles([]);
    setSelectedParquetFile("");
    setParquetPayload(null);
    sheetPreviewCache.current = {};
  };

  const handleConvertOutputDirectoryChange = (value: string) => {
    setOutputDirectory(value);
    saveSetting("asset_excel_output_directory", value);
    setPreviewData(null);
    setLastResult(null);
    setOutputInfo(null);
    setSelectedParquetFile("");
    setParquetPayload(null);
  };

  const handleMergeBaseDirectoryChange = (value: string) => {
    setMergeBaseDirectory(value);
    saveSetting("asset_excel_merge_input_directory", value);
    setPreviewData(null);
    setLastResult(null);
    setSelectedMergeFiles([]);
    setDuplicateInspectionResult(null);
    setDuplicateDeleteConfirmed(false);
    setDuplicateDeleteConfirmationText("");
  };

  const handleMergeOutputDirectoryChange = (value: string) => {
    setOutputDirectory(value);
    saveSetting("asset_excel_merge_output_directory", value);
    setPreviewData(null);
    setLastResult(null);
  };

  const handleMergeSameDirectoryChange = (value: boolean) => {
    setMergeSameDirectory(value);
    saveSetting("asset_excel_merge_same_directory", value);
  };

  const handleCleanupMergedItemsChange = (value: boolean) => {
    setCleanupMergedItems(value);
    saveSetting("asset_excel_cleanup_merged_items", value);
  };

  const handleDuplicateScanRecursiveChange = (value: boolean) => {
    duplicateScanRecursiveRef.current = value;
    setDuplicateScanRecursive(value);
    saveSetting("asset_excel_duplicate_scan_recursive", value);
  };

  const handleInspectDuplicates = async () => {
    if (activeJobId) return;
    if (!mergeBaseDirectory.trim()) {
      setStatus("병합 대상 데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    try {
      setStatus("중복 검사 작업을 시작하는 중...");
      setIsErrorStatus(false);
      setDuplicateInspectionResult(null);
      const data = await startAssetParquetDuplicateCleanup({
        target_directory: mergeBaseDirectory,
        dry_run: true,
        scan_recursive: duplicateScanRecursiveRef.current,
      });
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const handleDeleteDuplicateFiles = async () => {
    if (activeJobId) return;
    if (!duplicateDeleteConfirmed || duplicateDeleteConfirmationText.trim() !== "확인했습니다.") {
      setStatus('삭제하려면 삭제 허가를 체크하고 "확인했습니다."를 입력하세요.');
      setIsErrorStatus(true);
      return;
    }
    try {
      setStatus("중복 파일 삭제 작업을 시작하는 중...");
      setIsErrorStatus(false);
      const data = await startAssetParquetDuplicateCleanup({
        target_directory: mergeBaseDirectory,
        dry_run: false,
        delete_confirmed: duplicateDeleteConfirmed,
        delete_confirmation_text: duplicateDeleteConfirmationText,
        scan_recursive: duplicateScanRecursiveRef.current,
      });
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const updateAccountMapping = (index: number, key: keyof AssetAccountMapping, value: string) => {
    setAccountMappings((current) => current.map((mapping, itemIndex) => (
      itemIndex === index ? { ...mapping, [key]: value } : mapping
    )));
  };

  const addAccountMapping = () => {
    setAccountMappings((current) => [
      ...current,
      {
        account_id: nextAccountId(current),
        account_name: "",
        sheet_name: "",
      },
    ]);
  };

  const deleteAccountMapping = (index: number) => {
    setAccountMappings((current) => current.filter((_, itemIndex) => itemIndex !== index));
  };

  const handleAccountMappingEditToggle = async () => {
    if (!isAccountMappingEditing) {
      setIsAccountMappingEditing(true);
      return;
    }
    if (accountMappingIssues.length) {
      setStatus(accountMappingIssues.join("\n"));
      setIsErrorStatus(true);
      return;
    }
    setMappingsSaving(true);
    try {
      await saveAssetExcelAccountMappings(normalizedAccountMappings);
      setAccountMappings(normalizedAccountMappings);
      setIsAccountMappingEditing(false);
      setStatus("계정-ID 매핑을 저장했습니다.");
      setIsErrorStatus(false);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setMappingsSaving(false);
    }
  };

  const handleStart = async (resumeFailedOnly = false) => {
    if (activeJobId) return;
    if (isMergeMode) {
      if (!mergeBaseDirectory.trim()) {
        setStatus("병합 대상 데이터 경로를 선택하세요.");
        setIsErrorStatus(true);
        return;
      }
      if (!mergeSameDirectory && !outputDirectory.trim()) {
        setStatus("병합 결과 데이터 경로를 선택하세요.");
        setIsErrorStatus(true);
        return;
      }
      if (!mergeSelectionReady) {
        setStatus("병합 대상 데이터 경로에서 같은 계정 Parquet 파일을 2개씩 선택하세요.");
        setIsErrorStatus(true);
        return;
      }

      setStatus("병합 작업을 시작하는 중...");
      setIsErrorStatus(false);

      try {
        const data = await startAssetParquetMerge({
          target_directory: mergeBaseDirectory,
          selected_files: selectedMergeFiles,
          output_directory: outputDirectory,
          same_directory: mergeSameDirectory,
          cleanup_merged_items: cleanupMergedItems,
        });
        startPolling(data.job_id);
      } catch (err: any) {
        setStatus(err.message);
        setIsErrorStatus(true);
      }
      return;
    }

    if (!sourceDirectory.trim() || !outputDirectory.trim()) {
      setStatus("데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (!excelFiles.length) {
      setStatus("데이터 경로 아래에 변환할 Excel 파일이 없습니다.");
      setIsErrorStatus(true);
      return;
    }
    if (!selectedConvertFileCount) {
      setStatus("변환 대상 파일을 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (mappingsLoading) {
      setStatus("계정-ID 매핑을 불러오는 중입니다.");
      setIsErrorStatus(true);
      return;
    }
    if (accountMappingIssues.length) {
      setStatus(accountMappingIssues.join("\n"));
      setIsErrorStatus(true);
      return;
    }
    try {
      setStatus("작업을 시작하는 중...");
      setIsErrorStatus(false);

      const data = await startAssetExcelConversion({
        source_directory: sourceDirectory,
        output_directory: outputDirectory,
        write_mode: writeMode,
        selected_files: selectedConvertFiles,
        account_mappings: normalizedAccountMappings,
        resume_failed_only: resumeFailedOnly,
      });
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  return (
    <WorkflowPageShell workflowId="price-data">
      <div className="relative action-dock-host space-y-6 md:grid md:grid-cols-[minmax(0,1fr)_4rem] md:items-start md:gap-x-4">
        <section className="min-w-0 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">데이터 경로</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {!isMergeMode && !isParquetPreviewMode ? (
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">원본 데이터 경로</Label>
                  <PathPickerInput
                    mode="folder"
                    value={sourceDirectory}
                    onChange={handleSourceDirectoryChange}
                    placeholder="/path/to/resources/Quantiwise"
                    onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                  />
                  {isConvertMode ? (
                    <p className="text-xs text-slate-500 dark:text-slate-400">이 경로 아래의 Excel 파일 중 선택한 파일만 실행 대상으로 사용합니다. 대상 파일: {formatInteger(selectedConvertFileCount)} / {formatInteger(excelFiles.length)}개</p>
                  ) : null}
                </div>
              ) : null}

              {isConvertMode || isParquetPreviewMode ? (
                <>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">데이터 경로</Label>
                    <PathPickerInput
                      mode="folder"
                      value={outputDirectory}
                      onChange={handleConvertOutputDirectoryChange}
                      placeholder="/path/to/resources/assets_merged"
                      onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                    />
                  </div>

                </>
              ) : null}

              {isMergeMode ? (
                <>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">병합 대상 데이터 경로</Label>
                    <PathPickerInput
                      mode="folder"
                      value={mergeBaseDirectory}
                      onChange={handleMergeBaseDirectoryChange}
                      placeholder="/path/to/existing/assets_parquet"
                      onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">병합 결과 데이터 경로</Label>
                    <PathPickerInput
                      mode="folder"
                      value={outputDirectory}
                      onChange={handleMergeOutputDirectoryChange}
                      placeholder="/path/to/resources/assets_merged"
                      disabled={mergeSameDirectory}
                      onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                    />
                  </div>
                </>
              ) : null}
            </CardContent>
          </Card>

          {isConvertMode ? (
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base dark:text-white">대상 파일</CardTitle>
                  <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">선택한 Excel 파일만 변환합니다.</p>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={selectAllConvertFiles} disabled={!!activeJobId || loading || allConvertFilesSelected || !excelFiles.length}>
                    전체 선택
                  </Button>
                  <Button variant="outline" size="sm" onClick={clearConvertFiles} disabled={!!activeJobId || loading || !selectedConvertFileCount}>
                    선택 해제
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className={`text-sm ${selectedConvertFileCount ? "text-slate-600 dark:text-slate-300" : "text-amber-600 dark:text-amber-300"}`}>
                선택한 파일: {formatInteger(selectedConvertFileCount)} / {formatInteger(excelFiles.length)}개
              </p>
              <div className={htmlTableFrameClassName}>
                <table className="w-full min-w-[560px] select-none text-sm">
                  <thead className="sticky top-0 bg-slate-50 dark:bg-[#0d1117]">
                    <tr className="text-left text-slate-500 dark:text-slate-400">
                      <th className="min-w-16 whitespace-nowrap px-3 py-2 font-medium">선택</th>
                      <th className="px-3 py-2 font-medium">파일</th>
                      <th className="px-3 py-2 text-right font-medium">크기</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
                    {excelFiles.map((file) => {
                      const selected = selectedConvertFileSet.has(file.relative_path);
                      return (
                        <tr
                          key={file.relative_path}
                          className={selectionRowClassName(selected)}
                          onMouseDown={(event) => beginConvertFileDrag(event, file.relative_path, selected)}
                          onMouseEnter={() => continueConvertFileDrag(file.relative_path)}
                        >
                          <td className="px-3 py-2">
                            <Checkbox
                              checked={selected}
                              disabled={!!activeJobId}
                              onMouseDown={(event) => event.stopPropagation()}
                              onCheckedChange={(value) => toggleConvertFile(file.relative_path, !!value)}
                              aria-label={`${file.relative_path} 선택`}
                              className="dark:border-[#30363d]"
                            />
                          </td>
                          <td className="break-all px-3 py-2">{file.relative_path}</td>
                          <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">{formatBytes(file.size_bytes)}</td>
                        </tr>
                      );
                    })}
                    {!excelFiles.length ? (
                      <tr>
                        <td colSpan={3} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">
                          {loading ? "파일 목록을 불러오는 중..." : "표시할 Excel 파일이 없습니다."}
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
          ) : null}

          {isConvertMode ? (
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base dark:text-white">계정-ID 매핑</CardTitle>
                  <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">변환 실행 시 Sheet 이름을 account_id와 account_name으로 연결합니다.</p>
                </div>
                <div className="flex items-center gap-2">
                  {isAccountMappingEditing ? (
                    <Button variant="outline" size="sm" onClick={addAccountMapping} disabled={mappingsLoading || mappingsSaving || !!activeJobId}>
                      <Plus className="mr-2 h-4 w-4" />
                      추가
                    </Button>
                  ) : null}
                  <Button
                    variant={isAccountMappingEditing ? "default" : "outline"}
                    size="sm"
                    onClick={handleAccountMappingEditToggle}
                    disabled={mappingsLoading || mappingsSaving || !!activeJobId}
                  >
                    {mappingsSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : isAccountMappingEditing ? <Check className="mr-2 h-4 w-4" /> : <Pencil className="mr-2 h-4 w-4" />}
                    {mappingsSaving ? "저장 중" : isAccountMappingEditing ? "완료" : "편집"}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className={htmlTableFrameClassName}>
                <table className="w-full min-w-[620px] table-fixed text-sm">
                  <thead className="sticky top-0 bg-slate-50 dark:bg-[#0d1117]">
                    <tr className="text-left text-slate-500 dark:text-slate-400">
                      <th className="px-3 py-2 font-medium">Sheet</th>
                      <th className="px-3 py-2 font-medium">ID</th>
                      <th className="px-3 py-2 font-medium">계정</th>
                      {isAccountMappingEditing ? <th className="px-3 py-2 font-medium text-right">삭제</th> : null}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
                    {accountMappings.map((mapping, index) => (
                      <tr key={index} className="dark:text-slate-300">
                        <td className="px-3 py-2">
                          {isAccountMappingEditing ? (
                            <Input
                              value={mapping.sheet_name}
                              onChange={(event) => updateAccountMapping(index, "sheet_name", event.target.value)}
                              aria-label="Sheet"
                              disabled={!!activeJobId}
                              className="h-9 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                            />
                          ) : (
                            <span className="block py-2">{mapping.sheet_name || "-"}</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {isAccountMappingEditing ? (
                            <Input
                              value={mapping.account_id}
                              onChange={(event) => updateAccountMapping(index, "account_id", event.target.value)}
                              aria-label="ID"
                              disabled={!!activeJobId}
                              className="h-9 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                            />
                          ) : (
                            <span className="block py-2">{mapping.account_id || "-"}</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {isAccountMappingEditing ? (
                            <Input
                              value={mapping.account_name}
                              onChange={(event) => updateAccountMapping(index, "account_name", event.target.value)}
                              aria-label="계정"
                              disabled={!!activeJobId}
                              className="h-9 dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                            />
                          ) : (
                            <span className="block py-2">{mapping.account_name || "-"}</span>
                          )}
                        </td>
                        {isAccountMappingEditing ? (
                          <td className="px-3 py-2 text-right">
                            <Button variant="ghost" size="icon" onClick={() => deleteAccountMapping(index)} disabled={!!activeJobId} title="삭제">
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </td>
                        ) : null}
                      </tr>
                    ))}
                    {!accountMappings.length ? (
                      <tr>
                        <td colSpan={isAccountMappingEditing ? 4 : 3} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">
                          {mappingsLoading ? "매핑을 불러오는 중..." : "매핑 없음"}
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
              {accountMappingIssues.length ? (
                <div className="whitespace-pre-wrap rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
                  {accountMappingIssues.slice(0, 5).join("\n")}
                  {accountMappingIssues.length > 5 ? `\n외 ${accountMappingIssues.length - 5}개` : ""}
                </div>
              ) : null}
            </CardContent>
          </Card>
          ) : null}

          {!isConvertMode && !isParquetPreviewMode && !isMergeMode ? (
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base dark:text-white">
                <Eye className="h-4 w-4" />
                Sheet 읽기/미리보기
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">파일</Label>
                  <Select value={selectedPreviewFile} onValueChange={handlePreviewFileChange}>
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                      <SelectValue placeholder="파일 선택" />
                    </SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      {excelFiles.map((file) => <SelectItem key={file.relative_path} value={file.relative_path}>{file.relative_path}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">Sheet</Label>
                  <Select value={selectedSheet} onValueChange={setSelectedSheet} disabled={!selectedPreviewFile || sheetsLoading || sheetNames.length === 0}>
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                      <SelectValue placeholder={sheetsLoading ? "Sheet 목록 로딩 중" : "Sheet 선택"} />
                    </SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      {sheetNames.map((name: string) => <SelectItem key={name} value={name}>{name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                {sheetPayload?.account_name ? (
                  <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
                    <span>계정: {sheetPayload.account_name}</span>
                    <span>상태: {sheetStatusLabel(sheetPayload.status)}</span>
                    <span>행: {formatInteger(sheetPayload.row_count ?? sheetPayload.preview_row_count)}</span>
                    {sheetPayload.date_start && sheetPayload.date_end ? <span>{sheetPayload.date_start} ~ {sheetPayload.date_end}</span> : null}
                  </div>
                ) : null}
                {sheetPayload?.metadata?.period_from || sheetPayload?.metadata?.period_to ? (
                  <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
                    <span>Period(From): {sheetPayload.metadata.period_from || "-"}</span>
                    <span>Period(To): {sheetPayload.metadata.period_to || "-"}</span>
                    <span>행: {formatInteger(sheetPayload.row_count ?? sheetPayload.preview_row_count)}</span>
                  </div>
                ) : null}
              </div>

              {(sheetPayload?.columns || []).length > 12 ? (
                <p className="text-xs text-slate-500 dark:text-slate-400">미리보기는 앞 12개 컬럼만 표시합니다. 전체 컬럼: {formatInteger(sheetPayload?.columns?.length)}개</p>
              ) : null}

              <div className={htmlTableFrameClassName}>
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-slate-50 dark:bg-[#0d1117]">
                    <tr className="text-left text-slate-500 dark:text-slate-400">
                      {previewColumns.slice(0, 12).map((column: string) => <th key={column} className="px-3 py-2 font-medium">{column}</th>)}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
                    {sheetRows.map((row: any, index: number) => (
                      <tr key={index} className="dark:text-slate-300">
                        {previewColumns.slice(0, 12).map((column: string) => <td key={column} className="px-3 py-2 whitespace-nowrap">{String(row[column] ?? "")}</td>)}
                      </tr>
                    ))}
                    {sheetPayload?.error ? (
                      <tr><td colSpan={Math.max(1, previewColumns.length)} className="px-3 py-6 text-red-600 dark:text-red-300">{sheetPayload.error}</td></tr>
                    ) : null}
                    {!sheetPayload?.error && sheetBodyLoading ? (
                      <tr><td colSpan={Math.max(1, previewColumns.length)} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">본문을 불러오는 중...</td></tr>
                    ) : null}
                    {!sheetPayload?.error && !sheetBodyLoading && !selectedSheet ? (
                      <tr><td colSpan={Math.max(1, previewColumns.length)} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">Sheet를 선택하세요.</td></tr>
                    ) : null}
                    {!sheetPayload?.error && !sheetBodyLoading && selectedSheet && !sheetRows.length ? (
                      <tr><td colSpan={Math.max(1, previewColumns.length)} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">표시할 행 없음</td></tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
          ) : null}

          {isConvertMode ? (
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <Button className="w-full" onClick={() => handleStart(false)} disabled={!!activeJobId || loading || mappingsLoading || !sourceDirectory.trim() || !outputDirectory.trim() || !excelFiles.length || !selectedConvertFileCount}>
                  {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                <Button variant="outline" className="w-full" onClick={() => handleStart(true)} disabled={!!activeJobId || loading || mappingsLoading || !sourceDirectory.trim() || !outputDirectory.trim() || !excelFiles.length || !selectedConvertFileCount}>
                  {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실패분 이어서 실행
                </Button>
                <Button variant="outline" className="w-full" onClick={cancelJob} disabled={!activeJobId}>
                  {UI_TEXT.actions.cancelJob}
                </Button>
              </div>
              {previewData?.sheets?.length ? (
                <div className={htmlTableFrameClassName}>
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-slate-50 dark:bg-[#0d1117]">
                      <tr className="text-left text-slate-500 dark:text-slate-400">
                        <th className="px-3 py-2 font-medium">파일</th>
                        <th className="px-3 py-2 font-medium">Sheet</th>
                        <th className="px-3 py-2 font-medium">상태</th>
                        <th className="px-3 py-2 font-medium">계정</th>
                        <th className="px-3 py-2 font-medium">날짜</th>
                        <th className="px-3 py-2 font-medium text-right">코드</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
                      {(previewData?.sheets || []).map((sheet: any, index: number) => (
                        <tr key={`${sheet.file_name}-${sheet.sheet_name}-${index}`} className="dark:text-slate-300">
                          <td className="px-3 py-2 break-all">{sheet.relative_path || sheet.file_name}</td>
                          <td className="px-3 py-2">{sheet.sheet_name}</td>
                          <td className="px-3 py-2">{sheetStatusLabel(sheet.status)}</td>
                          <td className="px-3 py-2">{sheet.account_name || sheet.reason || "-"}</td>
                          <td className="px-3 py-2 tabular-nums">{sheet.date_start && sheet.date_end ? `${sheet.date_start} ~ ${sheet.date_end}` : "-"}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{formatInteger(sheet.columns)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}

              {skippedRows.length ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-sm font-medium text-amber-800 dark:text-amber-200">
                    <AlertTriangle className="h-4 w-4" />
                    건너뛴 Sheet
                  </div>
                  <div className="max-h-56 overflow-auto rounded-md border border-amber-200 dark:border-amber-900/50">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-amber-50 dark:bg-amber-950/30">
                        <tr className="text-left text-amber-900 dark:text-amber-200">
                          <th className="px-3 py-2 font-medium">파일</th>
                          <th className="px-3 py-2 font-medium">Sheet</th>
                          <th className="px-3 py-2 font-medium">이유</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-amber-100 dark:divide-amber-900/40">
                        {skippedRows.map((item: any, index: number) => (
                          <tr key={`${item.file_name}-${item.sheet_name}-${index}`} className="dark:text-slate-300">
                            <td className="px-3 py-2 break-all">{item.relative_path || item.file_name}</td>
                            <td className="px-3 py-2">{item.sheet_name}</td>
                            <td className="px-3 py-2">{item.reason || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}

              {conflictRows.length ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-sm font-medium text-red-700 dark:text-red-300">
                    <AlertTriangle className="h-4 w-4" />
                    값 충돌 상세
                  </div>
                  <div className="max-h-64 overflow-auto rounded-md border border-red-200 dark:border-red-900/50">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-red-50 dark:bg-red-950/30">
                        <tr className="text-left text-red-800 dark:text-red-200">
                          <th className="px-3 py-2 font-medium">계정</th>
                          <th className="px-3 py-2 font-medium">날짜</th>
                          <th className="px-3 py-2 font-medium">코드</th>
                          <th className="px-3 py-2 font-medium">기존 값</th>
                          <th className="px-3 py-2 font-medium">새 값</th>
                          <th className="px-3 py-2 font-medium">원천</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-red-100 dark:divide-red-900/40">
                        {conflictRows.map((item: any, index: number) => (
                          <tr key={`${item.accountName}-${item.date}-${item.code}-${index}`} className="dark:text-slate-300">
                            <td className="px-3 py-2 font-medium">{item.accountName}</td>
                            <td className="px-3 py-2 tabular-nums">{item.date || "-"}</td>
                            <td className="px-3 py-2">{item.code || "-"}</td>
                            <td className="px-3 py-2">{item.existing_value || item.message || "-"}</td>
                            <td className="px-3 py-2">{item.incoming_value || "-"}</td>
                            <td className="px-3 py-2 break-all">{item.incoming_file ? `${item.incoming_file} / ${item.incoming_sheet || ""}` : "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>
          ) : null}

          {isParquetPreviewMode ? (
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base dark:text-white">
                <Eye className="h-4 w-4" />
                Parquet 미리보기
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">파일</Label>
                  <Select value={selectedParquetFile} onValueChange={setSelectedParquetFile} disabled={!parquetOptions.length}>
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                      <SelectValue placeholder="파일 선택" />
                    </SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      {parquetOptions.map((item) => (
                        <SelectItem key={`${item.key}-${item.fileName}`} value={item.fileName}>{item.fileName}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {(parquetPayload?.columns || []).length > 12 ? (
                <p className="text-xs text-slate-500 dark:text-slate-400">미리보기는 앞 12개 컬럼만 표시합니다. 전체 컬럼: {formatInteger(parquetPayload?.columns?.length)}개</p>
              ) : null}

              <div className={htmlTableFrameClassName}>
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-slate-50 dark:bg-[#0d1117]">
                    <tr className="text-left text-slate-500 dark:text-slate-400">
                      {parquetPreviewColumns.slice(0, 12).map((column: string) => <th key={column} className="px-3 py-2 font-medium">{column}</th>)}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
                    {parquetRows.map((row: any, index: number) => (
                      <tr key={index} className="dark:text-slate-300">
                        {parquetPreviewColumns.slice(0, 12).map((column: string) => <td key={column} className="px-3 py-2 whitespace-nowrap">{String(row[column] ?? "")}</td>)}
                      </tr>
                    ))}
                    {parquetPayload?.error ? (
                      <tr><td colSpan={Math.max(1, parquetPreviewColumns.length)} className="px-3 py-6 text-red-600 dark:text-red-300">{parquetPayload.error}</td></tr>
                    ) : null}
                    {!parquetPayload?.error && parquetLoading ? (
                      <tr><td colSpan={Math.max(1, parquetPreviewColumns.length)} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">본문을 불러오는 중...</td></tr>
                    ) : null}
                    {!parquetPayload?.error && !parquetLoading && !selectedParquetFile ? (
                      <tr><td colSpan={Math.max(1, parquetPreviewColumns.length)} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">Parquet 파일을 선택하세요.</td></tr>
                    ) : null}
                    {!parquetPayload?.error && !parquetLoading && selectedParquetFile && !parquetRows.length ? (
                      <tr><td colSpan={Math.max(1, parquetPreviewColumns.length)} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">표시할 행 없음</td></tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
          ) : null}

          {isMergeMode ? (
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="flex items-center gap-2 text-base dark:text-white">
                  <Eye className="h-4 w-4" />
                  병합대상 모아보기
                </CardTitle>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={selectAllMergeFiles} disabled={!!activeJobId || loading || allMergeFilesSelected || !mergeBaseOutputRows.length}>
                    전체 선택
                  </Button>
                  <Button variant="outline" size="sm" onClick={clearMergeFiles} disabled={!!activeJobId || loading || !mergeSelectedCount}>
                    선택 해제
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className={`text-sm ${mergeSelectionReady ? "text-emerald-600 dark:text-emerald-300" : "text-slate-500 dark:text-slate-400"}`}>
                {formatMergeSelectionSummary(formatInteger(mergeSelectedCount), formatInteger(mergePairCount), incompleteMergeAccountNames)}
              </p>
              <div className="space-y-2">
                {renderOutputRowsTable(sortedMergeBaseOutputRows, "병합 대상 데이터 경로에 표시할 병합 대상이 없습니다.", true)}
              </div>
            </CardContent>
          </Card>
          ) : null}

          {isMergeMode ? (
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <Button variant="outline" className="w-full" onClick={handleInspectDuplicates} disabled={!!activeJobId || loading || !mergeBaseDirectory.trim()}>
                  {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}
                  중복 검사하기
                </Button>
                <Button className="w-full" onClick={() => handleStart(false)} disabled={!!activeJobId || loading || !mergeBaseDirectory.trim() || (!mergeSameDirectory && !outputDirectory.trim()) || !mergeSelectionReady}>
                  {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                <Button variant="outline" className="w-full" onClick={cancelJob} disabled={!activeJobId}>
                  {UI_TEXT.actions.cancelJob}
                </Button>
              </div>
            </CardContent>
          </Card>
          ) : null}

          {isParquetPreviewMode ? (
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base dark:text-white">
                <Eye className="h-4 w-4" />
                Parquet 모아보기
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {renderOutputRowsTable(sortedOutputRows)}
            </CardContent>
          </Card>
          ) : null}
        </section>

        {isConvertMode || isMergeMode ? (
        <ActionDock
          activityActive={!!activeJobId}
          activityContent={
            <JobStatusLogger
              status={activityStatus}
              isErrorStatus={isErrorStatus}
              isCancellable={!!activeJobId}
              onCancel={cancelJob}
            />
          }
          notificationActive={isErrorStatus || skippedRows.length > 0 || conflictCount > 0 || duplicateNotificationActive}
          notificationContent={
            <div className="space-y-3">
              {isErrorStatus ? (
                <div className="whitespace-pre-wrap text-sm text-red-600 dark:text-red-300">{status || "오류 내용을 확인할 수 없습니다."}</div>
              ) : duplicateNotificationActive ? (
                <div className="space-y-4">
                  {duplicateDeletionCandidateCount > 0 ? (
                    <div className="space-y-3 border-b border-slate-200 pb-4 dark:border-[#30363d]">
                      <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
                        삭제 예정 파일 {formatInteger(duplicateDeletionCandidateCount)}개
                      </div>
                      <div className="max-h-40 overflow-auto rounded-md border border-slate-200 dark:border-[#30363d]">
                        <table className="w-full text-xs">
                          <thead className="sticky top-0 bg-slate-50 dark:bg-[#0d1117]">
                            <tr className="text-left text-slate-500 dark:text-slate-400">
                              <th className="px-3 py-2 font-medium">삭제 예정 파일</th>
                              <th className="px-3 py-2 font-medium">기준 파일</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
                            {duplicateDeletionCandidates.slice(0, 20).map((item: any, index: number) => (
                              <tr key={`${item.path}-${index}`} className="dark:text-slate-300">
                                <td className="break-all px-3 py-2">{item.file_name || "-"}</td>
                                <td className="break-all px-3 py-2">{item.canonical_file || "-"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <div className="flex items-center space-x-2">
                        <Checkbox id="assetDuplicateDeleteConfirmed" checked={duplicateDeleteConfirmed} onCheckedChange={(value) => setDuplicateDeleteConfirmed(!!value)} className="dark:border-[#30363d]" />
                        <Label htmlFor="assetDuplicateDeleteConfirmed" className="cursor-pointer text-sm dark:text-slate-300">삭제 허가</Label>
                      </div>
                      <div className="space-y-2">
                        <Label className="dark:text-slate-300">확인 문구</Label>
                        <Input
                          value={duplicateDeleteConfirmationText}
                          onChange={(event) => setDuplicateDeleteConfirmationText(event.target.value)}
                          placeholder="확인했습니다."
                          className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200"
                        />
                      </div>
                      <Button
                        variant="outline"
                        className="w-full"
                        onClick={handleDeleteDuplicateFiles}
                        disabled={
                          !!activeJobId ||
                          !duplicateDeleteConfirmed ||
                          duplicateDeleteConfirmationText.trim() !== "확인했습니다."
                        }
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        삭제 예정 파일 {formatInteger(duplicateDeletionCandidateCount)}개 삭제
                      </Button>
                    </div>
                  ) : null}
                  {duplicateDeletedCount > 0 ? (
                    <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900 dark:border-emerald-900/40 dark:bg-emerald-900/20 dark:text-emerald-200">
                      중복 파일 {formatInteger(duplicateDeletedCount)}개를 삭제했습니다.
                    </div>
                  ) : null}
                  {duplicateDeletionCandidateCount === 0 && duplicateDeletedCount === 0 && duplicateMismatchedRows.length === 0 ? (
                    <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-300">
                      삭제 후보 없음
                    </div>
                  ) : null}
                  {duplicateMismatchedRows.length > 0 ? (
                    <div className="space-y-2 rounded-md border border-slate-200 p-3 text-sm text-slate-700 dark:border-[#30363d] dark:text-slate-300">
                      <div className="font-medium">내용이 달라 삭제하지 않은 파일 {formatInteger(duplicateMismatchedRows.length)}개</div>
                      <div className="max-h-32 overflow-auto whitespace-pre-wrap text-xs">
                        {duplicateMismatchedRows.slice(0, 20).map((item: any) => `${item.file_name} - ${item.reason}`).join("\n")}
                      </div>
                    </div>
                  ) : null}
                  <div className="space-y-2 border-t border-slate-200 pt-4 dark:border-[#30363d]">
                    <Label className="dark:text-slate-300">중복 검사 결과</Label>
                    <pre className="max-h-72 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 dark:border-slate-700 dark:bg-[#090d12] dark:text-blue-100">
                      {JSON.stringify(duplicateInspectionResult, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : skippedRows.length > 0 || conflictCount > 0 ? (
                <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
                  <div className="font-medium">확인 필요</div>
                  <div>건너뛴 Sheet {formatInteger(skippedRows.length)}개, 값 충돌 {formatInteger(conflictCount)}개가 있습니다.</div>
                </div>
              ) : (
                <div className="text-sm text-slate-500 dark:text-slate-400">알림 없음</div>
              )}
            </div>
          }
          settingsTitle="시스템 설정"
          settingsContent={
            isMergeMode ? (
              <div className="space-y-4">
                <label className="flex items-center gap-3 text-sm text-slate-700 dark:text-slate-200">
                  <Checkbox
                    checked={mergeSameDirectory}
                    onCheckedChange={(value) => handleMergeSameDirectoryChange(!!value)}
                    className="dark:border-[#30363d]"
                  />
                  동일 폴더에서 작업하기
                </label>
                <label className="flex items-center gap-3 text-sm text-slate-700 dark:text-slate-200">
                  <Checkbox
                    checked={cleanupMergedItems}
                    onCheckedChange={(value) => handleCleanupMergedItemsChange(!!value)}
                    className="dark:border-[#30363d]"
                  />
                  병합된 요소 정리하기
                </label>
                <label className="flex items-center gap-3 text-sm text-slate-700 dark:text-slate-200">
                  <Checkbox
                    checked={duplicateScanRecursive}
                    onCheckedChange={(value) => handleDuplicateScanRecursiveChange(!!value)}
                    className="dark:border-[#30363d]"
                  />
                  내부까지 검사
                </label>
              </div>
            ) : <div />
          }
        />
        ) : null}
      </div>
    </WorkflowPageShell>
  );
}
