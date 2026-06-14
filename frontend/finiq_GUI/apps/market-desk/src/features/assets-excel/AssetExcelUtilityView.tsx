"use client"

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Eye, Loader2, Play, RefreshCw } from "lucide-react";
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
  fetchAssetExcelSheets,
  fetchAssetExcelSheet,
  previewAssetExcelConversion,
  startAssetExcelConversion,
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
  if (data.progress_log?.length) lines.push("", "최근 로그:", ...data.progress_log.slice(-12));
  if (data.status === "completed" && data.result) {
    lines.push(
      "",
      "변환 완료",
      `계정 파일: ${formatInteger(data.result.accounts_processed)}개`,
      `업데이트 계정: ${formatInteger(data.result.updated_accounts?.length)}개`,
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

export default function AssetExcelUtilityPage({ mode = "preview" }: { mode?: "preview" | "save" }) {
  const isSaveMode = mode === "save";
  const pageTitle = isSaveMode ? "Quantiwise - 저장하기" : "Quantiwise - 미리보기";
  const pageDescription = isSaveMode ? "Quantiwise 엑셀 데이터 파싱해서 저장하기 기능" : "Quantiwise 엑셀 미리보기 기능";
  const [excelFiles, setExcelFiles] = useState<AssetExcelFile[]>([]);
  const [sourceDirectory, setSourceDirectory] = useState("");
  const [outputDirectory, setOutputDirectory] = useState("");
  const [writeMode, setWriteMode] = useState("update");
  const [loading, setLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [previewSignature, setPreviewSignature] = useState("");
  const [outputInfo, setOutputInfo] = useState<any>(null);
  const [lastResult, setLastResult] = useState<any>(null);
  const [selectedPreviewFile, setSelectedPreviewFile] = useState("");
  const [selectedSheet, setSelectedSheet] = useState("");
  const [sheetNames, setSheetNames] = useState<string[]>([]);
  const [sheetsLoading, setSheetsLoading] = useState(false);
  const [sheetBodyLoading, setSheetBodyLoading] = useState(false);
  const [sheetPayload, setSheetPayload] = useState<SheetPayload | null>(null);
  const sheetPreviewCache = useRef<Record<string, SheetPayload>>({});
  const sheetBodyRequestToken = useRef(0);

  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus, cancelJob } = useJobPolling({
    pollingEndpoint: "/api/assets/excels/jobs/{jobId}",
    cancelEndpoint: "/api/assets/excels/cancel",
    formatStatus: jobStatusLines,
    onSuccess: (result) => {
      setLastResult(result);
      setPreviewData(null);
    },
  });

  useEffect(() => {
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
  }, [sourceDirectory, setIsErrorStatus, setStatus]);

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
  const accountRows = useMemo(() => Object.entries(previewData?.accounts || lastResult?.accounts || {}), [previewData, lastResult]);
  const currentPreviewSignature = useMemo(
    () => JSON.stringify({ sourceDirectory, outputDirectory, writeMode }),
    [sourceDirectory, outputDirectory, writeMode],
  );
  const previewIsCurrent = Boolean(previewData && previewSignature === currentPreviewSignature);
  const skippedRows = previewData?.skipped || [];
  const conflictRows = useMemo(
    () => Object.entries(previewData?.conflicts || {}).flatMap(([accountName, items]: [string, any]) =>
      (Array.isArray(items) ? items : []).map((item: any) => ({ accountName, ...item })),
    ),
    [previewData],
  );
  const updatingAccountCount = useMemo(
    () => accountRows.filter(([, item]: [string, any]) => item?.will_update_existing).length,
    [accountRows],
  );
  const previewColumns = sheetPayload?.preview_columns || sheetPayload?.columns || [];
  const sheetRows = sheetPayload?.rows || [];

  const handlePreviewFileChange = (value: string) => {
    setSelectedPreviewFile(value);
    setSelectedSheet("");
    setSheetNames([]);
    setSheetPayload(null);
    setSheetBodyLoading(false);
  };

  const handlePreview = async () => {
    if (!sourceDirectory.trim()) {
      setStatus("데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (!outputDirectory.trim()) {
      setStatus("데이터 경로를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (!excelFiles.length) {
      setStatus("데이터 경로 아래에 변환할 Excel 파일이 없습니다.");
      setIsErrorStatus(true);
      return;
    }
    setPreviewLoading(true);
    setStatus("사전 점검 중...");
    setIsErrorStatus(false);
    try {
      const data = await previewAssetExcelConversion({
        source_directory: sourceDirectory,
        output_directory: outputDirectory,
        write_mode: writeMode,
      });
      setPreviewData(data);
      setPreviewSignature(currentPreviewSignature);
      setStatus(`사전 점검 완료\n계정: ${formatInteger(Object.keys(data.accounts || {}).length)}개\n정상 Sheet: ${formatInteger((data.sheets || []).filter((sheet: any) => sheet.status === "mapped").length)}개\n충돌: ${formatInteger(Object.keys(data.conflicts || {}).length)}개 계정`);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleStart = async () => {
    if (activeJobId) return;
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
    if (!previewIsCurrent) {
      setStatus("현재 선택/옵션으로 사전 점검을 먼저 실행하세요.");
      setIsErrorStatus(true);
      return;
    }

    setStatus("작업을 시작하는 중...");
    setIsErrorStatus(false);

    try {
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
              <div className="space-y-2">
                <Label className="dark:text-slate-300">원본 데이터 경로</Label>
                <PathPickerInput
                  mode="folder"
                  value={sourceDirectory}
                  onChange={(value) => {
                    setSourceDirectory(value);
                    setPreviewData(null);
                    setLastResult(null);
                    sheetPreviewCache.current = {};
                  }}
                  placeholder="/path/to/resources/Quantiwise"
                  onError={(err) => { setStatus(err.message); setIsErrorStatus(true); }}
                />
                {isSaveMode ? (
                  <p className="text-xs text-slate-500 dark:text-slate-400">이 경로 아래의 모든 Excel 파일을 실행 대상으로 사용합니다. 대상 파일: {formatInteger(excelFiles.length)}개</p>
                ) : null}
              </div>

              {isSaveMode ? (
                <>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="dark:text-slate-300">저장 방식</Label>
                      <Select value={writeMode} onValueChange={setWriteMode}>
                        <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                          <SelectItem value="update">기존 결과와 병합</SelectItem>
                          <SelectItem value="replace">전체 파일 다시 저장(기존 미병합)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
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

                  {outputExists ? (
                    <div className="flex items-start gap-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      <div>
                        <p className="font-medium">기존 결과가 감지되었습니다.</p>
                        <p>{writeMode === "update" ? "기존 Parquet를 읽어 새 Excel 데이터와 병합합니다." : "기존 Parquet는 병합에 쓰지 않고 원본 데이터 경로 아래 전체 Excel에서 나온 계정 파일만 저장합니다."}</p>
                        <p>{writeMode === "update" ? "원본 데이터 경로에 없는 기존 계정도 기존 출력에서 함께 유지됩니다." : "다시 생성된 계정 파일만 덮어쓰며, 원본 데이터 경로에 없는 기존 Parquet는 삭제하지 않습니다."}</p>
                        <p>기존 계정 파일: {formatInteger(activeOutputInfo?.account_count || activeOutputInfo?.parquet_files?.length)}개</p>
                      </div>
                    </div>
                  ) : null}
                </>
              ) : null}
            </CardContent>
          </Card>

          {!isSaveMode ? (
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

          {isSaveMode ? (
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="text-base dark:text-white">Quantiwise - 저장하기</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={handlePreview} disabled={previewLoading || !!activeJobId}>
                  {previewLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                  사전 점검
                </Button>
                <Button onClick={handleStart} disabled={!!activeJobId || loading || !excelFiles.length || !previewIsCurrent}>
                  {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  Quantiwise 변환
                </Button>
                <Button variant="outline" onClick={cancelJob} disabled={!activeJobId}>
                  {UI_TEXT.actions.cancelJob}
                </Button>
                {previewIsCurrent ? (
                  <div className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-300">
                    <CheckCircle2 className="h-4 w-4" />
                    현재 선택/옵션 점검 완료
                  </div>
                ) : previewData ? (
                  <div className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-300">
                    <AlertTriangle className="h-4 w-4" />
                    선택 또는 옵션이 바뀌었습니다. 다시 점검하세요.
                  </div>
                ) : null}
              </div>

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

          {accountRows.length ? (
          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="text-base dark:text-white">결과 탐색</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="max-h-80 overflow-auto rounded-md border border-slate-200 dark:border-[#30363d]">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-slate-50 dark:bg-[#0d1117]">
                    <tr className="text-left text-slate-500 dark:text-slate-400">
                      <th className="px-3 py-2 font-medium">계정</th>
                      <th className="px-3 py-2 font-medium">파일</th>
                      <th className="px-3 py-2 font-medium text-right">행</th>
                      <th className="px-3 py-2 font-medium text-right">코드</th>
                      <th className="px-3 py-2 font-medium text-right">결측률</th>
                      <th className="px-3 py-2 font-medium">구간</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
                    {accountRows.map(([name, item]: [string, any]) => (
                      <tr key={name} className="dark:text-slate-300">
                        <td className="px-3 py-2 font-medium">{name}</td>
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
                  {accountRows.slice(0, 3).map(([name, item]: [string, any]) => (
                    <div key={name} className="break-all">
                      <span className="font-medium">{name}</span>
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

        {isSaveMode ? (
        <ActionDock
          activityActive={!!activeJobId}
          activityContent={
            <>
              <div className="space-y-3 rounded-md border border-slate-200 p-3 text-sm dark:border-[#30363d]">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-500 dark:text-slate-400">대상 파일</span>
                  <span className="font-medium text-slate-900 dark:text-slate-100">{formatInteger(excelFiles.length)}개</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-500 dark:text-slate-400">예상 계정</span>
                  <span className="font-medium text-slate-900 dark:text-slate-100">{formatInteger(Object.keys(previewData?.accounts || {}).length)}개</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-500 dark:text-slate-400">업데이트 계정</span>
                  <span className="font-medium text-slate-900 dark:text-slate-100">{formatInteger(updatingAccountCount)}개</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-500 dark:text-slate-400">Skipped / 충돌</span>
                  <span className="font-medium text-slate-900 dark:text-slate-100">{formatInteger(skippedRows.length)} / {formatInteger(conflictCount)}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-500 dark:text-slate-400">실행 영향</span>
                  <span className="text-right font-medium text-slate-900 dark:text-slate-100">{writeMode === "update" ? "기존 포함 병합" : "선택 계정 재저장"}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-500 dark:text-slate-400">점검 상태</span>
                  <span className={previewIsCurrent ? "font-medium text-emerald-700 dark:text-emerald-300" : "font-medium text-amber-700 dark:text-amber-300"}>
                    {previewIsCurrent ? "완료" : "필요"}
                  </span>
                </div>
              </div>
              <JobStatusLogger
                status={status}
                isErrorStatus={isErrorStatus}
                isCancellable={!!activeJobId}
                onCancel={cancelJob}
              />
            </>
          }
          notificationActive={isErrorStatus || !!previewData || !!lastResult}
          notificationContent={<JobStatusLogger status={status || "알림 없음"} isErrorStatus={isErrorStatus} />}
          settingsTitle="시스템 설정"
          settingsContent={
            <div className="space-y-2 text-sm text-slate-600 dark:text-slate-400">
              <p>원본 데이터 경로, 데이터 경로, 저장 방식은 본문에서 바로 조작합니다.</p>
            </div>
          }
        />
        ) : null}
      </div>
    </WorkflowPageShell>
  );
}
