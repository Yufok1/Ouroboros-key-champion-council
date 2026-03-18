# Codex Task: Build Skills Reference System for get_help()

## YOUR MISSION
You are editing `F:\End-Game\ouroboros-key\agent_compiler.py` — a ~49,000-line quine generator. You will expand `get_help()` to accept a `topic` parameter and build a queryable skills document registry for every tool in the system (~166 tools across 18 categories).

---

## GOVERNING LAW #1: THE QUINE RULES (from claudeoctor.txt)

This file is a **3-level quine system**. Understanding this is MANDATORY before touching any code.

### The Three Levels
```
LEVEL 0: THE COMPILER — Normal Python. {x} = give me x's value.
LEVEL 1: THE TEMPLATE (inside f'''...''') — Generated code. {{x}} = output will say {x}.
LEVEL 2: NESTED GENERATION — Code writing code writing code. {{{{x}}}} = nested f-string.
```

### The Nine Transformations (Level 1 escaping)
| You Want in Output | You Write in Template |
|--------------------|-----------------------|
| `{`                | `{{`                  |
| `}`                | `}}`                  |
| `{variable}`       | `{{variable}}`        |
| `{"key": "val"}`   | `{{"key": "val"}}`    |
| `"""`              | `\"\"\"`              |
| `\n` (literal)     | `\\n`                 |
| `\`                | `\\`                  |
| `f"{x}"`           | `f"{{x}}"`            |
| `f"{x}"` at Lvl 2  | `f"{{{{x}}}}"`        |

### The Five Precepts
1. **READ BEFORE YOU WRITE** — Read 50 lines above and below before editing
2. **COUNT YOUR BRACES** — One orphan brace corrupts everything
3. **PRESERVE WHAT YOU DO NOT UNDERSTAND** — If you see `{{{{` and don't know why, leave it
4. **TEST AFTER EVERY EDIT** — `python -m py_compile agent_compiler.py`
5. **MINIMAL DIFF, MAXIMUM INTENT** — Change only what you must

### Checklist Before Every Edit
- Have I read the surrounding 50 lines?
- Do I know what level I am at?
- Have I identified all brace purposes? (injection `{var}` vs literal `{{}}` vs dict `{{"key": "val"}}` vs f-string `{{var}}`)
- Have I preserved all existing escaping I don't understand?
- Is my change the minimum required?

---

## GOVERNING LAW #2: INTEGRATION SURFACES (from AGENT_COMPILER_INTEGRATION_SURFACES.md)

When you change a tool, you must check ALL these surfaces:

### A. Runtime behavior
- `@logged_tool()` implementation in generated runtime
- Helper functions used by that tool
- `_handle_mcp_request(...)` if dispatch depends on request structure

### B. MCP instruction and help mirrors
- `_build_mcp_instructions()` : line ~34198
- `get_help()` : line ~41645 (THIS IS WHAT YOU'RE CHANGING)
- `get_quickstart()` : line ~41619
- `get_onboarding()` : line ~41460
- README generator

### C. Discovery and inventory mirrors
- `_MONOLITH_INDEX['mcp_tools']` : line ~47470
- `get_capabilities()` : line ~35520

### D. TUI / CLI mirrors
- `on_input_submitted(...)` : line ~29289

### E. Export / wrapper mirrors
- Arcade writers if exported

### Verification Protocol
1. `python -m py_compile agent_compiler.py`
2. Regenerate target artifact(s)
3. Run direct runtime checks against regenerated artifact(s)
4. Verify help/docs/index surfaces match runtime truth

---

## WHAT EXISTS NOW

### Current get_help() — line ~43114 (agent_compiler.py) / line ~36676 (champion_gen8.py)
```python
@logged_tool()
def get_help() -> str:
    """Get comprehensive help with all available tools and their purposes."""
```
- Takes NO parameters
- Returns flat JSON with: overview, essential_tools, tool_reference (10 categories with one-line descriptions), common_patterns, api_server, total_tools
- ~175 lines of hardcoded JSON construction

### Current _MONOLITH_INDEX — line ~49668
- Version 1.0.0, maps 22 code sections, 12 classes, 9 brain types, 11 integrations
- Lists 159 mcp_tools + 7 CASCADE tools = 166 total
- Has search patterns for grepping

---

## WHAT TO BUILD

### Phase 1: Infrastructure (do this FIRST, validate, then proceed)

#### Task 1.1: Add `topic` parameter to get_help()

Find `get_help()` around line 43114. This is at **Level 1** (inside the capsule template f-string).

Change the signature. Then add routing at the TOP of the function body:

```python
# REMEMBER: This is Level 1! All braces in dicts/JSON must be doubled!
@logged_tool()
def get_help(topic: str = '') -> str:
    \"\"\"Get help on any tool, category, or the system overall.

    Args:
        topic: Tool name, category name, or empty for overview.
               Examples: 'cascade_graph', 'workflow', 'bag_put', 'environment'

    Returns:
        JSON with targeted help content
    \"\"\"
    if topic:
        topic_lower = topic.lower().strip()
        # Check skills registry first
        if topic_lower in _SKILLS_REGISTRY:
            return json.dumps(_SKILLS_REGISTRY[topic_lower], indent=2)
        # Check category registry
        if topic_lower in _CATEGORY_REGISTRY:
            cat = _CATEGORY_REGISTRY[topic_lower]
            # Enrich with tool summaries from skills registry
            enriched = dict(cat)
            enriched['tool_details'] = {{{{}}}}
            for t in cat.get('tools', []):
                if t in _SKILLS_REGISTRY:
                    enriched['tool_details'][t] = _SKILLS_REGISTRY[t].get('purpose', '')
            return json.dumps(enriched, indent=2)
        # Index request
        if topic_lower == 'index':
            return json.dumps(_MONOLITH_INDEX, indent=2)
        # Search
        if topic_lower.startswith('search:'):
            query = topic_lower[7:]
            results = {{{{}}}}
            for tool_name, doc in _SKILLS_REGISTRY.items():
                searchable = json.dumps(doc).lower()
                if query in searchable:
                    results[tool_name] = {{{{
                        "category": doc.get("category", ""),
                        "purpose": doc.get("purpose", "")
                    }}}}
            return json.dumps({{{{"query": query, "matches": len(results), "results": results}}}}, indent=2)
        # Fuzzy match fallback
        matches = [k for k in _SKILLS_REGISTRY if topic_lower in k.lower()]
        if matches:
            return json.dumps({{{{m: _SKILLS_REGISTRY[m].get('purpose', '') for m in matches}}}}, indent=2)
        # Category fuzzy match
        cat_matches = [k for k in _CATEGORY_REGISTRY if topic_lower in k.lower()]
        if cat_matches:
            return json.dumps({{{{c: _CATEGORY_REGISTRY[c].get('purpose', '') for c in cat_matches}}}}, indent=2)
        return json.dumps({{{{"error": f"No help found for '{{{{topic}}}}'", "hint": "Try get_help() for overview or get_help('index') for full index"}}}}, indent=2)
    # Original behavior below for empty topic...
```

**CRITICAL BRACE NOTE:** The above example shows Level 1 escaping. Every `{` in the generated runtime code = `{{` in agent_compiler.py. Nested dicts inside the f-string template use `{{{{` and `}}}}`. Count carefully.

**ALSO:** You need to update the MCP tool registration to accept the new parameter. Find where get_help is registered (look for `get_help` near the FastMCP setup sites around lines 34417, 34843). The `@logged_tool()` decorator should handle it automatically, but verify.

#### Task 1.2: Create _SKILLS_REGISTRY stub

Place this NEAR `_MONOLITH_INDEX` (around line 49668) or near get_help. Start EMPTY:

```python
# Level 1 code — all braces doubled
_SKILLS_REGISTRY = {{{{}}}}
_CATEGORY_REGISTRY = {{{{}}}}
```

Then validate: `python -m py_compile agent_compiler.py`

#### Task 1.3: Add 3-5 example skills docs

Pick simple tools first. Example for `bag_put`:

```python
_SKILLS_REGISTRY = {{{{
    "bag_put": {{{{
        "tool": "bag_put",
        "category": "memory_bag",
        "purpose": "Store an item in FelixBag persistent semantic memory with automatic BGE embedding for semantic search.",
        "parameters": {{{{
            "key": {{{{"type": "str", "required": True, "description": "Storage key. Use prefixes for organization (e.g., 'docs/myfile.md', 'config:setting')"}}}},
            "value": {{{{"type": "str", "required": True, "description": "Content to store. Strings only — serialize objects to JSON first."}}}}
        }}}},
        "returns": {{{{"structure": "JSON", "key_fields": ["status", "key", "id", "type"]}}}}
        "use_cases": [
            "Store configuration, documents, workflow definitions, agent session traces",
            "Persist data across server restarts",
            "Build semantic knowledge base searchable via bag_search"
        ],
        "related_tools": ["bag_get", "bag_search", "bag_catalog", "bag_induct", "bag_checkpoint"],
        "common_patterns": [
            "bag_put(key='docs/myfile.md', value=content) — store as document (auto-indexed)",
            "bag_put + bag_checkpoint — store then create named checkpoint for versioning",
            "bag_put + bag_search — store content, later find it semantically"
        ],
        "gotchas": [
            "Keys with 'docs/' prefix get document-style indexing automatically",
            "Values must be strings — use json.dumps() for structured data",
            "Overwrites existing key without warning — use bag_checkpoint first if versioning matters",
            "For file_write/file_list, pass strings for content/file_type (avoid null)"
        ]
    }}}},
}}}}
```

**YES, THAT IS EIGHT BRACES (`{{{{` / `}}}}`) FOR NESTED DICTS.** This is Level 1 code containing dict literals containing dict literals. The outer `{{` escapes to `{` in the output, and the inner `{{` inside that escapes to `{` again. Count them.

### Phase 2: Research & Write Skills Docs (one category at a time)

For each category, you need to:

1. **Read every `@logged_tool()` function** in that category from agent_compiler.py
2. **Extract all parameters** — types, defaults, validation, constraints
3. **Read the MCP handler** dispatch for each tool
4. **Study helper functions** called by each tool
5. **Check existing guides** in FelixBag (e.g., `cascade_tools_guide`, `workflow_automation_guide`)
6. **Write the complete skills document** per the schema
7. **Add to `_SKILLS_REGISTRY`** in agent_compiler.py

**Category order (foundational first):**
1. meta (7 tools) — get_help, get_about, get_onboarding, get_quickstart, get_embedder_info, list_models, heartbeat, demo
2. status_and_identity (13 tools)
3. memory_bag (18 tools)
4. file_workspace (16 tools)
5. inference (9 tools)
6. model_management (12 tools)
7. council (7 tools)
8. chat (4 tools)
9. cascade_lattice (7 tools)
10. workflow_automation (9 tools)
11. diagnostics (6 tools)
12. environment (6 tools)
13. huggingface_hub (8 tools)
14. vast_gpu (13 tools)
15. quine_and_export (12 tools)
16. hold_and_security (5 tools)
17. advanced (4 tools)
18. server_and_relay (6 tools)

### Phase 3: Category Documents
Write `_CATEGORY_REGISTRY` entries for all 18 categories with architecture notes, tool relationships, canonical patterns.

### Phase 4: Integration
- Wire get_help routing to both registries
- Update `_MONOLITH_INDEX` to reference skills system
- Update `get_onboarding` and `_build_mcp_instructions` to mention `get_help(topic)` syntax

### Phase 5: Validation
1. `python -m py_compile agent_compiler.py`
2. Regenerate champion_gen8.py, compress to capsule.gz
3. Test: `get_help()` returns overview, `get_help('bag_put')` returns skills doc, `get_help('workflow')` returns category doc

---

## KEY FILE LOCATIONS
- Agent compiler: `F:\End-Game\ouroboros-key\agent_compiler.py`
- Governing docs: `F:\End-Game\ouroboros-key\data\claudeoctor.txt` and `AGENT_COMPILER_INTEGRATION_SURFACES.md`
- Capsule runtime (generated, DO NOT EDIT): `F:\End-Game\champion_councl\capsule\champion_gen8.py`
- Compressed capsule: `F:\End-Game\champion_councl\capsule\capsule.gz`

## CRITICAL WARNINGS
1. **NEVER edit champion_gen8.py or capsule.gz directly**
2. **Brace escaping is the #1 failure mode** — count every brace
3. **Validate after EVERY edit**: `python -m py_compile agent_compiler.py`
4. **Start small** — get infrastructure working with 3-5 tools before scaling
5. **Each category is independently shippable** — don't try to do all 166 tools at once
6. **Preserve existing get_help() behavior for empty topic** — backward compatible

## DELIVERY
Each phase is a checkpoint. After Phase 1 infrastructure works, each Phase 2 category can be delivered independently. Validate compiles after every category.
