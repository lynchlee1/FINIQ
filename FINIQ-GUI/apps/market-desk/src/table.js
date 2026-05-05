const elements = {
  rootDirectory: document.getElementById("rootDirectory"),
  classificationPath: document.getElementById("classificationPath"),
  classificationPathOptions: document.getElementById("classificationPathOptions"),
  outputPath: document.getElementById("outputPath"),
  tableName: document.getElementById("tableName"),
  refreshBtn: document.getElementById("refreshBtn"),
  buildBtn: document.getElementById("buildBtn"),
  status: document.getElementById("status"),
  result: document.getElementById("result"),
  summaryCards: document.getElementById("summaryCards"),
};

function setStatus(message, isError = false) {
  elements.status.textContent = message || "";
  elements.status.dataset.tone = isError ? "error" : "default";
}

function setResult(payload) {
  elements.result.textContent = JSON.stringify(payload, null, 2);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function fetchJson(url, init) {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function manifestPathFromRawPath(path) {
  const normalized = String(path || "").trim();
  if (!normalized) {
    return "";
  }
  if (!/\.json$/i.test(normalized)) {
    return normalized.replace(/\/?$/, "/kind.sqlite_manifest.json");
  }
  return normalized.replace(/\.json$/i, ".sqlite_manifest.json");
}

function selectedClassificationPath() {
  return String(elements.classificationPath.value || "").trim();
}

function renderSummary(payload) {
  const summary = payload?.summary || {};
  const rows = [
    ["회사", summary.companies || 0],
    ["공시", summary.disclosures || 0],
    ["Shard", summary.shards || 0],
    ["FTS", summary.fts_enabled ? "ON" : "OFF"],
  ];
  elements.summaryCards.innerHTML = rows
    .map(
      ([label, value]) => `
        <div class="summary-card">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `,
    )
    .join("");
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
  elements.classificationPath.value = matched ? selectedPath : files[0].path;
}

async function loadClassifications(rootDirectory, selectedPath = "") {
  const url = new URL("/api/classifications", window.location.origin);
  url.searchParams.set("root_directory", rootDirectory);
  const payload = await fetchJson(url.pathname + url.search);
  renderClassificationOptions(payload.classification_files || [], selectedPath || payload.selected_classification_path || "");
  elements.outputPath.value = manifestPathFromRawPath(selectedClassificationPath());
}

async function initialize() {
  setStatus("소스를 불러오는 중...");
  const config = await fetchJson("/api/config");
  elements.rootDirectory.value = config.output_root || "";
  await loadClassifications(config.output_root || "", config.selected_classification_path || "");
  setStatus("준비 완료");
}

async function buildTable() {
  const classificationPath = selectedClassificationPath();
  if (!classificationPath) {
    throw new Error("Raw JSON을 선택하세요.");
  }
  const payload = await fetchJson("/api/disclosures/table/build", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      root_directory: String(elements.rootDirectory.value || "").trim(),
      classification_path: classificationPath,
      output_path: String(elements.outputPath.value || "").trim(),
      table_name: String(elements.tableName.value || "disclosures").trim(),
    }),
  });
  setResult(payload);
  renderSummary(payload);
  setStatus(`연도별 SQLite shard를 생성했습니다: ${payload.manifest_path || payload.output_path}`);
}

elements.classificationPath.addEventListener("change", () => {
  elements.outputPath.value = manifestPathFromRawPath(selectedClassificationPath());
});

elements.classificationPath.addEventListener("input", () => {
  elements.outputPath.value = manifestPathFromRawPath(selectedClassificationPath());
});

elements.refreshBtn.addEventListener("click", async () => {
  try {
    setStatus("소스를 새로고침하는 중...");
    await loadClassifications(String(elements.rootDirectory.value || "").trim(), selectedClassificationPath());
    setStatus("소스를 새로고침했습니다.");
  } catch (error) {
    setStatus(error.message, true);
  }
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
