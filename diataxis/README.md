# Documentation Structure

Organize each leaf module under `docs/` by the kind of statement being made.

* `guides.md`: List every major capability and describe its normal input-to-result flow. Include exact input or output names when they are essential to recognizing the capability.
* `cases.md`: Describe behavior that is triggered by a condition, including supported variations, edge cases, recovery, limits, and stop conditions.
* `reference.md`: Record static lookup facts such as paths, data shapes, fields, states, allowed values, and constants. Do not narrate flows or conditional outcomes.

## Ownership rules

1. Give every major capability its own section in `guides.md`. A reader must be able to discover what the module does without reading the other files.
2. Put a normal input-to-result flow such as “read A and create B” in `guides.md`.
3. Put a runtime, service, UI, or user-decision outcome that depends on “if”, “when”, or “unless” in `cases.md`.
4. Put exact paths, formats, accepted input constraints, defaults, output-integrity invariants, and the metadata or stored-state contract needed for reuse and recovery in `reference.md`.
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

- `<data_root>/<exact-input-folder-a>/<input-artifact-a>` + `<data_root>/<exact-input-folder-b>/<input-artifact-b>` → `<data_root>/<exact-output-folder-a>/<output-artifact-a>` + `<data_root>/<exact-output-folder-b>/<output-artifact-b>`

## Input formats

### `<input-artifact-a>`

- `{brief-purpose}`
- `{format-and-fields}`

### `<input-artifact-b>`

- `{brief-purpose}`
- `{format-and-fields}`

## Output formats

### `<output-artifact-a>`

- `{brief-purpose}`
- `{format-and-fields}`

### `<output-artifact-b>`

- `{brief-purpose}`
- `{format-and-fields}`

## Input constraints and defaults

### `{constraint-or-default-group}`

- `{accepted-values-and-required-metadata}`
- `{default-values}`

## Output integrity

### `{integrity-group}`

- `{invariant}`
- `{publication-contract}`

## Reuse and recovery

### `{stored-state-group}`

- `{reuse-requirement}`
- `{recovery-state-contract}`

## States and values
```

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
