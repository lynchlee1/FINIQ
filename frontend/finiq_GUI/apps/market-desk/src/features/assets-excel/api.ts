import { apiGet, apiPost } from "@/api/client";
import type { JobStartResponse } from "@/types/api";
import type { AssetExcelConvertPayload, AssetExcelFilesResponse, PreviewData, SheetPayload } from "./types";

function encodePath(value: string): string {
  return value.split("/").map((part) => encodeURIComponent(part)).join("/");
}

export function fetchAssetExcelFiles() {
  return apiGet<AssetExcelFilesResponse>("/api/assets/excels");
}

export function fetchAssetExcelOutput(outputDirectory: string) {
  const params = new URLSearchParams({ output_directory: outputDirectory });
  return apiGet<any>(`/api/assets/excels/output?${params.toString()}`);
}

export function fetchAssetExcelSheet(params: {
  fileName: string;
  sheetName?: string;
  interpreted?: boolean;
  rowLimit?: number;
}) {
  const query = new URLSearchParams({ row_limit: String(params.rowLimit ?? 20) });
  if (params.sheetName) query.set("sheet_name", params.sheetName);
  if (params.interpreted) query.set("interpreted", "true");
  return apiGet<SheetPayload>(`/api/assets/excels/${encodePath(params.fileName)}?${query.toString()}`);
}

export function previewAssetExcelConversion(payload: AssetExcelConvertPayload) {
  return apiPost<PreviewData>("/api/assets/excels/preview-conversion", payload);
}

export function startAssetExcelConversion(payload: AssetExcelConvertPayload) {
  return apiPost<JobStartResponse>("/api/assets/excels/convert-wide-parquet/start", payload);
}
