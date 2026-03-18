# Asset Ingestion Pipeline

This document describes the current photoreal asset ingestion flow for the environment runtime, with the `v117` historical-world expansion model.

## Flow

1. Choose a source and verify the asset terms before download.
2. Preserve source-native `glb` / `gltf` when possible.
3. Convert `fbx` assets manually in Blender when needed.
4. Place the converted assets in a dedicated pack folder under `static/assets/packs/`.
5. Run `scripts/generate-pack-manifest.js` for that pack.
6. Run `scripts/generate-pack-index.js` to refresh the master pack index.
7. Verify that the manifest carries usable `category`, `tags`, `kind`, and `scale_hint` fields before the assets are spawned in the browser.

## Source To Pack

| Source | Typical terms | Native format | Conversion path | Intended pack pattern |
| --- | --- | --- | --- | --- |
| Poly Haven | CC0 | glTF | direct | `polyhaven-{collection}/` |
| Sketchfab CC0 / CC-BY | verify per asset | glTF / glb / FBX / OBJ | direct when glTF/glb, otherwise Blender to GLB | `sketchfab-{collection}/` |
| Smithsonian Open Access 3D | CC0 on marked items | web 3D / downloadable model payloads | normalize and export to GLB when needed | `smithsonian-open-access/` |
| Renderpeople free models | commercial-use allowed, redistribution constrained | FBX / GLB / OBJ depending product family | Blender to GLB for internal runtime use | `renderpeople-free-internal/` |
| ActorCore / AccuRIG free content | verify export and redistribution per asset | FBX / USD / iAvatar | Blender to GLB for runtime packs | `actorcore-free/` |
| Mixamo motions | Adobe-account workflow, verify use case | FBX | keep as motion source, retarget manually | `mixamo-motions/` |

## Pack-Native Categories vs Canonical Taxonomy

Pack manifests already carry pack-native categories such as:

- `ships`
- `structures`
- `props`
- `character`
- `nature`
- `rocks`
- `containers`
- `decorative`
- `furniture`
- `industrial`
- `lighting`

These values do not need rewriting.

The runtime maps those pack-native categories into canonical taxonomy classes at load time. Taxonomy is used for scale reasoning and scene-authoring guidance. It is not a manifest migration system.

Canonical classes currently include:

- `ships`
- `harbor_structures`
- `coastal_hazards`
- `roman_architecture`
- `roman_props`
- `historical_architecture`
- `historical_vessels`
- `historical_props`
- `humans`
- `creatures`
- `reef_underwater`
- `vegetation`
- `small_props`

## Multi-Axis Tags

The taxonomy class controls broad structural behavior. Historical richness lives in additive tags.

Recommended additive tag axes:

- `era`
- `region`
- `culture`
- `domain`
- `material`
- `environment`
- `function`

Example values:

- `era`: `antiquity`, `medieval`, `renaissance`, `age_of_sail`, `colonial`, `industrial`, `modern`
- `region`: `mediterranean`, `northern_europe`, `middle_east`, `south_asia`, `east_asia`, `pacific`, `mesoamerica`
- `culture`: `roman`, `greek`, `egyptian`, `viking`, `persian`, `chinese`, `japanese`, `polynesian`, `arab`
- `domain`: `maritime`, `architecture`, `military`, `trade`, `domestic`, `religious`, `agricultural`
- `environment`: `port`, `market`, `farm`, `desert`, `delta`, `jungle`, `steppe`, `mountain`, `reef`, `river`, `island`, `urban`, `ruins`, `underwater`, `coastal`
- `function`: `vessel`, `weapon`, `armor`, `tool`, `furniture`, `container`, `structure`, `decoration`, `religious_object`

These tags are additive. They do not replace the manifest category.

## Required Manifest Fields

Every manifest asset entry should include:

- `id`
- `file`
- `name`
- `category`
- `tags`
- `kind`
- `scale_hint`
- `data.source` when available

`tags` should include:

- taxonomy-relevant form/function cues
- historical tags when known
- environment cues when useful for scene audit

Examples:

- `['ships', 'naval', 'age_of_sail', 'dutch', 'maritime', 'vessel']`
- `['ships', 'historical_vessels', 'greek', 'antiquity', 'mediterranean', 'maritime', 'military', 'vessel']`
- `['historical_architecture', 'egyptian', 'antiquity', 'north_africa', 'architecture', 'religious', 'stone']`
- `['reef_underwater', 'underwater', 'reef', 'coral', 'coastal']`

## FBX To GLB Manual Steps

1. Import the source FBX into Blender.
2. Confirm unit scale, orientation, and armature transforms.
3. Reconnect textures if the FBX importer does not wire them automatically.
4. Pack or embed textures when practical for runtime portability.
5. Export as GLB with animations enabled when the asset includes skeletal motion.
6. Place the exported file in the target pack directory.
7. Regenerate the pack manifest and master index.

## Historical World Lanes

`v117` broadens the content program beyond any single civilization. New ingested assets should be slotted into one or more of these lanes:

- `historical_maritime`
- `historical_architecture`
- `historical_people`
- `historical_props`
- `historical_environments`

These lanes are documentation and procurement buckets. Runtime taxonomy still resolves primarily from form and function.

## Runtime Notes

- `category` and `tags` propagate from `_envNormalizeAssetPackAsset` through `_envSpawnFromAsset`.
- The taxonomy resolver is backward-compatible with existing manifests.
- Culture, era, and region tags are for filtering, documentation, and procurement discipline. They do not override structural taxonomy class resolution.
- Scene audit warnings are advisory only and should not block spawn or mutate persisted scene data.
