# Owned Surface Click/Input/Submit Validation — 2026-03-13

## Purpose

Close the remaining owned-HTML validation gap for:

- `surface_click`
- `surface_input`
- `surface_submit`

using a real persisted surface with actual tabs, inputs, and a submit path.

## Validation surface used

Persisted panel:

- object key: `panel::temp-html-form-lab`
- label: `Surface Form Lab`
- meta: `owned-html click input submit validation surface`
- mode: `surface-card`
- source type: owned HTML / `srcdoc`

The panel contains:

- tab targets:
  - `overview`
  - `form`
  - `submitted`
- text input:
  - `fighter_name`
- select input:
  - `weapon_choice`
- checkbox input:
  - `crowd_favor`
- form:
  - `surface-diagnostic-form`
- submit button:
  - `submit_roster`

Submit route behavior is intentionally simple and deterministic:

- form submit triggers a click on `tab-submitted`
- resulting active tab / section becomes `submitted`

## Live validation results

### 1) `surface_click`

Command target payload:

```json
{"surface":"temp-html-form-lab","target":"form"}
```

Observed live bridge state after sync:

- `active_tab: form`
- `active_section: form`
- `last_command: surface_click`
- `last_target: form`
- `last_ok: true`
- live `synced_at: 1773431539.1085014`

Result:

- shell-driven click succeeded
- active panel state moved from `overview` to `form`

### 2) `surface_input`

Command target payload:

```json
{"surface":"temp-html-form-lab","target":"fighter_name","value":"Tetraites"}
```

Observed live bridge state after sync:

- `active_tab: form`
- `active_section: form`
- `last_command: surface_input`
- `last_target: fighter_name`
- `last_ok: true`
- live `synced_at: 1773431593.296088`

Result:

- shell-driven input routing succeeded against a real named field
- bridge acknowledged the input command on the correct target

### 3) `surface_submit`

Command target payload:

```json
{"surface":"temp-html-form-lab","target":"surface-diagnostic-form"}
```

Observed live bridge state after sync:

- `active_tab: submitted`
- `active_section: submitted`
- `last_command: surface_submit`
- `last_target: surface-diagnostic-form`
- `last_ok: true`
- live `synced_at: 1773431623.7439306`

Result:

- shell-driven submit succeeded
- submit route advanced the owned surface into the `submitted` state

## Conclusion

The previously unresolved owned-surface controls are now honestly validated on a real form-capable surface:

- `surface_click` — validated
- `surface_input` — validated
- `surface_submit` — validated

## Important interpretation

This pass did **not** require a frontend source patch to validate the bridge path.

The immediate blocker was primarily the lack of a proper owned test surface with:

- a real clickable tab target
- a real input field
- a real submit path

Once that surface existed and was hydrated/opened as the active owned HTML panel, the current bridge path validated successfully.

## Cleanup / artifacts

Kept:

- `panel::temp-html-form-lab` as a reusable owned-surface validation object

Removed:

- `panel::spawn-test`
  - this was only a temporary JSON/HTML quoting sanity-check object used while getting the form-lab panel spawned

## Remaining separate issues

These remain separate from click/input/submit validation:

- environment/council parity is still not trustworthy for slot/provider truth
  - example: stale synthetic `slot::0` representation still conflicts with live council truth
- panel-focus composition / clipped label issue remains cosmetic/live-layout work

## Practical next step

Move back to the next tactical layer:

1. tighten env/council parity for slot/provider truth
2. keep `temp-html-form-lab` available as a regression surface for future bridge changes
3. use the newly completed validation result as the tactical baseline for typed surface work
