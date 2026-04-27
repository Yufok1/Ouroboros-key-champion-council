# Cube Robot Recursive Embodiment Spec 2026-04-11

Status: Draft  
Scope: Parallel robotics substrate / builder test body  
Purpose: Define a mechanically explicit reference body that can drive workbench sequencing, support-transfer reasoning, blackboard diagnostics, and future recursive embodiment research.

## Core Thesis

Treat the Rubik-style `3 x 3 x 3` cube as a **reconfigurable robotics substrate**, not as a puzzle.

The parent cube is:

- a dense stored body
- a load-bearing lattice
- a chain/scaffold deployer
- a tool-body that can spend its own volume as limbs, supports, and fine distal agency

The recursive idea is the north star:

- each parent cell can itself be a smaller cube robot
- coarse scale handles gross reach, support, and body form
- fine scale handles contact detail, manipulation, and precision embodiment

Do **not** treat the literal Rubik toy mechanism as the final hardware.  
Keep the topology and the adjacency logic. Engineer the real couplers as robotics joints, locks, buses, and deployment surfaces.

## Productive Use In Champion Council

This is useful now because it is a more explicit mechanics body than the humanoid.

It forces the stack to handle:

- joint locking vs articulation
- support transfer
- deployment sequencing
- load redistribution
- coarse-to-fine embodiment
- body-as-tool reasoning

This makes it a strong parallel facility while the humanoid mechanics lane continues.

## V0 North-Star Image

The coolest basic form is not the stored cube. The coolest basic form is:

- parent cube fully unraveled
- selected parent cells deployed into body branches
- recursive child-cube deployment used as finer legs, feet, tendrils, or tool fingers
- weight redistributed dynamically through re-locking and re-anchoring the body

The reference mental model is:

- **stored mode**: compact cube
- **deployed mode**: insect-like or surgeon-tool-like articulated body

The insect interpretation is mechanically useful because it demands:

- many support legs
- low center of mass
- continuous redistribution of load
- mixed rigid and compliant distal structures

## Doctrine

1. The parent cube is the first real robot body. Recursive children are deferred until the parent mechanics are coherent.
2. Face surfaces are first-class embodiment surfaces, not decoration.
3. Locks, couplers, and support truth matter more than visual skin.
4. Builder and blackboard should reason about this body mechanically, not anthropomorphically.
5. Recursive child cubes are for later finer embodiment, not an excuse to skip parent-level mechanics.

## Parent Body Topology

The parent body is a `3 x 3 x 3` lattice:

- `27` cell positions
- `8` corners
- `12` edges
- `6` face centers
- `1` core

Role split:

- `core`
  - bus root
  - global load collector
  - reconfiguration scheduler anchor
- `face`
  - surface deployment
  - tool-face or support-face
  - main interface for outward task geometry
- `edge`
  - chain turn, branch elbow, and load path redirect
- `corner`
  - distal branch root, tripod/insect stance anchor, aggressive orientation change point

## Mechanical Interpretation

Every neighboring cell pair is joined by a robotics coupler with at least these conceptual facilities:

- rotational articulation
- rigid lock
- power/data pass-through
- load-state measurement
- orientation sensing

Optional later facilities:

- telescoping offset
- quick detach
- compliant micro-flex
- child-cube deployment hatch

This is not a free ragdoll.  
The important state is whether a link is:

- locked
- rotating
- weight-bearing
- unloaded
- acting as deployment root

## Embodiment Surfaces

Each outward face of each cell is an embodiment surface that can act as:

- support pad
- contact patch
- sensor face
- tool face
- child deployment face
- structural shield

This gives the cube robot an explicit surface-based body language:

- face-down surfaces become supports
- face-forward surfaces become tools/sensors
- face-out surfaces become armor/shields
- opened faces become recursive deployment ports

## First Transformation Modes

These are the first believable parent-body modes.

### 1. Compact Cube

- all parent cells densely packed
- maximum protection
- maximum storage density
- minimum reach

### 2. Spine Chain

- parent cube unraveled into a single articulated chain
- useful for reach, threading, and gross manipulation
- simplest deployment benchmark

### 3. Elbow Arm

- parent cube deploys into a bent manipulator with rigid proximal segment and freer distal segment
- useful for basic tool-body behavior

### 4. Tripod Scaffold

- three support branches lock down
- remaining body becomes active work volume
- useful for load-transfer and support reasoning

### 5. Insect Body

- body center retained as thorax/abdomen mass
- multiple branches deployed as legs
- later recursive child cubes provide finer distal legs/feet

This is the first north-star morphology worth simulating.

## Recursive Scaling Plan

### Parent Scale

- gross body position
- load routing
- major branch deployment
- support topology choice

### Child Scale

- distal leg segmentation
- local contact shaping
- fine reach inside constrained spaces
- tool-tip refinement

### Grandchild Scale

- tactile/surgical micro-adjustment
- surface following
- micro-manipulation

Important constraint:

- do **not** build full recursion at all 27 cells first
- start with selected deployment cells only

## Champion Council V0 Scope

`cube_robot_v0` starts as a **parent-only** body.

It includes:

- a `27`-cell topology
- explicit role map
- adjacency map
- first deployment recipes
- blackboard/report rows for lock/support/load/phase state

It does **not** yet include:

- fully recursive child cubes in every cell
- literal surgery tooling
- autonomous self-repair
- arbitrary programmable matter behavior

## Builder / Workbench Mapping

Treat the cube robot as a workbench mechanics surrogate.

Map these concepts into the existing stack:

- cell = controllable body unit
- coupler = joint/lock relationship
- deployment recipe = support topology / route sequence
- face surface = contact/support/tool surface
- stored/deployed states = pose macro families

The workbench should eventually support:

- selecting cells or cell groups
- selecting couplers
- locking/unlocking links
- staging deployment sequences
- asserting load and support truth
- reading route/blocker/next state through text theater and blackboard

## Blackboard Rows Needed

The first cube body should emit rows like:

- `cube.mode`
- `cube.phase`
- `cube.topology`
- `cube.lock_state`
- `cube.support_set`
- `cube.load_path`
- `cube.deployment_root`
- `cube.overloaded_cells`
- `cube.free_cells`
- `cube.recursion_ports`

These should follow the same doctrine as the current blackboard:

- stable row ids
- explicit family/layer/source
- anchors back to cells/couplers
- route and support truth exposed as readable data

## First Sequencing Questions

The first real mechanics questions are:

1. How does compact cube become chain without losing load truth?
2. Which cells stay locked as the structural spine while others become free movers?
3. How do support cells hand off load during deployment?
4. Which corners/edges are best as leg roots?
5. Where do recursive child deployments eventually emerge without destabilizing the parent body?

## First Real Milestone

The first milestone is not "full recursive cube insect."

It is:

**A parent `27`-cell cube that can transition between compact, chain, elbow, tripod, and early insect-like stance while exposing readable lock/support/load/phase truth.**

If that works, the recursive child-body idea becomes worth pursuing seriously.
