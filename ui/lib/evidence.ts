// Structured evidence as readable cards (item 24 follow-up): a catalogue entry or a roster row is shown as
// what it says, not as raw YAML or a markdown table with ids. The raw text stays one click away.

export interface EvidenceCard {
  title: string;
  rows: [string, string][];
  line?: string;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function day(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso.trim());
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : iso;
}

/** "team:infra" → "Infra", "project:shared-services" → "Shared Services": a readable name without the id. */
export function idName(v: string): string {
  const s = v.trim().replace(/^[a-z_]+:/, "");
  return s.split("-").map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
}

const ID = /^(person|team|system|project|decision|ticket):[a-z0-9-]+$/;

function catalogue(text: string): EvidenceCard | null {
  if (!/^\s*-\s*id:\s*\S+/m.test(text)) return null;
  const kv: Record<string, string> = {};
  const deps: string[] = [];
  for (const line of text.split("\n")) {
    const dep = /^\s*-\s*\{\s*id:\s*([^,}]+)(?:,\s*from:\s*([^}]+))?\}/.exec(line);
    if (dep) { deps.push(idName(dep[1])); continue; }
    const m = /^\s*-?\s*([a-z_]+):\s*(.*)$/.exec(line);
    if (m) kv[m[1]] = m[2].trim().replace(/^"(.*)"$/, "$1");
  }
  const rows: [string, string][] = [];
  if (kv.owner) rows.push(["Owner", idName(kv.owner) + (kv.owner_from ? ` · since ${day(kv.owner_from)}` : "")]);
  if (kv.tier) rows.push(["Tier", kv.tier]);
  if (kv.project) rows.push(["Project", idName(kv.project)]);
  const listed = (kv.depends_on || "").replace(/^\[|\]$/g, "").split(",").map((x) => x.trim()).filter(Boolean).map(idName);
  const allDeps = [...listed, ...deps];
  if (allDeps.length) rows.push(["Depends on", allDeps.join(", ")]);
  return { title: kv.name || idName(kv.id || ""), rows };
}

function rosterRow(text: string): EvidenceCard | null {
  const t = text.trim();
  if (!t.startsWith("|")) return null;
  const cells = t.split("|").map((c) => c.trim()).filter((c, i, all) => !(c === "" && (i === 0 || i === all.length - 1)));
  if (cells.length < 2 || cells.every((c) => /^-+$/.test(c))) return null;
  const name = cells[0];
  const rest = cells.slice(1).filter((c) => !ID.test(c) && !/^(yes|no)$/i.test(c));
  const date = rest.find((c) => /^\d{4}-\d{2}-\d{2}/.test(c));
  const other = rest.filter((c) => c !== date);
  const parts = [name, ...other, ...(date ? [`since ${day(date)}`] : [])];
  return { title: name, rows: [], line: parts.join(" · ") };
}

/** A readable card for a catalogue entry or a roster row, or null for prose (shown as it is). */
export function structuredEvidence(text: string, kind?: string): EvidenceCard | null {
  if (kind === "catalog" || (!kind && /^\s*-\s*id:/m.test(text))) return catalogue(text);
  if (kind === "roster" || (!kind && text.trim().startsWith("|"))) return rosterRow(text);
  return null;
}
