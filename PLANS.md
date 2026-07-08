# Completed Changes

## MarketDesk visual QA cleanup

- Purpose: Address visual QA feedback on disclosure workflow screens by reducing inactive gray states, tightening palette usage, aligning right-side hover docks, constraining font sizes, removing emoji markers, and deleting distracting gradients.
- Implementation: Reworked the shared topbar, sidebar, action dock, disclosure download, HTML download, HTML workflow, and graph-viewer surfaces to use app-defined `--tv-*` palette tokens and predefined typography utilities; replaced emoji prefixes with Lucide icons or plain labels; removed hover background fills from inactive controls; aligned action docks to `top-0`; flattened graph-viewer gradient panels.
- Verification: `node --test tests/frontend/navigation.test.mjs` and `npm run build -w @finiq/app-market-desk` passed. Browser checks on `/download` and `/html-content-download` confirmed dock top alignment, no body emoji matches, and no rendered gradient backgrounds.

## MarketDesk TradingView palette lock

- Purpose: Reduce visual noise from mixed slate, cyan, teal, amber, rose, and GitHub-style dark colors by locking MarketDesk to a TradingView-inspired palette.
- Implementation: Added shared `--tv-*` color tokens for background, surfaces, borders, text, primary accent, and market/status colors; wired Tailwind theme colors, the topbar, workflow sidebar, action dock, graph-viewer theme, and chart fallback colors to those tokens.
- Verification: `node --test tests/frontend/navigation.test.mjs` and `npm run build -w @finiq/app-market-desk` passed. Browser checks on `/download` and `/graph/chart` confirmed shared surface, border, text, and accent tokens are applied.

## MarketDesk disclosure sidebar group hierarchy

- Purpose: Make disclosure sidebar groups read as table-of-contents categories instead of weak helper labels.
- Implementation: Kept the existing group labels and restyled `WorkflowSidebar` groups as distinct TOC blocks with bordered sections, stronger headers, and contained step lists.
- Verification: `node --test tests/frontend/navigation.test.mjs` and `npm run build -w @finiq/app-market-desk` passed. Browser check on `/download` confirmed grouped sidebar headers render as distinct TOC sections.

## MarketDesk Ontology type scale tightening

- Purpose: Reduce font-size variation in Ontology screens so labels, empty states, and explanatory copy feel stricter and more professional.
- Implementation: Lowered the Graph View selected-company/empty-state heading from display-like sizing to the shared body/title scale, and aligned Triple Barrier step descriptions with the same `text-sm` body size used by their step labels.
- Verification: `npm run build -w @finiq/app-market-desk` passed.

## MarketDesk font unification

- Purpose: Keep MarketDesk typography professional by using one font family across the app instead of separate sans and mono faces.
- Implementation: Restored Inter as the app font, mapped both Tailwind `font-sans` and `font-mono` tokens to the same Inter-based stack, and removed the graph viewer JSON editor's direct monospace font stack so it follows the shared app font.
- Verification: `npm run build -w @finiq/app-market-desk` passed.

## FINIQ web app component package

- Purpose: Split FINIQ app-level web design components from primitive UI controls so shared shells, navigation, docks, status logs, loading states, and path inputs can live in a dedicated `@finiq/web-app` package.
- Implementation: Added `frontend/finiq_GUI/packages/web-app` with `AppFrame`, `Topbar`, `WorkflowPageShell`, `WorkflowSidebar`, `WorkflowTabs`, `ActionDock`, `JobStatusLogger`, `PageLoadingSpinner`, and a picker-injected `PathPickerInput`; kept MarketDesk-specific navigation/runtime/file-dialog wiring as thin app adapters; updated MarketDesk imports, Tailwind source scanning, Next transpile packages, and npm workspace metadata.
- Verification: `npm run build -w @finiq/app-market-desk` passed; `node --test tests/frontend/actionDock.test.mjs tests/frontend/runtimeInfo.test.mjs tests/frontend/navigation.test.mjs` passed. `node --test tests/frontend/*.mjs` still has 3 unrelated text-snapshot failures in existing HTML parse/filter and ontology frame expectations.
