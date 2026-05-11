import { bindPathPicker } from "./path-picker.js";
import { bindPathSetting } from "./settings.js";

const HTML_DOWNLOAD_STORAGE_KEY = "finiq.kind.filteredDisclosures";

const elements = {
  outputDirectory: document.getElementById("outputDirectory"),
  timeout: document.getElementById("timeout"),
  maxRequestsPerMinute: document.getElementById("maxRequestsPerMinute"),
  waitSeconds: document.getElementById("waitSeconds"),
  limit: document.getElementById("limit"),
  skipExisting: document.getElementById("skipExisting"),
  progressInterval: document.getElementById("progressInterval"),
  sourceJsonPath: document.getElementById("sourceJsonPath"),
  downloadHtmlBtn: document.getElementById("downloadHtmlBtn"),
  cancelHtmlBtn: document.getElementById("cancelHtmlBtn"),
  status: document.getElementById("status"),
  result: document.getElementById("result"),
};

let activeCancelToken = "";
let stopRequested = false;
let activeJobId = "";
let jobPollTimer = 0;

function setStatus(message, isError = false) {
  elements.status.textContent = message || "";
  elements.status.dataset.tone = isError ? "error" : "default";
}

function logLines(lines, isError = false) {
  setStatus(lines.filter(Boolean).join("\n"), isError);
  if (elements.status) {
    elements.status.scrollTop = elements.status.scrollHeight;
  }
}

function timestamp() {
  return new Date().toLocaleTimeString("ko-KR", { hour12: false });
}

function setResult(payload) {
  elements.result.textContent = JSON.stringify(payload, null, 2);
}

function statusLabel(status) {
  if (status === "queued") {
    return "대기 중";
  }
  if (status === "running") {
    return "실행 중";
  }
  if (status === "completed") {
    return "완료";
  }
  if (status === "failed") {
    return "실패";
  }
  return status || "-";
}

function stopJobPolling() {
  if (jobPollTimer) {
    window.clearTimeout(jobPollTimer);
    jobPollTimer = 0;
  }
}

async function fetchJson(url, init) {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function makeCancelToken() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function setDownloadRunning(isRunning) {
  if (elements.downloadHtmlBtn) {
    elements.downloadHtmlBtn.disabled = isRunning;
  }
  if (elements.cancelHtmlBtn) {
    elements.cancelHtmlBtn.disabled = !isRunning || stopRequested;
  }
}

async function loadConfig() {
  const config = await fetchJson("/api/config");
  elements.outputDirectory.value = config.html_output_directory || `${config.output_root || ""}/viewer_html`;
  const transferredPayload = sessionStorage.getItem(HTML_DOWNLOAD_STORAGE_KEY);
  if (transferredPayload) {
    const transferReference = JSON.parse(transferredPayload);
    elements.sourceJsonPath.value = transferReference.source_json_path || "";
    sessionStorage.removeItem(HTML_DOWNLOAD_STORAGE_KEY);
    setStatus("공시 필터에서 생성한 결과 파일을 불러왔습니다.");
    return;
  }
  setStatus("저장 경로 기본값을 불러왔습니다.");
}

function buildPayload() {
  const sourceJsonPath = String(elements.sourceJsonPath.value || "").trim();
  if (!sourceJsonPath) {
    throw new Error("필터 결과 파일을 선택하세요.");
  }
  return {
    output_directory: elements.outputDirectory.value,
    source_json_path: sourceJsonPath,
    timeout: Number(elements.timeout.value || 20),
    max_requests_per_minute: Number(elements.maxRequestsPerMinute.value || 90),
    wait_seconds: Number(elements.waitSeconds.value || 0),
    limit: elements.limit.value ? Number(elements.limit.value) : "",
    skip_existing: elements.skipExisting.checked,
    progress_interval: Number(elements.progressInterval.value || 10),
    log_limit: 200,
  };
}

function formatDownloadJobStatus(payload) {
  const result = payload.result || {};
  const lines = [`작업 상태: ${statusLabel(payload.status)}`];
  if (payload.error) {
    lines.push(`오류: ${payload.error}`);
  }
  if (result.requested_count !== undefined) {
    lines.push(`요청 접수번호: ${result.requested_count || 0}`);
    lines.push(`저장 파일: ${result.saved_count || 0}`);
    lines.push(`저장 경로: ${result.output_directory || ""}`);
  }
  if (Array.isArray(payload.progress_log) && payload.progress_log.length) {
    lines.push("", "최근 로그", ...payload.progress_log);
  }
  return lines.join("\n");
}

async function pollDownloadJob(jobId) {
  try {
    const payload = await fetchJson(`/api/disclosures/html/jobs/${encodeURIComponent(jobId)}`);
    setResult(payload.result || payload);
    setStatus(formatDownloadJobStatus(payload), payload.status === "failed");
    if (payload.status === "completed" || payload.status === "failed") {
      activeJobId = "";
      activeCancelToken = "";
      stopRequested = false;
      stopJobPolling();
      setDownloadRunning(false);
      return;
    }
    jobPollTimer = window.setTimeout(() => pollDownloadJob(jobId), 1000);
  } catch (error) {
    activeJobId = "";
    activeCancelToken = "";
    stopRequested = false;
    stopJobPolling();
    setDownloadRunning(false);
    setStatus(error.message, true);
  }
}

async function runDownload() {
  if (activeCancelToken || activeJobId) {
    return;
  }
  stopJobPolling();
  const requestPayload = buildPayload();
  activeCancelToken = makeCancelToken();
  stopRequested = false;
  setDownloadRunning(true);
  logLines([
    `[${timestamp()}] HTML 저장을 시작했습니다.`,
    `필터 결과 파일: ${requestPayload.source_json_path || ""}`,
    `저장 경로: ${requestPayload.output_directory || ""}`,
    `타임아웃: ${requestPayload.timeout}초`,
    `최대 요청/분: ${requestPayload.max_requests_per_minute}`,
    `요청 간격: ${requestPayload.wait_seconds}초`,
    `최대 처리 건수: ${requestPayload.limit || "전체"}`,
    `기존 파일 건너뛰기: ${requestPayload.skip_existing ? "예" : "아니오"}`,
    `진행 확인 간격: ${requestPayload.progress_interval}건`,
  ]);
  try {
    const payload = await fetchJson("/api/disclosures/html/download/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...requestPayload, cancel_token: activeCancelToken }),
    });
    activeJobId = payload.job_id;
    setResult(payload);
    setStatus(formatDownloadJobStatus(payload));
    pollDownloadJob(activeJobId);
  } catch (error) {
    activeCancelToken = "";
    stopRequested = false;
    activeJobId = "";
    setDownloadRunning(false);
    throw error;
  }
}

async function cancelDownload() {
  if (!activeCancelToken || stopRequested) {
    return;
  }
  stopRequested = true;
  setDownloadRunning(true);
  setStatus(`[${timestamp()}] HTML 저장 중지를 요청했습니다. 진행 중인 요청이 끝나면 멈춥니다.`);
  await fetchJson("/api/disclosures/html/download/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cancel_token: activeCancelToken }),
  });
}

elements.downloadHtmlBtn?.addEventListener("click", () => {
  runDownload().catch((error) => setStatus(error.message, true));
});
elements.cancelHtmlBtn?.addEventListener("click", () => {
  cancelDownload().catch((error) => setStatus(error.message, true));
});

bindPathSetting(
  elements.outputDirectory,
  () => ({ html_output_directory: elements.outputDirectory.value }),
  (error) => setStatus(error.message, true),
);

loadConfig().catch((error) => setStatus(error.message, true));

bindPathPicker(document, {
  onError: (error) => setStatus(error.message, true),
});
