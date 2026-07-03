# Review Findings

## 2026-07-03 Market Desk Feature Module Split

Purpose: Split long modules under `src/finiq/market_desk/web/features` into smaller responsibility-focused files without retaining thin compatibility wrappers.

Implementation summary: Moved Market Desk web code into feature packages and split the large download, disclosure HTML, disclosure parse, market data, and storage modules into concrete modules for API payloads, jobs, folder inspection, existing download metadata, HTML cleanup/download/merge/compression, parse preview/change/export/summary, source loading, filtering, insight charts, and integrated provider actions. Updated app, routers, scripts, and tests to import those concrete modules directly.

Verification: `PYTHONPATH=src .venv/bin/python -m compileall -q src/finiq/market_desk/web scripts tests/market_desk` passed. Deleted wrapper import scan found no remaining references to `downloads.kind`, `disclosures.html`, `disclosures.html_parse`, or `market_data.service`. `find src/finiq/market_desk/web/features -type f | xargs wc -l | sort -nr | head` shows the largest feature file is 934 lines. `.venv/bin/python -m pytest tests/market_desk -q` passed with 262 tests and one existing Starlette deprecation warning.
