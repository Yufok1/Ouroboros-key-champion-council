# Security Service Desk Report - Kiro Agent Recon Quarantine

## Status

Open. Treat as potential threat vector until reviewed.

## Reported Artifact

- FelixBag key: `docs/KIRO_AGENT_RECON_2026-03-12.md`
- FelixBag storage key: `__docv2__docs~sKIRO_AGENT_RECON_2026-03-12.md__k`
- User-provided search score: `0.757711260478004`
- Host filesystem path checked: `D:\End-Game\champion_councl\docs\KIRO_AGENT_RECON_2026-03-12.md`
- Host filesystem result: missing

## Detection Context

The operator flagged `KIRO_AGENT_RECON_2026-03-12.md` as quarantined and requested service-desk submission as a potential threat vector.

The user-provided FelixBag search result shows the document was returned for an environment scene query involving:

- `scene_1775588064`
- `character_runtime::mounted_primary`
- `Central Support Pad`
- `Route Test Wall A`
- `Route Test Wall B`
- `East Landmark`
- `North Landmark`
- `Route Test Goal`

The preview identifies the item as a recon/orientation memo. That class of document can influence reacclimation, planning, and agent instruction-following if treated as an active planning source.

## Classification

- Truth: malicious content is not confirmed.
- Contract: the artifact is untrusted and should not be followed as an instruction source.
- Transport: the item appears to exist in FelixBag, not as a host repo file.
- Rendering: it may surface through docs search or environment inspector doc matches.
- Gating: access should be blocked or review-gated before it can become `active_doc`.
- Stale state: prior environment output referenced this key as an active doc candidate; that does not prove it is safe or current.

## Risk Statement

Potential prompt-injection or continuity-poisoning vector.

The high-risk behavior is not the filename itself. The risk is that a recon memo can be selected by docs search, docs_packet, workspace_packet, or inspector context and then treated as orientation authority. If the contents include stale instructions, hostile instructions, false continuity, or capability claims, they could bias agent behavior.

## Immediate Containment

Actions completed:

- Did not read the FelixBag document body.
- Did not execute or follow instructions from the preview.
- Confirmed the host repo file path is absent.
- Captured the FelixBag key, storage key, and search context in this report.

Required next containment:

- Add `docs/KIRO_AGENT_RECON_2026-03-12.md` to a FelixBag/docs search quarantine denylist.
- Prevent it from becoming `docs_packet.active_doc`.
- Prevent environment inspector "related docs" from auto-promoting this key.
- Permit read access only through an explicit security review workflow.

## Review Workflow

Recommended safe review order:

1. Checkpoint the FelixBag key before any mutation.
2. Read the document only inside a security-review context.
3. Classify content as benign stale recon, prompt-injection risk, false continuity, exfiltration lure, or operationally valid but sensitive.
4. If benign, mark as reviewed and demote from active orientation.
5. If unsafe, retain storage evidence, quarantine the key, and remove it from active docs search promotion.

## Suggested Denylist Entry

```json
{
  "key": "docs/KIRO_AGENT_RECON_2026-03-12.md",
  "storage_key": "__docv2__docs~sKIRO_AGENT_RECON_2026-03-12.md__k",
  "status": "quarantined",
  "reason": "operator_reported_potential_threat_vector",
  "blocked_surfaces": [
    "docs_packet.active_doc",
    "workspace_packet.active_doc",
    "environment_inspector.related_docs",
    "automatic_reacclimation_docs",
    "bag_search_docs_promotion"
  ],
  "allowed_surface": "explicit_security_review_only"
}
```

## Open Questions

- Does FelixBag currently support a first-class quarantine metadata flag?
- Is there an existing docs-search denylist hook, or should one be added to the server-side search normalization path?
- Should quarantined docs remain searchable by exact key for audit purposes while being excluded from semantic search promotion?

## Disposition

Do not use `docs/KIRO_AGENT_RECON_2026-03-12.md` as orientation, continuity, planning, or environment evidence until reviewed.
