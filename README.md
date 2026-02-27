---
title: Champion Council
emoji: "🐍"
colorFrom: purple
colorTo: blue
sdk: docker
pinned: false
license: mit
short_description: 'Local-first AI orchestration with 140+ MCP tools'
tags:
  - mcp
  - model-orchestration
  - ai-agent
  - workflow
  - local-ai
  - llm
  - multi-model
  - semantic-search
  - observability
  - vscode
app_port: 7860
---

# Champion Council - AI Model Orchestrator

Local-first AI orchestration platform. Run multi-model workflows, semantic memory, diagnostics, and capsule orchestration from one system.

## What Is This?

Champion Council is an AI model orchestration system built on the Ouroboros quine architecture — a self-contained, self-verifying, portable substrate for composing multiple AI models into deliberative councils.

### Core Capabilities

- **Multi-Slot Model Council** - Plug HuggingFace models into council slots. Run inference, debate, consensus, and chaining across up to 32 models simultaneously.
- **140+ MCP Tools** - Full Model Context Protocol tool surface. Works with any MCP client (Claude Code, Cursor, Windsurf, Kiro, etc.).
- **Workflow Engine** - 10 node types: tool, agent, input, output, fan_out, http, if, set, merge, web_search. DAGs with expression interpolation and conditional branching.
- **Semantic Memory (FelixBag)** - Local embedding store with search, catalog, induction, and export.
- **VS Code Extension Integrations** - Community and Nostr surfaces are part of the VS Code extension build, linked below.
- **Self-Verifying Quine** - Every capsule carries its own source, weights, merkle hash, and provenance chain.
- **Vast SSH Bootstrap** - Space runtime auto-creates `~/.ssh/id_rsa` (or loads `SSH_PRIVATE_KEY` / `SSH_PUBLIC_KEY`) for `vast_ready`, `vast_connect`, and remote GPU actions.
- **Vast Fleet Parity** - GPU Fleet surfaces use normalized Vast instance payloads and expose direct per-instance Vast Console links for active rentals.

### Install the VS Code Extension

[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/Ouroboros.champion-council?label=VS%20Code%20Marketplace&logo=visual-studio-code)](https://marketplace.visualstudio.com/items?itemName=Ouroboros.champion-council)

### Links

- [GitHub Repository](https://github.com/Yufok1/Ouroboros_extension)
- [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=Ouroboros.champion-council)

## License

MIT

