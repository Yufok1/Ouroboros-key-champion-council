Codex Task: v99a.1 — Fix Cockpit Click Delegation + Theme Picker Overlap

Files:
- F:\End-Game\champion_councl\static\main.js (v99)
- F:\End-Game\champion_councl\static\panel.html (CSS fix + version bump)
- F:\End-Game\champion_councl\static\sw.js (cache bump)

Scope: Frontend only. Two bugs + cache-busting version bump. No new features.

---
MANDATORY PRE-READ

Read these sections of static/main.js before editing:

1. **Stage click delegate** at line 30003–30084 — `envStageEl.addEventListener('click', ...)`. This is the click handler for `envops-stage`, which is the DOM element that contains the 3D theater and cockpit overlay. It already handles `data-env-action` values at line 30019–30068 (inspector actions, scene-object, refresh-health, replay controls). The v99a cockpit actions are MISSING from this handler.

2. **Kernel click delegate** at line 30210–30356 — `envKernelEl.addEventListener('click', ...)`. This is on `envops-kernel`, a SIBLING element to `envops-stage`. It has all the v99a action handlers at line 30319–30356 (set-label-mode, toggle-kind-panel, toggle-kind, kind-show-all, kind-hide-all, toggle-asset-browser) plus set-camera-mode at line 30315. These handlers WORK when triggered from kernel HTML but CANNOT receive clicks from the cockpit because the cockpit is inside `envops-stage`, not `envops-kernel`.

3. **DOM structure** in panel.html — `envops-stage` at line 10481 and `envops-kernel` at line 10562 are SIBLING divs. Events bubble UP through parent elements, never sideways to siblings. This is why cockpit clicks (inside stage) never reach the kernel delegate.

4. **Cockpit HTML** — rendered by `_envRenderHabitat()` at line 22841–22895. Goes into `stageEl.innerHTML` at line 25463. Contains chips with `data-env-action` values: `set-camera-mode`, `reset-camera`, `set-label-mode`, `toggle-kind-panel`, `toggle-kind`, `kind-show-all`, `kind-hide-all`, `toggle-asset-browser`.

5. **Theme picker** — `_env3DCreateThemePicker(container)` at line 19725. Appends a `div.env-theme-picker` to the 3D container. CSS at panel.html:2625: `position: absolute; bottom: 10px; right: 10px; z-index: 30`.

6. **Cockpit CSS** at panel.html:3794: `position: absolute; right: 14px; bottom: 14px; z-index: 28`. Both anchor to the same bottom-right corner. Theme picker (z-index 30) overlays the cockpit (z-index 28).

7. **Kind filter functions** — `_env3DToggleKindFilter()` at line 19771, `_env3DApplyKindFilter()` at line 19837, `_env3DSetAllKindsVisible()` at line 19827, `_env3DApplyLabelMode()` at line 19785.

---
BUG 1: Cockpit actions don't fire (kind filter, label mode, camera mode, asset browser)

Root cause: The cockpit is rendered inside `envops-stage` but the action handlers are in the `envops-kernel` click delegate. Clicks from stage never reach kernel because they are sibling DOM elements.

Fix: Add the cockpit action handlers to the EXISTING stage delegate. The stage delegate already has a `data-env-action` branch at line 30019–30068. Add the missing handlers INSIDE that branch, AFTER the `replay-focus` handler (line 30064–30067) and BEFORE the closing `}` at line 30068.

Add these handlers in order:

```javascript
                if (action === 'set-camera-mode') {
                    _envQueueControl('set_camera_mode', actionEl.getAttribute('data-env-camera-mode') || 'overview', uiActor, 'cockpit camera mode');
                    return;
                }
                if (action === 'reset-camera') {
                    _envQueueControl('reset_camera', '', uiActor, 'cockpit camera reset');
                    return;
                }
                if (action === 'set-label-mode') {
                    var labelTarget = actionEl.getAttribute('data-env-label-target') || '';
                    if (labelTarget) {
                        _env3D.labelMode = String(labelTarget || 'full').trim().toLowerCase() || 'full';
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
                    var kindName = actionEl.getAttribute('data-env-kind') || '';
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
                if (action === 'toggle-asset-browser') {
                    _envAssetBrowserState.expanded = !_envAssetBrowserState.expanded;
                    renderEnvironmentView();
                    _envRenderAssetBrowser();
                    return;
                }
```

IMPORTANT: Do NOT remove the handlers from the kernel delegate (line 30315–30356). Those handlers are needed for actions triggered from kernel HTML (Scene Operator Spine area). Both delegates must handle these actions.

IMPORTANT: The variable name in the stage delegate is `actionEl` (line 30019), matching the kernel delegate. Use `actionEl` in all getAttribute calls.

---
BUG 2: Theme picker overlaps cockpit bottom-right

Root cause: Both `.env-theme-picker` and `.envops-habitat-scene-cockpit` are positioned `absolute` at the bottom-right corner of the 3D container. The theme picker (z-index 30) covers the cockpit (z-index 28).

Fix: Move the theme picker to the bottom-LEFT of the 3D container instead of bottom-right.

In panel.html, find the `.env-theme-picker` rule at line 2625:

```css
.env-theme-picker {
    position: absolute;
    bottom: 10px;
    right: 10px;       /* ← change this */
```

Change `right: 10px` to `left: 10px`. This moves the theme dot strip to the bottom-left of the viewport, clearing the cockpit entirely.

No other changes needed — the theme picker is a simple row of dots that works in any corner.

---
PART 3: Version Bump (cache-busting)

The service worker in sw.js uses a cache-first fetch strategy. Without a version bump, the hotfix will stay hidden behind the existing v99 cache. Bump v99 → v99.1:

A. panel.html — find the main.js script tag (line 11681):
```html
main.js?v=99
```
Change to:
```html
main.js?v=99.1
```

B. sw.js — line 1:
```javascript
var CACHE_NAME = 'champion-council-v99';
```
Change to:
```javascript
var CACHE_NAME = 'champion-council-v99-1';
```

C. sw.js — in STATIC_ASSETS array, find:
```javascript
'/static/main.js?v=99'
```
Change to:
```javascript
'/static/main.js?v=99.1'
```

---
Testing

1. Open the Environment tab with a live scene (any scene with objects)
2. Click a camera mode chip in the cockpit (e.g. "Pan") — camera mode should change. Before fix: nothing happens.
3. Click a label mode chip (Full / Half / Hidden) — labels should toggle. Before fix: nothing happens.
4. Press K or click "Kind Filter" cockpit header — panel should open/close showing kind chips
5. Click a kind chip (e.g. "slot") — that kind's meshes should disappear from the 3D view. Before fix: nothing happens.
6. Click "Show All" / "Hide All" — all kinds toggle. Before fix: nothing happens.
7. Click "Asset Library" cockpit header or press A — browser should toggle, cockpit indicator should update. Before fix: nothing happens from click.
8. Theme picker dots should now be visible in the bottom-LEFT corner, not overlapping the cockpit
9. Keyboard shortcuts (L, K, A, [, ]) should still work as before (they bypass click delegation)
10. Inspector actions (clicking on 3D objects) should still work (existing stage delegate handlers unchanged)
11. `node --check static/main.js` passes
12. `node --check static/sw.js` passes
13. Hard refresh picks up v99.1 — old v99 cache is evicted by new CACHE_NAME

---
Constraints

- Only edit main.js (line ~30064), panel.html (line ~2627 + version bump), and sw.js (cache bump)
- Do NOT change any function signatures or implementations
- Do NOT modify the kernel delegate handlers — keep them as-is for kernel-sourced clicks
- Do NOT change cockpit HTML rendering in _envRenderHabitat
- Do NOT change _env3DCreateThemePicker logic — CSS-only position fix
- Use var and function declarations (existing code style)
- All action handlers must use `return;` at the end (matching existing delegation pattern)
