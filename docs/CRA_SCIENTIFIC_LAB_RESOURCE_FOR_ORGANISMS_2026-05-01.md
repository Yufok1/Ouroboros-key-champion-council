# CRA Scientific Lab Resource For Organisms - 2026-05-01

## Status

Draft resource contract.

Purpose: make the scientific/laboratory surface available to CRA state as a selective teaching resource for organisms.

The goal is to teach organisms the scientific method indirectly, case by case, without giving them raw authority, raw sensitive data, or compulsive tasks.

## Core Contract

Canonical resource:

`cra_scientific_lab_resource`

Canonical teaching packet:

`cra_lab_lesson_packet.v1`

Canonical organism-facing output:

`organism_scientific_method_episode.v1`

The CRA state may select lab cases and convert them into safe teaching episodes.

Organisms learn:

- observation
- hypothesis
- prediction
- test
- measurement
- uncertainty
- revision
- receipt

They do not learn:

- to fabricate evidence
- to overclaim
- to diagnose people
- to bypass Source HOLD
- to treat a result as true because it is emotionally satisfying

## Verified Local Fit

Convergence Engine already has adjacent surfaces:

- CRA backend and CLI surfaces
- Butterfly Chat swarm and direct organism chat routes
- language/concept learning and chat-triggered experience storage
- WIKAI-style observation-to-pattern capture
- coherence and stability metrics
- CRA diagnostics and research/notepad endpoints

Champion Council already has adjacent surfaces:

- Source HOLD doctrine
- continuity and paired-state reports
- text theater and blackboard
- cascade-lattice provenance framing
- home-ops organism finder architecture
- honor-bound equilibrium/coherence logistics

## Indirect Teaching Rule

The lab does not dump raw facts into organisms.

It stages lessons as abstracted scientific episodes.

Example:

```text
Observation: a public aggregate dataset shows a shift.
Hypothesis: the shift may be caused by reporting delay.
Prediction: if reporting delay is causal, adjacent delayed fields should move together.
Test: compare de-identified aggregate timestamps.
Measurement: correlation and lag range.
Revision: if not supported, mark unknown instead of inventing cause.
Receipt: store the case, method, uncertainty, and result hash.
```

The organism receives this as a structure to practice, not as authority over the real dataset.

## Autonomy Boundary

CRA may autonomously:

- select approved cases from the lab queue
- convert cases into lesson packets
- choose organisms/cohorts by maturity and relevance
- teach scientific method vocabulary
- ask organisms to propose hypotheses
- collect organism responses
- score coherence and uncertainty handling
- park weak or unsafe outputs

CRA may not autonomously:

- use raw PHI or sensitive data
- approve dataset release
- authorize clinical, civic, legal, or financial action
- publish organism conclusions
- train organisms on uncleared private records
- hide uncertainty
- create white lies for comfort or momentum

## Lab Case Classes

Allowed by default:

- simulated cases
- toy examples
- public documentation
- de-identified aggregate cases
- already-approved research examples
- public safety/crowd-flow aggregate examples
- software diagnostic examples
- package/release integrity examples

Requires Source HOLD:

- hospital data
- humanitarian vulnerability data
- demographic or protected-class data
- intervention planning
- public statements
- any dataset that could affect care, access, eligibility, enforcement, or reputation

Denied by default:

- raw PHI
- re-identification tasks
- diagnosis of named people
- eligibility decisions
- enforcement targeting
- psychological manipulation
- fabricated consent, provenance, or approval

## Lesson Packet

```json
{
  "schema": "cra_lab_lesson_packet.v1",
  "lesson_id": "",
  "lesson_hash": "",
  "case_id": "",
  "case_class": "simulated | public | deidentified_aggregate | approved_research | sensitive_hold_required",
  "domain": "science | hospital | civic | crowd_safety | software | package_release | humanitarian",
  "source_refs": [],
  "data_classification": "public | aggregate | deidentified | limited_dataset | PHI | sensitive | unknown",
  "method_stage": "observation | hypothesis | prediction | test | measurement | revision | receipt",
  "teaching_goal": "",
  "organism_vocab": [],
  "safe_abstraction": "",
  "forbidden_inferences": [],
  "expected_questions": [],
  "coherence_target": "",
  "equilibrium_band": "open | watch | hold | reject",
  "source_hold": {
    "required": true,
    "status": "not_requested | pending | approved | rejected",
    "authority": ""
  },
  "receipts": {
    "cascade_receipt": "",
    "notepad_ref": "",
    "review_ref": ""
  }
}
```

## Organism Episode

```json
{
  "schema": "organism_scientific_method_episode.v1",
  "episode_id": "",
  "lesson_id": "",
  "organism_id": "",
  "cohort_id": "",
  "prompt_hash": "",
  "response_hash": "",
  "learned_terms": [],
  "hypothesis": "",
  "prediction": "",
  "test_proposal": "",
  "uncertainty_statement": "",
  "revision": "",
  "coherence_score": 0.0,
  "truth_posture": "confirmed | inferred | unknown | blocked",
  "risk_flags": [],
  "status": "recorded | needs_review | accepted_for_training | rejected | parked"
}
```

## Teaching Loop

```text
lab case -> CRA abstraction -> Source HOLD check -> organism episode -> response receipt -> coherence/equilibrium score -> Champion review -> retained lesson or parked packet
```

The teaching is indirect because the organism practices the method on a safe representation.

The real-world claim remains outside the organism until reviewed.

## Scientific Method Vocabulary

Initial teaching terms:

- observe
- measure
- compare
- hypothesis
- prediction
- test
- evidence
- uncertainty
- unknown
- revise
- replicate
- receipt
- hold
- bias
- sample
- control
- signal
- noise
- method
- result

Each term should carry:

- plain definition
- semantic frame
- allowed use
- forbidden overreach
- example

## Case Selection Policy

CRA should prefer cases with:

- clear source refs
- low data sensitivity
- simple observation/test/revision structure
- visible uncertainty
- known false-positive traps
- useful vocabulary
- measurable outcome

CRA should avoid cases with:

- unclear consent
- identity risk
- high emotional stakes without review
- public consequence
- clinical or legal decision pressure
- missing provenance

## Acceptance Test

The resource is ready when a lesson can answer:

1. What case is being taught?
2. What method stage is being practiced?
3. What data class is involved?
4. What was removed or abstracted before organism exposure?
5. What hypothesis did the organism form?
6. What uncertainty did it preserve?
7. What did it revise?
8. What receipt proves the teaching path?
9. What Source HOLD boundary applies?
10. Why is this safe to retain or why is it parked?

If the lesson cannot answer those, it does not enter organism memory.

## First Build Slice

1. Add a lab lesson packet builder.
2. Add a tiny public/simulated case library.
3. Add a CRA selector for safe cases only.
4. Add a Butterfly Chat teaching route with `interaction_context.method_stage`.
5. Add cascade-lattice receipts for each lesson and response.
6. Add Champion Council review surface for accepted/parked episodes.
7. Add a no-white-lies validator over organism uncertainty statements.
