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
- If the user specified a source of truth, you must never rely on any other sources.

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

## 5. Avoid Fallbacks

**Minimize fallback logic to keep the codebase maintainable.**

- Always get the user's permission before creating a new fallback.
- By fallback, it includes all the logic that is used when the normal parsing or conversion path fails or does not return the expected result, as shown below.
  1. Logic that uses a different parser, selector, tag, attribute, or data source.
  2. Logic that looks for the desired HTML element in different places, such as parent, child or adjacent elements, or other DOM paths.
  3. Logic that substitutes another field, metadata, source text or a default value when a specific field is missing or empty.
  4. Logic that handles errors, exceptions, empty results, format mismatches and validation failures in separate branches.
  5. Conditional statements, correction logic or temporary processing are used to get around specific disclosure formats or exceptional HTML structures.

## 6. Other Rules
- Use `PLANS.md` only for completed changes that still require follow-up. Record each item's purpose, implementation summary, verification result, and unresolved finding. Remove items after the follow-up is resolved.
- Keep the current project documentation under `docs/`. When behavior changes, update the owning stage or domain document in the same change. Do not create empty placeholder documents or repeat one contract in multiple files.
- Before adding or changing UI labels, button names, page titles, status text, or feature names, consult the UI terminology section in `docs/design/index.md`. Reuse existing terms as much as possible; do not invent new button names or near-synonyms. If a new term is genuinely needed, add it to that section in the same change and keep UI/tests aligned with it.
