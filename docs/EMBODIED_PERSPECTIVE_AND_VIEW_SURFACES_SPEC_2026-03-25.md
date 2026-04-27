# Embodied Perspective and Operator/Agent View Surfaces

Status: Draft
Date: 2026-03-25
Scope: How agents perceive their world, how operators observe agents, and the view surface architecture connecting them

## Purpose

Define the complete view surface architecture for Champion Council:

1. What the agent sees (embodied perspective)
2. What the operator sees (observation and control surfaces)
3. How these views connect without making visual perspective the sole cognition channel

## Core Framing

An embodied agent operates through multiple parallel surfaces, not one visual feed.

### Agent Cognition Surfaces (ranked by implementation priority)

1. **Structured world state** — env_read mirror, scene objects, spatial metrics
2. **Perception state** — FOV/LOS computed visible/occluded objects, support, focus key
3. **Command surface** — character.* verbs, tool calls, workflow execution
4. **Memory** — bounded namespaces via character.memory_read/write
5. **Activity history** — recent actions, movements, observations (cascade_record)
6. **Tool grants** — capabilities from accessed utility objects
7. **Visual perspective** — the spatial view from the embodied position (supplemental, not primary)

Visual perspective is surface #7 — important but not dominant. The agent does not need to "see a screenshot" to know what's around it. The perception state (surface #2) already provides that symbolically.

### When Visual Perspective Becomes Primary

Visual perspective gains importance when:
- the agent needs spatial reasoning about geometry (is there a gap? how wide?)
- the operator wants the agent to respond to visual features (color, shape, detail)
- image-model vision is enabled as an optional future layer

For now, symbolic perception is sufficient. Image-model vision is explicitly a non-goal for v1.

## Agent View Architecture

### What the Agent Has Access To (already implemented or specified)

| Surface | Source | Status |
|---|---|---|
| Position and facing | inhabitant runtime state | IMPLEMENTED |
| Grounded + support_key | grounding system | IMPLEMENTED |
| Visible objects | _envBuildInhabitantPerceptionState FOV/LOS | IMPLEMENTED |
| Occluded objects | perception blocker checks | IMPLEMENTED |
| Focus key | nearest salient visible object | IMPLEMENTED |
| Last seen memory | bounded last_seen map with timestamps | IMPLEMENTED |
| FOV/sight range | configurable per-inhabitant | IMPLEMENTED |
| World state snapshot | env_read mirror | IMPLEMENTED |
| Movement commands | character.move_to, character.follow, etc. | SPECIFIED |
| Memory read/write | character.memory_read/write | SPECIFIED |
| Tool grants | via utility object access | PLANNED |

### What the Agent Does NOT Have Yet

| Surface | Purpose | When |
|---|---|---|
| Constraint identification | "there's a river between A and B" | With nav hardening |
| Nearby object detail | structured data about objects within reach | Post-Gate 4 |
| Interaction capability | character.interact with utility objects | Post-Gate 5 |
| Image-based vision | actual rendered viewport as model input | Future optional |

### Agent Action Loop

```
1. Receive command (from operator, from another agent, or from own goal)
2. Read perception state (what do I see?)
3. Read world state (what's around me structured?)
4. Evaluate command against perceived constraints
5. If action possible: execute (move, interact, speak, fabricate)
6. If action blocked: report constraint, attempt alternative, or request help
7. Update memory with result
8. Return to idle/awaiting next command
```

This loop does not require image rendering. It uses structured surfaces.

## Operator View Architecture

### What the Operator Can See (already implemented or planned)

| View | Source | Status |
|---|---|---|
| Overview camera | theater orbit view | IMPLEMENTED |
| Follow camera | inhabitant camera binding | IMPLEMENTED |
| Cockpit perception readout | perception state in cockpit UI | IMPLEMENTED |
| Live mirror state | shared state publish | IMPLEMENTED |
| Inhabitant status (Summon/Dismiss/Follow) | cockpit controls | IMPLEMENTED |
| Perception detail (visible/occluded counts) | cockpit line 31693 | IMPLEMENTED |
| Debug tab | auto-populated by MCP tool calls | IMPLEMENTED |
| HTML panel for object interaction | _envHtmlPanelState system | IMPLEMENTED |
| Control unit command surface | workstation HTML template | PLANNED |
| FOV cone visualization | 3D debug overlay | PLANNED (Gate 4) |
| Workbench mode (single-object zoom) | camera mode switch | PLANNED |

### Operator Experience Hierarchy

1. **Overview** — see the whole scene, all objects, inhabitant position
2. **Follow** — camera tracks the inhabitant, shows their movement
3. **Control unit** — click a workstation to open command interface for the agent
4. **Inspector** — click any object to see its properties and state
5. **Workbench** — zoom into one object for detailed inspection/editing
6. **Debug** — raw MCP tool call history, perception internals

The operator moves between these views fluidly. They are not separate modes — they are layers.

## View Surface Connections

### Operator → Agent

```
Operator clicks "Move to East Pad" in control unit
  → character.move_to { target: 'prop::val-pad-east' }
  → inhabitant movement system activates
  → agent moves, perception updates
  → control unit panel refreshes with new position
```

### Agent → Operator

```
Agent perception detects new visible object
  → perception state updates visible_object_keys
  → mirror publishes updated state
  → cockpit readout shows new visible count
  → control unit panel (if open) shows updated perception
```

### Agent → World

```
Agent interacts with forge utility object
  → character.interact { target: 'prop::forge-01' }
  → proximity check passes
  → agent gains granted_tools: ['workflow_execute']
  → agent can now run crafting workflow
  → workflow produces new scene object via env_spawn
  → new object appears in theater
  → perception updates to include new object
```

## Spectator/Debug Surfaces (Gate 4 deliverable)

### Perception Overlay

Extend the existing cockpit perception readout (line 31693) with:

- visible objects listed by key and distance
- occluded objects listed by key and blocker
- current focus key highlighted
- support surface name and kind

### FOV Cone Debug Visualization

Optional 3D overlay showing the agent's field of view:

- semi-transparent cone mesh attached to inhabitant position
- rotates with facing direction
- colored by state: green = clear, orange = partially occluded
- toggle via cockpit control or env_control command

### Movement Path Debug

When the inhabitant is moving:

- show a line from current position to target
- show waypoints if patrol/multi-target
- highlight blocked paths in red

## Implementation Priority

1. **Gate 4 (now):** Finish perception overlay + optional FOV debug vis
2. **Gate 5:** HTTP facade — operator can command agent via HTTP, not just cockpit
3. **Post-Gate 5:** Control unit HTML templates, utility object interaction flow
4. **Post-Gate 5:** Workbench camera mode
5. **Future:** Image-model vision as optional perception layer
6. **Future:** Multi-agent camera wall for multiple inhabitant monitoring

## Non-Goals

- Real-time rendered first-person view as agent input (future optional)
- VR/AR operator view (not in scope)
- Replacing symbolic perception with image-only perception
- Making visual perspective required for any agent action
