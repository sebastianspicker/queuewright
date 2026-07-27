# Studio interface conventions

The implementation under `studio-ui/src/` is the source of truth for the
Queuewright Studio interface.

## Terminology

- Use `Queuewright` for the repository and product.
- Use `Queuewright Studio` for the browser application.
- The browser header displays `qWright`.
- `ready` means locally valid for review. It does not mean applied or verified
  against a tenant.
- `Validate design` is the primary compile action.

## Visual system

Design tokens are defined in `studio-ui/src/styles/tokens.css`. Layout and
component rules are split across the remaining files in
`studio-ui/src/styles/`.

- Body text uses Inter, Segoe UI Variable, or the system sans-serif.
- Identifiers and hashes use IBM Plex Mono or the system monospace font.
- Status must use text and structure in addition to color.
- Controls must retain visible keyboard focus.
- Motion must respect `prefers-reduced-motion`.

## Layout

The desktop interface contains a project bar, local-status strip, ordered step
navigation, revision rail, editing canvas, inspector, and status rail.

Responsive behavior is defined at 1280, 1020, 760, and 420 pixels. Below 1020
pixels, the revision rail is hidden and the inspector moves into the document
flow. Below 760 pixels, step navigation scrolls horizontally and content uses a
single column. The stylesheet defines a minimum supported width of 320 pixels.

## Source layout

| Path | Purpose |
|---|---|
| `studio-ui/src/shell/` | Navigation, status, revision, and inspector components |
| `studio-ui/src/screens/` | Workflow screens |
| `studio-ui/src/styles/` | Tokens and component styles |
| `studio-ui/src/model/` | Project mutation and access rules |
| `studio-ui/src/studio-state.tsx` | Browser state and compile orchestration |
| `studio-ui/src/storage.ts` | IndexedDB persistence |

## Accessibility status

The source includes visible focus rules, reduced-motion handling, keyboard
controls, responsive layouts, and structured status text. WCAG 2.2 AA is a
target, not a verified conformance claim. A release still requires browser
testing, keyboard review, zoom and clipping checks, and accessibility tooling.
