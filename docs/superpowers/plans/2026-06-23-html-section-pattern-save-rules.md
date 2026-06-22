# HTML Section Pattern Save Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users choose which TOC sections to save per 목차 조합 while still processing every HTML file.

**Architecture:** Extend the existing section pattern summary with per-pattern `sections`, then pass a compact `section_save_rules` map into the existing save job. The save job computes each document's signature and filters sections only when a rule exists for that signature.

**Tech Stack:** Python FastAPI service helpers, React/Next client components, pytest, TypeScript.

## Global Constraints

- Use existing UI terms from `docs/ui-terminology.md`.
- Keep output folders in the existing `결과 데이터 경로/toc_id/source-relative-path.html` structure.
- Do not change unrelated parsing, review, or download workflows.
- Use TDD for behavior changes.

---

### Task 1: Backend Pattern Metadata and Save Filtering

**Files:**
- Modify: `src/finiq/market_desk/web/disclosure_html_sections.py`
- Test: `tests/market_desk/test_kind_web_service.py`

**Interfaces:**
- Consumes: existing `_section_signature(sections: list[dict[str, Any]]) -> str`.
- Produces: pattern items with `sections: list[dict[str, str | int]]`.
- Produces: save payload support for `section_save_rules: dict[str, list[str]]`.

- [ ] **Step 1: Write failing tests**

Add tests proving pattern items include `sections` and save rules filter sections by signature.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest tests/market_desk/test_kind_web_service.py::test_summarize_disclosure_html_section_kinds_payload_counts_unique_toc_sequences tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_filters_toc_sections_by_pattern_rule -q`

Expected: new assertions fail because `sections` and filtering are not implemented.

- [ ] **Step 3: Implement minimal backend changes**

Update `_section_patterns` to store sections for each signature and update `save_disclosure_html_sections_payload` to apply `section_save_rules`.

- [ ] **Step 4: Run focused tests and verify pass**

Run: `pytest tests/market_desk/test_kind_web_service.py::test_summarize_disclosure_html_section_kinds_payload_counts_unique_toc_sequences tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_filters_toc_sections_by_pattern_rule -q`

Expected: PASS.

### Task 2: API Route Coverage

**Files:**
- Test: `tests/market_desk/test_kind_web_app.py`

**Interfaces:**
- Consumes: `/api/disclosures/html/sections/save/start`.
- Produces: route behavior that accepts `section_save_rules`.

- [ ] **Step 1: Write failing route test**

Add a route test that starts a save job with `section_save_rules` and verifies only selected toc folders are written.

- [ ] **Step 2: Run route test**

Run: `pytest tests/market_desk/test_kind_web_app.py::test_html_section_save_start_route_applies_pattern_toc_selection -q`

Expected: PASS after Task 1 because the route forwards payloads unchanged.

### Task 3: Frontend Rule Selection UI

**Files:**
- Modify: `frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx`
- Modify: `frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx`
- Test: `tests/market_desk/test_kind_web_service.py`

**Interfaces:**
- Consumes: `SectionPattern.sections`.
- Produces: `section_save_rules` in save payload.

- [ ] **Step 1: Add static UI assertions**

Update existing UI source assertions for `section_save_rules`, selected toc checkbox handlers, and Korean labels reused from current terminology.

- [ ] **Step 2: Run static UI test and verify failure**

Run: `pytest tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui -q`

Expected: FAIL until UI code contains the new state and payload fields.

- [ ] **Step 3: Implement UI state and checkboxes**

Track selected toc ids by signature, default each loaded pattern to all sections selected, render checkboxes in `목차 조합 모아보기`, and include `section_save_rules` in `startSave`.

- [ ] **Step 4: Run static UI test and focused backend tests**

Run: `pytest tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui tests/market_desk/test_kind_web_service.py::test_summarize_disclosure_html_section_kinds_payload_counts_unique_toc_sequences tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_filters_toc_sections_by_pattern_rule -q`

Expected: PASS.

### Task 4: Project Notes and Verification

**Files:**
- Modify: `PLANS.md`

**Interfaces:**
- Consumes: completed implementation and test output.
- Produces: project-required implementation summary and verification result.

- [ ] **Step 1: Update `PLANS.md`**

Record purpose, implementation summary, and verification command results for the completed code change.

- [ ] **Step 2: Run final focused verification**

Run: `pytest tests/market_desk/test_kind_web_service.py::test_summarize_disclosure_html_section_kinds_payload_counts_unique_toc_sequences tests/market_desk/test_kind_web_service.py::test_save_disclosure_html_sections_payload_filters_toc_sections_by_pattern_rule tests/market_desk/test_kind_web_app.py::test_html_section_save_start_route_applies_pattern_toc_selection -q`

Expected: PASS.
