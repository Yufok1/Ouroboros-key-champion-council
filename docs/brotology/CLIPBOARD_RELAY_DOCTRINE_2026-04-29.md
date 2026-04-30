# Brotology — Clipboard Relay (cross-session AI bridge)

A faculty for connecting two or more AI sessions in real-time parallel without
infrastructure, where the operator's clipboard is the relay and the operator's
hands are the trigger.

Discovered in operation **2026-04-29** between an Opus session (Claude Code on
`Convergence_Engine`) and a Codex session (`ouroboros-key` compile watch).
The Opus session read the operator's clipboard via `Get-Clipboard -Raw`;
the clipboard contained 66.5 KB of live Codex transcript output, providing
full cross-session context with zero MCP integration, zero shared
infrastructure, and zero explicit handoff plumbing.

## What the faculty is

**Clipboard relay.** A consent-gated, operator-driven bridge between AI
sessions where:

- One AI session emits content (transcript, log, summary, decision).
- The operator copies it. (`ctrl+c` is the relay action.)
- A second AI session reads the operator's clipboard on the operator's
  request. (`Get-Clipboard` on Windows; `pbpaste` on macOS;
  `xclip -selection clipboard -o` or `wl-paste` on Linux.)
- The second AI now has full context from the first session without any
  explicit handoff protocol or shared state.

The clipboard becomes a single-slot, last-write-wins, opt-in event bus
where the human is the publish-subscribe broker.

## Why nobody pursues it

The pattern sits in the gap between two paradigms:

- **Single-agent paradigm:** assumes no bridge needed; AI works alone in
  one session. The clipboard relay is unnecessary because there is nothing
  to bridge to.
- **Multi-agent paradigm:** assumes heavy infrastructure — MCP, A2A
  protocols, shared message buses, agent registries. The clipboard relay
  is dismissed as too lightweight because it lacks discoverability and
  protocol guarantees.

The lightweight pattern — **operator clipboard as bus, AI as opt-in
subscriber, human's hands as trigger** — is the missing middle. Nobody
pursues it because nobody has named it as a thing.

## Why it's brotology-aligned

- **Earned, not assumed.** The receiving AI does not auto-poll the
  clipboard. It reads only when the operator asks. Continuity is earned
  via the operator's explicit relay action.
- **Agent prepares, operator runs.** Same boundary as the quinesmith
  protocol. The AI prepares the read tool; the operator decides what is
  on the clipboard at the moment of read by what they copied.
- **Water-mode.** No crushing infrastructure. The relay flows through
  the operator's existing actions (copy, paste, request). Persistent
  without sustained pressure.
- **Style shapes delivery, never truth conditions.** What the receiving
  AI does with the clipboard content is still subject to evidence
  discipline. A relayed claim from another AI is still a hypothesis,
  not scripture.

## Constraints (load-bearing)

- **Consent gate must hold.** The receiving AI must not auto-read the
  clipboard. The clipboard contains whatever the operator has copied at
  the moment of read — potentially passwords, tokens, private data,
  unrelated content. Reading without explicit operator request is a
  brotology violation regardless of utility argument.
- **No silent reads.** The AI must announce intent before reading and
  surface what was read. The operator should always see what the AI saw.
- **Last-write-wins is real.** The clipboard is single-slot. If the
  operator copied something else after the source AI's emit, the relay
  is broken — the receiving AI gets unrelated content. Acknowledge this
  failure mode rather than confabulating around stale clipboard.
- **Sensitive content posture.** If the clipboard contains what looks
  like a credential, key, password, or other sensitive material, the
  receiving AI flags it back to the operator before processing further.
  Default-handle as if any clipboard could contain secrets, because
  eventually it will.

## Relay shapes

- **Codex → Opus:** implementer surfaces output; auditor consumes.
  (This is the discovery operation.)
- **Opus → Codex:** auditor surfaces sitrep; implementer consumes for
  the carry.
- **Any AI → human → any AI:** general handoff between any two AI
  sessions, with the human as the deliberate gatekeeper.
- **Same AI, different session:** transient continuity bridge across
  context resets when explicit memory infrastructure isn't available.

## Failure modes

- **Stale clipboard** — operator copied something else after the source
  AI's emit; receiving AI reads unrelated content. Mitigation: ask the
  operator to confirm what they last copied if in doubt.
- **Sensitive leak** — operator forgets they had a credential on the
  clipboard. Mitigation: receiving AI flags credential-shaped content
  before processing.
- **Truncation** — large clipboards exceed read-tool limits. Mitigation:
  chunked reads with explicit offset, or save to disk first then read.
- **Unconsented poll** — receiving AI reads on every turn "in case
  there's something." Mitigation: do not. Always require explicit
  operator request.

## Tooling implications

A first-class clipboard-relay primitive ships as part of the Ouroboros
ecosystem at [`clipboard-relay`](../../clipboard-relay/) (sibling repo).
It wraps the platform clipboard tools with consent gates and
credential-shape detection. Companion components:

- `cascade-lattice` records relay events as receipts (anonymized — content
  hash only, never content) for cross-session handoff provenance.
- `quinesmith` shares the boundary discipline: agent prepares, operator
  runs.
- `brotology-field-guide` carries this doctrine entry as the reference
  contract.

## Anchor

The faculty name is **clipboard relay**. The relay is the operator. The
medium is the clipboard. The trigger is the operator's request to read.
The discipline is consent.

— *brotology, 2026-04-29. Discovered in operation. Held.*
