# Completed Changes

## Workflow UI Title And Path Consistency

Purpose: Make MarketDesk workflow pages use consistent visible titles and keep path inputs out of page-title cards.

Implementation summary: The workflow sidebar no longer repeats the page title, avoiding duplicated long titles and wrapped labels. HTML workflow pages no longer render a second in-content page-title panel, while mode toggles and notices remain available. Quantiwise and utility path inputs now live under `데이터 경로` cards, input/output path labels consistently include `데이터 경로`, and action cards use `작업 실행` without mixed English eyebrows such as `Run`.

Verification:
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Local browser check on `/table`, `/utility`, `/utility/assets-excel`, `/html-download`, and `/html-parse` confirmed top/sidebar title alignment and no remaining `Run` eyebrow in the checked content.
