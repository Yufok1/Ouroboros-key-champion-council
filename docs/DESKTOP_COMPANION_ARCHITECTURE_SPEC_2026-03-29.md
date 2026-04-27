# Desktop Companion Architecture Spec

Status: Draft
Date: 2026-03-29
Scope: Interactive 3D agent companion as desktop-native delivery form for character products

## Purpose

Define the architecture for shipping Champion Council character products as desktop companions — 3D
agents that live on the user's desktop, track their workflow context, react to their interactions,
and offer themselves as contextual utilities.

This is a new delivery form, not a new product class. The same character product that mounts into a
browser theater environment should mount into a desktop shell. Same GLB, same manifest, same command
surface, same animation contract.

## Core Concept

The desktop IS an environment. Window title bars are support surfaces. The taskbar is ground. Screen
edges are walls. The cursor is an interactive entity. App windows are landmarks. The agent perceives
this environment and navigates it the same way it perceives and navigates a 3D theater scene — through
a perception surface, a command surface, and a mount contract.

## Two Product Orientations

### Orientation A: Environment-Primary

The 3D environment is the main visible product. The agent is an actor/performer within it.

```
[Environment Product] + [Character Product(mounted)] = Interactive Scene
```

This is the existing theater model. A living diorama, terrarium, workshop, storefront. The user sees a
scene. The agent inhabits it. The environment is the resource.

Delivery: full-window application, embedded widget, or browser panel.

### Orientation B: Agent-Primary

The 3D character IS the primary interface. Everything else is summoned around it.

```
[Character Product] -> summons -> [Environment fragments as needed]
```

The agent sits on the desktop. It IS the chat interface. It can summon objects, tools, and environment
fragments around itself reactively. At minimum: a character on the taskbar. At maximum: pulling in a
full environment scene.

Delivery: desktop overlay application with system tray.

Both orientations ship the same character product. The runtime host differs.

## Desktop Shell

### Recommended Stack

Electron + Three.js for the initial implementation.

Rationale:
- Transparent window + WebGL is proven in Electron (shipped examples, npm packages)
- Click-through solved via setIgnoreMouseEvents(true, { forward: true }) + dynamic hit-testing
- Tauri has open bugs with transparent WebGL (context loss, click-through still a feature request)
- Binary size (150-200MB) is acceptable for a desktop companion

### Core Window Properties

- Transparent frameless window (transparent: true, frame: false)
- Always on top (screen-saver level)
- WebGL renderer with alpha channel (premultipliedAlpha: false, clearColor 0x000000 alpha 0)
- Click-through on transparent pixels, interactive on character pixels
- Multi-monitor aware

### System Tray

- Tray icon with context menu
- Chat popover (text input, conversation history)
- Quick actions (mute, dismiss, summon, settings)
- Permission controls

## Desktop Perception Surface

The agent perceives the desktop as an environment. This is the analog to the theater perception
surface (FOV/LOS/visible/occluded) but for the desktop context.

### Perception Inputs

```js
desktop_perception: {
    // Active window
    foreground_window: {
        handle: Number,
        title: String,
        app_name: String,         // 'chrome', 'code', 'explorer', etc.
        app_class: String,        // 'browser', 'editor', 'terminal', 'media', 'game', 'unknown'
        rect: { x, y, w, h },
        state: String             // 'normal', 'maximized', 'minimized'
    },

    // All visible windows (polled every 200-500ms)
    visible_windows: [{
        handle, title, app_name, app_class, rect, state, z_order
    }],

    // Cursor state
    cursor: {
        screen_x: Number,
        screen_y: Number,
        velocity: { vx, vy },     // pixels/second
        over_window: String,       // handle of window under cursor
        idle_seconds: Number,
        click_rate: Number         // clicks per minute (rolling 30s window)
    },

    // User activity classification
    user_state: String,            // 'active', 'typing', 'browsing', 'idle', 'away'
    interaction_tempo: String,     // 'frantic', 'steady', 'slow', 'idle'

    // Screen geometry
    screen_bounds: [{ x, y, w, h, primary: Boolean }],
    taskbar: { edge, x, y, w, h },

    // Events (recent, rolling buffer)
    recent_events: [{
        type: String,              // 'window_open', 'window_close', 'window_focus',
                                   // 'window_move', 'window_resize', 'app_launch',
                                   // 'click', 'idle_start', 'idle_end'
        timestamp: Number,
        data: Object
    }]
}
```

### Permission Tiers

All desktop awareness is opt-in. User grants levels:

- **Level 0: None** — Pure desktop pet. Animation only. No awareness.
- **Level 1: Window awareness** — Agent sees window positions, names, lifecycle. Reacts physically.
- **Level 2: App awareness** — Agent identifies apps, classifies context, adapts behavior.
- **Level 3: Content awareness** — Agent can read screen content (accessibility APIs or OCR). Offers
  substantive help.
- **Level 4: Action capability** — Agent can open apps, type, browse, manage files on behalf of user.

Default: Level 1. User escalates explicitly.

## Desktop Reaction System

How the agent reacts to perceived desktop events.

### Physical Navigation

The agent physically traverses the desktop in response to context changes:

- Window opens -> agent jumps/swings to the new window
- Window closes -> agent falls to next surface below or retreats to taskbar
- Window moves -> agent rides along or jumps off
- Window focus changes -> agent relocates to active window
- User goes idle -> agent finds a resting spot and idles

### Contextual Animation Selection

The agent's animation state responds to desktop context:

- Browser opens -> curious/interested posture
- IDE opens -> focused/studious posture
- Media plays -> relaxed/watching posture
- Game launches -> excited/cheering, then retreats to not block
- Terminal opens -> attentive/ready posture
- User typing fast -> agent stays quiet, small idle animations
- User idle -> agent explores, does ambient animations, stretches

### Contextual Assistance

Based on app context and permission level, the agent can:

- Browser: offer to search, summarize page, find related resources
- IDE: offer code help, explain errors, suggest fixes
- Terminal: offer command help, explain output
- File explorer: offer to organize, find, or process files
- Email/chat: offer to draft responses, summarize threads
- Calendar: remind about events, suggest schedule optimization
- General: answer questions, take notes, set reminders

### Non-Intrusive Presence Rule

The agent follows the user's focus but never blocks it.

Rules:
1. Position on window edges, margins, taskbar — adjacent to action, not on top
2. Never cover text the user is reading or writing
3. Retreat during flow state (sustained fast typing, rapid window switching)
4. Quiet down when user dismisses or mutes
5. Only proactively offer help at natural breakpoints (window switch, idle transition)
6. Speech bubbles disappear after timeout, don't accumulate
7. No sound unless user opts in to voice

## Desktop Physics

### Surface Model

Desktop surfaces map to the same concepts as environment surfaces:

| Desktop Element | Environment Analog | Physics Role |
|---|---|---|
| Taskbar | Ground plane / support surface | Primary walkable surface |
| Window title bars | Platforms | Secondary walkable surfaces |
| Window edges | Ledges | Grabbable/hangable |
| Screen edges | Walls | Boundary blockers |
| Cursor | Interactive entity | Grappable target, follow target |
| App icons (taskbar) | Landmarks | Navigation references |

### Physics Model

Simple 2.5D constraint solving against rectangles:

- Character: circle/capsule collider with gravity
- Window rects: static platform bodies (updated on poll)
- Gravity pulls character down
- Window top edges = walkable ground
- Screen edges = walls
- Taskbar = primary ground plane

### Cursor Interaction Modes

- **Follow:** Agent walks/runs toward cursor at a distance
- **Flee:** Agent runs away from cursor (comedic/personality-dependent)
- **Grapple:** Agent attaches a line to cursor, swings based on cursor velocity
- **Ride:** Agent attaches to cursor, moves with it
- **Interact:** Agent reacts to clicks (jumps, ducks, celebrates)
- **Ignore:** Agent does its own thing regardless of cursor

### Grapple/Swing System (Spider-Man Example)

1. Agent fires projectile toward cursor position
2. Rope constraint connects agent to cursor anchor point
3. Cursor moves -> rope origin moves -> pendulum physics applies
4. Agent swings based on cursor velocity and direction
5. At apex or on user click -> agent releases, travels on inertia arc
6. Agent lands on nearest surface (window edge, taskbar, screen border)
7. Cycle repeats

Physics parameters (tunable per character product):
- rope_length: max grapple distance
- swing_damping: how quickly energy dissipates
- launch_boost: extra velocity on release
- gravity: fall speed
- landing_snap_distance: how close to a surface to snap onto it

## Character Renderer Adaptation

The theater Three.js renderer adapts for desktop with these changes:

| Theater | Desktop |
|---|---|
| Orbit camera | Fixed orthographic or tight perspective |
| Environment lighting + HDR | Simplified: 1 directional + ambient |
| Visible ground plane | Transparent shadow catcher |
| Full-scale scene | Character fills ~100-200px |
| All LODs | Lowest LOD only, <20k triangles |
| Full post-processing | Minimal or none (alpha channel issues) |

What transfers directly from static/main.js:
- GLB/VRM loading pipeline
- AnimationMixer + clip resolver (v133b)
- Rig detection + joint mapping (v133a)
- animation_surface state tracking (v133b.1)
- All 7 animation command handlers
- Character command surface (26 verbs)

## Communication Relay

The 3D character IS the communication interface.

### Input Channels

- System tray chat (text)
- Voice input (ASR — modality already GREEN)
- Click/gesture on character (context menu, quick actions)
- Drag character to target (move to window, inspect object)

### Output Channels

- Speech bubble (text overlay positioned near character)
- Voice output (TTS — modality already GREEN)
- Gesture/animation (nod, shake head, point, shrug, celebrate)
- Facial expression (morph targets or jaw bone for lip sync)
- Desktop action (open app, type, navigate — Level 4 only)

### Character-as-Interface Principle

The character's animation state communicates agent state:

- Thinking -> pacing, hand on chin, looking up
- Working -> typing, focused posture, tools in hand
- Waiting -> idle, looking around, small ambient animations
- Error -> confused gesture, scratching head
- Success -> celebration, thumbs up
- Listening -> attentive posture, leaning forward

## Environment Summoning

The agent can summon environment fragments around itself.

### Level 1: Object Summoning

Agent places individual 3D objects on the desktop. A book, a tool, a prop, a sign. These come from
the existing asset library (4,771+ CC0 GLBs). Objects sit on the taskbar or float near the character.

### Level 2: Scene Context

Agent creates a localized environment around itself. A small desk, a workshop corner, a garden patch.
This is a partial environment mount — a few objects composed around the character's position.

### Level 3: Full Environment Transition

The character walks through a summoned portal. The transparent overlay expands into a full-window scene.
The desktop companion transitions into theater mode — Orientation B sliding into Orientation A. When the
user dismisses, the scene collapses back to desktop companion mode.

## Packaging

A desktop companion character product ships as:

```
character-companion-package/
    app/                          # Electron shell
        main.js                   # Main process
        renderer/                 # Three.js renderer
        physics/                  # Desktop physics
        perception/               # Desktop perception surface
        tray/                     # System tray + chat
    character/                    # Character product
        model.glb                 # Primary asset
        manifest.json             # Product manifest
        clips/                    # Animation clips (if external)
        thumbnail.png             # Preview
    environments/                 # Optional environment products
        default_context.json      # Default summoning catalog
    config/
        permissions.json          # Default permission tier
        personality.json          # Reaction mappings, behavior weights
        physics.json              # Grapple params, gravity, surfaces
    installer/                    # Platform installer
```

This maps onto the three shipping modes:

- **Capsule-Free:** Static desktop pet. Animated character, no AI brain. Click to trigger animations.
  Like Desktop Mate but with open character products.
- **Capsule-Optional:** Desktop pet + optional AI connection. Character comes alive when connected to
  a provider (local model, cloud API, capsule).
- **Capsule-Required:** Full agent companion. Character has memory, tools, workflows, desktop
  perception, contextual assistance.

## Win32 API Surface

### Required APIs (Windows)

```
user32.dll:
    EnumWindows              — list visible windows
    GetWindowRect            — window bounding rectangle
    GetForegroundWindow      — active window handle
    GetWindowText            — window title text
    GetClassName             — window class (for app identification)
    GetCursorPos             — global cursor position
    SetWinEventHook          — subscribe to window lifecycle events
        EVENT_SYSTEM_FOREGROUND    — window focus change
        EVENT_OBJECT_CREATE        — window created
        EVENT_OBJECT_DESTROY       — window destroyed
        EVENT_OBJECT_LOCATIONCHANGE — window moved/resized

kernel32.dll:
    QueryFullProcessImageName — get exe path from process (for app name)

shell32.dll:
    SHAppBarMessage          — taskbar position and size
```

### Access Method

From Electron main process via ffi-napi or a native Node addon.

From Tauri (future): native Rust via windows crate — cleaner, more performant.

## Relationship to Existing Architecture

| Existing Concept | Desktop Analog |
|---|---|
| Environment product | Desktop surface (windows, taskbar, screen) |
| Support surfaces | Window title bars, taskbar |
| Blockers | Screen edges |
| Landmarks | App icons, pinned windows |
| Utility objects | Desktop apps (IDE grants code tools, browser grants search) |
| Perception surface | Desktop perception surface |
| Mount contract | Desktop shell mounts character product |
| animation_surface | Same — character animation state |
| command_surface | Same — 26 character commands |
| env_control | Desktop control (app launch, file ops, typing) |

## Implementation Sequencing

Do not interrupt the current v133 lane. The animation system and command surface being built now IS the
foundation the desktop companion needs.

### Phase 1: Current Lane (v133-v136)

Complete in order:
1. v133b.1 upstream validation (current)
2. v133b.2 queue/interrupt (reactions critical for desktop — agent reacts to events)
3. v133c blend tree (smooth locomotion critical — character walks along taskbar)
4. v133d proxy lane (static models as desktop decorations)
5. v135 attachment (character holds summoned objects)
6. v136 export pipeline (character product packaging)

### Phase 2: Desktop Foundation

7. Electron shell + transparent window + Three.js character renderer
8. Desktop physics (window collision, gravity, surface detection)
9. System tray + chat popover + speech bubble overlay
10. Desktop perception surface Level 1 (window positions, lifecycle events)

### Phase 3: Desktop Intelligence

11. Desktop perception surface Level 2 (app classification, context adaptation)
12. Cursor interaction modes (follow, grapple, flee, ride)
13. Contextual animation selection (app-aware behavior)
14. Environment summoning Level 1 (object placement)

### Phase 4: Desktop Agent

15. Desktop perception surface Level 3-4 (content awareness, action capability)
16. Voice relay (ASR/TTS through character)
17. Environment summoning Level 2-3 (scene context, full theater transition)
18. Grapple/swing physics (Spider-Man mode)
19. Passive entertainment scene sequencer

### Phase 5: Desktop Products

20. Desktop companion product packaging
21. Character personality/reaction authoring tools
22. Desktop companion marketplace integration
23. Multi-character desktop presence (multiple companions)

## Competitive Positioning

| Feature | Desktop Mate | Razer AVA | Nvidia R2X | Champion Council |
|---|---|---|---|---|
| 3D character on desktop | Yes | Hologram | Overlay | Yes |
| Desktop physics | Yes | No | No | Yes (planned) |
| AI agent brain | No | Yes | Yes | Yes |
| Desktop context awareness | No | Partial | Screen reading | Full perception surface |
| Reactive context-following | No | No | No | Yes (planned) |
| Open character ecosystem | No (DLC only) | No | Planned open source | Yes |
| Environment summoning | No | No | No | Yes (planned) |
| Provider-agnostic | N/A | Grok/Gemini/ChatGPT | GPT-4o/Grok | Any (local/cloud/capsule) |
| Character portability | No | No | No | GLB/VRM (cross-engine) |

## Non-Goals For First Pass

- Mobile/tablet companion (desktop first)
- VR/AR companion
- Multi-user shared desktop presence
- Game engine integration of desktop companion (separate from character product portability)
- Full screen capture / OCR at Level 3 (defer until Level 1-2 proven)
- Autonomous desktop actions at Level 4 (defer until trust model proven)
