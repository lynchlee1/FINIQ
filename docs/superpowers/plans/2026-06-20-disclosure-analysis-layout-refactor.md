# Disclosure Analysis Layout Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `공시 분석` less cramped by grouping controls into clear execution workflow sections while preserving existing Triple Barrier behavior.

**Architecture:** Keep the current `DisclosureAnalysisWorkspace` state and API calls unchanged. Refactor only the JSX layout so execution target, disclosure scope, Triple Barrier parameters, and saved results read as separate workflow areas.

**Tech Stack:** Next.js 16 canary, React 19, TypeScript, Tailwind v4, `@finiq/ui`, Node test runner.

## Global Constraints

- Reuse terms from `docs/ui-terminology.md`; do not invent near-synonym button names.
- Follow `DESIGN.md`: operational page, slate/card surfaces, token-backed Tailwind classes, borders plus tonal shift, no decorative shadows.
- Keep changes surgical to `공시 분석`, its regression test, and `PLANS.md`.
- Preserve existing API endpoints and state behavior.

---

### Task 1: Workflow Section Regression

**Files:**
- Modify: `tests/frontend/ontologyGraphWorkspace.test.mjs`

**Interfaces:**
- Consumes: `analysisWorkspacePath`
- Produces: A source-level regression that requires section labels in this order: `1. 실행 대상`, `2. 공시 범위`, `3. Triple Barrier 설정`, `저장 결과 요약`, `결과 테이블`.

- [ ] **Step 1: Write the failing test**

```javascript
test("disclosure analysis groups execution controls by workflow", async () => {
  const source = await readFile(analysisWorkspacePath, "utf8");
  const executionTargetStart = source.indexOf("1. 실행 대상");
  const disclosureScopeStart = source.indexOf("2. 공시 범위");
  const parameterStart = source.indexOf("3. Triple Barrier 설정");
  const summaryStart = source.indexOf("저장 결과 요약");
  const tableStart = source.indexOf("결과 테이블");

  assert.ok(executionTargetStart > -1);
  assert.ok(disclosureScopeStart > executionTargetStart);
  assert.ok(parameterStart > disclosureScopeStart);
  assert.ok(summaryStart > parameterStart);
  assert.ok(tableStart > summaryStart);
  assert.match(source, /검사 대상 이벤트/);
  assert.match(source, /Triple Barrier 실행/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/frontend/ontologyGraphWorkspace.test.mjs`

Expected: FAIL because `1. 실행 대상` does not exist yet.

### Task 2: Layout Refactor

**Files:**
- Modify: `frontend/finiq_GUI/apps/market-desk/src/app/graph/analysis/DisclosureAnalysisWorkspace.tsx`

**Interfaces:**
- Consumes: existing component state and handlers.
- Produces: the same page behavior with clearer workflow grouping.

- [ ] **Step 1: Implement minimal JSX changes**

Group execution controls into numbered sections:
- `1. 실행 대상`: execution stock search/select.
- `2. 공시 범위`: disclosure group chips and selectable event list.
- `3. Triple Barrier 설정`: event basis, price basis, barriers, and execute button.
- `저장 결과 요약` and `결과 테이블`: preserved below workflow controls.

- [ ] **Step 2: Run test to verify it passes**

Run: `node --test tests/frontend/ontologyGraphWorkspace.test.mjs`

Expected: PASS.

### Task 3: Verification and Completion Record

**Files:**
- Modify: `PLANS.md`

**Interfaces:**
- Consumes: successful test/build/browser verification.
- Produces: completed-change record for this UI refactor.

- [ ] **Step 1: Run verification**

Run:
```bash
node --test tests/frontend/ontologyGraphWorkspace.test.mjs
npm --prefix frontend/finiq_GUI/apps/market-desk run build
```

- [ ] **Step 2: Browser QA**

Open `/graph/analysis` in the market-desk app and verify desktop/mobile layout does not overflow, mode toggle works, and workflow sections are visible.

- [ ] **Step 3: Update `PLANS.md`**

Add a completed section with purpose, implementation summary, and verification results.
