"""Standalone HTML template for the legacy KIND download page."""

from __future__ import annotations

_DOWNLOAD_PAGE_HTML = """<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>KIND 다운로드</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f6f8fb;
        --surface: #ffffff;
        --surface-2: #f3f6fa;
        --surface-3: #e7edf5;
        --line: rgba(148, 163, 184, 0.26);
        --line-strong: rgba(100, 116, 139, 0.34);
        --text: #1f2937;
        --muted: #5f6f83;
        --subtle: #8a97a8;
        --green: #0f766e;
        --red: #dc2626;
        --app-bg: linear-gradient(145deg, #f8fafc 0%, #f4f7fb 56%, #ffffff 100%);
        --topbar-bg: rgba(255, 255, 255, 0.82);
        --panel-bg: rgba(255, 255, 255, 0.78);
        --panel-strong-bg: rgba(255, 255, 255, 0.94);
        --panel-soft-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(248, 250, 252, 0.78));
        --control-bg: rgba(255, 255, 255, 0.92);
        --control-focus-bg: rgba(255, 255, 255, 0.98);
        --button-color: #334155;
        --button-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(241, 245, 249, 0.9)), #ffffff;
        --button-hover-bg: linear-gradient(180deg, rgba(239, 246, 255, 0.98), rgba(226, 232, 240, 0.86)), #ffffff;
        --primary-color: #0f766e;
        --primary-bg: linear-gradient(135deg, rgba(204, 251, 241, 0.96), rgba(219, 234, 254, 0.88)), #ffffff;
        --metric-bg: rgba(15, 23, 42, 0.04);
        --summary-bg: rgba(248, 250, 252, 0.84);
        --grid-line: rgba(148, 163, 184, 0.16);
        --shadow: 0 18px 55px rgba(15, 23, 42, 0.1);
        font-family: "IBM Plex Sans KR", Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      *,
      *::before,
      *::after {
        box-sizing: border-box;
      }
      body {
        margin: 0;
        min-height: 100vh;
        background: var(--app-bg);
        color: var(--text);
      }
      body::before {
        position: fixed;
        inset: 0;
        z-index: -1;
        pointer-events: none;
        content: "";
        background-image:
          linear-gradient(var(--grid-line) 1px, transparent 1px),
          linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
        background-size: 28px 28px;
        mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.55), transparent 84%);
      }
      main {
        display: flex;
        flex-direction: column;
        gap: 12px;
        max-width: 1320px;
        margin: 0 auto;
        padding: 12px;
      }
      h1 {
        margin: 0;
        font-size: 32px;
        line-height: 1.1;
      }
      h2 {
        margin: 0;
        font-size: 17px;
      }
      p,
      .hint {
        margin: 6px 0 0;
        color: var(--muted);
        font-size: 13px;
      }
      .topbar {
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 14px;
        padding: 16px 18px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--topbar-bg);
        box-shadow: var(--shadow);
        backdrop-filter: blur(18px);
      }
      .brand-label,
      .panel-kicker {
        margin: 0 0 4px;
        color: var(--green);
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      .panel {
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--panel-bg);
        box-shadow: var(--shadow);
        padding: 12px;
      }
      .panel-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 10px;
      }
      .row {
        display: grid;
        gap: 10px;
        margin-top: 10px;
      }
      .row:first-child {
        margin-top: 0;
      }
      .row.cols-2 {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .row.cols-3 {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }
      label {
        display: grid;
        gap: 6px;
        min-width: 0;
        color: var(--muted);
        font-size: 12px;
        font-weight: 700;
      }
      input,
      select,
      textarea {
        width: 100%;
        min-width: 0;
        border: 1px solid rgba(148, 163, 184, 0.22);
        border-radius: 7px;
        padding: 9px 10px;
        font: inherit;
        color: var(--text);
        background: var(--control-bg);
        outline: none;
        transition: border-color 140ms ease, box-shadow 140ms ease, background 140ms ease;
      }
      input:focus,
      select:focus,
      textarea:focus {
        border-color: rgba(125, 211, 252, 0.72);
        box-shadow: 0 0 0 3px rgba(125, 211, 252, 0.12);
        background: var(--control-focus-bg);
      }
      input[type="checkbox"] {
        width: 15px;
        height: 15px;
        accent-color: var(--green);
      }
      details {
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 10px;
        background: var(--panel-soft-bg);
      }
      details + details {
        margin-top: 8px;
      }
      summary {
        cursor: pointer;
        color: var(--text);
        font-size: 12px;
        font-weight: 850;
      }
      .disc-items {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 6px 10px;
        margin-top: 10px;
      }
      .disc-items label {
        display: flex;
        align-items: center;
        gap: 8px;
        min-height: 28px;
        font-size: 12px;
      }
      .disc-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 8px;
      }
      button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 36px;
        min-width: 0;
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 8px;
        padding: 8px 14px;
        color: var(--button-color);
        background: var(--button-bg);
        box-shadow: 0 1px 0 rgba(255, 255, 255, 0.7) inset;
        font: inherit;
        font-size: 13px;
        font-weight: 750;
        line-height: 1;
        cursor: pointer;
        transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
      }
      button:hover {
        transform: translateY(-1px);
        border-color: rgba(125, 211, 252, 0.42);
        background: var(--button-hover-bg);
      }
      button.primary {
        color: var(--primary-color);
        border-color: rgba(52, 211, 153, 0.56);
        background: var(--primary-bg);
      }
      button.muted {
        color: var(--button-color);
        background: var(--button-bg);
      }
      button.danger {
        color: #991b1b;
        border-color: rgba(248, 113, 113, 0.56);
        background: linear-gradient(135deg, rgba(254, 226, 226, 0.98), rgba(255, 241, 242, 0.9)), #ffffff;
      }
      .actions {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }
      .path-input-row {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 8px;
        align-items: center;
      }
      #status {
        margin-top: 10px;
        color: var(--muted);
        font-size: 13px;
        font-weight: 700;
        white-space: pre-wrap;
      }
      #deletePanel {
        display: none;
        margin-top: 12px;
        border: 1px solid rgba(248, 113, 113, 0.42);
        border-radius: 8px;
        padding: 12px;
        background: rgba(254, 242, 242, 0.92);
      }
      #deletePanel.visible {
        display: grid;
        gap: 10px;
      }
      #deleteCandidates {
        display: grid;
        gap: 8px;
        max-height: 180px;
        overflow: auto;
        border: 1px solid rgba(248, 113, 113, 0.24);
        border-radius: 7px;
        padding: 10px;
        background: rgba(255, 255, 255, 0.92);
        font-size: 12px;
      }
      .candidate-name {
        color: var(--text);
        font-weight: 800;
      }
      .candidate-reason {
        margin-top: 3px;
        color: var(--muted);
      }
      pre {
        margin: 0;
        border: 1px solid var(--line-strong);
        border-radius: 8px;
        padding: 12px;
        background: #090d12;
        color: #dbeafe;
        overflow: auto;
        max-height: 420px;
        font-size: 12px;
        line-height: 1.5;
      }
      .checkbox-field {
        align-content: end;
      }
      .checkbox-card {
        display: flex;
        align-items: center;
        gap: 8px;
        min-height: 37px;
        padding: 9px 10px;
        border: 1px solid var(--line);
        border-radius: 7px;
        background: var(--control-bg);
      }
      @media (max-width: 900px) {
        .topbar,
        .panel-header {
          align-items: stretch;
          flex-direction: column;
        }
        .row.cols-2,
        .row.cols-3,
        .path-input-row,
        .disc-items {
          grid-template-columns: 1fr;
        }
      }
    </style>
  </head>
  <body>
    <main>
      <header class="topbar">
        <div>
          <p class="brand-label">FINIQ DataScraper</p>
          <h1>KIND 다운로드</h1>
          <p>검색 조건을 구성하고 KIND 공시 원문을 내려받습니다.</p>
        </div>
      </header>

      <section class="panel">
        <div class="panel-header">
          <div>
            <p class="panel-kicker">Run Scope</p>
            <h2>저장 위치와 기간</h2>
          </div>
        </div>
        <div class="row">
          <label>
            저장 경로
            <div class="path-input-row">
              <input id="outputDirectory" type="text" />
              <button id="chooseOutputDirectoryBtn" class="muted" type="button" aria-label="경로 선택">📁</button>
            </div>
          </label>
        </div>
        <div class="row cols-2">
          <label>
            시작일
            <input id="startDate" type="date" />
          </label>
          <label>
            종료일
            <input id="endDate" type="date" />
          </label>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <p class="panel-kicker">Search Filters</p>
            <h2>검색 조건</h2>
          </div>
        </div>
        <div class="row cols-2">
          <label>
            회사명
            <input id="companyName" type="text" placeholder="예: 삼성전자" />
          </label>
          <label>
            제출인명
            <input id="submitterName" type="text" />
          </label>
        </div>
        <div class="row cols-2">
          <label>
            시장구분
            <select id="marketLabel"></select>
          </label>
          <label>
            유가증권구분
            <select id="securitiesLabel"></select>
          </label>
        </div>
        <div class="row cols-3">
          <label>
            페이지 크기
            <input id="pageSize" type="number" min="1" max="100" value="100" />
          </label>
          <label>
            요청 간격(초)
            <input id="waitSeconds" type="number" min="0" max="30" step="0.5" value="1.0" />
          </label>
          <label>
            타임아웃(초)
            <input id="timeout" type="number" min="1" max="120" step="1" value="20" />
          </label>
        </div>
        <div class="row cols-3">
          <label class="checkbox-field">
            <span>최종보고서보기</span>
            <span class="checkbox-card"><input id="lastReportOnly" type="checkbox" /> 최종보고서만 조회</span>
          </label>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <p class="panel-kicker">Disclosure Types</p>
            <h2>공시유형</h2>
          </div>
        </div>
        <div id="disclosureGroups"></div>
      </section>

      <section class="panel">
        <div class="actions">
          <button id="previewBtn" class="muted" type="button">페이로드 미리보기</button>
          <button id="inspectBtn" class="muted" type="button">기존 파일 검사</button>
        </div>
        <div id="status"></div>
        <div id="deletePanel">
          <div>
            <strong>삭제 확인 필요</strong>
            <p class="hint">기존 다운로드 파일이 현재 요청과 맞지 않습니다. 삭제 후보를 확인한 뒤 실행하세요.</p>
          </div>
          <div id="deleteCandidates"></div>
          <div id="deleteSummary" class="hint"></div>
          <label class="checkbox-card"><input id="deleteConfirmed" type="checkbox" /> 삭제 허가</label>
          <label>
            확인 문구
            <input id="deleteConfirmationText" type="text" placeholder="확인했습니다." />
          </label>
          <button id="deleteCandidatesBtn" class="danger" type="button">삭제 후보 삭제</button>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <p class="panel-kicker">Result</p>
            <h2>응답 페이로드</h2>
          </div>
        </div>
        <pre id="result">결과 없음</pre>
      </section>
    </main>

    <script>
      const el = {
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
        lastReportOnly: document.getElementById("lastReportOnly"),
        disclosureGroups: document.getElementById("disclosureGroups"),
        previewBtn: document.getElementById("previewBtn"),
        inspectBtn: document.getElementById("inspectBtn"),
        status: document.getElementById("status"),
        result: document.getElementById("result"),
        deletePanel: document.getElementById("deletePanel"),
        deleteCandidates: document.getElementById("deleteCandidates"),
        deleteSummary: document.getElementById("deleteSummary"),
        deleteConfirmed: document.getElementById("deleteConfirmed"),
        deleteConfirmationText: document.getElementById("deleteConfirmationText"),
        deleteCandidatesBtn: document.getElementById("deleteCandidatesBtn"),
      };

      let optionsPayload = null;
      let currentDeleteCandidates = [];
      let currentDeletionConfirmation = "";

      function setStatus(message, isError = false) {
        el.status.textContent = message || "";
        el.status.style.color = isError ? "#b91c1c" : "#334155";
      }

      function setResult(payload) {
        el.result.textContent = JSON.stringify(payload, null, 2);
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
          throw new Error(payload.detail || payload.error || `Request failed: ${response.status}`);
        }
        return payload;
      }

      function renderDeleteCandidates(payload) {
        currentDeleteCandidates = Array.isArray(payload.deletion_candidates) ? payload.deletion_candidates : [];
        currentDeletionConfirmation = String(payload.deletion_confirmation || "");
        el.deleteCandidates.innerHTML = "";
        currentDeleteCandidates.forEach((file) => {
          const item = document.createElement("div");
          const name = document.createElement("div");
          name.className = "candidate-name";
          name.textContent = file.name || file.path || "";
          const reason = document.createElement("div");
          reason.className = "candidate-reason";
          reason.textContent = file.reason || "";
          item.appendChild(name);
          item.appendChild(reason);
          el.deleteCandidates.appendChild(item);
        });
        const summary = payload.summary || {};
        el.deleteSummary.textContent = `최신 상태: 성공 ${summary.success || 0}/${summary.total || 0}건, 삭제 후보 ${currentDeleteCandidates.length}개`;
        el.deletePanel.classList.toggle("visible", currentDeleteCandidates.length > 0);
      }

      async function inspectDownloadFolder(dryRun) {
        const payload = {
          ...buildPayload(),
          dry_run: dryRun,
          delete_confirmed: Boolean(el.deleteConfirmed.checked),
          delete_confirmation_text: String(el.deleteConfirmationText.value || "").trim(),
          ...(dryRun ? {} : { deletion_confirmation: currentDeletionConfirmation }),
        };
        const result = await fetchJson("/api/download/inspect-folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        renderDeleteCandidates(result);
        setResult(result);
        return result;
      }

      async function chooseOutputDirectory() {
        const payload = await fetchJson("/api/file-dialog", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mode: "folder",
            title: "저장 폴더 선택",
            default_path: el.outputDirectory.value || "",
          }),
        });
        if (payload.path) {
          el.outputDirectory.value = payload.path;
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
        el.disclosureGroups.innerHTML = "";
        groups.forEach((group) => {
          const details = document.createElement("details");
          details.open = false;
          details.dataset.suffix = group.suffix;

          const summary = document.createElement("summary");
          summary.textContent = `${group.label} (${group.items.length})`;
          details.appendChild(summary);

          const actions = document.createElement("div");
          actions.className = "disc-actions";
          const selectAll = document.createElement("button");
          selectAll.type = "button";
          selectAll.className = "muted";
          selectAll.textContent = "전체 선택";
          selectAll.addEventListener("click", () => {
            details.querySelectorAll('input[type="checkbox"]').forEach((input) => {
              input.checked = true;
            });
          });
          const clearAll = document.createElement("button");
          clearAll.type = "button";
          clearAll.className = "muted";
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
          el.disclosureGroups.appendChild(details);
        });
      }

      function collectDisclosureGroups() {
        const result = {};
        el.disclosureGroups
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
        return {
          mode: "yearly",
          output_directory: String(el.outputDirectory.value || "").trim(),
          start_date: String(el.startDate.value || "").trim(),
          end_date: String(el.endDate.value || "").trim(),
          company_name: String(el.companyName.value || "").trim(),
          submitter_name: String(el.submitterName.value || "").trim(),
          market_label: String(el.marketLabel.value || "").trim(),
          securities_label: String(el.securitiesLabel.value || "").trim(),
          page_size: Number(el.pageSize.value || 100),
          wait_seconds: Number(el.waitSeconds.value || 1),
          timeout: Number(el.timeout.value || 20),
          last_report_only: Boolean(el.lastReportOnly.checked),
          disclosure_type_groups: collectDisclosureGroups(),
        };
      }

      async function initialize() {
        setStatus("옵션을 불러오는 중...");
        optionsPayload = await fetchJson("/api/download/options");

        fillSelect(el.marketLabel, optionsPayload.market_types);
        fillSelect(el.securitiesLabel, optionsPayload.securities_types);
        renderDisclosureGroups(optionsPayload.disclosure_groups);

        el.outputDirectory.value = optionsPayload.default_output_directory || "";
        const today = new Date();
        const start = new Date(today);
        start.setDate(today.getDate() - 30);
        el.startDate.value = start.toISOString().slice(0, 10);
        el.endDate.value = today.toISOString().slice(0, 10);
        setStatus("준비 완료");
      }

      document.getElementById("chooseOutputDirectoryBtn").addEventListener("click", () => {
        chooseOutputDirectory().catch((error) => setStatus(error.message, true));
      });

      el.previewBtn.addEventListener("click", async () => {
        try {
          setStatus("미리보기 생성 중...");
          const payload = buildPayload();
          const result = await fetchJson("/api/download/preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          setResult(result);
          setStatus("미리보기 완료");
        } catch (error) {
          setStatus(error.message, true);
        }
      });

      el.inspectBtn.addEventListener("click", async () => {
        try {
          setStatus("기존 다운로드 파일을 검사하는 중...");
          const result = await inspectDownloadFolder(true);
          const count = result.deletion_candidate_count || 0;
          setStatus(count ? `삭제 확인이 필요한 기존 파일 ${count}개가 있습니다.` : "삭제할 기존 불일치 파일이 없습니다.");
        } catch (error) {
          setStatus(error.message, true);
        }
      });

      el.deleteCandidatesBtn.addEventListener("click", async () => {
        try {
          if (!el.deleteConfirmed.checked || String(el.deleteConfirmationText.value || "").trim() !== "확인했습니다.") {
            setStatus('삭제하려면 삭제 허가를 체크하고 "확인했습니다."를 입력하세요.', true);
            return;
          }
          setStatus("확인된 기존 파일을 삭제하는 중...");
          const result = await inspectDownloadFolder(false);
          el.deleteConfirmed.checked = false;
          el.deleteConfirmationText.value = "";
          setStatus(`기존 파일 ${result.deleted_count || 0}개를 삭제했습니다. 최신 상태 기준 성공 ${result.summary?.success || 0}/${result.summary?.total || 0}건입니다.`);
        } catch (error) {
          setStatus(error.message, true);
        }
      });

      initialize().catch((error) => {
        setStatus(error.message, true);
      });
    </script>
  </body>
</html>
"""


def render_download_page() -> bytes:
    return _DOWNLOAD_PAGE_HTML.encode("utf-8")
