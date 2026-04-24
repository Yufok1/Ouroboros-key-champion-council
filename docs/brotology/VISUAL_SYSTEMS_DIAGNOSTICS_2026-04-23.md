# Visual Systems Diagnostics

Date: 2026-04-23
Repo: `D:\End-Game\champion_councl`
Status: active diagram and diagnostics note
Mode: `plain_to_engineering_visual_read`

## Purpose

Give the current planning lane one disciplined diagram grammar and one diagnostic checklist that can survive translation:

- from caveman scientist
- to field operator
- to rocket scientist

## Bottom Line

If a diagram cannot show all six of these, it is not ready:

1. where the mass is
2. where the pivot is
3. where the charge comes from
4. where the motion goes
5. where the catch / return happens
6. who benefits or stays safe

## Register Ladder

| Register | What they need to understand | What the figure must show |
|---|---|---|
| `caveman scientist` | big thing stores pull, small thing releases it, safe cave stays safe | big mass, little trigger, safe zone |
| `field operator` | charge, hold, release, catch, service split, public value | cycle path, band split, receivers |
| `rocket scientist` | inertial members, coupling, damping, hazard envelope, utility receiver, failure gate | pivots, ranges, loads, reserves, lockouts |

## Canonical Figure Set

Every serious packet should eventually contain these five figures:

1. `cross_section`
   Basin / span / service-depth cutaway.
2. `motion_cycle`
   Charge, hold, trigger, release, catch, return, recharge.
3. `panel_cascade`
   Inner heavy member to outer visible panel relation.
4. `band_split`
   Clean occupancy versus dirty/service bands.
5. `value_path`
   Public receivers and peril-mode lattice translation.

## Example Cross-Section

```text
rim anchor ---------------- primary span ---------------- rim anchor
                   \            |            /
                    \       spine pivot     /
                     \          |          /
                      \    carrier arm    /
                       \        |        /
                        \  relay segment/
                         \      |      /
                          \  panel   /
                           \  leaf  /
                            \     /
                         service void
                    [clean band] [dirty band]
                         |             |
                   public outputs   recovery / recharge
```

## Figure Legend

Use a simple legend consistently:

- `[square brackets]` = zones or bands
- `(parentheses)` = pivots or joints
- `-->` = directional flow
- `====` = primary span or main structure
- `////` = exclusion or hazard area
- `++++` = charge / reserve area

## Diagnostic Pass

Run this pass on every new diagram:

1. `truth pass`
   Does it show actual mechanism or only silhouette?
2. `energy pass`
   Does it show charge and recharge?
3. `safety pass`
   Does it show who stays clear and where?
4. `utility pass`
   Does it show who benefits?
5. `failure pass`
   Does it show what happens when the cycle fails?

## Common Bad Figures

Reject drawings that do any of these:

- show motion with no charge source
- show release with no catch path
- show panels with no pivots
- show people standing inside sweep envelopes
- show giant civic claims with no receiver nodes

## Current Recommendation

The next best diagram pack for this lane is:

1. one `canyon_span_slice` cross-section
2. one `release_valve_cycle`
3. one `brohandoskygivingfacility` cutaway
4. one `civic_protection_lattice` node map

## Related Canon

- `docs/brotology/OPERATIONAL_SURFACE_2026-04-23.md`
- `docs/brotology/ATRAI_VESSEL_FIELD_BRIEF_2026-04-23.md`
- `docs/brotology/BROHANDOSKYGIVINGFACILITY_FIELD_CONCEPT_2026-04-23.md`
- `docs/brotology/CIVIC_PROTECTION_LATTICE_SPEC_2026-04-23.md`
- `docs/brotology/HIGH_YIELD_BROSPECULATION_CANYON_SPAN_SIMULATION_PRIMITIVES_REPORT_2026-04-23.md`
