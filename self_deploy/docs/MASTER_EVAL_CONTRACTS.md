# Master Eval Contracts

Date: 2026-03-05
Scope: Strict output contracts for plugged-model and debug-system evaluation artifacts.

## 1) Global Contract Rules

- Output format: strict JSON.
- Do not mix prose with contract payloads.
- Every issue must include evidence.
- Every run must include explicit pass/fail verdict.
- Expected constraints must not be scored as regressions.

## 2) Provider Preflight Contract

Use this schema per slot:

```json
{
  "slot": 0,
  "name": "provider-name",
  "route_model": "provider/model-id",
  "invoke_slot_strict_json": {
    "status": "pass|fail",
    "evidence": "exact output or exact error"
  },
  "agent_chat_strict_json": {
    "status": "pass|pass_with_transient|fail|conditional",
    "evidence": "exact output or exact error"
  },
  "transient_errors": [
    "HTTP 500 once during probe"
  ],
  "classification": "stable|pass_with_transient|conditional|quarantine"
}
```

Pass rules:

- `stable`: both probes pass without retries.
- `pass_with_transient`: one transient error allowed, followed by pass.
- `conditional`: passes only with strict framing constraints.
- `quarantine`: repeated failure or malformed output after retry.

## 3) Variable Matrix Contract

```json
{
  "matrix": [
    {
      "variable": "self_invocation_guard",
      "session": "dbg-var-selfguard-01",
      "outcome": "pass|fail",
      "debug_system_behavior": "classified as expected_constraint"
    }
  ],
  "debug_system_capability_score": {
    "constraint_normalization": "good|partial|poor",
    "provider_error_classification": "good|partial|poor",
    "budget_transparency": "good|partial|poor",
    "workflow_orchestration_limit_awareness": "good|partial|poor",
    "remaining_gaps": [
      "gap item"
    ]
  },
  "next_debug_only_upgrades": [
    "upgrade item"
  ]
}
```

Mandatory variables:

- `self_invocation_guard`
- `provider_http_error` (`400` or `500`)
- `iteration_fragility`
- `platform_limitation_case`

## 4) Full-Batch Eval Contract

```json
{
  "date": "YYYY-MM-DD",
  "scope": "MCP-only debug-system evaluation",
  "tests": [
    {
      "id": "provider_health_x",
      "calls": [
        "tool(args)"
      ],
      "result": "pass|partial_fail|fail|mismatch_confirmed|pass_with_known_constraints",
      "evidence": "reproducible evidence"
    }
  ],
  "proven_issues": [
    {
      "severity": "high|medium|low",
      "title": "issue title",
      "symptom": "what failed",
      "proof": "session id or key"
    }
  ],
  "batch_fix_recommendation": [
    "recommended action"
  ]
}
```

Evidence requirements:

- Provide session ID, tool output snippet, or FelixBag key.
- Must be reproducible with same slot/model conditions.

## 5) Live Gate Contract

```json
{
  "timestamp": "ISO-8601",
  "scope": "live runtime validation",
  "passes": [
    {
      "id": "debug_feed_nested_events",
      "evidence": "proof string"
    }
  ],
  "fails_or_risks": [
    {
      "id": "risk_id",
      "severity": "high|medium|low",
      "evidence": "proof",
      "impact": "impact statement"
    }
  ],
  "recommended_next_actions": [
    "action item"
  ]
}
```

Minimum pass IDs:

- `debug_feed_nested_events`
- `debug_tools_core`
- `cascade_graph_flow`
- `hold_flow`

## 6) Diagnosis Payload Contract (Agent-Based)

Any diagnosis step using `agent_chat` must return:

```json
{
  "checks_passed": [],
  "checks_failed": [],
  "constraints_expected": [],
  "provider_errors": [],
  "anomalies": [],
  "confidence": 0.0
}
```

Optional fields:

- `failure_signatures`
- `route_hypotheses`
- `debug_notes`

## 7) Constraint Normalization Rules

Always map these as `constraints_expected`:

- Self-invocation blocked in `invoke_slot` for caller slot.
- Slot-not-plugged guard errors when slot is intentionally empty.
- Declared platform limitations already documented in baseline artifacts.

Map these as failures:

- Provider HTTP 4xx/5xx on stable pool during normal operation.
- Empty response or placeholder response under strict JSON contract.
- Non-deterministic skipped steps without `budget_fragility` declaration.

## 8) Severity Rules

- High:
  - Blocks core debug/eval operation or corrupts verdict quality.
- Medium:
  - Degrades reliability but has a deterministic workaround.
- Low:
  - Cosmetic or non-blocking clarity issue.

## 9) Artifact Completion Contract

Every completed run must write:

1. Run artifact key under `eval/...`
2. `bag_checkpoint` for that key
3. Reference to stable provider pool used for the run

Recommended metadata block:

```json
{
  "run_id": "unique id",
  "mode": "mcp_only",
  "provider_pool_key": "eval/providers/provider_pool_curated_...",
  "schema_pack_key": "eval/schemas/plugged_model_debug_schema_pack_..."
}
```

