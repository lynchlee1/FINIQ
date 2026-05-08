const HTML_DOWNLOAD_STORAGE_KEY = "finiq.kind.filteredDisclosures";

const elements = {
  outputDirectory: document.getElementById("outputDirectory"),
  timeout: document.getElementById("timeout"),
  maxRequestsPerMinute: document.getElementById("maxRequestsPerMinute"),
  waitSeconds: document.getElementById("waitSeconds"),
  limit: document.getElementById("limit"),
  skipExisting: document.getElementById("skipExisting"),
  parseMode: document.getElementById("parseMode"),
  parseOutputPath: document.getElementById("parseOutputPath"),
  jsonInput: document.getElementById("jsonInput"),
  downloadHtmlBtn: document.getElementById("downloadHtmlBtn"),
  parseHtmlBtn: document.getElementById("parseHtmlBtn"),
  status: document.getElementById("status"),
  result: document.getElementById("result"),
};

function setStatus(message, isError = false) {
  elements.status.textContent = message || "";
  elements.status.dataset.tone = isError ? "error" : "default";
}

function setResult(payload) {
  elements.result.textContent = JSON.stringify(payload, null, 2);
}

function defaultParseOutputPath() {
  const outputDirectory = elements.outputDirectory.value || "";
  const mode = elements.parseMode?.value || "bond_issuance";
  return outputDirectory ? `${outputDirectory}/parsed-${mode}.json` : "";
}

function refreshParseOutputPath() {
  if (!elements.parseOutputPath || elements.parseOutputPath.dataset.touched === "true") {
    return;
  }
  elements.parseOutputPath.value = defaultParseOutputPath();
}

async function fetchJson(url, init) {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function loadConfig() {
  const config = await fetchJson("/api/config");
  elements.outputDirectory.value = `${config.output_root || ""}/viewer_html`;
  refreshParseOutputPath();
  const transferredPayload = sessionStorage.getItem(HTML_DOWNLOAD_STORAGE_KEY);
  if (transferredPayload) {
    elements.jsonInput.value = JSON.stringify(JSON.parse(transferredPayload), null, 2);
    sessionStorage.removeItem(HTML_DOWNLOAD_STORAGE_KEY);
    setStatus("필터 페이지에서 선택한 JSON을 불러왔습니다.");
    return;
  }
  setStatus("저장 경로 기본값을 불러왔습니다.");
}

function buildPayload() {
  let parsedJson;
  try {
    parsedJson = JSON.parse(elements.jsonInput.value);
  } catch (error) {
    throw new Error(`JSON 파싱 실패: ${error.message}`);
  }
  return {
    output_directory: elements.outputDirectory.value,
    json: parsedJson,
    source_json_path: parsedJson.source_json_path || "",
    timeout: Number(elements.timeout.value || 20),
    max_requests_per_minute: Number(elements.maxRequestsPerMinute.value || 90),
    wait_seconds: Number(elements.waitSeconds.value || 0),
    limit: elements.limit.value ? Number(elements.limit.value) : "",
    skip_existing: elements.skipExisting.checked,
  };
}

function buildParsePayload() {
  return {
    input_directory: elements.outputDirectory.value,
    output_path: elements.parseOutputPath.value || defaultParseOutputPath(),
    mode: elements.parseMode.value,
    limit: elements.limit.value ? Number(elements.limit.value) : "",
    skip_errors: true,
  };
}

async function runDownload() {
  setStatus("HTML 다운로드 중입니다. 처리 건수가 많으면 잠시 걸립니다.");
  const payload = await fetchJson("/api/disclosures/html/download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildPayload()),
  });
  setResult(payload);
  const lines = [
    `요청 접수번호: ${payload.requested_count || 0}`,
    `저장 파일: ${payload.saved_count || 0}`,
    `저장 경로: ${payload.output_directory || ""}`,
    "",
    ...(payload.progress_log || []),
  ];
  setStatus(lines.join("\n"));
}

async function runParse() {
  refreshParseOutputPath();
  setStatus("HTML 파싱 중입니다.");
  const payload = await fetchJson("/api/disclosures/html/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildParsePayload()),
  });
  setResult(payload);
  const summary = payload.summary || {};
  const lines = [
    `파싱 모드: ${payload.mode || ""}`,
    `대상 HTML: ${summary.found_files || 0}`,
    `파싱 성공: ${summary.parsed_files || 0}`,
    `파싱 실패: ${summary.failed_files || 0}`,
    `결과 경로: ${payload.output_path || ""}`,
  ];
  setStatus(lines.join("\n"), Number(summary.failed_files || 0) > 0);
}

elements.outputDirectory?.addEventListener("input", refreshParseOutputPath);

elements.parseMode?.addEventListener("change", () => {
  if (elements.parseOutputPath) {
    elements.parseOutputPath.dataset.touched = "false";
  }
  refreshParseOutputPath();
});

elements.parseOutputPath?.addEventListener("input", () => {
  elements.parseOutputPath.dataset.touched = "true";
});

elements.downloadHtmlBtn?.addEventListener("click", () => {
  runDownload().catch((error) => setStatus(error.message, true));
});

elements.parseHtmlBtn?.addEventListener("click", () => {
  runParse().catch((error) => setStatus(error.message, true));
});

loadConfig().catch((error) => setStatus(error.message, true));
