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
  log_limit: number;
  start_page: number;
  end_page: number | null;
  last_report_only: boolean;
  resume_yearly: boolean;
  disclosure_type_groups: Record<string, string[]>;
};

export type DownloadInspectPayload = DownloadPayload & {
  dry_run: boolean;
  delete_confirmed: boolean;
  delete_confirmation_text: string;
};
