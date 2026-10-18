# Demo recording `data-testid` targets

Stable kebab-case targets for CursorCam beat scripts (`testid=<name>`).

## Log-in and onboarding (`/login`, `/start`)
- `demo-login`: "Use the demo account" button on `/login` (`ui/app/login/page.tsx`)
- `load-demo-company`: "LOAD THE DEMO COMPANY" card on `/start` (`ui/app/start/page.tsx`)
- `bring-context`: "Bring your company's context" link on an empty workspace (`ui/components/Shell.tsx`)

## Signed-in app rail (`ui/components/Shell.tsx`)
- `rail-ask`: Ask link (`/ask`)
- `rail-explore`: Explore link (`/explore`)
- `rail-inbox`: Inbox link (`/inbox`)
- `rail-sources`: Sources link (`/sources`)
- `rail-mcp`: "Connect your coding agent" (MCP) button
- `rail-toggle`: Expand / collapse sidebar button

## Lens controls: As-of and Acting-as (`ui/components/Shell.tsx`)
- `as-of-button`: As-of trigger in the rail or top header
- `as-of-input`: Date input (`type="date"`) inside the As-of popover
- `as-of-today`: "Today" button inside the As-of popover
- `as-of-done`: "Done" button inside the As-of popover
- `as-of-clear`: "×" button on the As-of trigger to reset to today
- `acting-as-button`: Acting-as trigger in the rail or top header
- `acting-as-search`: Search input inside the Acting-as menu
- `acting-as-option-<slug>`: Person option in the Acting-as menu, e.g. `acting-as-option-priya-raman`, `acting-as-option-bob-lindqvist`, `acting-as-option-tomas-reyes`, `acting-as-option-jonah-feld`

## Ask page (`ui/app/ask/page.tsx`)
- `ask-input`: Question / action textarea (`#ask-box`)
- `ask-button`: "Ask ↵" submit button
- `citation-chip-1`, `citation-chip-2`, `citation-chip-3`: Inline `[1]`, `[2]`, `[3]` citation chips on the lead sentence
- `citation-chip`: Source citation chip on supporting fact rows and path steps (`ui/components/Chips.tsx`)
- `action-chip`: Action record chip (`ui/components/Chips.tsx`)
- `evidence-line`: One-click path / proof bar under the lead answer
- `how-i-answered`: "How I answered" button on the status line
- `see-as-of`: "See it as of <date>" button under an answer with a past change
- `dispute-this`: "Dispute this" button under an ownership/leadership answer
- `then-now`: Container for the Then / Now comparison on a past-date follow-up turn
- `then-card`: The "THEN · AS OF …" card
- `now-card`: The "NOW" card
- `view-and-settle`: "View and settle" button on a conversation dispute notice (`ui/components/Dispute.tsx`)

## Proof rail / "How I answered" (`ui/components/TraceView.tsx`)
- `proof-tab-path`: Path tab
- `proof-tab-sources`: Sources tab
- `proof-tab-cypher`: Cypher tab
- `proof-tab-checks`: Checks tab
- `proof-source`: Source button on a path step
- `proof-quote-1`, `proof-quote-2`, …: Quoted source card in the Sources tab

## Evidence panel, Action record and Graph (`ui/components/EvidencePanel.tsx`, `ui/components/ActionRecord.tsx`, `ui/app/graph/page.tsx`)
- `tab-source`, `tab-path`, `tab-timeline`: Tabs in the Evidence inspector (`ui/components/ui.tsx`)
- `open-in-graph`: "Open in Graph" button in the Evidence Path tab
- `recenter-path`: Recenter on focused path button on `/graph`
- `as-of-slider`: Time-scrubber range input on `/graph`
- `graph-zoom-in`, `graph-zoom-out`, `graph-fit`: Zoom controls on `/graph`
- `segmented-then`, `segmented-now`: Then / Now toggle on an Action record (`ui/components/ui.tsx`)

## Inbox, Confirm and Undo (`ui/app/inbox/page.tsx`, `ui/components/ConfirmControl.tsx`, `ui/components/ui.tsx`)
- `tab-awaiting`, `tab-mine`, `tab-activity`, `tab-disputes`: Inbox tabs
- `inbox-row-1`, `inbox-row-2`, …: Rows in the "Awaiting you" list
- `inbox-mine-1`, `inbox-mine-2`, …: Rows in the "Your proposals" table
- `inbox-activity-1`, `inbox-activity-2`, …: Rows in the "Activity" table
- `inbox-dispute-1`, `inbox-dispute-2`, …: Rows in the "All open disputes" table
- `confirm-button`: "Confirm" / "Confirm the challenger" / "Confirm proposal" button
- `confirm-modal-submit`: Confirm button inside the confirmation modal
- `undo-button`: "Undo" button on an action record or confirmation result card
- `undo-modal-submit`: Undo button inside the undo confirmation modal
- `toast-action`: Action link (e.g. "Undo") inside a toast notification
- `view-action`: "View action" button on a confirmation result card
- `switch-to-<slug>`: "Switch to <FirstName>" shortcut on a "Who can …" row, e.g. `switch-to-priya-raman`

## Explore and Entity page (`ui/app/explore/page.tsx`, `ui/app/e/[id]/page.tsx`)
- `explore-search`: Search input on `/explore` (`#find`)
- `explore-pill-all`, `explore-pill-systems`, `explore-pill-people`, `explore-pill-decisions`, `explore-pill-tickets`: Filter pills on `/explore`
- `explore-row-<id>`: Result row on `/explore`, e.g. `explore-row-system:ledger`, `explore-row-team:payments`
- `entity-as-of-before`: "Before <date>" button on `/e/[id]`
- `entity-as-of-today`: "Today" button on `/e/[id]`
