# Nodus UI — design audit, information architecture and design system

Status: proposal, no code changed. Screenshots of the current UI are in `docs/ui-audit/` (dark mode, 1440 px, token set unless noted). This document is the contract for the redesign; the implementation is critiqued against §4 and §5 after each screen is built.

Aesthetic direction: calm, information-dense, professional. Reference points are Linear (navigation, density, keyboard-first) and the Stripe Dashboard (tables, inspector panels, neutral palette with one accent). No gradients, no illustrations, no decorative colour.

---

## 1. Audit of the current UI

Screens audited: Overview, entity drawer, evidence panel (source, path, timeline), pending drawer, action view, Ask (empty, streaming, answer, impact, dispute, action cards, learn-fact refusal), Graph, anonymous mode. Light mode and widths under 1100 px were audited from the CSS (the window resize did not take effect in the harness).

### 1.1 Shell, navigation, top bar

| # | Problem | Evidence |
|---|---|---|
| S1 | The top bar carries six unrelated controls on one line: As-of date, Acting-as select, an italic disclaimer, a team tag, Pending, and a password field for the token. There is no grouping, no hierarchy, and it wraps on narrow widths. | `01-overview-top.jpg`, `Shell.tsx:387-444` |
| S2 | Acting-as options stuff role text into the `<option>` label (`Priya Raman · leads Payments · decider of ADR-007, …`), which truncates in the native select. The role is the most important thing for the authorisation demo and it is the first thing cut off. | `01-overview-top.jpg` |
| S3 | The As-of input shows `dd/mm/yyyy` when empty. Nothing says that empty means today, and once set there is no persistent indicator on the page that you are viewing the past. A Graph slider drag silently changes it for every page. | `Shell.tsx:393-405`, `graph/page.tsx:448` |
| S4 | The token field is permanently visible as a password input labelled "judges' token". Credentials do not belong in a primary toolbar. "token set" / "clear" is a tag plus a button with no affordance difference. | `17-overview-anonymous.jpg` |
| S5 | The anonymous banner is a full-width amber band with two sentences of copy on every page. At the same time Pending still shows a count and Acting-as is still selectable, which contradicts "actions are off". | `17-overview-anonymous.jpg`, `18-ask-anonymous.jpg` |
| S6 | Rail icons are Unicode glyphs (`◫ ? ⬡`) that render differently per platform; the brand wraps to two lines in a 76 px rail; there is no collapse, no keyboard shortcut, no tooltip. | `Shell.tsx:331-335` |
| S7 | No page header pattern. Overview has an `h1`, Ask has a card title inside the log, Graph has no title at all. No page has a description, meta or actions row. | `09-ask-empty.jpg`, `16-graph.jpg` |
| S8 | Overlays stack as independent fixed drawers with cumulative right offsets (`.drawer`, `.l2` at 24 px, `.l3` at 48 px) plus a modal at z-60. Opening a citation from the entity drawer opens a third drawer that covers it, leaving two `×` buttons 48 px apart. No focus trap, no `role="dialog"`, no Escape handling, no scroll lock, no focus return. | `05-evidence-source-stacked-drawers.jpg`, `globals.css:185-196` |
| S9 | No global search. The only ways to reach an entity are a link on Overview, a node on the Graph, or asking. | all screens |
| S10 | Session state (acting person, as-of, token) is partly in localStorage, partly in a per-page-load session, and nothing in the UI says a reload creates a new session. | `store.tsx:541-559` |

### 1.2 Visual hierarchy, density, consistency

| # | Problem | Evidence |
|---|---|---|
| V1 | Everything clickable is accent blue. On Overview the team name, lead, every member and every owned system are the same blue link, so the page is a wall of links with no hierarchy. | `01-overview-top.jpg` |
| V2 | One hue carries several meanings. Green = citation label "graph", status "current", "confirmed", eligibility "holder". Red = "disputed", danger button, error text, "changed since". Purple = "proposed" and every action chip. Amber = "stale", "fallback", text-only citations and the anon banner. In an answer line `current` (green outline) sits next to `❝ session` (green fill) meaning two different things. | `10-ask-answer-owner.jpg`, `globals.css:141-159` |
| V3 | Status vocabulary is inconsistent and leaks implementation: `current, historical, disputed, overruled, proposed, confirmed, withdrawn, retracted, done, refused, undone, new · disputed`, plus `changed since` styled as a dispute. | `format.ts:73-86`, `PendingDrawer.tsx:768`, `ActionModal.tsx:1097` |
| V4 | Spacing is ad hoc: 1, 2, 3, 4, 6, 8, 10, 12, 14, 16, 18, 20, 30, 40 px all appear, several as inline styles (`style={{ marginTop: 8 }}`, `padding: 8`). Radii are 2, 6, 8, 10, 12 px. | `globals.css`, `EntityDrawer.tsx:1265`, `EvidencePanel.tsx:1555` |
| V5 | Type scale is unmanaged: 20/16/14/13/12/11 px with mono used for stage logs, intervals, chain ids and whole source documents. 11 px chip text is below the readable floor for dense data. | `globals.css:86-96, 142` |
| V6 | Casing is mixed within one view: `lead / owns / members` lowercase labels, `Accepted decisions` sentence case, chips lowercase, buttons lowercase (`clear`, `use`, `today`), section labels `RECORDED` uppercase, modal title `confirm fact` lowercase. | `03-entity-drawer-ledger.jpg`, `08-action-view-modal.jpg` |
| V7 | Team cards are an `auto-fill` grid with unequal heights; Risk is twice the height of Payments and the second row leaves a two-card hole. | `02-overview-decisions.jpg` |
| V8 | Member names wrap unevenly inside a 110 px label grid (`Bianca Ishikawa` alone on a line, then `Esme Oyelaran Rhea Hartley` together). | `01-overview-top.jpg` |
| V9 | Hard-coded colours bypass tokens: `<mark>` is `#ffe58a` on `#1d1d1b` in both themes; graph node colours are a fixed six-hue map not adjusted for dark mode. | `globals.css:218`, `GraphCanvas.tsx:1731-1738` |
| V10 | Dark-mode primary button is white text on `#7ea2ff` (contrast ≈ 2.5:1, fails AA). The disabled Ask button is a dim blue square that reads as "loading". | `09-ask-empty.jpg`, `globals.css:120` |

### 1.3 Overview

| # | Problem |
|---|---|
| O1 | Teams are cards, decisions are flat rows, pending is a conditional list. Three list shapes for three lists of records; none is sortable, filterable or scannable as a table. |
| O2 | The dispute flag `⚑` after a system name has no label, tooltip or text alternative, and the red glyph is the only signal. |
| O3 | Decisions show id, title and "affects" only: no status, no date, no decider, no superseded-by. |
| O4 | Loading is the text "loading the organisation…"; errors are a red line; there is no skeleton, no retry, no empty state for a seed with no teams. |
| O5 | The pending section appears only when non-empty, so the page layout shifts depending on the acting person. |

### 1.4 Entity drawer

| # | Problem |
|---|---|
| E1 | Sections are a flat stack of `h3`s (Open disputes, Owner, Lead, Dependencies, Decisions, History, Sources) with no in-panel navigation; the history section dumps every chain with raw ids (`ch_DEPENDS_ON:system:checkout>system:ledger`) and raw predicates (`OWNS`, `DEPENDS_ON`, `PART_OF`) as labels. `04-entity-drawer-history.jpg` |
| E2 | Rendering bug: `NOT NOT: Ledger depends on Postgres Main` (negated flag prefixed onto a statement that already contains the negation). |
| E3 | Fact rows are `flex-wrap` with statement, status chip, mono interval, up to three citation chips and an action chip; at 560 px some rows fit one line and others wrap to two, so the column of chips never aligns. |
| E4 | The dispute notice lists "Who can confirm" under both the recorded and the challenger side, showing the same person, the same path and two "switch to Bob" buttons. |
| E5 | "Fed by" is shown first when opened from Graph, "Sources that mention it" is shown last otherwise. Same data, two positions. |
| E6 | "Depended on by" renders paths as plain strings (`Ledger ← Checkout ← Payments ← Priya Raman`), not interactive, not aligned. |
| E7 | Clicking a citation inside the drawer opens the Evidence drawer on top of it (see S8). The user loses the fact they were inspecting. |
| E8 | The header's "Ask about this" button navigates away and closes the panel, with no way back to the same entity. |

### 1.5 Evidence panel

| # | Problem |
|---|---|
| EV1 | Two containers for the same component: an inline card on Ask, a stacked drawer elsewhere. Widths, headers and close buttons differ. |
| EV2 | Disabled tabs (Path when no path, Timeline when no chain) look identical to enabled muted tabs; clicking does nothing and nothing explains why. `06-evidence-timeline.jpg` |
| EV3 | The Source tab shows the entire source document in 12 px mono muted text with the span block highlighted; revision selector shows a hash (`0b79f5f1b6a3 (latest)`); `chars 2231..2494` is shown to end users. `05-evidence-source-stacked-drawers.jpg` |
| EV4 | The Path tab from an eligibility link shows node pills with the raw id as both name and tag (`ledger ledger`, `bob-lindqvist bob-lindqvist`) and `evidence (0)` per edge. `15-evidence-path.jpg` |
| EV5 | The Timeline tab header is the raw call `get_history(system:checkout, DEPENDS_ON)`. |
| EV6 | The external link is a bare `↗` glyph; "Expand" and "View full graph" have no description of what they do. |

### 1.6 Ask

| # | Problem |
|---|---|
| A1 | The planner/tool trace (`plan: ownership → link_entities({"mentions":["Ledger"]}) ← 1 item(s) graph … verified: kept 2, dropped 0`) is printed in mono above every answer, six lines per turn, before the user sees the answer. It is developer output in the primary reading path. `10-ask-answer-owner.jpg` |
| A2 | The answer is a list of verified facts with chips, with no answer sentence. For "What breaks if Ledger goes down, and who do I tell?" the user gets eleven unstructured lines and must infer the two groups (what breaks, who to tell). `12-ask-impact-answer.jpg` |
| A3 | "How I answered" is a `<details>` that expands full-width Cypher blocks inline in the chat log, so an open trace pushes every later turn down and makes the log scroll unusable. `11-ask-trace-and-evidence.jpg` |
| A4 | The user message is a right-aligned rounded bubble, a consumer chat idiom. The composer placeholder lists three example questions separated by `·`. Enter-to-send is undocumented; there is no stop/cancel during streaming. |
| A5 | Action cards show eligibility paths as underlined raw-id strings (`rds-42 −ABOUT→ ledger infra −OWNS→ ledger bob-lindqvist −LEADS→ infra`) and a "switch to Bob" button inline. `14-ask-action-cards.jpg` |
| A6 | The learn-fact refusal reads "Not confirmable: Priya Raman's confirmation is live on the run this disputes; undo that confirmation first" with no link to that confirmation. |
| A7 | The dispute notice is repeated in full (recorded, challenger, two who-can-confirm blocks) under every turn that touches the disputed fact. `13-ask-dispute-notice.jpg` |
| A8 | The evidence panel keeps the last target across turns with no indication which claim it belongs to; under 1100 px it stacks below the log and is off-screen. |
| A9 | No turn metadata (time, as-of used), no permalink, no copy; suggestions include a write ("Infra owns Ledger now") with no hint that it writes. |

### 1.7 Graph

| # | Problem |
|---|---|
| G1 | 143 nodes and 271 edges rendered as one force-directed hairball; labels overlap, edge labels are 7 px, tickets (RDS-, FUL-, INS-) dominate and add noise. `16-graph.jpg` |
| G2 | No legend for node shapes/colours (only edge kinds), no search, no zoom or fit controls, no reset layout, no loading state inside the canvas. |
| G3 | The time slider ticks are unlabeled 1 px bars not aligned to the thumb; dragging changes the global As-of for every page with no confirmation. |
| G4 | One click on a node both selects it and opens the drawer; multi-select is a hidden shift-click. The edge panel renders below the canvas and pushes the layout. |
| G5 | The filter column is three cards of checkboxes with the convention "none checked = all" and explanatory copy under each. No applied-filter summary, no clear-all. |

### 1.8 Pending drawer and action view

| # | Problem |
|---|---|
| P1 | Awaiting items show a summary, a type tag, `fallback: any team lead` twice (header and beside the button) and a primary Confirm button, with no link to the fact, the entity or the evidence. The user is asked to confirm blind. `07-pending-drawer.jpg` |
| P2 | The log row is a link, a `done` chip and a mono UTC timestamp; no kind, no target. |
| P3 | Action view: title is the raw kind (`confirm fact`), then/now are underline tabs in the header with no label; "Relied on: Nothing (e.g. learned from chat)" and "Produced: No new facts" for a confirmation that did produce a confirmed assertion; the Undo button is a red outline with no confirmation step and no statement of consequence. `08-action-view-modal.jpg` |

### 1.9 Accessibility and feedback

| # | Problem |
|---|---|
| X1 | Colour-only encoding of status and citation class; red flag glyph without text; `title` attributes are the only explanation on chips (unavailable to keyboard and touch). |
| X2 | Tabs have no `role="tablist"`/`aria-selected`; drawers and the modal have no `role="dialog"`, `aria-modal`, focus trap or focus return; the range slider has no `aria-valuetext` with the date. |
| X3 | No custom focus-visible styles; chips at 11 px; disabled states at 55 % opacity only. |
| X4 | Feedback after writes is a notice line inside the card (`✓ Done`); there are no toasts, no optimistic state, no error recovery path; `confirm preview failed: …` is red small text. |
| X5 | Loading states are the word "loading…" in six places; no skeletons, no progress during streaming beyond the trace lines. |

---

## 2. Roles, tasks and information architecture

### 2.1 Roles

The product has one UI and a demo "acting as" switch; the graph authorisation rule decides what each person may do. The roles below are what the switch simulates.

| Role | Who | Top tasks |
|---|---|---|
| Reader (engineer, on-call, new joiner) | Any person | Find who owns / leads / knows a system; see what depends on it and what breaks; read why a decision was made; open the source behind a claim. Read-only. |
| Holder (team lead, system owner) | Leads of teams that own things; deciders | Everything a reader does, plus: see what is awaiting them; confirm a routed ticket or a draft; settle a dispute about something they hold; undo their own confirmation; see the then/now of an action. |
| Requester (any person) | Anyone with the write token | Route a ticket to the owner; record a fact learned in chat; draft an ADR supersession; follow their open proposals; withdraw one. |
| Operator (judge, demo driver, developer) | Token holder | Set the token; pick the acting person; set the as-of date; watch the reset schedule; inspect packs, verifier report and Cypher. |

### 2.2 Objects

Teams, People, Systems, Projects, Decisions, Tickets (entities); Facts (assertions with status and interval); Sources and Spans; Actions (route, learn, draft, confirm, undo); Disputes (a run with a recorded and a challenger side); Paths; Turns.

Every object gets a stable URL so it can be linked from an answer, an inbox item or a toast:

```
/ask                       conversation (?q= prefill)
/ask/t/:turnId             a turn and its trace
/directory                 teams (default), systems, people, projects, decisions, tickets as tabs
/e/:entityId               entity page; ?tab=overview|history|sources|disputes
/graph                     graph; ?select=a,b  ?as_of=
/inbox                     awaiting me (default), my proposals, activity
/a/:actionId               action record (then/now)
/s/:sourceId#span          source with a span highlighted
```

The same views open as an **inspector** (right panel) when reached from a list or an answer, and as a **page** when reached by URL. One component, two containers, never stacked more than one deep.

### 2.3 Navigation

```
┌──────────────┬──────────────────────────────────────────────┬────────────────┐
│ Sidebar 232  │ Context bar 48                               │                │
│              │ [⌘K Search…]      [As of: Today ▾] [Priya R ▾]│                │
│ ● Ask        ├──────────────────────────────────────────────┤  Inspector     │
│ ● Directory  │ Page header (title · meta · actions · tabs)  │  (380–480,     │
│ ● Graph      │                                              │  resizable,    │
│ ● Inbox  4   │ Content                                      │  one level,    │
│              │                                              │  breadcrumb    │
│ ─────────    │                                              │  inside)       │
│ Session      │                                              │                │
│ ○ demo mode  │                                              │                │
└──────────────┴──────────────────────────────────────────────┴────────────────┘
```

- **Sidebar** (collapsible to 56 px icon rail, `[` to toggle): Ask, Directory, Graph, Inbox with count. Footer: session status (Demo mode / Writes enabled, next reset), acting person avatar, and a "Session…" item that opens the settings sheet (token, acting-as, as-of, debug).
- **Context bar**: search / command palette (`⌘K`: entities, questions, inbox items, "switch to…", "as of…"), the **As-of pill** (reads "Today" or "As of 12 Mar 2026 · Clear"; when set, the content area gets a thin top border in the warning colour and the pill is filled, so the past is never silent), and the **acting-person menu** (name, role badges, "demo identity" note, switch).
- **Inspector**: the single right panel. Holds the entity peek, the evidence (source / path / timeline), the action record, or an inbox item. It has its own breadcrumb (`Ledger › Evidence › Service catalogue`) and a back action instead of stacking. On Ask it is always open; elsewhere it opens on demand and closes with Escape.
- **Modals** are reserved for confirmation of writes (Confirm, Undo) and the session sheet. Nothing else is modal.

### 2.4 Task flows

1. **Find and inspect**: `⌘K` → entity → inspector peek (owner, lead, deps, disputes, recent history) → "Open page" → entity page tabs (Overview, History, Sources, Disputes).
2. **Ask and verify**: Ask → answer with a lead sentence and grouped claims → click a claim → inspector shows Source with the quote; tabs Path and Timeline → "Open entity".
3. **Act**: Ask ("Route RDS-42…") or entity page action menu → proposal card (what, to whom, who can confirm, why) → the holder sees it in Inbox → Confirm modal (what changes, as-of, eligibility) → toast with "View action" → action record.
4. **Settle a dispute**: dispute badge anywhere → inspector Disputes tab: recorded vs challenger side by side with sources → Confirm one side (modal) → toast.
5. **Explore in time**: Graph → filters chip bar → time scrubber with labelled change ticks → node → inspector peek → "Ask about selection".
6. **Audit**: Inbox › Activity or an action chip → action record with Then / Now segmented control and a "changed since" diff.

---

## 3. Design system

### 3.1 Principles

1. Neutral first, light first. The interface is white and cool grey; colour is reserved for state and for the one indigo accent that marks interaction. No dark-by-default, no blue link walls.
2. Colour never carries meaning alone. Every state has a shape or a word as well (dot, icon, label).
3. One component, every container. Fact rows, chips, notices and panels look the same in a page, an inspector, a card or a modal.
4. Dense but aligned. 4 px grid, fixed row heights, right-aligned numerics and dates, chips in a fixed trailing column.
5. Explain, don't expose. Raw ids, predicates, chain ids, template names and Cypher live behind "Details" or in the debug panel, never in a label.

### 3.2 Colour tokens

**Light is the default and the primary theme.** The current UI follows the OS into a near-black dark theme with saturated blue links; that reads as a developer tool. Enterprise dashboards (Stripe, Linear, Atlassian, Workday) are light, cool-grey surfaces with one restrained accent, and that is the direction here. Dark remains available as an explicit opt-in in the Session sheet, never auto-applied.

Palette rationale:

- **Neutrals: cool slate.** A slightly blue-grey scale (not warm beige, not pure grey) reads as precise and corporate, keeps white panels crisp, and gives borders and table rules enough presence at 1 px without looking heavy.
- **Accent: indigo.** `#4f46e5` is the enterprise signature shared by Stripe and Linear: distinct from the default-browser-link blue the current UI uses, calm at small sizes, and strong enough for a primary button on white (6.3:1). It is used only for interaction: primary buttons, links, focus rings, selected rows, the "proposed" state.
- **Semantics: green, amber, red**, each with a 100-tint for chips and notices. No teal, purple or orange anywhere else, so the three semantic colours are always unambiguous.
- **Sidebar is light** (white on the slate page background with a right border), not a dark column; the only dark surfaces are tooltips and the command palette backdrop.

```css
:root {
  /* neutrals (cool slate) */
  --n-0:   #ffffff;  --n-50:  #f8fafc;  --n-100: #f1f5f9;  --n-200: #e2e8f0;
  --n-300: #cbd5e1;  --n-400: #94a3b8;  --n-500: #64748b;  --n-600: #475569;
  --n-700: #334155;  --n-800: #1e293b;  --n-900: #0f172a;  --n-950: #020617;

  /* accent: indigo (interaction only) */
  --accent-700: #4338ca;  --accent-600: #4f46e5;  --accent-500: #6366f1;
  --accent-100: #e0e7ff;  --accent-50:  #eef2ff;

  /* semantic */
  --success-700: #15803d;  --success-600: #16a34a;  --success-100: #dcfce7;
  --warning-700: #b45309;  --warning-600: #d97706;  --warning-100: #fef3c7;
  --error-700:   #b91c1c;  --error-600:   #dc2626;  --error-100:   #fee2e2;

  /* roles */
  --bg:            var(--n-50);     /* page */
  --surface:       var(--n-0);      /* cards, tables, sidebar, inspector */
  --surface-2:     var(--n-100);    /* table header, hover, code */
  --surface-3:     var(--n-200);    /* pressed, skeleton */
  --border:        var(--n-200);
  --border-strong: var(--n-300);    /* inputs, dividers inside data */
  --text:          var(--n-900);
  --text-2:        var(--n-600);    /* secondary: 7.5:1 on white */
  --text-3:        var(--n-500);    /* tertiary, placeholders: 4.8:1 on white */
  --text-disabled: var(--n-400);
  --text-inverse:  var(--n-0);
  --link:          var(--accent-700);
  --primary:       var(--accent-600);  --primary-hover: var(--accent-700);
  --focus:         var(--accent-500);
  --selection:     var(--accent-50);   --selection-bar: var(--accent-600);
  --tooltip-bg:    var(--n-800);
  --overlay:       rgb(15 23 42 / 0.45);
  --shadow-1: 0 1px 2px rgb(15 23 42 / 0.06), 0 1px 3px rgb(15 23 42 / 0.04);
  --shadow-2: 0 8px 24px rgb(15 23 42 / 0.12);
}

/* opt-in only; never applied from prefers-color-scheme */
:root[data-theme="dark"] {
  --bg: var(--n-950); --surface: var(--n-900); --surface-2: var(--n-800); --surface-3: var(--n-700);
  --border: var(--n-800); --border-strong: var(--n-700);
  --text: #e2e8f0; --text-2: #94a3b8; --text-3: #7c8aa0; --text-disabled: #475569; --text-inverse: var(--n-950);
  --accent-700: #a5b4fc; --accent-600: #818cf8; --accent-500: #6366f1; --accent-100: #27306b; --accent-50: #1e2452;
  --success-700: #4ade80; --success-100: #14321f;
  --warning-700: #fbbf24; --warning-100: #3a2a0a;
  --error-700:   #f87171; --error-100:   #3b1515;
  --link: var(--accent-700); --primary: var(--accent-600); --primary-hover: var(--accent-700);
  --selection: var(--accent-50); --tooltip-bg: var(--n-700); --overlay: rgb(0 0 0 / 0.6);
}
```

Semantic usage rule: chips and notices use the `-100` tint as background with the `-700` colour for text and icon (never `-600` text on a tint). Solid semantic fills are reserved for the status dot and the toast icon.

Contrast (light): `--text` 17.9:1, `--text-2` 7.5:1, `--text-3` 4.8:1 on white; white on `--primary` 6.3:1; `--success-700` on `--success-100` 5.2:1; `--warning-700` on `--warning-100` 5.6:1; `--error-700` on `--error-100` 6.1:1; `--link` on white 8.1:1. Floor: ≥ 4.5:1 for all text, including chip text, in both themes; dark primary uses `--text-inverse` (near-black) on `--accent-600`.

**Product semantics mapped onto the palette.** Hue count stays at neutral + accent + 3.

| Meaning | Encoding |
|---|---|
| Fact status `current` | success dot ● + word |
| `historical` (superseded) | neutral hollow dot ○ + word, text-2 |
| `disputed` (open) | error dot + word; error flag icon on entities |
| `overruled` (dispute settled against) | neutral dot + strikethrough word |
| `proposed` | accent dot + word |
| `confirmed` | success dot + word "confirmed" |
| `withdrawn` / `retracted` | neutral, strikethrough |
| `unknown at date` | neutral dashed outline |
| Stale document | warning ghost (dashed) edge; warning notice |
| Citation class `graph` | quote icon, neutral chip, no colour |
| Citation class `text-only` | quote icon, neutral chip, suffix "text only" in text-3 |
| Citation class `unverified` | dashed neutral chip, suffix "unverified" |
| Eligibility `holder` / `receiver` | neutral chip with a key icon |
| Eligibility `fallback` | warning chip "fallback: any team lead" |
| Action kinds | neutral chip with a kind icon; never purple |
| Node types on the graph | shape + a 5-step neutral/accent ramp; one legend |

### 3.3 Typography

Font: `Inter` (variable, via `next/font`), fallback system-ui. Mono: `JetBrains Mono`, fallback ui-monospace. Tabular numerals on dates, counts and intervals (`font-variant-numeric: tabular-nums`).

| Token | Size / line | Weight | Use |
|---|---|---|---|
| `display` | 24 / 32 | 600 | Entity page title only |
| `title` | 18 / 24 | 600 | Page header |
| `heading` | 15 / 20 | 600 | Section, inspector title, modal title |
| `label` | 12 / 16 | 600, `letter-spacing: 0.02em`, uppercase | Column headers, kv labels, group labels |
| `body` | 13.5 / 20 | 400 | Default UI text (dense) |
| `body-strong` | 13.5 / 20 | 500 | Fact statements, row primaries |
| `small` | 12 / 16 | 400 | Meta, help text, chips |
| `micro` | 11 / 14 | 500 | Counts in badges only |
| `mono` | 12.5 / 18 | 400 | Ids, Cypher, source text, intervals |

Casing: sentence case everywhere (titles, buttons, chips, section labels). Only `label` tokens are uppercase. No lowercase titles or buttons.

### 3.4 Spacing, sizing, shape

- Grid: 4 px. Scale: `4, 8, 12, 16, 24, 32, 48, 64`.
- Component heights: input / button / chip-row 32; small button 28; table row 36 (dense) or 44 (comfortable); list row 40; sidebar item 32; context bar 48; page header 56 + optional 40 tab row.
- Page gutter 24; section gap 24; card padding 16; inspector padding 16; kv gap 8 / 16.
- Radii: 4 (chips, checkboxes, inputs), 6 (buttons, cards, rows), 8 (inspector, modal, popovers). No pills except the count badge.
- Borders: 1 px `--border` everywhere; `--border-strong` for inputs and dividers inside data.
- Shadows: `--shadow-1` on popovers, `--shadow-2` on modals and the inspector when overlaying. Cards have no shadow.
- Motion: 120 ms ease-out for hover/press, 180 ms for panels, none for data updates. Respect `prefers-reduced-motion`.

### 3.5 Iconography

One icon set (Lucide, 16 px, 1.5 px stroke, `currentColor`). Named uses: search, calendar, user, inbox, git-branch (graph), book-open (directory), message-square (ask), quote (citation), flag (dispute), clock (historical/as-of), key (eligibility), undo-2, check, x, external-link, chevron-right, info, alert-triangle, alert-circle, loader. No Unicode glyph icons anywhere.

### 3.6 Components and patterns

**Page header.** Title (`title`), optional description (`small`, text-2), meta chips row (as-of, counts), right-aligned actions (one primary at most), optional tab row. Sticky at top of the content column with a bottom border.

**Table.** Dense rows (36 px), sticky header, `label` column headers, text columns left, numeric and dates right in tabular mono, a trailing fixed-width "status" column with status chips, a hover row background `--surface-2`, a selected row `--selection` with a 2 px accent left bar. Row click opens the inspector; a chevron shows on hover. Sorting by header click; applied sort shown with an arrow. Empty state inside the table body (icon, one line, one action). Loading: 5 skeleton rows. Pagination only above 200 rows; otherwise virtualised scroll.

**Fact row** (the atom of this product). Fixed layout, never flex-wrap:

```
┌ 2px status bar ┐
│ Statement (body-strong, wraps)                  ● current   2025-01-01 → now   [❝ catalogue] [❝ wiki] +1   ⋯ │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Columns: statement (flex), status (96 px), interval (152 px, mono, tabular), citations (max two chips + "+n"), overflow menu (open evidence, open timeline, open action, copy id). On narrow containers (< 480 px) the trailing columns move to a second line but keep their column alignment. Negation is rendered once ("Not: …") by the row, never by prefixing a statement that already contains it.

**Chips.** 24 px high, 12 px text, 4 px radius, 1 px border, 8 px horizontal padding. Variants: `status` (dot + word), `kind` (icon + word, neutral), `citation` (quote icon + source kind, neutral; hover shows title and date; keyboard focusable; opens evidence), `count` (micro). No chip is coloured by hue alone; see §3.2.

**Form.** Labels above fields (`label` token, sentence case), 32 px inputs with `--border-strong`, help text below in `small` text-2, inline validation in error colour with an icon, required marked with "(required)" text, never a red asterisk alone. Submit row right-aligned: secondary then primary. Date input is a popover calendar with a "Today" shortcut and a typed field.

**Filters.** A toolbar above lists: a search field, filter popovers (multi-select with counts), applied filters rendered as removable chips, "Clear all" when any are applied, and the result count at the right ("143 nodes · 271 edges"). "None selected = all" is replaced by an explicit "All" default in each popover.

**Inspector.** Right panel, 420 px default, resizable 360–560, border-left, `--surface`. Header: breadcrumb (`small`, text-2) + title (`heading`) + actions (open page, close). Body scrolls independently; sticky in-panel tab row when it has tabs. One level only; navigating inside replaces content and pushes the breadcrumb; Back and Escape pop. Focus moves into the panel on open and returns on close. `role="complementary"` (non-modal).

**Modal.** 480 (confirm) / 640 (form) / 880 (record) px, `role="dialog" aria-modal`, focus trap, Escape and backdrop close unless the modal is mid-submit. Header (title + close), body, footer (secondary left, destructive/primary right). Destructive modals state the consequence in one sentence and name the undo path.

**Toast.** Bottom-right, 360 px, 5 s (8 s if it has an action), stack up to 3, kinds: success, info, warning, error (icon + colour + word). Every write ends in a toast with a "View action" link. Errors from writes are toasts with a "Retry" action; errors from reads are inline.

**Notice (callout).** Inline block with a 2 px left bar and an icon: info (accent), warning, error, success. Used for refusals, disputes, stale and anonymous notes. One notice per situation; never repeated per turn.

**Empty / loading / error states.** Every list and panel has all three: skeletons shaped like the final content (not spinners) for < 1 s expected loads; a one-line empty state with an icon and a single action; an inline error with the message, a "Retry" and a "Copy details" (status code, request id).

**Keyboard.** `⌘K` palette; `/` focuses search; `Esc` closes inspector/modal; `[` sidebar; `g a / g d / g g / g i` jump to Ask / Directory / Graph / Inbox; Enter sends in the composer, Shift+Enter newline, `⌘.` stops streaming. Visible focus ring: 2 px `--focus` with 2 px offset on all interactive elements.

---

## 4. Screen-by-screen redesign and state coverage

Each screen lists layout, components and the state matrix. "States" means every one must be implemented and screenshotted.

### 4.1 Shell and session

- Sidebar, context bar and inspector as in §2.3.
- **As-of pill** states: Today (neutral) · As-of set (filled warning tint, "As of 12 Mar 2026", thin warning top border on content) · Unsupported (page has no time axis, pill disabled with tooltip).
- **Acting person menu**: avatar + name; menu shows role chips ("Leads Payments", "Decides ADR-007"), team, "Demo identity, not authentication" note, searchable list of people with their roles aligned in a second column, and "Open session settings".
- **Session sheet** (modal): mode (Demo / Writes enabled) with explanation; token field (password, masked, "Use" / "Remove"); acting person; as-of; theme; debug toggle; next reset time. All session controls live here, not in the toolbar.
- **Demo mode**: sidebar footer shows "Demo mode · writes off" with an info icon; Inbox shows a notice in place of Confirm buttons; the count badge is hidden; the banner is removed.
- States: API reachable · API unreachable (full-page error with retry and the URL) · demo · writes enabled · writes enabled with scheduled reset (small notice in the sidebar footer with the time) · session creation failed (inline error in the footer with retry).

### 4.2 Ask

Layout: conversation column (max 760 px, centred in the content area) + inspector (always open on Ask, shows the evidence for the selected claim; empty state explains).

- **Empty state**: title "Ask Nodus", one line on verification, suggested questions as a two-column list grouped "Questions" and "Actions (write)", each with a kind icon. Composer at the bottom.
- **Turn**: user line (left-aligned, `body-strong`, person avatar, time, as-of chip if set); then a **status line** that replaces the raw trace: during streaming "Planning… · Reading owners… · Verifying…" with a progress bar; when done "Ownership · 2 tools · 2 claims verified · 0 dropped · 310 ms" with a "Trace" button that opens the trace in the inspector (Cypher, params, rows, timings, verifier report). Nothing mono is shown in the conversation.
- **Answer**: a lead sentence assembled from the claims ("Infra owns Ledger; the lead is Bob Lindqvist.") followed by claims as fact rows, grouped by the planner intent (impact: "What breaks" / "Who to tell"; ownership: "Owner" / "Lead"; history: a timeline). Selecting a row highlights it and drives the inspector. The unverified explanation, if any, is a muted paragraph labelled "Explanation (not verified)".
- **Abstain**: notice (info) "No verified answer" + "Nearest evidence" rows, each opening the Path tab.
- **Dispute**: one notice per disputed fact per conversation (not per turn), collapsed to a line "Ownership of Statements is disputed · View" that opens the Disputes view in the inspector.
- **Action card**: kind icon + title ("Route RDS-42 to the owner"), a two-column summary (Target, Proposed assignee, Why: the relied-on facts as compact rows), then an **eligibility block**: "Who can confirm" as a list of people with role chip and a "Why" link (opens Path), and a "Switch to Bob" secondary button. Confirm button only when eligible; otherwise the block says so in one line. Refusal: error notice with the reason and, when the reason names another action, a link to it. Learn-fact: "Recorded at chat rank as disputed · View dispute".
- **Composer**: 2-row textarea, placeholder "Ask a question or describe an action…", send button with icon, hint "Enter to send · Shift+Enter for a new line", Stop button while streaming. Disabled with reason when there is no session.
- States: empty · streaming (status line + skeleton answer) · answered · abstained · answered with explanation · dispute · action proposed (eligible / not eligible / fallback / anonymous) · refusal · write error · stream error (notice with Retry that resends the same text) · debug on (raw packs in the inspector Trace tab) · narrow (< 1100 px: inspector becomes a bottom sheet opened by the row's chevron).

### 4.3 Directory (replaces Overview)

Page header: "Directory" · as-of meta · tabs Teams / Systems / People / Projects / Decisions / Tickets · filter toolbar.

- **Teams**: table with columns Team, Lead, Members (count, expands), Owns (chips, "+n"), Disputes (count with flag). Row opens the team in the inspector. Teams with no current lead show "No current lead" in text-3 with a clock icon.
- **Systems**: System, Tier, Owner (team · lead), Depends on (count), Depended on by (count), Decisions (count), Status (any open dispute / stale).
- **People**: Name, Title, Team, Leads, Decides, Owns via team.
- **Decisions**: Id, Title, Status (accepted / proposed / superseded), Decided, Deciders, Affects, Replaces.
- **Tickets**: Id, Title, About, Assigned to, Status.
- A "Pending for you" summary strip above the table when the acting person has items (links to Inbox), always rendered (as "Nothing pending") so layout does not shift.
- States: loading (skeleton table) · loaded · empty seed · filtered to nothing ("No systems match · Clear filters") · error with retry · as-of in the past (header meta and pill) · demo mode (unchanged, read-only).

### 4.4 Entity (inspector peek and full page)

Peek (inspector): breadcrumb (type), title, type chip, dispute flag chip if any, actions "Open page", "Ask about this" (opens Ask with the question prefilled, keeps the inspector), close.
Sections in fixed order: **Summary** (kv: owner, lead, tier, part of, as-of), **Open disputes** (only if any; one line each with "Settle"), **Dependencies** (two aligned lists with entity links; impact paths as rows with hop count), **Decisions** (rows: id, title, status, date), **Recent history** (last 5 fact rows across predicates, "View all history" → page tab).

Page (`/e/:id`): page header with the same title/actions; tabs **Overview** (the peek content at full width, two columns), **History** (per-predicate timelines; predicate names humanised: "Ownership", "Lead", "Depends on", "Part of", "Affects"; chain ids hidden behind a "Details" toggle; timeline uses the fact row plus a vertical rail with status dots), **Sources** (table: title, kind, date, latest/old revision, spans count; row opens the Source tab in the inspector), **Disputes** (recorded vs challenger side by side, each with sources, one who-can-confirm block, Confirm on the chosen side).

- States: loading · loaded · not found (page-level empty with "Search") · no owner / no lead / no dependencies / no decisions / no history / no sources (each a one-line text-3 placeholder, not a hidden section) · open dispute · settled dispute (overruled rendering) · as-of past (facts unknown at date rendered with dashed status) · from graph (identical; "Fed by" is just the Sources tab).

### 4.5 Evidence (inspector)

Tabs Source / Path / Timeline, each disabled with a reason tooltip and `aria-disabled` when unavailable ("No graph path for a text-only citation").

- **Source**: header with kind icon, title, date, revision menu (human label "Revision 3 · latest" with the hash in a tooltip), "Open original" button with icon. Body: the document with the cited span scrolled into view and highlighted with `--selection` and a 2 px accent left bar; the exact quote marked in `--warning-100` with text `--text` (tokenised, dark-safe). "Not in the latest revision" is a warning notice with a button to the latest. Offsets (`chars 2231..2494`) appear only in the "Details" row.
- **Path**: vertical step list: node cards (name, type chip, entity link) and edge rows (humanised type "owns", interval, evidence count chip that expands citation chips, dispute side-row in error tint). Buttons: "Show neighbourhood" (1/2 hops, inline canvas 320 px with its own legend) and "Open in Graph". Eligibility paths resolve ids to names and labels before rendering.
- **Timeline**: header "History of ownership · Ledger" (humanised), the history timeline component, actions list as chips.
- States: empty (no selection) · loading · source loaded · span not in latest · span removed entirely · tab unavailable · path with superseded edge · path with dispute · impact (every affected path) · neighbourhood loading / loaded / error · timeline empty.

### 4.6 Graph

Page header: "Graph" · "143 nodes · 271 edges" · actions: Fit, Reset layout, Layout menu (force / concentric / hierarchy), Legend toggle.
Toolbar: search node (typeahead, selects and centres), filter popovers (Entity type, Source kind, Highlights: disputed n, stale n, "Hide tickets" default on), applied chips, Clear all.
Canvas: full height of the content area; zoom controls bottom-right; legend bottom-left (node shape/type and edge kinds in one panel); loading overlay with a spinner and "Laying out 143 nodes…"; empty overlay when filters remove everything.
Time scrubber (below header, 48 px): labelled start/end dates, a draggable thumb with a date tooltip, change ticks with hover labels, "Today" button; dragging previews locally and commits As-of on release with a toast "Viewing as of 1 Mar 2026 · Undo".
Selection: click selects and opens the inspector peek; shift-click multi-selects; a selection bar appears above the canvas ("2 selected · Ask about selection · Clear"). Edge click opens the edge in the inspector (facts and evidence), never below the canvas.

- States: loading · loaded · filtered to nothing · one selected · many selected · edge selected · disputed edge · stale edge · as-of past · error · reduced-motion (no layout animation).

### 4.7 Inbox (replaces Pending drawer)

Page header "Inbox" · tabs **Awaiting you** (n) / **Your proposals** (n) / **Activity**. Row = action kind icon, summary, target entity link, requester, age, eligibility chip (holder / fallback), and a trailing **Confirm** (primary, small) or the reason it is unavailable. Row click opens the item in the inspector: the proposal's relied-on facts, the produced fact, sources, who can confirm with "Why", then Confirm.
Confirm modal: "Confirm: Infra owns Ledger" · what will become current and what becomes superseded · as-of · eligibility rule used · Cancel / Confirm. Success toast "Confirmed · View action". Guard refusal → error toast with reason and "View".
Your proposals: rows with status and "Withdraw" (secondary, opens an Undo modal that names the consequence). Activity: table of the person's actions (kind, summary, status, time) with row → action record.

- States: loading · nothing awaiting · items · fallback item · anonymous (rows render, Confirm replaced by "Writes are off in demo mode") · not eligible (reason text) · confirm in flight (button spinner, modal locked) · confirmed · refused by the guard · undo available / unavailable / done · activity empty.

### 4.8 Action record (`/a/:id`, also in the inspector)

Header: kind icon + humanised title ("Confirmation: Infra owns Ledger"), status chip (done / proposed / withdrawn / refused), **Then / Now** segmented control with a one-line caption ("What the brain believed when it acted, 12 Oct 2026 15:07"). KV: requested by (with role chip), via, confirmed by (list with eligibility chip and link), when, target.
Sections: **Relied on** (fact rows; rows that changed since carry a "Changed since" warning chip when Now is selected, with a hover diff "then: Payments · now: Infra"), **Produced** (fact rows; a confirmation lists the confirmed assertion), **Draft** (collapsed; "Agent draft, not evidence" label; withdrawn state struck through), **Undo** (button with consequence text; disabled with reason; after undo, a link to the undo action).

- States: loading · then · now · now with changes · withdrawn · undo allowed / not allowed / done · not found · debug (raw pack).

### 4.9 Global states

- **Anonymous**: no banner; sidebar footer status; write controls replaced by one-line reasons; the Session sheet explains.
- **API down**: full-page state with the API URL, "Retry", and "Open session settings".
- **Rate limited (429)**: toast with a countdown; composer disabled until it passes.
- **Stale as-of**: pill and top border as in §4.1.
- **Narrow (< 1100 px)**: sidebar collapses to the icon rail; inspector becomes a bottom sheet; tables hide tertiary columns behind a "⋯" column menu.
- **Theme**: light is the shipped default and is what every state is designed and screenshotted in first. Dark is opt-in from the Session sheet and is verified as a second pass.

---

## 5. Critique checklist (applied after each screen is implemented)

Each screen is screenshotted in light at 1440 px and at 1024 px, in every state listed in §4 (dark opt-in checked once per screen at 1440 px), and checked against:

1. Only neutral + accent + success / warning / error hues on screen; no hue carries meaning without a dot, icon or word.
2. Every size, gap and radius is a token from §3.4; no inline `style` with pixel values.
3. Type sizes are from §3.3; no 11 px text except count badges; sentence case everywhere except `label` tokens.
4. No raw ids, predicates, chain ids, template names, offsets or Cypher outside a "Details" toggle or the Trace panel.
5. Fact rows align their status, interval and citation columns across the whole list.
6. One overlay at a time; inspector has a breadcrumb; modal has focus trap, Escape and focus return.
7. Every list and panel shows loading, empty and error states; every write ends in a toast with a link.
8. Contrast ≥ 4.5:1 for text and chip text in both themes (checked with the computed colours).
9. Keyboard: Tab order follows reading order; focus ring visible; shortcuts from §3.6 work.
10. Demo mode and as-of-past are visible without a banner and never contradicted by an enabled control.

---

## 6. Implementation plan (for approval)

No code in this step. Proposed order, each step ending with the §5 pass:

1. **Foundation**: tokens, theme switch, Inter/JetBrains Mono, Lucide, primitives (Button, Chip, StatusChip, CitationChip, Notice, Toast, Skeleton, Tabs, Table, KV, Modal, Inspector, PageHeader, Field). Replace `globals.css` with token-based CSS modules or Tailwind with a token config (recommendation: Tailwind 4 with CSS variables, since the project already builds with Next 15 and has no UI library).
2. **Shell**: sidebar, context bar, As-of pill, acting-person menu, Session sheet, command palette, inspector container, routes from §2.2.
3. **Fact row, timeline, evidence**: the shared atoms, then the Evidence inspector (Source / Path / Timeline) with id-to-name resolution for eligibility paths and the negation fix.
4. **Ask**: status line, grouped answer, inspector-driven evidence, trace panel, action cards and eligibility block, dispute line, composer, every state.
5. **Directory and Entity**: tables per tab, entity peek and page with tabs.
6. **Inbox and Action record**: tabs, confirm/undo modals, toasts, then/now diff.
7. **Graph**: toolbar, scrubber, legend, selection bar, inspector hookup, ticket filter default.
8. **Final pass**: light at 1440 and 1024 px, dark opt-in once per screen, keyboard walk-through, screenshots into `docs/ui-audit/after/`.

API gaps the redesign needs (small, additive): `GET /directory/{systems|people|projects|tickets}` list endpoints (or extend `/overview`), names and labels on eligibility paths, a humanised `summary` on the stream's `plan` event, and the produced assertion on confirm actions.
