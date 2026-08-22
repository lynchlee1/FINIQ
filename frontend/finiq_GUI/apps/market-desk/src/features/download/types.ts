export type DisclosureItem = {
  code: string;
  name: string;
};

export type DisclosureGroup = {
  label: string;
  suffix: string;
  items: DisclosureItem[];
};

export type DownloadOptions = {
  market_types: { label: string }[];
  securities_types: { label: string }[];
  disclosure_groups: DisclosureGroup[];
  default_output_directory: string;
};

export type DownloadPayload = {
  data_root: string;
  separate_output_directory: boolean;
  mode: "yearly";
  output_directory: string;
  start_date: string;
  end_date: string;
  company_name: string;
  submitter_name: string;
  market_label: string;
  securities_label: string;
  page_size: number;
  wait_seconds: number;
  timeout: number;
  worker_count: number;
  parallel_strategy: "years" | "pages";
  log_limit: number;
  start_page: number;
  end_page: number | null;
  last_report_only: boolean;
  disclosure_type_groups: Record<string, string[]>;
};

export type DownloadInspectPayload = DownloadPayload & {
  dry_run: boolean;
  delete_confirmed: boolean;
  delete_confirmation_text: string;
};

export type DownloadSavedFilters = Pick<
  DownloadPayload,
  | "company_name"
  | "submitter_name"
  | "market_label"
  | "securities_label"
  | "disclosure_type_groups"
  | "last_report_only"
>;

export type DownloadExistingPayload = Pick<
  DownloadPayload,
  | "output_directory"
  | "start_date"
  | "end_date"
  | "company_name"
  | "submitter_name"
  | "market_label"
  | "securities_label"
  | "page_size"
  | "last_report_only"
  | "disclosure_type_groups"
>;

export type DownloadExistingRange = {
  start_date: string | null;
  end_date: string | null;
  folder_name: string;
  local_count: number | null;
  kind_count: number | null;
  status: "validated" | "stale" | "unverified";
  error_detail: string | null;
  metadata_missing?: boolean;
  metadata_obsolete?: boolean;
  metadata_status?: "ok" | "missing" | "obsolete" | "mismatch";
  filters_match?: boolean;
  folder_path: string;
};

export type DownloadExistingResponse = {
  has_existing: boolean;
  earliest_date?: string | null;
  latest_date?: string | null;
  ranges?: DownloadExistingRange[];
  saved_filters?: DownloadSavedFilters | null;
  saved_filters_consistent: boolean;
};
