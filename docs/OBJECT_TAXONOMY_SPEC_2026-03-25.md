# Object Taxonomy for Agent-Operable Worlds

Status: Draft
Date: 2026-03-25
Scope: Complete classification of objects agents and operators interact with in Champion Council environments

## Purpose

Map every object category that must exist for agents to operate completely within their environments.

This taxonomy serves three audiences:

1. **Runtime** — the environment system needs to know what each object is for, how it behaves, and who can use it
2. **Agents** — embodied agents need to understand what objects are around them, what they can do with them, and what constraints they impose
3. **Operators** — humans authoring or inspecting a scene need to understand the role of every object at a glance

## Design Rules

1. Every object in a scene must have a classifiable role.
2. An object may serve multiple roles (a bridge is both support and transport).
3. Classification drives runtime behavior: blocking, visibility, interaction, capability granting.
4. The taxonomy is additive to the existing object contract — it extends `semantics.role` and blocker profiles, not a parallel system.
5. Agent-operable objects are not just scenery with a flag. They have interaction contracts.

## Object Categories

### 1. Support Surfaces

Objects the inhabitant can stand or walk on.

Existing contract: `data.support_surface = true`, `semantics.role = floor|platform|path|transition`

Examples: ground tiles, platforms, decks, walkways, bridges, stairs, ramps

Runtime behavior:
- grounding target for inhabitant placement
- navigation graph nodes
- support_key reported in inhabitant state

### 2. Solid Blockers

Objects that block passage and line of sight.

Existing contract: blocker profile `traversal_blocking = true`, `sight_blocking = true`

Examples: walls, cliffs, barriers, boulders, buildings, locked doors

Runtime behavior:
- excluded from navigation paths
- occlude LOS for perception
- cannot be walked through

### 3. Portals / Thresholds

Openings, transitions, and connective geometry.

Existing contract: `semantics.role = portal|gate|archway`

Examples: doorways, gates, arches, tunnels, cave mouths, zone transitions

Runtime behavior:
- traversable but semantically significant
- may trigger zone transitions or state changes
- perception treats as pass-through (not occluding)

### 4. Landmarks / References

Distant or notable objects that serve as orientation anchors.

Existing contract: `semantics.role = landmark|reference`

Examples: towers, mountains, beacons, flags, signs, monuments

Runtime behavior:
- visible from distance for perception/navigation reference
- not interactive by default
- may be perception focus targets

### 5. Utility Objects

Objects that grant or expose capabilities when accessed, equipped, or operated by an agent.

**This is the new category.** Not just scenery — these are capability surfaces.

Examples:
- a forge grants crafting capability
- a telescope grants extended perception range
- an anchor point grants a mooring capability
- a chest grants storage access
- a signal fire grants broadcast capability

Schema addition:
```
utility: {
    capability_grant: 'craft|perceive|store|broadcast|compute|navigate|...',
    interaction_mode: 'equip|operate|access|consume',
    requires_proximity: true,
    activation_command: 'character.interact',
    granted_tools: ['tool_name_1', 'tool_name_2'],
    cooldown_seconds: 0,
    consumable: false
}
```

Runtime behavior:
- when agent is within proximity and activates, capabilities are granted
- granted capabilities may be temporary (while operating) or persistent (while equipped)
- capability grant maps onto the agent's available tool set
- mirror reports which utility objects the agent has activated

### 6. Workstations / Control Units

Interactive nodes that expose HTML interfaces and command surfaces in-theater.

**This builds on the existing HTML panel system** (`_envHtmlPanelState`, `panelMode`, object `html` field).

Examples:
- a command terminal shows agent status and accepts typed commands
- a map table shows the agent's perception state on a spatial display
- a crafting bench shows available recipes and inventory
- a comms station shows message history and allows broadcast

Schema addition:
```
workstation: {
    surface_type: 'terminal|display|workbench|console|custom',
    html_template: 'command_terminal',
    panel_mode: 'sidebar|fullscreen|overlay',
    bound_agent_key: 'npc::resident_primary',
    input_commands: ['character.move_to', 'character.speak', 'character.set_goal'],
    output_streams: ['perception', 'activity', 'memory'],
    persistent: true
}
```

Runtime behavior:
- clicking opens the HTML panel with the workstation's interface
- input commands are routed through the character command surface
- output streams show live agent state
- workstation may be bound to a specific agent or available to any

Relationship to MCP workstation tools:
- `workstation_bind`, `workstation_list`, `workstation_unbind` exist in the MCP server orientation
- These are not yet wired into `server.py`
- The theater-side HTML panel system is the rendering surface
- MCP workstation tools become the binding/lifecycle surface

### 7. Fabrication / Production Objects

Objects agents use to produce new objects or resources.

Examples:
- a forge produces equipment
- a lumber mill produces materials
- a printing press produces documents
- a garden plot produces food

Schema addition:
```
fabrication: {
    product_type: 'equipment|material|document|consumable|structure',
    recipe_source: 'built_in|workflow|agent_generated',
    requires_materials: true,
    output_placement: 'inventory|adjacent|specified',
    production_time_seconds: 0
}
```

Runtime behavior:
- agent activates fabrication object with materials/intent
- production may be instant or time-based
- output is a new scene object or an inventory entry
- production history tracked in agent memory

### 8. Containers / Storage

Objects that hold other objects or resources.

Examples: chests, barrels, shelves, bags, warehouses, vaults

Schema addition:
```
container: {
    capacity: 20,
    item_filter: null,
    access_policy: 'open|locked|agent_only|faction_only',
    contents: []
}
```

Runtime behavior:
- agents can deposit or withdraw items
- contents are part of scene state
- access may be restricted

### 9. Transport / Traversal Objects

Objects that move agents or goods between locations.

Examples: boats, carts, elevators, ziplines, teleporters, bridges (when movable)

Schema addition:
```
transport: {
    mode: 'vehicle|elevator|teleporter|conveyance',
    capacity: 1,
    route: null,
    requires_operation: true,
    speed: 5.0
}
```

Runtime behavior:
- agent boards/operates transport
- transport moves agent along route or to destination
- may require agent operation (rowing) or be automatic (elevator)

### 10. Tools / Instruments

Portable objects agents can equip or use directly.

Examples: weapons, measuring tools, keys, communication devices, maps

Schema addition:
```
instrument: {
    equip_slot: 'hand_r|hand_l|back|belt|head',
    capability_grant: 'attack|measure|unlock|communicate|navigate',
    consumable: false,
    durability: null
}
```

Runtime behavior:
- equipping changes agent capability set
- uses the existing attachment point system from CHARACTER_EMBODIMENT_SPEC
- instrument state tracked on the agent

### 11. Documents / Interface Objects

Objects that present information surfaces or interactive interfaces to agents.

**These are utility objects specifically for information and computation.**

Examples:
- an IDE terminal grants coding/file-ops capability
- a map display shows environment layout
- a message board shows community state
- a library grants knowledge lookup
- a browser terminal grants web access

Schema addition:
```
interface_object: {
    surface_type: 'ide|browser|map|library|message_board|custom',
    html_template: 'ide_terminal',
    panel_mode: 'fullscreen',
    capability_grant: 'code|browse|read|write|search',
    granted_tools: ['file_read', 'file_write', 'file_edit', 'file_search'],
    persistent: true
}
```

Runtime behavior:
- agent accesses the interface object
- HTML panel opens with the appropriate interface
- agent gains access to granted tools while using the interface
- this is the concrete mechanism for "Batman's utility belt" — the object IS the capability

### 12. Passive Props / Decoration

Objects with no interactive function. Visual only.

Existing contract: blocker profile `decorative`, `semantics.role = decal|marker|vegetation_patch`

Examples: flowers, flags (non-landmark), debris, ambient particles, visual effects

Runtime behavior:
- visible but not interactive
- not blocking, not support
- may be soft (traversable)

## Cross-Category Rules

1. **An object may belong to multiple categories.** A bridge is support + transport. A forge is workstation + fabrication. A locked door is blocker + portal (when unlocked).

2. **Category drives runtime behavior, not kind alone.** Two `prop` objects may have completely different interaction contracts based on their category membership.

3. **Capability granting is explicit.** No object silently grants tools. The `utility`, `workstation`, or `instrument` block must declare what is granted and how.

4. **Category is expressed through existing contract fields.** This taxonomy doesn't add a new top-level `category` field that conflicts with the existing one. It extends `semantics`, `data`, and adds optional typed blocks (`utility`, `workstation`, `fabrication`, `container`, `transport`, `instrument`, `interface_object`).

## Relationship to Existing Systems

| Existing System | How This Taxonomy Relates |
|---|---|
| Blocker taxonomy (NPC_PERCEPTION_AND_GROUNDING_SPEC) | Categories 1-4 map directly to support/solid/portal/decorative |
| Object contract (_envNormalizeSceneObjectRecord) | New optional blocks extend the existing record |
| HTML panel system (_envHtmlPanelState) | Workstations and interface objects use this as their rendering surface |
| Character embodiment (CHARACTER_EMBODIMENT_SPEC) | Character embodiments are not part of the scene taxonomy; mounted character runtimes operate through this taxonomy |
| MCP workstation tools | Binding/lifecycle for category 6 |
| Character commands (CHARACTER_COMMAND_REGISTRY) | `character.interact`, `character.inspect` are the primary verbs for object interaction |

## Implementation Sequencing

This taxonomy does not need to be implemented all at once.

- **Already exists:** Categories 1-4 and 12 (support, blockers, portals, landmarks, props)
- **Gate 4 hardening:** Tightens categories 1-2 (support + blockers)
- **Next design lane:** Categories 5-11 (utility, workstation, fabrication, container, transport, instrument, interface)
- **Character composition lane:** separate embodiment/product lane, not a scene taxonomy category

## Non-Goals

- This taxonomy is not a crafting system design document
- This taxonomy does not define specific recipes, items, or resources
- This taxonomy does not specify inventory management rules
- Those are facility-level concerns that sit on top of this classification
