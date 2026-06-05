import { create } from "zustand";

interface SettingsState {
  output_root: string;
  quanti_dir: string;
  price_root_directory: string;
  selected_classification_path: string;
  sqlite_source_path: string;
  download_output_directory: string;
  sqlite_manifest_path: string;
  html_output_directory: string;
  html_content_output_directory: string;
  html_transfer_directory: string;
  html_parse_result_path: string;
  html_parse_mode: string;
  integrated_merge_input_path: string;
  integrated_merge_output_path: string;
  integrated_history_item_registry_path: string;
  integrated_history_output_path: string;
  html_download_source_path: string;
  html_merge_output_path: string;
  integrated_data_values: Record<string, string>;
  change_log_date_thresholds: Record<string, number>;
  change_log_numeric_thresholds: Record<string, number>;
  condition_presets: any[];
  
  // Actions
  updateSettings: (newSettings: Partial<Omit<SettingsState, "updateSettings" | "fetchSettings" | "saveSetting" | "saveSettings">>) => void;
  fetchSettings: () => Promise<any>;
  saveSetting: (key: keyof Omit<SettingsState, "updateSettings" | "fetchSettings" | "saveSetting" | "saveSettings">, value: any) => Promise<void>;
  saveSettings: (payload: Partial<Omit<SettingsState, "updateSettings" | "fetchSettings" | "saveSetting" | "saveSettings">>) => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  output_root: "",
  quanti_dir: "",
  price_root_directory: "",
  selected_classification_path: "",
  sqlite_source_path: "",
  download_output_directory: "",
  sqlite_manifest_path: "",
  html_output_directory: "",
  html_content_output_directory: "",
  html_transfer_directory: "",
  html_parse_result_path: "",
  html_parse_mode: "",
  integrated_merge_input_path: "",
  integrated_merge_output_path: "",
  integrated_history_item_registry_path: "",
  integrated_history_output_path: "",
  html_download_source_path: "",
  html_merge_output_path: "",
  integrated_data_values: {},
  change_log_date_thresholds: {},
  change_log_numeric_thresholds: {},
  condition_presets: [],

  updateSettings: (newSettings) => set((state) => ({ ...state, ...newSettings })),

  fetchSettings: async () => {
    try {
      const response = await fetch("/api/config");
      if (response.ok) {
        const config = await response.json();
        set((state) => ({ ...state, ...config }));
        return config;
      }
    } catch (err) {
      console.error("Failed to fetch settings:", err);
    }
  },

  saveSetting: async (key, value) => {
    set((state) => ({ ...state, [key]: value }));
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: value }),
      });
    } catch (err) {
      console.error(`Failed to save setting ${String(key)}:`, err);
    }
  },

  saveSettings: async (payload) => {
    set((state) => ({ ...state, ...payload }));
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (err) {
      console.error(`Failed to save settings:`, err);
    }
  },
}));
