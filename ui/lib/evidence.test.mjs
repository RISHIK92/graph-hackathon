// node --test lib/evidence.test.mjs (Node 22 strips the module's types)
import assert from "node:assert/strict";
import { test } from "node:test";
import { structuredEvidence } from "./evidence.ts";

test("a catalogue entry becomes owner, tier, project and dependencies, without ids", () => {
  const yaml = `- id: system:billing
    name: "Billing"
    aliases: ["billing-svc"]
    tier: 2
    owner: team:fulfilment
    owner_from: 2025-01-01
    project: project:instant-payouts
    project_from: 2025-01-01
    depends_on:
      - {id: system:rate-limiter, from: 2025-01-01}`;
  const c = structuredEvidence(yaml, "catalog");
  assert.equal(c.title, "Billing");
  assert.deepEqual(c.rows, [["Owner", "Fulfilment · since 1 Jan 2025"], ["Tier", "2"], ["Project", "Instant Payouts"], ["Depends on", "Rate Limiter"]]);
  assert.ok(!JSON.stringify(c).includes("team:"));
});

test("an empty dependency list adds no row", () => {
  const c = structuredEvidence(`- id: system:aurora\n  name: "Aurora"\n  owner: team:infra\n  owner_from: 2025-01-01\n  depends_on: []`, "catalog");
  assert.deepEqual(c.rows, [["Owner", "Infra · since 1 Jan 2025"]]);
});

test("a roster row becomes name · role · since date, without the id or the yes/no column", () => {
  const c = structuredEvidence("| Bob Lindqvist | person:bob-lindqvist | lead | yes | 2025-01-01 |", "roster");
  assert.equal(c.line, "Bob Lindqvist · lead · since 1 Jan 2025");
});

test("prose is left as it is", () => {
  assert.equal(structuredEvidence("Platform owns Ledger.", "wiki"), null);
});
