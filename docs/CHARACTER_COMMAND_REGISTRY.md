# Character Command Registry

Status: Draft
Date: 2026-03-25
Scope: Buyer-facing command surface for one character product

## Purpose

Define the stable external verbs for an individual character product.

These commands are the buyer vocabulary. They are not raw MCP tools.

## Design Rules

1. Commands are character-first.
2. Commands are stable even if implementation bindings change.
3. Queries and actions are separated clearly.
4. Internal tools, workflows, and FelixBag layouts remain implementation details.
5. Group verbs are an additive extension later.

## Command Classes

- `query` — read state, no side effects
- `action` — changes character behavior or state
- `memory` — interacts with bounded character memory lanes
- `config` — reads or updates supported configuration

## Canonical Commands

| Command | Class | Summary | Typical Request | Typical Response |
|---|---|---|---|---|
| `character.info` | query | Static product and embodiment metadata | `{}` | identity, embodiment, asset summary |
| `character.status` | query | Live runtime state | `{}` | enabled, position, facing, behavior, activity |
| `character.spawn` | action | Activate character presence | optional spawn target | spawn result, active state |
| `character.despawn` | action | Deactivate character presence | `{}` | active state, reason |
| `character.move_to` | action | Move to a target point or named marker | target position or marker id | accepted, route summary |
| `character.look_at` | action | Face a target point or object | target ref | accepted, facing target |
| `character.follow` | action | Follow a target object or anchor | target ref, distance | accepted, follow state |
| `character.stop` | action | Stop current directed action | optional mode | accepted, behavior reset |
| `character.set_goal` | action | Set a higher-level goal or task | goal id, params | accepted, goal summary |
| `character.speak` | action | Emit text or trigger speech behavior | text, channel | accepted, utterance id |
| `character.inspect` | action | Inspect a target object or location | target ref | accepted, inspection state |
| `character.memory_read` | memory | Read bounded memory namespace | namespace, key | value, found |
| `character.memory_write` | memory | Write bounded memory namespace | namespace, key, value | written, timestamp |
| `character.config_get` | config | Read supported config values | keys optional | config payload |
| `character.config_set` | config | Update supported config values | config patch | applied values, warnings |

## Command Payload Contracts

### Shared Response Envelope

All commands should return a stable envelope:

```json
{
  "ok": true,
  "command": "character.status",
  "character_id": "sapper_alpha",
  "timestamp": "2026-03-25T00:00:00Z",
  "result": {},
  "warnings": []
}
```

### `character.move_to`

Request:

```json
{
  "target": { "x": 10, "y": 20, "z": 0 },
  "mode": "goto"
}
```

Response result:

```json
{
  "accepted": true,
  "behavior": "goto",
  "target": { "x": 10, "y": 20, "z": 0 }
}
```

### `character.set_goal`

Request:

```json
{
  "goal_id": "inspect_anchor",
  "params": {
    "target_id": "crate_07"
  }
}
```

Response result:

```json
{
  "accepted": true,
  "goal_id": "inspect_anchor"
}
```

### `character.memory_read`

Request:

```json
{
  "namespace": "character/sapper_alpha/memory",
  "key": "last_patrol_marker"
}
```

Response result:

```json
{
  "found": true,
  "value": "marker_north_gate"
}
```

### `character.config_set`

Request:

```json
{
  "patch": {
    "follow_distance": 3.0,
    "speech_verbosity": "brief"
  }
}
```

Response result:

```json
{
  "applied": {
    "follow_distance": 3.0,
    "speech_verbosity": "brief"
  }
}
```

## Implementation Binding Model

Each command should bind to one of:

- a workflow id
- a runtime command handler
- a future HTTP facade route

Bindings should remain internal to the product package.

Example:

- `character.move_to` -> `workflow:character_move_to`
- `character.status` -> `handler:character_status`

## Commands To Exclude From The Buyer Surface

Do not expose:

- raw `bag_*` tools
- raw `file_*` tools
- raw `workflow_*` tools
- council slot management
- provider token configuration
- destructive runtime admin surfaces

These may still exist internally behind bounded workflows and handlers.

## Future Extension

Group commands are a separate extension layer:

- `group.status`
- `group.broadcast`
- `group.move`
- `group.regroup`

They are not part of the base character registry.
