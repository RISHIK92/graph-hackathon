"use client";

import { Copy, KeyRound } from "lucide-react";
import { useState } from "react";
import { ACCOUNTS, send } from "@/lib/api";
import tools from "@/lib/mcp-tools.json";
import { useStore } from "@/lib/store";
import { Button, Chip, Modal } from "./ui";

// Run from the repository folder: the server reads FalkorDB settings from its .env, and BRAIN_MCP_ACTOR is
// the person its writes are recorded as (without it, the write tools refuse).
const COMMAND = 'claude mcp add nodus -e BRAIN_MCP_ACTOR=person:priya-raman -- "$(pwd)/.venv/bin/python" -m mcp_server.server';
const CONFIG = JSON.stringify({
  mcpServers: {
    "nodus": {
      command: "/path/to/graphs-hackathon-dev/.venv/bin/python",
      args: ["-m", "mcp_server.server"],
      env: { BRAIN_MCP_ACTOR: "person:priya-raman" },
    },
  },
}, null, 2);
const EXAMPLE = "I'm changing ledger-service. Who owns it, who should review the change, and what depends on it?";
const KIND = { read: "Read", write: "Write (recorded as the actor)", risky: "Confirm and undo (stdio only)" } as const;

/** "Use from your coding agent" (M16): the MCP command, a client config, the registered tools and a prompt. */
export function CodingAgentHelp({ onClose }: { onClose: () => void }) {
  const { toast, account } = useStore();
  const [key, setKey] = useState("");
  // item 24: with accounts on, a per-workspace key points the server at this workspace's graph
  const withKey = (cmd: string) => (key ? cmd.replace("-e BRAIN_MCP_ACTOR", `-e NODUS_API_KEY=${key} -e BRAIN_MCP_ACTOR`) : cmd);
  const copy = (text: string) => navigator.clipboard.writeText(text).then(
    () => toast({ tone: "success", title: "Copied" }), () => toast({ tone: "error", title: "Couldn't copy" }));
  return (
    <Modal title="Use from your coding agent" size="lg" onClose={onClose} footer={<Button variant="primary" onClick={onClose}>Done</Button>}>
      <div className="stack-4">
        <div className="t-small text-2">The same graph tools, over MCP. Every result is an evidence pack with its citations, exactly as this app shows it. Run this from the repository folder:</div>
        <div className="stack">
          <pre className="code">{withKey(COMMAND)}</pre>
          <Button size="sm" icon={Copy} onClick={() => copy(withKey(COMMAND))}>Copy command</Button>
        </div>
        {ACCOUNTS && account && (
          <div className="stack">
            <span className="t-label">This workspace&apos;s key</span>
            <div className="t-small text-2">{key ? "Shown once. It's in the command above; creating a new key revokes this one." : "Create a key so the server reads your workspace instead of the shared demo company."}</div>
            <div><Button size="sm" icon={KeyRound} onClick={async () => {
              try { setKey((await send<{ key: string }>("POST", "/auth/keys", {})).key); }
              catch (e) { toast({ tone: "error", title: "Couldn't create a key", body: String((e as Error).message || e) }); }
            }}>{key ? "Create a new key" : "Create an API key"}</Button></div>
          </div>
        )}
        <details className="details">
          <summary>Other MCP clients (JSON config)</summary>
          <div className="details-body stack"><pre className="code">{CONFIG}</pre><Button size="sm" icon={Copy} onClick={() => copy(CONFIG)}>Copy config</Button></div>
        </details>
        <div className="stack">
          <span className="t-label">Try asking it</span>
          <div className="t-small">“{EXAMPLE}”</div>
        </div>
        <div className="stack">
          <span className="t-label">Tools ({tools.length})</span>
          {tools.map((t) => (
            <div key={t.name} className="row-wrap t-small">
              <code>{t.name}</code><Chip tone="neutral">{KIND[t.kind as keyof typeof KIND] || t.kind}</Chip><span className="text-2">{t.description}</span>
            </div>
          ))}
        </div>
      </div>
    </Modal>
  );
}
