"use client"

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Eye, Loader2, Play } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { useJobPolling } from "@/hooks/useJobPolling";
import { ActionDock } from "@/components/ui/ActionDock";
import { UI_TEXT } from "@/config/uiText";
import { formatInteger } from "@/lib/format";
import {
  fetchAssetExcelFiles,
  fetchAssetExcelOutput,
  fetchAssetParquetPreview,
  fetchAssetExcelSheets,
  fetchAssetExcelSheet,
  startAssetExcelConversion,
  startAssetParquetMerge,
} from "./api";
import type { AssetExcelFile, PreviewData, SheetPayload } from "./types";

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
    lines.push(
      "",
      "변환 완료",
      `Sheet Parquet: ${formatInteger(data.result.sheets_processed ?? Object.keys(data.result.outputs || {}).length)}개`,
      `계정: ${formatInteger(data.result.accounts_processed)}개`,
      `건너뛴 Sheet: ${formatInteger(data.result.skipped?.length)}개`,
      `데이터 경로: ${data.result.output_directory || ""}`,
    );
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

export default function AssetExcelUtilityPage({ mode = "preview" }: { mode?: "preview" | "convert" | "merge" }) {
  const isConvertMode = mode === "convert";
  const isMergeMode = mode === "merge";
  const pageTitle = isConvertMode ? "Quantiwise - 변환하기" : isMergeMode ? "Quantiwise - 병합하기" : "Quantiwise - 미리보기";
  const pageDescription = isConvertMode ? "Quantiwise 엑셀 데이터를 Parquet으로 변환하는 기능" : isMergeMode ? "생성된 Quantiwise Parquet을 병합하는 기능" : "Quantiwise 엑셀 미리보기 기능";
  const [excelFiles, setExcelFiles] = useState<AssetExcelFile[]>([]);
  const [sourceDirectory, setSourceDirectory] = useState("");
  const [outputDirectory, setOutputDirectory] = useState("");
  const [mergeBaseDirectory, setMergeBaseDirectory] = useState("");
  const [mergeIncomingDirectory, setMergeIncomingDirectory] = useState("");
  const writeMode = "replace";
  const [loading, setLoading] = useState(true);
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [outputInfo, setOutputInfo] = useState<any>(null);
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
  const sheetPreviewCache = useRef<Record<string, SheetPayload>>({});
  const sheetBodyRequestToken = useRef(0);

  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus, cancelJob } = useJobPolling({
    pollingEndpoint: "/api/assets/excels/jobs/{jobId}",
    cancelEndpoint: "/api/assets/excels/cancel",
    formatStatus: jobStatusLines,
    onSuccess: (result) => {
      setLastResult(result);
      setPreviewData(null);
      setParquetPayload(null);
      if (result?.output_directory) setOutputDirectory(result.output_directory);
      const firstOutput = Object.values(result?.outputs || {}).find((item: any) => item?.output_file || item?.path) as any;
      setSelectedParquetFile(firstOutput?.output_file || fileNameFromPath(firstOutput?.path));
    },
  });

  useEffect(() => {
    if (isMergeMode) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    fetchAssetExcelFiles(sourceDirectory || undefined)
      .then((data) => {
        if (cancelled) return;
        const files = data.excel_files || [];
        setSourceDirectory((current) => current || data.root_directory || "");
        setExcelFiles(files);
        setSelectedPreviewFile((current) => current && files.some((file: AssetExcelFile) => file.relative_path === current) ? current : files[0]?.relative_path || "");
        setOutputDirectory((current) => current || data.default_output_directory || "");
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
  }, [isMergeMode, sourceDirectory, setIsErrorStatus, setStatus]);

  useEffect(() => {
    if (!outputDirectory.trim()) return;
    let cancelled = false;
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
    if (!selectedPreviewFile) return;
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
    if (!selectedPreviewFile || !selectedSheet) {
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
    const cacheKey = JSON.stringify({ selectedPreviewFile, selectedSheet });
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
  }, [selectedPreviewFile, selectedSheet, sheetNames]);

  const conflictCount = useMemo(
    () => Object.values(previewData?.conflicts || {}).reduce((sum, items: any) => sum + (Array.isArray(items) ? items.length : 0), 0),
    [previewData],
  );
  const outputRows = useMemo(() => Object.entries(previewData?.outputs || lastResult?.outputs || {}), [previewData, lastResult]);
  const skippedRows = previewData?.skipped || [];
  const conflictRows = useMemo(
    () => Object.entries(previewData?.conflicts || {}).flatMap(([accountName, items]: [string, any]) =>
      (Array.isArray(items) ? items : []).map((item: any) => ({ accountName, ...item })),
    ),
    [previewData],
  );
  const parquetOptions = useMemo(
    () => outputRows
      .map(([name, item]: [string, any]) => {
        const fileName = item?.output_file || fileNameFromPath(item?.path) || `${name}.parquet`;
        return {
          key: name,
          fileName,
          label: item?.sheet_name || item?.account_name || name,
        };
      })
      .filter((item) => item.fileName && item.fileName.endsWith(".parquet")),
    [outputRows],
  );
  const updatingAccountCount = useMemo(
    () => outputRows.filter(([, item]: [string, any]) => item?.will_update_existing).length,
    [outputRows],
  );
  const activityStatus = [
    `작업: ${isMergeMode ? "Parquet 병합" : "Excel에서 Parquet 변환"}`,
    isMergeMode ? null : `대상 파일: ${formatInteger(excelFiles.length)}개`,
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

  useEffect(() => {
    if (!isConvertMode) return;
    if (!parquetOptions.length) {
      setSelectedParquetFile("");
      setParquetPayload(null);
      return;
    }
    if (!selectedParquetFile || !parquetOptions.some((item) => item.fileName === selectedParquetFile)) {
      setSelectedParquetFile(parquetOptions[0].fileName);
    }
  }, [isConvertMode, parquetOptions, selectedParquetFile]);

  useEffect(() => {
    if (!isConvertMode || !selectedParquetFile || !outputDirectory.trim()) {
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
  }, [isConvertMode, selectedParquetFile, outputDirectory]);

  const handlePreviewFileChange = (value: string) => {
    setSelectedPreviewFile(value);
    setSelectedSheet("");
    setSheetNames([]);
    setSheetPayload(null);
    setSheetBodyLoading(false);
  };

  const handleStart = async () => {
    if (activeJobId) return;
    if (isMergeMode) {
      if (!mergeBaseDirectory.trim() || !mergeIncomingDirectory.trim() || !outputDirectory.trim()) {
        setStatus("데이터 경로를 선택하세요.");
        setIsErrorStatus(true);
        return;
      }

      setStatus("병합 작업을 시작하는 중...");
      setIsErrorStatus(false);

      try {
        const data = await startAssetParquetMerge({
          base_directory: mergeBaseDirectory,
          incoming_directory: mergeIncomingDirectory,
          output_directory: outputDirectory,
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
    try {
      setStatus("작업을 시작하는 중...");
      setIsErrorStatus(false);

      const data = await startAssetExcelConversion({
        source_directory: sourceDirectory,
        output_directory: outputDirectory,
        write_mode: writeMode,
      });
      startPolling(data.job_id);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    }
  };

  const activeOutputInfo = previewData?.output || outputInfo;
  const outputExists = Boolean(activeOutputInfo?.manifest_exists || activeOutputInfo?.parquet_files?.length);

  return (
    <WorkflowPageShell workflowId="utility">
      <div className="relative space-y-6">
        <section className="min-w-0 space-y-6">
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Quantiwise</p>
              <CardTitle className="text-xl dark:text-white">{pageTitle}</CardTitle>
              <p className="text-sm text-slate-500 dark:text-slate-400">{pageDescription}</p>
            </CardHeader>
            <CardContent className="pt-6 space-y-5">
              {!isMergeMode ? (
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">원본 데이터 경로</Label>
                  <PathPickerInput
                    mode="folder"
                    value={sourceDirectory}
                    onChange={(value) => {
                      setSourceDirectory(value);
                      setPreviewData(null);
                      setLastResult(null);
                      setSelectedParquetFile("");
                      setParquetPayload(null);
                      sheetPreviewCache.current = {};
                    }}
                    placeholder="/path/to/resources/Quantiwise"
                    onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                  />
                  {isConvertMode ? (
                    <p className="text-xs text-slate-500 dark:text-slate-400">이 경로 아래의 모든 Excel 파일을 실행 대상으로 사용합니다. 대상 파일: {formatInteger(excelFiles.length)}개</p>
                  ) : null}
                </div>
              ) : null}

              {isConvertMode ? (
                <>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">데이터 경로</Label>
                    <PathPickerInput
                      mode="folder"
                      value={outputDirectory}
                      onChange={(value) => {
                        setOutputDirectory(value);
                        setPreviewData(null);
                        setLastResult(null);
                        setSelectedParquetFile("");
                        setParquetPayload(null);
                      }}
                      placeholder="/path/to/resources/assets_merged"
                      onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                    />
                  </div>

                  {outputExists ? (
                    <div className="flex items-start gap-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      <div>
                        <p className="font-medium">기존 결과가 감지되었습니다.</p>
                        <p>변환하기는 기존 Parquet를 병합에 쓰지 않고 원본 데이터 경로 아래 전체 Excel에서 나온 Sheet Parquet만 저장합니다.</p>
                        <p>기존 결과와 합치려면 `Quantiwise - 병합하기`를 사용하세요.</p>
                        <p>기존 Parquet: {formatInteger(activeOutputInfo?.account_count || activeOutputInfo?.parquet_files?.length)}개</p>
                      </div>
                    </div>
                  ) : null}
                </>
              ) : null}

              {isMergeMode ? (
                <>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">기존 Parquet 경로</Label>
                    <PathPickerInput
                      mode="folder"
                      value={mergeBaseDirectory}
                      onChange={setMergeBaseDirectory}
                      placeholder="/path/to/existing/assets_parquet"
                      onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">병합할 Parquet 경로</Label>
                    <PathPickerInput
                      mode="folder"
                      value={mergeIncomingDirectory}
                      onChange={setMergeIncomingDirectory}
                      placeholder="/path/to/new/assets_parquet"
                      onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="dark:text-slate-300">데이터 경로</Label>
                    <PathPickerInput
                      mode="folder"
                      value={outputDirectory}
                      onChange={setOutputDirectory}
                      placeholder="/path/to/resources/assets_merged"
                      onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                    />
                  </div>
                </>
              ) : null}
            </CardContent>
          </Card>

          {!isConvertMode && !isMergeMode ? (
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

              <div className="max-h-80 overflow-auto rounded-md border border-slate-200 dark:border-[#30363d]">
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
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Run</p>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <Button className="w-full" onClick={handleStart} disabled={!!activeJobId || loading || !excelFiles.length}>
                  {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  실행
                </Button>
                <Button variant="outline" className="w-full" onClick={cancelJob} disabled={!activeJobId}>
                  {UI_TEXT.actions.cancelJob}
                </Button>
              </div>
              {parquetOptions.length ? (
                <div className="space-y-4 border-t border-slate-200 pt-4 dark:border-[#30363d]">
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="dark:text-slate-300">실행 결과</Label>
                      <Select value={selectedParquetFile} onValueChange={setSelectedParquetFile}>
                        <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                          <SelectValue placeholder="Parquet 선택" />
                        </SelectTrigger>
                        <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                          {parquetOptions.map((item) => (
                            <SelectItem key={`${item.key}-${item.fileName}`} value={item.fileName}>
                              {item.label} · {item.fileName}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {parquetPayload?.account_name ? (
                      <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
                        <span>계정: {parquetPayload.account_name}</span>
                        <span>상태: {sheetStatusLabel(parquetPayload.status)}</span>
                        <span>행: {formatInteger(parquetPayload.row_count ?? parquetPayload.preview_row_count)}</span>
                        {parquetPayload.date_start && parquetPayload.date_end ? <span>{parquetPayload.date_start} ~ {parquetPayload.date_end}</span> : null}
                      </div>
                    ) : null}
                    {parquetPayload?.metadata?.period_from || parquetPayload?.metadata?.period_to ? (
                      <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
                        <span>Period(From): {parquetPayload.metadata.period_from || "-"}</span>
                        <span>Period(To): {parquetPayload.metadata.period_to || "-"}</span>
                        <span>행: {formatInteger(parquetPayload.row_count ?? parquetPayload.preview_row_count)}</span>
                      </div>
                    ) : null}
                  </div>

                  {(parquetPayload?.columns || []).length > 12 ? (
                    <p className="text-xs text-slate-500 dark:text-slate-400">미리보기는 앞 12개 컬럼만 표시합니다. 전체 컬럼: {formatInteger(parquetPayload?.columns?.length)}개</p>
                  ) : null}

                  <div className="max-h-80 overflow-auto rounded-md border border-slate-200 dark:border-[#30363d]">
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
                        {!parquetPayload?.error && !parquetLoading && selectedParquetFile && !parquetRows.length ? (
                          <tr><td colSpan={Math.max(1, parquetPreviewColumns.length)} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">표시할 행 없음</td></tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
              {previewData?.sheets?.length ? (
                <div className="max-h-80 overflow-auto rounded-md border border-slate-200 dark:border-[#30363d]">
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

          {isMergeMode ? (
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Run</p>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <Button className="w-full" onClick={handleStart} disabled={!!activeJobId || loading}>
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

          {outputRows.length ? (
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="text-base dark:text-white">결과 탐색</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="max-h-80 overflow-auto rounded-md border border-slate-200 dark:border-[#30363d]">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-slate-50 dark:bg-[#0d1117]">
                    <tr className="text-left text-slate-500 dark:text-slate-400">
                      <th className="px-3 py-2 font-medium">Sheet</th>
                      <th className="px-3 py-2 font-medium">ID</th>
                      <th className="px-3 py-2 font-medium">계정</th>
                      <th className="px-3 py-2 font-medium">파일</th>
                      <th className="px-3 py-2 font-medium text-right">행</th>
                      <th className="px-3 py-2 font-medium text-right">코드</th>
                      <th className="px-3 py-2 font-medium text-right">결측률</th>
                      <th className="px-3 py-2 font-medium">구간</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
                    {outputRows.map(([name, item]: [string, any]) => (
                      <tr key={name} className="dark:text-slate-300">
                        <td className="px-3 py-2 font-medium">{item.sheet_name || name}</td>
                        <td className="px-3 py-2">{item.account_id || "-"}</td>
                        <td className="px-3 py-2">{item.account_name || "-"}</td>
                        <td className="px-3 py-2 break-all">{item.path || item.output_file || `${name}.parquet`}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatInteger(item.rows)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatInteger(item.columns)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatPercent(item.quality?.missing_ratio)}</td>
                        <td className="px-3 py-2">{(item.date_segments || []).map((segment: any) => `${segment.start}~${segment.end}`).join(", ") || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="rounded-md border border-slate-200 p-3 text-xs dark:border-[#30363d] dark:text-slate-300">
                <p className="mb-2 font-medium text-slate-900 dark:text-slate-100">최근 샘플</p>
                <div className="space-y-2">
                  {outputRows.slice(0, 3).map(([name, item]: [string, any]) => (
                    <div key={name} className="break-all">
                      <span className="font-medium">{item.sheet_name || name}</span>
                      <span className="ml-2 text-slate-500 dark:text-slate-400">
                        {(item.quality?.sample_rows || []).map((row: any) => JSON.stringify(row)).join(" / ") || "샘플 없음"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
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
          notificationActive={isErrorStatus || skippedRows.length > 0 || conflictCount > 0}
          notificationContent={
            <div className="space-y-3">
              {isErrorStatus ? (
                <div className="whitespace-pre-wrap text-sm text-red-600 dark:text-red-300">{status || "오류 내용을 확인할 수 없습니다."}</div>
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
            <div className="space-y-2 text-sm text-slate-600 dark:text-slate-400">
              <p>{isMergeMode ? "병합은 두 Parquet 경로를 읽어 데이터 경로에 새 결과를 저장합니다." : "변환하기는 Excel을 Parquet으로 생성합니다. 기존 Parquet와 합치는 작업은 병합하기에서 실행합니다."}</p>
            </div>
          }
        />
        ) : null}
      </div>
    </WorkflowPageShell>
  );
}
