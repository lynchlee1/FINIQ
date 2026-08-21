import { create } from "zustand";
import { apiGet, apiPost } from "@/api/client";

let cachedSettings: Record<string, any> | null = null;
let settingsRequest: Promise<Record<string, any>> | null = null;

interface SettingsState {
  parallel_worker_count: number;
  runtime_info_loaded: boolean;
  output_root: string;
  quanti_dir: string;
  price_root_directory: string;
  selected_classification_path: string;
  sqlite_source_path: string;
  download_output_directory: string;
  disclosure_separate_output_directory: boolean;
  sqlite_output_directory: string;
  external_html_output_directory: string;
  internal_html_output_directory: string;
  html_section_split_output_directory: string;
  external_html_transfer_directory: string;
  html_parse_output_directory: string;
  html_parse_result_path: string;
  html_parse_mode: string;
  integrated_merge_input_path: string;
  integrated_merge_output_path: string;
  integrated_history_item_registry_path: string;
  integrated_history_output_path: string;
  asset_excel_source_directory: string;
  asset_excel_output_directory: string;
  asset_excel_merge_input_directory: string;
  asset_excel_merge_output_directory: string;
  asset_excel_merge_same_directory: boolean;
  asset_excel_cleanup_merged_items: boolean;
  asset_excel_duplicate_scan_recursive: boolean;
  asset_excel_account_mappings: any[];
  external_html_compressed_json_path: string;
  external_html_compress_input_directory: string;
  external_html_compress_output_directory: string;
  integrated_data_values: Record<string, string>;
  change_log_date_thresholds: Record<string, number>;
  change_log_numeric_thresholds: Record<string, number>;
  job_retention_minutes: number;
  
  // Actions
  updateSettings: (newSettings: Partial<Omit<SettingsState, "updateSettings" | "fetchSettings" | "fetchRuntimeInfo" | "saveSetting" | "saveSettings">>) => void;
  fetchSettings: () => Promise<any>;
  fetchRuntimeInfo: () => Promise<any>;
  saveSetting: (key: keyof Omit<SettingsState, "updateSettings" | "fetchSettings" | "fetchRuntimeInfo" | "saveSetting" | "saveSettings" | "parallel_worker_count" | "runtime_info_loaded">, value: any) => Promise<boolean>;
  saveSettings: (payload: Partial<Omit<SettingsState, "updateSettings" | "fetchSettings" | "fetchRuntimeInfo" | "saveSetting" | "saveSettings" | "parallel_worker_count" | "runtime_info_loaded">>) => Promise<boolean>;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  parallel_worker_count: 1,
  runtime_info_loaded: false,
  output_root: "",
  quanti_dir: "",
  price_root_directory: "",
  selected_classification_path: "",
  sqlite_source_path: "",
  download_output_directory: "",
  disclosure_separate_output_directory: false,
  sqlite_output_directory: "",
  external_html_output_directory: "",
  internal_html_output_directory: "",
  html_section_split_output_directory: "",
  external_html_transfer_directory: "",
  html_parse_output_directory: "",
  html_parse_result_path: "",
  html_parse_mode: "",
  integrated_merge_input_path: "",
  integrated_merge_output_path: "",
  integrated_history_item_registry_path: "",
  integrated_history_output_path: "",
  asset_excel_source_directory: "",
  asset_excel_output_directory: "",
  asset_excel_merge_input_directory: "",
  asset_excel_merge_output_directory: "",
  asset_excel_merge_same_directory: false,
  asset_excel_cleanup_merged_items: true,
  asset_excel_duplicate_scan_recursive: false,
  asset_excel_account_mappings: [],
  external_html_compressed_json_path: "",
  external_html_compress_input_directory: "",
  external_html_compress_output_directory: "",
  integrated_data_values: {},
  change_log_date_thresholds: {},
  change_log_numeric_thresholds: {},
  job_retention_minutes: 60,

  updateSettings: (newSettings) => set((state) => ({ ...state, ...newSettings })),

  fetchSettings: async () => {
    let config = cachedSettings;
    if (!config) {
      settingsRequest ||= apiGet<Record<string, any>>("/api/config")
        .then((config) => {
          cachedSettings = config;
          return config;
        })
        .finally(() => {
          settingsRequest = null;
        });
      config = await settingsRequest;
    }
    const workerCount = Number(config.parallel_worker_count);
    if (!Number.isInteger(workerCount) || workerCount < 1) {
      throw new Error("parallel_worker_count must be a positive integer");
    }
    set((state) => ({ ...state, ...config, runtime_info_loaded: true }));
    return config;
  },

  fetchRuntimeInfo: async () => {
    const state = get();
    if (state.runtime_info_loaded) {
      return {
        parallel_worker_count: state.parallel_worker_count,
      };
    }
    const config = await apiGet<any>("/api/config");
    const workerCount = Number(config.parallel_worker_count);
    if (!Number.isInteger(workerCount) || workerCount < 1) {
      throw new Error("parallel_worker_count must be a positive integer");
    }
    set((current) => ({
      ...current,
      parallel_worker_count: workerCount,
      runtime_info_loaded: true,
    }));
    return config;
  },

  saveSetting: async (key, value) => {
    try {
      const config = await apiPost<any>("/api/settings", { [key]: value });
      cachedSettings = config;
      set((state) => ({ ...state, ...config }));
      return true;
    } catch (err) {
      console.error(`Failed to save setting ${String(key)}:`, err);
      return false;
    }
  },

  saveSettings: async (payload) => {
    try {
      const config = await apiPost<any>("/api/settings", payload);
      cachedSettings = config;
      set((state) => ({ ...state, ...config }));
      return true;
    } catch (err) {
      console.error(`Failed to save settings:`, err);
      return false;
    }
  },
}));
