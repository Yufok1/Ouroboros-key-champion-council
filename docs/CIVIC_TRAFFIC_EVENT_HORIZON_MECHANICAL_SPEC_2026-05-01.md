# Civic Traffic Event Horizon Mechanical Spec - 2026-05-01

## Status

Draft mechanical finalization.

Purpose: define a buildable observation and routing system for public traffic, dense crowd movement, public speech surfaces, acoustic no-entry zones, and emergency decompression.

This is not a truth oracle, policing surface, or coercive crowd-control system.

Core rule:

`observe -> receipt -> classify -> route -> publish boundary -> review`

## Name

Canonical primitive:

`civic_traffic_event_horizon`

Related primitives:

- `event_horizon_observer`
- `crowd_flow_map`
- `compression_front_detector`
- `acoustic_no_entry_zone`
- `public_laughter_sonar`
- `slow_entry_gate`
- `decompression_route`
- `source_hold_gate`

## Mechanical Objective

Make crowd and traffic flow as legible as map traffic:

- where movement is smooth
- where movement is stalled
- where density is rising
- where exits are blocked
- where crossflow is forming
- where panic or overload may be starting
- where safe decompression routes exist
- what the evidence source is
- what is confirmed, inferred, and unknown

The system should help people and responders see the same public state before the situation smears into rumor, panic, blame, or unsafe movement.

## Evidence Baseline

Crowd safety guidance treats risk assessment, monitoring, safe capacity, distribution, entrances/exits, pinch points, queues, confined spaces, surges, and public information as primary controls.

Engineering implication:

The first useful system is not identity recognition. It is flow visibility and early hazard detection.

## State Model

Represent the site as a directed graph:

```json
{
  "zones": [
    {
      "id": "zone.stage_front.left",
      "type": "standing_area",
      "capacity_model": "local_authority_configured",
      "privacy_mode": "aggregate_only"
    }
  ],
  "edges": [
    {
      "id": "edge.exit_a_to_plaza",
      "from": "zone.exit_a",
      "to": "zone.plaza",
      "direction": "outbound",
      "width_m": 4.0,
      "status": "open"
    }
  ],
  "sensors": [],
  "actuators": [],
  "events": []
}
```

## Inputs

Allowed input classes:

- aggregate entry/exit counters
- public map/traffic feeds
- venue camera-derived aggregate flow only
- thermal or lidar aggregate density where legal and appropriate
- staff/steward reports
- public incident reports
- acoustic intensity and timing bands
- signage/gate state
- weather and surface condition
- transit arrival/departure bursts
- emergency services route state

Default privacy posture:

- no face identification
- no personal identity tracking
- no private-person scoring
- no hidden persuasion profile
- store aggregate movement state unless a lawful emergency authority requires more

## Core Metrics

Each zone and edge should compute:

- `density_band`: open, busy, compressed, critical, unknown
- `flow_rate`: people per minute, configured by site
- `mean_speed`: aggregate movement speed
- `stop_wave`: repeated stall/advance pulses
- `counterflow`: opposing streams crossing
- `turbulence`: high local variance in movement direction/speed
- `queue_pressure`: backpressure at gates, doors, stairs, escalators, concessions, transport
- `exit_capacity_margin`: available route capacity minus observed or forecast demand
- `fall_risk`: uneven surface, sudden compression, trip reports, stalled dense movement
- `acoustic_stress`: intensity, abrupt spikes, crowd call/response mismatch, public instruction intelligibility
- `no_entry_state`: open, slow_entry, no_entry, emergency_clear

Thresholds must be configurable by venue, local law, professional crowd engineers, and public safety authorities. The system may ship with example bands, but it must not pretend one universal density number is safe for every crowd, venue, or event.

## Event Types

```json
{
  "event_type": "flow_slowdown | bottleneck | exit_blocked | compression_front | surge | counterflow | fall_cluster | acoustic_overload | no_entry_zone_active | decompression_route_open | incident_reported",
  "zone_id": "zone.stage_front.left",
  "source": "aggregate_counter | camera_flow | staff_report | public_report | acoustic_sensor | map_feed",
  "confirmed": [],
  "inferred": [],
  "unknown": [],
  "risk_band": "open | watch | urgent | critical",
  "timestamp": "ISO-8601"
}
```

## Risk Bands

`open`

- normal movement
- no blocked exits
- public instructions intelligible
- capacity margin healthy

`watch`

- localized congestion
- slow movement
- early queue pressure
- elevated acoustic stress
- staff review recommended

`urgent`

- compression trend rising
- exit margin low
- crossflow or reverse flow forming
- public instruction degraded
- activate slow-entry, reroute, or decompression recommendation

`critical`

- crush/suffocation/trampling risk plausible
- stalled dense crowd
- exit blocked or backpressure severe
- panic onset indicators
- route emergency response and open decompression paths under lawful authority

## Control Surfaces

Allowed life-safety outputs:

- public route display
- map hazard marker
- slow-entry recommendation
- no-entry warning
- alternate exit/path recommendation
- staff/steward dispatch recommendation
- public-address script
- acoustic softening cue
- lighting/signage cue
- gate state recommendation
- emergency route clearance recommendation

Forbidden outputs:

- punishment targeting
- personal blacklists
- face-based public scoring
- coercive acoustic force
- hidden persuasion
- automated police conclusion
- "guilt" or intent inference

## Decompression Mechanics

Use the word `destabilization` only as pressure dissipation:

- reduce inflow
- phase releases
- open lateral relief paths
- split flows before pinch points
- redirect to less crowded viewing areas
- pause attractor events that pull people forward
- add visible route alternatives
- improve public instruction intelligibility
- route vulnerable people away from compression
- keep emergency lanes clear

The mechanical goal is to reduce coupled pressure waves in the crowd. It is not to shock, confuse, or dominate people.

## Acoustic Layer

Acoustic engineering is paramount because sound can either calm a route or amplify panic.

Acoustic primitives:

- `acoustic_no_entry_zone`: sound-safe boundary around a sensitive area
- `voice_gate`: intelligible public instruction lane
- `warning_ring`: local hazard cue
- `quiet_membrane`: low-stimulation buffer
- `public_laughter_sonar`: public speech/comedy mood read, aggregate only
- `attention_beacon`: draws attention to a safe route or message

Every acoustic output must name:

- source
- intended receiver class
- safe intensity band
- duration
- duty cycle
- fallback visual/tactile cue
- ingress rule
- Source HOLD condition

## Public Speech Layer

Public speech is a special case of crowd flow:

- attention flows toward a speaker or stage
- jokes and call/response reveal timing, overload, trust, and tension
- props or spectacle markers can create visible beat receipts
- acoustic sequencing can soften no-entry or slow-entry instructions

Professional comedians and acoustic/surfology experts may help produce timing and tone, but their output is public-surface readiness and aggregate friction notes. It is not a personal judgment system.

## Event Receipt

Each event must produce a compact receipt:

```json
{
  "schema": "civic_traffic_event_horizon.event.v1",
  "event_id": "",
  "site_id": "",
  "zone_id": "",
  "surface": "map | venue | public_speech | transit | emergency",
  "source": {
    "kind": "sensor | staff | public | official | model",
    "id": "",
    "privacy": "aggregate_only | anonymized | restricted"
  },
  "timestamp": "",
  "risk_band": "open | watch | urgent | critical",
  "confirmed": [],
  "inferred": [],
  "unknown": [],
  "recommended_routes": [],
  "authority_boundary": "observation_only | staff_review | emergency_authority_required",
  "source_hold": {
    "required": true,
    "condition": "real-world access, routing, emergency, civic, or public instruction action"
  }
}
```

## Human Authority Boundary

Observation can be automatic.

Real-world restriction, evacuation, access control, emergency order, enforcement, or public commitment requires the appropriate human/community/legal authority.

The system can recommend:

- "slow entry"
- "route to exit B"
- "decompress stage-front left"
- "open lateral gate"
- "send steward to pinch point"

It cannot self-authorize:

- forced movement
- closure with legal consequences
- punitive classification
- emergency command
- financial or civic commitment

## Minimum Viable Prototype

1. Site graph editor: zones, edges, exits, pinch points, no-entry membranes.
2. Aggregate event ingest: manual staff report plus simple counters.
3. Risk classifier: open/watch/urgent/critical with confirmed/inferred/unknown.
4. Public map overlay: hazard markers, safe route suggestions, confidence.
5. Acoustic boundary registry: no-entry, quiet, warning, attention cues.
6. Receipt log: timestamped evidence packet for every event.
7. Review board: after-action debrief and threshold tuning.

## Google Fit

This extends the traffic map pattern:

- car traffic -> human traffic
- crash marker -> incident/compression marker
- slowdown -> density/flow slowdown
- closure -> no-entry/slow-entry zone
- alternate route -> decompression route
- estimated travel time -> route pressure and exit capacity
- user report -> public/staff event receipt

The product shape is familiar: shared situational awareness, safer routing, and visible uncertainty.

## Acceptance Test

The system is mechanically credible when it can answer:

1. What zone or edge is under pressure?
2. What evidence source says so?
3. What is confirmed, inferred, and unknown?
4. What is the safest route or decompression action?
5. What authority is required before action?
6. What public display can reduce panic instead of increasing it?
7. What after-action receipt lets humans improve the plan?

If it cannot answer those, it is not an event horizon system yet.

## Sources To Keep Attached

- HSE, "Assess crowd safety risks and identify hazards"
- HSE, "Monitor the crowd"
- HSE, "Put crowd controls in place"
- HSE, "Crowd controls inside the venue"
