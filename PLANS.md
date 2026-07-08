# Completed Changes

## MarketDesk shared topbar typography

- Purpose: Restore normal letter spacing in the shared MarketDesk topbar brand label after review found an unintended `tracking-wider` class.
- Implementation: Removed `tracking-wider` from the brand label `<p>` class list in `frontend/finiq_GUI/packages/web-app/src/components/layout/Topbar.tsx`.
- Verification: `npm run verify:web-app`, `npm run verify:market-desk`, and `git diff --check` passed.
