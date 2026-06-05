# FINIQ GUI

Shared GUI workspace for FINIQ web surfaces.

## Structure

- `apps/graph-viewer`: FINIQ Graph Viewer website.
- `apps/market-desk`: FINIQ MarketDesk website shell. During development it proxies `/api` to `http://127.0.0.1:8765`.
- `packages/graph-viewer`: reusable graph viewer library exported from the original GraphViewer source.
- `packages/theme`: shared base and GraphViewer-derived CSS assets.
- `packages/ui`: small reusable React UI building blocks used by FINIQ GUI apps.

## Commands

```sh
npm install
npm run build
npm run dev:graph-viewer
npm run dev:market-desk
```

Run `kind-web` from `FINIQ-MarketDesk` before `npm run dev:market-desk` when the FINIQ MarketDesk app needs live data.
