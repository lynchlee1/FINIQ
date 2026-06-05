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
    status: "상세 필드 지원",
    description: "유무상증자 HTML에서 신주 수, 발행목적, 발행가액, 기준주가, 납입일, 상장예정일, 배정 대상자를 추출합니다.",
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
  bondRows: document.getElementById("bondRows"),
  bondDetail: document.getElementById("bondDetail"),
  changeMode: document.getElementById("changeMode"),
  loadChangeLogBtn: document.getElementById("loadChangeLogBtn"),
  changeSearch: document.getElementById("changeSearch"),
  changeShowOnlyChanges: document.getElementById("changeShowOnlyChanges"),
  changeLimit: document.getElementById("changeLimit"),
  changeLimitAll: document.getElementById("changeLimitAll"),
  changeFamilyRail: document.getElementById("changeFamilyRail"),
  changeDetailStage: document.getElementById("changeDetailStage"),
  exportExcelBtn: document.getElementById("exportExcelBtn"),
  exportLatestOnly: document.getElementById("exportLatestOnly"),
};

let activeCancelToken = "";
let stopRequested = false;
let activeJobId = "";
let jobPollTimer = 0;
let bondSummary = null;
let selectedBondKey = "";
let changeLog = null;
let selectedChangeFamilyId = "";

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

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    // Check if it's a list of targets/entities
    if (Array.isArray(value[0])) {
      return value.map((v) => v.filter((item) => item !== null && item !== "").join(" ")).join("\n");
    }
    return value.join(", ");
  }
  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

function formatValueWithField(value, fieldName) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  // Handle specific fields that need 100M unit formatting
  if (fieldName === "발행금액" || fieldName === "발행가액") {
    return formatHundredMillion(value);
  }

  // Handle list fields (like targets) that might contain amounts
  if (fieldName === "발행대상자" && Array.isArray(value)) {
    return value.map((target) => {
      if (Array.isArray(target)) {
        const name = target[0];
        const amount = target[target.length - 1];
        if (target.length > 1 && !isNaN(Number(amount))) {
          return `${name} (${formatNumber(amount)})`;
        }
        return target.join(" ");
      }
      return String(target);
    }).join("\n");
  }

  return formatValue(value);
}

function formatHundredMillion(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return String(value);
  }
  return (number / 100000000).toLocaleString("ko-KR", {
    maximumFractionDigits: 2,
  });
}

function field(record, key) {
  return record?.fields?.[key] ?? "";
}

function kindDisclosureUrl(record) {
  const acptNo = String(record?.acpt_no || "").trim();
  const docNo = String(record?.rcept_no || "").trim();
  if (!acptNo) {
    return "";
  }
  return `https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno=${encodeURIComponent(acptNo)}&docno=${encodeURIComponent(docNo)}&viewerhost=&viewerport=`;
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
  const mode = elements.parseMode?.value || elements.changeMode?.value || PARSE_MODES[0].key;
  return inputDirectory ? `${inputDirectory}/parsed-${mode}.json` : "";
}

function defaultParseResultPath(htmlDirectory, mode) {
  return htmlDirectory ? `${htmlDirectory}/parsed-${mode}.json` : "";
}

function defaultParseResultDirectory(htmlDirectory) {
  return htmlDirectory || "";
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
  if (config.html_parse_mode) {
    if (elements.parseMode) {
      elements.parseMode.value = config.html_parse_mode;
      syncModeCards();
    }
    if (elements.changeMode) {
      elements.changeMode.value = config.html_parse_mode;
    }
  }

  if (elements.inputDirectory) {
    elements.inputDirectory.value = config.html_output_directory || `${config.output_root || ""}/viewer_html`;
    if (config.html_parse_result_path) {
      elements.outputPath.value = config.html_parse_result_path;
      elements.outputPath.dataset.touched = "true";
    } else {
      refreshOutputPath();
    }
  } else if (elements.outputPath && elements.outputPath.dataset.touched !== "true") {
    const htmlDirectory = config.html_output_directory || `${config.output_root || ""}/viewer_html`;
    const mode = elements.changeMode?.value || elements.parseMode?.value || "bond_issuance";
    if (config.html_parse_result_path) {
      elements.outputPath.value = config.html_parse_result_path;
      elements.outputPath.dataset.touched = "true";
    } else {
      elements.outputPath.value = defaultParseResultPath(htmlDirectory, mode);
    }
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
  const limitValue = elements.bondLimit?.value || "20";
  const records = (bondSummary?.records || [])
    .filter((record) => bondRecordMatches(record, keyword))
    .filter((record) => bondRecordPassesCorrectionFilter(record, correctionFilter));
  if (limitValue === "all") {
    return records;
  }
  return records.slice(0, Number(limitValue || 20));
}

function renderBondRows() {
  const records = visibleBondRecords();
  if (!records.length) {
    elements.bondRows.innerHTML = `<tr><td colspan="5" class="empty-state">표시할 채권 정보가 없습니다.</td></tr>`;
    renderBondDetail(null);
    return;
  }
  if (!selectedBondKey || !records.some((record) => recordKey(record) === selectedBondKey)) {
    selectedBondKey = recordKey(records[0]);
  }
  elements.bondRows.innerHTML = records.map((record) => {
    const key = recordKey(record);
    const disclosureUrl = kindDisclosureUrl(record);
    return `
      <tr class="html-bond-row" data-key="${escapeHtml(key)}" data-selected="${key === selectedBondKey ? "true" : "false"}">
        <td class="html-bond-title">${escapeHtml(record.title || "-")}</td>
        <td>${escapeHtml(field(record, "회차") || "-")}</td>
        <td>${formatHundredMillion(field(record, "발행금액"))}</td>
        <td><code>${escapeHtml(record.rcept_no || "-")}</code></td>
        <td>${
          disclosureUrl
            ? `<a class="line-button html-bond-open-link" href="${escapeHtml(disclosureUrl)}" target="_blank" rel="noopener noreferrer">열기</a>`
            : "-"
        }</td>
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
    elements.bondDetail.innerHTML = `<div class="empty-state">행을 선택하면 채권 상세 정보가 표시됩니다.</div>`;
    return;
  }
  const detailFields = [
    ["제목", record.title || "-"],
    ["정정", correctionLabel(record)],
    ["rcept_no", record.rcept_no || "-"],
    ["acpt_no", record.acpt_no || "-"],
    ["source_file", record.source_file || "-"],
    ["상장시장", field(record, "상장시장") || "-"],
    ["회차", field(record, "회차") || "-"],
    ["발행금액(억원)", formatHundredMillion(field(record, "발행금액"))],
    ["발행목적", field(record, "발행목적") || "-"],
    ["표면이자율", field(record, "표면이자율") || "-"],
    ["만기이자율", field(record, "만기이자율") || "-"],
    ["만기일", field(record, "만기일") || "-"],
    ["할증률(%)", field(record, "할증률(%)") || "-"],
    ["행사가액", formatNumber(field(record, "행사가액"))],
    ["행사대상", field(record, "행사대상") || "-"],
    ["전환시작일", field(record, "전환시작일") || "-"],
    ["전환종료일", field(record, "전환종료일") || "-"],
    ["리픽싱(%)", field(record, "리픽싱(%)") || "-"],
    ["청약일", field(record, "청약일") || "-"],
    ["납입일", field(record, "납입일") || "-"],
    ["납입방법", field(record, "납입방법") || "-"],
  ];
  elements.bondDetail.innerHTML = `
    <div class="html-bond-detail-head">
      <span>${escapeHtml(correctionLabel(record))}</span>
      <strong>${escapeHtml(record.title || "-")}</strong>
      <code>${escapeHtml(record.family_id || record.rcept_no || "-")}</code>
    </div>
    <div class="html-bond-field-list">
      ${detailFields.map(([label, value]) => `
        <div>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `).join("")}
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

  const limitValue = elements.bondLimit?.value || "20";
  const limit = limitValue === "all" ? "" : Number(limitValue);

  const btn = elements.loadBondSummaryBtn;
  const originalText = btn ? btn.textContent : "결과 불러오기";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "불러오는 중";
  }

  try {
    const payload = await fetchJson("/api/disclosures/html/parse/bond-summary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        output_path: outputPath,
        limit: limit,
      }),
    });
    bondSummary = payload;
    selectedBondKey = "";
    renderBondRows();
    setStatus("채권 요약을 불러왔습니다.");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  }
}

function modeLabel(mode) {
  return PARSE_MODES.find((item) => item.key === mode)?.label || mode || "-";
}

function changedFieldsForFamily(family) {
  const fields = [];
  const seen = new Set();
  for (const change of family.changes || []) {
    for (const fieldChange of change.changes || []) {
      const field = String(fieldChange.field || "").trim();
      if (!field || seen.has(field)) {
        continue;
      }
      seen.add(field);
      fields.push(field);
    }
  }
  return fields;
}

function familyMatches(family, keyword) {
  if (!keyword) {
    return true;
  }
  const fieldNames = family.has_details ? changedFieldsForFamily(family) : [];
  const haystack = [
    family.family_id,
    family.title || "",
    ...(family.records || []).flatMap((record) => [record.title, record.acpt_no, record.rcept_no]),
    ...(family.changes || []).flatMap((change) => [
      change.before?.title,
      change.after?.title,
    ]),
    ...fieldNames,
  ].join(" ").toLowerCase();
  return haystack.includes(keyword);
}

function visibleChangeFamilies() {
  const keyword = String(elements.changeSearch?.value || "").trim().toLowerCase();
  const showOnlyChanges = elements.changeShowOnlyChanges?.checked ?? false;
  return (changeLog?.families || [])
    .filter((family) => {
      if (showOnlyChanges && !family.changed_fields) {
        return false;
      }
      return familyMatches(family, keyword);
    })
    .sort((left, right) => {
      const leftFields = Number(left.changed_fields || 0);
      const rightFields = Number(right.changed_fields || 0);
      if (Boolean(rightFields) !== Boolean(leftFields)) {
        return Number(Boolean(rightFields)) - Number(Boolean(leftFields));
      }
      if (rightFields !== leftFields) {
        return rightFields - leftFields;
      }
      return String(right.family_id || "").localeCompare(String(left.family_id || ""), "ko-KR");
    });
}

function _json_stable(value) {
  if (value === null || value === undefined) return "null";
  if (typeof value !== "object") return String(value);
  try {
    return JSON.stringify(value);
  } catch (e) {
    return String(value);
  }
}

function renderChangeRail() {
  const families = visibleChangeFamilies();
  if (!elements.changeFamilyRail) {
    return;
  }
  if (!changeLog) {
    elements.changeFamilyRail.innerHTML = `<div class="empty-state">파싱 결과를 불러오면 정정 패밀리별 변동 사항이 표시됩니다.</div>`;
    return;
  }
  if (!families.length) {
    elements.changeFamilyRail.innerHTML = `<div class="empty-state">표시할 정정 패밀리가 없습니다.</div>`;
    return;
  }

  elements.changeFamilyRail.innerHTML = families
    .map((family) => {
      const fields = family.has_details ? changedFieldsForFamily(family) : [];
      const metaInfo = family.has_details
        ? `<span>문서 ${formatNumber(family.record_count)}</span><span>필드 ${formatNumber(family.changed_fields)}</span>`
        : `<span>문서 ${formatNumber(family.record_count)}</span><span style="color:var(--muted)">미분석</span>`;

      return `
      <button class="change-family-card" type="button" data-family-id="${escapeHtml(
        family.family_id,
      )}" data-selected="${family.family_id === selectedChangeFamilyId ? "true" : "false"}" data-changed="${
        family.has_details && family.changed_fields > 0 ? "true" : "false"
      }">
        <strong>${escapeHtml(family.title || family.family_id || "-")}</strong>
        <div class="change-family-meta">
          ${metaInfo}
        </div>
        ${
          family.has_details
            ? fields.length > 0
              ? `<div class="change-field-chips">${fields
                  .slice(0, 3)
                  .map((f) => `<span>${escapeHtml(f)}</span>`)
                  .join("")}${fields.length > 3 ? `<span>+${fields.length - 3}</span>` : ""}</div>`
              : `<div class="change-no-diff">변동 없음</div>`
            : `<div class="change-no-diff" style="opacity:0.6">대기 중...</div>`
        }
      </button>
    `;
    })
    .join("");
}

async function loadFamilyDetail(familyId) {
  if (!changeLog || !familyId) return;

  const family = changeLog.families.find((f) => f.family_id === familyId);
  if (!family || family.has_details) {
    renderChangeDetail(family);
    return;
  }

  // Show loading in detail stage if it's the active one
  if (selectedChangeFamilyId === familyId) {
    elements.changeDetailStage.innerHTML = `
      <div class="change-matrix-empty">
        <div class="change-matrix-empty-icon">⏳</div>
        <p>${escapeHtml(family.title || family.family_id)}</p>
        <span>상세 변동 내역을 분석하고 있습니다...</span>
      </div>
    `;
  }

  try {
    const payload = await fetchJson("/api/disclosures/html/parse/change-log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        output_path: elements.outputPath.value,
        mode: elements.changeMode.value,
        family_id: familyId,
      }),
    });

    const detailedFamily = payload.families.find((f) => f.family_id === familyId);
    if (detailedFamily) {
      // Update the local cache
      Object.assign(family, detailedFamily);
      family.has_details = true;

      if (selectedChangeFamilyId === familyId) {
        renderChangeRail(); // Update rail (for severity colors/chips)
        renderChangeDetail(family);
      }
    }
  } catch (error) {
    if (selectedChangeFamilyId === familyId) {
      elements.changeDetailStage.innerHTML = `<div class="empty-state">상세 내역 로드 실패: ${escapeHtml(error.message)}</div>`;
    }
  }
}

function renderChangeDetail(family) {
  if (!elements.changeDetailStage) {
    return;
  }
  if (!family) {
    elements.changeDetailStage.innerHTML = `<div class="empty-state">패밀리를 선택하면 변경 필드와 이전/이후 값이 표시됩니다.</div>`;
    return;
  }

  const records = family.records || [];
  const changes = family.changes || [];
  const changedFieldNames = changedFieldsForFamily(family);

  // Build the Matrix
  // Matrix structure: { [fieldName]: [val1, val2, val3...] }
  const matrix = {};
  for (const field of changedFieldNames) {
    matrix[field] = new Array(records.length).fill(null);
  }

  // Populate Matrix
  // Record 0 (Original) values
  if (changes.length > 0) {
    const firstChange = changes[0];
    for (const field of changedFieldNames) {
      const fieldDelta = firstChange.changes.find((c) => c.field === field);
      if (fieldDelta) {
        matrix[field][0] = fieldDelta.before;
      }
    }
  }

  // Successive records values
  for (let i = 0; i < changes.length; i++) {
    const change = changes[i];
    const versionIndex = i + 1; // After version
    for (const field of changedFieldNames) {
      const fieldDelta = change.changes.find((c) => c.field === field);
      if (fieldDelta) {
        matrix[field][versionIndex] = fieldDelta.after;
      } else {
        // Carry forward
        matrix[field][versionIndex] = matrix[field][versionIndex - 1];
      }
    }
  }

  // If a field didn't appear in the first change, we need to backtrack it
  for (const field of changedFieldNames) {
    let firstKnownIndex = matrix[field].findIndex((v) => v !== null);
    if (firstKnownIndex > 0) {
      const value = matrix[field][firstKnownIndex];
      // This is tricky: if it wasn't in change[0].before, we don't know the exact value at V0
      // unless we assume it was the same as the first time it appeared.
      // But build_record_change only includes it if it CHANGED.
      // So if it's in change[k], it means V[k] != V[k+1].
      // If k > 0, we don't know V[0...k].
      // However, usually fields that change once tend to be present in all.
      // For now, let's fill backwards.
      for (let j = 0; j < firstKnownIndex; j++) {
        matrix[field][j] = matrix[field][firstKnownIndex];
      }
    }
  }

  const tableHeader = `
    <thead>
      <tr>
        <th class="change-matrix-field-col">변동 필드</th>
        ${records
          .map(
            (r, i) => `
          <th class="change-matrix-version-header">
            <strong>#${i + 1}</strong>
            <code>${escapeHtml(r.rcept_no || "-")}</code>
          </th>
        `,
          )
          .join("")}
      </tr>
    </thead>
  `;

  const parseKoreanDate = (dateStr) => {
    if (!dateStr || typeof dateStr !== "string") return NaN;
    const match = dateStr.match(/(\d{4})\s*[년.-]\s*(\d{1,2})\s*[월.-]\s*(\d{1,2})/);
    if (match) {
      const y = parseInt(match[1], 10);
      const m = parseInt(match[2], 10) - 1;
      const d = parseInt(match[3], 10);
      return new Date(y, m, d).getTime();
    }
    const clean = dateStr.replace(/[^\d]/g, "");
    if (clean.length === 8) {
      const y = parseInt(clean.substring(0, 4), 10);
      const m = parseInt(clean.substring(4, 6), 10) - 1;
      const d = parseInt(clean.substring(6, 8), 10);
      return new Date(y, m, d).getTime();
    }
    return NaN;
  };

  const getDaysDiff = (val1, val2) => {
    const t1 = parseKoreanDate(val1);
    const t2 = parseKoreanDate(val2);
    if (isNaN(t1) || isNaN(t2)) return Infinity;
    return Math.abs(t1 - t2) / (1000 * 60 * 60 * 24);
  };

  const tableRows = changedFieldNames
    .map((field) => {
      const values = matrix[field];
      return `
      <tr class="change-matrix-row">
        <td class="change-matrix-field-col">${escapeHtml(field)}</td>
        ${values
          .map((val, i) => {
            let isChanged = false;
            let changeType = "none";
            let indicatorHtml = "";
            
            if (i > 0 && _json_stable(val) !== _json_stable(values[i - 1])) {
              isChanged = true;
              changeType = "correction";
              
              if (field === "회차") {
                changeType = "minor";
              } else if (["만기일", "전환시작일", "전환종료일", "청약일", "납입일"].includes(field)) {
                const daysDiff = getDaysDiff(val, values[i - 1]);
                if (daysDiff <= 3) {
                  changeType = "minor";
                }
              }

              if (changeType === "correction") {
                indicatorHtml = `<span class="change-matrix-diff-indicator correction">정정</span>`;
              } else if (changeType === "minor") {
                indicatorHtml = `<span class="change-matrix-diff-indicator minor">단순변동</span>`;
              }
            }
            
            return `
            <td class="change-matrix-cell" data-changed="${isChanged ? changeType : "false"}">
              <div class="change-matrix-cell-content">
                ${indicatorHtml}
                <div class="change-matrix-value">${escapeHtml(formatValueWithField(val, field))}</div>
              </div>
            </td>
          `;
          })
          .join("")}
      </tr>
    `;
    })
    .join("");

  elements.changeDetailStage.innerHTML = `
    <div class="change-detail-head">
      <div>
        <strong>${escapeHtml(family.records?.at(-1)?.title || "-")}</strong>
        <code>${escapeHtml(family.family_id || "-")}</code>
      </div>
    </div>
    <div class="change-matrix-container">
      ${
        changedFieldNames.length > 0
          ? `
        <table class="change-matrix-table">
          ${tableHeader}
          <tbody>${tableRows}</tbody>
        </table>
      `
          : `
        <div class="change-matrix-empty">
          <div class="change-matrix-empty-icon">🔍</div>
          <p>비교 대상 필드에서 감지된 값 변동이 없습니다.</p>
          <span>모든 필드가 이전 버전과 동일합니다.</span>
        </div>
      `
      }
    </div>
  `;
}

async function loadChangeLog() {
  const outputPath = elements.outputPath?.value || "";
  if (!outputPath) {
    setStatus("파싱 결과 경로가 필요합니다.", true);
    return;
  }
  const btn = elements.loadChangeLogBtn;
  const originalText = btn ? btn.textContent : "변동 불러오기";

  // Clear existing state and show loading in UI
  changeLog = null;
  selectedChangeFamilyId = "";
  if (elements.changeFamilyRail) {
    elements.changeFamilyRail.innerHTML = `<div class="empty-state">변동 기록 목록을 불러오는 중...</div>`;
  }
  if (elements.changeDetailStage) {
    elements.changeDetailStage.innerHTML = `<div class="empty-state">불러오는 중...</div>`;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = "불러오는 중";
  }

  try {
    const limitValue = elements.changeLimit ? elements.changeLimit.value : "50";
    const limit = (limitValue === "" || limitValue === undefined) ? null : Number(limitValue);

    // Phase 1: Load summaries only (Fast)
    const payload = await fetchJson("/api/disclosures/html/parse/change-log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        output_path: outputPath,
        mode: elements.changeMode?.value || "",
        summary_only: true,
        limit: limit,
      }),
    });
    changeLog = payload;
    renderChangeRail();
    setStatus(`${modeLabel(payload.mode)} 목록 ${payload.families.length}건을 불러왔습니다.`);

    // Phase 2: Automatically load the first family if available
    if (payload.families.length > 0) {
      selectedChangeFamilyId = payload.families[0].family_id;
      loadFamilyDetail(selectedChangeFamilyId);
    }
  } catch (error) {
    setStatus(error.message, true);
    if (elements.changeFamilyRail) {
      elements.changeFamilyRail.innerHTML = `<div class="empty-state">목록을 불러오지 못했습니다.</div>`;
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  }
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
  savePathSetting({ html_parse_mode: elements.parseMode.value }).catch((error) => setStatus(error.message, true));
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
elements.bondLimit?.addEventListener("change", () => {
  loadBondSummary().catch((error) => setStatus(error.message, true));
});
elements.changeMode?.addEventListener("change", () => {
  if (elements.outputPath) {
    elements.outputPath.dataset.touched = "false";
  }
  refreshOutputPath();
  changeLog = null;
  selectedChangeFamilyId = "";
  renderChangeRail();
  savePathSetting({ html_parse_mode: elements.changeMode.value }).catch((error) => setStatus(error.message, true));
});
elements.loadChangeLogBtn?.addEventListener("click", () => {
  loadChangeLog().catch((error) => setStatus(error.message, true));
});
elements.changeSearch?.addEventListener("input", renderChangeRail);
elements.changeShowOnlyChanges?.addEventListener("change", renderChangeRail);
elements.changeLimitAll?.addEventListener("click", () => {
  if (elements.changeLimit) {
    elements.changeLimit.value = "";
    loadChangeLog().catch((error) => setStatus(error.message, true));
  }
});
elements.changeLimit?.addEventListener("change", () => {
  loadChangeLog().catch((error) => setStatus(error.message, true));
});
elements.changeFamilyRail?.addEventListener("click", (event) => {
  const card = event.target.closest(".change-family-card");
  if (!card) {
    return;
  }
  selectedChangeFamilyId = card.dataset.familyId || "";
  renderChangeRail();
  loadFamilyDetail(selectedChangeFamilyId);
});
elements.bondRows?.addEventListener("click", (event) => {
  if (event.target.closest("a")) {
    return;
  }
  const row = event.target.closest(".html-bond-row");
  if (!row) {
    return;
  }
  selectedBondKey = row.dataset.key || "";
  renderBondRows();
});

elements.exportExcelBtn?.addEventListener("click", () => {
  const outputPath = elements.outputPath?.value || "";
  const mode = elements.parseMode?.value || elements.changeMode?.value || "";
  const latestOnly = elements.exportLatestOnly?.checked || false;
  if (!outputPath) {
    setStatus("결과 경로가 필요합니다.", true);
    return;
  }
  const params = new URLSearchParams({
    output_path: outputPath,
    mode: mode,
    latest_only: latestOnly,
  });
  window.location.href = `/api/disclosures/html/parse/export.xlsx?${params.toString()}`;
});

if (elements.inputDirectory) {
  bindPathSetting(
    elements.inputDirectory,
    () => ({ html_output_directory: elements.inputDirectory.value }),
    (error) => setStatus(error.message, true),
  );
}

if (elements.outputPath) {
  bindPathSetting(
    elements.outputPath,
    () => ({ html_parse_result_path: elements.outputPath.value }),
    (error) => setStatus(error.message, true),
  );
}

loadConfig().catch((error) => setStatus(error.message, true));

bindPathPicker(document, {
  onError: (error) => setStatus(error.message, true),
});
