import { bindPathPicker } from "./path-picker.js";
import { bindPathSetting } from "./settings.js";

const HTML_DOWNLOAD_STORAGE_KEY = "finiq.kind.filteredDisclosures";
const CONDITION_PRESET_STORAGE_KEY = "finiq.kind.conditionPresets";

const elements = {
  rootDirectory: document.getElementById("rootDirectory"),
  htmlTransferPath: document.getElementById("htmlTransferPath"),
  conditionBlocks: document.getElementById("conditionBlocks"),
  conditionPreview: document.getElementById("conditionPreview"),
  addConditionBtn: document.getElementById("addConditionBtn"),
  presetSelect: document.getElementById("presetSelect"),
  presetName: document.getElementById("presetName"),
  loadPresetBtn: document.getElementById("loadPresetBtn"),
  savePresetBtn: document.getElementById("savePresetBtn"),
  deletePresetBtn: document.getElementById("deletePresetBtn"),
  filterWorkers: document.getElementById("filterWorkers"),
  progressInterval: document.getElementById("progressInterval"),
  filterBtn: document.getElementById("filterBtn"),
  cancelFilterBtn: document.getElementById("cancelFilterBtn"),
  status: document.getElementById("status"),
  disclosureTableBody: document.getElementById("disclosureTableBody"),
  prevPageBtn: document.getElementById("prevPageBtn"),
  nextPageBtn: document.getElementById("nextPageBtn"),
  pageInfo: document.getElementById("pageInfo"),
};

const RESULT_PAGE_SIZE = 20;

let latestPayload = null;
let resultPage = 0;
let progressLines = [];
let filterAbortController = null;
let conditionBlocks = [defaultConditionBlock()];

const fieldOptions = [
  ["title", "제목"],
  ["company_name", "회사명"],
  ["submitter", "제출인"],
  ["market", "시장"],
  ["disclosed_date", "공시일"],
  ["acpt_no", "접수번호"],
  ["company_id", "회사코드"],
];

const operatorOptions = [
  ["contains", "contains"],
  ["not_contains", "not contains"],
  ["exact_match", "exact match"],
  ["equals", "equals"],
  ["not_equals", "not equals"],
  ["starts_with", "starts with"],
  ["ends_with", "ends with"],
  ["in", "in"],
  ["before", "before"],
  ["after", "after"],
  ["on_or_before", "<="],
  ["on_or_after", ">="],
  ["between", "between"],
  ["exists", "exists"],
  ["empty", "is empty"],
];

function defaultConditionBlock() {
  return {
    connector: "",
    open_count: 0,
    not: false,
    ignore_spaces: false,
    clean_search: false,
    field: "title",
    operator: "contains",
    value: "",
    close_count: 0,
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setStatus(message, isError = false) {
  elements.status.textContent = message || "";
  elements.status.dataset.tone = isError ? "error" : "default";
}

function appendStatus(message, isError = false) {
  progressLines.push(message);
  progressLines = progressLines.slice(-80);
  setStatus(progressLines.join("\n"), isError);
}

function storeHtmlDownloadTransferPath(payload) {
  const transfer = payload?.html_download_transfer || {};
  const transferPath = String(transfer.path || "").trim();
  if (!transferPath) {
    sessionStorage.removeItem(HTML_DOWNLOAD_STORAGE_KEY);
    return null;
  }
  const reference = {
    source_json_path: transferPath,
    acpt_numbers: Number(transfer.acpt_numbers || 0),
  };
  sessionStorage.setItem(HTML_DOWNLOAD_STORAGE_KEY, JSON.stringify(reference));
  return reference;
}

function quoteExpressionTerm(value) {
  const rawValue = String(value || "").trim();
  if (!rawValue) {
    return "";
  }
  return `"${rawValue.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

function syncExpressionFromBlocks() {
  const expression = conditionBlocks
    .map((block, index) => {
      const term = quoteExpressionTerm(block.value);
      if (!term) {
        return "";
      }
      const parts = [];
      if (index > 0) {
        parts.push(block.connector || "AND");
      }
      if (block.open_count) {
        parts.push("(".repeat(Number(block.open_count)));
      }
      if (block.not) {
        parts.push("NOT");
      }
      parts.push(`[${fieldLabel(block.field)} ${operatorLabel(block.operator)} ${term}]`);
      if (block.close_count) {
        parts.push(")".repeat(Number(block.close_count)));
      }
      return parts.join(" ");
    })
    .filter(Boolean)
    .join(" ");
  renderConditionPreview(expression);
}

function optionMarkup(options, selectedValue) {
  return options
    .map(([value, label]) => `<option value="${value}" ${value === selectedValue ? "selected" : ""}>${label}</option>`)
    .join("");
}

function fieldLabel(value) {
  return fieldOptions.find(([key]) => key === value)?.[1] || value || "필드";
}

function operatorLabel(value) {
  return operatorOptions.find(([key]) => key === value)?.[1] || value || "operator";
}

function renderConditionPreview() {
  const html = conditionBlocks
    .map((block, index) => {
      if (!String(block.value || "").trim() && !["exists", "empty"].includes(block.operator)) {
        return "";
      }
      const connector = index > 0 ? `<span class="logic-chip">${escapeHtml(block.connector || "AND")}</span>` : "";
      const open = Number(block.open_count || 0)
        ? `<span class="paren-chip">${"(".repeat(Number(block.open_count))}</span>`
        : "";
      const not = block.not ? '<span class="logic-chip">NOT</span>' : "";
      const space = block.ignore_spaces ? '<span class="space-chip">공백무시</span>' : "";
      const cleanSearch = block.clean_search ? '<span class="space-chip">Clean</span>' : "";
      const close = Number(block.close_count || 0)
        ? `<span class="paren-chip">${")".repeat(Number(block.close_count))}</span>`
        : "";
      const value = ["exists", "empty"].includes(block.operator) ? "" : `<strong>${escapeHtml(block.value)}</strong>`;
      return `
        ${connector}
        ${open}
        ${not}
        <span class="filter-chip">
          <span>${escapeHtml(fieldLabel(block.field))}</span>
          <em>${escapeHtml(operatorLabel(block.operator))}</em>
          ${value}
          ${space}
          ${cleanSearch}
        </span>
        ${close}
      `;
    })
    .filter(Boolean)
    .join("");
  elements.conditionPreview.innerHTML = html || '<span class="empty-state">조건 블록을 추가하세요.</span>';
}

function renderConditionBlocks() {
  elements.conditionBlocks.innerHTML = conditionBlocks
    .map(
      (block, index) => `
        <div class="condition-block" data-index="${index}">
          <div class="condition-lead">
            <select class="condition-connector" ${index === 0 ? "disabled" : ""} aria-label="연결 조건">
              <option value="" ${index === 0 ? "selected" : ""}>START</option>
              <option value="AND" ${index > 0 && block.connector === "AND" ? "selected" : ""}>AND</option>
              <option value="OR" ${index > 0 && block.connector === "OR" ? "selected" : ""}>OR</option>
            </select>
          </div>
          <div class="condition-clause">
            <input class="group-toggle condition-paren-input ${block.open_count ? "active" : ""}" data-group-toggle="open" type="text" value="${block.open_count ? "(".repeat(Number(block.open_count)) : ""}" aria-label="그룹 시작" />
            <label class="condition-not">
              <input class="condition-not-input" type="checkbox" ${block.not ? "checked" : ""} />
              NOT
            </label>
            <label class="condition-space">
              <input class="condition-ignore-spaces-input" type="checkbox" ${block.ignore_spaces ? "checked" : ""} />
              공백무시
            </label>
            <label class="condition-space">
              <input class="condition-clean-search-input" type="checkbox" ${block.clean_search ? "checked" : ""} />
              Clean
            </label>
            <select class="condition-field" aria-label="필드">${optionMarkup(fieldOptions, block.field)}</select>
            <select class="condition-operator" aria-label="연산자">${optionMarkup(operatorOptions, block.operator)}</select>
            <input class="condition-value" type="text" value="${escapeHtml(block.value)}" placeholder="값" />
            <input class="group-toggle condition-paren-input ${block.close_count ? "active" : ""}" data-group-toggle="close" type="text" value="${block.close_count ? ")".repeat(Number(block.close_count)) : ""}" aria-label="그룹 끝" />
          </div>
          <button class="condition-remove" type="button" aria-label="조건 삭제">삭제</button>
        </div>
      `,
    )
    .join("");
  syncExpressionFromBlocks();
}

function normalizeParenCount(value, paren) {
  if (typeof value === "string" && /^[()]+$/.test(value.trim())) {
    return [...value.trim()].filter((char) => char === paren).length;
  }
  const count = Number(value || 0);
  return Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
}

function normalizeConditionBlocks(blocks) {
  const normalized = Array.isArray(blocks)
    ? blocks
        .map((block, index) => {
          const connector = String(block?.connector || "AND").toUpperCase();
          return {
            ...defaultConditionBlock(),
            connector: index === 0 || !["AND", "OR"].includes(connector) ? "" : connector,
            open_count: normalizeParenCount(block?.open_count, "("),
            not: Boolean(block?.not),
            ignore_spaces: Boolean(block?.ignore_spaces),
            clean_search: Boolean(block?.clean_search),
            field: fieldOptions.some(([value]) => value === block?.field) ? block.field : "title",
            operator: operatorOptions.some(([value]) => value === block?.operator) ? block.operator : "contains",
            value: String(block?.value || ""),
            close_count: normalizeParenCount(block?.close_count, ")"),
          };
        })
        .filter((block) => block.value.trim() || ["exists", "empty"].includes(block.operator))
    : [];
  return normalized.length ? normalized : [defaultConditionBlock()];
}

function readConditionBlocksFromDom() {
  const rows = [...(elements.conditionBlocks?.querySelectorAll(".condition-block") || [])];
  if (!rows.length) {
    return conditionBlocks;
  }
  conditionBlocks = rows.map((row, index) => {
    const connector = String(row.querySelector(".condition-connector")?.value || "AND").toUpperCase();
    const field = row.querySelector(".condition-field")?.value || "title";
    const operator = row.querySelector(".condition-operator")?.value || "contains";
    return {
      ...defaultConditionBlock(),
      connector: index === 0 || !["AND", "OR"].includes(connector) ? "" : connector,
      open_count: normalizeParenCount(row.querySelector('[data-group-toggle="open"]')?.value, "("),
      not: Boolean(row.querySelector(".condition-not-input")?.checked),
      ignore_spaces: Boolean(row.querySelector(".condition-ignore-spaces-input")?.checked),
      clean_search: Boolean(row.querySelector(".condition-clean-search-input")?.checked),
      field: fieldOptions.some(([value]) => value === field) ? field : "title",
      operator: operatorOptions.some(([value]) => value === operator) ? operator : "contains",
      value: row.querySelector(".condition-value")?.value || "",
      close_count: normalizeParenCount(row.querySelector('[data-group-toggle="close"]')?.value, ")"),
    };
  });
  return conditionBlocks;
}

function readConditionPresets() {
  try {
    const parsed = JSON.parse(localStorage.getItem(CONDITION_PRESET_STORAGE_KEY) || "[]");
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .map((preset) => ({
        name: String(preset?.name || "").trim(),
        condition_blocks: normalizeConditionBlocks(preset?.condition_blocks),
      }))
      .filter((preset) => preset.name)
      .sort((a, b) => a.name.localeCompare(b.name, "ko"));
  } catch {
    return [];
  }
}

function writeConditionPresets(presets) {
  localStorage.setItem(CONDITION_PRESET_STORAGE_KEY, JSON.stringify(presets));
}

function renderPresetOptions(selectedName = elements.presetSelect?.value || "") {
  if (!elements.presetSelect) {
    return;
  }
  const presets = readConditionPresets();
  elements.presetSelect.innerHTML = [
    '<option value="">프리셋 선택</option>',
    ...presets.map((preset) => `<option value="${escapeHtml(preset.name)}">${escapeHtml(preset.name)}</option>`),
  ].join("");
  elements.presetSelect.value = presets.some((preset) => preset.name === selectedName) ? selectedName : "";
  if (elements.loadPresetBtn) {
    elements.loadPresetBtn.disabled = !elements.presetSelect.value;
  }
  if (elements.deletePresetBtn) {
    elements.deletePresetBtn.disabled = !elements.presetSelect.value;
  }
}

function selectedPresetName() {
  return String(elements.presetSelect?.value || "").trim();
}

function applyConditionPreset(name) {
  const preset = readConditionPresets().find((item) => item.name === name);
  if (!preset) {
    setStatus("선택한 프리셋을 찾을 수 없습니다.", true);
    renderPresetOptions();
    return;
  }
  conditionBlocks = normalizeConditionBlocks(preset.condition_blocks);
  renderConditionBlocks();
  if (elements.presetName) {
    elements.presetName.value = preset.name;
  }
  setStatus(`조건검색 프리셋을 불러왔습니다: ${preset.name}`);
}

function saveConditionPreset() {
  const name = String(elements.presetName?.value || "").trim();
  if (!name) {
    setStatus("저장할 프리셋 이름을 입력하세요.", true);
    elements.presetName?.focus();
    return;
  }
  const presets = readConditionPresets().filter((preset) => preset.name !== name);
  presets.push({
    name,
    condition_blocks: normalizeConditionBlocks(readConditionBlocksFromDom()),
  });
  writeConditionPresets(presets.sort((a, b) => a.name.localeCompare(b.name, "ko")));
  renderPresetOptions(name);
  setStatus(`조건검색 프리셋을 저장했습니다: ${name}`);
}

function deleteConditionPreset() {
  const name = selectedPresetName();
  if (!name) {
    return;
  }
  writeConditionPresets(readConditionPresets().filter((preset) => preset.name !== name));
  if (elements.presetName?.value === name) {
    elements.presetName.value = "";
  }
  renderPresetOptions();
  setStatus(`조건검색 프리셋을 삭제했습니다: ${name}`);
}

function addCondition(block = {}) {
  conditionBlocks.push({
    ...defaultConditionBlock(),
    connector: conditionBlocks.length ? "AND" : "",
    ...block,
  });
  renderConditionBlocks();
}

function totalResultPages(disclosures = latestPayload?.disclosures || []) {
  return Math.max(1, Math.ceil(disclosures.length / RESULT_PAGE_SIZE));
}

function updatePager(disclosures = latestPayload?.disclosures || []) {
  const totalPages = totalResultPages(disclosures);
  resultPage = Math.min(Math.max(resultPage, 0), totalPages - 1);
  if (elements.pageInfo) {
    elements.pageInfo.textContent = disclosures.length ? `${resultPage + 1} / ${totalPages}` : "0 / 0";
  }
  if (elements.prevPageBtn) {
    elements.prevPageBtn.disabled = !disclosures.length || resultPage <= 0;
  }
  if (elements.nextPageBtn) {
    elements.nextPageBtn.disabled = !disclosures.length || resultPage >= totalPages - 1;
  }
}

function setResult(payload) {
  latestPayload = payload;
  resultPage = 0;
  const transferReference = storeHtmlDownloadTransferPath(payload);
  renderTable(payload.disclosures || []);
  return transferReference;
}

function viewerUrl(acptNo) {
  return `https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno=${encodeURIComponent(acptNo)}&docno=&viewerhost=&viewerport=`;
}

function renderTable(disclosures) {
  if (!disclosures.length) {
    elements.disclosureTableBody.innerHTML = '<tr><td colspan="6" class="empty-state">필터 결과가 없습니다.</td></tr>';
    updatePager(disclosures);
    return;
  }
  updatePager(disclosures);
  const pageRows = disclosures.slice(resultPage * RESULT_PAGE_SIZE, (resultPage + 1) * RESULT_PAGE_SIZE);
  elements.disclosureTableBody.innerHTML = pageRows
    .map((disclosure) => {
      const acptNo = String(disclosure.acpt_no || disclosure.acptno || "");
      const title = disclosure.title || "";
      const titleCell = acptNo
        ? `<a class="table-link" href="${viewerUrl(acptNo)}" target="_blank" rel="noreferrer">${escapeHtml(title)}</a>`
        : escapeHtml(title);
      return `
        <tr>
          <td>${escapeHtml(String(disclosure.disclosed_at || "").split(" ", 1)[0])}</td>
          <td>${escapeHtml(disclosure.company_name || "")}</td>
          <td>${escapeHtml(disclosure.market || "")}</td>
          <td>${titleCell}</td>
          <td>${escapeHtml(disclosure.submitter || "")}</td>
          <td>${escapeHtml(acptNo)}</td>
        </tr>
      `;
    })
    .join("");
}

async function fetchJson(url, init) {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function buildPayload() {
  readConditionBlocksFromDom();
  return {
    root_directory: elements.rootDirectory.value,
    html_transfer_path: elements.htmlTransferPath?.value || "",
    filter_blocks: conditionBlocks,
    title_expression: "",
    limit_unlimited: true,
    include_html_download_acpt_numbers: true,
    filter_workers: Number(elements.filterWorkers?.value || 8),
    progress_interval: Number(elements.progressInterval?.value || 100),
  };
}

function formatProgress(progress) {
  if (progress.message) {
    return progress.message;
  }
  const unitLabel = progress.unit_label || "항목";
  const records = Number(progress.records || 0).toLocaleString("ko-KR");
  const completed = Number(progress.completed || 0).toLocaleString("ko-KR");
  const total = Number(progress.total || 0).toLocaleString("ko-KR");
  return `${unitLabel} ${completed}/${total} 완료 · 누적 ${records}건`;
}

async function fetchJsonStream(url, init, onProgress) {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...(init?.headers || {}),
      Accept: "application/x-ndjson",
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  if (!response.body) {
    return fetchJson(url, init);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) {
        continue;
      }
      const event = JSON.parse(line);
      if (event.type === "progress") {
        onProgress(event.progress || {});
      } else if (event.type === "result") {
        return event.payload;
      } else if (event.type === "error") {
        throw new Error(event.error || "필터 실행 중 오류가 발생했습니다.");
      }
    }
  }
  if (buffer.trim()) {
    const event = JSON.parse(buffer);
    if (event.type === "result") {
      return event.payload;
    }
    if (event.type === "error") {
      throw new Error(event.error || "필터 실행 중 오류가 발생했습니다.");
    }
  }
  throw new Error("필터 결과를 받지 못했습니다.");
}

async function loadConfig() {
  const config = await fetchJson("/api/config");
  elements.rootDirectory.value = config.output_root || "";
  if (elements.htmlTransferPath) {
    elements.htmlTransferPath.value = config.html_transfer_directory || `${config.output_root || ""}/.finiq/transfers`;
  }
  setStatus("공시 소스 폴더를 불러왔습니다.");
}

function setFilterRunning(isRunning) {
  if (elements.filterBtn) {
    elements.filterBtn.disabled = isRunning;
  }
  if (elements.cancelFilterBtn) {
    elements.cancelFilterBtn.disabled = !isRunning;
  }
}

async function runFilter() {
  if (filterAbortController) {
    return;
  }
  filterAbortController = new AbortController();
  setFilterRunning(true);
  progressLines = [];
  appendStatus("필터링 중...");
  try {
    const payload = await fetchJsonStream("/api/disclosures/filter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
      signal: filterAbortController.signal,
    }, (progress) => appendStatus(formatProgress(progress)));
    const transferReference = setResult(payload);
    const transferMessage = transferReference
      ? `접수번호 ${transferReference.acpt_numbers}개를 저장했습니다: ${transferReference.source_json_path}`
      : "저장 파일을 만들지 못했습니다.";
    appendStatus(`매칭 ${payload.summary?.matched_disclosures || 0}건 중 ${payload.summary?.returned_disclosures || 0}건을 표시했고, ${transferMessage}`, !transferReference);
  } catch (error) {
    if (error.name === "AbortError") {
      appendStatus("필터링을 중단했습니다.", true);
      return;
    }
    throw error;
  } finally {
    filterAbortController = null;
    setFilterRunning(false);
  }
}

function moveResultPage(offset) {
  if (!latestPayload) {
    return;
  }
  resultPage += offset;
  renderTable(latestPayload.disclosures || []);
}

elements.conditionBlocks?.addEventListener("input", (event) => {
  const row = event.target.closest?.(".condition-block");
  if (!row) {
    return;
  }
  const index = Number(row.dataset.index);
  if (!Number.isInteger(index) || !conditionBlocks[index]) {
    return;
  }
  if (event.target.matches?.(".condition-paren-input")) {
    const paren = event.target.dataset.groupToggle === "open" ? "(" : ")";
    const value = [...event.target.value].filter((char) => char === paren).join("");
    const key = paren === "(" ? "open_count" : "close_count";
    conditionBlocks[index][key] = value.length;
    event.target.value = value;
    event.target.classList.toggle("active", value.length > 0);
  }
  conditionBlocks[index].field = row.querySelector(".condition-field")?.value || "title";
  conditionBlocks[index].operator = row.querySelector(".condition-operator")?.value || "contains";
  conditionBlocks[index].value = row.querySelector(".condition-value")?.value || "";
  conditionBlocks[index].not = Boolean(row.querySelector(".condition-not-input")?.checked);
  conditionBlocks[index].ignore_spaces = Boolean(row.querySelector(".condition-ignore-spaces-input")?.checked);
  conditionBlocks[index].clean_search = Boolean(row.querySelector(".condition-clean-search-input")?.checked);
  syncExpressionFromBlocks();
});

elements.conditionBlocks?.addEventListener("change", (event) => {
  const row = event.target.closest?.(".condition-block");
  if (!row) {
    return;
  }
  const index = Number(row.dataset.index);
  if (!Number.isInteger(index) || !conditionBlocks[index]) {
    return;
  }
  conditionBlocks[index].connector = row.querySelector(".condition-connector")?.value || "";
  conditionBlocks[index].not = Boolean(row.querySelector(".condition-not-input")?.checked);
  conditionBlocks[index].ignore_spaces = Boolean(row.querySelector(".condition-ignore-spaces-input")?.checked);
  conditionBlocks[index].clean_search = Boolean(row.querySelector(".condition-clean-search-input")?.checked);
  conditionBlocks[index].field = row.querySelector(".condition-field")?.value || "title";
  conditionBlocks[index].operator = row.querySelector(".condition-operator")?.value || "contains";
  conditionBlocks[index].value = row.querySelector(".condition-value")?.value || "";
  syncExpressionFromBlocks();
});

elements.conditionBlocks?.addEventListener("click", (event) => {
  const removeButton = event.target.closest?.(".condition-remove");
  if (!removeButton) {
    return;
  }
  const row = removeButton.closest(".condition-block");
  const index = Number(row?.dataset.index);
  conditionBlocks.splice(index, 1);
  if (conditionBlocks[0]) {
    conditionBlocks[0].connector = "";
  }
  renderConditionBlocks();
});

elements.filterBtn?.addEventListener("click", () => {
  runFilter().catch((error) => setStatus(error.message, true));
});
elements.cancelFilterBtn?.addEventListener("click", () => {
  filterAbortController?.abort();
});
elements.addConditionBtn?.addEventListener("click", () => addCondition());
elements.presetSelect?.addEventListener("change", () => {
  const name = selectedPresetName();
  if (elements.presetName) {
    elements.presetName.value = name;
  }
  renderPresetOptions(name);
});
elements.loadPresetBtn?.addEventListener("click", () => applyConditionPreset(selectedPresetName()));
elements.savePresetBtn?.addEventListener("click", () => saveConditionPreset());
elements.deletePresetBtn?.addEventListener("click", () => deleteConditionPreset());
elements.presetName?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    saveConditionPreset();
  }
});
elements.prevPageBtn?.addEventListener("click", () => moveResultPage(-1));
elements.nextPageBtn?.addEventListener("click", () => moveResultPage(1));

bindPathSetting(
  elements.rootDirectory,
  () => ({ output_root: elements.rootDirectory.value }),
  (error) => setStatus(error.message, true),
);
bindPathSetting(
  elements.htmlTransferPath,
  () => ({ html_transfer_directory: elements.htmlTransferPath.value }),
  (error) => setStatus(error.message, true),
);

loadConfig().catch((error) => setStatus(error.message, true));
renderConditionBlocks();
renderPresetOptions();

bindPathPicker(document, {
  onError: (error) => setStatus(error.message, true),
});
