# FINIQ MarketDesk Design System

## 1. Atmosphere & Identity

FINIQ MarketDesk is a quiet analyst cockpit: dense, exact, and calm under noisy market data. The signature is a slate terminal surface with restrained blue focus states and tabular numeric rhythm, so disclosure events, price data, and model labels feel auditable rather than decorative.

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
| --- | --- | --- | --- | --- |
| Surface/primary | `--background` | `#f8fafc` | `#0d1117` | Main app background |
| Surface/card | `--color-card` | `#ffffff` | `#161b22` | Cards, analysis panels |
| Surface/muted | `--color-muted` | `#f1f5f9` | `#21262d` | Subtle metric blocks, table headers |
| Surface/input | `--surface-input` | `#ffffff` | `#0d1117` | Inputs, selects, table body |
| Text/primary | `--foreground` | `#0f172a` | `#f0f6fc` | Primary copy |
| Text/secondary | `--color-muted-foreground` | `#64748b` | `#8b949e` | Captions, help text |
| Border/default | `--color-border` | `#e2e8f0` | `#30363d` | Dividers and panel outlines |
| Accent/primary | `--color-primary` | `#0f172a` | `#2f81f7` | Primary actions and focus |
| Status/success | `--status-success` | `#15803d` | `#3fb950` | Completed rows, positive labels |
| Status/warning | `--status-warning` | `#b45309` | `#d29922` | Reused or partial runs |
| Status/error | `--color-destructive` | `#dc2626` | `#ef4444` | Failed rows, API errors |

### Rules

- Blue is reserved for active controls, focus, and primary execution. Do not use it as ambient decoration.
- Tables and metrics use tonal shift first, borders second, and shadows never.
- Raw hex values should stay in `globals.css` tokens or legacy compatibility classes; new UI should prefer token-backed Tailwind colors already used in the app.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Tracking | Usage |
| --- | --- | --- | --- | --- | --- |
| H1 | 24px | 650 | 1.25 | 0 | Workflow page titles |
| H2 | 18px | 650 | 1.35 | 0 | Panel titles |
| H3 | 15px | 600 | 1.4 | 0 | Section titles |
| Body | 14px | 400 | 1.55 | 0 | Standard controls and rows |
| Body/sm | 13px | 400 | 1.45 | 0 | Secondary explanations |
| Caption | 12px | 500 | 1.35 | 0.02em | Labels and metadata |
| Numeric | 13px | 500 | 1.4 | 0 | Tabular financial values |

### Font Stack

- Primary: IBM Plex Sans KR, Inter fallback, system UI.
- Mono: Space Grotesk, SFMono-Regular, monospace.

### Rules

- Financial values use tabular numerals.
- Korean workflow labels stay concise and reuse `docs/ui-terminology.md`.
- Avoid oversized hero typography; MarketDesk is an operational platform, not a marketing page.

## 4. Spacing & Layout

### Base Unit

All spacing derives from a base of 4px.

| Token | Value | Usage |
| --- | --- | --- |
| `--space-1` | 4px | Icon-to-label, tight table cells |
| `--space-2` | 8px | Inline controls, compact gaps |
| `--space-3` | 12px | Form field groups |
| `--space-4` | 16px | Card inner spacing |
| `--space-5` | 20px | Panel group spacing |
| `--space-6` | 24px | Major card padding |
| `--space-8` | 32px | Section breaks |

### Grid

- Max content width: 1280px via the existing app shell.
- Operational pages use stacked full-width bands first; two-column layouts are reserved for controls next to live result panels.
- Tables may overflow horizontally inside a contained scroll region, never the page.

### Rules

- Use compact controls for analyst workflows; avoid empty cards that do not change decisions.
- Summary cards must show decision-making values such as total, completed, failed, created, reused, or active parameter hash.

## 5. Components

### Analysis Panel

- **Structure**: card header with title and concise context, then controls or data.
- **Variants**: execution setup, result review, event selection.
- **Spacing**: `--space-4` inner groups, `--space-5` between major groups.
- **States**: loading skeleton/spinner, empty copy, inline error copy.
- **Accessibility**: labels on every input/select; buttons disable while running.
- **Motion**: no layout motion; hover/focus only.

### Segmented Mode Control

- **Structure**: two or three buttons in a bordered row.
- **Variants**: active tonal fill, inactive transparent.
- **Spacing**: `--space-1` button gap, `--space-2` horizontal padding.
- **States**: hover, active, focus visible.
- **Accessibility**: use `aria-pressed` for active mode.
- **Motion**: 150ms color transition.

### Result Table

- **Structure**: sticky mental model of header, horizontal scroll container, compact rows.
- **Variants**: stored results, selected event list.
- **Spacing**: `--space-2` vertical cell padding, `--space-3` horizontal cell padding.
- **States**: empty, failed-row status, completed-row status.
- **Accessibility**: semantic table, visible status text, no color-only meaning.
- **Motion**: none.

## 6. Motion & Interaction

| Type | Duration | Easing | Usage |
| --- | --- | --- | --- |
| Micro | 120ms | ease-out | Button hover and active state |
| Standard | 200ms | ease-in-out | Mode switch color changes |

### Rules

- Only animate `transform` and `opacity` for any future motion.
- Focus rings are required for inputs, selects, and mode buttons.
- Loading states must preserve layout height to avoid result table jumps.

## 7. Depth & Surface

### Strategy

Borders plus tonal shift.

| Type | Value | Usage |
| --- | --- | --- |
| Default border | `1px solid var(--color-border)` | Cards, tables, mode controls |
| Subtle surface | `var(--color-muted)` | Table headers, summary blocks |
| Input surface | `var(--surface-input)` | Selects and text inputs |

### Rules

- Do not add decorative shadows to analyst panels.
- Dark mode uses the established GitHub-like slate palette from `globals.css`.
- Separate dense data with dividers and background tone, not nested cards.
