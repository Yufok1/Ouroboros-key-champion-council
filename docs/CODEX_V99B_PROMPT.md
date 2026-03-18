Codex Task: v99b — CC0 Asset Ingestion (Capsule-Side MCP Tools)

Files:
- F:\End-Game\ouroboros-key\agent_compiler.py (~57,000 lines, quine generator)

Scope: Add 5 new MCP tools (asset_search, asset_register, asset_download, asset_list, asset_catalog) and a CC0 seed catalog to the generated capsule runtime. Capsule-side only — no frontend changes.

CRITICAL: This file is a quine generator. Read F:\End-Game\ouroboros-key\data\claudeoctor.txt for the full escaping law BEFORE making any edits. Summary:

- **Level 1** (lines ~10003 to ~45237, inside `_generate_capsule_source()` f-string template):
  - `{` → `{{` for literal braces
  - `}` → `}}`
  - `"""` → `\"\"\"`
  - Dict literals: `{"key": "val"}` → `{{"key": "val"}}`
  - F-strings in output: `f"{var}"` → `f"{{var}}"`
- **Level 0** (lines before ~10003 and after ~45237): Normal Python — no brace doubling.

Each code block below is marked **LEVEL 0** or **LEVEL 1**. Use the correct escaping for each.

---
MANDATORY PRE-READ

Read these before editing. Use grep patterns to find current line numbers (they drift over time):

1. Escaping law: `F:\End-Game\ouroboros-key\data\claudeoctor.txt`
2. Integration surfaces: `F:\End-Game\ouroboros-key\data\AGENT_COMPILER_INTEGRATION_SURFACES.md` — read Sections 17 (propagation checklist) and 19 (change-type routing matrix, "New or renamed tool")
3. Hub tools monolith — grep: `def hub_count\(` (~line 41975). Read to end of function. New tools go AFTER hub_count, BEFORE `# ═══...Vast.ai Extended` header.
4. Hub tools TUI dispatch — grep: `elif tool == 'hub_count':` (~line 28246). Read to `# SLOT TOOLS` header. New dispatch goes after hub_count block.
5. Hub tools proxy-mode — grep: `def hub_search_datasets.*_bus_call` (~line 35444). New wrappers go AFTER hub_search_datasets, BEFORE `env_spawn`.
6. `_build_mcp_instructions` — grep: `"HuggingFace Hub:` (~line 35006). Extend with asset tools.
7. get_help overview — grep: `lines.append.*HUGGINGFACE HUB` (~line 2458). New section after capture_model.
8. `get_capabilities` — grep: `'skill_save', 'skill_search'` (~line 36540). Add tool names.
9. `populate_bag_with_embedded` — grep: `def populate_bag_with_embedded` (~line 13110). Read to `return added`. Seed catalog bootstrap goes before return.
10. FelixBag access patterns — grep: `_BAG.induct\|_BAG.search\|_BAG._bag\|_bag_find_item` to see how tools read/write the bag.
11. get_help skill topics — grep: `"huggingface_hub": \{\{` (~line 43367). Add asset_library category.
12. get_help workflow patterns — grep: `hub_search_datasets.*bag_induct` (~line 43450). Add asset patterns.
13. `_HELP_SKILLS_SEED` — grep: `"hub_count": \{` at Level 0 (~line 55085). Add 5 entries after hub_count.
14. `_HELP_CATEGORY_STUBS` — grep: `"huggingface_hub":` with `"tools":` (~line 56657). Add asset_library category.
15. `_HELP_TOPIC_ALIASES` — grep: `_HELP_TOPIC_ALIASES` (~line 50634). Add asset aliases.
16. `_MONOLITH_INDEX` mcp_tools — grep: `# Hub` in mcp_tools section (~line 56890). Add tool names.

---
PART 1: CC0 SEED CATALOG + BOOTSTRAP

A. Catalog Constant — **LEVEL 1 CODE**

Place BEFORE `def populate_bag_with_embedded():` (grep for that function definition). This is inside the f-string template — double all braces.

```python
    # CC0 Asset Catalog — seed data for asset_search/list/catalog
    _CC0_ASSET_CATALOG = [
        {{"id": "kenney/nature-kit", "source": "kenney", "name": "Nature Kit", "description": "Trees, rocks, flowers, mushrooms — 60+ low-poly models", "license": "CC0", "author": "Kenney", "tags": "nature,trees,rocks,plants,outdoor", "format": "glb", "style": "low-poly", "poly_budget": "low", "url": "https://kenney.nl/assets/nature-kit"}},
        {{"id": "kenney/space-kit", "source": "kenney", "name": "Space Kit", "description": "Spaceships, stations, asteroids, planets — 40+ models", "license": "CC0", "author": "Kenney", "tags": "space,sci-fi,ships,stations", "format": "glb", "style": "low-poly", "poly_budget": "low", "url": "https://kenney.nl/assets/space-kit"}},
        {{"id": "kenney/medieval-fantasy", "source": "kenney", "name": "Medieval Fantasy", "description": "Castles, towers, houses, walls — 30+ models", "license": "CC0", "author": "Kenney", "tags": "medieval,fantasy,castles,buildings", "format": "glb", "style": "low-poly", "poly_budget": "low", "url": "https://kenney.nl/assets/medieval-fantasy"}},
        {{"id": "kenney/city-kit-commercial", "source": "kenney", "name": "City Kit Commercial", "description": "Buildings, roads, vehicles, lampposts — 50+ models", "license": "CC0", "author": "Kenney", "tags": "city,urban,buildings,vehicles", "format": "glb", "style": "low-poly", "poly_budget": "low", "url": "https://kenney.nl/assets/city-kit-commercial"}},
        {{"id": "kenney/furniture-kit", "source": "kenney", "name": "Furniture Kit", "description": "Tables, chairs, shelves, beds — 20+ models", "license": "CC0", "author": "Kenney", "tags": "furniture,interior,house,indoor", "format": "glb", "style": "low-poly", "poly_budget": "low", "url": "https://kenney.nl/assets/furniture-kit"}},
        {{"id": "quaternius/ultimate-nature", "source": "quaternius", "name": "Ultimate Nature Pack", "description": "Trees, rocks, plants, flowers — 200+ models with variations", "license": "CC0", "author": "Quaternius", "tags": "nature,trees,rocks,plants,outdoor", "format": "glb", "style": "low-poly", "poly_budget": "low", "url": "https://quaternius.com/packs/ultimatenature.html"}},
        {{"id": "quaternius/medieval-buildings", "source": "quaternius", "name": "Medieval Buildings", "description": "Houses, towers, walls, bridges — 30+ models", "license": "CC0", "author": "Quaternius", "tags": "medieval,buildings,architecture", "format": "glb", "style": "low-poly", "poly_budget": "low", "url": "https://quaternius.com/packs/medievalbuildings.html"}},
        {{"id": "quaternius/lowpoly-foods", "source": "quaternius", "name": "Lowpoly Foods", "description": "Fruits, vegetables, meals — 50+ food models", "license": "CC0", "author": "Quaternius", "tags": "food,props,items", "format": "glb", "style": "low-poly", "poly_budget": "low", "url": "https://quaternius.com/packs/lowpolyfoods.html"}},
        {{"id": "quaternius/cyberpunk-game-kit", "source": "quaternius", "name": "Cyberpunk Game Kit", "description": "Futuristic buildings, vehicles, props — 40+ models", "license": "CC0", "author": "Quaternius", "tags": "cyberpunk,sci-fi,futuristic,buildings", "format": "glb", "style": "low-poly", "poly_budget": "low", "url": "https://quaternius.com/packs/cyberpunk.html"}},
        {{"id": "polyhaven/hdris", "source": "polyhaven", "name": "Poly Haven HDRIs", "description": "500+ CC0 environment HDRIs for lighting and skyboxes", "license": "CC0", "author": "Poly Haven", "tags": "hdri,lighting,environment,skybox", "format": "hdr", "style": "realistic", "poly_budget": "n/a", "url": "https://polyhaven.com/hdris"}},
        {{"id": "polyhaven/textures", "source": "polyhaven", "name": "Poly Haven Textures", "description": "1000+ CC0 PBR material textures", "license": "CC0", "author": "Poly Haven", "tags": "textures,pbr,materials", "format": "png", "style": "realistic", "poly_budget": "n/a", "url": "https://polyhaven.com/textures"}},
        {{"id": "polyhaven/models", "source": "polyhaven", "name": "Poly Haven Models", "description": "100+ CC0 3D scanned models", "license": "CC0", "author": "Poly Haven", "tags": "models,scanned,realistic,props", "format": "glb", "style": "realistic", "poly_budget": "high", "url": "https://polyhaven.com/models"}},
        {{"id": "ambientcg/pbr-materials", "source": "ambientcg", "name": "ambientCG PBR Materials", "description": "2000+ CC0 PBR texture sets — metals, woods, concrete, fabric", "license": "CC0", "author": "ambientCG", "tags": "textures,pbr,materials,surfaces", "format": "png", "style": "realistic", "poly_budget": "n/a", "url": "https://ambientcg.com/"}},
    ]
```

B. Seed Bootstrap — **LEVEL 1 CODE**

Add to `populate_bag_with_embedded()` BEFORE the final `return added` line (grep: `return added` after the populate function). This is Level 1 — double all braces.

```python
    # === CC0 ASSET CATALOG ===
    try:
        for _asset_entry in _CC0_ASSET_CATALOG:
            _asset_key = f"asset_pack:{{_asset_entry['source']}}:{{_asset_entry['id'].split('/')[-1]}}"
            bag.induct(_asset_key, json.dumps(_asset_entry), item_type='asset_catalog',
                       tags=['embedded', 'cc0', 'asset', _asset_entry['source']])
            added += 1
    except Exception:
        pass
```

---
PART 2: TOOL IMPLEMENTATIONS

All 5 tools go in the monolith @logged_tool section. Insert AFTER `hub_count` function ends (grep: the closing `return json.dumps` inside hub_count, then blank line), BEFORE the `# ═══...Vast.ai Extended` header.

Add this section header, helper function, and 5 tool implementations. **LEVEL 1 CODE** — double all braces for dict literals, use `\"\"\"` for docstrings.

```python
    # ═══════════════════════════════════════════════════════════
    # MCP TOOLS - Asset Library (CC0)
    # ═══════════════════════════════════════════════════════════

    def _asset_matches_filters(entry, src_lower, tag_set, lic_lower, fmt_lower):
        \"\"\"Check if an asset entry matches the given filters.\"\"\"
        if src_lower and str(entry.get('source', '')).lower() != src_lower:
            return False
        if lic_lower and str(entry.get('license', '')).lower() != lic_lower:
            return False
        if fmt_lower and str(entry.get('format', '')).lower() != fmt_lower:
            return False
        if tag_set:
            entry_tags = set(t.strip().lower() for t in str(entry.get('tags', '')).split(',') if t.strip())
            if not tag_set.intersection(entry_tags):
                return False
        return True

    @logged_tool()
    def asset_search(query: str = "", source: str = "", tags: str = "", license: str = "", format: str = "", limit: int = 20) -> str:
        \"\"\"Search the CC0 asset registry by query and filters.

        Args:
            query: Semantic search text (optional — if empty, lists all and applies filters)
            source: Filter by source (kenney, quaternius, polyhaven, ambientcg)
            tags: Comma-separated tag filter (nature, space, buildings, etc.)
            license: License filter (CC0, CC-BY, etc.)
            format: File format filter (glb, gltf, hdr, png, etc.)
            limit: Max results (default 20)

        Returns:
            JSON with matching asset entries
        \"\"\"
        try:
            populate_bag_with_embedded()
        except Exception:
            pass
        results = []
        tag_set = set(t.strip().lower() for t in tags.split(',') if t.strip()) if tags else set()
        src_lower = source.strip().lower() if source else ""
        lic_lower = license.strip().lower() if license else ""
        fmt_lower = format.strip().lower() if format else ""

        if query and query.strip():
            # Semantic search via bag
            if hasattr(_BAG, 'search'):
                raw = _BAG.search(query, top_k=limit * 3)
                for r in raw:
                    rname = r.get('name', '') if isinstance(r, dict) else str(r)
                    if not rname.startswith('asset_pack:'):
                        continue
                    try:
                        _eid, _eitem = _bag_find_item(rname)
                        if not _eitem:
                            continue
                        content = _eitem.get('content', '')
                        entry = json.loads(content) if isinstance(content, str) else content
                        if _asset_matches_filters(entry, src_lower, tag_set, lic_lower, fmt_lower):
                            results.append(entry)
                    except Exception:
                        continue
        else:
            # List all asset_pack:* entries
            for _iid, _item in _BAG._bag.items():
                _name = str(_item.get('name', ''))
                if not _name.startswith('asset_pack:'):
                    continue
                try:
                    content = _item.get('content', '')
                    entry = json.loads(content) if isinstance(content, str) else content
                    if _asset_matches_filters(entry, src_lower, tag_set, lic_lower, fmt_lower):
                        results.append(entry)
                except Exception:
                    continue

        results = results[:limit]
        return json.dumps({{"query": query, "filters": {{"source": source, "tags": tags, "license": license, "format": format}}, "count": len(results), "results": results}}, indent=2)

    @logged_tool()
    def asset_register(name: str, source: str, license: str = "CC0", url: str = "", author: str = "", tags: str = "", format: str = "glb", style: str = "", poly_budget: str = "", preview_url: str = "", description: str = "") -> str:
        \"\"\"Register an asset or pack in the CC0 asset registry.

        Args:
            name: Asset/pack name (required)
            source: Source identifier — kenney, quaternius, polyhaven, ambientcg, or custom (required)
            license: License — CC0, CC-BY, CC-BY-SA, etc. (default CC0)
            url: Download or source URL
            author: Author/creator name
            tags: Comma-separated tags
            format: File format — glb, gltf, obj, hdr, png, etc. (default glb)
            style: Visual style — low-poly, realistic, stylized
            poly_budget: Polygon budget — low, medium, high
            preview_url: Preview image URL
            description: Human-readable description

        Returns:
            Confirmation JSON
        \"\"\"
        if not name or not source:
            return json.dumps({{"error": "name and source are required"}})

        clean_name = name.strip().lower().replace(' ', '-')
        clean_source = source.strip().lower()
        asset_id = f"{{clean_source}}/{{clean_name}}"
        bag_key = f"asset_pack:{{clean_source}}:{{clean_name}}"

        from datetime import datetime as _dt
        entry = {{
            "id": asset_id,
            "source": clean_source,
            "name": name.strip(),
            "description": description,
            "license": license.strip(),
            "author": author.strip(),
            "tags": tags,
            "format": format.strip().lower(),
            "style": style.strip().lower(),
            "poly_budget": poly_budget.strip().lower(),
            "url": url.strip(),
            "preview_url": preview_url.strip(),
            "registered_at": _dt.now().isoformat()
        }}

        if hasattr(_BAG, 'induct'):
            _BAG.induct(bag_key, json.dumps(entry), item_type='asset_catalog',
                        tags=['asset', clean_source, license.strip()])
        elif hasattr(_BAG, 'put'):
            _BAG.put(bag_key, json.dumps(entry))
        else:
            _BAG._bag[bag_key] = json.dumps(entry)

        return json.dumps({{"status": "ok", "key": bag_key, "asset_id": asset_id}})

    @logged_tool()
    def asset_download(asset_key: str, destination: str = "") -> str:
        \"\"\"Download an asset file from the registry to local cache.

        Args:
            asset_key: FelixBag key (e.g. 'asset_pack:kenney:nature-kit') or asset ID (e.g. 'kenney/nature-kit')
            destination: Local file path (optional — defaults to .asset_cache/<source>/<filename>)

        Returns:
            JSON with local file path or error
        \"\"\"
        import urllib.request
        import os

        # Normalize key
        if '/' in asset_key and not asset_key.startswith('asset_pack:'):
            parts = asset_key.split('/', 1)
            asset_key = f"asset_pack:{{parts[0]}}:{{parts[1]}}"

        # Look up metadata
        _eid, _eitem = _bag_find_item(asset_key)
        if not _eitem:
            return json.dumps({{"error": f"Asset not found: {{asset_key}}", "hint": "Use asset_search or asset_list to find available assets"}})

        try:
            content = _eitem.get('content', '')
            meta = json.loads(content) if isinstance(content, str) else content
        except Exception:
            return json.dumps({{"error": "Could not parse asset metadata"}})

        url = meta.get('url', '')
        if not url:
            return json.dumps({{"error": "Asset has no download URL", "asset": asset_key}})

        # Determine destination
        if not destination:
            cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.asset_cache', meta.get('source', 'unknown'))
            os.makedirs(cache_dir, exist_ok=True)
            filename = url.split('/')[-1] or meta.get('name', 'asset').replace(' ', '_')
            if '.' not in filename:
                filename += f".{{meta.get('format', 'glb')}}"
            destination = os.path.join(cache_dir, filename)

        try:
            urllib.request.urlretrieve(url, destination)
            return json.dumps({{"status": "ok", "path": destination, "url": url, "size": os.path.getsize(destination)}})
        except Exception as e:
            return json.dumps({{"error": str(e), "url": url, "hint": "Check URL accessibility or try manually"}})

    @logged_tool()
    def asset_list(source: str = "", license: str = "", format: str = "", style: str = "", page: int = 1, limit: int = 20) -> str:
        \"\"\"List registered assets with optional filters.

        Args:
            source: Filter by source (kenney, quaternius, polyhaven, ambientcg)
            license: Filter by license (CC0, CC-BY, etc.)
            format: Filter by format (glb, hdr, png, etc.)
            style: Filter by style (low-poly, realistic, etc.)
            page: Page number (default 1)
            limit: Results per page (default 20)

        Returns:
            JSON with paginated asset list
        \"\"\"
        try:
            populate_bag_with_embedded()
        except Exception:
            pass

        all_entries = []
        src_lower = source.strip().lower() if source else ""
        lic_lower = license.strip().lower() if license else ""
        fmt_lower = format.strip().lower() if format else ""
        sty_lower = style.strip().lower() if style else ""

        for _iid, _item in _BAG._bag.items():
            _name = str(_item.get('name', ''))
            if not _name.startswith('asset_pack:'):
                continue
            try:
                content = _item.get('content', '')
                entry = json.loads(content) if isinstance(content, str) else content
                if src_lower and str(entry.get('source', '')).lower() != src_lower:
                    continue
                if lic_lower and str(entry.get('license', '')).lower() != lic_lower:
                    continue
                if fmt_lower and str(entry.get('format', '')).lower() != fmt_lower:
                    continue
                if sty_lower and str(entry.get('style', '')).lower() != sty_lower:
                    continue
                all_entries.append(entry)
            except Exception:
                continue

        # Sort by source then name
        all_entries.sort(key=lambda e: (e.get('source', ''), e.get('name', '')))

        # Paginate
        start = (page - 1) * limit
        page_entries = all_entries[start:start + limit]

        return json.dumps({{
            "total": len(all_entries),
            "page": page,
            "limit": limit,
            "pages": (len(all_entries) + limit - 1) // limit if all_entries else 0,
            "assets": page_entries
        }}, indent=2)

    @logged_tool()
    def asset_catalog() -> str:
        \"\"\"Get an overview of the asset registry — counts by source, license, format, style.

        Returns:
            JSON with registry statistics
        \"\"\"
        try:
            populate_bag_with_embedded()
        except Exception:
            pass

        by_source = {{}}
        by_license = {{}}
        by_format = {{}}
        by_style = {{}}
        total = 0

        for _iid, _item in _BAG._bag.items():
            _name = str(_item.get('name', ''))
            if not _name.startswith('asset_pack:'):
                continue
            try:
                content = _item.get('content', '')
                entry = json.loads(content) if isinstance(content, str) else content
                total += 1
                src = str(entry.get('source', 'unknown'))
                lic = str(entry.get('license', 'unknown'))
                fmt = str(entry.get('format', 'unknown'))
                sty = str(entry.get('style', '')) or 'unspecified'
                by_source[src] = by_source.get(src, 0) + 1
                by_license[lic] = by_license.get(lic, 0) + 1
                by_format[fmt] = by_format.get(fmt, 0) + 1
                by_style[sty] = by_style.get(sty, 0) + 1
            except Exception:
                continue

        return json.dumps({{
            "total_assets": total,
            "by_source": by_source,
            "by_license": by_license,
            "by_format": by_format,
            "by_style": by_style,
            "sources": sorted(by_source.keys())
        }}, indent=2)
```

---
PART 3: TUI _handle_mcp_request DISPATCH

Insert after the `hub_count` elif block (grep: `elif tool == 'hub_count':`, read to `result = {{'error': str(e)}}` and the blank line after). Place BEFORE the `# SLOT TOOLS` header.

**LEVEL 1 CODE** — double all braces. Indent is 16 spaces (4 levels deep).

```python
                # ═══════════════════════════════════════════════════════════
                # ASSET TOOLS
                # ═══════════════════════════════════════════════════════════
                elif tool == 'asset_search':
                    _aq = args.get('query', '')
                    _asrc = args.get('source', '')
                    _atags = args.get('tags', '')
                    _alic = args.get('license', '')
                    _afmt = args.get('format', '')
                    _alim = int(args.get('limit', 20))
                    try:
                        populate_bag_with_embedded()
                    except Exception:
                        pass
                    _aresults = []
                    _atag_set = set(t.strip().lower() for t in _atags.split(',') if t.strip()) if _atags else set()
                    _asrc_l = _asrc.strip().lower()
                    _alic_l = _alic.strip().lower()
                    _afmt_l = _afmt.strip().lower()
                    if _aq and _aq.strip():
                        if hasattr(_BAG, 'search'):
                            _araw = _BAG.search(_aq, top_k=_alim * 3)
                            for _ar in _araw:
                                _arname = _ar.get('name', '') if isinstance(_ar, dict) else str(_ar)
                                if not _arname.startswith('asset_pack:'):
                                    continue
                                try:
                                    _aeid, _aeitem = _bag_find_item(_arname)
                                    if _aeitem:
                                        _acontent = _aeitem.get('content', '')
                                        _aentry = json.loads(_acontent) if isinstance(_acontent, str) else _acontent
                                        if _asset_matches_filters(_aentry, _asrc_l, _atag_set, _alic_l, _afmt_l):
                                            _aresults.append(_aentry)
                                except Exception:
                                    continue
                    else:
                        for _aiid, _aitem in _BAG._bag.items():
                            _aname = str(_aitem.get('name', ''))
                            if not _aname.startswith('asset_pack:'):
                                continue
                            try:
                                _acontent = _aitem.get('content', '')
                                _aentry = json.loads(_acontent) if isinstance(_acontent, str) else _acontent
                                if _asset_matches_filters(_aentry, _asrc_l, _atag_set, _alic_l, _afmt_l):
                                    _aresults.append(_aentry)
                            except Exception:
                                continue
                    result = {{'query': _aq, 'count': len(_aresults[:_alim]), 'results': _aresults[:_alim]}}

                elif tool == 'asset_register':
                    _aname = args.get('name', '')
                    _asource = args.get('source', '')
                    if not _aname or not _asource:
                        result = {{'error': 'name and source are required'}}
                    else:
                        _aclean_name = _aname.strip().lower().replace(' ', '-')
                        _aclean_source = _asource.strip().lower()
                        _abag_key = f"asset_pack:{{_aclean_source}}:{{_aclean_name}}"
                        from datetime import datetime as _dt
                        _aentry = {{
                            'id': f"{{_aclean_source}}/{{_aclean_name}}",
                            'source': _aclean_source,
                            'name': _aname.strip(),
                            'description': args.get('description', ''),
                            'license': args.get('license', 'CC0').strip(),
                            'author': args.get('author', '').strip(),
                            'tags': args.get('tags', ''),
                            'format': args.get('format', 'glb').strip().lower(),
                            'style': args.get('style', '').strip().lower(),
                            'poly_budget': args.get('poly_budget', '').strip().lower(),
                            'url': args.get('url', '').strip(),
                            'preview_url': args.get('preview_url', '').strip(),
                            'registered_at': _dt.now().isoformat()
                        }}
                        if hasattr(_BAG, 'induct'):
                            _BAG.induct(_abag_key, json.dumps(_aentry), item_type='asset_catalog',
                                        tags=['asset', _aclean_source])
                        elif hasattr(_BAG, 'put'):
                            _BAG.put(_abag_key, json.dumps(_aentry))
                        result = {{'status': 'ok', 'key': _abag_key, 'asset_id': _aentry['id']}}

                elif tool == 'asset_download':
                    _akey = args.get('asset_key', '')
                    _adest = args.get('destination', '')
                    import urllib.request
                    import os
                    if '/' in _akey and not _akey.startswith('asset_pack:'):
                        _aparts = _akey.split('/', 1)
                        _akey = f"asset_pack:{{_aparts[0]}}:{{_aparts[1]}}"
                    _aeid, _aeitem = _bag_find_item(_akey)
                    if not _aeitem:
                        result = {{'error': f'Asset not found: {{_akey}}', 'hint': 'Use asset_search or asset_list to find available assets'}}
                    else:
                        try:
                            _acontent = _aeitem.get('content', '')
                            _ameta = json.loads(_acontent) if isinstance(_acontent, str) else _acontent
                            _aurl = _ameta.get('url', '')
                            if not _aurl:
                                result = {{'error': 'Asset has no download URL', 'asset': _akey}}
                            else:
                                if not _adest:
                                    _acache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.asset_cache', _ameta.get('source', 'unknown'))
                                    os.makedirs(_acache_dir, exist_ok=True)
                                    _afn = _aurl.split('/')[-1] or _ameta.get('name', 'asset').replace(' ', '_')
                                    if '.' not in _afn:
                                        _afn += f".{{_ameta.get('format', 'glb')}}"
                                    _adest = os.path.join(_acache_dir, _afn)
                                urllib.request.urlretrieve(_aurl, _adest)
                                result = {{'status': 'ok', 'path': _adest, 'url': _aurl, 'size': os.path.getsize(_adest)}}
                        except Exception as e:
                            result = {{'error': str(e)}}

                elif tool == 'asset_list':
                    _asrc = args.get('source', '').strip().lower()
                    _alic = args.get('license', '').strip().lower()
                    _afmt = args.get('format', '').strip().lower()
                    _asty = args.get('style', '').strip().lower()
                    _apage = int(args.get('page', 1))
                    _alimit = int(args.get('limit', 20))
                    try:
                        populate_bag_with_embedded()
                    except Exception:
                        pass
                    _aall = []
                    for _aiid, _aitem in _BAG._bag.items():
                        _an = str(_aitem.get('name', ''))
                        if not _an.startswith('asset_pack:'):
                            continue
                        try:
                            _ac = _aitem.get('content', '')
                            _ae = json.loads(_ac) if isinstance(_ac, str) else _ac
                            if _asrc and str(_ae.get('source', '')).lower() != _asrc:
                                continue
                            if _alic and str(_ae.get('license', '')).lower() != _alic:
                                continue
                            if _afmt and str(_ae.get('format', '')).lower() != _afmt:
                                continue
                            if _asty and str(_ae.get('style', '')).lower() != _asty:
                                continue
                            _aall.append(_ae)
                        except Exception:
                            continue
                    _aall.sort(key=lambda e: (e.get('source', ''), e.get('name', '')))
                    _astart = (_apage - 1) * _alimit
                    result = {{'total': len(_aall), 'page': _apage, 'limit': _alimit, 'assets': _aall[_astart:_astart + _alimit]}}

                elif tool == 'asset_catalog':
                    try:
                        populate_bag_with_embedded()
                    except Exception:
                        pass
                    _aby_src = {{}}
                    _aby_lic = {{}}
                    _aby_fmt = {{}}
                    _atotal = 0
                    for _aiid, _aitem in _BAG._bag.items():
                        _an = str(_aitem.get('name', ''))
                        if not _an.startswith('asset_pack:'):
                            continue
                        try:
                            _ac = _aitem.get('content', '')
                            _ae = json.loads(_ac) if isinstance(_ac, str) else _ac
                            _atotal += 1
                            _as = str(_ae.get('source', 'unknown'))
                            _al = str(_ae.get('license', 'unknown'))
                            _af = str(_ae.get('format', 'unknown'))
                            _aby_src[_as] = _aby_src.get(_as, 0) + 1
                            _aby_lic[_al] = _aby_lic.get(_al, 0) + 1
                            _aby_fmt[_af] = _aby_fmt.get(_af, 0) + 1
                        except Exception:
                            continue
                    result = {{'total_assets': _atotal, 'by_source': _aby_src, 'by_license': _aby_lic, 'by_format': _aby_fmt, 'sources': sorted(_aby_src.keys())}}
```

---
PART 4: PROXY-MODE WRAPPERS

Insert after the `hub_search_datasets` proxy wrapper (grep: `def hub_search_datasets.*_bus_call`), BEFORE `env_spawn`. **LEVEL 1 CODE** — 8-space indent.

```python
        @logged_tool()
        def asset_search(query: str = "", source: str = "", tags: str = "", license: str = "", format: str = "", limit: int = 20) -> str:
            \"\"\"Search the CC0 asset registry by query and filters.\"\"\"
            return _bus_call('asset_search', {{'query': query, 'source': source, 'tags': tags, 'license': license, 'format': format, 'limit': limit}})

        @logged_tool()
        def asset_register(name: str, source: str, license: str = "CC0", url: str = "", author: str = "", tags: str = "", format: str = "glb", style: str = "", poly_budget: str = "", preview_url: str = "", description: str = "") -> str:
            \"\"\"Register an asset or pack in the CC0 asset registry.\"\"\"
            return _bus_call('asset_register', {{'name': name, 'source': source, 'license': license, 'url': url, 'author': author, 'tags': tags, 'format': format, 'style': style, 'poly_budget': poly_budget, 'preview_url': preview_url, 'description': description}})

        @logged_tool()
        def asset_download(asset_key: str, destination: str = "") -> str:
            \"\"\"Download an asset file from the registry to local cache.\"\"\"
            return _bus_call('asset_download', {{'asset_key': asset_key, 'destination': destination}})

        @logged_tool()
        def asset_list(source: str = "", license: str = "", format: str = "", style: str = "", page: int = 1, limit: int = 20) -> str:
            \"\"\"List registered assets with optional filters.\"\"\"
            return _bus_call('asset_list', {{'source': source, 'license': license, 'format': format, 'style': style, 'page': page, 'limit': limit}})

        @logged_tool()
        def asset_catalog() -> str:
            \"\"\"Get an overview of the asset registry.\"\"\"
            return _bus_call('asset_catalog', {{}})
```

---
PART 5: DISCOVERY SURFACE PROPAGATION

### A. _build_mcp_instructions — **LEVEL 1 CODE**

Grep: `"HuggingFace Hub:` (~line 35006). Add a new line AFTER the hub line:

```python
            "Asset Library: asset_search, asset_register, asset_download, asset_list, asset_catalog.\\n"
```

### B. get_help overview / README — **LEVEL 0 CODE**

Grep: `lines.append.*capture_model` (~line 2466). Add AFTER the `capture_model` line and before the blank line / VAST section:

```python
        lines.append("")
        lines.append("  ASSET LIBRARY (5 tools)")
        lines.append("    asset_search     → Search CC0 asset registry by query and filters")
        lines.append("    asset_register   → Register an asset or pack (CC0 sources)")
        lines.append("    asset_download   → Download asset file to local cache")
        lines.append("    asset_list       → List registered assets with filters")
        lines.append("    asset_catalog    → Overview stats of the asset registry")
```

### C. get_capabilities — **LEVEL 1 CODE**

Grep: `'skill_save', 'skill_search', 'skill_apply'` (~line 36540). Add after this line, before the `])`:

```python
            'asset_search', 'asset_register', 'asset_download', 'asset_list', 'asset_catalog',
```

### D. get_help skill topics — **LEVEL 1 CODE**

Grep: `"huggingface_hub": \{\{` (~line 43367). Add AFTER the closing `}},` of the huggingface_hub block (after `"hub_plug": "Search and plug in one step"`):

```python
                "asset_library": {{
                    "asset_search": "Search CC0 asset registry by query and filters",
                    "asset_register": "Register an asset or pack",
                    "asset_download": "Download asset file to local cache",
                    "asset_list": "List registered assets with filters",
                    "asset_catalog": "Overview stats of the asset registry"
                }},
```

### E. get_help workflow patterns — **LEVEL 1 CODE**

Grep: `hub_search_datasets.*bag_induct` (~line 43450). Add AFTER that line:

```python
                "asset_search() → asset_download() → env_spawn() - Find CC0 asset and place in scene",
                "asset_catalog() → asset_list(source='kenney') → asset_search(tags='nature') - Browse CC0 library",
```

### F. _HELP_SKILLS_SEED — **LEVEL 0 CODE** (this is OUTSIDE the f-string template)

Grep: `"hub_count": {` (~line 55085). Find the closing `},` of the hub_count entry (should end around line ~55114). Add AFTER it:

```python
    "asset_search": {
        "tool": "asset_search",
        "category": "asset_library",
        "purpose": "Search the CC0 asset registry by semantic query and/or structured filters (source, tags, license, format).",
        "parameters": {
            "query": {"type": "str", "required": False, "default": "", "description": "Semantic search text. If empty, returns all assets matching filters."},
            "source": {"type": "str", "required": False, "default": "", "description": "Filter by source: kenney, quaternius, polyhaven, ambientcg."},
            "tags": {"type": "str", "required": False, "default": "", "description": "Comma-separated tag filter."},
            "license": {"type": "str", "required": False, "default": "", "description": "License filter: CC0, CC-BY, etc."},
            "format": {"type": "str", "required": False, "default": "", "description": "File format filter: glb, gltf, hdr, png."},
            "limit": {"type": "int", "required": False, "default": 20, "description": "Max results."}
        },
        "returns": {"structure": "JSON", "key_fields": ["query", "filters", "count", "results"]},
        "use_cases": [
            "Find nature assets across all CC0 sources.",
            "Filter to only Kenney GLB packs.",
            "Semantic search for 'medieval castle buildings'."
        ],
        "related_tools": ["asset_list", "asset_catalog", "asset_download", "asset_register"],
        "common_patterns": [
            "asset_search(query='nature') to find relevant packs.",
            "asset_search(source='kenney', format='glb') for filtered browsing.",
            "asset_search(query='castle') -> asset_download(key) -> env_spawn() for end-to-end."
        ],
        "gotchas": ["Semantic search uses FelixBag embeddings — quality depends on description richness."]
    },
    "asset_register": {
        "tool": "asset_register",
        "category": "asset_library",
        "purpose": "Register a new asset or asset pack into the CC0 asset registry stored in FelixBag.",
        "parameters": {
            "name": {"type": "str", "required": True, "description": "Asset or pack name."},
            "source": {"type": "str", "required": True, "description": "Source identifier (kenney, quaternius, polyhaven, ambientcg, or custom)."},
            "license": {"type": "str", "required": False, "default": "CC0", "description": "License string."},
            "url": {"type": "str", "required": False, "default": "", "description": "Download or source URL."},
            "author": {"type": "str", "required": False, "default": "", "description": "Author name."},
            "tags": {"type": "str", "required": False, "default": "", "description": "Comma-separated tags."},
            "format": {"type": "str", "required": False, "default": "glb", "description": "File format."},
            "style": {"type": "str", "required": False, "default": "", "description": "Visual style."},
            "poly_budget": {"type": "str", "required": False, "default": "", "description": "Polygon budget: low, medium, high."},
            "preview_url": {"type": "str", "required": False, "default": "", "description": "Preview image URL."},
            "description": {"type": "str", "required": False, "default": "", "description": "Description."}
        },
        "returns": {"structure": "JSON", "key_fields": ["status", "key", "asset_id"]},
        "use_cases": [
            "Register a custom asset pack not in the seed catalog.",
            "Add a Sketchfab download with CC-BY attribution.",
            "Bulk-register a set of CC0 models from a local directory."
        ],
        "related_tools": ["asset_search", "asset_list", "asset_catalog", "bag_put"],
        "common_patterns": ["asset_register(name='...', source='custom', ...) -> asset_download(key) to make asset locally available."],
        "gotchas": ["name and source are required. Key is derived as asset_pack:<source>:<name>."]
    },
    "asset_download": {
        "tool": "asset_download",
        "category": "asset_library",
        "purpose": "Download an asset file from its registered URL to local cache.",
        "parameters": {
            "asset_key": {"type": "str", "required": True, "description": "FelixBag key (asset_pack:source:name) or shorthand (source/name)."},
            "destination": {"type": "str", "required": False, "default": "", "description": "Local file path. Defaults to .asset_cache/<source>/<filename>."}
        },
        "returns": {"structure": "JSON", "key_fields": ["status", "path", "url", "size", "error"]},
        "use_cases": [
            "Download a Kenney pack ZIP for local extraction.",
            "Cache an HDRI from Poly Haven for environment lighting.",
            "Download a specific GLB model for env_spawn."
        ],
        "related_tools": ["asset_search", "asset_register", "env_spawn"],
        "common_patterns": ["asset_search('nature') -> asset_download(key) -> env_spawn() for full pipeline."],
        "gotchas": ["Uses urllib — some URLs may require auth or redirect handling. The tool stores to .asset_cache/ by default."]
    },
    "asset_list": {
        "tool": "asset_list",
        "category": "asset_library",
        "purpose": "List all registered assets with optional filtering and pagination.",
        "parameters": {
            "source": {"type": "str", "required": False, "default": "", "description": "Filter by source."},
            "license": {"type": "str", "required": False, "default": "", "description": "Filter by license."},
            "format": {"type": "str", "required": False, "default": "", "description": "Filter by format."},
            "style": {"type": "str", "required": False, "default": "", "description": "Filter by style."},
            "page": {"type": "int", "required": False, "default": 1, "description": "Page number."},
            "limit": {"type": "int", "required": False, "default": 20, "description": "Results per page."}
        },
        "returns": {"structure": "JSON", "key_fields": ["total", "page", "limit", "pages", "assets"]},
        "use_cases": [
            "Browse all kenney packs: asset_list(source='kenney').",
            "Filter to GLB models only: asset_list(format='glb').",
            "Paginate through the full registry."
        ],
        "related_tools": ["asset_search", "asset_catalog", "asset_download"],
        "common_patterns": ["asset_list() for full overview, then asset_list(source='kenney') to drill down."],
        "gotchas": ["Returns all matching entries from FelixBag — ensure populate_bag_with_embedded has run for seed data."]
    },
    "asset_catalog": {
        "tool": "asset_catalog",
        "category": "asset_library",
        "purpose": "Get an overview of the asset registry with counts by source, license, format, and style.",
        "parameters": {},
        "returns": {"structure": "JSON", "key_fields": ["total_assets", "by_source", "by_license", "by_format", "by_style", "sources"]},
        "use_cases": [
            "Check how many assets are registered.",
            "See which sources have the most content.",
            "Verify CC0 coverage across formats."
        ],
        "related_tools": ["asset_list", "asset_search"],
        "common_patterns": ["asset_catalog() first to understand the registry, then asset_list(source='...') to drill down."],
        "gotchas": ["Counts reflect FelixBag state — run populate_bag_with_embedded for seed data."]
    },
```

### G. _HELP_CATEGORY_STUBS — **LEVEL 0 CODE**

Grep: `"huggingface_hub":` with `"tools":` (~line 56657). Find its closing `},` (should end around line ~56664). Add AFTER it:

```python
    "asset_library": {
        "category": "asset_library",
        "purpose": "CC0 asset discovery, registration, download, and catalog — manages a FelixBag-backed asset registry.",
        "tools": ["asset_search", "asset_register", "asset_download", "asset_list", "asset_catalog"],
        "architecture": "Asset metadata lives in FelixBag under 'asset_pack:<source>:<name>' keys. Semantic search via bag embeddings, structured filters via post-processing. Seed catalog bootstraps 13 CC0 packs from Kenney, Quaternius, Poly Haven, ambientCG.",
        "canonical_patterns": ["asset_catalog -> asset_list(source='...') -> asset_search(tags='...') -> asset_download -> env_spawn"],
        "status": "seeded"
    },
```

### H. _HELP_TOPIC_ALIASES — **LEVEL 0 CODE**

Grep: `_HELP_TOPIC_ALIASES` (~line 50634). Add inside the dict:

```python
    "assets": "asset_library",
    "cc0": "asset_library",
    "asset": "asset_library",
```

### I. _MONOLITH_INDEX mcp_tools — **LEVEL 0 CODE**

Grep: `# Hub` in the mcp_tools section (~line 56890). Add AFTER the Hub line:

```python
        # Asset Library
        "asset_search", "asset_register", "asset_download", "asset_list", "asset_catalog",
```

---
Testing

1. `python -m py_compile agent_compiler.py` passes
2. After regeneration and startup:
   - `asset_catalog()` returns JSON with 13 seed entries, 4 sources (kenney, quaternius, polyhaven, ambientcg), all CC0
   - `asset_list()` returns paginated list of all 13 seed assets
   - `asset_list(source='kenney')` returns only Kenney packs (5 entries)
   - `asset_list(format='glb')` returns only GLB format assets
   - `asset_search(query='nature')` returns Nature Kit and Ultimate Nature Pack via semantic match
   - `asset_search(source='quaternius', tags='medieval')` returns Medieval Buildings
   - `asset_register(name='My Custom Pack', source='custom', description='Test assets', tags='test')` registers successfully
   - After register: `asset_list(source='custom')` shows the new entry
   - `asset_download(asset_key='kenney/nature-kit')` attempts HTTP download from kenney.nl URL
   - `get_help(topic='asset_library')` returns full category documentation
   - `get_help(topic='asset_search')` returns tool-level documentation
   - `get_capabilities()` includes all 5 asset tool names
   - `asset_catalog()` after register shows 14 total (13 seed + 1 custom)

---
Constraints

- ONLY edit agent_compiler.py — no other files
- Read `claudeoctor.txt` before any edits — obey the escaping law
- Read surrounding 50 lines of context before editing any section
- Level 1 code (lines ~10003 to ~45237): double all `{` and `}`, use `\"\"\"` for docstrings
- Level 0 code (before ~10003 and after ~45237): normal Python, no escaping
- Use `var` naming with `_a` prefix in TUI dispatch to avoid variable name collisions with surrounding code
- Minimal diff — do NOT modify existing hub, vast, env, or other tool implementations
- Do NOT add TUI direct-action dispatch (`elif action == 'asset'`) — asset tools are MCP-only like environment/workstation/facility/skills tools
- Do NOT add arcade writers — asset tools do not need arcade export
- Do NOT modify `_generate_ensemble_source()` — only `_generate_capsule_source()` and Level 0 sections
- Helper function `_asset_matches_filters` is defined BEFORE `asset_search` so it's callable at runtime
- The `_bag_find_item` helper already exists at ~line 38662 — use it, do NOT redefine it
- The `_BAG` global already exists at ~line 13011 — use it, do NOT redefine it
- `populate_bag_with_embedded()` already has a guard `if len(bag._bag) > 0: return 0` — seed catalog only populates on first run
- Validate: `python -m py_compile agent_compiler.py` after every edit
