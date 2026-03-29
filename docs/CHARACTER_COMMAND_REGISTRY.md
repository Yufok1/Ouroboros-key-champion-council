# Character Command Registry

Status: Draft, updated for v133b.1 runtime checkpoint
Date: 2026-03-29
Scope: Buyer-facing command surface for one character product

## Purpose

Define the stable external verbs for an individual character product.

These commands are the buyer vocabulary. They are not raw MCP tools.

## Current State

As of 2026-03-29, the movement/presence lane is implemented in the runtime host surface, and the
animation lane is working in the browser/runtime through the mounted owned-surface control path.

Current implementation truth in `static/main.js`:

- derived animation contract exists
- clip inventory and resolver exist
- retargeted clip inventory exists
- mounted runtime refresh/export exists
- mounted runtime exports a live `animation_surface`
- mounted owned-surface control can drive `play_clip`, `set_loop`, `set_speed`, `stop_clip`, `get_animation_state`, and `play_reaction`
- public direct `env_control(character_*)` validation still stops short of the animation verbs upstream

This registry therefore distinguishes:

- `live` commands already available through the mounted runtime host surface
- `live via owned surface` commands already working for mounted runtime orchestration
- `upstream pending` commands whose remaining gap is validated ingress rather than playback/runtime logic
- `v133b.2` commands that depend on queue/interrupt semantics

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

| Command | Class | Status | Summary | Typical Request | Typical Response |
|---|---|---|---|---|---|
| `character.info` | query | planned | Static product and embodiment metadata | `{}` | identity, embodiment, asset summary |
| `character.status` | query | partial | Live runtime state | `{}` | enabled, position, facing, behavior, activity |
| `character.spawn` | action | alias of `character.mount` later | Activate character presence | optional spawn target | spawn result, active state |
| `character.despawn` | action | alias of `character.unmount` later | Deactivate character presence | `{}` | active state, reason |
| `character.mount` | action | live | Activate mounted character runtime | optional behavior | mounted state |
| `character.unmount` | action | live | Deactivate mounted character runtime | `{}` | mounted state |
| `character.focus` | action | live | Focus theater on mounted character runtime | `{}` | accepted, focus state |
| `character.set_model` | action | live | Swap mounted character asset | asset ref | accepted, asset ref |
| `character.move_to` | action | live | Move to a target point or named marker | target position or marker id | accepted, route summary |
| `character.look_at` | action | live | Face a target point or object | target ref | accepted, facing target |
| `character.follow` | action | planned | Follow a target object or anchor | target ref, distance | accepted, follow state |
| `character.stop` | action | live | Stop current directed action | optional mode | accepted, behavior reset |
| `character.set_goal` | action | planned | Set a higher-level goal or task | goal id, params | accepted, goal summary |
| `character.speak` | action | planned | Emit text or trigger speech behavior | text, channel | accepted, utterance id |
| `character.inspect` | action | planned | Inspect a target object or location | target ref | accepted, inspection state |
| `character.play_clip` | action | live via owned surface, upstream pending | Resolve and play one clip using the existing resolver/mixer lane | clip id or raw name | accepted, active clip |
| `character.queue_clips` | action | partial, semantics deferred to v133b.2 | Queue multiple clips for runtime playback | queue or clip list | accepted, queue summary |
| `character.stop_clip` | action | live via owned surface, upstream pending | Stop clip override and return control to runtime behavior | optional reason | accepted, override cleared |
| `character.set_loop` | action | live via owned surface, upstream pending | Set loop mode for the active clip | `repeat` or `once` | accepted, loop mode |
| `character.set_speed` | action | live via owned surface, upstream pending | Set playback speed for the active clip | numeric speed | accepted, speed |
| `character.get_animation_state` | query | live via owned surface, upstream pending | Read mounted animation state surface | `{}` | active clip, paused, queue, source |
| `character.play_reaction` | action | live via owned surface, upstream pending | Request a high-level reaction intent resolved to clips | reaction id | accepted, reaction + clip |
| `character.memory_read` | memory | planned | Read bounded memory namespace | namespace, key | value, found |
| `character.memory_write` | memory | planned | Write bounded memory namespace | namespace, key, value | written, timestamp |
| `character.config_get` | config | planned | Read supported config values | keys optional | config payload |
| `character.config_set` | config | planned | Update supported config values | config patch | applied values, warnings |

## Naming Alignment

Canonical buyer-facing names stay dotted:

- `character.mount`
- `character.play_clip`
- `character.get_animation_state`

The current browser/runtime host transport uses underscored command ids:

- `character_mount`
- `character_play_clip`
- `character_get_animation_state`

Implementation rule:

- docs, specs, buyers, and product manifests use dotted names
- runtime host handlers may keep underscored ids internally
- the runtime must provide a stable alias map so these two forms do not drift
- until upstream direct validation is aligned, agent orchestration may enter through mounted owned surfaces that delegate into the same underlying `character_*` handlers

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

### `character.play_clip`

Request:

```json
{
  "clip": "idle",
  "source_preference": "contract",
  "loop": "repeat",
  "speed": 1
}
```

Response result:

```json
{
  "accepted": true,
  "active_clip": "idle",
  "active_clip_source": "retargeted",
  "loop_mode": "repeat",
  "speed": 1
}
```

### `character.get_animation_state`

Request:

```json
{}
```

Response result:

```json
{
  "available": true,
  "active_clip": "idle",
  "active_clip_raw": "Idle",
  "active_clip_source": "native",
  "paused": false,
  "loop_mode": "repeat",
  "speed": 1,
  "override_active": true,
  "queue": [],
  "queue_cursor": 0,
  "contract_clip_count": 12,
  "native_clip_count": 32,
  "updated_ts": 1774790000000
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
- `character.play_clip` -> `handler:character_play_clip`
- `character.get_animation_state` -> `handler:character_get_animation_state`

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
