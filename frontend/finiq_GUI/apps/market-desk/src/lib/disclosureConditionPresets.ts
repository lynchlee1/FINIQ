import { apiPost } from "@/api/client";
import type { DisclosureConditionPreset } from "@/components/disclosures/DisclosureConditionFilterCard";

type PresetStoreResponse = {
  format: "finiq_disclosure_filter_preset_directory_v1";
  path: string;
  presets: DisclosureConditionPreset[];
};

const endpoint = "/api/disclosures/filter/presets";

export const listDisclosureConditionPresets = (dataRoot: string) =>
  apiPost<PresetStoreResponse>(endpoint, { data_root: dataRoot, action: "list" });

export const saveDisclosureConditionPreset = (
  dataRoot: string,
  preset: DisclosureConditionPreset,
) => apiPost<PresetStoreResponse>(endpoint, { data_root: dataRoot, action: "save", preset });

export const renameDisclosureConditionPreset = (
  dataRoot: string,
  name: string,
  newName: string,
) => apiPost<PresetStoreResponse>(endpoint, {
  data_root: dataRoot,
  action: "rename",
  name,
  new_name: newName,
});

export const deleteDisclosureConditionPreset = (dataRoot: string, name: string) =>
  apiPost<PresetStoreResponse>(endpoint, { data_root: dataRoot, action: "delete", name });
