# Codex Recovery: Skills System — Batch 3

## WHERE YOU ARE
You're building a queryable skills reference system in `F:\End-Game\ouroboros-key\agent_compiler.py`. You've already completed 8 categories (~94 tool docs). You were mid-batch on the next 4 categories when context reset.

## THE QUINE RULE (critical)
agent_compiler.py is a quine generator. The skills data lives at **Level 0** (normal Python dicts around line ~50700) and is injected into the Level 1 template via `{_HELP_SKILLS_SEED}`. This means you write **normal Python dicts** — no brace doubling needed for the data itself. Just add entries to the `_HELP_SKILLS_SEED` dict.

## WHAT'S ALREADY DONE — DO NOT DUPLICATE THESE
The `_HELP_SKILLS_SEED` dict (starts ~line 49722) already contains docs for:

**meta:** get_help, get_about, get_onboarding, get_quickstart, get_embedder_info, list_models, demo
**status_and_identity:** get_status, heartbeat, verify_integrity, verify_hash, get_capabilities, get_identity, get_genesis, get_provenance, tree, show_weights, show_dims, show_rssm, show_lora
**memory_bag:** bag_put, bag_get, bag_read_doc, bag_list_docs, bag_search_docs, bag_tree, bag_checkpoint, bag_versions, bag_diff, bag_restore, bag_catalog, bag_induct, bag_search, bag_forget, bag_export, summon, pocket, materialize, load_bag, save_bag
**inference:** forward, infer, embed_text, generate, classify, rerank, deliberate, imagine, invoke_slot
**file_workspace:** file_read, file_write, file_edit, file_append, file_prepend, file_delete, file_rename, file_copy, file_list, file_tree, file_search, file_info, file_checkpoint, file_versions, file_diff, file_restore
**model_management:** plug_model, hub_plug, unplug_slot, list_slots, slot_info, get_slot_params, clone_slot, mutate_slot, rename_slot, swap_slots, grab_slot, restore_slot, cull_slot
**council:** broadcast, council_status, set_consensus, debate, chain, all_slots, compare
**chat:** chat, chat_reset, chat_history, agent_chat

**Also already done (seed docs from Phase 1):** cascade_graph, env_spawn, workflow_execute

## YOUR TASK NOW — ADD THESE 4 CATEGORIES

### 1. cascade_lattice (6 tools to add — cascade_graph already done)
Add: `cascade_chain`, `cascade_data`, `cascade_system`, `cascade_instrument`, `cascade_record`, `cascade_proxy`

Each CASCADE tool uses an `operation` parameter with sub-dispatch. Document the operation matrix (like cascade_graph's existing doc does). Read each tool's `@logged_tool()` implementation to find the operation branches.

Key locations in agent_compiler.py:
- cascade_chain: search for `def cascade_chain(`
- cascade_data: search for `def cascade_data(`
- cascade_system: search for `def cascade_system(`
- cascade_instrument: search for `def cascade_instrument(`
- cascade_record: search for `def cascade_record(`
- cascade_proxy: search for `def cascade_proxy(`

### 2. workflow_automation (8 tools to add — workflow_execute already done)
Add: `workflow_create`, `workflow_list`, `workflow_get`, `workflow_update`, `workflow_delete`, `workflow_history`, `workflow_status`, `workflow_test`

`workflow_create` is the most important — document the 10 node types: tool, agent, input, output, fan_out, http, if, set, merge, web_search. Document the connection schema (from/to, branch for if-nodes). Document data wiring syntax ($input.field, $node.nodeId.key, $env.VAR, $now, $uuid, $random).

### 3. environment (5 tools to add — env_spawn already done)
Add: `env_mutate`, `env_remove`, `env_read`, `env_control`, `env_persist`

`env_control` has 30+ commands — document the command dispatch. `env_persist` has operation sub-dispatch: snapshot, list, load, export, sync_live, prune_snapshots, clear. `env_read` has query dispatch: list/objects, kinds, object by id, state, live, contracts, etc.

### 4. diagnostics (6 tools — all new)
Add: `diagnose_file`, `diagnose_directory`, `symbiotic_interpret`, `trace_root_causes`, `forensics_analyze`, `metrics_analyze`

These wrap CASCADE's DiagnosticEngine. Read each implementation for parameters and behavior.

## SKILLS DOC SCHEMA
Each tool entry follows this structure (normal Python dict):
```python
"tool_name": {
    "tool": "tool_name",
    "category": "category_name",
    "purpose": "One-line description of what it does.",
    "parameters": {
        "param_name": {
            "type": "str",
            "required": True/False,
            "default": "value",  # if optional
            "description": "What this param does."
        }
    },
    "returns": {
        "structure": "JSON",
        "key_fields": ["field1", "field2"],
        "notes": ["Any important notes about return shape"]
    },
    "use_cases": ["Use case 1", "Use case 2"],
    "related_tools": ["related_tool_1", "related_tool_2"],
    "common_patterns": ["pattern_1 -> pattern_2 for X"],
    "gotchas": ["Warning about non-obvious behavior"]
},
```

For operation-dispatch tools, add an `"operation_matrix"` field (see cascade_graph's existing entry as reference).

## HOW TO ADD
1. Find `_HELP_SKILLS_SEED` dict (starts ~line 49722, ends ~line 50960ish)
2. Add new entries at the END of the dict, before the closing `}`
3. Also update `_HELP_CATEGORY_STUBS` (starts ~line 50974ish) — change `"status": "stub"` to `"status": "seeded"` for each completed category, and add `"architecture"` and `"canonical_patterns"` fields

## VALIDATION
After EACH category: `python -m py_compile F:\End-Game\ouroboros-key\agent_compiler.py`

## DO NOT
- Edit champion_gen8.py or capsule.gz
- Restructure existing entries
- Touch the get_help routing logic (already done at line ~43120)
- Touch the TUI mirror at ~line 29462
