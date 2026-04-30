# Roots Mullet Hair Surface - 2026-04-28

## Purpose

Operationalize the "lion mane mullet beard burgeon" hair lane as a named browser/runtime surface instead of an informal caption.

## Contract

- Front: business/readability lane. The glyph message stays TECHLIT-compatible and uses negative space between roots as the readable carrier.
- Back: party/mane lane. Rear visual mass is biased toward lion-mane counterweight and visible sweep.
- Lower face: beard-burgeon lane. Current implementation carries this as explicit silhouette intent and caption metadata; a future slot-level beard mesh can bind to the same preset.
- Roots: grounding metaphor and technical anchor. The preset keeps root-lock/saiyan semantics instead of replacing them.

## Runtime Entry Points

- `window.envopsSetRootsMulletHair()`
- `window.envopsSetHairMullet()`
- `window.envopsSetHairPreset('roots_mullet_lion_mane_beard')`
- `window.envopsSetHairPreset('techlitty_saiyan_mullet')`

## Verification

- `env_help(topic='techlit_hair_control_surface')`
- `env_help(topic='hair_granulation_surface')`
- `env_read(query='text_theater_embodiment')`
- `env_read(query='text_theater_snapshot')`

## Current Boundary

This is a browser runtime surface. The patched hook becomes live after the web theater reloads the updated `static/main.js`. If the browser is still running an old bundle, `env_help` may know the hook while `window.envopsSetRootsMulletHair` is absent until reload.
