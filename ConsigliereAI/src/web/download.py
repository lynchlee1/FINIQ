"""KIND download page and API helpers for kind-web."""

from __future__ import annotations

from collections import deque
from collections.abc import MutableSequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any
import uuid

_DATASCRAPER_SRC = Path(__file__).resolve().parents[3] / "FINIQ-DataScraper" / "src"
if _DATASCRAPER_SRC.is_dir():
    data_scraper_path = str(_DATASCRAPER_SRC)
    if data_scraper_path not in sys.path:
        sys.path.insert(0, data_scraper_path)

from core.client import download_pages
from core.constants import (
    DEFAULT_REQUEST_HEADERS,
    DISCLOSURE_GROUPS,
    MARKET_TYPES,
    SECURITIES_TYPES,
)
from parse import pagination_info
from workflow import (
    KindWorkflow,
    inspect_download_directory_pages,
    make_page_size_integrity_validator,
)


@dataclass(slots=True)
class DownloadJob:
    id: str
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    progress_log: deque[str] = field(default_factory=lambda: deque(maxlen=20))
    result: dict[str, Any] | None = None
    error: str | None = None


_DOWNLOAD_JOBS: dict[str, DownloadJob] = {}
_DOWNLOAD_JOBS_LOCK = threading.Lock()

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
      .actions {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }
      #status {
        margin-top: 10px;
        color: var(--muted);
        font-size: 13px;
        font-weight: 700;
        white-space: pre-wrap;
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
            <input id="outputDirectory" type="text" />
          </label>
        </div>
        <div class="row cols-3">
          <label>
            모드
            <select id="mode">
              <option value="single">단건 검색</option>
              <option value="yearly">연도별 일괄</option>
              <option value="resume">이어받기</option>
            </select>
          </label>
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
          <label>
            시작 페이지
            <input id="startPage" type="number" min="1" value="1" />
          </label>
          <label>
            끝 페이지 (비우면 자동 전체)
            <input id="endPage" type="number" min="1" />
          </label>
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
          <button id="runBtn" class="primary" type="button">다운로드 실행</button>
        </div>
        <div id="status"></div>
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
        mode: document.getElementById("mode"),
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
        startPage: document.getElementById("startPage"),
        endPage: document.getElementById("endPage"),
        lastReportOnly: document.getElementById("lastReportOnly"),
        disclosureGroups: document.getElementById("disclosureGroups"),
        previewBtn: document.getElementById("previewBtn"),
        runBtn: document.getElementById("runBtn"),
        status: document.getElementById("status"),
        result: document.getElementById("result"),
      };

      let optionsPayload = null;

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
          throw new Error(payload.error || `Request failed: ${response.status}`);
        }
        return payload;
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
        const endPageRaw = String(el.endPage.value || "").trim();
        return {
          mode: el.mode.value,
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
          start_page: Number(el.startPage.value || 1),
          end_page: endPageRaw ? Number(endPageRaw) : null,
          last_report_only: Boolean(el.lastReportOnly.checked),
          disclosure_type_groups: collectDisclosureGroups(),
        };
      }

      function syncModeState() {
        const resumeMode = el.mode.value === "resume";
        el.startDate.disabled = resumeMode;
        el.endDate.disabled = resumeMode;
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
        syncModeState();
        setStatus("준비 완료");
      }

      el.mode.addEventListener("change", syncModeState);

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

      el.runBtn.addEventListener("click", async () => {
        try {
          setStatus("다운로드 실행 중... (시간이 걸릴 수 있습니다)");
          const payload = buildPayload();
          const result = await fetchJson("/api/download/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          setResult(result);
          setStatus("다운로드 완료");
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


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _split_yearly_ranges(start: date, end: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        year_end = date(cursor.year, 12, 31)
        ranges.append((cursor, min(year_end, end)))
        cursor = date(cursor.year + 1, 1, 1)
    return ranges


def _normalize_disclosure_type_groups(payload: dict[str, Any]) -> dict[str, list[str]] | None:
    raw_groups = payload.get("disclosure_type_groups")
    if not raw_groups:
        return None
    if not isinstance(raw_groups, dict):
        raise ValueError("disclosure_type_groups must be an object")

    normalized: dict[str, list[str]] = {}
    for suffix, _, items in DISCLOSURE_GROUPS:
        selected = raw_groups.get(suffix)
        if not selected:
            continue
        if not isinstance(selected, list):
            raise ValueError(f"disclosure_type_groups.{suffix} must be an array")
        allowed = {code for code, _name in items}
        codes = [str(code) for code in selected if str(code) in allowed]
        if codes:
            normalized[suffix] = codes
    return normalized or None


def _build_search_filters(payload: dict[str, Any]) -> dict[str, str] | None:
    search_filters: dict[str, str] = {}

    company_name = str(payload.get("company_name") or "").strip()
    if company_name:
        search_filters["searchCorpName"] = company_name

    submitter_name = str(payload.get("submitter_name") or "").strip()
    if submitter_name:
        search_filters["submitOblgNm"] = submitter_name

    market_label = str(payload.get("market_label") or "").strip()
    market_value = MARKET_TYPES.get(market_label, "")
    if market_value:
        search_filters["marketType"] = market_value

    securities_label = str(payload.get("securities_label") or "").strip()
    securities_value = SECURITIES_TYPES.get(securities_label, "")
    if securities_value:
        search_filters["securities"] = securities_value

    return search_filters or None


def _as_int(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key)
    if value in ("", None):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _as_float(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key)
    if value in ("", None):
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number") from exc


def _as_bool(payload: dict[str, Any], key: str) -> bool | None:
    value = payload.get(key)
    if value in ("", None):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    raise ValueError(f"{key} must be a boolean")


def _detect_pagination(folder: Path) -> dict[str, Any] | None:
    body_files = sorted(folder.glob("*_post_page_*.body"))
    if not body_files:
        return None
    latest = body_files[-1]
    info = pagination_info(latest.read_bytes())
    if info is None:
        return None
    info["downloaded_pages"] = len(body_files)
    info["latest_file"] = latest.name
    return info


def _load_workflow_input(folder: Path) -> dict[str, Any] | None:
    input_path = folder / "kind_workflow.input.json"
    if not input_path.exists():
        return None
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return None


def _as_worker_count(payload: dict[str, Any], *, default: int | None = None) -> int:
    cpu_count = os.cpu_count() or 1
    fallback = default if default is not None else min(4, cpu_count)
    worker_count = _as_int(payload, "worker_count", fallback)
    if worker_count < 1:
        raise ValueError("worker_count must be >= 1")
    return min(worker_count, cpu_count)


def _as_log_limit(payload: dict[str, Any], *, default: int = 20) -> int:
    log_limit = _as_int(payload, "log_limit", default)
    if log_limit < 1:
        raise ValueError("log_limit must be >= 1")
    return min(log_limit, 500)


def _as_resume_yearly(payload: dict[str, Any]) -> bool:
    value = payload.get("resume_yearly")
    if value in ("", None):
        return True
    return bool(_as_bool(payload, "resume_yearly"))


def _build_progress_collector(prefix: str = "", external_callback: Any | None = None) -> tuple[deque[str], Any]:
    progress_log: deque[str] = deque(maxlen=0)

    def _callback(message: str) -> None:
        normalized = str(message).strip()
        if normalized:
            line = f"{prefix}{normalized}"
            if progress_log.maxlen != 0:
                progress_log.append(line)
            if external_callback is not None:
                external_callback(line)

    return progress_log, _callback


def _download_integrity_status(output_directory: Path, page_size: int) -> dict[str, Any]:
    pagination = _detect_pagination(output_directory)
    status: dict[str, Any] = {
        "output_directory": str(output_directory),
        "pagination": pagination,
        "integrity_valid": False,
        "complete": False,
        "missing_pages": [],
        "errors": [],
    }
    try:
        inspected = inspect_download_directory_pages(
            output_directory,
            expected_page_size=page_size,
            require_complete=False,
        )
        total_pages = int(inspected.get("total_pages") or 0)
        downloaded_pages = int(inspected.get("downloaded_pages") or 0)
        status.update(inspected)
        status["integrity_valid"] = True
        status["complete"] = total_pages > 0 and downloaded_pages == total_pages
        if total_pages > downloaded_pages:
            status["missing_pages"] = list(range(downloaded_pages + 1, total_pages + 1))
    except Exception as exc:
        status["errors"].append(str(exc))
    return status


def _append_progress(
    progress_log: MutableSequence[str] | deque[str],
    message: str,
    progress_callback: Any | None = None,
) -> None:
    if getattr(progress_log, "maxlen", None) != 0:
        progress_log.append(message)
    if progress_callback is not None:
        progress_callback(message)


def _download_payload_summary(payload: dict[str, Any]) -> list[str]:
    mode = str(payload.get("mode") or "single").strip().lower()
    return [
        f"mode={mode}",
        f"output={str(payload.get('output_directory') or '').strip()}",
        f"range={str(payload.get('start_date') or '').strip()}~{str(payload.get('end_date') or '').strip()}",
        f"pages={payload.get('start_page') or 1}~{payload.get('end_page') or 'auto'}",
        f"page_size={payload.get('page_size') or 100}",
        f"wait={payload.get('wait_seconds') or 1}s",
        f"timeout={payload.get('timeout') or 20}s",
        f"workers={payload.get('worker_count') or 1}",
        f"log_limit={payload.get('log_limit') or 20}",
        f"resume_yearly={payload.get('resume_yearly', True)}",
    ]


def _append_status_progress(
    progress_log: MutableSequence[str] | deque[str],
    status: dict[str, Any],
    progress_callback: Any | None = None,
) -> None:
    pagination = status.get("pagination") or {}
    downloaded = status.get("downloaded_pages") or pagination.get("downloaded_pages") or 0
    total = status.get("total_pages") or pagination.get("total_pages") or 0
    total_items = status.get("total_items") or pagination.get("total_items") or 0
    _append_progress(
        progress_log,
        f"STATUS output={status.get('output_directory')} downloaded={downloaded}/{total} total_items={total_items}",
        progress_callback,
    )
    latest_file = pagination.get("latest_file")
    if latest_file:
        _append_progress(progress_log, f"STATUS latest_file={latest_file}", progress_callback)
    missing_pages = status.get("missing_pages") or []
    if missing_pages:
        preview = ",".join(str(page) for page in missing_pages[:20])
        suffix = f"...(+{len(missing_pages) - 20})" if len(missing_pages) > 20 else ""
        _append_progress(progress_log, f"STATUS missing_pages={preview}{suffix}", progress_callback)
    if int(downloaded or 0) == 0:
        _append_progress(progress_log, "STATUS no_saved_result_pages=true", progress_callback)
        return
    if status.get("integrity_valid"):
        _append_progress(progress_log, "INTEGRITY ok page_numbers=true row_counts=true", progress_callback)
    else:
        _append_progress(
            progress_log,
            "INTEGRITY failed " + " / ".join(status.get("errors") or ["unknown"]),
            progress_callback,
        )


def _run_single(payload: dict[str, Any], progress_callback: Any | None = None) -> dict[str, Any]:
    output_directory_raw = str(payload.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    output_directory = Path(output_directory_raw).expanduser().resolve()

    start_date_raw = str(payload.get("start_date") or "").strip()
    end_date_raw = str(payload.get("end_date") or "").strip()
    if not start_date_raw or not end_date_raw:
        raise ValueError("start_date and end_date are required")
    _parse_iso_date(start_date_raw, "start_date")
    _parse_iso_date(end_date_raw, "end_date")

    start_page = _as_int(payload, "start_page", 1)
    end_page = payload.get("end_page")
    end_page_value = _as_int(payload, "end_page", start_page) if end_page not in ("", None) else None
    page_size = _as_int(payload, "page_size", 100)
    wait_seconds = _as_float(payload, "wait_seconds", 1.0)
    timeout = _as_float(payload, "timeout", 20.0)
    if wait_seconds < 0:
        raise ValueError("wait_seconds must be >= 0")
    if timeout <= 0:
        raise ValueError("timeout must be > 0")

    workflow = KindWorkflow()
    progress_log, local_progress_callback = _build_progress_collector(external_callback=progress_callback)
    for line in _download_payload_summary(payload):
        _append_progress(progress_log, f"SINGLE {line}", progress_callback)
    search_filters = _build_search_filters(payload)
    disclosure_type_groups = _normalize_disclosure_type_groups(payload)
    last_report_only = _as_bool(payload, "last_report_only")
    _append_progress(progress_log, f"SINGLE search_filters={search_filters or {}}", progress_callback)
    _append_progress(
        progress_log,
        f"SINGLE disclosure_group_count={len(disclosure_type_groups or {})}",
        progress_callback,
    )

    if end_page_value is not None:
        _append_progress(
            progress_log,
            f"SINGLE fixed_page_download start_page={start_page} end_page={end_page_value}",
            progress_callback,
        )
        workflow.run(
            output_directory=output_directory,
            request_headers=DEFAULT_REQUEST_HEADERS,
            start_date=start_date_raw,
            end_date=end_date_raw,
            start_page=start_page,
            end_page=end_page_value,
            page_size=page_size,
            search_filters=search_filters,
            disclosure_type_groups=disclosure_type_groups,
            last_report_only=last_report_only,
            include_previous_disclosures=None,
            wait_seconds_between_requests=wait_seconds,
            timeout=timeout,
            parse_mode="simpletable",
            save=True,
            progress_callback=local_progress_callback,
        )
    else:
        _append_progress(progress_log, "SINGLE auto_page_download first_page_probe=1", progress_callback)
        workflow.run(
            output_directory=output_directory,
            request_headers=DEFAULT_REQUEST_HEADERS,
            start_date=start_date_raw,
            end_date=end_date_raw,
            start_page=1,
            end_page=1,
            page_size=page_size,
            search_filters=search_filters,
            disclosure_type_groups=disclosure_type_groups,
            last_report_only=last_report_only,
            include_previous_disclosures=None,
            wait_seconds_between_requests=wait_seconds,
            timeout=timeout,
            parse_mode="simpletable",
            save=True,
            progress_callback=local_progress_callback,
        )
        paging = _detect_pagination(output_directory)
        if paging and int(paging.get("total_pages") or 0) > 1:
            saved_input = _load_workflow_input(output_directory)
            if saved_input is None:
                raise ValueError("kind_workflow.input.json is missing")
            _append_progress(
                progress_log,
                f"SINGLE pagination_detected total_pages={int(paging['total_pages'])} total_items={int(paging.get('total_items') or 0)}",
                progress_callback,
            )
            download_pages(
                output_directory=output_directory,
                request_headers=saved_input["request_headers"],
                start_date=saved_input["start_date"],
                end_date=saved_input["end_date"],
                start_page=2,
                end_page=int(paging["total_pages"]),
                page_size=int(saved_input.get("page_size", page_size)),
                search_filters=saved_input.get("search_filters") or None,
                disclosure_type_groups=saved_input.get("disclosure_type_groups") or None,
                last_report_only=saved_input.get("last_report_only"),
                include_previous_disclosures=saved_input.get("include_previous_disclosures"),
                wait_seconds_between_requests=wait_seconds,
                timeout=float(saved_input.get("timeout", timeout)),
                progress_callback=local_progress_callback,
                saved_file_validator=make_page_size_integrity_validator(
                    expected_page_size=int(saved_input.get("page_size", page_size)),
                ),
            )

    status = _download_integrity_status(output_directory, page_size)
    _append_status_progress(progress_log, status, progress_callback)
    return {
        "mode": "single",
        "output_directory": str(output_directory),
        "pagination": status.get("pagination"),
        "download_status": status,
        "progress_log": list(progress_log),
    }


def _run_yearly_chunk(payload: dict[str, Any]) -> dict[str, Any]:
    return _run_single(payload)


def _yearly_task_resume_payload(task: dict[str, Any]) -> dict[str, Any] | None:
    output_directory = Path(str(task.get("output_directory") or "")).expanduser().resolve()
    if not output_directory.is_dir():
        return None
    if _detect_pagination(output_directory) is None:
        return None
    if _load_workflow_input(output_directory) is None:
        return None
    return {
        **task,
        "mode": "resume",
        "start_date": "",
        "end_date": "",
    }


def _run_yearly_task(
    task: dict[str, Any],
    *,
    resume_yearly: bool,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    resume_payload = _yearly_task_resume_payload(task) if resume_yearly else None
    if resume_payload is None:
        if resume_yearly:
            _append_progress(deque(maxlen=0), "resume_unavailable -> full_download", progress_callback)
        return _run_single(task, progress_callback=progress_callback)
    _append_progress(deque(maxlen=0), "resume_available -> resume_download", progress_callback)
    return _run_resume(resume_payload, progress_callback=progress_callback)


def _run_yearly(payload: dict[str, Any], progress_callback: Any | None = None) -> dict[str, Any]:
    output_directory_raw = str(payload.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")

    start_date_raw = str(payload.get("start_date") or "").strip()
    end_date_raw = str(payload.get("end_date") or "").strip()
    if not start_date_raw or not end_date_raw:
        raise ValueError("start_date and end_date are required")

    start_date = _parse_iso_date(start_date_raw, "start_date")
    end_date = _parse_iso_date(end_date_raw, "end_date")
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")

    base_output = Path(output_directory_raw).expanduser().resolve()
    page_size = _as_int(payload, "page_size", 100)
    wait_seconds = _as_float(payload, "wait_seconds", 1.0)
    timeout = _as_float(payload, "timeout", 20.0)
    if wait_seconds < 0:
        raise ValueError("wait_seconds must be >= 0")
    if timeout <= 0:
        raise ValueError("timeout must be > 0")

    search_filters = _build_search_filters(payload)
    disclosure_type_groups = _normalize_disclosure_type_groups(payload)
    last_report_only = _as_bool(payload, "last_report_only")
    resume_yearly = _as_resume_yearly(payload)
    yearly_ranges = _split_yearly_ranges(start_date, end_date)
    worker_count = min(_as_worker_count(payload), max(1, len(yearly_ranges)))
    progress_log: deque[str] = deque(maxlen=0)
    for line in _download_payload_summary(payload):
        _append_progress(progress_log, f"YEARLY {line}", progress_callback)
    _append_progress(progress_log, f"YEARLY chunks={len(yearly_ranges)} workers={worker_count}", progress_callback)
    tasks: list[dict[str, Any]] = []

    for chunk_start, chunk_end in yearly_ranges:
        folder_name = f"{chunk_start.strftime('%Y%m%d')}_{chunk_end.strftime('%Y%m%d')}"
        chunk_output = base_output / folder_name
        tasks.append(
            {
                "output_directory": str(chunk_output),
                "start_date": chunk_start.isoformat(),
                "end_date": chunk_end.isoformat(),
                "start_page": 1,
                "end_page": None,
                "page_size": page_size,
                "wait_seconds": wait_seconds,
                "timeout": timeout,
                "company_name": (search_filters or {}).get("searchCorpName", ""),
                "submitter_name": (search_filters or {}).get("submitOblgNm", ""),
                "market_label": str(payload.get("market_label") or ""),
                "securities_label": str(payload.get("securities_label") or ""),
                "disclosure_type_groups": disclosure_type_groups or {},
                "last_report_only": last_report_only,
                "worker_count": 1,
                "resume_yearly": resume_yearly,
                "log_limit": payload.get("log_limit") or 20,
                "_folder_name": folder_name,
            }
        )

    chunk_results_by_folder: dict[str, dict[str, Any]] = {}
    if worker_count == 1:
        for task in tasks:
            folder_name = str(task["_folder_name"])
            _append_progress(progress_log, f"[{folder_name}] worker_start thread=main", progress_callback)
            chunk_results_by_folder[folder_name] = _run_yearly_task(
                task,
                resume_yearly=resume_yearly,
                progress_callback=lambda line, folder=folder_name: _append_progress(
                    progress_log,
                    f"[{folder}] {line}",
                    progress_callback,
                ),
            )
            _append_progress(progress_log, f"[{folder_name}] worker_done", progress_callback)
    else:
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="kind-download") as executor:
            future_to_folder = {}
            for worker_index, task in enumerate(tasks, start=1):
                folder_name = str(task["_folder_name"])
                _append_progress(
                    progress_log,
                    f"[{folder_name}] worker_submit index={worker_index}/{len(tasks)}",
                    progress_callback,
                )
                future = executor.submit(
                    _run_yearly_task,
                    task,
                    resume_yearly=resume_yearly,
                    progress_callback=lambda line, folder=folder_name: _append_progress(
                        progress_log,
                        f"[{folder}] {line}",
                        progress_callback,
                    ),
                )
                future_to_folder[future] = folder_name
            for future in as_completed(future_to_folder):
                folder_name = future_to_folder[future]
                try:
                    chunk_results_by_folder[folder_name] = future.result()
                    _append_progress(progress_log, f"[{folder_name}] worker_done", progress_callback)
                except Exception as exc:
                    _append_progress(progress_log, f"[{folder_name}] worker_failed error={exc}", progress_callback)
                    raise ValueError(f"{folder_name} download failed: {exc}") from exc

    results: list[dict[str, Any]] = []
    for task in tasks:
        folder_name = str(task["_folder_name"])
        result = chunk_results_by_folder[folder_name]
        results.append(
            {
                "folder": folder_name,
                "output_directory": result.get("output_directory"),
                "pagination": result.get("pagination"),
                "download_status": result.get("download_status"),
            }
        )

    return {
        "mode": "yearly",
        "base_output_directory": str(base_output),
        "ranges": len(yearly_ranges),
        "worker_count": worker_count,
        "results": results,
        "progress_log": list(progress_log),
    }


def _run_resume(payload: dict[str, Any], progress_callback: Any | None = None) -> dict[str, Any]:
    output_directory_raw = str(payload.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    output_directory = Path(output_directory_raw).expanduser().resolve()
    if not output_directory.is_dir():
        raise ValueError(f"directory not found: {output_directory}")

    paging = _detect_pagination(output_directory)
    if paging is None:
        raise ValueError("pagination info not found in output directory")

    saved_input = _load_workflow_input(output_directory)
    if saved_input is None:
        raise ValueError("kind_workflow.input.json is missing")

    total_pages = int(paging["total_pages"])
    downloaded_pages = int(paging["downloaded_pages"])
    page_size = int(saved_input.get("page_size", 100))
    status_before = _download_integrity_status(output_directory, page_size)
    progress_log, local_progress_callback = _build_progress_collector(external_callback=progress_callback)
    _append_status_progress(progress_log, status_before, progress_callback)
    start_page = downloaded_pages + 1
    if start_page > total_pages:
        return {
            "mode": "resume",
            "output_directory": str(output_directory),
            "message": "all pages already downloaded",
            "pagination": paging,
            "download_status": status_before,
            "progress_log": list(progress_log),
        }

    wait_seconds = _as_float(payload, "wait_seconds", float(saved_input.get("wait_seconds_between_requests", 1.0)))
    timeout = _as_float(payload, "timeout", float(saved_input.get("timeout", 20.0)))
    if wait_seconds < 0:
        raise ValueError("wait_seconds must be >= 0")
    if timeout <= 0:
        raise ValueError("timeout must be > 0")

    download_pages(
        output_directory=output_directory,
        request_headers=saved_input["request_headers"],
        start_date=saved_input["start_date"],
        end_date=saved_input["end_date"],
        start_page=start_page,
        end_page=total_pages,
        page_size=int(saved_input.get("page_size", 100)),
        search_filters=saved_input.get("search_filters") or None,
        disclosure_type_groups=saved_input.get("disclosure_type_groups") or None,
        last_report_only=saved_input.get("last_report_only"),
        include_previous_disclosures=saved_input.get("include_previous_disclosures"),
        wait_seconds_between_requests=wait_seconds,
        timeout=timeout,
        progress_callback=local_progress_callback,
        saved_file_validator=make_page_size_integrity_validator(
            expected_page_size=page_size,
        ),
    )
    status_after = _download_integrity_status(output_directory, page_size)
    _append_status_progress(progress_log, status_after, progress_callback)
    return {
        "mode": "resume",
        "output_directory": str(output_directory),
        "pagination": status_after.get("pagination"),
        "download_status": status_after,
        "progress_log": list(progress_log),
    }


def build_download_options_payload(*, default_output_directory: str | Path) -> dict[str, Any]:
    return {
        "default_output_directory": str(Path(default_output_directory).resolve()),
        "market_types": [{"label": label, "value": value} for label, value in MARKET_TYPES.items()],
        "securities_types": [{"label": label, "value": value} for label, value in SECURITIES_TYPES.items()],
        "disclosure_groups": [
            {
                "suffix": suffix,
                "label": label,
                "items": [{"code": code, "name": name} for code, name in items],
            }
            for suffix, label, items in DISCLOSURE_GROUPS
        ],
    }


def build_download_preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    output_directory_raw = str(payload.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    start_date_raw = str(payload.get("start_date") or "").strip()
    end_date_raw = str(payload.get("end_date") or "").strip()
    if not start_date_raw or not end_date_raw:
        raise ValueError("start_date and end_date are required")
    _parse_iso_date(start_date_raw, "start_date")
    _parse_iso_date(end_date_raw, "end_date")

    start_page = _as_int(payload, "start_page", 1)
    end_page = payload.get("end_page")
    end_page_value = _as_int(payload, "end_page", start_page) if end_page not in ("", None) else start_page
    page_size = _as_int(payload, "page_size", 100)
    wait_seconds = _as_float(payload, "wait_seconds", 1.0)
    timeout = _as_float(payload, "timeout", 20.0)
    if wait_seconds < 0:
        raise ValueError("wait_seconds must be >= 0")
    if timeout <= 0:
        raise ValueError("timeout must be > 0")

    workflow = KindWorkflow()
    workflow.configure(
        output_directory=output_directory_raw,
        request_headers=DEFAULT_REQUEST_HEADERS,
        start_date=start_date_raw,
        end_date=end_date_raw,
        start_page=start_page,
        end_page=end_page_value,
        page_size=page_size,
        search_filters=_build_search_filters(payload),
        disclosure_type_groups=_normalize_disclosure_type_groups(payload),
        last_report_only=_as_bool(payload, "last_report_only"),
        include_previous_disclosures=None,
        wait_seconds_between_requests=wait_seconds,
        timeout=timeout,
    )
    request_data = workflow.build_request_data(page_number=start_page)
    return {
        "mode": str(payload.get("mode") or "single"),
        "request_data": [{"name": name, "value": value} for name, value in request_data],
    }


def build_download_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    output_directory_raw = str(payload.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    output_directory = Path(output_directory_raw).expanduser().resolve()
    if not output_directory.is_dir():
        raise ValueError(f"directory not found: {output_directory}")

    saved_input = _load_workflow_input(output_directory) or {}
    page_size = _as_int(payload, "page_size", int(saved_input.get("page_size") or 100))
    status = _download_integrity_status(output_directory, page_size)
    progress_log: deque[str] = deque(maxlen=_as_log_limit(payload))
    _append_status_progress(progress_log, status)
    return {
        "mode": "status",
        "output_directory": str(output_directory),
        "pagination": status.get("pagination"),
        "download_status": status,
        "progress_log": list(progress_log),
    }


def run_download_action(payload: dict[str, Any], progress_callback: Any | None = None) -> dict[str, Any]:
    mode = str(payload.get("mode") or "single").strip().lower()
    if mode == "single":
        return _run_single(payload, progress_callback=progress_callback)
    if mode == "yearly":
        return _run_yearly(payload, progress_callback=progress_callback)
    if mode == "resume":
        return _run_resume(payload, progress_callback=progress_callback)
    raise ValueError("mode must be one of: single, yearly, resume")


def _job_snapshot(job: DownloadJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "progress_log": list(job.progress_log),
        "result": job.result,
        "error": job.error,
    }


def _update_job(job_id: str, **updates: Any) -> None:
    with _DOWNLOAD_JOBS_LOCK:
        job = _DOWNLOAD_JOBS[job_id]
        for key, value in updates.items():
            setattr(job, key, value)
        job.updated_at = time.time()


def _append_job_progress(job_id: str, message: str) -> None:
    with _DOWNLOAD_JOBS_LOCK:
        job = _DOWNLOAD_JOBS[job_id]
        timestamp = time.strftime("%H:%M:%S")
        job.progress_log.append(f"[{timestamp}] {message}")
        job.updated_at = time.time()


def start_download_job(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    job = DownloadJob(id=job_id, progress_log=deque(maxlen=_as_log_limit(payload)))
    with _DOWNLOAD_JOBS_LOCK:
        _DOWNLOAD_JOBS[job_id] = job

    def _worker() -> None:
        try:
            _update_job(job_id, status="running")
            _append_job_progress(job_id, f"JOB start id={job_id}")
            for line in _download_payload_summary(payload):
                _append_job_progress(job_id, f"JOB {line}")
            result = run_download_action(
                payload,
                progress_callback=lambda message: _append_job_progress(job_id, message),
            )
            _update_job(job_id, status="completed", result=result)
            _append_job_progress(job_id, f"JOB completed id={job_id}")
        except Exception as exc:  # pragma: no cover - runtime path
            _update_job(job_id, status="failed", error=str(exc))
            _append_job_progress(job_id, f"JOB failed error={exc}")

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return get_download_job(job_id)


def get_download_job(job_id: str) -> dict[str, Any]:
    with _DOWNLOAD_JOBS_LOCK:
        job = _DOWNLOAD_JOBS.get(job_id)
        if job is None:
            raise ValueError(f"download job not found: {job_id}")
        return _job_snapshot(job)
