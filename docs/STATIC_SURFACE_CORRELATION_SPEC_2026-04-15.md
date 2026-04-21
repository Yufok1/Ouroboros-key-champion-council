# Static Surface Correlation Spec 2026-04-15

Repo: `D:\End-Game\champion_councl`

Purpose:

- define the next environment/body correlation pivot after point-contact truth
- reuse existing part-surface and support/contact primitives for static environments
- keep completed model grounding honest without collapsing everything into point contacts only

## Bottom Line

The current substrate already knows a lot about ground/contact interaction:

- `support_polygon`
- `support_polygon_world`
- `contact_patch`
- `support_y`
- `selected_part_surface`
- `part_camera_recipes`
- `workbench_set_pose_batch`
- `workbench_stage_contact`

That means the next honest step for static environments is not "invent better ground."

It is to correlate total surface against point-contact truth.

## The Shift

Point contacts answer:

- where load currently bears
- where contact is missing
- whether support is real or blocked

Total-surface correlation answers:

- how the broader body surface relates to the environment plane
- whether a completed model is coherently oriented across its full contacting region
- whether static fit, altitude, and orientation should be solved by more than a few sparse points

## Local Translation

The clean local bridge is:

- point truth from `contact_patch` and support records
- body/part extent from `selected_part_surface`
- coordinated mutation from `workbench_set_pose_batch`

This lets the system ask:

- does the total relevant body surface agree with the current contact set?
- are the points representative of the whole surface?
- should the next correction operate on a surface zone rather than one contact point?

## First Honest Slice

Do not jump straight to full environmental deformation.

First add a correlation layer that can summarize:

- selected/active part surface
- nearby support plane or static surface
- alignment score / altitude delta / orientation delta
- whether point contacts are representative or misleading

This becomes a read/diagnostic layer first.

## Relation To Pan

Static surface correlation is not Pan itself.

It is a prerequisite enrichment for Pan and support-field work:

- Pan routes support changes over truthful body/world correlation
- support-field procgen can answer the correlation result
- point contacts remain the acceptance gate

## Local Rule

Use the existing substrate:

- no second pose system
- no second terrain truth
- no bypass around `workbench_set_pose_batch`
- no bypass around `workbench_stage_contact`

Correlation deepens the same truth lane.
