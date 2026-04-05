# Environment Help System Spec 2026-04-04

Status: proposed
Scope: environment/browser/runtime command discoverability for commands that are absent or under-described in `get_help(...)`

## Problem

The current help system is strong at the capsule/MCP tool layer and weak at the browser environment command layer.

Current truth:

- `get_help(...)` is an excellent index for the capsule-side tool registry.
- `env_control` is documented only as a broad dispatch surface.
- many environment behaviors live authoritatively in `static/main.js`, not in the capsule help registry
- some commands are proxied through `env_control`
- some commands are browser/surface only
- some behaviors are UI-local and should never be presented as if they are MCP-reachable

This creates three recurring failures:

1. an agent knows `env_control` exists but not how a specific command really behaves
2. a command appears reachable when it is actually UI-local only
3. a command exists, but important gotchas are invisible without a source dive

The `workbench_apply_motion_preset` seam is the current example:

- the command exists
- the command is proxied
- the command loads a timeline and applies frame `0`
- it does **not** auto-play motion
- this is not discoverable from current `get_help(...)`

## Goal

Build an articulate, queryable environment help system that explains:

- what environment commands exist
- which transport reaches them
- what mode/surface they require
- what they actually do
- how to use them safely
- how to verify the result
- what common failure modes and misconceptions apply

This system should help Codex-class agents, browser operators, and future local workflows without creating a second truth plane.

## Non-Goals

- replacing `get_help(...)`
- duplicating every environment concept doc inside one giant registry blob
- inventing a parallel environment runtime
- pretending UI-local commands are workflow/MCP-safe

## Recommendation

Use a hybrid design:

1. a dedicated environment help registry as the canonical command reference
2. a dedicated `env_help` tool for direct lookup
3. a cross-link from `get_help('environment')` and `get_help('env_help')`
4. companion playbooks for multi-step operator flows

This is better than either extreme:

- better than forcing all browser/runtime detail into the existing capsule `get_help(...)`
- better than leaving environment knowledge trapped in specs, source, and memory notes

## Why Not Use Skills As The Primary Vehicle

Skills are the wrong primary abstraction for this job.

Why:

- skills are Codex-side behavior extensions
- environment help needs to describe runtime/browser commands authoritatively
- the target audience includes agents and operators using the environment control lane itself
- environment command truth is transport-aware and mode-aware; skills are not the right canonical store for that

Skills may still help with coding or maintenance workflows, but the authoritative environment reference should be a structured registry plus playbooks.

## Recommended Placement

### Canonical Structured Registry

Create a machine-readable registry in the repo, for example:

- `static/data/help/environment_command_registry.json`

Why here:

- environment/browser command truth lives near the runtime, not the capsule
- the browser can read it
- the server can expose it
- docs can be generated from it later

### Dedicated Tool

Add a new tool:

- `env_help`

Purpose:

- query the environment command registry directly
- return structured reference for commands, categories, playbooks, aliases, and search hits

This should be the environment-side equivalent of targeted `get_help(...)`, not a replacement for `get_help(...)`.

### Cross-Link From `get_help`

Keep `get_help(...)` as the top-level umbrella and route users toward environment help:

- `get_help('environment')` should explicitly point to `env_help`
- `get_help('env_help')` should explain how to query the environment registry
- optional later convenience: `get_help('env:workbench_apply_motion_preset')` delegates to `env_help`

### Companion Human Docs

Keep structured command truth separate from multi-step operational docs.

Use companion docs such as:

- `docs/ENVIRONMENT_COMMAND_REFERENCE.md` (generated or semi-generated)
- `docs/ENVIRONMENT_OPERATOR_PLAYBOOKS.md`

The registry explains commands.
The playbooks explain flows.

## Information Model

Each environment command entry should answer seven questions:

1. what is it called
2. how do I reach it
3. when is it valid
4. what does it actually do
5. what does `target_id` mean
6. how do I verify it
7. what will confuse me if I am not warned

Suggested schema:

```json
{
  "command": "workbench_apply_motion_preset",
  "title": "Apply Builder Motion Preset",
  "category": "builder_motion",
  "status": "live",
  "transport": {
    "mcp": true,
    "env_control": true,
    "browser_surface": true,
    "ui_local_only": false
  },
  "availability": {
    "theater_modes": ["character"],
    "visual_modes": ["builder_subject"],
    "requires_focus_kind": ["character_runtime"],
    "requires_builder_subject": true
  },
  "target_contract": {
    "shape": "string_or_json",
    "examples": [
      "step_left",
      "{\"preset\":\"step_left\"}"
    ]
  },
  "summary": "Load a preset builder timeline and apply the pose at cursor 0.",
  "effects": [
    "sets builder timeline",
    "sets cursor to 0",
    "applies frame-0 pose"
  ],
  "verification": [
    "capture_time_strip",
    "workbench_set_timeline_cursor",
    "capture_probe",
    "env_read(query='shared_state')"
  ],
  "gotchas": [
    "does not auto-play motion",
    "builder-only"
  ],
  "related_commands": [
    "workbench_set_timeline_cursor",
    "capture_time_strip"
  ],
  "source_anchors": [
    {
      "file": "static/main.js",
      "symbol": "_envWorkbenchApplyMotionPreset"
    }
  ]
}
```

## Required Distinctions

The registry must explicitly distinguish:

### 1. Proxied Runtime Commands

These are reachable through `env_control`.

Examples:

- `camera_*`
- `capture_*`
- `character_*`
- `workbench_*`

### 2. Browser/Surface Commands

These are reachable through the environment/browser layer but may be owned-surface specific.

Examples:

- `surface_action`
- `surface_submit`
- `surface_input`

### 3. UI-Local Commands

These exist in the browser but are **not** MCP-safe or workflow-safe.

These must be labeled clearly to prevent false assumptions.

Example:

- turntable-style local toggles that do not travel through the server proxy

This distinction is critical. It prevents the system from lying.

## Command Families

The initial family split should match real runtime usage, not abstract taxonomy purity.

Recommended first families:

- `focus_navigation`
- `camera_pose`
- `capture_observer`
- `surface_bridge`
- `theater_profile_recipe`
- `character_runtime`
- `builder_structure`
- `builder_pose_timeline`
- `builder_motion`
- `diagnostic_observation`

These are close to the current `env_control` reality and easier for agents to navigate than one giant alphabetical list.

## Registry Content Layers

The system should expose three levels of help:

### Level 1: Command Reference

One command at a time.

Use when:

- an agent already knows the command name
- a browser operator needs exact payload syntax
- a failure needs gotcha-level clarification

### Level 2: Family Overview

A category page for a command family.

Use when:

- an agent knows the domain but not the exact verb
- a workflow needs to find the right command among similar commands

### Level 3: Playbooks

Task-oriented multi-command guides.

Use when:

- the user wants an outcome, not a command
- the operator needs a proven sequence

Initial playbooks should include:

- mounted asset inspection
- builder subject creation
- motion preset preview and scrub
- scaffold/load validation
- observer capture corroboration
- focus/camera recovery

## Tool Contract Recommendation

Suggested `env_help` inputs:

- `topic`
- `search`
- `category`
- `mode`

Suggested query patterns:

- `env_help(topic='index')`
- `env_help(topic='workbench_apply_motion_preset')`
- `env_help(category='builder_motion')`
- `env_help(search='support floor planted feet')`
- `env_help(topic='playbook:mounted_asset_inspection')`

Suggested outputs:

- structured JSON
- same style as `get_help(...)`
- include `purpose`, `parameters`, `effects`, `verification`, `gotchas`, `related_commands`, `source_anchors`

## UX / Discoverability

The best system is not enough if nobody finds it.

Recommended discoverability surfaces:

1. `get_help('environment')` cross-link
2. `get_help('env_help')` short how-to
3. optional Environment theater affordance:
   - `OPEN ENV HELP`
4. optional inspector/cockpit help chip:
   - `Help`
   - resolves contextually by current surface/focus/mode

The help entrypoint should be obvious but not noisy.

## Generation Strategy

Do **not** try to parse every handler body as the primary source of help text.

Better approach:

1. seed a structured registry manually for the highest-value commands
2. use source anchors for traceability
3. later add lightweight generation/validation against:
   - `_ENV_CONTROL_PROXY_COMMANDS` in `server.py`
   - mounted `command_surface.host_commands`
   - category completeness checks

This keeps prose curated while still catching drift.

## Rollout Plan

### Phase 1: Canonical Registry Skeleton

- create `environment_command_registry.json`
- seed top families:
  - camera
  - capture
  - character
  - builder/workbench
  - surface bridge
- include transport and mode distinctions from day one

### Phase 2: `env_help` Tool

- add `env_help`
- expose exact command, family, index, and search modes
- add cross-links from `get_help`

### Phase 3: Playbooks

- create operator playbooks for common flows
- reference command entries instead of duplicating command truth

### Phase 4: UI Discoverability

- add Environment-side help affordance
- optional context-sensitive help opening by focus/mode

### Phase 5: Drift Detection

- compare registry entries against proxied command set and known browser surfaces
- fail loudly when a proxied command has no help entry

## Best Placement Decision

Direct answer:

- this should **not** be “just another env branch”
- it **should** become a dedicated environment help subsystem
- the best core is **another tool**: `env_help`
- the best storage is **structured registry data**, not skills
- the best companions are **playbooks/cookbooks**, not monolithic prose alone
- `get_help(...)` should remain the umbrella and cross-link to it

## Why This Matters

The environment system is now large enough that “source + memory + luck” is not a stable operating model.

Without a dedicated environment help layer:

- agents waste time rediscovering command behavior
- browser-only vs proxied vs UI-local distinctions stay muddy
- users think a command is broken when it is only staged differently
- new environment features become less usable as the system grows

With a dedicated environment help layer:

- the browser/runtime command surface becomes legible
- agents can reason more accurately
- workflows can target the right transport
- the environment system becomes teachable instead of tribal
