# Implementation Review Workflow

Use `PLANS.md` as the review queue. Each topic defines an implementation that must be inspected and either retained as an unresolved finding or removed after it is verified.

## 1. Review the Current Changes

1. Read every topic in `PLANS.md` and treat each topic as a separate review item.
2. Do not modify implementation code during this phase. Updating `PLANS.md` is allowed.
3. For each topic, locate the relevant code, tests, documentation, and contracts. Use Git status, diffs, blame, and history only as supporting evidence; do not infer the review scope from commit boundaries.
4. Proactively use subagents when a topic can be reviewed independently or benefits from specialized analysis. Give each subagent a bounded topic and clear file ownership; the primary agent must validate and consolidate the findings.
5. Examine correctness directly. Tests are supporting evidence, not a substitute for checking logic, state transitions, failure paths, races, destructive operations, and missed edge cases.
6. Remove every `PLANS.md` topic whose implementation is free of errors. Keep only topics with unresolved findings.
7. Report findings only. Do not mention error-free areas.

If no errors remain, complete the documentation and plan cleanup in Phase 3, verify the repository, and commit only the changes covered by the reviewed topics. Do not push unless explicitly requested.

## 2. Classify and Resolve Findings

Classify every finding before changing behavior:

- **Intentional:** The behavior is supported by an explicit contract, test, or clear implementation history. Do not change it; briefly cite the evidence.
- **Implementation error:** The behavior conflicts with an explicit contract or produces a reproducibly incorrect result. State the evidence, then fix it and add proportionate regression coverage.
- **Insufficient evidence:** The expected behavior depends on preference, assumption, or ambiguity. Do not change it.

Keep fixes surgical. Do not reimplement intentional or ambiguous behavior, and do not modify unrelated code.

## 3. Synchronize Documentation and Plans

1. Update `docs/` for every functional contract changed or clarified by the fixes.
2. Keep documentation concise and place details in the narrowest relevant document.
3. Recheck `PLANS.md` after implementation and verification. Remove resolved and error-free topics; retain only unresolved errors.
4. Run focused regression tests, the relevant broader suite, required builds or type checks, and `git diff --check`.
5. In the final report, include only classified findings, fixes, documentation changes, remaining `PLANS.md` topics, and verification results.

## Evidence Order

Prefer evidence in this order:

1. Explicit requirements and feature contracts
2. `docs/design/terminology/index.md` and the linked domain terminology contract
3. API, schema, type, and persistence invariants
4. Reproducible runtime behavior
5. Regression tests
6. Git history used only to establish intent or context
