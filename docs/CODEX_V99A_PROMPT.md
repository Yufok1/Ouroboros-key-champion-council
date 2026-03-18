Codex Task: v99a — Label Toggle, Kind Filters, Asset Browser Shell

Files:
- F:\End-Game\champion_councl\static\main.js (v98.1)
- F:\End-Game\champion_councl\static\panel.html (version bump)
- F:\End-Game\champion_councl\static\sw.js (cache bump)

Scope: Frontend only. Do NOT edit agent_compiler.py or capsule code. No new addon script files. No new MCP tools. All new controls are keyboard shortcuts + cockpit UI chips. The asset browser cockpit shortcut toggles the existing `_envAssetBrowserState` browser — it does NOT create a second browser.

---
MANDATORY PRE-READ

Read these sections of static/main.js before editing:

1. `_env3D` state object at line 19080 — you will add `labelMode` and `kindFilter` fields here.

2. `_env3DKindColors` at line 19126 — defines kind→color mapping, but does NOT include all real kinds. `_envDefaultKindAssets` at line 15580 adds `prop` and `marker`. Scene inspector at line 17197 uses `zone`. The kind filter chip list MUST be built from the union of live scene object kinds + `_env3DKindColors` keys + `_envDefaultKindAssets` keys — NOT from `_env3DKindColors` alone.

3. `_env3DIsAgentKind()` at line 19331 — identifies agent kinds (slot, npc, chatbot, actor). Kind filter uses this for grouping, not logic.

4. Keyboard handler at line 19757 — currently handles `[` and `]` for theme cycling. You will add `L` (label toggle) and `K` (kind filter toggle) here following the same guard pattern.

5. `_env3DLabelMarkupForObject()` at line 18072 — generates label HTML per object. Not modified, but read to understand label structure.

6. CSS2D label creation in `_env3DSyncObjects()` at line 22207 — this is where labels are created and attached to meshes. You will apply `labelMode` visibility here.

7. `_env3DUpdateLabelScale()` at line 22292 — CRITICAL: this function dynamically scales panel/surface-card labels via `--env-surface-card-scale` CSS variable (set on `cssLabel.element`, consumed by `.envops-scene-surface-card` at panel.html:2658). CSS2DRenderer owns `cssLabel.element.style.transform` for screen positioning. You MUST NOT set inline transform on either `cssLabel.element` or `firstElementChild`. Use a CSS class on `cssLabel.element` instead — see Part 1B.

8. Label update path at line 22269 — existing markup refresh. Apply `labelMode` after markup update too.

9. `_envRenderHabitat()` at line 22687 — builds the full habitat HTML. The cockpit section starts at line 22741. You will add the kind filter panel and label mode indicator after the camera cockpit section.

10. Cockpit section at lines 22741–22746 — Camera controls with `envops-focus-chip` buttons. Kind filter and label toggle get their own cockpit sections below this, using the same CSS patterns.

11. `_env3DSyncObjects()` mesh visibility at line 22065 — the main sync loop. Apply kind filter visibility here after mesh creation/update.

12. HUD layer detection at line 18351 — add entries for new panels so `_envMountedLayerNames()` reports them.

13. `_envRenderHabitatTelemetry()` at line 15080 — the overlay dock with status chips. Reference for chip styling.

14. Spin exemption at line 22388 — not modified, just read to confirm tile/substrate are already exempt.

15. Event delegation — `envKernelEl` click handler at line 30060. The delegate resolves `actionEl` at line 30063 and reads `action` at line 30065. Camera actions at line 30165. New cockpit actions go after this block. Use `actionEl` (NOT `el`) for `getAttribute` calls.

16. `renderEnvironmentView()` at line 25127 — the re-render function for the full habitat HTML. Call this after state changes that need cockpit UI refresh.

17. Existing asset browser: `_envAssetBrowserState` at line 19113, `_envRenderAssetBrowser()` at line 24954, toggle wiring at line 29816, DOM at panel.html line 10488. Do NOT create a second browser — the cockpit A-key shortcut toggles THIS browser.

18. `_envDefaultKindAssets` at line 15580 — lists kinds with default GLB assets. Includes `prop` and `marker` which are NOT in `_env3DKindColors`.

19. `_envSceneObjectPool()` at line 8356 — returns the merged pool of all scene objects. Used by `_env3DAllKnownKinds()` to discover kinds from persisted objects not yet mounted as meshes.

---
PART 1: Label Toggle System

The label toggle cycles through 3 modes: full (default), half (0.5 scale), hidden (invisible). Keyboard shortcut: L key.

A. State — add to `_env3D` state object (after `assetPackBootstrapped` at line 19104):

```javascript
labelMode: 'full',   // 'full', 'half', 'hidden'
```

B. Cycle function — add near `_env3DCycleTheme`:

```javascript
function _env3DCycleLabelMode() {
    var modes = ['full', 'half', 'hidden'];
    var idx = modes.indexOf(_env3D.labelMode || 'full');
    _env3D.labelMode = modes[(idx + 1) % modes.length];
    _env3DApplyLabelMode();
}

function _env3DApplyLabelMode() {
    var mode = _env3D.labelMode || 'full';
    var keys = Object.keys(_env3D.cssLabels || {});
    for (var i = 0; i < keys.length; i++) {
        var cssLabel = _env3D.cssLabels[keys[i]];
        if (!cssLabel || !cssLabel.element) continue;
        // IMPORTANT: Do NOT set inline transform on cssLabel.element (CSS2DRenderer owns it)
        // or on firstElementChild (surface cards own transform via --env-surface-card-scale).
        // Use a CSS class instead — the CSS rules handle both regular and surface-card labels.
        if (mode === 'hidden') {
            cssLabel.visible = false;
        } else {
            cssLabel.visible = true;
            cssLabel.element.classList.toggle('env3d-label-mode-half', mode === 'half');
        }
    }
    // Update cockpit indicator if present
    var indicator = document.querySelector('[data-env-label-mode]');
    if (indicator) indicator.textContent = mode;
}
```

B2. CSS rules — add to panel.html `<style>` section (near the existing `.env3d-label-shell` styles):

```css
/* Label mode: half — scale all label children to 50% */
.env3d-label-shell.env3d-label-mode-half > * {
    transform: scale(0.5);
    transform-origin: center bottom;
}
/* Surface cards: compose half-mode with the dynamic distance-based scale */
.env3d-label-shell.env3d-label-mode-half > .envops-scene-surface-card {
    transform: scale(calc(var(--env-surface-card-scale, 0.76) * 0.5));
    transform-origin: center bottom;
}
```

This avoids fighting CSS2DRenderer's transform on `cssLabel.element` AND the surface card's dynamic `--env-surface-card-scale`.

C. Keyboard binding — add to the keyboard handler at line 19758, inside the keydown listener, after the `]` / `[` branches:

```javascript
else if (e.key === 'l' || e.key === 'L') { e.preventDefault(); _env3DCycleLabelMode(); }
```

D. Apply on label creation — after the label is created and added at line 22215, apply current mode via CSS class:

```javascript
// After: _env3D.cssLabels[key] = cssLabel;
if (_env3D.labelMode === 'hidden') {
    cssLabel.visible = false;
} else if (_env3D.labelMode === 'half') {
    cssLabel.element.classList.add('env3d-label-mode-half');
}
```

E. Apply on label markup refresh — after the markup update at line 22269, re-apply mode via CSS class:

```javascript
// After markup refresh, re-apply label mode
var refreshLabel = _env3D.cssLabels[key];
if (refreshLabel) {
    if (_env3D.labelMode === 'hidden') {
        refreshLabel.visible = false;
    } else {
        refreshLabel.visible = true;
        refreshLabel.element.classList.toggle('env3d-label-mode-half', _env3D.labelMode === 'half');
    }
}
```

---
PART 2: Kind Filter System

Kind filter allows toggling visibility of scene objects by their kind. When a kind is filtered out, both its 3D mesh AND its CSS2D label are hidden. All kinds start visible.

A. State — add to `_env3D` state object (after `labelMode`):

```javascript
kindFilter: {},       // { kind: true/false } — true = visible (default all true)
kindFilterOpen: false // cockpit panel open/closed
```

B. Filter functions — add near `_env3DCycleLabelMode`:

```javascript
function _env3DKindFilterVisible(kind) {
    var k = String(kind || '').trim().toLowerCase();
    if (!k) return true;
    var filter = _env3D.kindFilter || {};
    return filter[k] !== false; // default visible
}

function _env3DToggleKindFilter(kind) {
    var k = String(kind || '').trim().toLowerCase();
    if (!k) return;
    if (!_env3D.kindFilter) _env3D.kindFilter = {};
    _env3D.kindFilter[k] = !_env3DKindFilterVisible(k);
    _env3DApplyKindFilter();
}

function _env3DAllKnownKinds() {
    // Seed with baseline kinds that exist in the codebase but may not be in
    // _env3DKindColors or _envDefaultKindAssets (e.g. zone, prop, marker).
    // This guarantees the filter UI always shows them even with an empty scene.
    var seen = { prop: true, zone: true, marker: true };
    // Union: color table
    var colorKeys = Object.keys(_env3DKindColors || {});
    for (var i = 0; i < colorKeys.length; i++) seen[colorKeys[i]] = true;
    // Union: default asset kinds
    var assetKeys = Object.keys(_envDefaultKindAssets || {});
    for (var j = 0; j < assetKeys.length; j++) seen[assetKeys[j]] = true;
    // Union: live meshes (catches any runtime-only kinds)
    var meshKeys = Object.keys(_env3D.meshes || {});
    for (var m = 0; m < meshKeys.length; m++) {
        var mk = meshKeys[m].split('::')[0];
        if (mk) seen[mk] = true;
    }
    // Union: scene object pool (catches persisted objects not yet mounted as meshes)
    var pool = (typeof _envSceneObjectPool === 'function') ? _envSceneObjectPool() : [];
    for (var p = 0; p < pool.length; p++) {
        var pk = String((pool[p] || {}).kind || '').trim().toLowerCase();
        if (pk) seen[pk] = true;
    }
    return Object.keys(seen).sort();
}

function _env3DSetAllKindsVisible(visible) {
    var kinds = _env3DAllKnownKinds();
    if (!_env3D.kindFilter) _env3D.kindFilter = {};
    for (var i = 0; i < kinds.length; i++) {
        _env3D.kindFilter[kinds[i]] = !!visible;
    }
    _env3DApplyKindFilter();
}

function _env3DApplyKindFilter() {
    var meshKeys = Object.keys(_env3D.meshes || {});
    for (var i = 0; i < meshKeys.length; i++) {
        var key = meshKeys[i];
        var kind = key.split('::')[0] || '';
        var visible = _env3DKindFilterVisible(kind);
        var mesh = _env3D.meshes[key];
        if (mesh) mesh.visible = visible;
        var label = _env3D.cssLabels[key];
        if (label) {
            if (!visible) {
                label.visible = false;
            } else if (_env3D.labelMode !== 'hidden') {
                label.visible = true;
            }
        }
    }
}
```

C. Keyboard binding — add after the L key handler:

```javascript
else if (e.key === 'k' || e.key === 'K') { e.preventDefault(); _env3D.kindFilterOpen = !_env3D.kindFilterOpen; renderEnvironmentView(); }
```

Note: `renderEnvironmentView()` is the existing re-render function at line 25127. It rebuilds the full habitat HTML including cockpit sections.

D. Apply in sync loop — in `_env3DSyncObjects()`, after mesh is created/updated and positioned (after the visual type dispatch block ending around line 22234), apply kind filter:

```javascript
// Apply kind filter visibility
var kindVisible = _env3DKindFilterVisible(obj.kind);
mesh.visible = kindVisible;
if (!kindVisible && _env3D.cssLabels[key]) {
    _env3D.cssLabels[key].visible = false;
}
```

---
PART 3: Cockpit UI — Label Mode Indicator + Kind Filter Panel

Add two new cockpit sections after the Camera cockpit section (line 22745). These go inside the habitat HTML, after the camera cockpit `</div>` and before the final `</div>`.

A. Label mode indicator — a small cockpit section showing current mode:

```javascript
'<div class="envops-habitat-scene-cockpit" style="margin-top:4px;">' +
'<div class="envops-habitat-scene-cockpit-head"><span>Labels</span><span data-env-label-mode>' + _esc(_env3D.labelMode || 'full') + '</span></div>' +
'<div class="envops-focus-strip">' +
'<span class="envops-focus-chip' + ((_env3D.labelMode || 'full') === 'full' ? ' active' : '') + '" data-env-action="set-label-mode" data-env-label-target="full">Full</span>' +
'<span class="envops-focus-chip' + ((_env3D.labelMode || 'full') === 'half' ? ' active' : '') + '" data-env-action="set-label-mode" data-env-label-target="half">Half</span>' +
'<span class="envops-focus-chip' + ((_env3D.labelMode || 'full') === 'hidden' ? ' active' : '') + '" data-env-action="set-label-mode" data-env-label-target="hidden">Hidden</span>' +
'</div>' +
'<div class="envops-kernel-note">Press L to cycle</div>' +
'</div>' +
```

B. Kind filter panel — collapsible, shows when `kindFilterOpen` is true:

```javascript
'<div class="envops-habitat-scene-cockpit" style="margin-top:4px;">' +
'<div class="envops-habitat-scene-cockpit-head" style="cursor:pointer;" data-env-action="toggle-kind-panel"><span>Kind Filter</span><span>' + (_env3D.kindFilterOpen ? '▼' : '▶') + '</span></div>' +
(_env3D.kindFilterOpen ? (function () {
    var kinds = _env3DAllKnownKinds();
    var chips = '';
    for (var ki = 0; ki < kinds.length; ki++) {
        var kname = kinds[ki];
        var kvisible = _env3DKindFilterVisible(kname);
        chips += '<span class="envops-focus-chip' + (kvisible ? ' active' : '') + '" data-env-action="toggle-kind" data-env-kind="' + _esc(kname) + '" style="font-size:10px;padding:2px 6px;margin:1px;">' + _esc(kname) + '</span>';
    }
    return '<div class="envops-focus-strip" style="flex-wrap:wrap;">' + chips + '</div>' +
        '<div class="envops-focus-strip" style="margin-top:2px;">' +
        '<span class="envops-focus-chip" data-env-action="kind-show-all" style="font-size:10px;padding:2px 6px;">Show All</span>' +
        '<span class="envops-focus-chip" data-env-action="kind-hide-all" style="font-size:10px;padding:2px 6px;">Hide All</span>' +
        '</div>' +
        '<div class="envops-kernel-note">Press K to toggle panel</div>';
})() : '') +
'</div>' +
```

C. Action handlers — add to the `envKernelEl` click delegate at line 30062. The delegate variable is `actionEl` (line 30063), NOT `el`. Add these cases after the existing `set-camera-mode` handler at line 30165:

```javascript
if (action === 'set-label-mode') {
    var labelTarget = actionEl.getAttribute('data-env-label-target');
    if (labelTarget) {
        _env3D.labelMode = labelTarget;
        _env3DApplyLabelMode();
        renderEnvironmentView();
    }
    return;
}
if (action === 'toggle-kind-panel') {
    _env3D.kindFilterOpen = !_env3D.kindFilterOpen;
    renderEnvironmentView();
    return;
}
if (action === 'toggle-kind') {
    var kindName = actionEl.getAttribute('data-env-kind');
    if (kindName) {
        _env3DToggleKindFilter(kindName);
        renderEnvironmentView();
    }
    return;
}
if (action === 'kind-show-all') {
    _env3DSetAllKindsVisible(true);
    renderEnvironmentView();
    return;
}
if (action === 'kind-hide-all') {
    _env3DSetAllKindsVisible(false);
    renderEnvironmentView();
    return;
}
```

---
PART 4: Asset Browser Cockpit Shortcut

There is an EXISTING asset browser: `_envAssetBrowserState` at line 19113, `_envRenderAssetBrowser()` at line 24954, toggle button at line 29816 (`#envops-asset-browser-toggle`), DOM panel at panel.html line 10488 (`#envops-asset-browser`). Do NOT create a second browser. The cockpit shortcut just toggles the existing one.

A. Keyboard binding — add after the K key handler:

```javascript
else if (e.key === 'a' || e.key === 'A') {
    e.preventDefault();
    _envAssetBrowserState.expanded = !_envAssetBrowserState.expanded;
    renderEnvironmentView();
    _envRenderAssetBrowser();
}
```

B. Cockpit indicator — add after the kind filter cockpit section in the habitat HTML:

```javascript
'<div class="envops-habitat-scene-cockpit" style="margin-top:4px;">' +
'<div class="envops-habitat-scene-cockpit-head" style="cursor:pointer;" data-env-action="toggle-asset-browser"><span>Asset Library</span><span>' + (_envAssetBrowserState.expanded ? 'open' : 'closed') + '</span></div>' +
'<div class="envops-kernel-note">Press A to toggle asset browser</div>' +
'</div>' +
```

C. Action handler — add to the `envKernelEl` click delegate (same block as Part 3C):

```javascript
if (action === 'toggle-asset-browser') {
    _envAssetBrowserState.expanded = !_envAssetBrowserState.expanded;
    renderEnvironmentView();
    _envRenderAssetBrowser();
    return;
}
```

D. No new state fields needed — reuses existing `_envAssetBrowserState.expanded`.

---
PART 5: HUD Layer Detection

Add an entry to `_envMountedLayerNames()` at line 18351 so the telemetry reports the kind filter panel:

```javascript
add('kind_filter', '[data-env-action="toggle-kind-panel"]');
```

(The existing asset browser already has its own DOM element `#envops-asset-browser` — no new HUD entry needed for it.)

---
PART 6: Version Bump

v98.1 → v99:
- panel.html: `main.js?v=98.1` → `main.js?v=99`
- sw.js: `CACHE_NAME = 'champion-council-v98-1'` → `CACHE_NAME = 'champion-council-v99'`
- sw.js: `/static/main.js?v=98.1` → `/static/main.js?v=99`

---
Testing

1. `node --check static/main.js` passes
2. `node --check static/sw.js` passes
3. L key cycles label mode: full → half → hidden → full
4. In "full" mode, all CSS2D labels render at normal size (default behavior, identical to v98.1)
5. In "half" mode, all CSS2D labels render at 50% scale via `env3d-label-mode-half` CSS class on `cssLabel.element` — the CSS rules scale children, NOT the element itself (CSS2DRenderer owns that transform). Panel/surface-card labels compose the half scale with `--env-surface-card-scale`.
6. In "hidden" mode, all CSS2D labels are invisible (cssLabel.visible = false)
7. New labels created while in "half" or "hidden" mode start in the correct mode
8. Label mode indicator in cockpit shows current mode with clickable Full/Half/Hidden chips
9. Clicking a label mode chip in cockpit sets that mode (equivalent to pressing L)
10. K key toggles kind filter panel open/closed
11. Kind filter panel shows all known kinds as clickable chips — built from the union of `_env3DKindColors` + `_envDefaultKindAssets` + live scene kinds (includes `prop`, `zone`, `marker`)
12. Clicking a kind chip toggles that kind's visibility — filtered kinds have mesh.visible=false AND label hidden
13. "Show All" / "Hide All" buttons work correctly
14. Filtering a kind hides both the 3D mesh and the CSS2D label for all objects of that kind
15. Showing a filtered kind restores mesh visibility AND respects current label mode (hidden labels stay hidden even when kind is shown)
16. A key toggles the existing asset browser panel (`_envAssetBrowserState.expanded`) — same effect as clicking `#envops-asset-browser-toggle`
17. Asset browser cockpit indicator shows "open" or "closed" state
18. A-key does NOT create a second browser panel — it reuses the existing one at `#envops-asset-browser`
19. All three new cockpit sections render correctly below the Camera cockpit
20. Existing scene objects (rooms, portals, NPCs, tiles, substrates, decals) render unchanged when no filters are active
21. Existing keyboard shortcuts ([ ] for theme cycling) still work
22. Bloom, shadows, triggers, terrain, locomotion all unaffected
23. Service worker cache name updated to v99

---
Constraints

- Only edit frontend files (main.js, panel.html, sw.js)
- Use var and function declarations (existing code style)
- No new addon script files
- No new MCP tools
- Do NOT modify existing visual dispatch, trigger system, terrain, bloom, shadow, or locomotion code
- Do NOT modify `_env3DApplyTileState`, `_env3DApplySubstrateState`, `_env3DApplyDecalState`, `_env3DApplyPrimitiveState`
- Do NOT modify `_env3DStoreTriggerMeta` or `_env3DTriggerFire`
- Do NOT change coordinate mapping in `_env3DXYZFromObject`
- Do NOT change `_env3DLabelMarkupForObject` — label content stays the same, only visibility/scale changes
- Kind filter default is all kinds visible (filter object starts empty, missing key = visible)
- Kind filter chip list MUST include `prop`, `zone`, `marker` — use `_env3DAllKnownKinds()`, NOT just `_env3DKindColors`
- Label mode default is 'full' (identical to v98.1 behavior)
- Label scaling MUST use the `env3d-label-mode-half` CSS class on `cssLabel.element` — NEVER set inline `transform` on `cssLabel.element` (CSS2DRenderer owns it) or on `firstElementChild` (surface cards own their transform via `--env-surface-card-scale`). The CSS rules in panel.html handle both regular and surface-card labels.
- Action handlers MUST use `actionEl` (line 30063), NOT `el` — that is the delegate variable in the `envKernelEl` click handler
- Re-render function is `renderEnvironmentView()` at line 25127 — NOT `_envScheduleRender`
- Asset browser: do NOT create a second browser — A-key toggles existing `_envAssetBrowserState.expanded` and calls `_envRenderAssetBrowser()`
- Cockpit sections must use existing CSS class patterns: `envops-habitat-scene-cockpit`, `envops-habitat-scene-cockpit-head`, `envops-focus-strip`, `envops-focus-chip`, `envops-kernel-note`
