# Glass Bite Gentle Food Observer Spec - 2026-05-01

## Status

Draft product and system contract.

Working names:

- Glass Bite
- ClearBite
- BiteLens
- TrueSpoon
- HoloSpoon

Purpose:

Build a transparent smart spoon that helps a person see what they are eating one bite at a time.

This is a gentle food observer, not a food judge.

It exists to produce bite receipts.

It does not exist to shame, diagnose, purify food, guarantee allergen detection, or make medical claims.

## One Line

A transparent smart spoon that pairs with a phone and turns each bite into an honest food observation: estimated weight, likely food type, nutrition estimate, confidence, and unknowns.

Comedy phrase:

```text
This spoon has receipts.
```

Serious phrase:

```text
Gentle food truth without shame.
```

## Core Use Case

The user is eating.

They want to know:

- what is this bite likely made of?
- how much food is on the spoon?
- what is the estimated nutrition impact?
- how confident is the system?
- what does the system not know?

The system answers with a bounded observation, not a verdict.

## Hardware Concept

### Spoon Head

- transparent food-contact spoon bowl
- removable and washable
- shaped so the phone/camera view can see through or across the bite
- no electronics exposed to food
- clear boundary between food-contact part and sensor handle

### Handle

Candidate sensors:

- strain gauge or small load cell for bite weight estimate
- optical sensor or small camera window for bite appearance
- LED backlight for consistent illumination
- inertial sensor for bite angle and movement
- Bluetooth Low Energy module for phone connection
- small haptic motor for capture feedback

The first prototype should avoid exotic chemistry claims.

The first prototype should prove:

- reliable tare
- stable bite weight estimate
- image capture at the moment of eating
- confidence-aware food classification
- simple phone receipt

## Phone Surface

The phone is the main interpretation layer.

Per bite, show:

- timestamp
- bite weight estimate
- detected food candidates
- confidence
- estimated calories
- estimated macros
- optional points-style score
- running meal total
- uncertainty notes
- confirm/correct controls

Default language should be neutral:

- "Likely rice, 18 g, medium confidence"
- "Unknown sauce, confirm?"
- "Estimate changed after your correction"

Avoid shame language:

- no "bad food"
- no "failure"
- no guilt prompts
- no streak punishment

## Data Boundaries

This system handles sensitive personal food behavior.

Defaults:

- local-first
- no hidden upload
- no public sharing
- no social scoring
- no automatic medical inference
- no ad-targeting data path
- export and delete controls visible

Cloud sync, coaching, or research export requires explicit consent.

## Non-Claims

The product must not claim:

- it removes carcinogens
- it detects all carcinogens
- it guarantees allergen safety
- it diagnoses disease
- it replaces a dietitian or doctor
- it proves exact calories
- it knows ingredients with certainty from image alone

Permitted claim shape:

```text
The system estimates and shows confidence.
```

Forbidden claim shape:

```text
The system certifies the food.
```

## Observer Contract Alignment

Glass Bite is a `gentle_danger_observer` appliance for food awareness.

It observes:

- bite size drift
- unknown ingredients
- hidden sauces or dense ingredients
- repeated mismatch between expected and observed intake
- uncertainty in nutrition estimation

It must preserve:

- user dignity
- uncertainty
- correction rights
- private control
- data provenance

It must not become:

- a coercive diet authority
- a compulsive tracking surface
- a body-shame machine
- a medical claim engine
- a hidden surveillance appliance

## Bite Receipt Schema

```json
{
  "schema": "food_observation_packet.v1",
  "packet_id": "",
  "device_id": "",
  "capture_mode": "spoon_live | phone_manual | imported | simulation",
  "data_classification": "personal_food_behavior",
  "consent_posture": "explicit | local_only | unknown",
  "meal_id": "",
  "bite": {
    "bite_id": "",
    "timestamp": "",
    "weight_g": 0.0,
    "weight_confidence": 0.0,
    "image_hash": "",
    "lighting_quality": "good | mixed | poor | unknown",
    "motion_quality": "stable | moving | blurred | unknown"
  },
  "classification": {
    "candidates": [
      {
        "food_label": "",
        "confidence": 0.0,
        "source": "user_confirmed | model_estimate | prior_meal_context | unknown"
      }
    ],
    "unknowns": []
  },
  "nutrition_estimate": {
    "calories": 0.0,
    "protein_g": 0.0,
    "carbs_g": 0.0,
    "fat_g": 0.0,
    "fiber_g": 0.0,
    "sodium_mg": 0.0,
    "confidence": 0.0,
    "source": "user_label | local_database | public_database | model_estimate | unknown"
  },
  "user_review": {
    "status": "unreviewed | confirmed | corrected | rejected",
    "correction": "",
    "notes": ""
  },
  "receipts": {
    "previous_hash": "",
    "event_hash": "",
    "review_hash": ""
  }
}
```

## Champion Council Role

Champion Council reviews the food observation packets as artifacts.

It can:

- display bite receipts
- show confidence and unknowns
- route unclear foods to review
- compare user corrections against model estimates
- preserve local-first posture
- block medical or certainty-overclaim language

It must not:

- publish personal food behavior by default
- turn estimates into moral verdicts
- route personal nutrition data to public organisms without explicit consent

## Convergence Engine Role

Convergence Engine organisms can learn from simulated or approved examples.

Safe organism lessons:

- estimating under uncertainty
- asking for confirmation
- separating observation from interpretation
- learning nutrition vocabulary
- identifying when data is insufficient

Forbidden organism lessons:

- shame persuasion
- medical diagnosis
- body scoring
- sensitive personal inference
- claiming certainty from weak food signals

## First Prototype

Minimum prototype target:

1. Transparent spoon head and weighted handle mock.
2. Phone capture flow.
3. Bite weight estimate or manual weight stand-in.
4. Food candidate classifier.
5. Confidence and unknown display.
6. Running meal total.
7. Local-only exportable JSON receipt.

Success condition:

The user can take five bites and receive five honest bite receipts without being shamed, misled, or forced into cloud sharing.

## Open Seams

- Food-contact material and cleaning constraints need product engineering review.
- Nutrition source database needs selection and licensing review.
- Camera-only food classification will be uncertain for mixed foods, sauces, and hidden ingredients.
- Medical, allergy, diabetes, eating disorder, and child-use contexts require stricter boundaries.
- Any research or population-health use requires explicit consent and review.
