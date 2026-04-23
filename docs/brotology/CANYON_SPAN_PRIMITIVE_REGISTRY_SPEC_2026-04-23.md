# Canyon-Span Primitive Registry Spec

Date: 2026-04-23
Repo: `D:\End-Game\champion_councl`
Status: active planning spec
Mode: `registry_first`

## Purpose

Define the canonical primitive registry for the first kinetic-architecture simulation facility.

This is the first planning artifact after the dossier because it converts imagery into named bodies, joints, bands, and observers.

This spec is for:

- the `canyon_span_slice` facility
- the `momentum_lobby_demonstrator` precursor where applicable
- later `carrier_fortress` translation by extension, not by premature scope explosion

## Continuity Grounding

Read with:

- `docs/brotology/CARRIER_FORTRESS_CANYON_SPAN_PLANNING_DOSSIER_2026-04-23.md`
- `docs/brotology/HIGH_YIELD_BROSPECULATION_CANYON_SPAN_SIMULATION_PRIMITIVES_REPORT_2026-04-23.md`
- `docs/ETRIGAN_OPERATIONS_FIELD_BRIEF_2026-04-17.md`
- `docs/PHYSICAL_DIAGNOSTIC_FACILITY_OF_FACILITIES_BLUEPRINT_2026-04-18.md`
- `docs/REACTIVE_MOBILITY_PRIMITIVES_TRAJECTORY_2026-04-10.md`
- `docs/VITRUVIAN_REACH_ENVELOPE_MIME_SURFACE_PLAN_2026-04-21.md`

## Active Default Posture

Until revised:

- `site_grammar = open_pit_mine`
- `motion_grammar = switchback_relay`
- `proof_target = outer_panel_wave`
- `scale_posture = lobby_proof`

## Registry Law

1. Every primitive must have one canonical `id`, one `kind`, and one bounded role.
2. Visual spectacle is downstream of structural truth.
3. `micro_sequencer` is a trigger, not the prime mover.
4. Every charged motion must name its `charge_bank` and `catch_path`.
5. Every utility claim must name a real `sink`.
6. The registry is allowed to be ambitious, not vague.

## Canonical Object Shape

Every primitive row should be representable as:

```json
{
  "id": "string",
  "kind": "string",
  "label": "string",
  "band": "string",
  "state": "planned|armed|active|caught|recovering|faulted",
  "geometry_ref": "string",
  "parent_id": "string",
  "tags": ["string"],
  "params": {},
  "observability": {},
  "notes": "string"
}
```

## Primitive Families

### 1. Site Primitives

These define the basin and the standing geometry around the moving machine.

| Kind | Required params | Units |
|---|---|---|
| `basin_profile` | `depth`, `rim_width`, `shelf_count`, `cross_section_family` | `m`, count |
| `rim_anchor` | `x`, `y`, `z`, `anchor_class`, `capacity` | `m`, `kN` |
| `terrace_shelf` | `elevation`, `depth`, `width`, `shelf_role` | `m` |
| `service_void` | `depth`, `width`, `clearance_height` | `m` |
| `shaft` | `depth`, `diameter`, `shaft_role` | `m` |
| `subsurface_band` | `band_role`, `elevation_min`, `elevation_max` | `m` |

### 2. Structural Primitives

These are the large physical members.

| Kind | Required params | Units |
|---|---|---|
| `primary_span` | `span_length`, `mass`, `stiffness_class` | `m`, `kg` |
| `spine_pivot` | `pivot_axis`, `max_rotation`, `bearing_class` | axis, `deg` |
| `carrier_arm` | `arm_length`, `mass`, `moment_class` | `m`, `kg` |
| `relay_segment` | `segment_index`, `length`, `mass`, `phase_offset` | count, `m`, `kg`, `deg` |
| `panel_leaf` | `panel_area`, `mass`, `sweep_angle`, `panel_role` | `m2`, `kg`, `deg` |
| `anchor_truss` | `span`, `load_class`, `truss_family` | `m`, class |
| `guide_rail` | `path_length`, `rail_family`, `travel_limit` | `m` |
| `counterweight_carriage` | `mass`, `travel_range`, `carriage_role` | `kg`, `m` |

### 3. Joint And Transmission Primitives

These connect and time the members.

| Kind | Required params | Units |
|---|---|---|
| `hinge_joint` | `axis`, `range_min`, `range_max` | axis, `deg` |
| `torsion_joint` | `torsion_rate`, `preload` | relative, `N*m` |
| `clutch` | `engage_threshold`, `release_threshold` | `N*m` or relative |
| `brake` | `brake_gain`, `heat_limit` | relative, thermal units |
| `ratchet` | `step_angle`, `direction` | `deg` |
| `tension_member` | `length`, `tension_limit`, `member_family` | `m`, `N` |
| `damper` | `damping_rate`, `stroke_limit` | relative, `m` |
| `gear_ratio` | `input_id`, `output_id`, `ratio` | ids, scalar |

### 4. Dynamic Primitives

These carry the motion logic.

| Kind | Required params | Units |
|---|---|---|
| `mass_node` | `mass`, `inertia_class`, `com_offset` | `kg`, class, `m` |
| `phase_offset` | `angle`, `timing_family` | `deg` |
| `stroke_profile` | `charge_ms`, `release_ms`, `crest_ms`, `return_ms` | `ms` |
| `rebound_gain` | `gain` | scalar |
| `crest_condition` | `angle_threshold`, `velocity_threshold` | `deg`, `deg/s` |
| `settle_window` | `max_vibration`, `settle_ms` | amplitude, `ms` |
| `lock_window` | `capture_angle_min`, `capture_angle_max` | `deg` |
| `fault_latch` | `fault_class`, `trip_threshold` | class, scalar |

### 5. Envelope And Safety Primitives

These define admissibility.

| Kind | Required params | Units |
|---|---|---|
| `range_gate` | `range_min`, `range_max`, `gate_role` | `deg` or `m` |
| `clearance_envelope` | `volume_family`, `clearance_min` | family, `m` |
| `reach_envelope` | `sweep_radius`, `sweep_angle`, `envelope_role` | `m`, `deg` |
| `load_limit` | `max_force`, `max_torque` | `N`, `N*m` |
| `oscillation_limit` | `max_amplitude`, `max_frequency` | `deg`, `Hz` |
| `service_exclusion_zone` | `zone_family`, `clear_condition` | family, state |
| `occupancy_zone` | `zone_family`, `human_safe_only` | family, bool |
| `quarantine_load` | `quarantine_reason`, `release_condition` | text |

### 6. Service-Architecture Primitives

These make the machine into a building system instead of a kinetic toy.

| Kind | Required params | Units |
|---|---|---|
| `transfer_floor` | `floor_role`, `capacity`, `transfer_direction` | class, count or `kg` |
| `maintenance_dock` | `dock_role`, `service_capacity` | class, count |
| `swap_bay` | `bay_family`, `module_capacity` | family, count |
| `recovery_lane` | `lane_role`, `lane_length` | class, `m` |
| `inspection_gate` | `gate_role`, `pass_condition` | class, state |
| `clean_band` | `band_role`, `occupancy_class` | class |
| `dirty_band` | `band_role`, `process_class` | class |

### 7. Observation Primitives

These are the first honest dashboard surfaces.

| Kind | Required params | Units |
|---|---|---|
| `load_probe` | `target_id`, `read_family` | id, class |
| `angle_probe` | `target_id`, `axis` | id, axis |
| `deflection_probe` | `target_id`, `baseline_ref` | id, ref |
| `vibration_probe` | `target_id`, `sampling_hz` | id, `Hz` |
| `wind_probe` | `zone_id`, `sampling_hz` | id, `Hz` |
| `trajectory_correlator` | `plan_ref`, `actual_ref`, `grade_scale` | refs |
| `output_state` | `orientation_id`, `summary_ref` | id, ref |
| `pan_probe` | `selected_target`, `measurement_role` | id, class |

### 8. Trigger And Utility Primitives

These connect theatrical motion to real plant logic.

| Kind | Required params | Units |
|---|---|---|
| `micro_sequencer` | `trigger_target`, `trigger_mode`, `timing_ms` | id, class, `ms` |
| `latch_state` | `latch_role`, `armed`, `caught` | class, bool, bool |
| `charge_bank` | `bank_family`, `stored_energy_class`, `recharge_path` | class, class, ref |
| `thermal_plant` | `plant_family`, `thermal_output_class` | class, class |
| `water_head` | `head_height`, `flow_class` | `m`, class |
| `process_sink` | `sink_family`, `demand_class`, `duty_cycle` | class, class, class |
| `habitation_sink` | `sink_family`, `comfort_role`, `duty_cycle` | class, class, class |
| `utility_bus` | `bus_role`, `source_ids`, `sink_ids` | class, ids |

## Minimum Facility Graph

V1 `canyon_span_slice` should contain at minimum:

- `1 basin_profile`
- `2 rim_anchor`
- `1 primary_span`
- `1 spine_pivot`
- `1 carrier_arm`
- `3 to 7 relay_segment`
- `1 outer panel_leaf family`
- `1 counterweight_carriage`
- `1 charge_bank`
- `1 micro_sequencer`
- `1 catch_path` implemented through `latch_state` + `damper` + `brake`
- `1 transfer_floor`
- `1 clean_band`
- `1 dirty_band`
- `1 observation packet`

## Required Relationships

These edges must be explicit in the graph:

| From | To | Relation |
|---|---|---|
| `rim_anchor` | `primary_span` | `supports` |
| `primary_span` | `spine_pivot` | `hosts` |
| `spine_pivot` | `carrier_arm` | `rotates` |
| `carrier_arm` | `relay_segment` | `drives` |
| `relay_segment` | `panel_leaf` | `projects` |
| `micro_sequencer` | `latch_state` | `releases` |
| `charge_bank` | `carrier_arm` | `preloads` |
| `damper` | `relay_segment` | `settles` |
| `counterweight_carriage` | `carrier_arm` | `balances` |
| `thermal_plant` | `utility_bus` | `feeds` |
| `utility_bus` | `process_sink` or `habitation_sink` | `serves` |
| `dirty_band` | `transfer_floor` | `returns_through` |
| `inspection_gate` | `clean_band` | `admits_to` |

## Minimal Simulation Packet

Every tick or snapshot should be able to emit:

```json
{
  "scenario_id": "string",
  "tick": 0,
  "phase": "charge|hold|release|crest|catch|return|recharge",
  "selected_member_id": "string",
  "latch_state": "armed|released|caught|faulted",
  "carrier_angle_deg": 0,
  "panel_angle_deg": 0,
  "phase_relation_deg": 0,
  "load_band": "quiet|watch|hot",
  "vibration_band": "quiet|watch|hot",
  "utility_state": "idle|feeding|overdrawn",
  "service_state": "clean|transfer|dirty|quarantine",
  "trajectory_grade": "match|adjacent|widen|drift|break"
}
```

## Out Of Scope For This Registry

Not yet:

- full material science
- political site analysis
- exact power-plant chemistry
- whole-city deployment maps
- occupant choreography
- decorative skin language

This registry is for the first honest machine grammar.

## Immediate Next Mutation

After this registry, the next document should be:

- `CANYON_SPAN_MOTION_CYCLE_SPEC_2026-04-23.md`

Its only job:

- define the exact `charge -> hold -> release -> crest -> catch -> return -> recharge` cycle

## Coda

Name each member. Bind each role.
If the graph stays clean, the span may roll.
