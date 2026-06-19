# Completed Changes

## Workflow UI Title And Path Consistency

Purpose: Make MarketDesk workflow pages use consistent visible titles and keep path inputs out of page-title cards.

Implementation summary: The workflow sidebar no longer repeats the page title, avoiding duplicated long titles and wrapped labels. HTML workflow pages no longer render a second in-content page-title panel, while mode toggles and notices remain available. Quantiwise and utility path inputs now live under `데이터 경로` cards, input/output path labels consistently include `데이터 경로`, and action cards use `작업 실행` without mixed English eyebrows such as `Run`.

Verification:
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Loop 1 browser check on `/utility/assets-excel`, `/table`, `/filter`, `/html-parse`, and `/` confirmed no sidebar `h2` title and path labels with `데이터 경로`.
- Loop 2 browser check on `/html-download`, `/html-section-split`, `/html-parse`, `/html-change-log`, `/html-bond-summary`, and `/utility/assets-excel/merge` confirmed no sidebar `h2` title and no checked path labels missing `데이터 경로`.
