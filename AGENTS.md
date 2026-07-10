# AGENTS.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## Project-Specific Notes

- Do not read, write, generate, convert, or execute workflows against files under `resources/` without explicit user permission in the current turn. Tests, builds, linters, package commands, and other verification commands are allowed when they do not target or mutate `resources/`.
- Always use `PLANS.md` to record the purpose, implementation summary, and verification result for completed code changes.
- Before adding or changing UI labels, button names, page titles, status text, or feature names, consult `docs/ui-terminology.md`. Reuse existing terms as much as possible; do not invent new button names or near-synonyms. If a new term is genuinely needed, add it to the glossary in the same change and keep UI/tests aligned with it.
- Do not add four meaningless info boxes just to fill space; summary cards must carry decision-making value or be omitted.
- Our goal is to minimize fallback logic to keep the codebase maintainable. Remove any fallback mechanism when eliminating it does not change the resulting behavior or output. Retain fallbacks only when they are necessary to preserve correctness, reliability, or meaningful edge-case handling.

## Doc Routing

To minimize token use, do not read all files under `docs/` by default. Open only
the document that matches the current task:

- UI labels, button names, page titles, status text, or feature names: `docs/ui-terminology.md`.
- Quantiwise Excel, Wide Format, Parquet conversion, preview, merge, duplicate cleanup, account mapping, or date-range metadata: `docs/quantiwise-parquet-conversion.md`.
- KIND disclosure identifiers, `acpt_no`, `doc_no`, `rcept_no`, `mainDoc`, `filtered.json`, `compressed-external-html.json`, or correction families: `docs/kind-disclosure-identifiers.md`.
- Disclosure HTML parser architecture or cross-mode extraction behavior: `docs/disclosure-html-parser-logic.md`.
- Editing KIND HTML parser rules, labels, warnings, correction-table filtering, or parser verification expectations: `docs/disclosure-html-parser-rules.md`.
- KIND HTML parser common parsing behavior or shared metadata connection flow: `src/finiq/market_desk/web/html_parsers/docs/common/common-html-parser-logic-rules.md`.
- KIND HTML parser common table/base record shape, saved record fields, or raw table/row storage policy: `src/finiq/market_desk/web/html_parsers/docs/common/common-html-parser-data-structure.md`.
- KIND HTML parser common warning/status semantics or execution error handling: `src/finiq/market_desk/web/html_parsers/docs/common/common-html-parser-exception-handling.md`.
- Bond issuance parser field extraction, metadata, title extraction, listing market, or fallback decisions: `src/finiq/market_desk/web/html_parsers/docs/bond-issuance-parser-logic-rules.md`.
- Rights issuance parser field extraction or type handling for 유상증자, 무상증자, or 유무상증자: `src/finiq/market_desk/web/html_parsers/docs/rights-issuance-parser-logic-rules.md`.
