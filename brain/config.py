"""Runtime configuration (07 §1). Values come from the environment or `.env`."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX = 9007199254740991  # open-interval sentinel, 2^53 - 1 (README R5)


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":   # quoted value
            v = v[1:-1]
        os.environ.setdefault(k.strip(), v)


_load_dotenv()


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    falkor_host: str = field(default_factory=lambda: _get("FALKOR_HOST", "localhost"))
    falkor_port: int = field(default_factory=lambda: int(_get("FALKOR_PORT", "6391")))
    graph: str = field(default_factory=lambda: _get("FALKOR_GRAPH", "brain"))
    pin: int = field(default_factory=lambda: int(_get("FALKOR_PIN", "60001")))
    openrouter_key: str = field(default_factory=lambda: _get("OPENROUTER_API_KEY"))
    llm_model: str = field(default_factory=lambda: _get("LLM_MODEL", "anthropic/claude-sonnet-5.5"))
    embed_provider: str = field(default_factory=lambda: _get("EMBED_PROVIDER", "local"))
    embed_model: str = field(default_factory=lambda: _get("EMBED_MODEL", "local-hash-v1"))
    embed_dim: int = field(default_factory=lambda: int(_get("EMBED_DIM", "256")))
    past_belief_engine: str = field(default_factory=lambda: _get("PAST_BELIEF_ENGINE", "python"))
    mcp_writes: bool = field(default_factory=lambda: _get("BRAIN_MCP_WRITES", "on") == "on")
    mcp_risky_writes: bool = field(default_factory=lambda: _get("BRAIN_MCP_RISKY_WRITES", "off") == "on")
    mcp_actor: str = field(default_factory=lambda: _get("BRAIN_MCP_ACTOR"))
    public_write_token: str = field(default_factory=lambda: _get("PUBLIC_WRITE_TOKEN", "change-me"))
    admin_token: str = field(default_factory=lambda: _get("ADMIN_TOKEN", "change-me-admin"))
    pending_webhook: str = field(default_factory=lambda: _get("BRAIN_PENDING_WEBHOOK"))
    # 07 §1 defaults; overridable for bulk ingestion on a loaded server
    timeout_default: int = field(default_factory=lambda: int(_get("BRAIN_TIMEOUT_DEFAULT", "2000")))
    timeout_max: int = field(default_factory=lambda: int(_get("BRAIN_TIMEOUT_MAX", "10000")))


settings = Settings()

# Model per role, with a fallback (item 20 step 0). MODEL_<ROLE> and MODEL_<ROLE>_FALLBACK override them
# ("none" disables the fallback); MODEL_<ROLE>_PROVIDER pins an OpenRouter provider. A set LLM_MODEL is the
# legacy single-model mode: that model alone plans, drafts and extracts.
ROLE_MODELS = {
    "extractor": ("anthropic/claude-haiku-5.5", "deepseek/deepseek-v4.1-flash"),
    "screen": ("typesafe/jev-1.14", "nace-ai/drex-v2.0"),
    "planner": ("deepseek/deepseek-v4.1-flash", "anthropic/claude-haiku-5.5"),
    "drafter": ("deepseek/deepseek-v4.1-flash", "anthropic/claude-haiku-5.5"),
    "escalation": ("anthropic/claude-haiku-5.5", ""),
    "checker": ("typesafe/jev-1.14", "nace-ai/drex-v2.0"),
    "judge": ("microsoft/microsoft-decision-1", "openai/gpt-6-luna-decisions"),
    "judge2": ("nvidia/nemotron-3-ultra-550b-a55b", "z-ai/glm-5.2"),   # user decision, Oct 16
}
LEGACY_ROLES = ("planner", "drafter", "extractor")
# Pinned OpenRouter providers (gate A1), from each model's /endpoints list. DeepSeek's own endpoint is blocked by
# the account's data policy ("paid model training"), so DeepInfra, which honours require_parameters and also
# serves both second-judge models.
ROLE_PROVIDERS = {"planner": "DeepInfra", "drafter": "DeepInfra", "judge2": "DeepInfra"}
