# Market Desk refactor plan

This document records the current refactor direction for the Market Desk app so future page additions follow the same structure.

## Frontend structure

- Route files under `frontend/finiq_GUI/apps/market-desk/src/app` should stay thin. Put feature-specific API calls and DTOs under `src/features/<feature>/`.
- Use `src/api/client.ts` for JSON API requests instead of calling `fetch` directly from shared hooks or new feature APIs.
- Put route, top navigation, and workflow tab metadata in `src/config/navigation.ts`.
- Use `WorkflowPageShell` for pages that follow the standard `WorkflowTabs + page body` layout.
- Put cross-feature response types in `src/types`, and keep feature-only types in the feature folder.

## Backend structure

- Keep `src/finiq/market_desk/web/app.py` focused on app wiring, remaining legacy routes, and job startup while routes are migrated.
- Add new route groups under `src/finiq/market_desk/web/routers/`.
- Register background jobs through `JOB_HANDLERS` instead of adding new `if/elif` branches to `_run_job_worker`.
- Put file discovery helpers in `src/finiq/market_desk/web/discovery.py`; keep `service.py` for business payload builders and compatibility exports.

## Migration order for new work

1. Add feature API/types first.
2. Move repeated layout into shared layout components only when at least two pages use the pattern.
3. Move backend routes one domain at a time.
4. Keep existing import paths compatible unless all callers are updated in the same change.
5. Verify frontend changes with `npm run build` in `frontend/finiq_GUI/apps/market-desk`.
6. Verify backend route/service changes with focused `pytest tests/market_desk/...` runs.
