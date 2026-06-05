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

## 5. Git Hygiene

**Do not leave the user guessing what changed.**

Before ending a coding task:
- Run `git status --short` from the repository root.
- State exactly which files changed and whether they are staged.
- If the user asked for a commit, stage only the files directly related to the request, commit them, and report the commit hash.
- If the user did not ask for a commit, do not stage or commit silently. Tell the user the exact `git add`/`git commit` commands to run, or ask whether to commit when that is the obvious next step.
- Never discard or restore changes unless the user explicitly asks for that.

## 6. KIND Bond Issuance Parsing

**Preserve legacy output fields while accepting issuer-specific table labels.**

- `finiq_marketDesk`의 사채 발행 파서는 전환사채와 신주인수권부사채를 같은 `bond_issuance` 레코드로 내보낸다.
- 출력 필드는 기존 호환성을 위해 `전환시작일`/`전환종료일`을 유지한다.
- 전환사채는 `전환청구기간` + `시작일`/`종료일` 행에서 값을 가져온다.
- 신주인수권부사채는 같은 출력 필드에 `권리행사기간` + `시작일`/`종료일` 행을 매핑해야 한다. `resources/kind_kosdaq/kind_html/20080825000412.html`, `20080826000146.html`, `20080826000267.html`이 이 케이스다.
- 신주인수권부사채의 `행사가액`, `행사대상`, `납입방법`은 각각 `행사가액 (원/주)`, `인수권행사에 따라 발행할 주식의 종류`, `신주대금 납입방법` 행에서 가져온다.
- 신주인수권부사채 여부는 본문 전체 키워드가 아니라 `사채의 종류` 행에 `신주인수권`이 있는지로 판단한다. 전환사채의 조정 설명문에 신주인수권부사채가 언급될 수 있다.
- 신주인수권부사채의 만기상환률 `100%+` 값은 `할증률(%)`로 파싱하지 않는다.
- 리픽싱은 `행사가액 조정` 문맥 안의 `최저조정가액비율 : N%`, `조정한도 ... N%이상`, `행사가액에 N%를 한도`처럼 최저 조정 한도를 나타내는 표현에서만 가져온다. 만기상환률, 조기상환률, 청약증거금 `100%` 같은 주변 숫자를 리픽싱으로 쓰지 않는다.
- `rowspan`/`colspan` 확장 후 같은 행에 보이는 라벨 조합을 기준으로 찾고, 임의의 본문 정규식으로 날짜를 뽑지 않는다.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
