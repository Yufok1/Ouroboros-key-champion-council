# v102 Plan — Bulk Asset Pack Ingestion Pipeline

## Status: DRAFT — For Codex bounce-back review

## Research Basis
- Full audit of asset registry (18 pack-level entries, 0 per-model entries)
- Code read of existing asset browser infrastructure (already has Register Local Model, localStorage persist, HF search, character-aware spawn)
- Web search confirming Kenney (40k+ assets), Quaternius (thousands), KayKit, Poly Haven all CC0
- Live runtime verification that only 9 GLBs exist in `/static/assets/`

---

## Context: What Already Works (v101 delivered)

The following infrastructure is **already implemented** — v102 does NOT rebuild any of it:

| System | Line | Status |
|--------|------|--------|
| `_envRegisterAssetPack(manifest)` | 26677 | Works — pushes into `_envAssetPacks`, re-renders browser |
| `_envLoadAssetPackManifest(url, cb)` | 26693 | Works — fetches JSON manifest from URL, registers it |
| `_envRegisterLocalModelAsset(config)` | 26526 | Works — creates `user_models` pack, persists to localStorage |
| `_envPersistUserAssetPack(pack)` | 26506 | Works — saves to localStorage |
| `_envRestoreUserAssetPack()` | 26514 | Works — restores on startup |
| `_envEnsureBuiltinAssetPacks()` | 26875 | Works — loads builtins + CC0 starter + user pack |
| `_envSearchHubModelsForAssets(query)` | 26624 | Works — searches HF, registers results as pack |
| `_envDownloadHubModelAsset(modelId)` | 26647 | Works — downloads to HF cache, tracks state |
| `_envMutateAssetPackAsset(packId, assetId, changes)` | 26575 | Works — mutates asset in pack |
| `_envAssetDownloadState(asset)` | 26497 | Works — local/ready/remote/downloading/error |
| `_envAssetLooksCharacterAsset(asset)` | 26482 | Works — character filter |
| `_envSpawnFromAsset(packId, assetId)` | 27039 | Works — character-aware spawn |
| Register Local Model UI button | 26974 | Works — form with path/name/category/archetype |
| HuggingFace Search UI panel | 26993 | Works — search + download buttons |
| Characters category filter | 26889 | Works — filters asset grid |
| `_envGetAssetUrl(packId, assetId)` | 26711 | Works — resolves `base_url + asset.file` |
| `_envNormalizeAssetPackAsset(asset, i)` | 26428 | Works — normalizes `file`, `name`, `category`, `tags`, `kind`, `scale_hint`, `appearance`, `data` |
| `_envCc0StarterPackManifest()` | 26781 | Works — pattern: `base_url: '/static/assets/'`, assets with `file: 'npc.glb'` |

## What's Actually Missing

### The gap is content + ingestion, not infrastructure

1. **Only 9 placeholder GLBs in `/static/assets/`** — npc.glb, terminal.glb, gear.glb, crystal.glb, crate.glb, chatbot.glb, screen.glb, server.glb, pin.glb. That's everything the renderer can actually load.

2. **The asset registry has 18 pack-level entries, not per-model entries.** `kenney/nature-kit` = 1 row representing "60+ models" but zero of those 60 models are individually registered or fetchable.

3. **All Kenney/Quaternius entries have `download_url: ""` and `download_mode: "archive"`.** The `asset_download` tool fails with "No direct download URL available for this archive pack."

4. **No extraction pipeline.** Even if we had the .zip files, there's no unzip → find GLBs → generate per-model manifest → place in webroot flow.

5. **No per-pack manifest JSON files.** `_envLoadAssetPackManifest` (26693) can load manifest JSONs from URLs, but none exist yet beyond the hardcoded builtins.

---

## Implementation Plan — 4 Phases

### PHASE 1: Pack Manifest Format + Directory Convention

**Goal:** Define the standard manifest format and directory layout so every subsequent pack follows the same pattern.

**Batch 1A: Directory convention (~0 code lines, convention only)**

```
static/assets/
├── npc.glb                      ← existing starter GLBs (unchanged)
├── terminal.glb
├── ...
├── packs/                       ← NEW: all ingested packs go here
│   ├── kenney-nature-kit/
│   │   ├── manifest.json        ← per-model manifest (loaded by _envLoadAssetPackManifest)
│   │   ├── tree_oak.glb
│   │   ├── tree_pine.glb
│   │   ├── rock_large.glb
│   │   └── ...
│   ├── quaternius-medieval-buildings/
│   │   ├── manifest.json
│   │   ├── house_small.glb
│   │   └── ...
│   └── index.json               ← NEW: master index listing all pack manifest URLs
```

**Batch 1B: Manifest JSON schema (~0 code lines, schema definition)**

Each `manifest.json` follows the exact format that `_envNormalizeAssetPackManifest` (line 26458) already expects:

```json
{
  "pack_id": "kenney-nature-kit",
  "name": "Kenney Nature Kit",
  "version": "1.0.0",
  "license": "CC0-1.0",
  "description": "60+ low-poly nature models - trees, rocks, flowers, mushrooms",
  "base_url": "/static/assets/packs/kenney-nature-kit/",
  "assets": [
    {
      "id": "tree_oak",
      "file": "tree_oak.glb",
      "name": "Oak Tree",
      "category": "vegetation",
      "tags": ["tree", "oak", "nature", "foliage"],
      "kind": "prop",
      "scale_hint": 1.2
    },
    {
      "id": "rock_large",
      "file": "rock_large.glb",
      "name": "Large Rock",
      "category": "terrain",
      "tags": ["rock", "stone", "terrain"],
      "kind": "prop",
      "scale_hint": 1.0
    }
  ]
}
```

Key contract points:
- `base_url` ends with `/` — `_envGetAssetUrl` (26711) concatenates `base_url + asset.file`
- `file` is the GLB filename relative to `base_url` — no leading `/`
- `category` drives the browser dropdown filter
- `tags` are an array (not comma-separated) — `_envNormalizeAssetPackAsset` (26428) preserves them
- `kind` maps to the spawn system's object kind (prop, npc, marker, etc.)
- `scale_hint` drives the default spawn scale

**Batch 1C: Master index format (~0 code lines, schema definition)**

`static/assets/packs/index.json`:
```json
{
  "packs": [
    "/static/assets/packs/kenney-nature-kit/manifest.json",
    "/static/assets/packs/quaternius-medieval-buildings/manifest.json"
  ]
}
```

**Phase 1 scope:** Convention and schema only. No code changes.

---

### PHASE 2: Manifest Generator Script

**Goal:** A utility script that takes a directory of extracted GLBs and produces a valid `manifest.json`.

**Batch 2A: `scripts/generate-pack-manifest.js` (~120 lines)**

Node.js script (runs locally, not in browser). Input: directory path + pack metadata. Output: `manifest.json`.

```bash
node scripts/generate-pack-manifest.js \
  --dir static/assets/packs/kenney-nature-kit \
  --pack-id kenney-nature-kit \
  --name "Kenney Nature Kit" \
  --license CC0-1.0 \
  --source kenney \
  --base-url /static/assets/packs/kenney-nature-kit/ \
  --default-kind prop \
  --default-category vegetation
```

The script:
1. Scans the directory for all `.glb` and `.gltf` files recursively
2. For each file, generates an asset entry:
   - `id`: relative path from pack root, without extension, lowercased, `/` and spaces replaced with `-` (e.g., `Trees/oak.glb` → `trees-oak`). This guarantees uniqueness even when two subdirectories contain the same filename.
   - `file`: relative path from pack root with **POSIX forward slashes only** (e.g., `Trees/oak.glb`, never `Trees\oak.glb`). On Windows, `path.relative()` emits backslashes — the script MUST normalize: `relativePath.split(path.sep).join('/')`
   - `name`: filename humanized (underscores/dashes → spaces, title case)
   - `category`: inferred from parent directory name if in subdirectory, else `--default-category`
   - `tags`: extracted from filename parts + source name
   - `kind`: `--default-kind` (most CC0 packs are props)
   - `scale_hint`: 1.0 default (can be overridden per-model later)
3. After generating all entries, **check for duplicate `id` values** and append a numeric suffix if collisions remain (e.g., `oak`, `oak-2`)
4. Writes `manifest.json` to the pack directory
5. Prints summary: pack_id, model count, categories found, any deduplication warnings

**Category inference rules:**
- Subdirectory name if files are nested (e.g., `Trees/oak.glb` → category: `vegetation`)
- Filename prefix heuristics: `tree_*` → vegetation, `rock_*` → terrain, `house_*` → structure, `character_*` → character
- Fallback to `--default-category`

**Batch 2B: `scripts/generate-pack-index.js` (~40 lines)**

Scans `static/assets/packs/*/manifest.json`, generates `static/assets/packs/index.json`.

```bash
node scripts/generate-pack-index.js
```

**Phase 2 scope:** ~160 lines of Node.js. Offline tooling, not shipped to browser.

---

### PHASE 3: Startup Pack Loading in Frontend

**Goal:** On page load, fetch the master index, then load all pack manifests into the asset browser.

**Batch 3A: Load pack index on startup (~40 lines)**

Add to `_envEnsureBuiltinAssetPacks` (line 26875):

**IMPORTANT:** This function is called TWICE — once at global startup (line 31922) and again during 3D init (line 23530). The pack index loader must be idempotent to avoid double-fetching all manifests.

```javascript
var _envPackIndexPromise = null;  // memoized promise — null means not yet attempted

function _envLoadPackIndex(indexUrl) {
    if (_envPackIndexPromise) return _envPackIndexPromise;  // already loading/loaded — reuse
    if (!indexUrl || typeof fetch !== 'function') return;
    _envPackIndexPromise = fetch(indexUrl).then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
    }).then(function (data) {
        if (!data || !Array.isArray(data.packs)) return;
        data.packs.forEach(function (manifestUrl) {
            _envLoadAssetPackManifest(manifestUrl);  // line 26693 — already works
        });
    }).catch(function (error) {
        console.warn('[envops] pack index load failed', indexUrl, error);
        _envPackIndexPromise = null;  // clear on failure so the second call can retry
    });
    return _envPackIndexPromise;
}

function _envEnsureBuiltinAssetPacks() {
    _envRegisterAssetPack(_envBuiltinAssetPackManifest());
    _envRegisterAssetPack(_envCc0StarterPackManifest());
    _envRestoreUserAssetPack();
    // NEW: load external pack manifests (memoized — retries on failure, dedupes on success)
    _envLoadPackIndex('/static/assets/packs/index.json');
}
```

This way: first call starts the fetch and stores the promise. Second call (from 3D init) reuses the same promise if it's still in flight or already resolved. If the **index fetch** failed (network error, 404), the promise is cleared so the second call gets a fresh retry.

**Scope of retry:** Only the index.json fetch is retried on failure. Individual manifest loads (`_envLoadAssetPackManifest` at line 26693) are fire-and-forget — if one manifest 404s, that pack simply won't appear in the browser. This is acceptable for v102: manifests are local static files that should not transiently fail. If per-manifest retry is needed later, `_envLoadAssetPackManifest` can be extended independently.

**Touch point:** `_envEnsureBuiltinAssetPacks` (line 26875). Add `_envPackIndexPromise` memoized var + `_envLoadPackIndex` function + one call line. `_envRegisterAssetPack` (26677) is also idempotent (replaces by pack_id), so even if a manifest loaded twice the browser state would be correct — but we avoid the redundant network requests.

**Batch 3B: Graceful fallback when no packs directory exists (~5 lines)**

If `index.json` returns 404, silently continue with just the builtins. The fetch `.catch()` above handles this. No error toast.

**Batch 3C: Asset count update after async pack loads (~15 lines)**

The pack manifests load asynchronously. After each one completes, `_envRegisterAssetPack` already calls `_envRenderAssetBrowser()` (line 26689), so the browser grid updates automatically. But the asset count in the header should show a brief loading indicator while packs are loading.

Add a `_envAssetBrowserState.packsLoading` counter:
- Add `packsLoading: 0` to `_envAssetBrowserState` (line 19574)
- Increment before each `_envLoadAssetPackManifest` call in `_envLoadPackIndex`
- Decrement in the `_envLoadAssetPackManifest` callback (both success and error paths)
- In `_envRenderAssetBrowser` (line 26925), update the count element (line 27004) to show "Loading packs..." while `packsLoading > 0`

**Touch points for Batch 3C:**
- `_envAssetBrowserState` declaration (line 19574) — add `packsLoading: 0`
- `_envRenderAssetBrowser` count display (line 27004) — conditional text
- `_envLoadPackIndex` — increment/decrement around each manifest load

**Phase 3 scope:** ~60 lines of frontend JavaScript across 3 touch points.

---

### PHASE 4: Proof-of-Concept with 2 Real Packs

**Goal:** Download, extract, manifest-generate, and load Kenney Nature Kit and Quaternius Medieval Buildings as the first real packs.

**Batch 4A: Kenney Nature Kit ingestion**

Manual steps (documented, not automated):
1. Download from `https://kenney.nl/assets/nature-kit` (zip file)
2. Extract to `static/assets/packs/kenney-nature-kit/`
3. Run: `node scripts/generate-pack-manifest.js --dir static/assets/packs/kenney-nature-kit --pack-id kenney-nature-kit --name "Kenney Nature Kit" --license CC0-1.0 --source kenney --base-url /static/assets/packs/kenney-nature-kit/ --default-kind prop --default-category vegetation`
4. Run: `node scripts/generate-pack-index.js`
5. Verify: refresh browser → Nature Kit appears in pack dropdown → 60+ models in grid → SPAWN works

**Expected result:** 60+ individually spawnable vegetation/terrain models.

**Batch 4B: Quaternius Medieval Buildings ingestion**

Same flow:
1. Download from `https://quaternius.com/packs/medievalbuildings.html`
2. Extract to `static/assets/packs/quaternius-medieval-buildings/`
3. Run manifest generator
4. Run index generator
5. Verify: 30+ buildings in grid → SPAWN works

**Expected result:** 30+ individually spawnable building/structure models.

**Batch 4C: Update asset registry entries with download info (MCP operational step — NOT frontend code)**

This is a manual MCP tool call, not a code change. Run via the MCP client (Claude Code or the capsule's tool interface) to update the 2 registry entries with real download URLs:

```
asset_register(name="Nature Kit", source="kenney",
    download_url="https://kenney.nl/media/pages/assets/nature-kit/xxx/kenney_nature-kit.zip",
    download_mode="archive", download_ext=".zip")
```

(Exact download URL needs to be confirmed from the actual download page.)

**NOTE:** `asset_register` is a capsule-side MCP tool (lives in the Python server, not in main.js). This step is separate from the frontend code patch. Do NOT attempt to call it from main.js. It updates FelixBag metadata, not the browser asset packs.

**Batch 4D: Verify full spawn pipeline**

Test each of these in the browser:
1. Open Asset Browser → select "Kenney Nature Kit" from pack dropdown
2. Filter by category "vegetation" → see trees/bushes
3. Click SPAWN on "Oak Tree" → prop appears in theater at center
4. Repeat for Quaternius Medieval Buildings → spawn a house
5. Refresh page → packs still loaded (from index.json, not localStorage)

**Phase 4 scope:** Manual download + extraction + script runs. Registry update is an MCP operational step (not frontend code).

---

## Execution Order

| Phase | Dependency | Lines | What it delivers |
|-------|-----------|-------|-----------------|
| 1 | None | 0 | Directory convention + manifest schema |
| 2 | Phase 1 | ~160 | Manifest generator scripts (Node.js) |
| 3 | Phase 1 | ~60 | Startup pack loading in frontend |
| 4 | Phases 2+3 | 0 (manual + MCP ops) | Two real packs with 90+ models in browser |

**Recommended order:** Phase 1 (convention) → Phase 2+3 in parallel (scripts + frontend) → Phase 4 (proof).

**Total new code:** ~220 lines (160 Node.js scripts + 60 frontend). Phase 4 registry updates are MCP operations, not counted as code.

---

## Testing

1. **Phase 1:** No code — review manifest.json and index.json schemas for compatibility with `_envNormalizeAssetPackManifest` (26458) and `_envGetAssetUrl` (26711).

2. **Phase 2:** Run generator on a test directory with 3 GLBs → verify manifest.json is valid, matches schema, all fields present.

3. **Phase 3:** Place a test `index.json` with one manifest URL → refresh page → pack appears in browser grid → asset count updates.

4. **Phase 4:** Full end-to-end: download Kenney Nature Kit → extract → generate manifest → generate index → refresh → browse → spawn tree → verify it renders in theater.

---

## Files Modified / Created

| File | What |
|------|------|
| `scripts/generate-pack-manifest.js` | NEW — offline manifest generator |
| `scripts/generate-pack-index.js` | NEW — offline index generator |
| `static/main.js` | ~60 lines — pack index loading on startup |
| `static/assets/packs/index.json` | NEW — generated master index |
| `static/assets/packs/*/manifest.json` | NEW — generated per-pack manifests |
| `static/assets/packs/*/` | NEW — extracted GLB files |
| `static/panel.html` | Version bump to `main.js?v=102` (line 11686) |
| `static/sw.js` | Bump `CACHE_NAME` to `champion-council-v102` (line 1) and `main.js?v=102` (line 13) |

---

## Constraints

- All code uses global `THREE` object (no ES module imports) — frontend only
- Node.js scripts are offline tooling, not shipped to browser runtime
- Manifest format must pass through `_envNormalizeAssetPackManifest` (26458) unchanged
- `asset.file` is the only field the URL resolver reads — not `asset_ref`, not `url`
- `base_url` must end with `/` for `_envGetAssetUrl` concatenation to work (26711–26720)
- Pack manifests are loaded via `fetch()` — they must be in a browser-fetchable path
- Do NOT modify `_envCc0StarterPackManifest` or `_envBuiltinAssetPackManifest` — those stay as-is
- Do NOT modify the Register Local Model or HF Search UI — those already work
- Do NOT modify agent_compiler.py or capsule code
- Bump `main.js?v=102` in panel.html (line 11686) AND `sw.js` (line 1: `CACHE_NAME` → `champion-council-v102`, line 13: `main.js?v=102`). All three must match or the SW will serve stale code

---

## Key Line References (main.js) — verified 2026-03-16

| System | Line | Function |
|--------|------|----------|
| Asset browser state | 19574 | `_envAssetBrowserState` declaration |
| Ensure builtin packs (3D init call) | 23530 | `_envEnsureBuiltinAssetPacks()` |
| Asset pack normalizer | 26428 | `_envNormalizeAssetPackAsset` |
| Pack manifest normalizer | 26458 | `_envNormalizeAssetPackManifest` |
| Find asset pack | 26474 | `_envFindAssetPack` |
| Character asset check | 26482 | `_envAssetLooksCharacterAsset` |
| Asset download state | 26497 | `_envAssetDownloadState` |
| Persist user pack | 26506 | `_envPersistUserAssetPack` |
| Restore user pack | 26514 | `_envRestoreUserAssetPack` |
| Register local model | 26526 | `_envRegisterLocalModelAsset` |
| Mutate asset in pack | 26575 | `_envMutateAssetPackAsset` |
| HF search results | 26588 | `_envRegisterHubSearchResults` |
| HF model search | 26624 | `_envSearchHubModelsForAssets` |
| HF model download | 26647 | `_envDownloadHubModelAsset` |
| Find asset record | 26667 | `_envFindAssetRecord` |
| Register asset pack | 26677 | `_envRegisterAssetPack` |
| Load manifest from URL | 26693 | `_envLoadAssetPackManifest` |
| Get asset URL | 26711 | `_envGetAssetUrl` |
| Builtin pack manifest | 26723 | `_envBuiltinAssetPackManifest` |
| CC0 starter pack | 26781 | `_envCc0StarterPackManifest` |
| Ensure builtin packs (definition) | 26875 | `_envEnsureBuiltinAssetPacks` |
| Asset browser filter | 26881 | `_envAssetBrowserFilteredAssets` |
| Render asset browser | 26925 | `_envRenderAssetBrowser` |
| Asset count display | 27004 | `count.textContent = ...` |
| Spawn from asset | 27039 | `_envSpawnFromAsset` |
| Ensure builtin packs (global call) | 31922 | `_envEnsureBuiltinAssetPacks()` |

## Key Line References (sw.js)

| System | Line | What |
|--------|------|------|
| Cache name | 1 | `CACHE_NAME = 'champion-council-v101'` — must bump to v102 |
| Bundle precache | 13 | `main.js?v=101` — must bump to v102 |

## Key Line References (panel.html)

| System | Line | What |
|--------|------|------|
| Bundle script tag | 11686 | `main.js?v=101` — must bump to v102 |

---

## Expansion Path (post-v102)

Once the proof works on 2 packs:

1. **More Kenney packs:** Medieval Fantasy (30+), City Kit (50+), Space Kit (40+), Furniture Kit (20+) = ~140 more models
2. **More Quaternius packs:** Ultimate Nature (200+), Cyberpunk (40+), Lowpoly Foods (50+) = ~290 more models
3. **KayKit packs:** Dungeon, RPG Tools, Space Base, Prototype Bits = ~100+ more models
4. **Poly Haven models:** 100+ scanned models (individual API downloads, not archives)
5. **Automated download script:** `scripts/download-pack.js` that fetches + extracts + generates manifest in one command
6. **Preview thumbnails:** Generate 128x128 previews of each model for the asset browser cards
7. **Character tagging:** Post-process manifests to tag animated/rigged models as `category: 'character'`

Target: 500+ individually spawnable models within a few more pack ingestions, 1000+ with the full Quaternius + Kenney + KayKit libraries.

---

## Transition from v101

v102 builds on top of v101's existing asset browser infrastructure. Touch points in `main.js`:
- `_envAssetBrowserState` (19574) — add `packsLoading` field
- `_envEnsureBuiltinAssetPacks` (26875) — add `_envLoadPackIndex` call
- `_envRenderAssetBrowser` count display (27004) — loading indicator
- New `_envLoadPackIndex` function + `_envPackIndexPromise` memoized var

Plus `sw.js` (lines 1, 13) and `panel.html` (line 11686) for version bumps. Everything else is new files (scripts, manifests, GLBs) and the index.json convention.

The character pipeline from v101 (inspector authoring, NPC prefabs, behavior state machine) is orthogonal to v102. They can be implemented in parallel — v102 gives the character system real models to work with.
