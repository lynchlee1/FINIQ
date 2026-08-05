# Documentation Structure

Organize documentation under `docs/` using the following roles.

* `guides.md`: Give an at-a-glance overview of what the code does, its main features, and how users interact with it.
* `behavior.md`: Describe the code's default state, normal execution flow, and expected behavior under ordinary conditions.
* `reference.md`: Document only edge cases, limits, exceptional conditions, and behavior outside normal usage.

Apply these rules when classifying content:

1. Put feature summaries and usage entry points in `guides.md`.
2. Put detailed normal behavior in `behavior.md`, even when it depends on common conditions or configuration.
3. Put content in `reference.md` only when it describes an edge case or exceptional condition.
4. Do not use `reference.md` as a general description of conditional behavior.
5. A reader must be able to understand the module's purpose from `guides.md` and its normal operation from `behavior.md` without reading `reference.md`.
6. Do not duplicate information across files.
7. Create `reference.md` only when meaningful edge cases exist.

Use a module's `README.md` only to list and link its direct child modules. Put documentation files only in modules without child modules. Use `kebab-case` and do not create empty files or directories.

```text
docs/
├── README.md
└── {module}/
    ├── README.md
    └── {submodule}/
        ├── guides.md
        ├── behavior.md
        └── reference.md  # optional
```
