# v101 Plan — Surface Wiring, Inspector Authoring & Character Pipeline

## Status: DRAFT — For Codex bounce-back review

## Research Basis
- 3-round gpt-5.4 review of v100 plan (13 findings, all resolved)
- Live MCP runtime verification of v100 demo objects
- Direct code read of inspector, agent sprite, asset loading, locomotion, edit/remove actions
- Transcript analysis of remaining gaps and NPC character requirements

---

## Context: What v100 Delivered

- `mechanics` block on object contract with normalization
- Inspector "Mechanics" section showing family/wind/reaction/LOD
- `vegetation_patch` kind with InstancedMesh + ShaderMaterial + DataTexture influence field
- Ring-based LOD for vegetation (near/mid/far InstancedMesh)
- TransformControls: click-to-select custom objects, G/R/S editing, drag-end persistence
- Raycaster filtering to custom-only objects
- Foliage wind overlay on hero objects
- Influence field stamping from moving agents
- Disposal + SW cache alignment + version bump to v100

## What's Still Missing (from v100 surfaces + character pipeline)

### Surfaces Not Yet Exposed
1. No UI to **create** scene objects — only MCP tool calls (env_spawn)
2. No inspector controls for **appearance** (asset_ref, material, geometry)
3. No inspector controls for **mechanics editing** (currently read-only display)
4. No **selection highlight** or active-object readout when TransformControls are active
5. "Edit" button (line 17980) only shows for panels/HTML objects, not all custom objects
6. Edit prefill (line 17598) doesn't include `appearance` or `mechanics` fields

### Character/NPC Pipeline Gaps
7. Agent sprites are **modality icons** (LLM/ASR/TTS/etc.), not character sprites
8. No character model swap via UI — runtime already supports per-object `appearance.asset_ref`, but no inspector or prefab UI exposes it
9. AnimationMixer clips are limited to walk/run/idle — no attack/talk/emote states
10. No NPC prefab schema (archetype, equipment, voice, behavior profile)
11. Asset browser exists (panel.html:10491, main.js:25905) but has no character-aware spawn or NPC prefab integration
12. No retargeting or rig-agnostic animation system
13. Only 9 GLB assets in `/static/assets/` — no character variety

---

## Implementation Plan — 6 Phases

### PHASE 1: Inspector Object Authoring (expose what exists)

**Goal:** Make all v100 runtime features editable from the inspector UI, not just via MCP tool calls.

**Batch 1A: Edit button for all custom objects (~30 lines)**

The "Edit" action button currently only appears for panels/HTML objects (line 17980). Extend to all custom objects.

**Touch point:** `_envCollectInspectorView` (line 17979–17985)
```javascript
// CHANGE: Show edit button for ALL custom-kind objects, not just panels
if (_envIsCustomSceneKind(kind) && actionMarkup.indexOf('data-env-inspector-action="edit-object"') < 0) {
    actions.push(_envInspectorActionButton('edit-object', 'Edit'));
}
```

**Batch 1B: Edit prefill includes appearance + mechanics (~20 lines)**

The edit-object handler at line 17598 prefills env_mutate but omits appearance and mechanics. Add them.

**Touch point:** `_envInspectorActionHandler` (line 17598–17615)
```javascript
// Add to the prefill object:
appearance: _envCloneJson(sourceObj.appearance || _envSceneAppearanceForObject(sourceObj), {}),
mechanics: _envCloneJson(sourceObj.mechanics || null, null)
```

**Batch 1C: Spawn button in habitat ops rail (~60 lines)**

Add a "Spawn Object" button to the habitat ops rail that opens a minimal spawn form (kind dropdown, label input, position). This replaces the current "tool call only" workflow.

**Touch point:** Near the habitat ops rail rendering (search for `envops-habitat-ops-rail`). Add a spawn action button and a minimal form that calls `env_spawn` via the tool dispatch.

**Batch 1D: Mechanics editor section (~80 lines)**

Replace the read-only Mechanics section with an editable version. When the user clicks "Edit Mechanics", show inline controls for family dropdown, wind toggles, reaction sliders, LOD thresholds. On save, call `env_mutate` with the new mechanics block.

**Touch point:** `_envCollectInspectorView` mechanics section (line 17901–17925). Convert metrics to form inputs when in edit mode.

**Batch 1E: Selection highlight + active object readout (~40 lines)**

When TransformControls are attached to a mesh, show a visual indicator:
- Emissive highlight on the selected mesh (cyan `0x00ccff`)
- A small HUD readout showing the selected object's kind, id, and current position
- Clear highlight on deselect

**Touch point:** `_env3DSelectMesh` (line 22473) and `_env3DDeselectMesh` (line 22483). Add emissive set/clear. For HUD, add a CSS2D label or simple overlay div.

**Phase 1 scope:** ~230 lines. Makes the existing runtime fully authorable from the UI.

---

### PHASE 2: Character Model System (NPC prefabs)

**Goal:** First-class character objects with swappable models, animation profiles, and behavioral states.

> Supersession note: the schema shape in this Phase 2 section is historical guidance and is now superseded by [CHARACTER_EMBODIMENT_SPEC.md](/F:/End-Game/champion_councl/docs/CHARACTER_EMBODIMENT_SPEC.md) for canonical field ownership and version sequencing. The implementation seams in this phase still matter: inspector authoring, spawn UI, selection handling, asset flow, and runtime integration remain valid targets.

**Batch 2A: NPC prefab schema on object contract (~50 lines)**

Extend `_envNormalizeSceneObjectRecord` with a `character` block:
```javascript
character: {
    archetype: 'wizard',           // wizard | warrior | dragon | creature | civilian | custom
    asset_ref: '/static/assets/npc.glb',  // overrides appearance.asset_ref for the character mesh
    sprite_ref: null,              // optional billboard sprite sheet URL
    anim_set: 'humanoid',         // humanoid | quadruped | flying | custom
    voice: null,                   // TTS voice profile name
    behavior: 'idle',             // idle | patrol | follow | guard | wander
    equipment: [],                 // future: equipped item refs
    scale: 1.0                     // character-specific scale multiplier
}
```

**Touch point:** `_envNormalizeSceneObjectRecord` (line 15730+). Add character normalization after mechanics, same merge pattern.

**Batch 2B: Character asset resolution (~40 lines)**

**Single source of truth:** `appearance.asset_ref` is the only field the renderer reads. `character.asset_ref` is a *template* — during normalization it writes into `appearance.asset_ref`, overriding the default kind asset. There is no parallel rendering path.

**Touch point:** `_envNormalizeSceneObjectRecord` (line 15689+), NOT the appearance resolver. After character block normalization, propagate into appearance:
```javascript
// After character normalization, BEFORE appearance normalization:
if (character.asset_ref && character.asset_ref !== _envDefaultKindAssets[kind]) {
    // Character template overrides default kind asset into appearance
    if (!p.appearance) p.appearance = {};
    if (!p.appearance.asset_ref) {
        p.appearance.asset_ref = character.asset_ref;
    }
}
```
This means:
- The renderer only ever reads `appearance.asset_ref` (no change to `_envSceneAppearanceForObject`)
- `character.asset_ref` is the source-of-record for what model a character *should* use
- Explicit `appearance.asset_ref` in spawn/mutate calls wins (it's already set before the check)
- Default kind assets still work when no character.asset_ref is set
- No dual-field ambiguity at runtime — inspector edits and asset browser spawns both flow through the same path

**Batch 2C: Extended animation clip vocabulary (~80 lines)**

The current clip resolver handles walk/run/idle (line 23260–23262). Animation is derived from **locomotion state** (`_moving` → walk, `state === 'running'` → run, else idle). This derivation is correct and must stay — `character.behavior` is a *movement profile* (patrol, wander, etc.), NOT an animation clip name. Behavior drives locomotion targets; locomotion drives animation.

Extend the clip *vocabulary* so models with richer clip sets can use them:
- `talk` — triggered by explicit `state === 'talking'` (set by chat/invoke actions)
- `attack` — triggered by `state === 'attacking'`
- `emote` — triggered by `state === 'emoting'`
- `sleep` — triggered by `state === 'sleeping'`

**Touch point:** The state→clip derivation at line 23260–23262. Extend the ternary chain:
```javascript
var desiredClip = mesh.userData._moving ? 'walk'
    : (state === 'running' ? 'run'
    : (state === 'talking' ? 'talk'
    : (state === 'attacking' ? 'attack'
    : (state === 'emoting' ? 'emote'
    : (state === 'sleeping' ? 'sleep'
    : 'idle')))));
```

Also extend `_env3DNormalizeClipName` (line 21944) to recognize these new clip names when loading GLBs with non-standard naming.

**NOTE:** `character.behavior` (patrol/wander/follow/guard) is NOT involved here. Behavior generates movement targets (Phase 5), which set `_moving`, which selects walk/idle. The state field is set by explicit actions (chat → 'talking'), not by behavior.

**Batch 2D: Character inspector section (~60 lines)**

Add a "Character" section to the inspector showing archetype, model, animation set, behavior, voice. Make it editable for custom objects.

**Composition rule with existing Agent section (line 17753–17769):**
- NPCs with a council slot (`slotId` is truthy) already get an "Agent" section with Slot/Model/Provider/Chat/Invoke. The Character section is rendered **below** the Agent section, not instead of it. They are complementary: Agent = runtime identity, Character = visual/behavioral profile.
- NPCs without a council slot get ONLY the Character section (no Agent section).
- Non-NPC kinds with a character block (e.g., `actor` with character data) get the Character section but never the Agent section (that's gated on `kind === 'npc' && slotSummary`).

**Touch point:** `_envCollectInspectorView` (line 17740). **Exact insertion order:** Agent section (line 17753) → Capabilities section (line 17767) → Mechanics section (line 17901) → **Character section here**. Insert the Character block immediately after the Mechanics section push. Guard with:
```javascript
if (obj.character && typeof obj.character === 'object') {
    sections.push(_envInspectorSection('character', 'Character', [
        _envInspectorMetric('Archetype', obj.character.archetype || '—'),
        _envInspectorMetric('Model', obj.character.asset_ref || 'default'),
        _envInspectorMetric('Anim Set', obj.character.anim_set || '—'),
        _envInspectorMetric('Behavior', obj.character.behavior || 'idle'),
        _envInspectorMetric('Voice', obj.character.voice || '—')
    ].join(''), { meta: obj.character.archetype || 'character' }));
}
```

**Phase 2 scope:** ~230 lines. Characters become first-class citizens in the object contract.

---

### PHASE 3: Asset Browser Enhancement + Character Spawn

**NOTE:** The asset browser already exists (panel.html:10491–10507, main.js:25905–25936). It has pack/category filters, an asset grid, and a `_envSpawnFromAsset` handler (line 25905) that calls `env_spawn`. The "SPAWN" button is on each asset card (line 25900, class `envops-asset-card-spawn`).

**Goal:** Extend the existing asset browser to support character prefab spawning and NPC model browsing.

**Batch 3A: Character-aware spawn from asset (~50 lines)**

Extend `_envSpawnFromAsset` (line 25905) to detect GLB/character assets and auto-populate both the `character` template and the canonical `appearance.asset_ref`:
```javascript
// If asset has animation clips or is tagged as character/npc:
if (asset.category === 'character' || asset.tags.includes('animated')) {
    spawnArgs.kind = 'npc';
    spawnArgs.character = {
        archetype: asset.archetype || 'custom',
        asset_ref: assetUrl,           // template (source of record)
        anim_set: asset.anim_set || 'humanoid',
        behavior: 'idle'
    };
    // Normalization will propagate character.asset_ref → appearance.asset_ref,
    // but we can also set it explicitly to be safe:
    if (!spawnArgs.appearance) spawnArgs.appearance = {};
    spawnArgs.appearance.asset_ref = assetUrl;
}
```
This avoids dual-field ambiguity: `appearance.asset_ref` is what the renderer reads, `character.asset_ref` is the template record.

**Batch 3B: Asset browser "Characters" filter (~30 lines)**

Add a "Characters" category to the `#envops-asset-category-select` dropdown (line 10498). When selected, filter to assets tagged as character/NPC/creature.

**Batch 3C: Asset download state indicator (~40 lines)**

Show download progress/cache state on asset cards. The existing cards have a spawn button but no feedback when `asset_download` is running. Add a small status chip (cached/downloading/error).

**Phase 3 scope:** ~120 lines. Extends existing infrastructure, doesn't rebuild it.

---

### PHASE 4: Agent Sprite Upgrade (character sprites)

**Goal:** Layer character sprites on top of the existing modality-icon system. The modality atlas (LLM/ASR/TTS/VLM/EMBEDDING) is shared across ALL agent kinds (slots, actors, NPCs) and must remain intact. Character sprites are an *additional* visual layer for objects that have `character.sprite_ref`.

**Batch 4A: Character sprite layer (~100 lines)**

The current agent sprite system (line 21317, `_env3DEnsureAgentSprite`) creates a billboard Sprite using the modality icon atlas (line 19963, `_env3DEnsureAgentSpriteAtlas`). This path is **not replaced**. Instead, add a second conditional path:

- If `character.sprite_ref` is set on the object, create a *separate* Sprite with that texture, positioned above or in front of the modality sprite
- The modality sprite continues to render underneath (showing capabilities)
- If no sprite_ref, no character sprite is created — modality icons are the only visual (current behavior preserved)
- Support sprite sheets with frame indices for directional facing (4 or 8 directions)

**Touch point:** `_env3DEnsureAgentSprite` (line 21317). Add a character sprite branch AFTER the existing modality atlas path, not instead of it. The character sprite is a sibling child of the mesh group, not a replacement.

**Batch 4B: Directional sprite facing (~50 lines)**

In the locomotion update (line 21169+), when the agent is moving, update the sprite frame based on movement direction. Use `Math.atan2(dx, dz)` to select the correct sprite sheet column.

**Batch 4C: Sprite sheet loader + cache (~40 lines)**

Load sprite sheets from URLs or local paths. Cache in `_env3D.spriteSheetCache`. Support power-of-2 textures with configurable grid layout (e.g., 4x4 = 16 frames, or 4x2 = 8 directional frames).

**Phase 4 scope:** ~190 lines. Characters get visual identity beyond colored boxes + modality icons.

---

### PHASE 5: Behavior & Movement Profiles

**Goal:** Characters that do things beyond idle/walk to a point.

**Batch 5A: Behavior state machine (~100 lines)**

Based on `character.behavior`, add behavioral routines that generate **movement targets** for the existing locomotion system. Behaviors do NOT select animation clips — locomotion state does that (see Phase 2C note).

- `idle`: no movement target (existing default — locomotion stays idle, animation plays idle clip)
- `patrol`: cycle through waypoints defined in `data.waypoints[]`, setting locomotion target to next waypoint
- `wander`: pick random position within a radius, set as locomotion target, pick new one on arrival
- `follow`: set locomotion target to another object's position by id, updated each tick
- `guard`: face toward a point (set mesh rotation), return to home position if displaced beyond threshold

**Touch point:** New function `_env3DAdvanceCharacterBehavior(mesh, obj, dt)` called from `_env3DAnimate` BEFORE `_env3DAdvanceMeshLocomotion` (line 23259). It writes the fields that the existing locomotion system actually reads (line 21169–21203):

```javascript
// Locomotion contract — these are the fields _env3DAdvanceMeshLocomotion reads:
mesh.userData._moving = true;           // enables locomotion (line 21170)
mesh.userData._targetX = worldX;        // target position X (line 21171)
mesh.userData._targetZ = worldZ;        // target position Z (line 21172)
mesh.userData._targetY = worldY;        // target position Y (line 21173)
mesh.userData._moveSpeed = speed;       // movement speed (line 21178, default 5.0)
mesh.userData._waypoints = [{x, z}];    // optional waypoint queue (line 21179–21196)
```

**Coordinate space rule:** Waypoints are stored in **scene-space** (0–100) on `data.waypoints[]`, same as object `x`/`y` positions. The behavior function converts them to world-space before writing to `_targetX`/`_targetZ` using the same formulas as `_env3DXYZFromObject` (line 20415):
```javascript
// scene-space (0-100) → world-space
var worldX = ((sceneX / 100) * 80) - 40;   // line 20418
var worldZ = ((sceneY / 100) * 40) - 20;   // line 20419
```
This means saved waypoints survive reload (they're in the same space as the object contract), and the inspector waypoint editor can display them on the 2D map or 3D overlay using the same conversion.

For `patrol`: convert `data.waypoints[]` from scene-space to world-space, set as `_waypoints` array, set `_moving = true`. Locomotion consumes and shifts them automatically (line 21185–21196). When `_waypoints` empties, locomotion sets `_moving = false` (line 21202). Behavior detects this and reloads the waypoint list for looping.

For `wander`: pick a random scene-space position within radius of home, convert to world-space, set `_targetX`/`_targetZ`, `_moving = true`. On arrival (locomotion clears `_moving`), pick a new random target after a delay.

For `follow`: each tick, read the followed object's `x`/`y`, convert to world-space, update `_targetX`/`_targetZ`.

For `guard`: store home position in scene-space. If displaced beyond threshold (compare in world-space), set `_targetX`/`_targetZ` to converted home position, `_moving = true`.

It does NOT touch `_mixer`, `_clips`, or animation state.

**Batch 5B: Waypoint authoring (~60 lines)**

In the inspector, for objects with `character.behavior === 'patrol'`, show a waypoint editor. Click on the ground to add waypoints. Show waypoint path as a line in 3D.

**Batch 5C: Behavior inspector controls (~40 lines)**

Add behavior selector to the Character inspector section. Dropdown for behavior type, plus behavior-specific params (patrol speed, wander radius, follow target id).

**Phase 5 scope:** ~200 lines. Characters become autonomous agents in the theater.

---

### PHASE 6: Model Sourcing & Import Pipeline

**Goal:** Bring open-source 3D models from HuggingFace and CC0 catalogs into the theater as usable characters.

**Batch 6A: HuggingFace 3D model search integration (~60 lines)**

Use `hub_search` with task filters for 3D-related model types. Display results in the Asset Browser panel with model card info.

**Batch 6B: Model download + registration via MCP tools (~80 lines)**

All download and storage is handled by existing MCP tools — no new server-side code:
- Search: `hub_search` (already exists)
- Download: `hub_download` (already exists — downloads to HuggingFace cache)
- The frontend dispatches these via `callTool(...)`, same as all other MCP tool calls

**Critical: browser-fetchable URL requirement.** The renderer's `_envLoadAsset` (line 21984) passes `asset_ref` to `THREE.GLTFLoader.load()`, which issues a browser `fetch()`. A raw HF cache path (e.g., `~/.cache/huggingface/...`) is NOT browser-fetchable.

**NOTE on `file_copy` MCP tool:** `file_copy` operates on FelixBag workspace documents, NOT the host filesystem. It cannot copy files from HF cache to `/static/assets/`. The actual deployment path depends on how `hub_download` returns content:

1. **If `hub_download` returns the file content or a blob:** The frontend can POST it to a simple upload endpoint, or the capsule can serve it from the download cache. This requires a minimal server-side bridge (one route that serves files from the HF cache directory).
2. **If `hub_download` places files in a web-accessible location:** Use that path directly as `asset.file`.
3. **Fallback — manual placement:** User copies the downloaded GLB into `/static/assets/` manually, then registers it via the asset browser UI.

**For v101 implementation:** Use option 3 (manual placement) as the guaranteed path. Add a "Register Local Model" button in the asset browser that lets the user type a `/static/assets/<name>.glb` path and registers it. This is zero server-side work. Options 1-2 can be added later when the capsule's file-serving capabilities are better understood.

The download flow becomes:
```
hub_search → hub_download (to HF cache) → user copies GLB to /static/assets/<name>.glb → "Register Local Model" button → fill form → _envRegisterAssetPack + localStorage persist → SPAWN from browser grid
```

Registration uses `_envRegisterAssetPack` (line 25605) to add the model to `_envAssetPacks`, making it appear in the browser grid.

**Batch 6C: Register local models in asset browser + persist (~50 lines)**

The canonical local-model path is `/static/assets/` (same directory as all existing GLBs). No subdirectory — keeps it flat and consistent with existing assets.

Add a "Register Local Model" button to the asset browser that:
1. Opens a small form: file path input (prefilled with `/static/assets/`), name, category dropdown
2. On submit, creates/extends a `user_models` asset pack and registers it:

```javascript
// Create or extend a "User Models" asset pack:
var userPack = _envFindAssetPack('user_models') || {
    pack_id: 'user_models',
    name: 'User Models',
    base_url: '',
    assets: []
};
userPack.assets.push({
    id: modelSlug,
    name: modelName,
    file: '/static/assets/' + filename,  // MUST be 'file', not 'asset_ref'
    category: 'character',
    tags: ['local', 'user'],
    kind: 'npc',
    scale_hint: 1.0
});
_envRegisterAssetPack(userPack);  // line 25605 — re-renders browser grid
```

**Persistence:** `_envAssetPacks` is in-memory only — user-added packs vanish on reload. To survive page refreshes, persist the `user_models` pack to `localStorage`:
```javascript
// After _envRegisterAssetPack:
try {
    localStorage.setItem('champion_user_asset_pack', JSON.stringify(userPack));
} catch (e) { /* quota exceeded — session-only is acceptable fallback */ }

// On startup (after _envEnsureBuiltinAssetPacks):
try {
    var saved = localStorage.getItem('champion_user_asset_pack');
    if (saved) _envRegisterAssetPack(JSON.parse(saved));
} catch (e) { /* corrupted — ignore */ }
```
This is lightweight, requires no server-side work, and the worst case (localStorage unavailable) is graceful degradation to session-only.

**Why `file` not `asset_ref`:** The asset-pack normalizer (`_envNormalizeAssetPackAsset`, line 25544) preserves `asset.file` (line 25553). `_envGetAssetUrl` (line 25639) resolves from `asset.file`. The spawn handler `_envSpawnFromAsset` (line 25910) calls `_envGetAssetUrl` to get the URL, then writes it into `appearance.asset_ref` (line 25927). So the flow is: `asset.file` → `_envGetAssetUrl` → `appearance.asset_ref` → renderer. A root-level `asset_ref` on the pack entry would be silently dropped by the normalizer.

**Batch 6D: Animation retargeting stub (~40 lines)**

For models with different rig conventions, add a mapping layer that translates standard clip names (idle/walk/run) to the model's actual clip names. Store in `character.clip_map`.

**Phase 6 scope:** ~230 lines. Connects the open-source model ecosystem to the theater via fetchable URLs, localStorage persistence, and the existing asset browser pipeline.

---

## Execution Order

| Phase | Dependency | Lines | What it delivers |
|-------|-----------|-------|-----------------|
| 1 | v100 done | ~230 | Inspector authoring: edit/spawn/mechanics editor/selection highlight |
| 2 | Phase 1 | ~230 | NPC prefab schema + character asset resolution + extended animation |
| 3 | Phase 1 | ~120 | Extend existing asset browser with character spawn + filters |
| 4 | Phase 2 | ~190 | Character sprites with directional facing |
| 5 | Phase 2 | ~200 | Behavior state machine + waypoint authoring |
| 6 | Phase 3 | ~230 | HuggingFace model import + local registration + localStorage persist + retargeting stub |

**Recommended order:** Phase 1 first (expose what exists), then Phase 2+3 in parallel (characters + asset browser), then Phase 4+5 (sprites + behavior), then Phase 6 (model sourcing).

**Total:** ~1,200 lines across 6 phases.

---

## Testing

1. **Phase 1:** Click any custom object → Edit button appears. Click Edit → env_mutate prefill includes appearance + mechanics. Spawn button in habitat rail creates a new object. Edit mechanics inline.

2. **Phase 2:** `env_spawn({kind: 'npc', id: 'merlin', character: {archetype: 'wizard', asset_ref: '/static/assets/npc.glb', anim_set: 'humanoid', behavior: 'idle'}})` → NPC appears with character model. Inspector shows Character section.

3. **Phase 3:** Open Asset Browser → see local GLBs + CC0 catalog. Click Spawn on an asset → object appears in theater.

4. **Phase 4:** Set `character.sprite_ref` on an NPC → character sprite appears layered above the modality icon. Walk the NPC → character sprite faces movement direction. Remove `sprite_ref` → only modality icon remains (existing behavior preserved).

5. **Phase 5:** Set `character.behavior: 'patrol'` with waypoints → NPC walks the patrol route autonomously.

6. **Phase 6:** Search HuggingFace for 3D models via `hub_search` in the asset browser → `hub_download` to HF cache → user copies GLB to `/static/assets/` → click "Register Local Model" → fill name/path → model appears in browser grid → click SPAWN → NPC appears in theater with character data. Verify model persists in browser after page reload (localStorage).

---

## Files Modified

| File | What |
|------|------|
| `static/main.js` | All phases — inspector, contract, renderer, behavior |
| `static/panel.html` | Asset browser HTML structure, spawn form, version bump |

---

## Constraints

- All code uses global `THREE` object (no ES module imports)
- No new npm dependencies
- Object contract backwards compatible (character block optional, null by default)
- NPC prefabs use existing `_envNormalizeSceneObjectRecord` merge pattern
- Asset browser queries use existing MCP tool dispatch (`callTool(...)`)
- Character sprites layer ON TOP of existing agent sprite system, don't replace it
- Performance: character behavior updates capped at dt-based intervals, not every frame
- Do NOT modify agent_compiler.py or capsule code — frontend + existing MCP tools only (no new server endpoints)
- Bump `main.js?v=101` in panel.html after all changes

---

## Key Line References (main.js)

| System | Line | Function |
|--------|------|----------|
| Custom kind check | 15519 | `_envIsCustomSceneKind` |
| Mechanics normalization | 15585 | `_envNormalizeSceneMechanics` |
| Object contract | 15730+ | `_envNormalizeSceneObjectRecord` |
| Default kind assets | 15654 | `_envDefaultKindAssets` |
| Appearance resolver | 15667 | `_envSceneAppearanceForObject` |
| Inspector action handler | 17517 | `_envHandleInspectorAction` |
| Edit prefill | 17598 | `action === 'edit-object'` |
| Remove action | 17617 | `action === 'remove-object'` |
| Inspector section builder | 17652 | `_envInspectorSection` |
| Inspector metric helper | 17672 | `_envInspectorMetric` |
| Inspector view collector | 17740 | `_envCollectInspectorView` |
| Mechanics inspector | 17901 | mechanics section |
| Edit/Remove buttons | 17979 | action button injection |
| Inspector return | 17998 | view assembly + action dedup |
| Modality resolution | 19850 | `_env3DResolveAgentModality` |
| Sprite tile drawing | 19882 | `_env3DDrawAgentSpriteTile` (canvas icons) |
| Sprite atlas init | 19963 | `_env3DEnsureAgentSpriteAtlas` (5 modality tiles) |
| Agent kind check | 19809 | `_env3DIsAgentKind` |
| Agent sprite instance | 21317 | `_env3DEnsureAgentSprite` |
| Clip name normalize | 21944 | `_env3DNormalizeClipName` |
| Clip resolve | 21951 | `_env3DResolveAnimationClip` |
| Nav grid | 21004 | `_envBuildNavGrid` |
| Locomotion | 21169 | `_env3DAdvanceMeshLocomotion` |
| GLB loading | 21984 | `_envLoadAsset` |
| Clone asset | 21969 | `_envCloneAsset` (SkeletonUtils) |
| Mesh asset request | 22292 | `_env3DRequestMeshAsset` |
| Animation setup on load | 22329 | mixer + clip dict + initial play |
| TransformControls | 22457 | `_env3DInitTransformControls` |
| Select/deselect | 22473/22483 | `_env3DSelectMesh` / `_env3DDeselectMesh` |
| Animation playback loop | 23256 | mixer update + state→clip crossfade |
| Asset spawn handler | 25905 | `_envSpawnFromAsset` |
| Asset spawn listener | 30723 | click handler on `#envops-asset-grid` |
| Dispose | 23430+ | `_env3DDispose` |

## Key Line References (panel.html)

| System | Line | Element |
|--------|------|---------|
| Environment tab | 10439 | `#tab-environment` |
| Asset browser | 10491 | `#envops-asset-browser` |
| Pack filter | 10498 | `#envops-asset-pack-select` |
| Category filter | 10503 | `#envops-asset-category-select` |
| Asset grid | 10507 | `#envops-asset-grid` |
| Script tags | 11671 | addon loading order |
| Bundle tag | 11684 | `main.js?v=100` |

---

## Transition Strategy

Phase 1 finishes v100 by exposing everything that already works. Phases 2-3 transition into the character pipeline by building on the exact same object contract, inspector patterns, and asset loading paths. The NPC prefab schema is an extension of the existing object, not a separate system. This means:

- `mechanics` handles physics/wind/reaction (already done)
- `character` handles identity/model/behavior (new)
- `appearance` handles visual rendering (already done, needs exposure)
- Inspector sections are composable (already proven with Mechanics section)
- Asset loading is generic (already supports any GLB via asset_ref)

The character system drops into the existing pipeline without refactoring anything.

Schema note: the transition logic above still holds, but the canonical modern schema now lives in [CHARACTER_EMBODIMENT_SPEC.md](/F:/End-Game/champion_councl/docs/CHARACTER_EMBODIMENT_SPEC.md). Use this document for seam and implementation guidance, not as the final authority for Phase 2 field definitions.
