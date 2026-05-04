# FINIQ Graph Viewer Core

Headless graph data, state, validation, filtering, and export utilities for FINIQ graph experiences.

The reusable GUI and websites now live in `../FINIQ-GUI`:

- `../FINIQ-GUI/apps/graph-viewer`
- `../FINIQ-GUI/packages/graph-viewer`
- `../FINIQ-GUI/packages/theme`
- `../FINIQ-GUI/packages/ui`

## Run

```bash
npm install
npm run build
npm run lint
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
cd ../FINIQ-GUI
npm run dev:graph-viewer
```
