# Champion Council Agent Rules

Use the continuity tool lane first when the task is orientation, reacclimation, reset recovery, "what does the server know", continuity, or posture restore.

Default Champion Council reacclimation order:

1. `continuity_status`
2. `continuity_restore(summary=<active objective + subject + pivot>, cwd='D:\End-Game\champion_councl')`
3. `env_help(topic='continuity_reacclimation')`
4. `env_read(query='text_theater_embodiment')`
5. `env_control(command='capture_supercam', actor='assistant')`
6. `env_read(query='supercam')`
7. `env_read(query='text_theater_view', view='consult', section='blackboard', diagnostics=true)`
8. `env_read(query='text_theater_snapshot')`
9. `env_report(report_id='paired_state_alignment')`

Rules:

- Do not substitute a docs crawl or source crawl for the continuity tool lane when continuity is the seam.
- If the operator says `continuity`, `run continuity`, `do continuity`, or asks whether continuity was run, do not ask what they mean; treat that as a direct order to run the continuity lane.
- Code and doc inspection come after archive restore and live corroboration unless the operator explicitly orders a different sequence.
- `continuity_restore` is archive-side reacclimation, not live authority.
- Live theater, blackboard, snapshot freshness, and scoped reports outrank archive continuity when they disagree.
- If the operator explicitly prescribes a different reacclimation order, follow that order exactly.
