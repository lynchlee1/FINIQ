import { bindPathPicker } from "./path-picker.js";
import { bindPathSetting } from "./settings.js";

const elements = {
  outputDirectory: document.getElementById("outputDirectory"),
  startDate: document.getElementById("startDate"),
  endDate: document.getElementById("endDate"),
  companyName: document.getElementById("companyName"),
  submitterName: document.getElementById("submitterName"),
  marketLabel: document.getElementById("marketLabel"),
  securitiesLabel: document.getElementById("securitiesLabel"),
  pageSize: document.getElementById("pageSize"),
  waitSeconds: document.getElementById("waitSeconds"),
  timeout: document.getElementById("timeout"),
  workerCount: document.getElementById("workerCount"),
  startPage: document.getElementById("startPage"),
  endPage: document.getElementById("endPage"),
  lastReportOnly: document.getElementById("lastReportOnly"),
  resumeYearly: document.getElementById("resumeYearly"),
  logLimit: document.getElementById("logLimit"),
  disclosureGroups: document.getElementById("disclosureGroups"),
  previewBtn: document.getElementById("previewBtn"),
  runBtn: document.getElementById("runBtn"),
  status: document.getElementById("status"),
  result: document.getElementById("result"),
};

let activeJobId = "";
let jobPollTimer = 0;

function setStatus(message, isError = false) {
  elements.status.textContent = message || "";
  elements.status.dataset.tone = isError ? "error" : "default";
}

function setResult(payload) {
  elements.result.textContent = JSON.stringify(payload, null, 2);
}

function formatProgressLog(payload) {
  const lines = payload?.progress_log || payload?.result?.progress_log || [];
  if (!Array.isArray(lines) || !lines.length) {
    return "";
  }
  return lines.join("\n");
}

function formatDownloadStatus(status) {
  if (!status) {
    return "";
  }
  const downloaded = Number(status.downloaded_pages || status.pagination?.downloaded_pages || 0);
  const totalPages = Number(status.total_pages || status.pagination?.total_pages || 0);
  const totalItems = Number(status.total_items || status.pagination?.total_items || 0);
  const lines = [`페이지 저장: ${downloaded}/${totalPages}`, `전체 건수: ${totalItems}`];
  if (status.complete) {
    lines.push("무결성: 완료");
  } else if (Array.isArray(status.missing_pages) && status.missing_pages.length) {
    lines.push(`누락 페이지: ${status.missing_pages.join(", ")}`);
  } else {
    lines.push(`무결성: ${status.integrity_valid ? "정상" : "확인 필요"}`);
  }
  if (Array.isArray(status.errors) && status.errors.length) {
    lines.push(...status.errors.map((error) => `오류: ${error}`));
  }
  return lines.join("\n");
}

function formatFinalSummary(payload) {
  const result = payload?.result || {};
  const lines = [`작업 상태: ${statusLabel(payload?.status)}`];

  if (payload?.error) {
    lines.push(`오류: ${payload.error}`);
  }

  if (result.mode === "yearly" && Array.isArray(result.results)) {
    const totals = result.results.reduce(
      (acc, item) => {
        const status = item.download_status || {};
        acc.pages += Number(status.downloaded_pages || status.pagination?.downloaded_pages || 0);
        acc.totalPages += Number(status.total_pages || status.pagination?.total_pages || 0);
        acc.items += Number(status.total_items || status.pagination?.total_items || 0);
        if (Array.isArray(status.missing_pages)) {
          acc.missing += status.missing_pages.length;
        }
        return acc;
      },
      { pages: 0, totalPages: 0, items: 0, missing: 0 },
    );
    lines.push(`연도 범위: ${result.ranges || result.results.length}개`);
    lines.push(`병렬 작업 수: ${result.worker_count || "-"}`);
    lines.push(`페이지 저장: ${totals.pages}/${totals.totalPages}`);
    lines.push(`전체 건수: ${totals.items}`);
    lines.push(`누락 페이지: ${totals.missing}`);
  } else {
    const statusSummary = formatDownloadStatus(result.download_status);
    if (result.output_directory || result.base_output_directory) {
      lines.push(`저장 경로: ${result.output_directory || result.base_output_directory}`);
    }
    if (statusSummary) {
      lines.push(statusSummary);
    }
    if (result.message) {
      lines.push(`메시지: ${result.message}`);
    }
  }

  const progressLog = formatProgressLog(payload);
  if (progressLog) {
    lines.push("", "최근 로그", progressLog);
  }
  return lines.filter((line) => line !== undefined && line !== null).join("\n");
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

async function fetchJson(url, init) {
  const response = await fetch(url, init);
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (!response.ok) {
    throw new Error(`${url} 실패: ${payload.error || `HTTP ${response.status}`}`);
  }
  return payload;
}

function stopJobPolling() {
  if (jobPollTimer) {
    window.clearTimeout(jobPollTimer);
    jobPollTimer = 0;
  }
}

async function pollJob(jobId) {
  try {
    const payload = await fetchJson(`/api/download/jobs/${encodeURIComponent(jobId)}`);
    setResult(payload.result || payload);
    const message = [`작업 상태: ${statusLabel(payload.status)}`, formatProgressLog(payload)]
      .filter(Boolean)
      .join("\n");
    setStatus(message, payload.status === "failed");
    if (payload.status === "completed" || payload.status === "failed") {
      activeJobId = "";
      stopJobPolling();
      setStatus(formatFinalSummary(payload), payload.status === "failed");
      return;
    }
    jobPollTimer = window.setTimeout(() => pollJob(jobId), 1000);
  } catch (error) {
    activeJobId = "";
    stopJobPolling();
    setStatus(error.message, true);
  }
}

function fillSelect(selectElement, items) {
  selectElement.innerHTML = "";
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.label;
    option.textContent = item.label;
    selectElement.appendChild(option);
  });
}

function renderDisclosureGroups(groups) {
  elements.disclosureGroups.innerHTML = "";
  groups.forEach((group) => {
    const details = document.createElement("details");
    details.dataset.suffix = group.suffix;

    const summary = document.createElement("summary");
    summary.textContent = `${group.label} (${group.items.length})`;
    details.appendChild(summary);

    const actions = document.createElement("div");
    actions.className = "disc-actions";

    const selectAll = document.createElement("button");
    selectAll.type = "button";
    selectAll.className = "action-button action-button-muted action-button-compact";
    selectAll.textContent = "전체 선택";
    selectAll.addEventListener("click", () => {
      details.querySelectorAll('input[type="checkbox"]').forEach((input) => {
        input.checked = true;
      });
    });

    const clearAll = document.createElement("button");
    clearAll.type = "button";
    clearAll.className = "action-button action-button-muted action-button-compact";
    clearAll.textContent = "전체 해제";
    clearAll.addEventListener("click", () => {
      details.querySelectorAll('input[type="checkbox"]').forEach((input) => {
        input.checked = false;
      });
    });

    actions.appendChild(selectAll);
    actions.appendChild(clearAll);
    details.appendChild(actions);

    const itemsWrap = document.createElement("div");
    itemsWrap.className = "disc-items";
    group.items.forEach((item) => {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.dataset.suffix = group.suffix;
      input.dataset.code = item.code;
      const text = document.createElement("span");
      text.textContent = item.name;
      label.appendChild(input);
      label.appendChild(text);
      itemsWrap.appendChild(label);
    });

    details.appendChild(itemsWrap);
    elements.disclosureGroups.appendChild(details);
  });
}

function collectDisclosureGroups() {
  const result = {};
  elements.disclosureGroups
    .querySelectorAll('input[type="checkbox"][data-suffix][data-code]')
    .forEach((input) => {
      if (!input.checked) {
        return;
      }
      const suffix = input.dataset.suffix;
      const code = input.dataset.code;
      if (!result[suffix]) {
        result[suffix] = [];
      }
      result[suffix].push(code);
    });
  return result;
}

function buildPayload() {
  const endPageRaw = String(elements.endPage.value || "").trim();
  return {
    mode: "yearly",
    output_directory: String(elements.outputDirectory.value || "").trim(),
    start_date: String(elements.startDate.value || "").trim(),
    end_date: String(elements.endDate.value || "").trim(),
    company_name: String(elements.companyName.value || "").trim(),
    submitter_name: String(elements.submitterName.value || "").trim(),
    market_label: String(elements.marketLabel.value || "").trim(),
    securities_label: String(elements.securitiesLabel.value || "").trim(),
    page_size: Number(elements.pageSize.value || 100),
    wait_seconds: Number(elements.waitSeconds.value || 1),
    timeout: Number(elements.timeout.value || 20),
    worker_count: Number(elements.workerCount.value || 1),
    log_limit: Number(elements.logLimit.value || 20),
    start_page: Number(elements.startPage.value || 1),
    end_page: endPageRaw ? Number(endPageRaw) : null,
    last_report_only: Boolean(elements.lastReportOnly.checked),
    resume_yearly: Boolean(elements.resumeYearly.checked),
    disclosure_type_groups: collectDisclosureGroups(),
  };
}

async function initialize() {
  setStatus("옵션을 불러오는 중...");
  const optionsPayload = await fetchJson("/api/download/options");

  fillSelect(elements.marketLabel, optionsPayload.market_types);
  fillSelect(elements.securitiesLabel, optionsPayload.securities_types);
  renderDisclosureGroups(optionsPayload.disclosure_groups);

  elements.outputDirectory.value = optionsPayload.default_output_directory || "";
  const today = new Date();
  const start = new Date(today);
  start.setDate(today.getDate() - 30);
  elements.startDate.value = start.toISOString().slice(0, 10);
  elements.endDate.value = today.toISOString().slice(0, 10);
}

bindPathSetting(
  elements.outputDirectory,
  () => ({ download_output_directory: elements.outputDirectory.value }),
  (error) => setStatus(error.message, true),
);

elements.previewBtn.addEventListener("click", async () => {
  try {
    setStatus("미리보기 생성 중...");
    const result = await fetchJson("/api/download/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    setResult(result);
    setStatus("미리보기 완료");
  } catch (error) {
    setStatus(error.message, true);
  }
});

elements.runBtn.addEventListener("click", async () => {
  try {
    stopJobPolling();
    setStatus("다운로드 작업을 시작하는 중...");
    const result = await fetchJson("/api/download/run/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    activeJobId = result.job_id;
    setResult(result);
    setStatus(`작업 상태: ${statusLabel(result.status)}\n${formatProgressLog(result)}`.trim());
    pollJob(activeJobId);
  } catch (error) {
    setStatus(error.message, true);
  }
});

initialize().catch((error) => {
  setStatus(error.message, true);
});

bindPathPicker(document, {
  onError: (error) => setStatus(error.message, true),
});
