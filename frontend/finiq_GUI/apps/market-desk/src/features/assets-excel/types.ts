export type AssetExcelFile = {
  file_name: string;
  relative_path: string;
  size_bytes: number;
};

export type AssetExcelFilesResponse = {
  root_directory: string;
  excel_files: AssetExcelFile[];
};

export type AssetExcelConvertPayload = {
  output_directory: string;
  selected_files: string[];
  conflict_policy: string;
  write_mode: string;
};

export type PreviewData = {
  accounts?: Record<string, any>;
  sheets?: any[];
  skipped?: any[];
  conflicts?: Record<string, any[]>;
  output?: any;
};

export type SheetPayload = {
  error?: string;
  columns?: string[];
  preview_columns?: string[];
  rows?: any[];
  sheet_names?: string[];
  sheet_name?: string;
  account_name?: string;
  status?: string;
  date_start?: string;
  date_end?: string;
  row_count?: number;
  preview_row_count?: number;
};
