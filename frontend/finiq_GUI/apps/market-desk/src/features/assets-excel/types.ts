export type AssetAccountMapping = {
  account_id: string;
  account_name: string;
  legacy_account_name: string;
  sheet_name: string;
};

export type AssetAccountMappingsResponse = {
  items: AssetAccountMapping[];
};

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
  source_directory: string;
  output_directory: string;
  write_mode: string;
  account_mappings?: AssetAccountMapping[];
  resume_failed_only?: boolean;
};

export type AssetParquetMergePayload = {
  target_directory: string;
  selected_files: string[];
  output_directory: string;
  same_directory?: boolean;
  cleanup_merged_items?: boolean;
};

export type PreviewData = {
  outputs?: Record<string, any>;
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
  preview_type?: string;
  metadata?: {
    period_from?: string;
    period_to?: string;
  };
  code_name_rows?: Array<{
    code: string;
    name: string;
  }>;
  account_name?: string;
  status?: string;
  date_start?: string;
  date_end?: string;
  row_count?: number;
  preview_row_count?: number;
};

export type SheetListPayload = {
  file_name: string;
  relative_path: string;
  sheet_names: string[];
  sheet_count: number;
};
