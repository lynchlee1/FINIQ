# FINIQ Web App Design Principles

This package provides FINIQ app-level web components for financial workflows. It should reduce visual freedom, not expand it. A constrained system makes dense financial screens easier to scan, compare, and operate repeatedly.

## Core Direction

- Prefer Notion-like restraint: quiet surfaces, predictable spacing, limited type scale, and reusable blocks.
- Optimize for visibility under data density. The user should find status, controls, warnings, and primary records without decorative competition.
- Keep design decisions centralized in `@finiq/web-app` and primitive controls in `@finiq/ui`.
- Do not add one-off visual treatments in feature pages when a package component can carry the pattern.
- Do not add summary cards, badges, or boxes unless they help a user decide or act.

## Type Scale

Use a small, fixed set of text roles.

| Role | Tailwind Pattern | Use |
| --- | --- | --- |
| App title | `text-2xl font-bold` | Current page title in the app shell only. |
| Section title | `text-base font-semibold` | Card and panel titles. |
| Body | `text-sm` or `text-body` | Labels, table-adjacent copy, status text. |
| Helper | `text-xs` | Secondary metadata and compact hints. |
| Numeric/table microcopy | `text-[11px]` | Dense table cells or parsed-value indexes only. |

Avoid new arbitrary font sizes. If a screen needs another size, first ask whether the information hierarchy is doing too much.

## Component Types

Use the smallest component that matches the job.

| Component | Purpose |
| --- | --- |
| `AppFrame` | Page width, top spacing, and global shell containment. |
| `Topbar` | Brand, current page title, top navigation, and theme toggle. |
| `WorkflowPageShell` | Main page grid with optional workflow sidebar. |
| `WorkflowSidebar` | Left navigation for multi-step workflows. |
| `WorkflowTabs` | Horizontal step navigation when a page needs tabs. |
| `ActionDock` | Activity, notification, and settings panels for repeated workflow controls. |
| `JobStatusLogger` | Long-running job output and cancellation affordance. |
| `PageLoadingSpinner` | Full-page or major-region loading state. |
| `PathPickerInput` | File/folder/save path input with an injected picker implementation. |

`@finiq/ui` owns primitive controls such as `Button`, `Card`, `Input`, `Select`, `Tabs`, and `Checkbox`. `@finiq/web-app` owns FINIQ workflow composition. Domain-specific cards stay inside the consuming app until at least two workflows need the same behavior.

## Layout Rules

- Prefer full-width vertical workflow sections over decorative multi-card dashboards.
- Keep sidebars, docks, and repeated panels dimensionally stable.
- Use cards for concrete tools, repeated records, and panels. Do not nest cards inside cards.
- Keep financial controls close to the data or status they affect.
- Use icons for common actions when the meaning is familiar; use text when the action is domain-specific.

## Color And State

- Use shared `--tv-*` tokens for app surfaces, borders, text, accent, warning, up, and down states.
- Reserve accent color for navigation selection, primary action, and active state.
- Reserve warning color for user attention, parse warnings, and notification activity.
- Avoid local color inventions in feature pages.

## Review Checklist

Before adding or changing a component in this package:

- Does it reduce duplicated app-level UI behavior?
- Does it avoid introducing a new font size, radius, color, or spacing rhythm?
- Can the component be configured with data/children instead of importing app-specific stores or navigation?
- Is the resulting screen easier to scan under real financial data density?
- Would the same pattern still feel correct after hours of repeated workflow use?
