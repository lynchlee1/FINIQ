# Price Chart Crosshair OHLCV Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show TradingView-style hover values and crosshair labels on the FINIQ-owned `주가-공시 차트`.

**Architecture:** Keep the Canvas chart responsible for pointer index, dashed crosshair, price label, and time label. Keep React responsible for the top-left OHLC, change, percent change, and volume readout using existing crosshair payload data.

**Tech Stack:** React 19, Next.js app code, FINIQ-owned Canvas chart implementation, Node built-in test runner.

## Global Constraints

- Do not add TradingView or `lightweight-charts`.
- Reuse existing chart terms from `docs/ui-terminology.md`.
- Touch only chart hover/crosshair behavior, tests, and `PLANS.md`.
- Use TDD: add failing frontend regression tests before implementation.

---

### Task 1: Hover OHLCV Readout

**Files:**
- Modify: `tests/frontend/priceChart.test.mjs`
- Modify: `frontend/finiq_GUI/apps/market-desk/src/components/PriceChart.tsx`

**Interfaces:**
- Consumes: `PriceChartDatum` data array and `chart.subscribeCrosshairMove` payload.
- Produces: React-rendered hover readout containing `O`, `H`, `L`, `C`, signed price change, signed percent change, and `Vol`.

- [x] **Step 1: Write the failing test**

Add assertions that `PriceChart.tsx` keeps hover state, derives previous candle change, formats percent change, and renders `Vol`.

- [x] **Step 2: Run test to verify it fails**

Run: `node --test tests/frontend/priceChart.test.mjs`
Expected: FAIL because the readout helpers/state/rendering are not implemented.

- [x] **Step 3: Write minimal implementation**

Add helper functions in `PriceChart.tsx` for number, percent, volume, and signed change formatting. Track the hovered candle from `subscribeCrosshairMove`, fall back to the latest candle when not hovering, and render the readout above the chart body.

- [x] **Step 4: Run test to verify it passes**

Run: `node --test tests/frontend/priceChart.test.mjs`
Expected: PASS.

### Task 2: Crosshair Drawing Contract

**Files:**
- Modify: `tests/frontend/priceChart.test.mjs`
- Modify: `frontend/finiq_GUI/apps/market-desk/src/lib/charts.ts`

**Interfaces:**
- Consumes: `ChartApi.crosshair` with `{ index, x, y }`.
- Produces: dashed vertical and horizontal crosshair lines with right-side price label and bottom time label.

- [x] **Step 1: Write the failing test**

Add assertions that `drawCrosshair` draws dashed lines, emits price labels through `yToPrice`, and emits time labels.

- [x] **Step 2: Run test to verify it fails if the drawing contract is absent**

Run: `node --test tests/frontend/priceChart.test.mjs`
Expected: FAIL only if the existing chart lacks one of the required drawing contract markers.

- [x] **Step 3: Write minimal implementation**

Patch only the missing drawing behavior in `charts.ts`. If existing code already satisfies the test, leave `charts.ts` unchanged.

- [x] **Step 4: Run test to verify it passes**

Run: `node --test tests/frontend/priceChart.test.mjs`
Expected: PASS.

### Task 3: Completion Record

**Files:**
- Modify: `PLANS.md`

**Interfaces:**
- Consumes: final implementation and verification output.
- Produces: completed-change record with purpose, implementation summary, and verification commands.

- [x] **Step 1: Update `PLANS.md`**

Add a concise completed-change section for the hover OHLCV and crosshair behavior.

- [x] **Step 2: Run final verification**

Run: `node --test tests/frontend/priceChart.test.mjs`
Expected: PASS.

Run: `node --test tests/frontend/*.test.mjs`
Expected: PASS.
