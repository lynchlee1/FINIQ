# FINIQ Graph Viewer Core

Graph data, state, validation, filtering, export utilities, and reusable Graph Viewer UI for FINIQ graph experiences.

The demo app and shared UI dependencies are in the same `finiq_GUI` workspace. Paths below are relative to this package:

- `../../apps/graph-viewer`
- `../theme`
- `../ui`

## Run

From the repository root, change to `frontend/` before running workspace commands:

```bash
cd frontend
npm install
npm run build -w @finiq/graph-viewer
npm run lint -w @finiq/graph-viewer
```

## Public API

- `src/core/useGraphViewer.ts`: state controller hook and graph actions
- `src/types/graph.ts`: graph schema types
- `src/utils/validation.ts`: JSON parsing and validation
- `src/utils/filtering.ts`: search/filter pipeline
- `src/utils/algorithms.ts`: graph algorithms
- `src/utils/export.ts`: graph export helpers
- `src/utils/stylePresets.ts`: shared style configuration data

## GUI Development

From the same `frontend/` directory, start the visual app with:

```bash
npm run dev:graph-viewer
```
