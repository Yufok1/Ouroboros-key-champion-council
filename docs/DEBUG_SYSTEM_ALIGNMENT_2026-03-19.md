# Debug System Alignment

Date: 2026-03-19
Status: current local runtime alignment note

## Purpose

This document reconciles the current debug system behavior across:

- server-side activity mirroring
- the browser Debug tab
- loop-debug for `agent_chat`
- environment/operator workflows

It exists because older FelixBag notes are directionally correct, but some of them are now stale relative to the current frontend/runtime behavior.

## Current Truth

Champion Council has two cooperating debug layers.

### 1. Global Debug Mirror

This is the default substrate for ordinary tool and environment debugging.

What it does:

- every ordinary tool call passes through `_broadcast_activity(...)`
- those entries are mirrored into `observe(signal_type='agent_debug', ...)`
- a debug-shaped SSE row is also injected back into the browser activity stream

Where it lives:

- [server.py](/F:/End-Game/champion_councl/server.py)
- `server.py::_broadcast_activity(...)`
- `server.py::_mirror_activity_to_observe(...)`

Use it for:

- `env_control`
- `env_read`
- `env_mutate`
- workflow/debugging of ordinary runtime actions
- browser/runtime environment diagnosis

### 2. Agent Loop Debug

This is the stronger explicit debug path for `agent_chat` loops.

What it does:

- enables loop-debug behavior on browser agent tabs
- records debug step snapshots and probe/tool stats
- surfaces remote `agent_chat_sessions` into the Debug tab session layer

Where it lives:

- [static/main.js](/F:/End-Game/champion_councl/static/main.js)
- `toggleAchatDebugMode()`
- `_recordLoopDebugStep(...)`
- `_refreshDebugRemoteSessions(...)`

Use it for:

- multi-step investigations
- adversarial or intermittent failures
- loop-debug analysis of autonomous slot sessions

## Important Alignment Notes

These points are true in the current runtime and should be treated as canonical.

- The Debug tab is a filtered browser surface, not the sole source of truth.
- The always-on debug substrate is the global mirror plus `feed`.
- Remote `agent_chat_sessions` are now polled into the Debug tab session layer.
- `trace_root_causes(...)` is useful only when you understand that free-form descriptions mutate the default causal graph.
- `cascade_record` is explicit structured logging and tape capture. It is not the same thing as the automatic mirror.

## Default Operating Procedure

For environment/runtime debugging, use this order:

1. Trigger the real action.
2. Read environment truth:
   - `env_read(query='live')`
   - `env_read(query='shared_state')`
   - `env_read(query='contracts')`
   - `env_read(query='habitat_objects')`
3. Read the debug substrate:
   - `feed(n=...)`
   - `env_read(query='debug_state')`
4. Use the Debug tab as a filtered browser inspection surface.
5. Compare the debug substrate, mirrored environment state, and visible browser behavior.

This keeps debugging on the existing runtime path instead of inventing a parallel control plane.

## New Local Readback Surface

The environment proxy now exposes:

- `env_read(query='debug_state')`

This summarizes the existing debug substrate without creating a new one. It reports:

- mirror configuration
- debug row counts
- mirrored-tool row counts
- loop-debug row counts
- recent compact debug rows
- a small guidance block describing the intended operating model

Use this when you need a fast answer to:

- is the mirror alive?
- are debug rows being generated?
- is this recent traffic ordinary mirrored tool work or loop-debug traffic?

## Known Gaps

These are still misaligned:

- `get_help(topic='debug')` is not exposed by the capsule help registry right now.
- Older FelixBag docs still describe remote `agent_chat` session visibility as if it were absent or incomplete.
- The Debug tab remains discoverability-poor if an agent only consults `get_help(...)`.

## Recommendation For Future Agents

If you are doing environment, theater, or runtime debugging:

- do not reason from the Debug tab alone
- do not assume `trace_root_causes` is safe on arbitrary prose
- use `feed + env_read + visible browser result` as the debug triad
- use `env_read(query='debug_state')` when you need a compact state-of-debug summary
