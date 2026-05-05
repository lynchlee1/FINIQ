const HTML_DOWNLOAD_STORAGE_KEY = "finiq.kind.filteredDisclosures";

const elements = {
  rootDirectory: document.getElementById("rootDirectory"),
  htmlTransferPath: document.getElementById("htmlTransferPath"),
  conditionBlocks: document.getElementById("conditionBlocks"),
  conditionPreview: document.getElementById("conditionPreview"),
  addConditionBtn: document.getElementById("addConditionBtn"),
  addGroupBtn: document.getElementById("addGroupBtn"),
  limit: document.getElementById("limit"),
  limitUnlimited: document.getElementById("limitUnlimited"),
  filterWorkers: document.getElementById("filterWorkers"),
  progressInterval: document.getElementById("progressInterval"),
  filterBtn: document.getElementById("filterBtn"),
  cancelFilterBtn: document.getElementById("cancelFilterBtn"),
  status: document.getElementById("status"),
  result: document.getElementById("result"),
  summaryCards: document.getElementById("summaryCards"),
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
let conditionBlocks = [
  { connector: "", open_count: 0, not: false, ignore_spaces: false, field: "title", operator: "contains", value: "", close_count: 0 },
];

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
            <button class="group-toggle ${block.open_count ? "active" : ""}" type="button" data-group-toggle="open" aria-label="그룹 시작">(</button>
            <label class="condition-not">
              <input class="condition-not-input" type="checkbox" ${block.not ? "checked" : ""} />
              NOT
            </label>
            <label class="condition-space">
              <input class="condition-ignore-spaces-input" type="checkbox" ${block.ignore_spaces ? "checked" : ""} />
              공백무시
            </label>
            <select class="condition-field" aria-label="필드">${optionMarkup(fieldOptions, block.field)}</select>
            <select class="condition-operator" aria-label="연산자">${optionMarkup(operatorOptions, block.operator)}</select>
            <input class="condition-value" type="text" value="${escapeHtml(block.value)}" placeholder="값" />
            <button class="group-toggle ${block.close_count ? "active" : ""}" type="button" data-group-toggle="close" aria-label="그룹 끝">)</button>
          </div>
          <button class="condition-remove" type="button" aria-label="조건 삭제">삭제</button>
        </div>
      `,
    )
    .join("");
  syncExpressionFromBlocks();
}

function addCondition(block = {}) {
  conditionBlocks.push({
    connector: conditionBlocks.length ? "AND" : "",
    open_count: 0,
    not: false,
    ignore_spaces: false,
    field: "title",
    operator: "contains",
    value: "",
    close_count: 0,
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
  renderSummary(payload);
  renderTable(payload.disclosures || []);
  renderJsonPreview();
  return transferReference;
}

function currentPageDisclosures() {
  const disclosures = latestPayload?.disclosures || [];
  return disclosures.slice(resultPage * RESULT_PAGE_SIZE, (resultPage + 1) * RESULT_PAGE_SIZE);
}

function renderJsonPreview() {
  if (!latestPayload) {
    elements.result.textContent = "결과 없음";
    return;
  }
  const disclosures = currentPageDisclosures();
  const payload = {
    ...latestPayload,
    summary: {
      ...(latestPayload.summary || {}),
      json_preview: true,
      preview_page: resultPage + 1,
      preview_page_size: RESULT_PAGE_SIZE,
      preview_disclosures: disclosures.length,
    },
    disclosures,
  };
  elements.result.textContent = JSON.stringify(payload, null, 2);
}

function renderSummary(payload) {
  const summary = payload.summary || {};
  const disclosures = payload.disclosures || [];
  const companyCount = new Set(disclosures.map((item) => item.company_key || item.company_name).filter(Boolean)).size;
  const cards = [
    ["매칭", summary.matched_disclosures || 0],
    ["반환", summary.returned_disclosures || 0],
    ["회사", companyCount],
    ["접수번호", summary.unique_acpt_numbers || 0],
  ];
  elements.summaryCards.innerHTML = cards
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
  const limitUnlimited = Boolean(elements.limitUnlimited?.checked);
  const displayLimit = Number(elements.limit.value || 1000);
  return {
    root_directory: elements.rootDirectory.value,
    html_transfer_path: elements.htmlTransferPath?.value || "",
    filter_blocks: conditionBlocks,
    title_expression: "",
    limit: limitUnlimited ? null : displayLimit,
    limit_unlimited: limitUnlimited,
    return_limit: displayLimit,
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
    elements.htmlTransferPath.value = `${config.output_root || ""}/.finiq/transfers`;
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
      ? `HTML 저장용 접수번호 ${transferReference.acpt_numbers}개를 서버 파일로 저장했습니다.`
      : "HTML 저장용 전송 파일을 만들지 못했습니다.";
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
  renderJsonPreview();
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
  conditionBlocks[index].field = row.querySelector(".condition-field")?.value || "title";
  conditionBlocks[index].operator = row.querySelector(".condition-operator")?.value || "contains";
  conditionBlocks[index].value = row.querySelector(".condition-value")?.value || "";
  conditionBlocks[index].not = Boolean(row.querySelector(".condition-not-input")?.checked);
  conditionBlocks[index].ignore_spaces = Boolean(row.querySelector(".condition-ignore-spaces-input")?.checked);
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
  conditionBlocks[index].field = row.querySelector(".condition-field")?.value || "title";
  conditionBlocks[index].operator = row.querySelector(".condition-operator")?.value || "contains";
  conditionBlocks[index].value = row.querySelector(".condition-value")?.value || "";
  syncExpressionFromBlocks();
});

elements.conditionBlocks?.addEventListener("click", (event) => {
  const groupButton = event.target.closest?.(".group-toggle");
  if (groupButton) {
    const row = groupButton.closest(".condition-block");
    const index = Number(row?.dataset.index);
    if (Number.isInteger(index) && conditionBlocks[index]) {
      const key = groupButton.dataset.groupToggle === "open" ? "open_count" : "close_count";
      conditionBlocks[index][key] = conditionBlocks[index][key] ? 0 : 1;
      renderConditionBlocks();
    }
    return;
  }

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
elements.addGroupBtn?.addEventListener("click", () =>
  addCondition({
    connector: conditionBlocks.length ? "OR" : "",
    open_count: 1,
    field: "title",
    operator: "contains",
    value: "",
    close_count: 1,
  }),
);
elements.prevPageBtn?.addEventListener("click", () => moveResultPage(-1));
elements.nextPageBtn?.addEventListener("click", () => moveResultPage(1));
elements.limitUnlimited?.addEventListener("change", () => {
  elements.limit.disabled = Boolean(elements.limitUnlimited.checked);
});
if (elements.limit && elements.limitUnlimited) {
  elements.limit.disabled = Boolean(elements.limitUnlimited.checked);
}

loadConfig().catch((error) => setStatus(error.message, true));
renderConditionBlocks();
