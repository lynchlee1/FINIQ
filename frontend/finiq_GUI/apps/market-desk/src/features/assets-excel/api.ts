import { apiGet, apiPost } from "@/api/client";
import type { JobStartResponse } from "@/types/api";
import type { AssetAccountMappingsResponse, AssetExcelConvertPayload, AssetExcelFilesResponse, AssetParquetDuplicateCleanupPayload, AssetParquetMergePayload, PreviewData, SheetListPayload, SheetPayload } from "./types";

function encodePath(value: string): string {
  return value.split("/").map((part) => encodeURIComponent(part)).join("/");
}

export function fetchAssetExcelFiles(sourceDirectory: string) {
  const query = new URLSearchParams({ source_directory: sourceDirectory });
  return apiGet<AssetExcelFilesResponse>(`/api/assets/excels?${query.toString()}`);
}

export function fetchAssetExcelOutput(outputDirectory: string) {
  const params = new URLSearchParams({ output_directory: outputDirectory });
  return apiGet<any>(`/api/assets/excels/output?${params.toString()}`);
}

export function fetchAssetExcelAccountMappings() {
  return apiGet<AssetAccountMappingsResponse>("/api/assets/excels/account-mappings");
}

export function saveAssetExcelAccountMappings(items: AssetAccountMappingsResponse["items"]) {
  return apiPost<any>("/api/settings", { asset_excel_account_mappings: items });
}

export function fetchAssetExcelSheets(fileName: string, sourceDirectory: string) {
  const query = new URLSearchParams({ source_directory: sourceDirectory });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<SheetListPayload>(`/api/assets/excels/${encodePath(fileName)}/sheets${suffix}`);
}

export function fetchAssetExcelSheet(params: {
  fileName: string;
  sourceDirectory: string;
  sheetName?: string;
  rowLimit?: number;
}) {
  const query = new URLSearchParams({ row_limit: String(params.rowLimit ?? 20) });
  query.set("source_directory", params.sourceDirectory);
  if (params.sheetName) query.set("sheet_name", params.sheetName);
  return apiGet<SheetPayload>(`/api/assets/excels/${encodePath(params.fileName)}?${query.toString()}`);
}

export function fetchAssetParquetPreview(params: {
  fileName: string;
  outputDirectory: string;
  rowLimit?: number;
}) {
  const query = new URLSearchParams({
    file_name: params.fileName,
    output_directory: params.outputDirectory,
    row_limit: String(params.rowLimit ?? 20),
  });
  return apiGet<SheetPayload>(`/api/assets/parquet/preview?${query.toString()}`);
}

export function previewAssetExcelConversion(payload: AssetExcelConvertPayload) {
  return apiPost<PreviewData>("/api/assets/excels/preview-conversion", payload);
}

export function startAssetExcelConversion(payload: AssetExcelConvertPayload) {
  return apiPost<JobStartResponse>("/api/assets/excels/convert-wide-parquet/start", payload);
}

export function startAssetParquetMerge(payload: AssetParquetMergePayload) {
  return apiPost<JobStartResponse>("/api/assets/parquet/merge/start", payload);
}

export function startAssetParquetDuplicateCleanup(payload: AssetParquetDuplicateCleanupPayload) {
  return apiPost<JobStartResponse>("/api/assets/parquet/duplicates/start", payload);
}
