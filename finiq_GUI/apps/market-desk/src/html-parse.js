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
  loadBondSummaryBtn: document.getElementById("loadBondSummaryBtn"),
  bondSearch: document.getElementById("bondSearch"),
  bondCorrectionFilter: document.getElementById("bondCorrectionFilter"),
  bondLimit: document.getElementById("bondLimit"),
  bondSummaryCards: document.getElementById("bondSummaryCards"),
  bondRows: document.getElementById("bondRows"),
  bondDetail: document.getElementById("bondDetail"),
};

let activeCancelToken = "";
let stopRequested = false;
let activeJobId = "";
let jobPollTimer = 0;
let bondSummary = null;
let selectedBondKey = "";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("ko-KR") : String(value);
}

function field(record, key) {
  return record?.fields?.[key] ?? "";
}

function recordKey(record) {
  return `${record.rcept_no || ""}:${record.acpt_no || ""}:${record.index || ""}`;
}

function correctionLabel(record) {
  const current = Number(record.current_sequence ?? 0);
  const total = Number(record.family_member_count || 0);
  if (!total || total <= 1) {
    return "-";
  }
  return `${current + 1}/${total}`;
}

function targetText(record) {
  const targets = field(record, "발행대상자");
  if (!Array.isArray(targets)) {
    return "";
  }
  return targets.map((target) => Array.isArray(target) ? target.join(" ") : String(target || "")).join(" ");
}

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
  const inputDirectory = elements.inputDirectory?.value || "";
  const mode = elements.parseMode?.value || PARSE_MODES[0].key;
  return inputDirectory ? `${inputDirectory}/parsed-${mode}.json` : "";
}

function refreshOutputPath() {
  if (!elements.outputPath || elements.outputPath.dataset.touched === "true") {
    return;
  }
  elements.outputPath.value = defaultOutputPath();
}

function renderModes() {
  if (!elements.parseMode || !elements.modeCards) {
    return;
  }
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
  if (!elements.parseMode || !elements.modeCards) {
    return;
  }
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
  if (elements.inputDirectory) {
    elements.inputDirectory.value = config.html_output_directory || `${config.output_root || ""}/viewer_html`;
    refreshOutputPath();
  } else if (elements.outputPath && elements.outputPath.dataset.touched !== "true") {
    const htmlDirectory = config.html_output_directory || `${config.output_root || ""}/viewer_html`;
    elements.outputPath.value = htmlDirectory ? `${htmlDirectory}/parsed-bond_issuance.json` : "";
  }
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

function renderBondSummaryCards(payload, visibleCount) {
  const summary = payload?.summary || {};
  const cards = [
    ["표시", visibleCount],
    ["전체", summary.records || 0],
    ["정정 Family", summary.families || 0],
    ["최신 공시", summary.latest_records || 0],
  ];
  elements.bondSummaryCards.innerHTML = cards.map(([label, value]) => `
    <div class="summary-card">
      <span>${escapeHtml(label)}</span>
      <strong>${formatNumber(value)}</strong>
    </div>
  `).join("");
}

function bondRecordMatches(record, keyword) {
  if (!keyword) {
    return true;
  }
  const haystack = [
    record.title,
    record.acpt_no,
    record.rcept_no,
    record.family_id,
    field(record, "회차"),
    field(record, "납입일"),
    targetText(record),
  ].join(" ").toLowerCase();
  return haystack.includes(keyword);
}

function bondRecordPassesCorrectionFilter(record, filterValue) {
  const current = Number(record.current_sequence ?? 0);
  const total = Number(record.family_member_count || 0);
  if (filterValue === "corrected") {
    return total > 1;
  }
  if (filterValue === "current") {
    return current > 0;
  }
  if (filterValue === "latest") {
    return total > 0 && current === total - 1;
  }
  return true;
}

function visibleBondRecords() {
  const keyword = String(elements.bondSearch?.value || "").trim().toLowerCase();
  const correctionFilter = elements.bondCorrectionFilter?.value || "all";
  const limitValue = elements.bondLimit?.value || "100";
  const records = (bondSummary?.records || [])
    .filter((record) => bondRecordMatches(record, keyword))
    .filter((record) => bondRecordPassesCorrectionFilter(record, correctionFilter));
  if (limitValue === "all") {
    return records;
  }
  return records.slice(0, Number(limitValue || 100));
}

function renderBondRows() {
  const records = visibleBondRecords();
  renderBondSummaryCards(bondSummary, records.length);
  if (!records.length) {
    elements.bondRows.innerHTML = `<tr><td colspan="10" class="empty-state">표시할 채권 정보가 없습니다.</td></tr>`;
    renderBondDetail(null);
    return;
  }
  if (!selectedBondKey || !records.some((record) => recordKey(record) === selectedBondKey)) {
    selectedBondKey = recordKey(records[0]);
  }
  elements.bondRows.innerHTML = records.map((record) => {
    const key = recordKey(record);
    return `
      <tr class="html-bond-row" data-key="${escapeHtml(key)}" data-selected="${key === selectedBondKey ? "true" : "false"}">
        <td>${formatNumber(record.index)}</td>
        <td class="html-bond-title">${escapeHtml(record.title || "-")}</td>
        <td>${escapeHtml(field(record, "회차") || "-")}</td>
        <td>${formatNumber(field(record, "발행금액"))}</td>
        <td>${formatNumber(field(record, "행사가액"))}</td>
        <td>${formatNumber(field(record, "리픽싱(%)"))}</td>
        <td>${escapeHtml(field(record, "납입일") || "-")}</td>
        <td>${escapeHtml(correctionLabel(record))}</td>
        <td><code>${escapeHtml(record.rcept_no || "-")}</code></td>
        <td><code>${escapeHtml(record.acpt_no || "-")}</code></td>
      </tr>
    `;
  }).join("");
  renderBondDetail(records.find((record) => recordKey(record) === selectedBondKey) || records[0]);
}

function renderTargetList(record) {
  const targets = field(record, "발행대상자");
  if (!Array.isArray(targets) || targets.length === 0) {
    return `<div class="empty-state">발행 대상자 정보가 없습니다.</div>`;
  }
  return `
    <div class="html-bond-targets">
      ${targets.map((target) => {
        const name = Array.isArray(target) ? target[0] : target;
        const amount = Array.isArray(target) ? target[target.length - 1] : "";
        return `
          <div class="html-bond-target">
            <span>${escapeHtml(name || "-")}</span>
            <strong>${formatNumber(amount)}</strong>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderCorrectionTimeline(record) {
  const family = bondSummary?.families?.[record.family_id];
  const members = Array.isArray(family?.members) ? family.members : [];
  if (!members.length) {
    return `<div class="empty-state">정정공시 기록이 없습니다.</div>`;
  }
  return `
    <div class="html-correction-timeline">
      ${members.map((member) => `
        <div class="html-correction-step" data-current="${member.sequence === record.current_sequence ? "true" : "false"}">
          <span>${formatNumber(Number(member.sequence || 0) + 1)}</span>
          <div>
            <strong><code>${escapeHtml(member.rcept_no || "-")}</code></strong>
            <em>acpt_no ${escapeHtml(member.acpt_no || "-")}</em>
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderBondDetail(record) {
  if (!record) {
    elements.bondDetail.innerHTML = `<div class="empty-state">행을 선택하면 정정공시 기록과 발행 대상자가 표시됩니다.</div>`;
    return;
  }
  elements.bondDetail.innerHTML = `
    <div class="html-bond-detail-head">
      <span>${escapeHtml(correctionLabel(record))}</span>
      <strong>${escapeHtml(record.title || "-")}</strong>
      <code>${escapeHtml(record.family_id || record.rcept_no || "-")}</code>
    </div>
    <div class="html-bond-field-grid">
      <div><span>만기일</span><strong>${escapeHtml(field(record, "만기일") || "-")}</strong></div>
      <div><span>전환기간</span><strong>${escapeHtml(field(record, "전환시작일") || "-")} ~ ${escapeHtml(field(record, "전환종료일") || "-")}</strong></div>
      <div><span>납입방법</span><strong>${escapeHtml(field(record, "납입방법") || "-")}</strong></div>
      <div><span>행사대상</span><strong>${escapeHtml(field(record, "행사대상") || "-")}</strong></div>
    </div>
    <div class="html-bond-section-title">정정공시 기록</div>
    ${renderCorrectionTimeline(record)}
    <div class="html-bond-section-title">발행 대상자</div>
    ${renderTargetList(record)}
  `;
}

async function loadBondSummary() {
  if (elements.inputDirectory) {
    refreshOutputPath();
  }
  const outputPath = elements.outputPath.value || defaultOutputPath();
  if (!outputPath) {
    setStatus("파싱 결과 경로가 필요합니다.", true);
    return;
  }
  const payload = await fetchJson("/api/disclosures/html/parse/bond-summary", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ output_path: outputPath }),
  });
  bondSummary = payload;
  selectedBondKey = "";
  renderBondRows();
  setStatus(`채권 요약 ${payload.summary?.records || 0}건을 불러왔습니다.`);
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

if (elements.parseMode) {
  renderModes();
}

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
elements.loadBondSummaryBtn?.addEventListener("click", () => {
  loadBondSummary().catch((error) => setStatus(error.message, true));
});
elements.bondSearch?.addEventListener("input", renderBondRows);
elements.bondCorrectionFilter?.addEventListener("change", renderBondRows);
elements.bondLimit?.addEventListener("change", renderBondRows);
elements.bondRows?.addEventListener("click", (event) => {
  const row = event.target.closest(".html-bond-row");
  if (!row) {
    return;
  }
  selectedBondKey = row.dataset.key || "";
  renderBondRows();
});

if (elements.inputDirectory) {
  bindPathSetting(
    elements.inputDirectory,
    () => ({ html_output_directory: elements.inputDirectory.value }),
    (error) => setStatus(error.message, true),
  );
}

loadConfig().catch((error) => setStatus(error.message, true));

bindPathPicker(document, {
  onError: (error) => setStatus(error.message, true),
});
