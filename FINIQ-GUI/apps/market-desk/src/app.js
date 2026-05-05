const HOME_PATH = "/";
const DETAIL_PATH = "/company.html";
const FALLBACK_OUTPUT_ROOT = "/Users/wonwoolee/Documents/GitHub/FINIQ/resources/kind";
const FALLBACK_PRICE_ROOT = "/Users/wonwoolee/Documents/GitHub/FINIQ/resources/database";
const FALLBACK_PRICE_DIR = "/Users/wonwoolee/Documents/GitHub/FINIQ/resources/database/by_item";
const FALLBACK_CLASSIFICATION_PATH = "/Users/wonwoolee/Documents/GitHub/FINIQ/resources/kind/kind.company_classification.json";
const FALLBACK_CONFIG = {
  output_root: FALLBACK_OUTPUT_ROOT,
  quanti_dir: FALLBACK_PRICE_DIR,
  price_root_directory: FALLBACK_PRICE_ROOT,
  selected_price_path: FALLBACK_PRICE_DIR,
  selected_classification_path: FALLBACK_CLASSIFICATION_PATH,
  price_files: [{ path: FALLBACK_PRICE_DIR, label: "기본값 / by_item" }],
  classification_files: [{ path: FALLBACK_CLASSIFICATION_PATH, label: "기본값 / kind.company_classification.json" }],
  range_options: ["검색기간", "1개월", "3개월", "6개월", "1년", "전체"],
  display_frequency_options: ["자동", "일봉", "주봉", "월봉"],
};

const state = {
  page: document.body.dataset.page || "home",
  config: null,
  settingsOpen: true,
  apiAvailable: true,
  apiErrorMessage: "",
  companies: [],
  priceRootDir: FALLBACK_PRICE_ROOT,
  selectedCompanyKey: "",
  selectedClassificationPath: FALLBACK_CLASSIFICATION_PATH,
  outputRoot: FALLBACK_OUTPUT_ROOT,
  priceDir: FALLBACK_PRICE_DIR,
  priceSource: "quanti",
  rangeLabel: "검색기간",
  displayFrequency: "자동",
  keyword: "",
  stockCodeDraft: "",
  stockCodeOverrides: {},
  startDate: "",
  endDate: "",
  insight: null,
  groupVisibility: {},
  chart: null,
  candleSeries: null,
  volumeSeries: null,
  markerHandle: null,
  resizeObserver: null,
};

let companySearchTimer = null;

const elements = {
  companySearchInput: document.getElementById("companySearchInput"),
  searchCompaniesBtn: document.getElementById("searchCompaniesBtn"),
  toggleSettingsBtn: document.getElementById("toggleSettingsBtn"),
  settingsPanel: document.getElementById("settingsPanel"),
  priceDirInput: document.getElementById("priceDirInput"),
  priceFileSelect: document.getElementById("priceFileSelect"),
  rootDirInput: document.getElementById("rootDirInput"),
  classificationSelect: document.getElementById("classificationSelect"),
  saveSettingsBtn: document.getElementById("saveSettingsBtn"),
  settingsSaveStatus: document.getElementById("settingsSaveStatus"),
  companyCountBadge: document.getElementById("companyCountBadge"),
  companyList: document.getElementById("companyList"),
  backToHomeBtn: document.getElementById("backToHomeBtn"),
  heroCompanyName: document.getElementById("heroCompanyName"),
  heroMeta: document.getElementById("heroMeta"),
  rangeChipGroup: document.getElementById("rangeChipGroup"),
  startDateInput: document.getElementById("startDateInput"),
  endDateInput: document.getElementById("endDateInput"),
  frequencySelect: document.getElementById("frequencySelect"),
  stockCodeInput: document.getElementById("stockCodeInput"),
  detailPriceDirInput: document.getElementById("detailPriceDirInput"),
  applyFiltersBtn: document.getElementById("applyFiltersBtn"),
  statusBanner: document.getElementById("statusBanner"),
  chartTitle: document.getElementById("chartTitle"),
  chartSubtitle: document.getElementById("chartSubtitle"),
  quoteStrip: document.getElementById("quoteStrip"),
  chartContainer: document.getElementById("chartContainer"),
  groupFilters: document.getElementById("groupFilters"),
  timelineBody: document.getElementById("timelineBody"),
  timelineCountBadge: document.getElementById("timelineCountBadge"),
};

function parentDirectory(path) {
  const normalized = String(path || "").trim().replace(/[\\/]+$/, "");
  if (!normalized) {
    return "";
  }
  const lastSeparatorIndex = Math.max(normalized.lastIndexOf("/"), normalized.lastIndexOf("\\"));
  if (lastSeparatorIndex <= 0) {
    return normalized;
  }
  return normalized.slice(0, lastSeparatorIndex);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return new Intl.NumberFormat("ko-KR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value));
}

function toneClass(value) {
  const number = Number(value);
  if (Number.isNaN(number)) {
    return "quote-neutral";
  }
  if (number > 0) {
    return "quote-up";
  }
  if (number < 0) {
    return "quote-down";
  }
  return "quote-neutral";
}

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

async function getJson(url, params = null) {
  const requestUrl = params ? `${url}?${new URLSearchParams(params).toString()}` : url;
  const response = await fetch(requestUrl);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return response.json();
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    throw new Error(errorPayload.error || `Request failed: ${response.status}`);
  }
  return response.json();
}

function setStatus(message, isError = false) {
  if (!elements.statusBanner) {
    return;
  }
  if (!message) {
    elements.statusBanner.hidden = true;
    elements.statusBanner.textContent = "";
    elements.statusBanner.style.background = "";
    elements.statusBanner.style.borderColor = "";
    elements.statusBanner.style.color = "";
    return;
  }
  elements.statusBanner.hidden = false;
  elements.statusBanner.textContent = message;
  elements.statusBanner.style.background = isError ? "rgba(254, 226, 226, 0.92)" : "";
  elements.statusBanner.style.borderColor = isError ? cssVar("--red", "#dc2626") : "";
  elements.statusBanner.style.color = isError ? "#991b1b" : "";
}

function setSettingsStatus(message, isError = false) {
  if (!elements.settingsSaveStatus) {
    return;
  }
  if (!message) {
    elements.settingsSaveStatus.hidden = true;
    elements.settingsSaveStatus.textContent = "";
    elements.settingsSaveStatus.dataset.tone = "";
    return;
  }
  elements.settingsSaveStatus.hidden = false;
  elements.settingsSaveStatus.textContent = message;
  elements.settingsSaveStatus.dataset.tone = isError ? "error" : "success";
}

function syncDirectoryInputs() {
  if (elements.priceDirInput) {
    elements.priceDirInput.value = state.priceRootDir;
  }
  if (elements.detailPriceDirInput) {
    elements.detailPriceDirInput.value = state.priceDir;
  }
  if (elements.rootDirInput) {
    elements.rootDirInput.value = state.outputRoot;
  }
}

function syncSearchInput() {
  if (elements.companySearchInput) {
    elements.companySearchInput.value = state.keyword;
  }
}

function syncDetailInputs() {
  if (elements.startDateInput) {
    elements.startDateInput.value = state.startDate;
  }
  if (elements.endDateInput) {
    elements.endDateInput.value = state.endDate;
  }
  if (elements.frequencySelect) {
    elements.frequencySelect.value = state.displayFrequency;
  }
  if (elements.stockCodeInput) {
    elements.stockCodeInput.value = state.stockCodeDraft;
  }
  if (elements.detailPriceDirInput) {
    elements.detailPriceDirInput.value = state.priceDir;
  }
}

function renderSettingsVisibility() {
  if (!elements.settingsPanel) {
    return;
  }
  elements.settingsPanel.hidden = !state.settingsOpen;
}

function renderClassificationOptions(files, selectedPath) {
  if (!elements.classificationSelect) {
    return;
  }
  elements.classificationSelect.innerHTML = files
    .map(
      (file) => `
        <option value="${escapeHtml(file.path)}" ${selectedPath === file.path ? "selected" : ""}>
          ${escapeHtml(file.label)}
        </option>
      `,
    )
    .join("");
}

function renderPriceOptions(files, selectedPath) {
  if (!elements.priceFileSelect) {
    return;
  }
  if (!files.length) {
    elements.priceFileSelect.innerHTML = '<option value="">선택 가능한 파일이 없습니다.</option>';
    elements.priceFileSelect.value = "";
    return;
  }
  elements.priceFileSelect.innerHTML = files
    .map(
      (file) => `
        <option value="${escapeHtml(file.path)}" ${selectedPath === file.path ? "selected" : ""}>
          ${escapeHtml(file.label)}
        </option>
      `,
    )
    .join("");
}

function renderRangeChips(rangeOptions) {
  if (!elements.rangeChipGroup) {
    return;
  }
  elements.rangeChipGroup.innerHTML = rangeOptions
    .map(
      (label) => `
        <button
          type="button"
          class="chip ${state.rangeLabel === label ? "active" : ""}"
          data-range-label="${escapeHtml(label)}"
        >
          ${escapeHtml(label)}
        </button>
      `,
    )
    .join("");
}

function renderFrequencyOptions(options) {
  if (!elements.frequencySelect) {
    return;
  }
  elements.frequencySelect.innerHTML = options
    .map(
      (label) => `
        <option value="${escapeHtml(label)}" ${state.displayFrequency === label ? "selected" : ""}>
          ${escapeHtml(label)}
        </option>
      `,
    )
    .join("");
}

function renderCompanyList() {
  if (!elements.companyList || !elements.companyCountBadge) {
    return;
  }
  if (!state.apiAvailable) {
    elements.companyCountBadge.textContent = "0";
    elements.companyList.innerHTML = `<div class="empty-state">백엔드 연결 실패: ${escapeHtml(
      state.apiErrorMessage || "api/config",
    )}</div>`;
    return;
  }
  elements.companyCountBadge.textContent = formatNumber(state.companies.length);
  if (!state.selectedClassificationPath) {
    elements.companyList.innerHTML = '<div class="empty-state">분류 JSON을 먼저 선택해 주세요.</div>';
    return;
  }
  if (!state.companies.length) {
    elements.companyList.innerHTML = '<div class="empty-state">조건에 맞는 회사가 없습니다.</div>';
    return;
  }
  elements.companyList.innerHTML = state.companies
    .map((company) => {
      const tags = (company.badges || [])
        .slice(0, 3)
        .filter(Boolean)
        .map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`)
        .join("");
      return `
        <button type="button" class="company-link" data-company-key="${escapeHtml(company.company_key)}">
          <div class="company-main">
            <div class="company-name-row">
              <span class="company-name">${escapeHtml(company.company_name || "이름 미상")}</span>
              <span class="company-market-pill">${escapeHtml(company.market || "시장 미상")}</span>
            </div>
            <div class="company-tags">${tags || '<span class="tag">태그 없음</span>'}</div>
          </div>
          <div class="company-stat">
            <span class="company-stat-label">최근 공시</span>
            <strong class="company-stat-value">${escapeHtml(company.last_disclosed_at || "-")}</strong>
          </div>
          <div class="company-stat">
            <span class="company-stat-label">공시 건수</span>
            <strong class="company-stat-value">${formatNumber(company.disclosure_count)}건</strong>
          </div>
        </button>
      `;
    })
    .join("");
}

function renderHero() {
  if (!elements.heroCompanyName) {
    return;
  }
  const company = state.insight?.company;
  if (!company) {
    elements.heroCompanyName.textContent = "회사 선택 대기 중";
    elements.heroMeta.textContent = "선택한 회사의 공시와 주가를 함께 확인합니다.";
    return;
  }
  const metaParts = [
    company.market || "시장 미상",
    `공시 ${formatNumber(company.disclosure_count)}건`,
    ...(company.badges || []).slice(0, 2),
  ].filter(Boolean);
  elements.heroCompanyName.textContent = company.company_name || "이름 미상";
  elements.heroMeta.textContent = metaParts.join(" · ");
  document.title = `${company.company_name || "회사"} | FINIQ DataScraper Dart Navigator`;
}

function groupColor(groupName) {
  const group = (state.insight?.chart?.groups || []).find((entry) => entry.name === groupName);
  return group?.color || "#94a3b8";
}

function renderTimeline() {
  if (!elements.timelineBody || !elements.timelineCountBadge) {
    return;
  }
  const hasVisibilityState = Object.keys(state.groupVisibility).length > 0;
  const visibleGroups = new Set(
    Object.entries(state.groupVisibility)
      .filter(([, visible]) => visible)
      .map(([name]) => name),
  );
  const timeline = (state.insight?.timeline || []).filter(
    (item) => !hasVisibilityState || visibleGroups.has(item.group),
  );
  elements.timelineCountBadge.textContent = formatNumber(timeline.length);
  if (!timeline.length) {
    elements.timelineBody.innerHTML = '<tr><td colspan="6" class="empty-state">표시할 공시가 없습니다.</td></tr>';
    return;
  }
  elements.timelineBody.innerHTML = timeline
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.disclosed_at || "-")}</td>
          <td>
            <span class="group-pill">
              <span class="dot" style="background:${escapeHtml(groupColor(row.group))}"></span>
              ${escapeHtml(row.group || "-")}
            </span>
          </td>
          <td>${escapeHtml(row.title || "-")}</td>
          <td>${escapeHtml(row.submitter || "-")}</td>
          <td>${escapeHtml(row.acpt_no || "-")}</td>
          <td>${escapeHtml(row.trade_day || "-")}</td>
        </tr>
      `,
    )
    .join("");
}

function renderGroupFilters() {
  if (!elements.groupFilters) {
    return;
  }
  const groups = state.insight?.chart?.groups || [];
  if (!groups.length) {
    elements.groupFilters.innerHTML = '<div class="empty-state">공시 그룹이 없습니다.</div>';
    return;
  }
  if (Object.keys(state.groupVisibility).length === 0) {
    const hasDefaultVisible = groups.some((group) => Boolean(group.default_visible));
    groups.forEach((group) => {
      state.groupVisibility[group.name] = hasDefaultVisible
        ? Boolean(group.default_visible)
        : true;
    });
  }
  elements.groupFilters.innerHTML = groups
    .map(
      (group) => `
        <button type="button" class="chip ${state.groupVisibility[group.name] ? "active" : ""}" data-group-name="${escapeHtml(group.name)}">
          <span class="dot" style="background:${escapeHtml(group.color)}"></span>
          ${escapeHtml(group.name)}
          <span>${formatNumber(group.count)}</span>
        </button>
      `,
    )
    .join("");
}

function renderQuoteStripFromCandle(candle) {
  if (!elements.quoteStrip) {
    return;
  }
  if (!candle) {
    elements.quoteStrip.className = "quote-strip";
    elements.quoteStrip.textContent = "데이터 대기 중";
    return;
  }
  const delta = Number(candle.close) - Number(candle.open);
  elements.quoteStrip.className = `quote-strip ${toneClass(delta)}`;
  elements.quoteStrip.innerHTML = `
    <span><strong>${escapeHtml(candle.time)}</strong></span>
    <span>O <strong>${formatNumber(candle.open)}</strong></span>
    <span>H <strong>${formatNumber(candle.high)}</strong></span>
    <span>L <strong>${formatNumber(candle.low)}</strong></span>
    <span>C <strong>${formatNumber(candle.close)}</strong></span>
    <span>V <strong>${formatNumber(candle.volume)}</strong></span>
  `;
}

function ensureChart() {
  if (state.chart || !elements.chartContainer) {
    return;
  }
  const { createChart, CandlestickSeries, HistogramSeries } = window.MarketDeskCharts;
  state.chart = createChart(elements.chartContainer, {
    layout: {
      background: { type: "solid", color: cssVar("--surface", "#ffffff") },
      textColor: cssVar("--muted", "#5f6f83"),
      fontFamily: "'IBM Plex Sans KR', sans-serif",
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: "rgba(148, 163, 184, 0.18)", style: 2, visible: true },
      horzLines: { color: "rgba(148, 163, 184, 0.18)", style: 2, visible: true },
    },
    rightPriceScale: {
      borderVisible: false,
      scaleMargins: { top: 0.08, bottom: 0.28 },
    },
    timeScale: {
      borderVisible: false,
      timeVisible: true,
      secondsVisible: false,
      fixLeftEdge: true,
      fixRightEdge: true,
    },
  });

  state.candleSeries = state.chart.addSeries(CandlestickSeries, {
    upColor: "#22ab94",
    downColor: "#f23645",
    borderUpColor: "#22ab94",
    borderDownColor: "#f23645",
    wickUpColor: "#22ab94",
    wickDownColor: "#f23645",
    lastValueVisible: true,
    priceLineVisible: true,
    priceLineWidth: 1,
  });
  state.candleSeries.priceScale().applyOptions({
    scaleMargins: {
      top: 0.08,
      bottom: 0.28,
    },
  });

  state.volumeSeries = state.chart.addSeries(HistogramSeries, {
    priceFormat: { type: "volume" },
    priceScaleId: "",
    lastValueVisible: false,
    priceLineVisible: false,
  });
  state.volumeSeries.priceScale().applyOptions({
    scaleMargins: {
      top: 0.76,
      bottom: 0,
    },
  });

  state.chart.subscribeCrosshairMove((param) => {
    if (!param || !param.time) {
      const lastCandle = state.insight?.chart?.candles?.slice(-1)[0];
      renderQuoteStripFromCandle(lastCandle);
      return;
    }
    const candle = param.seriesData.get(state.candleSeries);
    if (!candle) {
      return;
    }
    const volume = param.seriesData.get(state.volumeSeries);
    renderQuoteStripFromCandle({
      time: param.time,
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
      volume: volume?.value,
    });
  });

  state.resizeObserver = new ResizeObserver((entries) => {
    const entry = entries[0];
    if (!entry || !state.chart) {
      return;
    }
    state.chart.applyOptions({
      width: entry.contentRect.width,
      height: entry.contentRect.height,
    });
    state.chart.timeScale().fitContent();
  });
  state.resizeObserver.observe(elements.chartContainer);
}

function renderChart() {
  if (!elements.chartContainer) {
    return;
  }
  ensureChart();
  const candles = state.insight?.chart?.candles || [];
  if (!candles.length) {
    state.candleSeries.setData([]);
    state.volumeSeries.setData([]);
    if (window.MarketDeskCharts.createSeriesMarkers) {
      if (!state.markerHandle) {
        state.markerHandle = window.MarketDeskCharts.createSeriesMarkers(state.candleSeries, []);
      } else {
        state.markerHandle.setMarkers([]);
      }
    }
    elements.chartTitle.textContent = "Price / Volume";
    elements.chartSubtitle.textContent = "주가 데이터가 없습니다.";
    renderQuoteStripFromCandle(null);
    return;
  }

  const candleData = candles.map((candle) => ({
    time: candle.time,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
  }));
  const volumeData = candles.map((candle) => ({
    time: candle.time,
    value: candle.volume,
    color: candle.color + "66",
  }));
  const visibleGroups = new Set(
    Object.entries(state.groupVisibility)
      .filter(([, visible]) => visible)
      .map(([name]) => name),
  );
  const hasVisibilityState = Object.keys(state.groupVisibility).length > 0;
  const markerData = (state.insight?.chart?.markers || []).filter(
    (marker) => !hasVisibilityState || visibleGroups.has(marker.group),
  );

  state.candleSeries.setData(candleData);
  state.volumeSeries.setData(volumeData);
  if (window.MarketDeskCharts.createSeriesMarkers) {
    if (!state.markerHandle) {
      state.markerHandle = window.MarketDeskCharts.createSeriesMarkers(state.candleSeries, markerData);
    } else {
      state.markerHandle.setMarkers(markerData);
    }
  }
  state.chart.timeScale().fitContent();

  const lastCandle = candles[candles.length - 1];
  elements.chartTitle.textContent = `${state.insight.company.company_name || "이름 미상"} · ${state.insight.display_frequency_label}`;
  const visibleRangeEnd = state.insight.visible_range_end || state.insight.range_end;
  elements.chartSubtitle.textContent = `${state.insight.range_start} ~ ${visibleRangeEnd} · Parquet`;
  renderQuoteStripFromCandle(lastCandle);
}

function buildUrl(pathname) {
  const params = new URLSearchParams();
  if (state.selectedClassificationPath) {
    params.set("classification_path", state.selectedClassificationPath);
  }
  if (state.outputRoot) {
    params.set("root_directory", state.outputRoot);
  }
  if (state.priceRootDir) {
    params.set("price_root_directory", state.priceRootDir);
  }
  if (state.priceDir) {
    params.set("price_dir", state.priceDir);
  }
  if (state.keyword) {
    params.set("keyword", state.keyword);
  }
  if (pathname === DETAIL_PATH) {
    if (state.selectedCompanyKey) {
      params.set("company_key", state.selectedCompanyKey);
    }
    if (state.rangeLabel) {
      params.set("range_label", state.rangeLabel);
    }
    if (state.startDate) {
      params.set("start_date", state.startDate);
    }
    if (state.endDate) {
      params.set("end_date", state.endDate);
    }
    if (state.displayFrequency && state.displayFrequency !== "자동") {
      params.set("display_frequency", state.displayFrequency);
    }
    const stockCode = state.stockCodeOverrides[state.selectedCompanyKey] || state.stockCodeDraft;
    if (stockCode) {
      params.set("stock_code", stockCode);
    }
  }
  const query = params.toString();
  return query ? `${pathname}?${query}` : pathname;
}

function updateUrl(pathname, { replace = false } = {}) {
  const nextUrl = buildUrl(pathname);
  const method = replace ? "replaceState" : "pushState";
  window.history[method]({}, "", nextUrl);
}

function applyRouteParams() {
  const url = new URL(window.location.href);
  state.outputRoot = url.searchParams.get("root_directory") || state.outputRoot;
  state.priceRootDir = url.searchParams.get("price_root_directory") || state.priceRootDir;
  state.selectedClassificationPath =
    url.searchParams.get("classification_path") || state.selectedClassificationPath;
  state.priceDir = url.searchParams.get("price_dir") || state.priceDir;
  state.keyword = url.searchParams.get("keyword") || state.keyword;
  state.selectedCompanyKey = url.searchParams.get("company_key") || "";
  state.rangeLabel = url.searchParams.get("range_label") || state.rangeLabel;
  state.startDate = url.searchParams.get("start_date") || state.startDate;
  state.endDate = url.searchParams.get("end_date") || state.endDate;
  state.displayFrequency = url.searchParams.get("display_frequency") || state.displayFrequency;
  const stockCode = url.searchParams.get("stock_code") || "";
  if (state.selectedCompanyKey && stockCode) {
    state.stockCodeOverrides[state.selectedCompanyKey] = stockCode;
    state.stockCodeDraft = stockCode;
  } else if (state.selectedCompanyKey) {
    state.stockCodeDraft = state.stockCodeOverrides[state.selectedCompanyKey] || "";
  } else {
    state.stockCodeDraft = "";
  }
}

async function loadConfig() {
  try {
    state.config = await getJson("/api/config");
    state.apiAvailable = true;
    state.apiErrorMessage = "";
  } catch (error) {
    state.config = { ...FALLBACK_CONFIG };
    state.apiAvailable = false;
    state.apiErrorMessage = error.message || "설정 API 연결에 실패했습니다.";
    setSettingsStatus(`백엔드 연결 실패: ${state.apiErrorMessage}`, true);
  }
  state.outputRoot = state.outputRoot || state.config.output_root;
  state.priceDir = state.priceDir || state.config.selected_price_path || state.config.quanti_dir;
  state.priceRootDir =
    state.priceRootDir || parentDirectory(state.priceDir) || state.config.price_root_directory;
  state.selectedClassificationPath =
    state.selectedClassificationPath || state.config.selected_classification_path || "";
  renderPriceOptions(state.config.price_files || [], state.priceDir);
  renderClassificationOptions(state.config.classification_files, state.selectedClassificationPath);
  renderRangeChips(state.config.range_options);
  renderFrequencyOptions(state.config.display_frequency_options);
  syncDirectoryInputs();
  syncSearchInput();
  syncDetailInputs();

  if (!state.apiAvailable) {
    return;
  }

  if (
    state.priceRootDir &&
    state.config.price_root_directory &&
    state.priceRootDir !== state.config.price_root_directory
  ) {
    await reloadPriceSources();
  }
}

async function reloadClassifications() {
  if (!state.apiAvailable) {
    throw new Error("백엔드가 연결되지 않아 공시 소스를 불러올 수 없습니다.");
  }
  const payload = await getJson("/api/classifications", {
    root_directory: state.outputRoot,
  });
  state.outputRoot = payload.root_directory || state.outputRoot;
  state.selectedClassificationPath = payload.selected_classification_path || "";
  renderClassificationOptions(payload.classification_files, state.selectedClassificationPath);
  syncDirectoryInputs();
}

async function reloadPriceSources() {
  if (!state.apiAvailable) {
    throw new Error("백엔드가 연결되지 않아 주가 소스를 불러올 수 없습니다.");
  }
  if (!state.priceRootDir) {
    state.priceRootDir = state.config?.price_root_directory || parentDirectory(state.priceDir);
  }
  const payload = await getJson("/api/price-sources", {
    root_directory: state.priceRootDir,
    selected_path: state.priceDir,
  });
  state.priceRootDir = payload.price_root_directory || state.priceRootDir;
  state.priceDir = payload.selected_price_path || "";
  renderPriceOptions(payload.price_files || [], state.priceDir);
  syncDirectoryInputs();
}

async function saveSettings() {
  if (!state.apiAvailable) {
    throw new Error("백엔드가 연결되지 않아 설정을 저장할 수 없습니다.");
  }
  state.outputRoot = elements.rootDirInput?.value.trim() || state.outputRoot;
  state.priceRootDir = elements.priceDirInput?.value.trim() || state.priceRootDir;

  if (state.outputRoot) {
    await reloadClassifications();
  }
  if (state.priceRootDir) {
    await reloadPriceSources();
  }

  const payload = await postJson("/api/settings", {
    output_root: state.outputRoot,
    selected_classification_path: state.selectedClassificationPath,
    price_root_directory: state.priceRootDir,
    quanti_dir: state.priceDir,
  });

  state.config = payload;
  state.outputRoot = payload.output_root || state.outputRoot;
  state.priceRootDir = payload.price_root_directory || state.priceRootDir;
  state.priceDir = payload.selected_price_path || payload.quanti_dir || state.priceDir;
  state.selectedClassificationPath =
    payload.selected_classification_path || state.selectedClassificationPath;
  renderPriceOptions(payload.price_files || [], state.priceDir);
  renderClassificationOptions(payload.classification_files || [], state.selectedClassificationPath);
  syncDirectoryInputs();
  updateUrl(HOME_PATH, { replace: true });
  await loadCompanies();
}

async function loadCompanies() {
  if (!state.apiAvailable) {
    state.companies = [];
    renderCompanyList();
    return;
  }
  if (!state.selectedClassificationPath) {
    state.companies = [];
    renderCompanyList();
    return;
  }
  const payload = await getJson("/api/companies", {
    classification_path: state.selectedClassificationPath,
    keyword: state.keyword,
  });
  state.companies = payload.companies || [];
  renderCompanyList();
}

async function loadInsight() {
  if (!state.apiAvailable) {
    setStatus("백엔드 연결이 없어 상세 데이터를 불러올 수 없습니다.", true);
    return;
  }
  if (!state.selectedClassificationPath || !state.selectedCompanyKey) {
    window.location.replace(HOME_PATH);
    return;
  }
  setStatus("Parquet 주가 데이터를 불러오는 중입니다...");
  const activeOverride = state.stockCodeOverrides[state.selectedCompanyKey] || "";
  const payload = await getJson("/api/insight", {
    classification_path: state.selectedClassificationPath,
    company_key: state.selectedCompanyKey,
    start_date: state.startDate,
    end_date: state.endDate,
    range_label: state.rangeLabel,
    display_frequency: state.displayFrequency,
    price_source: state.priceSource,
    quanti_dir: state.priceDir,
    stock_code: activeOverride,
  });
  state.insight = payload;
  state.startDate = payload.manual_start;
  state.endDate = payload.manual_end;
  state.stockCodeDraft = activeOverride || payload.stock_code || payload.inferred_stock_code || "";
  if (state.selectedCompanyKey && state.stockCodeDraft) {
    state.stockCodeOverrides[state.selectedCompanyKey] = state.stockCodeDraft;
  }
  syncDetailInputs();
  renderHero();
  state.groupVisibility = {};
  renderGroupFilters();
  renderTimeline();
  renderChart();
  setStatus((payload.messages || []).join(" · "), (payload.messages || []).length > 0);
}

function openDetail(companyKey) {
  state.selectedCompanyKey = companyKey;
  state.stockCodeDraft = state.stockCodeOverrides[companyKey] || "";
  window.location.assign(buildUrl(DETAIL_PATH));
}

function bindHomeEvents() {
  elements.toggleSettingsBtn.addEventListener("click", () => {
    state.settingsOpen = !state.settingsOpen;
    renderSettingsVisibility();
  });

  elements.searchCompaniesBtn.addEventListener("click", async () => {
    try {
      state.keyword = elements.companySearchInput.value.trim();
      updateUrl(HOME_PATH);
      await loadCompanies();
    } catch (error) {
      console.error(error);
    }
  });

  elements.companySearchInput.addEventListener("input", (event) => {
    state.keyword = event.target.value.trim();
    window.clearTimeout(companySearchTimer);
    companySearchTimer = window.setTimeout(async () => {
      try {
        updateUrl(HOME_PATH);
        await loadCompanies();
      } catch (error) {
        console.error(error);
      }
    }, 180);
  });

  elements.companySearchInput.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    window.clearTimeout(companySearchTimer);
    state.keyword = event.target.value.trim();
    updateUrl(HOME_PATH);
    await loadCompanies();
  });

  elements.rootDirInput.addEventListener("input", (event) => {
    state.outputRoot = event.target.value.trim();
  });

  const syncPriceRootDir = (value) => {
    state.priceRootDir = value.trim();
    state.priceDir = value.trim();
    syncDirectoryInputs();
  };

  elements.priceDirInput.addEventListener("input", (event) => {
    syncPriceRootDir(event.target.value);
  });

  const refreshPriceSources = async () => {
    try {
      await reloadPriceSources();
      updateUrl(HOME_PATH, { replace: true });
    } catch (error) {
      console.error(error);
    }
  };

  elements.priceDirInput.addEventListener("change", refreshPriceSources);
  elements.priceDirInput.addEventListener("blur", refreshPriceSources);

  elements.priceFileSelect.addEventListener("change", (event) => {
    state.priceDir = event.target.value;
    syncDirectoryInputs();
    updateUrl(HOME_PATH, { replace: true });
  });

  const refreshClassifications = async () => {
    try {
      await reloadClassifications();
      updateUrl(HOME_PATH);
      await loadCompanies();
    } catch (error) {
      console.error(error);
    }
  };

  elements.rootDirInput.addEventListener("change", refreshClassifications);
  elements.rootDirInput.addEventListener("blur", refreshClassifications);

  elements.classificationSelect.addEventListener("change", async (event) => {
    state.selectedClassificationPath = event.target.value;
    updateUrl(HOME_PATH);
    await loadCompanies();
  });

  elements.saveSettingsBtn.addEventListener("click", async () => {
    try {
      setSettingsStatus("설정을 저장하는 중입니다...");
      await saveSettings();
      setSettingsStatus("설정을 저장했습니다.");
    } catch (error) {
      console.error(error);
      setSettingsStatus(error.message, true);
    }
  });

  elements.companyList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-company-key]");
    if (!button) {
      return;
    }
    openDetail(button.dataset.companyKey);
  });
}

function bindDetailEvents() {
  const syncPriceDir = (value) => {
    state.priceDir = value.trim();
    state.priceRootDir = parentDirectory(state.priceDir);
    syncDirectoryInputs();
  };

  elements.backToHomeBtn.addEventListener("click", () => {
    window.location.assign(buildUrl(HOME_PATH));
  });

  elements.rangeChipGroup.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-range-label]");
    if (!button) {
      return;
    }
    state.rangeLabel = button.dataset.rangeLabel;
    renderRangeChips(state.config.range_options);
    updateUrl(DETAIL_PATH);
    await loadInsight();
  });

  elements.frequencySelect.addEventListener("change", (event) => {
    state.displayFrequency = event.target.value;
  });

  elements.startDateInput.addEventListener("change", (event) => {
    state.startDate = event.target.value;
    state.rangeLabel = "검색기간";
    renderRangeChips(state.config.range_options);
  });

  elements.endDateInput.addEventListener("change", (event) => {
    state.endDate = event.target.value;
    state.rangeLabel = "검색기간";
    renderRangeChips(state.config.range_options);
  });

  elements.stockCodeInput.addEventListener("input", (event) => {
    state.stockCodeDraft = event.target.value.trim();
    if (state.stockCodeDraft) {
      state.stockCodeOverrides[state.selectedCompanyKey] = state.stockCodeDraft;
      return;
    }
    delete state.stockCodeOverrides[state.selectedCompanyKey];
  });

  elements.detailPriceDirInput.addEventListener("input", (event) => {
    syncPriceDir(event.target.value);
  });

  elements.applyFiltersBtn.addEventListener("click", async () => {
    updateUrl(DETAIL_PATH);
    await loadInsight();
  });

  elements.groupFilters.addEventListener("click", (event) => {
    const button = event.target.closest("[data-group-name]");
    if (!button) {
      return;
    }
    const groupName = button.dataset.groupName;
    state.groupVisibility[groupName] = !state.groupVisibility[groupName];
    renderGroupFilters();
    renderTimeline();
    renderChart();
  });
}

async function bootstrapHome() {
  renderSettingsVisibility();
  bindHomeEvents();
  await loadConfig();
  await loadCompanies();
}

async function bootstrapDetail() {
  bindDetailEvents();
  await loadConfig();
  await loadInsight();
}

async function bootstrap() {
  applyRouteParams();
  if (state.page === "detail") {
    await bootstrapDetail();
    return;
  }
  await bootstrapHome();
}

bootstrap().catch((error) => {
  console.error(error);
  setStatus(error.message, true);
});
