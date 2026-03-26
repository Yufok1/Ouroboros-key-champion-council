# Control Units and Utility Objects

Status: Draft
Date: 2026-03-25
Scope: How agents interact with objects that grant capabilities, and how operators interact with agents through in-theater control surfaces

## Purpose

Define two linked systems:

1. **Utility objects** — world objects that grant capabilities to agents when accessed
2. **Control units** — workstation objects that expose HTML interfaces for operators to command agents

These are not decorations. They are the mechanism by which agents gain tools and operators gain command surfaces.

## Design Principles

1. Capability is acquired, not ambient. An agent does not start with every tool — it gains tools by accessing objects.
2. The HTML panel system already exists. Control units use it, not replace it.
3. Utility objects map MCP tool grants onto in-world objects. The tools already exist. The objects are the spatial binding.
4. An operator commanding an agent through a control unit is the same as calling `character.*` verbs. The control unit is a UI surface for those commands.
5. An agent using a utility object is the same as an agent gaining access to specific MCP tools. The object is the spatial justification.
6. Control units and utility objects belong to environment products. Mounted character runtimes consume them.

## Existing Infrastructure

### HTML Panel System (already in main.js)

- `_envHtmlPanelState` (line 121) — tracks active HTML panel
- Objects can carry `html` content and `panelMode` (fullscreen/sidebar/overlay)
- `_envCloseHtmlPanel`, `_envSceneObjectHasHtml`, `_envSceneObjectPanelMode` — lifecycle
- Bridge state carries `objectKey`, `objectKind`, `objectId` — panel knows which object it belongs to

### Object Contract (already in main.js)

- `_envNormalizeSceneObjectRecord` — extensible, already carries `character`, `mechanics`, `data`, `appearance`
- `panelMode` already normalized on the record
- `html` field carries arbitrary HTML content

### MCP Workstation Tools (in capsule, not yet wired to server.py)

- `workstation_bind` — bind a workflow to a scene workstation
- `workstation_unbind` — remove binding
- `workstation_list` — list active workstation bindings
- `facility_create`, `facility_bind`, `facility_activate` — facility lifecycle

### Character Commands (already specified)

- `character.interact` — not yet defined in detail but listed as conceptual
- `character.inspect` — inspect a target object
- `character.set_goal` — set a higher-level objective

## Control Unit Spec

A control unit is a scene object with kind `workstation` or any kind with a `workstation` block. It opens an HTML panel that lets the operator command a bound agent.

### Minimal Control Unit Object

```js
{
    kind: 'workstation',
    id: 'cmd-terminal-01',
    label: 'Command Terminal',
    x: 55, y: 48,
    semantics: { role: 'workstation' },
    panelMode: 'sidebar',
    workstation: {
        surface_type: 'terminal',
        bound_agent_key: 'npc::resident_primary',
        input_commands: [
            'character.move_to',
            'character.look_at',
            'character.speak',
            'character.set_goal',
            'character.stop'
        ],
        output_streams: ['status', 'perception', 'activity']
    },
    html: '' // generated at runtime from workstation template
}
```

### What the Operator Sees

When an operator clicks a control unit in the theater:

1. HTML panel opens in the configured mode (sidebar/fullscreen/overlay)
2. Panel shows:
   - bound agent's current status (position, behavior, activity, grounded)
   - perception readout (visible objects, focus key, occluded count)
   - command input surface (buttons or form for each `input_commands` verb)
   - activity feed (recent actions, movement, observations)
3. Operator issues a command (e.g., "move to east pad")
4. Command routes through `character.move_to` → runtime → inhabitant movement
5. Panel updates with result

### What the Agent Sees

The agent does not "see" the control unit as a special object. The agent receives commands through the normal command surface. The control unit is an operator convenience, not an agent dependency.

However: the agent DOES know about the control unit as a perceived object. If the agent is near a control unit, perception reports it. The agent can be directed to approach and interact with one via `character.interact`.

### HTML Template System

Rather than hand-coding HTML per workstation, define templates:

```
workstation_templates: {
    terminal: {
        layout: 'status_panel + command_input + activity_feed',
        auto_refresh_ms: 1000,
        command_buttons: true
    },
    display: {
        layout: 'perception_map + visible_objects',
        auto_refresh_ms: 500,
        read_only: true
    },
    workbench: {
        layout: 'recipe_list + material_inventory + craft_button',
        auto_refresh_ms: 0,
        interactive: true
    }
}
```

Templates generate HTML dynamically using the same bridge state pattern the existing panel system already uses.

## Utility Object Spec

A utility object is any scene object with a `utility` block. It grants capabilities to agents when they interact with it.

### Core Concept

MCP tools already exist (166+ tools across 18 categories). An agent's available tool set can be expanded or constrained based on what utility objects they have accessed.

A forge object does not implement crafting. It grants access to workflow tools that implement crafting.
A telescope object does not implement vision. It extends the perception range parameter.
An IDE terminal does not implement coding. It grants access to file_read/file_write/file_edit tools.

### Minimal Utility Object

```js
{
    kind: 'prop',
    id: 'forge-01',
    label: 'Forge',
    x: 40, y: 55,
    semantics: { role: 'workstation', placement_intent: 'fabrication' },
    utility: {
        capability_grant: 'craft',
        interaction_mode: 'operate',
        requires_proximity: true,
        proximity_radius: 3.0,
        granted_tools: ['workflow_execute', 'bag_get', 'bag_put'],
        granted_workflows: ['craft_equipment'],
        activation_command: 'character.interact',
        deactivation: 'on_leave',
        consumable: false
    }
}
```

### Interaction Flow

1. Agent is directed to the utility object (via `character.move_to` or `character.set_goal`)
2. Agent arrives within `proximity_radius`
3. Agent or operator issues `character.interact` targeting the utility object
4. Runtime checks proximity and activates the utility grant
5. Agent's available tool set expands to include `granted_tools`
6. Agent can now execute those tools as part of its reasoning/action loop
7. When agent leaves proximity (if `deactivation: 'on_leave'`) or explicitly deactivates, tools are revoked

### Capability Categories

Mapping existing MCP tool categories to potential utility object types:

| Capability | Utility Object Example | Granted Tools |
|---|---|---|
| Craft/Fabricate | Forge, Workbench, Loom | workflow_execute, bag_put |
| Store/Retrieve | Chest, Shelf, Vault | bag_get, bag_put, bag_search |
| Communicate | Signal Fire, Comms Tower | broadcast, relay_send, chat |
| Compute/Code | IDE Terminal, Scribe Desk | file_read, file_write, file_edit |
| Observe/Perceive | Telescope, Watchtower | extended sight_range, observe |
| Navigate | Map Table, Compass | env_read, bag_search |
| Produce | Garden, Mill, Press | workflow_execute, env_spawn |
| Diagnose | Probe Station | diagnose_file, diagnose_directory |
| Research | Library, Archive | bag_search, bag_read_doc, web_search |

### Relationship to Agent Slots

When an agent is plugged to a council slot, it has baseline capabilities. Utility objects EXTEND those capabilities, they don't define them from scratch.

A council slot agent without any utility objects can still:
- move, perceive, speak, remember (character.* commands)
- reason and plan (its model capabilities)

A council slot agent WITH utility objects additionally can:
- craft, store, communicate, code, etc. (granted by objects)

This is the "Batman's utility belt" principle: the agent is capable, the objects extend capability into specific domains.

## Shipping Rule

Utility objects and control units are environment-side facilities.

That means:

- they can ship inside environment products without shipping a mounted character
- they can be consumed by mounted character runtimes later
- they can also expose external-facing interfaces for other agents or operators

If a control unit or utility object only exposes static/interface metadata:

- the capsule is not required

If it executes live workflows, grants live tools, or drives live runtime behavior:

- a runtime host is required

## Overlay Control Unit Mode

Control units do not need to be only diegetic world props.

They may also appear as:

- a non-invasive theater overlay
- an on-demand chat/control drawer
- a compact command console bound to one mounted character runtime

Rules:

- the overlay should be summonable and dismissible
- it should only appear when explicitly opened or when the operator pins it
- it should bind to a specific agent-bearing runtime target
- in the current architecture, that means a mounted character runtime
- a plain scene object or static workstation is not enough
- if no agent-bearing runtime target is present in the theater, no chat overlay should appear
- it should not permanently clutter the theater

This allows a product to ship both:

- diegetic interfaces such as mirrors, terminals, books, or pools
- practical operator-facing chat/control surfaces for direct interaction with a bound agent

## Agent Perspective Surface

### Embodied Perspective

The agent's visual perspective is the view from its NPC model's position and facing direction. This is already partially implemented:

- `_envBuildInhabitantPerceptionState` computes FOV cone from eye position
- `visible_object_keys`, `occluded_object_keys`, `visible_focus_key` are computed
- perception state is published to mirror

### What Embodied Perspective IS

- a spatial context for the agent's reasoning
- input to decision-making alongside tool results, memory, and commands
- the basis for spatial rationalization ("there's a river between me and point B")

### What Embodied Perspective IS NOT

- the only cognition channel
- a replacement for MCP tool calls
- a requirement for every agent action
- an image-model vision system (that's a future optional layer)

### Minimum Surfaces for Complete Agent Operation

An agent needs these surfaces to "operate completely" without visual perspective being the only channel:

1. **Perception state** (already exists) — what's visible, what's occluded, what's the focus
2. **Command surface** (already exists) — character.* verbs for movement, interaction, speech
3. **Memory** (already exists) — character.memory_read/write with bounded namespaces
4. **Tool grants** (new via utility objects) — expanded capability from accessed objects
5. **World state** (already exists via env_read) — structured snapshot of the scene
6. **Activity history** — what the agent has done recently (trackable via cascade_record)
7. **Spatial context** — position, facing, support, nearby objects (already in inhabitant state)

Visual perspective is surface #1. It is important. It is not sufficient alone.

## Theater Workbench Mode

### Concept

When working on a single model (NPC, creature, object), the entire theater scene becomes that one model at inspection scale. Like a modeling viewport where the object is the world.

### Implementation Path

This is a camera/scene mode, not a second renderer.

1. `env_control` command: `workbench_mode` with target object key
2. Runtime:
   - stores current scene camera state
   - hides all other scene objects (visibility toggle, not removal)
   - centers orbit target on the target object's center
   - adjusts camera near/far planes for close inspection (0.01 / 100)
   - scales orbit distance to object's bounding box
   - disables overview and follow modes while in workbench
3. Exit: `env_control` command: `exit_workbench`
   - restores camera state
   - restores object visibility
   - returns to previous mode

### What the Operator Can Do in Workbench Mode

- orbit around the model at any distance
- zoom into surface detail
- inspect individual mesh parts
- view attachment points and skeleton joints (future)
- edit materials/textures on the model (future, via aspectation)
- see the model's animation clips playing (existing mixer system)

### Relationship to Character Composition

When the compositional assembly system exists, workbench mode becomes the authoring surface:

- view the skeleton template
- snap body parts onto attachment points
- preview assembled model
- apply aspectation (skins, textures, markings)
- validate rig compliance

## Spatial Command Under Constraints

### How It Works

1. Operator issues `character.move_to` with target point B
2. Agent evaluates path from current position A to target B
3. If path is clear: agent moves directly
4. If path is blocked by constraint (river, wall, gap):
   - agent reports the constraint via perception state
   - if agent has fabrication/tool capability: may construct a solution (bridge, boat)
   - if agent lacks capability: reports failure with reason
   - if agent has alternative route: takes it

### Runtime Requirements

- Navigation already avoids solid blockers (Gate 4 work)
- Constraint reporting requires perception to identify the blocking object
- Solution construction requires:
  - fabrication utility object access (or granted tools)
  - workflow that produces a traversal object (env_spawn)
  - agent reasoning about the constraint (model capability, not runtime)

### What This Means Concretely

The runtime provides:
- path evaluation with blocker detection
- perception state showing what's between A and B
- tool grants from utility objects
- env_spawn for producing new objects

The AGENT provides:
- reasoning about what to do when blocked
- decision to fabricate, detour, or report failure
- this is model capability, not hard-coded behavior

The runtime does not contain "if river then build boat" logic. The runtime provides the surfaces for the agent to reach that conclusion itself.

## Implementation Sequencing

### Already Done (Gate 1-3)
- Object contract with extensible blocks
- HTML panel system
- Inhabitant perception and grounding
- Character commands specified
- Validation habitat

### Gate 4 (current)
- Blocker/nav hardening
- Command-target movement validation
- Spectator/debug perception surfaces

### Gate 5 (next)
- HTTP command facade over character.* verbs
- OpenAPI spec

### Post-Gate 5: Control Unit / Utility Object Lane
1. Add `utility` and `workstation` optional blocks to object normalization
2. Wire MCP workstation_bind/unbind/list into server.py
3. Build first control unit HTML template (terminal type)
4. Build first utility object interaction flow (proximity + tool grant)
5. Test: operator commands agent through control unit, agent gains tool from utility object

### Post-Gate 5: Workbench Mode
1. Add workbench_mode env_control command
2. Camera state save/restore
3. Object visibility toggling
4. Orbit target centering on bounding box

### Future: Character Composition
1. Body part catalog with socket compatibility
2. Assembly grammar per rig family
3. Aspectation for character surfaces (coquina extension)
4. Workbench mode as the authoring surface
5. Validation against rig family contracts

## Non-Goals Right Now

- Full crafting/recipe system
- Inventory management
- Combat through utility objects
- Multi-agent tool sharing
- Image-model vision
- Procedural mesh generation

These are facility-level concerns that sit on top of this foundation.
