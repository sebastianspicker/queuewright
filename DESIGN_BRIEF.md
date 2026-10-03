# Queuewright Studio design brief

Scope: the Queuewright Studio browser client (`studio-ui/`). The Python CLI,
HTTP API and data contracts are out of scope and stay unchanged.

## 1. Product summary

Queuewright validates local JSON descriptions of a Zammad helpdesk
configuration and compiles them into deterministic, symbolic plans. Studio is
the loopback-only browser editor for the same model. It never connects to a
tenant, never reads credentials and never applies anything. Its output is a
set of reviewable artifacts: a Blueprint V2 document, a project bundle, a
profile, a desired-state manifest, an inert plan and a configuration graph
with a SHA-256 identity.

The workflow has eight steps in three phases:

| Phase  | Steps                              | What the user does |
| ------ | ---------------------------------- | ------------------ |
| Frame  | Start, Organization                | Pick or import a project; record operating context without contact data |
| Design | Services, Access, Policies         | Build the unit/service tree; set the role x service ACL matrix; choose capabilities |
| Assure | Governance, Readiness, Review      | Decide delivery and completion per capability; check readiness honestly; validate and export |

**Moment of value:** the Review step, when the local compile succeeds and the
six artifacts become downloadable, with an unambiguous statement of what they
do and do not prove. A secondary moment: the Services tree, when an
institution's real organization is first drawn as a tree that the compiler
accepts.

## 2. Audience

**Primary: the service-desk configuration owner at a public institution.**
Typically the person responsible for a Zammad instance at a university,
research institute or public administration, often in German-speaking Europe.
Role titles: IT service manager, helpdesk platform owner, ITSM lead.

- Expertise: knows Zammad groups, roles, ACLs, triggers and SLAs well; knows
  JSON; is not necessarily a developer. Thinks in organizational units,
  responsibilities and approvals.
- Goals: design a desk structure that mirrors the institution, get it reviewed
  by colleagues (data protection officer, works council, department heads)
  before anything touches production, and keep a traceable record.
- Anxieties: an accidental change to a live tenant; exposing restricted
  departments (HR, examinations, medical) to the wrong agents; personal data
  in test material; a tool that claims more than it did.
- Distrusts: vague "AI-powered" or "seamless" promises, green check marks
  that mean nothing, consumer-style playfulness, tools that hide state.
- Daily tools: Zammad itself, LDAP/AD consoles, spreadsheets for access
  matrices, Word/PDF change requests, ticketing for change management,
  occasionally Git.
- Signals of quality for this person: precise vocabulary, visible provenance
  (revision, hash, schema), explicit limits, dense but calm information,
  something that could be printed and attached to a change request.

**Secondary: the reviewer** (colleague, auditor, data protection officer) who
receives exported artifacts or looks over the owner's shoulder. Needs to see
status and limits at a glance without learning the tool.

**Tertiary: evaluators of the static GitHub Pages demo**, who need to
understand within seconds that every action there is simulated.

## 3. Key journeys

1. **Start from the template.** Start, then University template, then walk
   the steps, then Review, then export. (Primary, used for evaluation.)
2. **Import an existing bundle.** Import JSON (profile + manifest, V1
   project or Blueprint V2); it is validated and migrated; continue editing.
3. **Edit the service tree.** Services: add a unit or service, rename,
   re-parent, reorder by drag, mark sensitive or customer-facing, remove.
4. **Grant access.** Access: set none/read/create/work per role and service.
5. **Decide capabilities.** Policies and Governance: enable features,
   resolve open decisions, accept manual and unsupported boundaries.
6. **Validate and export.** Validate design (always reachable from the top
   bar), then Review: issues, coverage and six downloads.

## 4. Brand character

| Trait | Not tipping into |
| ----- | ---------------- |
| **Exact.** Every number, hash and state is stated precisely. | Pedantic: no wall of caveats where one sentence will do. |
| **Candid.** Says what the result does not prove, at the point it matters. | Alarmist: limits are facts, not warnings in red. |
| **Composed.** Calm, dense, unhurried; a tool for careful work. | Dull or bureaucratic: it should still feel crafted. |
| **Institutional.** Fits a university or public-sector change process. | Corporate gloss or startup swagger. |
| **Drafted, not deployed.** Everything here is a draft for review. | Tentative or unfinished-looking. |

## 5. Market observations

No web research was done for this brief; observations come from working
knowledge of the category (see assumption A6).

- **Helpdesk admin consoles** (Zammad admin, Zendesk Admin Center, Freshdesk
  admin, ServiceNow): left navigation tree, white cards on light grey,
  a single saturated brand color (green or blue), pill badges, toggle-heavy
  forms. Familiar but interchangeable.
- **Infrastructure-as-code review tools** (Terraform/HCP plan views, Pulumi,
  Spacelift, Atlantis comments): dark or purple developer aesthetics,
  monospaced diffs, "plan / apply" vocabulary. Precise, but they speak to
  developers and frame everything as about to be applied.
- **Generic SaaS setup wizards**: numbered stepper, big centered headlines,
  card grids with icons in tinted circles.

**Honor:** a persistent left list of steps (users depend on it), standard
form controls, a real table for the ACL matrix, keyboard-first editing,
monospace for keys and hashes.

**Break:** the blue SaaS palette and pill-chip look; card grids with icon
bubbles; the "apply" framing of IaC tools; scattering the same status
(revision, hash, local-only) across three separate bars.

## 6. Current state

- Stack: React 19, TypeScript, Vite 8, plain CSS in seven files under
  `src/styles/` with OKLCH custom properties in `tokens.css`. `lucide-react`
  icons, `@dnd-kit` for tree reordering. No CSS framework.
- Fonts: tokens name Inter and IBM Plex Mono, but neither is loaded, so the
  app renders in the system font.
- Brand assets: a blue rounded square with "q" and the wordmark "qWright".
  The docs (`docs/STUDIO.md`, "Interface conventions") require "Queuewright"
  and "Queuewright Studio"; the wordmark contradicts its own guide.
- Layout: top bar, provenance strip, step rail, a 74px revision rail,
  canvas, inspector, footer status rail. Revision appears three times, local-
  only status four times, open-decision count twice.

**Keep:** the information architecture (8 steps, 3 phases, inspector for
selection), the honesty copy ("design-ready is not applied"), the editor
seam, keyboard and focus behavior, OKLCH tokens as the idiom.

**Weaknesses:**
- Generic SaaS look: saturated blue primary, tinted icon cards, pills,
  a stock product feel that could belong to any admin tool.
- Redundant chrome: provenance strip + revision rail + status rail repeat
  each other and take about 140px of height and 74px of width.
- Inspector shows filler ("Review this step in the main workspace") on six
  of eight steps.
- Readiness and Review present key numbers as body sentences; the most
  important fact on each screen does not stand out.
- Mobile is a collapsed desktop: horizontally scrolling tabs, wrapped
  chips ("Local design only" on three lines), inspector unreachable.
- Wordmark contradicts the documented product name.

## 7. Constraints

- Preserve every feature, the step ids, the editor seam
  (`src/editor`), API client and persistence modules, and the static-demo
  behavior. No route or contract changes.
- No remote resources: `scripts/verify_repo.py` rejects remote `src`/`href`
  in `index.html`, and the product forbids outbound networking. Fonts must be
  bundled locally.
- No em dash characters in `.md`, `.ts`, `.tsx`, `.html` (repository policy).
- WCAG 2.2 AA, visible focus, `prefers-reduced-motion`, status conveyed by
  text and shape in addition to color (documented convention).
- `bash scripts/verify` must pass; Vitest tests must keep passing.

## 8. Assumptions log

| # | Assumption | Evidence | Confidence |
| - | ---------- | -------- | ---------- |
| A1 | Primary users are institutional (university/public sector) Zammad owners in Europe. | University template, `Europe/Berlin` placeholder, languages en/de/fr/es, works-council-like caution, "privacy-retention" domain. | Medium |
| A2 | Users print or attach artifacts to change requests and value provenance. | Hashes, revisions, "evidence" vocabulary, exports as files, governance step. | Medium |
| A3 | Most use is on desktop/laptop; mobile is for review and small edits. | Dense matrix and tree editing; README targets local dev servers. | High |
| A4 | Renaming the visible wordmark from "qWright" to "Queuewright Studio" is a correction, not a rebrand. | `docs/STUDIO.md` Interface conventions; README; package name `queuewright-studio`. | High |
| A5 | A dark theme is useful but secondary. | Admin tools are used all day; no existing dark mode request. | Low |
| A6 | Category conventions described in section 5 are current. | Working knowledge; not re-verified on the web for this brief. | Medium |
| A7 | Drafting-set conventions (title block, revision delta, "not for construction") are recognizable to this audience. | Public-sector IT staff routinely see building plans and formal document control; the product itself uses "Blueprint", "revision", "graph". | Low to medium; see robustness note in section 9. |

## 9. Design direction

### Direction A: Drawing set

**Concept.** A Studio project is a set of construction drawings for a
helpdesk. Each step is a numbered sheet (Sheet 03 of 08: Services). The
project's identity (revision, graph hash, schema, storage, validation) lives
in one **title block**, the ruled box every technical drawing carries. The
whole product's honesty principle maps onto a drafting convention that
already exists for exactly this purpose: drawings are stamped
**"preliminary, not for construction"** until issued. Here the stamp reads
"Local design. Not applied." Open decisions are marked with the drafting
**revision delta** (a small triangle carrying a count), the way a changed
detail is flagged on a sheet.

Why it fits: the product already speaks this language (Blueprint, revision,
graph, artifacts) and the audience works inside formal document control.
It makes provenance feel native instead of bolted on, and turns three
redundant status bars into one meaningful object.

- **Typography.** Archivo (variable, OFL) carries everything through its
  width axis: condensed widths for sheet numbers, labels and title-block
  captions (like drafting lettering), normal width for reading text. IBM Plex
  Mono (OFL) for keys, hashes and filenames, two weights only. Scale: 11 /
  12 / 13 / 14 / 16 / 20 / 28 / 40 px, with large condensed numerals for sheet
  numbers and key figures.
- **Color.** Paper (warm off-white) and graphite ink do almost all the work.
  Prussian ink (deep, desaturated blue) for interaction and selection: the
  color of drafting film and pen, not of SaaS. Redline (vermilion) only for
  open decisions, blockers and errors, as in markup. Ochre for manual work.
  Verdigris for locally valid. Every color has one role.
- **Layout.** A drawing frame: sheet index on the left, the sheet in the
  middle on a fixed reading measure, a notes column on the right (the
  inspector, which on non-editing steps carries real "sheet notes"), title
  block along the bottom. Hairline rules instead of cards and shadows.
  Square corners (2px radius at most).
- **Motion.** Almost none. Selection and state changes cross-fade in 120 to
  160ms; the inspector sheet slides on mobile. Nothing animates on scroll.
- **Signature details.** The title block with the "Not applied" stamp; the
  revision delta for open decisions; condensed sheet numerals.
- **Departs from category** by replacing cards, pills and brand blue with
  ruled drawing conventions; and by treating status as document metadata
  rather than badges.
- **Refuses:** cyan "blueprint" pastiche (white lines on blue), grid-paper
  backgrounds, fake paper texture, rounded cards, icon bubbles.

### Direction B: Change ledger

**Concept.** The project is a bound register of changes, like a land
registry or accounting ledger. Every step is a ledger section with ruled
columns; totals are struck under double rules; decisions are entries with
a status column.

- Typography: Newsreader (serif, OFL) for headings and figures with old-style
  numerals, Public Sans for UI, Plex Mono for keys.
- Color: cream, iron-gall ink, a single oxblood accent for open entries.
- Layout: full-width tables, strong horizontal rhythm, folio numbers.
- Motion: none beyond focus.
- Signature: double-rule totals; folio-style page numbering.
- Departs from category through serif editorial tone.
- Refuses: icons almost entirely.

Strength: very trustworthy and printable. Weakness: the tree editor and
drag-to-reorder fight a ledger's linear form; a serif-led UI reads as
archival and slow for a tool used all day; risks "bureaucratic" (the
counter-trait to avoid).

### Direction C: Exchange board

**Concept.** Queues as the lines of a telephone exchange: services are
jacks, roles are cords, the ACL matrix is a patch field. A graphite control
panel with lit indicators.

- Typography: Martian Mono for labels, Archivo for text.
- Color: graphite, signal amber and green lamps.
- Layout: dense panel modules with engraved labels.
- Motion: indicator lamps fade on change.
- Signature: patch-field ACL matrix.

Strength: memorable, and the matrix metaphor is apt. Weakness: an exchange
board implies live traffic and a connected system, which directly
contradicts the product's central promise that nothing is connected or
applied. Dark lit panels also drift toward the neon-on-dark cliché.

### Choice

**Direction A, Drawing set.** It is the only direction whose metaphor
reinforces the product's core truth (a design that is explicitly not yet
built) instead of competing with it, and it solves a real usability problem
(three redundant status bars become one title block). B is the safer
runner-up and its printability is partially absorbed into A's title block
and ruled tables. What A trades away: some warmth and immediacy. Drawing
conventions can read as cold, so copy must stay plain and humane, and the
paper tone and Archivo's normal width keep reading text friendly.

**Robustness against A7.** If users do not recognize drafting conventions,
nothing breaks: every signature element also carries plain text ("3 open
decisions", "Local design. Not applied.", "Revision 4"). The metaphor adds
meaning for those who see it and costs nothing for those who do not.
