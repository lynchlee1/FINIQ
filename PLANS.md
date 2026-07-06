# Review Findings

## Disclosure filter JSON preset loading

- Purpose: Change `공시내역 필터링` filter `불러오기` to load filter conditions from a saved result JSON while keeping saved condition presets usable.
- Implementation: Added `/api/disclosures/filter/preset` to read `filters.filter_blocks` from a selected result JSON. Updated the existing `조건검색 프리셋` row so its original `불러오기` button opens a result JSON file picker and applies the saved filters, and made preset selections apply automatically.
- Verification: `node --test tests/frontend/pathLayout.test.mjs`, `PYTHONPATH=src ./.venv/bin/python -m pytest tests/market_desk/test_kind_web_app.py -q -k 'filter_preset or filter_disclosures_stream_writes_transfer_file'`, and `npx tsc --noEmit` passed.

## Disclosure HTML parse filter progress

- Purpose: Keep parse progress and checkpoint behavior consistent between serial and parallel parsing when disclosure filter blocks exclude records.
- Implementation: Removed the serial-only early return so filtered-out records still pass through the common processed-count checkpoint path. Restored `next-env.d.ts` to the stable `.next/types/routes.d.ts` reference instead of the local `.next/dev` artifact path.
- Verification: `PYTHONPATH=src ./.venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -q -k 'parse_disclosure_html_payload_applies_filter_blocks or parse_disclosure_html_payload_counts_serial_filter_exclusions_for_progress or parse_disclosure_html_payload_logs_success_progress_by_interval'` and `npx tsc --noEmit` passed.
