# Opus Corrected Trajectory Report 2026-04-13

Repo: `F:\End-Game\champion_councl`

This report replaces:

- `docs/OPUS_REACCLIMATION_HANDOFF_2026-04-13.md`
- `docs/OPUS_SITREP_2026-04-13_BLACKBOARD_VITRUVIAN_ALIGNMENT.md`

Purpose:

- give Opus one corrected handoff
- remove the bad blackboard/web pairing rule from the prior writeups
- keep the next trajectory grounded in the current source, current runtime findings, and the user's actual direction

Constraints:

- no capsule edits
- no duplicate or parallel authority systems
- do not invent a new architecture where the repo already has one
- repair existing systems before adding new surfaces

## 1. Corrected execution rule

The blackboard system is for **text theater only**.

That is the active rule.

Do not treat blackboard as a permanently paired web-theater surface.

If text appears in the web theater later, it should be treated as:

- a selective special effect
- a selective measurement overlay
- or a selective text-rendered object

It is **not** a constant always-on paired mirror of the text theater blackboard.

So the correct surface split is:

- blackboard -> text theater
- web theater text -> occasional special-effect / measurement / object rendering

That correction replaces the earlier bad framing.

## 2. Current grounded truth

### 2.1 Current Dreamer/calibration state

Outer Dreamer work in `server.py` is still real:

- mechanics observation endpoint
- proposal preview
- episode step/reset
- transform relay
- bounded sweep

The capsule remains untouched.

The current debug line is still:

- repair calibration truth
- repair kneel-route truth
- only then build higher observability surfaces on top

### 2.2 The neutral/reset correction

The recent wrong turn was treating `workbench_reset_angles` as the neutral pose.

That is false.

Verified in `static/main.js`:

- `workbench_reset_angles` is structure-mode builder-angle reset at [static/main.js](../static/main.js:20363)
- active embodied pose lives in builder pose state at [static/main.js](../static/main.js:1726)
- `workbench_set_pose_batch` edits pose transforms at [static/main.js](../static/main.js:19576)
- `workbench_apply_pose_macro` applies macros through the pose layer at [static/main.js](../static/main.js:20183)

The live verification that mattered:

- `workbench_clear_pose {"all": true}` clears the active embodied pose layer and returns the body to standing neutral

So the neutral-anchor repair still needed is:

- use pose clearing as the embodied neutral reset
- do not confuse scaffold-angle reset with embodied neutral pose

### 2.3 The kneel/contact problem

The current kneel is still biased toward a minimalist shortest-path brace solve.

Verified in `static/main.js`:

- `half_kneel` route targets are `leadKnee` and `anchorFoot` at [static/main.js](../static/main.js:1508)
- `half_kneel_l_topology` makes `lower_leg_l` the leader and `foot_r` the anchor at [static/main.js](../static/main.js:5262)
- the knee patch is derived directly from the lower-leg-to-foot axis at [static/main.js](../static/main.js:2716)
- grounded knees are forced into brace semantics at [static/main.js](../static/main.js:4458)
- lower-leg motion is tightly clamped at [static/main.js](../static/main.js:1650)

The current system has:

- joint limits
- contact patches
- support polygon / CoM / load-field diagnostics

It does **not** yet have:

- whole-chain corridor guidance
- limb-vs-limb self-blocking
- torso-vs-leg body clearance logic

So the current system solves:

- compact knee-brace contact

more than:

- a valid whole-chain kneel transition

## 3. What the Vitruvian idea actually maps to

The user's "Vitruvian Man" idea should be read as:

- a text-theater observability surface
- built from existing articulation / diagnostics truth
- showing range, gates, guide tracks, and measured state

It should **not** be treated as:

- a second control plane
- a second blackboard
- a constant web mirror of the text-theater blackboard

The useful existing source/doc alignment is:

### 3.1 Blackboard is already the text-theater diagnostic bridge

From [TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md](TEXT_THEATER_BLACKBOARD_SPEC_2026-04-09.md:10):

- the text theater is being reframed into a diagnostic blackboard
- the blackboard is structured data first, rendered surface second

From source:

- blackboard state is built in `static/main.js` at [static/main.js](../static/main.js:31207)
- text theater already has blackboard and profile render sections in [scripts/text_theater.py](../scripts/text_theater.py:1021) and [scripts/text_theater.py](../scripts/text_theater.py:1043)

So the current Vitruvian direction belongs first in the text-theater blackboard path.

### 3.2 Glyph orientation and articulation docs already cover the right kind of text rendering

Relevant docs already exist:

- [TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md](TEXT_THEATER_GLYPH_ORIENTATION_SURFACE_SPEC_2026-04-11.md:42)
- [TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md](TEXT_THEATER_GLYPH_ARTICULATION_MAPPING_2026-04-11.md:41)

These already describe:

- text/glyphs as orientation-bearing primitives
- articulation authority already existing elsewhere
- glyph consumers being derived from existing articulation truth

That fits the user's request:

- range annotations
- guide tracks
- visible movement corridors
- measured orientation in text form

### 3.3 The web-theater text path should remain special-purpose

There are already web-overlay and profile concepts in `static/main.js`, but for this trajectory the user has now clarified the rule:

- text on the web theater is a special effect or selective measurement/object surface
- not the permanent paired blackboard reality

That means future web text work should stay:

- episodic
- purpose-built
- novelty-preserving

not a constant full blackboard mirror.

## 4. What should happen next

This is the corrected order.

### Step 1. Repair calibration truth first

- repair the neutral-anchor path around the true embodied neutral reset
- revalidate transform relay and bounded sweep from that anchor
- keep this on the current Dreamer/kneel debug line

### Step 2. Repair the kneel-route truth

Audit and repair the minimal pieces that are over-biasing the kneel toward compact brace contact:

- route targets
- topology weighting
- knee patch assumptions
- knee brace semantics

The goal is not to replace the route system.

The goal is to stop it from solving kneel mainly as "knee down fast with minimal chain reorganization."

### Step 3. Keep the Vitruvian work in the text-theater lane first

Once calibration truth and kneel-route truth are good enough:

- define the smallest text-theater blackboard contract for range/gate visibility
- let text theater render:
  - guide tracks
  - gate sectors
  - range corridors
  - planned vs realized path hints
  - measured articulation context

This is the first true Vitruvian-style surface.

### Step 4. Defer web text until it has a specific effect purpose

If web theater later uses text rendering, it should be because a specific surface deserves it:

- a measurement overlay
- a selected diagnostic object
- a heads-up special effect

Not because the text-theater blackboard must always be mirrored there.

## 5. What to defer

Defer:

- any new paired blackboard/web doctrine
- any attempt to make text theater and web theater permanent mirrored twins
- any new control plane for glyphs or Vitruvian overlays
- any broad Dreamer retune before calibration truth is stable

## 6. Questions for Opus

The next Opus report should answer:

1. What is the smallest truthful repair to the neutral-anchor calibration path now that embodied neutral reset is a pose-layer concern, not just a structure-angle reset?
2. Which kneel-route pieces should be repaired first to break the shortest-path brace bias with minimal blast radius?
3. What is the smallest text-theater blackboard contract for a first Vitruvian-style range/gate surface?
4. Which existing glyph-orientation / glyph-articulation pieces are immediately useful for that text-theater surface, and which should stay deferred?
5. What should remain web-theater-only special effects later, rather than becoming permanent blackboard mirrors?

## 7. Bottom line

The correction is simple:

- blackboard belongs to text theater
- web text is a selective effect, not a constant pair
- calibration truth and kneel-route truth still come first
- the Vitruvian idea should grow out of the text-theater blackboard path after those repairs, not alongside a new mirror system
