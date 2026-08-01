# Documentation Structure

Place modules under `docs/`. Organize modules without submodules using Diátaxis:

```text
docs/
├── README.md
└── {module}/
    ├── README.md
    └── {submodule}/
        ├── tutorials.md
        ├── how-to-guides.md
        ├── reference.md
        └── explanation.md
```

When a module has submodules, keep its `README.md` minimal and use it only to link to them. Apply Diátaxis within each module that has no submodules.

Use `kebab-case` and create only directories that contain documents.

## Diátaxis Classification

Classify each document by the reader's goal:

| Type | Content |
| --- | --- |
| tutorials.md | A guided, end-to-end learning path |
| how-to-guides.md | Steps for a specific goal or problem |
| reference.md | Exact rules, inputs, outputs, and APIs |
| explanation.md | Background, concepts, and design rationale |

Keep these purposes separate. Use `README.md` only as an index when child modules exist, and place each document in the matching Diátaxis file.
