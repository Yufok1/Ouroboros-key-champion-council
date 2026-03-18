Codex Task: v99b-patch — Asset Tool Schema Correction (download_url / download_mode / migration)

Files:
- F:\End-Game\ouroboros-key\agent_compiler.py (~57,000 lines, quine generator)

Scope: Schema correction pass on the 5 asset tools added in v99b. The tools are wired and working structurally, but the seed catalog `url` fields point to HTML landing pages, not downloadable files. `asset_download` would silently save HTML as `.glb`. This patch adds `download_url`, `download_mode`, and `download_ext` fields, upgrades the bootstrap migration, and hardens the download tool.

No new tools. No new propagation surfaces. All changes are within existing code.

CRITICAL: This file is a quine generator. Read F:\End-Game\ouroboros-key\data\claudeoctor.txt for the full escaping law BEFORE making any edits.

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

Read these before editing. Use grep to find current line numbers (they drift):

1. Escaping law: `F:\End-Game\ouroboros-key\data\claudeoctor.txt`
2. Integration surfaces: `F:\End-Game\ouroboros-key\data\AGENT_COMPILER_INTEGRATION_SURFACES.md`
3. Seed catalog — grep: `_CC0_ASSET_CATALOG = \[` (~line 13118). Read all 13 entries through closing `]`.
4. Bootstrap migration — grep: `def _ensure_asset_catalog` (~line 13145). Read through `return _asset_added`.
5. asset_register monolith — grep: `def asset_register\(name:` inside `@logged_tool` (~line 42430). Read through `return json.dumps`.
6. asset_download monolith — grep: `def asset_download\(asset_key:` inside `@logged_tool` (~line 42489). Read through `return json.dumps`.
7. TUI asset_register dispatch — grep: `elif tool == 'asset_register':` (~line 28393). Read through `result = {{'status': 'ok'`.
8. TUI asset_download dispatch — grep: `elif tool == 'asset_download':` (~line 28429). Read through `result = {{'error': str(e)`.
9. Proxy asset_register — grep: `def asset_register.*_bus_call` (~line 35745). Read single function.
10. Help: _HELP_SKILLS_SEED asset_register — grep: `"asset_register": \{` at Level 0 (~line 55804). Read through closing `}`.
11. Help: _HELP_SKILLS_SEED asset_download — grep: `"asset_download": \{` at Level 0 (~line 55831). Read through closing `}`.
12. Help: _HELP_CATEGORY_STUBS asset_library — grep: `"asset_library": \{` at Level 0 (~line 57436). Read full entry.
13. README / tool-list generation — grep: `ASSET LIBRARY` (~line 2468). Read the 5 asset tool description lines.
14. get_help skill topics — grep: `"asset_library": \{\{` at Level 1 (~line 44025). Read all 5 tool entries.
15. get_help common patterns — grep: `asset_search.*asset_download.*env_spawn` at Level 1 (~line 44109). Read the 2 asset patterns.

---
PART 1: SEED CATALOG — Add download fields — **LEVEL 1 CODE**

Find `_CC0_ASSET_CATALOG = [` (~line 13118).

Add three new fields to EVERY entry: `download_url`, `download_mode`, `download_ext`.

Rules:
- `url` stays as-is — it's the human-readable source/landing page.
- `download_url` is the direct-download URL. For all 13 seed entries, set to `""` (empty string) because no CC0 source has a stable predictable pack-level download URL.
- `download_mode` describes how to acquire the asset:
  - `"archive"` — Kenney and Quaternius packs (download is a ZIP but URL is not predictable)
  - `"catalog_only"` — Poly Haven and ambientCG (individual items available via API, no single pack download)
- `download_ext` is the expected file extension of the downloaded file:
  - `".zip"` for Kenney and Quaternius (archive packs)
  - `""` for Poly Haven and ambientCG catalog entries

The replacement should keep the same single-line format for each entry. Add the three fields after `"url"`:

For Kenney entries (5 entries, ids: kenney/nature-kit through kenney/furniture-kit):
```
..., "url": "<existing>", "download_url": "", "download_mode": "archive", "download_ext": ".zip"}},
```

For Quaternius entries (4 entries, ids: quaternius/ultimate-nature through quaternius/cyberpunk-game-kit):
```
..., "url": "<existing>", "download_url": "", "download_mode": "archive", "download_ext": ".zip"}},
```

For Poly Haven entries (3 entries, ids: polyhaven/hdris, polyhaven/textures, polyhaven/models):
```
..., "url": "<existing>", "download_url": "", "download_mode": "catalog_only", "download_ext": ""}},
```

For ambientCG entry (1 entry, id: ambientcg/pbr-materials):
```
..., "url": "<existing>", "download_url": "", "download_mode": "catalog_only", "download_ext": ""}},
```

---
PART 2: BOOTSTRAP MIGRATION — Upgrade stale entries — **LEVEL 1 CODE**

Find `def _ensure_asset_catalog():` (~line 13145).

Current code skips entries where `_asset_key in _existing`. This means existing bags with v99b-initial schema will NEVER get the new `download_mode` field.

Replace the entire `_ensure_asset_catalog` function (from `def _ensure_asset_catalog():` through `return _asset_added`) with:

```python
    def _ensure_asset_catalog():
        _asset_added = 0
        _asset_upgraded = 0
        _existing = {{}}
        try:
            for _iid, _item in getattr(bag, '_bag', {{}}).items():
                _name = str(_item.get('name', ''))
                if _name:
                    _existing[_name] = _iid
                    _existing[_iid] = _iid
        except Exception:
            pass
        for _asset_entry in _CC0_ASSET_CATALOG:
            _asset_key = f"asset_pack:{{_asset_entry['source']}}:{{_asset_entry['id'].split('/')[-1]}}"
            if _asset_key in _existing:
                # Schema migration: check if existing entry has download_mode
                try:
                    _eid = _existing[_asset_key]
                    _eitem = bag._bag.get(_eid, {{}})
                    _etext = _bag_item_text(_eitem) if _eitem else ''
                    if _etext:
                        _eparsed = json.loads(_etext)
                        if 'download_mode' not in _eparsed or 'download_url' not in _eparsed or 'download_ext' not in _eparsed:
                            # Upgrade: merge all missing download fields from seed
                            for _fld in ('download_url', 'download_mode', 'download_ext'):
                                if _fld not in _eparsed:
                                    _eparsed[_fld] = _asset_entry.get(_fld, '')
                            bag.induct(
                                _asset_key,
                                json.dumps(_eparsed),
                                item_type='asset_catalog',
                                tags=['embedded', 'cc0', 'asset', _asset_entry['source'], 'upgraded']
                            )
                            _asset_upgraded += 1
                except Exception:
                    pass
                continue
            try:
                bag.induct(
                    _asset_key,
                    json.dumps(_asset_entry),
                    item_type='asset_catalog',
                    tags=['embedded', 'cc0', 'asset', _asset_entry['source']]
                )
                _asset_added += 1
            except Exception:
                continue
        return _asset_added + _asset_upgraded
```

IMPORTANT: This is Level 1. All `{}` → `{{}}`, all `f"{x}"` → `f"{{x}}"`. The code above is already shown in Level 1 escaping.

---
PART 3: asset_register — Add new parameters — **LEVEL 1 CODE**

Find `def asset_register(name:` inside `@logged_tool()` (~line 42430).

A. Change the function signature — add three new params after `preview_url`:

OLD:
```python
    def asset_register(name: str, source: str, license: str = "CC0", url: str = "", author: str = "", tags: str = "", format: str = "glb", style: str = "", poly_budget: str = "", preview_url: str = "", description: str = "") -> str:
```

NEW:
```python
    def asset_register(name: str, source: str, license: str = "CC0", url: str = "", author: str = "", tags: str = "", format: str = "glb", style: str = "", poly_budget: str = "", preview_url: str = "", download_url: str = "", download_mode: str = "direct_file", download_ext: str = "", description: str = "") -> str:
```

B. Update the docstring — add these lines after the `preview_url` arg doc:

```
            download_url: Direct download URL (if different from source page url)
            download_mode: How to acquire - direct_file, archive, or catalog_only (default direct_file)
            download_ext: Expected file extension of download (e.g. .zip, .glb)
```

C. Add the new fields to the `entry` dict (after `"preview_url"` line):

OLD:
```python
            "preview_url": preview_url.strip(),
            "registered_at": _dt.now().isoformat()
```

NEW:
```python
            "preview_url": preview_url.strip(),
            "download_url": download_url.strip(),
            "download_mode": download_mode.strip().lower() or "direct_file",
            "download_ext": download_ext.strip(),
            "registered_at": _dt.now().isoformat()
```

---
PART 4: asset_download — Hardening — **LEVEL 1 CODE**

Find `def asset_download(asset_key:` inside `@logged_tool()` (~line 42489).

Replace the ENTIRE function body (from `def asset_download(` through the final `return json.dumps(...)` of that function) with this hardened version:

```python
    @logged_tool()
    def asset_download(asset_key: str, destination: str = "") -> str:
        \"\"\"Download an asset file from the registry to local cache.

        Args:
            asset_key: FelixBag key (e.g. 'asset_pack:kenney:nature-kit') or asset ID (e.g. 'kenney/nature-kit')
            destination: Local file path (optional - defaults to .asset_cache/<source>/<filename>)

        Returns:
            JSON with local file path or error
        \"\"\"
        import urllib.request
        import os

        if '/' in asset_key and not asset_key.startswith('asset_pack:'):
            parts = asset_key.split('/', 1)
            asset_key = f"asset_pack:{{parts[0]}}:{{parts[1]}}"

        _eid, _eitem = _bag_find_item(asset_key)
        if not _eitem:
            return json.dumps({{"error": f"Asset not found: {{asset_key}}", "hint": "Use asset_search or asset_list to find available assets"}})

        try:
            meta = _asset_entry_from_bag_item(_eitem)
            if not meta:
                raise ValueError("empty asset metadata")
        except Exception:
            return json.dumps({{"error": "Could not parse asset metadata"}})

        # Determine download mode
        dl_mode = meta.get('download_mode', 'direct_file')

        # Reject catalog_only — these are API-based catalogs, not single-file downloads
        if dl_mode == 'catalog_only':
            source = meta.get('source', 'unknown')
            return json.dumps({{
                "error": f"This is a catalog source ({{source}}) — individual items must be fetched via its API, not as a single pack download.",
                "source": source,
                "source_url": meta.get('url', ''),
                "hint": f"Use asset_register to add specific items from {{source}} with their direct download URLs."
            }})

        # Prefer download_url over url
        dl_url = meta.get('download_url', '') or meta.get('url', '')
        if not dl_url:
            return json.dumps({{"error": "Asset has no download URL", "asset": asset_key, "hint": "Register a download_url with asset_register."}})

        # Warn if download_url is empty and we're falling back to url (likely a landing page)
        using_fallback = not meta.get('download_url', '') and dl_url == meta.get('url', '')
        if using_fallback and dl_mode == 'archive':
            return json.dumps({{
                "error": "No direct download URL available for this archive pack.",
                "source_url": dl_url,
                "download_mode": dl_mode,
                "hint": "Download the pack manually from the source page. Then use asset_register with download_url set to the local file path or a direct URL."
            }})

        # Derive filename
        dl_ext = meta.get('download_ext', '')
        asset_name = meta.get('name', 'asset').replace(' ', '_')
        if dl_ext:
            filename = f"{{asset_name}}{{dl_ext}}"
        else:
            url_tail = dl_url.split('/')[-1].split('?')[0]
            if '.' in url_tail and len(url_tail) < 100:
                filename = url_tail
            else:
                fmt = meta.get('format', 'glb')
                filename = f"{{asset_name}}.{{fmt}}"

        if not destination:
            cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.asset_cache', meta.get('source', 'unknown'))
            os.makedirs(cache_dir, exist_ok=True)
            destination = os.path.join(cache_dir, filename)
        else:
            parent = os.path.dirname(destination)
            if parent:
                os.makedirs(parent, exist_ok=True)

        # Support local file paths: copy instead of HTTP fetch
        if os.path.isfile(dl_url) or dl_url.startswith('file://'):
            import shutil
            _local_src = dl_url.replace('file:///', '').replace('file://', '') if dl_url.startswith('file://') else dl_url
            if not os.path.isfile(_local_src):
                return json.dumps({{"error": f"Local file not found: {{_local_src}}"}})
            shutil.copy2(_local_src, destination)
            return json.dumps({{"status": "ok", "path": destination, "source_path": _local_src, "size": os.path.getsize(destination), "download_mode": dl_mode}})

        try:
            _req = urllib.request.urlopen(dl_url, timeout=30)
            _ct = _req.headers.get('Content-Type', '')
            if 'text/html' in _ct:
                _req.close()
                return json.dumps({{
                    "error": "URL returned Content-Type text/html — this is a landing page, not a binary asset.",
                    "url": dl_url,
                    "content_type": _ct,
                    "hint": "Use asset_register to set a direct download_url."
                }})
            with open(destination, 'wb') as _out:
                _head = _req.read(512)
                if b'<html' in _head.lower() or b'<!doctype' in _head.lower():
                    _req.close()
                    return json.dumps({{
                        "error": "Downloaded content appears to be HTML despite Content-Type.",
                        "url": dl_url,
                        "hint": "The URL may be a landing page. Use asset_register to set a direct download_url."
                    }})
                _out.write(_head)
                while True:
                    _chunk = _req.read(65536)
                    if not _chunk:
                        break
                    _out.write(_chunk)
            _req.close()
            fsize = os.path.getsize(destination)
            return json.dumps({{"status": "ok", "path": destination, "url": dl_url, "size": fsize, "download_mode": dl_mode}})
        except Exception as e:
            if os.path.exists(destination):
                try:
                    os.remove(destination)
                except Exception:
                    pass
            return json.dumps({{"error": str(e), "url": dl_url, "hint": "Check URL accessibility or try manually"}})
```

IMPORTANT: The code above is already in Level 1 escaping. Verify all `{{` `}}` pairs before pasting.

---
PART 5: TUI DISPATCH — Mirror changes — **LEVEL 1 CODE**

### 5A: TUI asset_register (~line 28393)

Find `elif tool == 'asset_register':` (~line 28393).

Add the 3 new fields to the `_aentry` dict. After the `'preview_url'` line, add:

```python
                            'download_url': args.get('download_url', '').strip(),
                            'download_mode': args.get('download_mode', 'direct_file').strip().lower() or 'direct_file',
                            'download_ext': args.get('download_ext', '').strip(),
```

### 5B: TUI asset_download (~line 28429)

Find `elif tool == 'asset_download':` (~line 28429).

Replace the entire `else:` block (from the line after `if not _aeitem:` result assignment through the `except Exception as e:` block) with the hardened logic matching Part 4. Here is the replacement for the `else:` block:

```python
                    else:
                        try:
                            _ameta = _asset_entry_from_bag_item(_aeitem)
                            if not _ameta:
                                raise ValueError('empty asset metadata')
                            _adl_mode = _ameta.get('download_mode', 'direct_file')
                            if _adl_mode == 'catalog_only':
                                _asource = _ameta.get('source', 'unknown')
                                result = {{
                                    'error': f'This is a catalog source ({{_asource}}) — individual items must be fetched via its API.',
                                    'source': _asource,
                                    'source_url': _ameta.get('url', ''),
                                    'hint': f'Use asset_register to add specific items from {{_asource}} with their direct download URLs.'
                                }}
                            else:
                                _adl_url = _ameta.get('download_url', '') or _ameta.get('url', '')
                                if not _adl_url:
                                    result = {{'error': 'Asset has no download URL', 'asset': _akey, 'hint': 'Register a download_url with asset_register.'}}
                                elif not _ameta.get('download_url', '') and _adl_url == _ameta.get('url', '') and _adl_mode == 'archive':
                                    result = {{
                                        'error': 'No direct download URL available for this archive pack.',
                                        'source_url': _adl_url,
                                        'download_mode': _adl_mode,
                                        'hint': 'Download the pack manually from the source page. Then use asset_register with download_url set to the local path or a direct URL.'
                                    }}
                                else:
                                    _adl_ext = _ameta.get('download_ext', '')
                                    _aname = _ameta.get('name', 'asset').replace(' ', '_')
                                    if _adl_ext:
                                        _afn = f"{{_aname}}{{_adl_ext}}"
                                    else:
                                        _aurl_tail = _adl_url.split('/')[-1].split('?')[0]
                                        if '.' in _aurl_tail and len(_aurl_tail) < 100:
                                            _afn = _aurl_tail
                                        else:
                                            _afmt = _ameta.get('format', 'glb')
                                            _afn = f"{{_aname}}.{{_afmt}}"
                                    if not _adest:
                                        _acache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.asset_cache', _ameta.get('source', 'unknown'))
                                        os.makedirs(_acache_dir, exist_ok=True)
                                        _adest = os.path.join(_acache_dir, _afn)
                                    else:
                                        _aparent = os.path.dirname(_adest)
                                        if _aparent:
                                            os.makedirs(_aparent, exist_ok=True)
                                    # Support local file paths
                                    if os.path.isfile(_adl_url) or _adl_url.startswith('file://'):
                                        import shutil
                                        _alocal = _adl_url.replace('file:///', '').replace('file://', '') if _adl_url.startswith('file://') else _adl_url
                                        if not os.path.isfile(_alocal):
                                            result = {{'error': f'Local file not found: {{_alocal}}'}}
                                        else:
                                            shutil.copy2(_alocal, _adest)
                                            result = {{'status': 'ok', 'path': _adest, 'source_path': _alocal, 'size': os.path.getsize(_adest), 'download_mode': _adl_mode}}
                                    else:
                                        _areq = urllib.request.urlopen(_adl_url, timeout=30)
                                        _act = _areq.headers.get('Content-Type', '')
                                        if 'text/html' in _act:
                                            _areq.close()
                                            result = {{
                                                'error': 'URL returned Content-Type text/html — landing page, not a binary asset.',
                                                'url': _adl_url,
                                                'content_type': _act,
                                                'hint': 'Use asset_register to set a direct download_url.'
                                            }}
                                        else:
                                            with open(_adest, 'wb') as _aout:
                                                _ahead = _areq.read(512)
                                                if b'<html' in _ahead.lower() or b'<!doctype' in _ahead.lower():
                                                    _areq.close()
                                                    result = {{
                                                        'error': 'Downloaded content appears to be HTML despite Content-Type.',
                                                        'url': _adl_url,
                                                        'hint': 'The URL may be a landing page. Use asset_register to set a direct download_url.'
                                                    }}
                                                else:
                                                    _aout.write(_ahead)
                                                    while True:
                                                        _achunk = _areq.read(65536)
                                                        if not _achunk:
                                                            break
                                                        _aout.write(_achunk)
                                                    _areq.close()
                                                    _afsize = os.path.getsize(_adest)
                                                    result = {{'status': 'ok', 'path': _adest, 'url': _adl_url, 'size': _afsize, 'download_mode': _adl_mode}}
                        except Exception as e:
                            if _adest and os.path.exists(_adest):
                                try:
                                    os.remove(_adest)
                                except Exception:
                                    pass
                            result = {{'error': str(e), 'hint': 'Check URL accessibility or try manually'}}
```

---
PART 6: PROXY WRAPPER — Add new params — **LEVEL 1 CODE**

Find `def asset_register(` near `_bus_call` (~line 35745).

OLD:
```python
        def asset_register(name: str, source: str, license: str = "CC0", url: str = "", author: str = "", tags: str = "", format: str = "glb", style: str = "", poly_budget: str = "", preview_url: str = "", description: str = "") -> str:
            \"\"\"Register an asset or pack in the CC0 asset registry.\"\"\"
            return _bus_call('asset_register', {{'name': name, 'source': source, 'license': license, 'url': url, 'author': author, 'tags': tags, 'format': format, 'style': style, 'poly_budget': poly_budget, 'preview_url': preview_url, 'description': description}})
```

NEW:
```python
        def asset_register(name: str, source: str, license: str = "CC0", url: str = "", author: str = "", tags: str = "", format: str = "glb", style: str = "", poly_budget: str = "", preview_url: str = "", download_url: str = "", download_mode: str = "direct_file", download_ext: str = "", description: str = "") -> str:
            \"\"\"Register an asset or pack in the CC0 asset registry.\"\"\"
            return _bus_call('asset_register', {{'name': name, 'source': source, 'license': license, 'url': url, 'author': author, 'tags': tags, 'format': format, 'style': style, 'poly_budget': poly_budget, 'preview_url': preview_url, 'download_url': download_url, 'download_mode': download_mode, 'download_ext': download_ext, 'description': description}})
```

---
PART 7: HELP MIRRORS — Update descriptions — **LEVEL 0 CODE**

### 7A: _HELP_SKILLS_SEED — asset_register (~line 55804)

Find the `"asset_register"` entry in _HELP_SKILLS_SEED.

Add three new parameter entries after `"preview_url"`:

```python
            "download_url": {"type": "str", "required": False, "default": "", "description": "Direct download URL (if different from source page url)."},
            "download_mode": {"type": "str", "required": False, "default": "direct_file", "description": "Acquisition mode: direct_file, archive, or catalog_only."},
            "download_ext": {"type": "str", "required": False, "default": "", "description": "Expected file extension of download (e.g. .zip, .glb)."},
```

Update the `"url"` parameter description to clarify it's the source page:

OLD:
```python
            "url": {"type": "str", "required": False, "default": "", "description": "Download or source URL."},
```

NEW:
```python
            "url": {"type": "str", "required": False, "default": "", "description": "Human-readable source/landing page URL."},
```

Add a gotcha:

```python
        "gotchas": ["name and source are required. Key is derived as asset_pack:<source>:<name>.", "Set download_url for direct downloads — url is the human source page. Use download_mode to indicate acquisition type."]
```

### 7B: _HELP_SKILLS_SEED — asset_download (~line 55831)

Find the `"asset_download"` entry.

Update the `"purpose"` line:

OLD:
```python
        "purpose": "Download an asset file from its registered URL to local cache.",
```

NEW:
```python
        "purpose": "Download an asset file from its registered download_url to local cache. Rejects catalog_only sources, detects HTML landing pages, and derives filenames from download_ext.",
```

Update use_cases:

OLD:
```python
        "use_cases": [
            "Download a Kenney pack ZIP or page target for local inspection.",
            "Cache an HDRI from Poly Haven for environment lighting.",
            "Download a specific GLB or texture target for later scene use."
        ],
```

NEW:
```python
        "use_cases": [
            "Download a directly-linked asset file to local cache.",
            "Attempt download and get a helpful error if the source is catalog_only.",
            "Download a specific GLB or texture target for later scene use."
        ],
```

Update gotchas:

OLD:
```python
        "gotchas": ["Uses urllib - some URLs may require auth or redirect handling. The tool stores to .asset_cache/ by default."]
```

NEW:
```python
        "gotchas": ["Uses urllib - some URLs may require auth or redirect handling. The tool stores to .asset_cache/ by default.", "Rejects catalog_only sources — use the source API to find individual item URLs, then asset_register them.", "Detects HTML responses and removes the file if the download appears to be a landing page, not a binary asset."]
```

### 7C: _HELP_CATEGORY_STUBS — asset_library (~line 57436)

Find the `"asset_library"` entry in _HELP_CATEGORY_STUBS.

Update the `"architecture"` string to mention the new schema:

OLD:
```python
        "architecture": "Asset metadata lives in FelixBag under asset_pack:<source>:<name> keys. Semantic search uses FelixBag embeddings when available, while structured filters and catalog stats operate over stored asset metadata. Seed catalog bootstraps 13 CC0 entries from Kenney, Quaternius, Poly Haven, and ambientCG.",
```

NEW:
```python
        "architecture": "Asset metadata lives in FelixBag under asset_pack:<source>:<name> keys with download_url/download_mode/download_ext fields distinguishing direct downloads from archive packs and API-only catalogs. Semantic search uses FelixBag embeddings when available. Seed catalog bootstraps 13 CC0 entries from Kenney, Quaternius, Poly Haven, and ambientCG. Bootstrap migration upgrades stale entries missing download_mode.",
```

---
PART 8: ADDITIONAL MIRRORS — **LEVEL 1 CODE** (8A, 8B) and **LEVEL 0 implied** (8C is inside Level 1 f-string)

These are existing description strings that must reflect the new download semantics. They are part of the same propagation surface family, not new surfaces.

### 8A: README / tool-list generation (~line 2468) — **LEVEL 1 CODE**

Find:
```python
        lines.append("    asset_download   → Download asset file to local cache")
```

Replace with:
```python
        lines.append("    asset_download   → Download asset via download_url (rejects catalog_only, sniffs HTML)")
```

Also update asset_register description:

Find:
```python
        lines.append("    asset_register   → Register an asset or pack (CC0 sources)")
```

Replace with:
```python
        lines.append("    asset_register   → Register asset with download_url/download_mode/download_ext")
```

### 8B: get_help skill topics (~line 44025) — **LEVEL 1 CODE**

Find:
```python
                "asset_library": {{
                    "asset_search": "Search CC0 asset registry by query and filters",
                    "asset_register": "Register an asset or pack",
                    "asset_download": "Download asset file to local cache",
                    "asset_list": "List registered assets with filters",
                    "asset_catalog": "Overview stats of the asset registry"
                }},
```

Replace with:
```python
                "asset_library": {{
                    "asset_search": "Search CC0 asset registry by query and filters",
                    "asset_register": "Register asset with download_url, download_mode, download_ext",
                    "asset_download": "Download via download_url (rejects catalog_only, detects HTML pages)",
                    "asset_list": "List registered assets with filters",
                    "asset_catalog": "Overview stats of the asset registry"
                }},
```

### 8C: get_help common patterns (~line 44109) — **LEVEL 1 CODE**

Find:
```python
                "asset_search() → asset_download() → env_spawn() - Find CC0 asset and place in scene",
                "asset_catalog() → asset_list(source='kenney') → asset_search(tags='nature') - Browse CC0 library",
```

Replace with:
```python
                "asset_search() → asset_download() → env_spawn() - Find CC0 asset and place in scene (requires download_url set)",
                "asset_catalog() → asset_list(source='kenney') → asset_register(download_url='local/path.glb') → asset_download() - Browse, register local file, download",
```

---
TESTING

After all edits, perform BOTH compile-time and grep verification:

### Step 1: Compile the generator
```bash
cd F:\End-Game\ouroboros-key
python -m py_compile agent_compiler.py
```
Must exit 0 with no output. This verifies the generator itself is valid Python.

### Step 2: Regenerate and compile the emitted capsule
Run the generator — it compiles a capsule and prints `Generated: <path>`:
```bash
python agent_compiler.py
```
Capture the path printed after `Generated:`, then compile *that* file:
```bash
python -m py_compile <generated_path>
```
Both must exit 0. Step 1 validates the generator; this step validates the emitted runtime. If the generator passes but the emitted capsule fails, a brace mismatch collapsed during emission.

### Step 3: Grep verification
All of these must pass:

1. **Seed catalog fields**: `rg "download_mode" agent_compiler.py | grep "_CC0_ASSET_CATALOG" -A20 | grep -c "download_mode"` — should be 13.

2. **Migration gate — all 3 fields**: `rg "download_mode.*not in.*_eparsed|download_url.*not in.*_eparsed|download_ext.*not in.*_eparsed" agent_compiler.py` — should find the triple-field check in _ensure_asset_catalog.

3. **Download hardening — catalog_only rejection**: `rg "catalog_only" agent_compiler.py` — should appear in BOTH monolith asset_download AND TUI asset_download blocks.

4. **Download hardening — Content-Type check**: `rg "text/html" agent_compiler.py` — should appear in BOTH monolith and TUI asset_download.

5. **Download hardening — head sniff**: `rg "<html|<!doctype" agent_compiler.py` — should appear in BOTH monolith and TUI asset_download (unconditional, not gated by file size).

6. **Local path support**: `rg "os.path.isfile.*dl_url|file://" agent_compiler.py` — should appear in BOTH monolith and TUI asset_download.

7. **Proxy params**: `rg "download_url.*download_mode.*download_ext" agent_compiler.py` — should match the proxy _bus_call dict.

8. **Mirror consistency**: `rg "asset_download.*Download" agent_compiler.py` — overview lines at ~2471 and skill topic at ~44028 should both mention download_url semantics.

9. **Brace parity**: For any Level 1 block you edited, count `{{` vs `}}` — they must be equal. A single unmatched brace breaks the entire quine. Quick check: `python -c "s=open('agent_compiler.py').read(); print('{{ count:', s.count('{{'), '}} count:', s.count('}}'))"` — counts should match.

---
CONSTRAINTS

- Do NOT add new tools. This is a schema correction, not a feature addition.
- Do NOT change tool names or FelixBag key patterns.
- Do NOT modify asset_search, asset_list, or asset_catalog — they already work correctly with the new fields (they just pass through whatever metadata is in the bag entry).
- Do NOT touch any code outside the 10 touch points listed in Parts 1–8 above.
- Level 1 code MUST use doubled braces `{{}}` for all dict literals and f-string expressions. Level 0 code uses normal braces `{}`.
- The `_bag_item_text` helper (used in Part 2 migration) already exists at ~line 39007. Do NOT redefine it.
- The `_asset_entry_from_bag_item` helper already exists at ~line 42328. Do NOT redefine it.
