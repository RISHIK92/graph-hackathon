"use client";

import { Copy } from "lucide-react";
import tools from "@/lib/mcp-tools.json";
import { useStore } from "@/lib/store";
import { Button, Chip, Modal } from "./ui";

// Run from the repository folder: the server reads FalkorDB settings from its .env, and BRAIN_MCP_ACTOR is
// the person its writes are recorded as (without it, the write tools refuse).
const COMMAND = 'claude mcp add company-brain -e BRAIN_MCP_ACTOR=person:priya-raman -- "$(pwd)/.venv/bin/python" -m mcp_server.server';
const CONFIG = JSON.stringify({
  mcpServers: {
    "company-brain": {
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
  const { toast } = useStore();
  const copy = (text: string) => navigator.clipboard.writeText(text).then(
    () => toast({ tone: "success", title: "Copied" }), () => toast({ tone: "error", title: "Couldn't copy" }));
  return (
    <Modal title="Use from your coding agent" size="lg" onClose={onClose} footer={<Button variant="primary" onClick={onClose}>Done</Button>}>
      <div className="stack-4">
        <div className="t-small text-2">The same graph tools, over MCP. Every result is an evidence pack with its citations, exactly as this app shows it. Run this from the repository folder:</div>
        <div className="stack">
          <pre className="code">{COMMAND}</pre>
          <Button size="sm" icon={Copy} onClick={() => copy(COMMAND)}>Copy command</Button>
        </div>
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
