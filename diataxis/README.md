# Documentation Structure

Organize each leaf module under `docs/` by the kind of statement being made.

* `guides.md`: List every major capability and describe its normal input-to-result flow. Include exact input or output names when they are essential to recognizing the capability.
* `cases.md`: Describe behavior that is triggered by a condition, including supported variations, edge cases, recovery, limits, and stop conditions.
* `reference.md`: Record static lookup facts such as paths, data shapes, fields, states, allowed values, and constants. Do not narrate flows or conditional outcomes.

## Ownership rules

1. Give every major capability its own section in `guides.md`. A reader must be able to discover what the module does without reading the other files.
2. Put a normal input-to-result flow such as “read A and create B” in `guides.md`.
3. Put a statement whose outcome depends on “if”, “when”, “unless” in `cases.md`.
4. Put a fact that answers “what is the exact name, value, path, or shape?” in `reference.md`, unless that fact is essential to identifying a Guide's input or result.
5. A topic may be named in more than one file, but each condition, outcome, value, and rule must have exactly one authoritative home. `guides.md` may summarize a capability but must not repeat its Case details.
6. Avoid links between leaf documents. Keep each fact in the file that owns it instead of using links to compensate for unclear classification.

## Internal structure

`guides.md`:

```text
# {Module}
## Purpose
## Capabilities
### {Capability}
{One or two sentences describing the normal input-to-result flow.}
## Usage  # only when users perform a task directly
```

`cases.md`:

```text
# {Module} Cases
## When {condition}
{The resulting behavior.}
```

`reference.md`:

```text
# {Module} Reference
## Paths
## Data formats
## States and values
```

Use only the headings that have content.

Use `kebab-case` and do not create empty files or directories.

```text
docs/
├── guides.md
├── cases.md
├── reference.md
└── {module}/
    ├── guides.md
    ├── cases.md
    ├── reference.md
    └── {submodule}/
        ├── guides.md
        ├── cases.md
        └── reference.md
```
