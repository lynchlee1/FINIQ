# FINIQ GUI

Shared GUI workspace for FINIQ web surfaces.

## Structure

- `apps/graph-viewer`: FINIQ Graph Viewer website.
- `apps/consigliere-ai`: ConsigliereAI website shell. During development it proxies `/api` to `http://127.0.0.1:8765`.
- `packages/graph-viewer`: reusable graph viewer library exported from the original GraphViewer source.
- `packages/theme`: shared base and GraphViewer-derived CSS assets.
- `packages/ui`: small reusable React UI building blocks used by FINIQ GUI apps.

## Commands

```sh
npm install
npm run build
npm run dev:graph-viewer
npm run dev:consigliere-ai
```

Run `kind-web` from `ConsigliereAI` before `npm run dev:consigliere-ai` when the ConsigliereAI app needs live data.
