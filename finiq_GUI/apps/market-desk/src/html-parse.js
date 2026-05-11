import { bindPathPicker } from "./path-picker.js";
import { bindPathSetting } from "./settings.js";

const PARSE_MODES = [
  {
    key: "bond_issuance",
    label: "사채발행파싱",
    status: "상세 필드 지원",
    description: "전환사채 등 사채 발행 HTML에서 회차, 발행금액, 발행목적, 만기일, 행사가액, 리픽싱, 납입일, 발행대상자를 추출합니다.",
  },
  {
    key: "rights_issuance",
    label: "유무상증자파싱",
    status: "원본 테이블 구조 지원",
    description: "유무상증자 HTML을 공통 구조로 파싱합니다. 상세 필드 규칙은 아직 추가되지 않았습니다.",
  },
  {
    key: "shareholder_meeting",
    label: "주주총회파싱",
    status: "원본 테이블 구조 지원",
    description: "주주총회 HTML을 공통 구조로 파싱합니다. 상세 필드 규칙은 아직 추가되지 않았습니다.",
  },
  {
    key: "asset_transaction",
    label: "유무형자산거래파싱",
    status: "원본 테이블 구조 지원",
    description: "유무형자산 거래 HTML을 공통 구조로 파싱합니다. 상세 필드 규칙은 아직 추가되지 않았습니다.",
  },
  {
    key: "security_transaction",
    label: "발행증권거래파싱",
    status: "원본 테이블 구조 지원",
    description: "발행증권 거래 HTML을 공통 구조로 파싱합니다. 상세 필드 규칙은 아직 추가되지 않았습니다.",
  },
];

const elements = {
  inputDirectory: document.getElementById("inputDirectory"),
  outputPath: document.getElementById("outputPath"),
  parseMode: document.getElementById("parseMode"),
  limit: document.getElementById("limit"),
  skipErrors: document.getElementById("skipErrors"),
  resumeParse: document.getElementById("resumeParse"),
  progressInterval: document.getElementById("progressInterval"),
  modeCards: document.getElementById("modeCards"),
  parseBtn: document.getElementById("parseBtn"),
  cancelParseBtn: document.getElementById("cancelParseBtn"),
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

function makeCancelToken() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function setParseRunning(isRunning) {
  if (elements.parseBtn) {
    elements.parseBtn.disabled = isRunning;
  }
  if (elements.cancelParseBtn) {
    elements.cancelParseBtn.disabled = !isRunning || stopRequested;
  }
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

function formatFailureLines(errors) {
  if (!Array.isArray(errors) || errors.length === 0) {
    return [];
  }
  return [
    "실패 파일 상세:",
    ...errors.map((error) => {
      const position = error.index && error.total ? `${error.index}/${error.total}` : "-";
      const type = error.error_type || "Error";
      const name = error.source_name || error.source_file || "";
      return `- ${position} ${name} (${type}) ${error.error || ""}`;
    }),
  ];
}

function defaultOutputPath() {
  const inputDirectory = elements.inputDirectory.value || "";
  const mode = elements.parseMode.value || PARSE_MODES[0].key;
  return inputDirectory ? `${inputDirectory}/parsed-${mode}.json` : "";
}

function refreshOutputPath() {
  if (!elements.outputPath || elements.outputPath.dataset.touched === "true") {
    return;
  }
  elements.outputPath.value = defaultOutputPath();
}

function renderModes() {
  elements.parseMode.innerHTML = PARSE_MODES.map(
    (mode) => `<option value="${mode.key}">${mode.label}</option>`,
  ).join("");
  elements.modeCards.innerHTML = PARSE_MODES.map(
    (mode) => `
      <article class="mode-card" data-active="${mode.key === elements.parseMode.value ? "true" : "false"}">
        <div class="mode-card-top">
          <strong>${mode.label}</strong>
          <span>${mode.status}</span>
        </div>
        <code>${mode.key}</code>
        <p>${mode.description}</p>
      </article>
    `,
  ).join("");
}

function syncModeCards() {
  for (const card of elements.modeCards.querySelectorAll(".mode-card")) {
    card.dataset.active = card.querySelector("code")?.textContent === elements.parseMode.value ? "true" : "false";
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

async function loadConfig() {
  const config = await fetchJson("/api/config");
  elements.inputDirectory.value = config.html_output_directory || `${config.output_root || ""}/viewer_html`;
  refreshOutputPath();
  setStatus("저장된 HTML 폴더 기본값을 불러왔습니다.");
}

function buildPayload() {
  return {
    input_directory: elements.inputDirectory.value,
    output_path: elements.outputPath.value || defaultOutputPath(),
    mode: elements.parseMode.value,
    limit: elements.limit.value ? Number(elements.limit.value) : "",
    skip_errors: elements.skipErrors.checked,
    resume: elements.resumeParse.checked,
    progress_interval: Number(elements.progressInterval.value || 10),
    log_limit: 200,
  };
}

function formatParseResult(result) {
  const summary = result.summary || {};
  const lines = [
    `대상 HTML: ${summary.found_files || 0}`,
    `이어받은 파일: ${summary.resumed_files || 0}`,
    `파싱 성공: ${summary.parsed_files || 0}`,
    `파싱 실패: ${summary.failed_files || 0}`,
    `결과 경로: ${result.output_path || ""}`,
    "",
    ...formatFailureLines(result.errors),
  ];
  return lines.filter((line) => line !== "").join("\n");
}

function formatParseJobStatus(payload) {
  const result = payload.result || {};
  const lines = [`작업 상태: ${statusLabel(payload.status)}`];
  if (payload.error) {
    lines.push(`오류: ${payload.error}`);
  }
  if (result.summary) {
    lines.push(formatParseResult(result));
  }
  if (Array.isArray(payload.progress_log) && payload.progress_log.length) {
    lines.push("", "최근 로그", ...payload.progress_log);
  }
  return lines.filter(Boolean).join("\n");
}

async function pollParseJob(jobId) {
  try {
    const payload = await fetchJson(`/api/disclosures/html/jobs/${encodeURIComponent(jobId)}`);
    setResult(payload.result || payload);
    setStatus(formatParseJobStatus(payload), payload.status === "failed" || Number(payload.result?.summary?.failed_files || 0) > 0);
    if (payload.status === "completed" || payload.status === "failed") {
      activeJobId = "";
      activeCancelToken = "";
      stopRequested = false;
      stopJobPolling();
      setParseRunning(false);
      return;
    }
    jobPollTimer = window.setTimeout(() => pollParseJob(jobId), 1000);
  } catch (error) {
    activeJobId = "";
    activeCancelToken = "";
    stopRequested = false;
    stopJobPolling();
    setParseRunning(false);
    setStatus(error.message, true);
  }
}

async function runParse() {
  if (activeCancelToken || activeJobId) {
    return;
  }
  refreshOutputPath();
  stopJobPolling();
  const requestPayload = buildPayload();
  activeCancelToken = makeCancelToken();
  stopRequested = false;
  setParseRunning(true);
  logLines([
    `[${timestamp()}] HTML 파싱을 시작했습니다.`,
    `입력 경로: ${requestPayload.input_directory || ""}`,
    `결과 경로: ${requestPayload.output_path || ""}`,
    `파싱 모드: ${requestPayload.mode || ""}`,
    `최대 처리 건수: ${requestPayload.limit || "전체"}`,
    `이어하기: ${requestPayload.resume ? "예" : "아니오"}`,
    `진행 확인 간격: ${requestPayload.progress_interval}건`,
  ]);
  try {
    const payload = await fetchJson("/api/disclosures/html/parse/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...requestPayload, cancel_token: activeCancelToken }),
    });
    activeJobId = payload.job_id;
    setResult(payload);
    setStatus(formatParseJobStatus(payload));
    pollParseJob(activeJobId);
  } catch (error) {
    activeCancelToken = "";
    stopRequested = false;
    activeJobId = "";
    setParseRunning(false);
    throw error;
  }
}

async function cancelParse() {
  if (!activeCancelToken || stopRequested) {
    return;
  }
  stopRequested = true;
  setParseRunning(true);
  setStatus(`[${timestamp()}] HTML 파싱 중지를 요청했습니다. 현재 파일 처리가 끝나면 멈춥니다.`);
  await fetchJson("/api/disclosures/html/parse/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cancel_token: activeCancelToken }),
  });
}

renderModes();

elements.inputDirectory?.addEventListener("input", refreshOutputPath);

elements.parseMode?.addEventListener("change", () => {
  if (elements.outputPath) {
    elements.outputPath.dataset.touched = "false";
  }
  refreshOutputPath();
  syncModeCards();
});

elements.outputPath?.addEventListener("input", () => {
  elements.outputPath.dataset.touched = "true";
});

elements.parseBtn?.addEventListener("click", () => {
  runParse().catch((error) => setStatus(error.message, true));
});
elements.cancelParseBtn?.addEventListener("click", () => {
  cancelParse().catch((error) => setStatus(error.message, true));
});

bindPathSetting(
  elements.inputDirectory,
  () => ({ html_output_directory: elements.inputDirectory.value }),
  (error) => setStatus(error.message, true),
);

loadConfig().catch((error) => setStatus(error.message, true));

bindPathPicker(document, {
  onError: (error) => setStatus(error.message, true),
});
