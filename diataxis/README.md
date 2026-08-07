# Documentation Structure

Every leaf module under `docs/` uses exactly two documents.

* `features.md`: Give every feature one authoritative section containing its normal behavior, defaults, conditions, failures, recovery, limits, service behavior, UI behavior, and user decisions.
* `reference.md`: Organize static file and stored-artifact contracts by exact path, including each artifact's I/O role, structure, fields, allowed values, defaults, and structural exceptions.

## Ownership rules

1. Give every feature its own `###` section in `features.md`. Do not split one feature across multiple documents.
2. Put the feature's normal operation under `#### Behavior`.
3. Put the same feature's defaults, conditional behavior, failures, recovery, limits, service behavior, UI behavior, and user decisions under `#### Defaults and Exceptions` when needed.
4. Give every input or output file and stored artifact its own `###` section in `reference.md` using its exact path.
5. Put an artifact's role, structure, format, and fields under `#### I/O Structure`. Put only allowed default values and structural exceptions under `#### Defaults and Exceptions` when needed.
6. Keep runtime outcomes and recovery behavior in `features.md`; do not put them in `reference.md` as file exceptions.
7. Give every fact one authoritative home. `features.md` may name an artifact but must not repeat its file structure, and `reference.md` must not repeat feature behavior.
8. Use English for all Markdown headings. Explanatory body text may remain Korean.
9. Avoid links between leaf documents. Keep each fact in the file that owns it instead of using links to compensate for unclear classification.
10. In disclosure References, copy every folder name, filename, and placeholder exactly from `docs/disclosures/reference.md`. Do not replace path segments with Korean or English feature names.

## Internal structure

`features.md`:

```text
# {Module} Features

## Purpose

{Module purpose.}

## Features

### {Feature}

#### Behavior

{Normal behavior.}

#### Defaults and Exceptions  # only when the feature has them

- {Default, condition, failure, recovery, or limit.}
```

`reference.md`:

```text
# {Module} Reference

## Paths

- `<data_root>/<exact-input-folder-a>/<input-artifact-a>` + `<data_root>/<exact-input-folder-b>/<input-artifact-b>` → `<data_root>/<exact-output-folder-a>/<output-artifact-a>` + `<data_root>/<exact-output-folder-b>/<output-artifact-b>`

### `<exact-input-folder-a>/<input-artifact-a>`

#### I/O Structure

- `{input-role-and-brief-purpose}`
- `{format-and-fields}`

#### Defaults and Exceptions  # only when the artifact has them

- `{accepted-default-or-exception-value}`

### `<exact-input-folder-b>/<input-artifact-b>`

#### I/O Structure

- `{input-role-and-brief-purpose}`
- `{format-and-fields}`

### `<exact-output-folder-a>/<output-artifact-a>`

#### I/O Structure

- `{output-role-and-brief-purpose}`
- `{format-and-fields}`

#### Defaults and Exceptions  # only when the artifact has them

- `{accepted-default-or-exception-value}`

### `<exact-output-folder-b>/<output-artifact-b>`

#### I/O Structure

- `{output-role-and-brief-purpose}`
- `{format-and-fields}`
```

```text
docs/
├── features.md
├── reference.md
└── {module}/
    ├── features.md
    ├── reference.md
    └── {submodule}/
        ├── features.md
        └── reference.md
```
