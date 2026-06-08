"use client"

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Eye, FileSpreadsheet, Loader2, Play, RefreshCw } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, Checkbox, Input, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@finiq/ui";
import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { JobStatusLogger } from "@/components/ui/JobStatusLogger";
import { PathPickerInput } from "@/components/ui/PathPickerInput";
import { useJobPolling } from "@/hooks/useJobPolling";
import { ActionDock } from "@/components/ui/ActionDock";
import {
  fetchAssetExcelFiles,
  fetchAssetExcelOutput,
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
  const statusLabel = data.status === "completed" ? "완료" : data.status === "failed" ? "실패" : data.status === "running" ? "실행 중" : "대기 중";
  const lines = [`작업 상태: ${statusLabel}`];
  if (data.error) lines.push(`오류: ${data.error}`);
  if (data.progress_log?.length) lines.push("", "최근 로그:", ...data.progress_log.slice(-12));
  if (data.status === "completed" && data.result) {
    lines.push(
      "",
      "변환 완료",
      `계정 파일: ${data.result.accounts_processed || 0}개`,
      `업데이트 계정: ${data.result.updated_accounts?.length || 0}개`,
      `건너뛴 Sheet: ${data.result.skipped?.length || 0}개`,
      `저장 경로: ${data.result.output_directory || ""}`,
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

export default function AssetExcelUtilityPage() {
  const [assetsRoot, setAssetsRoot] = useState("");
  const [excelFiles, setExcelFiles] = useState<AssetExcelFile[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [outputDirectory, setOutputDirectory] = useState("");
  const [conflictPolicy, setConflictPolicy] = useState("error");
  const [writeMode, setWriteMode] = useState("update");
  const [loading, setLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [previewSignature, setPreviewSignature] = useState("");
  const [outputInfo, setOutputInfo] = useState<any>(null);
  const [lastResult, setLastResult] = useState<any>(null);
  const [selectedPreviewFile, setSelectedPreviewFile] = useState("");
  const [selectedSheet, setSelectedSheet] = useState("");
  const [sheetPayload, setSheetPayload] = useState<SheetPayload | null>(null);
  const [sheetPreviewMode, setSheetPreviewMode] = useState<"raw" | "interpreted">("raw");
  const sheetPreviewCache = useRef<Record<string, SheetPayload>>({});
  const [filterText, setFilterText] = useState("");

  const { status, isErrorStatus, activeJobId, startPolling, setStatus, setIsErrorStatus } = useJobPolling({
    pollingEndpoint: "/api/assets/excels/jobs/{jobId}",
    formatStatus: jobStatusLines,
    onSuccess: (result) => {
      setLastResult(result);
      setPreviewData(null);
    },
  });

  useEffect(() => {
    let cancelled = false;
    fetchAssetExcelFiles()
      .then((data) => {
        if (cancelled) return;
        const files = data.excel_files || [];
        setAssetsRoot(data.root_directory || "");
        setExcelFiles(files);
        setSelectedFiles(files.map((file: AssetExcelFile) => file.relative_path));
        setSelectedPreviewFile(files[0]?.relative_path || "");
        setOutputDirectory((current) => current || `${data.root_directory || ""}/../resources/assets_merged`);
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
  }, [setIsErrorStatus, setStatus]);

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
    if (sheetPreviewMode === "interpreted" && !selectedSheet) return;
    let cancelled = false;
    const cacheKey = JSON.stringify({ selectedPreviewFile, selectedSheet, sheetPreviewMode });
    const cached = sheetPreviewCache.current[cacheKey];
    if (cached) {
      setSheetPayload(cached);
      if (!selectedSheet) setSelectedSheet(cached.sheet_name || cached.sheet_names?.[0] || "");
      return;
    }
    fetchAssetExcelSheet({
      fileName: selectedPreviewFile,
      sheetName: selectedSheet || undefined,
      interpreted: sheetPreviewMode === "interpreted",
      rowLimit: 20,
    })
      .then((data) => {
        if (cancelled) return;
        setSheetPayload(data);
        sheetPreviewCache.current[cacheKey] = data;
        if (!selectedSheet) setSelectedSheet(data.sheet_name || data.sheet_names?.[0] || "");
      })
      .catch((err) => {
        if (cancelled) return;
        setSheetPayload({ error: err.message, rows: [], columns: [], sheet_names: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [selectedPreviewFile, selectedSheet, sheetPreviewMode]);

  const selectedSet = useMemo(() => new Set(selectedFiles), [selectedFiles]);
  const visibleFiles = useMemo(
    () => excelFiles.filter((file) => file.relative_path.toLowerCase().includes(filterText.toLowerCase())),
    [excelFiles, filterText],
  );
  const totalSize = useMemo(
    () => excelFiles.reduce((sum, file) => sum + (file.size_bytes || 0), 0),
    [excelFiles],
  );
  const selectedSize = useMemo(
    () => excelFiles.filter((file) => selectedSet.has(file.relative_path)).reduce((sum, file) => sum + (file.size_bytes || 0), 0),
    [excelFiles, selectedSet],
  );
  const conflictCount = useMemo(
    () => Object.values(previewData?.conflicts || {}).reduce((sum, items: any) => sum + (Array.isArray(items) ? items.length : 0), 0),
    [previewData],
  );
  const accountRows = useMemo(() => Object.entries(previewData?.accounts || lastResult?.accounts || {}), [previewData, lastResult]);
  const currentPreviewSignature = useMemo(
    () => JSON.stringify({ outputDirectory, selectedFiles, conflictPolicy, writeMode }),
    [outputDirectory, selectedFiles, conflictPolicy, writeMode],
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
  const sheetStatusCounts = useMemo(() => {
    const counts = { mapped: 0, unmapped: 0, format_error: 0, conflict_accounts: 0 };
    (previewData?.sheets || []).forEach((sheet: any) => {
      if (sheet.status === "mapped") counts.mapped += 1;
      else if (sheet.status === "format_error") counts.format_error += 1;
      else counts.unmapped += 1;
    });
    counts.conflict_accounts = Object.keys(previewData?.conflicts || {}).length;
    return counts;
  }, [previewData]);
  const selectedPreviewFileIsSelected = selectedPreviewFile ? selectedSet.has(selectedPreviewFile) : true;
  const previewColumns = sheetPayload?.preview_columns || sheetPayload?.columns || [];
  const sheetRows = sheetPayload?.rows || [];

  const toggleFile = (relativePath: string) => {
    setSelectedFiles((current) => current.includes(relativePath) ? current.filter((item) => item !== relativePath) : [...current, relativePath]);
  };

  const handlePreview = async () => {
    if (!outputDirectory.trim()) {
      setStatus("저장 폴더를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (!selectedFiles.length) {
      setStatus("변환할 파일을 하나 이상 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    setPreviewLoading(true);
    setStatus("사전 점검 중...");
    setIsErrorStatus(false);
    try {
      const data = await previewAssetExcelConversion({
        output_directory: outputDirectory,
        selected_files: selectedFiles,
        conflict_policy: conflictPolicy,
        write_mode: writeMode,
      });
      setPreviewData(data);
      setPreviewSignature(currentPreviewSignature);
      setStatus(`사전 점검 완료\n계정: ${Object.keys(data.accounts || {}).length}개\n정상 Sheet: ${(data.sheets || []).filter((sheet: any) => sheet.status === "mapped").length}개\n충돌: ${Object.keys(data.conflicts || {}).length}개 계정`);
    } catch (err: any) {
      setStatus(err.message);
      setIsErrorStatus(true);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleStart = async () => {
    if (activeJobId) return;
    if (!outputDirectory.trim()) {
      setStatus("저장 폴더를 선택하세요.");
      setIsErrorStatus(true);
      return;
    }
    if (!selectedFiles.length) {
      setStatus("변환할 파일을 하나 이상 선택하세요.");
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
        output_directory: outputDirectory,
        selected_files: selectedFiles,
        conflict_policy: conflictPolicy,
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
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">Assets Excel</p>
              <CardTitle className="text-xl dark:text-white">자산 엑셀 변환</CardTitle>
            </CardHeader>
            <CardContent className="pt-6 space-y-5">
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">저장 방식</Label>
                  <Select value={writeMode} onValueChange={setWriteMode}>
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      <SelectItem value="update">기존 결과와 병합 업데이트</SelectItem>
                      <SelectItem value="replace">선택 파일만 저장(기존 미병합)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label className="dark:text-slate-300">값 충돌 정책</Label>
                  <Select value={conflictPolicy} onValueChange={setConflictPolicy}>
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      <SelectItem value="error">충돌 시 중단</SelectItem>
                      <SelectItem value="prefer_latest">뒤쪽 파일 우선</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label className="dark:text-slate-300">저장 폴더</Label>
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
                    <p>{writeMode === "update" ? "기존 Parquet를 읽어 새 Excel 데이터와 병합합니다." : "기존 Parquet는 병합에 쓰지 않고 선택 파일에서 나온 계정 파일만 저장합니다."}</p>
                    <p>{writeMode === "update" ? "선택 파일에 없는 기존 계정도 기존 출력에서 함께 유지됩니다." : "선택 파일에서 다시 생성된 계정 파일만 덮어쓰며, 선택 파일에 없는 기존 Parquet는 삭제하지 않습니다."}</p>
                    <p>기존 계정 파일: {activeOutputInfo?.account_count || activeOutputInfo?.parquet_files?.length || 0}개</p>
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base dark:text-white">
                <FileSpreadsheet className="h-4 w-4" />
                파일 선택
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid md:grid-cols-4 gap-3 text-sm">
                <div className="rounded-md border border-slate-200 p-3 dark:border-[#30363d]">
                  <p className="text-slate-500 dark:text-slate-400">Assets</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100 break-all">{assetsRoot || "-"}</p>
                </div>
                <div className="rounded-md border border-slate-200 p-3 dark:border-[#30363d]">
                  <p className="text-slate-500 dark:text-slate-400">전체 파일</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100">{loading ? "-" : excelFiles.length}</p>
                </div>
                <div className="rounded-md border border-slate-200 p-3 dark:border-[#30363d]">
                  <p className="text-slate-500 dark:text-slate-400">선택 파일</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100">{selectedFiles.length}</p>
                </div>
                <div className="rounded-md border border-slate-200 p-3 dark:border-[#30363d]">
                  <p className="text-slate-500 dark:text-slate-400">선택 크기</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100">{formatBytes(selectedSize)} / {formatBytes(totalSize)}</p>
                </div>
              </div>

              <div className="flex flex-col gap-3 md:flex-row md:items-center">
                <Input value={filterText} onChange={(event) => setFilterText(event.target.value)} placeholder="파일명 필터" className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200" />
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => setSelectedFiles(excelFiles.map((file) => file.relative_path))}>전체 선택</Button>
                  <Button variant="outline" onClick={() => setSelectedFiles([])}>전체 해제</Button>
                  {filterText.trim() ? (
                    <>
                      <Button variant="outline" onClick={() => setSelectedFiles(Array.from(new Set([...selectedFiles, ...visibleFiles.map((file) => file.relative_path)])))}>필터 선택</Button>
                      <Button variant="outline" onClick={() => setSelectedFiles(selectedFiles.filter((path) => !visibleFiles.some((file) => file.relative_path === path)))}>필터 해제</Button>
                    </>
                  ) : null}
                </div>
              </div>

              <div className="max-h-72 overflow-auto rounded-md border border-slate-200 dark:border-[#30363d]">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-slate-50 dark:bg-[#0d1117]">
                    <tr className="text-left text-slate-500 dark:text-slate-400">
                      <th className="w-10 px-3 py-2 font-medium"></th>
                      <th className="px-3 py-2 font-medium">파일</th>
                      <th className="px-3 py-2 font-medium text-right">크기</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-[#30363d]">
                    {visibleFiles.map((file) => (
                      <tr key={file.relative_path} className="dark:text-slate-300">
                        <td className="px-3 py-2">
                          <Checkbox checked={selectedSet.has(file.relative_path)} onCheckedChange={() => toggleFile(file.relative_path)} />
                        </td>
                        <td className="px-3 py-2 break-all">{file.relative_path}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatBytes(file.size_bytes)}</td>
                      </tr>
                    ))}
                    {!loading && visibleFiles.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">표시할 엑셀 파일 없음</td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

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
                  <Select value={selectedPreviewFile} onValueChange={(value) => { setSelectedPreviewFile(value); setSelectedSheet(""); }}>
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                      <SelectValue placeholder="파일 선택" />
                    </SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      {excelFiles.map((file) => <SelectItem key={file.relative_path} value={file.relative_path}>{file.relative_path}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  {!selectedPreviewFileIsSelected ? (
                    <p className="text-xs text-amber-700 dark:text-amber-300">이 파일은 현재 변환 선택에서 제외되어 있습니다.</p>
                  ) : null}
                </div>
                <div className="space-y-2">
                  <Label className="dark:text-slate-300">Sheet</Label>
                  <Select value={selectedSheet} onValueChange={setSelectedSheet}>
                    <SelectTrigger className="dark:bg-[#0d1117] dark:border-[#30363d] dark:text-slate-200">
                      <SelectValue placeholder="Sheet 선택" />
                    </SelectTrigger>
                    <SelectContent className="dark:bg-[#161b22] dark:border-[#30363d] dark:text-slate-200">
                      {(sheetPayload?.sheet_names || []).map((name: string) => <SelectItem key={name} value={name}>{name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button variant={sheetPreviewMode === "raw" ? "default" : "outline"} size="sm" onClick={() => setSheetPreviewMode("raw")}>원본</Button>
                <Button variant={sheetPreviewMode === "interpreted" ? "default" : "outline"} size="sm" onClick={() => setSheetPreviewMode("interpreted")} disabled={!selectedSheet}>변환 해석</Button>
                {sheetPayload?.account_name ? (
                  <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
                    <span>계정: {sheetPayload.account_name}</span>
                    <span>상태: {sheetStatusLabel(sheetPayload.status)}</span>
                    <span>행: {sheetPayload.row_count ?? sheetPayload.preview_row_count ?? 0}</span>
                    {sheetPayload.date_start && sheetPayload.date_end ? <span>{sheetPayload.date_start} ~ {sheetPayload.date_end}</span> : null}
                  </div>
                ) : null}
              </div>

              {(sheetPayload?.columns || []).length > 12 ? (
                <p className="text-xs text-slate-500 dark:text-slate-400">미리보기는 앞 12개 컬럼만 표시합니다. 전체 컬럼: {sheetPayload?.columns?.length}개</p>
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
                    {!sheetPayload?.error && !sheetRows.length ? (
                      <tr><td colSpan={Math.max(1, previewColumns.length)} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">표시할 행 없음</td></tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="text-base dark:text-white">Sheet/계정 매핑 미리보기</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Button variant="outline" onClick={handlePreview} disabled={previewLoading || !!activeJobId}>
                  {previewLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                  사전 점검
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

              <div className="grid md:grid-cols-5 gap-3 text-sm">
                <div className="rounded-md border border-slate-200 p-3 dark:border-[#30363d]">
                  <p className="text-slate-500 dark:text-slate-400">계정</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100">{Object.keys(previewData?.accounts || {}).length}</p>
                </div>
                <div className="rounded-md border border-slate-200 p-3 dark:border-[#30363d]">
                  <p className="text-slate-500 dark:text-slate-400">정상 Sheet</p>
                  <p className="font-medium text-emerald-700 dark:text-emerald-300">{sheetStatusCounts.mapped}</p>
                </div>
                <div className="rounded-md border border-slate-200 p-3 dark:border-[#30363d]">
                  <p className="text-slate-500 dark:text-slate-400">미매핑</p>
                  <p className="font-medium text-amber-700 dark:text-amber-300">{sheetStatusCounts.unmapped}</p>
                </div>
                <div className="rounded-md border border-slate-200 p-3 dark:border-[#30363d]">
                  <p className="text-slate-500 dark:text-slate-400">형식 오류</p>
                  <p className="font-medium text-red-700 dark:text-red-300">{sheetStatusCounts.format_error}</p>
                </div>
                <div className="rounded-md border border-slate-200 p-3 dark:border-[#30363d]">
                  <p className="text-slate-500 dark:text-slate-400">충돌 샘플</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100">{conflictCount}</p>
                </div>
              </div>

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
                        <td className="px-3 py-2 text-right tabular-nums">{sheet.columns || 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

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
                        <td className="px-3 py-2 text-right tabular-nums">{item.rows || 0}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{item.columns || 0}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatPercent(item.quality?.missing_ratio)}</td>
                        <td className="px-3 py-2">{(item.date_segments || []).map((segment: any) => `${segment.start}~${segment.end}`).join(", ") || "-"}</td>
                      </tr>
                    ))}
                    {!accountRows.length ? (
                      <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-500 dark:text-slate-400">사전 점검 또는 변환 완료 후 결과가 표시됩니다.</td></tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
              {accountRows.length ? (
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
              ) : null}
            </CardContent>
          </Card>

          <Card className="dark:bg-[#161b22] dark:border-[#30363d]">
            <CardHeader>
              <CardTitle className="dark:text-white">작업 실행</CardTitle>
            </CardHeader>
            <CardContent>
              <Button onClick={handleStart} disabled={!!activeJobId || loading || !selectedFiles.length || !previewIsCurrent} className="w-full md:w-auto">
                {activeJobId ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                자산 엑셀 변환
              </Button>
            </CardContent>
          </Card>
        </section>

        <ActionDock
          activityActive={!!activeJobId}
          activityContent={
            <>
              <div className="space-y-3 rounded-md border border-slate-200 p-3 text-sm dark:border-[#30363d]">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-500 dark:text-slate-400">선택 파일</span>
                  <span className="font-medium text-slate-900 dark:text-slate-100">{selectedFiles.length}개</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-500 dark:text-slate-400">예상 계정</span>
                  <span className="font-medium text-slate-900 dark:text-slate-100">{Object.keys(previewData?.accounts || {}).length}개</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-500 dark:text-slate-400">업데이트 계정</span>
                  <span className="font-medium text-slate-900 dark:text-slate-100">{updatingAccountCount}개</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-500 dark:text-slate-400">Skipped / 충돌</span>
                  <span className="font-medium text-slate-900 dark:text-slate-100">{skippedRows.length} / {conflictCount}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-500 dark:text-slate-400">실행 영향</span>
                  <span className="text-right font-medium text-slate-900 dark:text-slate-100">{writeMode === "update" ? "기존 포함 병합" : "선택 계정 재저장"}</span>
                </div>
                {conflictPolicy === "prefer_latest" ? (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200">
                    충돌 시 날짜 시작이 뒤쪽인 파일 값이 우선 적용됩니다.
                  </div>
                ) : null}
                <div className="flex items-center justify-between gap-3">
                  <span className="text-slate-500 dark:text-slate-400">점검 상태</span>
                  <span className={previewIsCurrent ? "font-medium text-emerald-700 dark:text-emerald-300" : "font-medium text-amber-700 dark:text-amber-300"}>
                    {previewIsCurrent ? "완료" : "필요"}
                  </span>
                </div>
              </div>
              <JobStatusLogger status={status} isErrorStatus={isErrorStatus} />
            </>
          }
          notificationActive={isErrorStatus || !!previewData || !!lastResult}
          notificationContent={<JobStatusLogger status={status || "알림 없음"} isErrorStatus={isErrorStatus} />}
          settingsTitle="자산 엑셀 설정"
          settingsContent={
            <div className="space-y-2 text-sm text-slate-600 dark:text-slate-400">
              <p>저장 방식, 충돌 정책, 저장 폴더, 파일 선택, Sheet 미리보기 옵션은 본문에서 바로 조작합니다.</p>
            </div>
          }
        />
      </div>
    </WorkflowPageShell>
  );
}
