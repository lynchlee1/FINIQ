import { bindPathPicker } from "./path-picker.js";
import { bindPathSetting, savePathSetting } from "./settings.js";

const elements = {
  classificationPath: document.getElementById("classificationPath"),
  classificationPathOptions: document.getElementById("classificationPathOptions"),
  outputPath: document.getElementById("outputPath"),
  tableName: document.getElementById("tableName"),
  refreshBtn: document.getElementById("refreshBtn"),
  buildBtn: document.getElementById("buildBtn"),
  status: document.getElementById("status"),
};

function setStatus(message, isError = false) {
  elements.status.textContent = message || "";
  elements.status.dataset.tone = isError ? "error" : "default";
}

async function fetchJson(url, init) {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function outputDirectoryFromRawPath(path) {
  const normalized = String(path || "").trim();
  if (!normalized) {
    return "";
  }
  if (/\.json$/i.test(normalized)) {
    return normalized.replace(/\.json$/i, "_sqlite");
  }
  return normalized.replace(/\/?$/, "/kind_sqlite");
}

function outputDirectoryFromSavedPath(path) {
  const normalized = String(path || "").trim();
  if (!/\.sqlite_manifest\.json$/i.test(normalized)) {
    return normalized;
  }
  return normalized.replace(/\/[^/]*$/i, "");
}

function selectedClassificationPath() {
  return String(elements.classificationPath.value || "").trim();
}

function formatSummary(payload) {
  const summary = payload?.summary || {};
  const rows = [
    ["회사", summary.companies || 0],
    ["공시", summary.disclosures || 0],
    ["Shard", summary.shards || 0],
    ["FTS", summary.fts_enabled ? "ON" : "OFF"],
  ];
  return rows.map(([label, value]) => `${label}: ${value}`).join(" · ");
}

function renderClassificationOptions(files, selectedPath = "") {
  elements.classificationPathOptions.innerHTML = "";
  if (!files.length) {
    elements.classificationPath.value = selectedPath || "";
    return;
  }
  files.forEach((file) => {
    const option = document.createElement("option");
    option.value = file.path;
    option.label = file.label || file.name || file.path;
    elements.classificationPathOptions.appendChild(option);
  });
  const matched = files.some((file) => file.path === selectedPath);
  elements.classificationPath.value = matched || selectedPath ? selectedPath : files[0].path;
}

async function loadClassifications(rootDirectory, selectedPath = "", selectedOutputPath = "") {
  const url = new URL("/api/classifications", window.location.origin);
  url.searchParams.set("root_directory", rootDirectory);
  const payload = await fetchJson(url.pathname + url.search);
  renderClassificationOptions(payload.classification_files || [], selectedPath || payload.selected_classification_path || "");
  elements.outputPath.value = outputDirectoryFromSavedPath(selectedOutputPath) || outputDirectoryFromRawPath(selectedClassificationPath());
}

async function initialize() {
  setStatus("소스를 불러오는 중...");
  const config = await fetchJson("/api/config");
  await loadClassifications(
    config.output_root || "",
    config.sqlite_source_path || config.selected_classification_path || "",
    config.sqlite_manifest_path || "",
  );
  setStatus("준비 완료");
}

async function buildTable() {
  const classificationPath = selectedClassificationPath();
  if (!classificationPath) {
    throw new Error("Raw JSON을 선택하세요.");
  }
  const outputPath = String(elements.outputPath.value || "").trim();
  const payload = await fetchJson("/api/disclosures/table/build", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      classification_path: classificationPath,
      output_path: outputPath,
      table_name: String(elements.tableName?.value || "disclosures").trim(),
    }),
  });
  setStatus(`연도별 SQLite shard를 저장했습니다: ${outputPath || payload.output_path}\n${formatSummary(payload)}`);
}

elements.classificationPath.addEventListener("change", () => {
  elements.outputPath.value = outputDirectoryFromRawPath(selectedClassificationPath());
  savePathSetting({
    sqlite_source_path: selectedClassificationPath(),
    sqlite_manifest_path: elements.outputPath.value,
  }).catch((error) => setStatus(error.message, true));
});

elements.classificationPath.addEventListener("input", () => {
  elements.outputPath.value = outputDirectoryFromRawPath(selectedClassificationPath());
});

elements.classificationPath.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") {
    return;
  }
  event.preventDefault();
  elements.outputPath.value = outputDirectoryFromRawPath(selectedClassificationPath());
  savePathSetting({
    sqlite_source_path: selectedClassificationPath(),
    sqlite_manifest_path: elements.outputPath.value,
  }).catch((error) => setStatus(error.message, true));
});

bindPathSetting(
  elements.outputPath,
  () => ({ sqlite_manifest_path: elements.outputPath.value }),
  (error) => setStatus(error.message, true),
);

elements.refreshBtn.addEventListener("click", async () => {
  try {
    setStatus("소스를 새로고침하는 중...");
    const config = await fetchJson("/api/config");
    await loadClassifications(config.output_root || "", selectedClassificationPath());
    setStatus("소스를 새로고침했습니다.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

bindPathPicker(document, {
  onError: (error) => setStatus(error.message, true),
});

elements.buildBtn.addEventListener("click", async () => {
  try {
    setStatus("SQLite 테이블 생성 중...");
    await buildTable();
  } catch (error) {
    setStatus(error.message, true);
  }
});

initialize().catch((error) => {
  setStatus(error.message, true);
});
