import { apiPost } from "@/api/client";
import type { DisclosureConditionPreset } from "@/components/disclosures/DisclosureConditionFilterCard";

type PresetStoreResponse = {
  format: "finiq_disclosure_filter_workflow_directory";
  path: string;
  presets: DisclosureConditionPreset[];
};

const endpoint = "/api/disclosures/filter/presets";

type PresetCacheEntry = {
  value?: PresetStoreResponse;
  promise?: Promise<PresetStoreResponse>;
};

const presetCache = new Map<string, PresetCacheEntry>();

const cacheKey = (dataRoot: string) => dataRoot.trim();

const storePresetResponse = (dataRoot: string, value: PresetStoreResponse) => {
  presetCache.set(cacheKey(dataRoot), { value });
  return value;
};

export const listDisclosureConditionPresets = (
  dataRoot: string,
  options: { force?: boolean } = {},
) => {
  const key = cacheKey(dataRoot);
  const cached = presetCache.get(key);
  if (cached?.promise) return cached.promise;
  if (!options.force && cached?.value) return Promise.resolve(cached.value);

  let promise: Promise<PresetStoreResponse>;
  promise = apiPost<PresetStoreResponse>(endpoint, { data_root: dataRoot, action: "list" }).then((response) => storePresetResponse(dataRoot, response)).finally(() => {
    const current = presetCache.get(key);
    if (current?.promise === promise) {
      presetCache.set(key, current.value ? { value: current.value } : {});
    }
  });
  presetCache.set(key, { ...cached, promise });
  return promise;
};

export const saveDisclosureConditionPreset = (
  dataRoot: string,
  preset: Pick<DisclosureConditionPreset, "mode" | "condition_blocks"> & { parent_mode?: string },
) => apiPost<PresetStoreResponse>(endpoint, {
  data_root: dataRoot, action: "save", preset,
}).then((response) => storePresetResponse(dataRoot, response));

export const deleteDisclosureConditionPreset = (dataRoot: string, mode: string, parentMode?: string) =>
  apiPost<PresetStoreResponse>(endpoint, {
    data_root: dataRoot,
    action: "delete",
    mode,
    ...(parentMode ? { parent_mode: parentMode } : {}),
  }).then((response) => storePresetResponse(dataRoot, response));
