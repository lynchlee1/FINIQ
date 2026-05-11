# FINIQ Graph Viewer Core

Graph data, state, validation, filtering, export utilities, and reusable Graph Viewer UI for FINIQ graph experiences.

The visual app lives in the root FINIQ workspace:

- `../finiq_GUI/apps/graph-viewer`
- `../finiq_GUI/packages/theme`
- `../finiq_GUI/packages/ui`

## Run

```bash
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

Use the new GUI workspace for the visual app:

```bash
npm run dev:graph-viewer
```
