/**
 * VS Code API Shim for standalone browser usage.
 * 
 * Replaces acquireVsCodeApi() with an HTTP bridge to the FastAPI server,
 * which proxies tool calls to the capsule's MCP server.
 * 
 * The webview's main.js calls:
 *   vscode.postMessage({ command: 'callTool', tool: 'get_status', args: {} })
 * 
 * This shim intercepts that and makes:
 *   POST /api/tool/get_status  { }
 * 
 * Then fires the response back via window message event.
 * 
 * All 72 command types from main.js are handled here:
 *   - Tool proxy commands (callTool, fetchToolSchemas, refresh, etc.)
 *   - Nostr commands → routed to capsule MCP tools
 *   - GitHub commands → graceful no-op (requires VS Code auth)
 *   - Web3 commands → routed to capsule MCP tools
 *   - Audio/mic commands → not available in browser (no HTTPS / no device access)
 *   - VS Code-specific commands → graceful no-op
 *   - Dreamer config → local storage fallback
 *   - UX settings → local storage
 */

(function() {
    // Prevent double-init
    if (window.__vsCodeShimInstalled) return;
    window.__vsCodeShimInstalled = true;

    const API_BASE = window.location.origin;
    let _state = {};

    // --- Local storage helpers for settings ---
    function loadLocal(key, fallback) {
        try { return JSON.parse(localStorage.getItem('cc_' + key)) || fallback; }
        catch { return fallback; }
    }
    function saveLocal(key, val) {
        try { localStorage.setItem('cc_' + key, JSON.stringify(val)); } catch {}
    }

    // Shim: acquireVsCodeApi
    window.acquireVsCodeApi = function() {
        return {
            postMessage: function(msg) { handleMessage(msg); },
            getState: function() { return _state; },
            setState: function(s) { _state = s; return s; }
        };
    };

    // --- MCP tool call helper (silent — no activity tracking) ---
    async function mcpToolCall(toolName, args) {
        const resp = await fetch(`${API_BASE}/api/tool/${toolName}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(args || {})
        });

        const contentType = String(resp.headers.get('content-type') || '').toLowerCase();
        const raw = await resp.text();
        let data = null;

        if (raw) {
            try { data = JSON.parse(raw); }
            catch {
                if (contentType.includes('application/json')) {
                    throw new Error(`Invalid JSON from server (HTTP ${resp.status}).`);
                }
                data = {
                    error: `HTTP ${resp.status} returned non-JSON response`,
                    status: resp.status,
                    content_type: contentType || '(unknown)',
                    body_preview: raw.slice(0, 500)
                };
            }
        } else {
            data = {};
        }

        // Extract result from JSON-RPC envelope
        if (data && data.result && data.result.content) {
            try {
                const text = data.result.content[0]?.text;
                return text ? JSON.parse(text) : data.result;
            } catch { return data.result; }
        }

        if (!resp.ok && (!data || typeof data !== 'object' || !data.error)) {
            return { error: `HTTP ${resp.status} ${resp.statusText || ''}`.trim(), status: resp.status };
        }

        return data;
    }

    // Activity is tracked ONLY via the SSE stream from the server.
    // The server's proxy_tool_call endpoint broadcasts every call
    // (both from the web UI and from external MCP clients like Kiro).
    // This avoids double-counting.

    // --- Web-mode unavailable message helper ---
    function webModeUnavailable(feature) {
        return { error: `${feature} is not available in web mode. Use the VS Code extension for this feature.` };
    }

    // ═══════════════════════════════════════════════════════════
    // COMMAND ROUTER — handles all 72 command types from main.js
    // ═══════════════════════════════════════════════════════════

    async function handleMessage(msg) {
        const command = msg.command;

        // ── Core tool proxy ──────────────────────────────────
        if (command === 'callTool') {
            try {
                const result = await mcpToolCall(msg.tool, msg.args);
                fireEvent({ type: 'toolResult', id: msg.id, data: result });
            } catch (err) {
                fireEvent({ type: 'toolResult', id: msg.id, error: err.message });
            }
        }
        else if (command === 'fetchToolSchemas') {
            try {
                const tools = await syncToolInventory(true);
                if (Array.isArray(tools) && tools.length > 0) {
                    fireEvent({ type: 'toolSchemas', tools: tools });
                } else {
                    const resp = await fetch(`${API_BASE}/api/tools`);
                    const data = await resp.json();
                    const freshTools = data.result?.tools || data.tools || [];
                    if (freshTools.length > 0) {
                        fireEvent({ type: 'toolSchemas', tools: freshTools });
                    }
                }
            } catch (err) {
                fireEvent({ type: 'toolSchemas', tools: [], error: err.message });
            }
        }
        else if (command === 'refresh' || command === 'ready') {
            // Trigger a full health poll which dispatches a proper flat state message
            pollHealthAndDispatchState();
        }
        else if (command === 'refreshMemoryCatalog') {
            try {
                const result = await mcpToolCall('bag_catalog', {});
                fireEvent({ type: 'memoryCatalog', data: result });
            } catch (err) {
                fireEvent({ type: 'memoryCatalog', error: err.message });
            }
        }
        else if (command === 'exportMemory') {
            try {
                const result = await mcpToolCall('bag_export', msg.args || {});
                // In web mode, offer the export as a downloadable JSON blob
                const exportData = JSON.stringify(result, null, 2);
                const blob = new Blob([exportData], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'felixbag_export_' + new Date().toISOString().slice(0,10) + '.json';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                fireEvent({ type: 'memoryExported', fileType: 'JSON', path: a.download });
            } catch (err) {
                fireEvent({ type: 'memoryExportError', error: err.message });
            }
        }

        // ── Diagnostics → route to actual MCP tools ──────
        else if (command === 'runDiagnostic') {
            const diagKey = msg.diagKey || '';
            // Map diagnostic keys to MCP tool calls
            const DIAG_TOOL_MAP = {
                'verify_integrity': ['verify_integrity', {}],
                'verify_hash': ['verify_hash', {}],
                'get_provenance': ['get_provenance', {}],
                'tree': ['tree', {}],
                'show_weights': ['show_weights', {}],
                'show_dims': ['show_dims', {}],
                'show_rssm': ['show_rssm', {}],
                'show_lora': ['show_lora', {}],
                'export_pt': ['export_pt', {}],
                'export_onnx': ['export_onnx', {}],
                'export_docs': ['export_docs', {}],
                'save_state': ['save_state', {}],
                'demo': ['demo', {}],
                'heartbeat': ['heartbeat', {}],
                'get_about': ['get_about', {}],
                'cascade_graph_stats': ['cascade_graph', {operation: 'stats'}],
                'cascade_genesis': ['get_genesis', {}],
                'cascade_identity': ['get_identity', {}],
                'cascade_session_stats': ['cascade_record', {operation: 'session_stats'}],
                'cascade_proxy_status': ['cascade_proxy', {operation: 'status'}],
            };
            const mapping = DIAG_TOOL_MAP[diagKey];
            if (mapping) {
                try {
                    const result = await mcpToolCall(mapping[0], mapping[1]);
                    // Wrap in the format handleDiagResult expects
                    fireEvent({
                        type: 'diagResult', id: msg.id, diagKey: diagKey,
                        data: { resolved: result, key: diagKey, label: diagKey, healthy: !result.error }
                    });
                } catch (err) {
                    fireEvent({
                        type: 'diagResult', id: msg.id, diagKey: diagKey,
                        error: err.message
                    });
                }
            } else {
                fireEvent({
                    type: 'diagResult', id: msg.id, diagKey: diagKey,
                    error: 'Unknown diagnostic: ' + diagKey
                });
            }
        }

        // ── Nostr commands → route through capsule MCP tools ─
        else if (command.startsWith('nostr')) {
            await handleNostrCommand(msg);
        }

        // ── GitHub commands → not available in web mode ──────
        else if (command.startsWith('github') || command === 'requestGistContent' ||
                 command === 'requestGistSearch' || command === 'triggerGistIndexing') {
            await handleGithubCommand(msg);
        }

        // ── Web3 commands → route through capsule MCP tools ──
        else if (command.startsWith('web3')) {
            await handleWeb3Command(msg);
        }

        // ── Audio/Mic commands → not available in web mode ───
        else if (command === 'startMicCapture' || command === 'stopMicCapture' ||
                 command === 'listAudioDevices' || command === 'setMicSensitivity' ||
                 command === 'setMicNoiseGate' || command === 'voiceP2PReady') {
            fireEvent({
                type: 'micStatus', id: msg.id,
                ...webModeUnavailable('Microphone capture (requires HTTPS + device permissions)')
            });
        }

        // ── Bag/Git commands → VS Code specific ──────────────
        else if (command === 'bagGitDiff' || command === 'bagGitInspect' ||
                 command === 'bagGitOpenNativeDiff' || command === 'checkGitAvailable' ||
                 command === 'commitBagVersion' || command === 'openBagDocFile') {
            await handleBagGitCommand(msg);
        }

        // ── Dreamer config (persisted in FelixBag) ─────────
        else if (command === 'loadDreamerConfigFile') {
            const _defaultDreamerCfg = {
                rewards: {
                    hold_accept: 1.0, hold_override: -0.5, bag_induct: 0.8,
                    bag_forget: -0.3, workflow_save: 1.0, workflow_success: 0.5,
                    workflow_failure: -0.5, tool_success: 0.1, tool_error: -0.2,
                    mutation_kept: 0.3, mutation_reverted: -0.1, normalize: true
                },
                training: {
                    enabled: true, auto_train: true, world_model_frequency: 32,
                    critic_frequency: 32, full_cycle_frequency: 64, batch_size: 32,
                    noise_scale: 0.005, gamma: 0.99, lambda: 0.95,
                    critic_target_tau: 0.02, timeout_budget_seconds: 30
                },
                imagination: { horizon: 15, n_actions: 8, auto_imagine_on_train: true },
                buffers: {
                    reward_buffer_max: 5000, obs_buffer_max: 1000,
                    value_history_max: 200, reward_rate_window: 100
                },
                architecture: {
                    critic_hidden_dim: 256, reward_head_hidden_dim: 128,
                    continue_head_hidden_dim: 64, latent_dim: 5120
                }
            };
            try {
                const result = await mcpToolCall('bag_get', { key: 'dreamer_config' });
                let cfg = null;
                if (result && result.value) {
                    try { cfg = typeof result.value === 'string' ? JSON.parse(result.value) : result.value; }
                    catch { cfg = result.value; }
                }
                fireEvent({ type: 'dreamerConfigLoaded', config: cfg || _defaultDreamerCfg });
            } catch {
                fireEvent({ type: 'dreamerConfigLoaded', config: _defaultDreamerCfg });
            }
        }
        else if (command === 'saveDreamerConfig') {
            try {
                const cfg = msg.config || msg.data;
                await mcpToolCall('bag_put', {
                    key: 'dreamer_config',
                    value: typeof cfg === 'string' ? cfg : JSON.stringify(cfg)
                });
                fireEvent({ type: 'dreamerConfigSaved', success: true });
            } catch (err) {
                fireEvent({ type: 'dreamerConfigSaved', success: false, error: err.message });
            }
        }
        else if (command === 'resetDreamerConfig') {
            try {
                await mcpToolCall('bag_forget', { key: 'dreamer_config' });
            } catch {}
            fireEvent({ type: 'dreamerConfigLoaded', config: null });
        }

        // ── UX Settings ──────────────────────────────────────
        else if (command === 'uxGetSettings') {
            const settings = loadLocal('uxSettings', {});
            fireEvent({ type: 'uxSettings', data: settings });
        }
        else if (command === 'uxSetSettings') {
            const current = loadLocal('uxSettings', {});
            const merged = { ...current, ...(msg.settings || msg.data || {}) };
            saveLocal('uxSettings', merged);
            fireEvent({ type: 'uxSettings', data: merged });
        }
        else if (command === 'uxResetSettings') {
            localStorage.removeItem('cc_uxSettings');
            fireEvent({ type: 'uxSettings', data: {} });
        }

        // ── VS Code-specific no-ops ─────────────────────────
        else if (command === 'openSettings' ||
                 command === 'openExternal') {
            if (command === 'openExternal' && msg.url) {
                window.open(msg.url, '_blank');
            } else {
                console.log('[shim] VS Code-specific command ignored:', command);
            }
        }
        else if (command === 'requestSlotMetrics') {
            try {
                var evalResult = await mcpToolCall('slot_info', { slot: msg.slotIndex });
                fireEvent({ type: 'slotEvalMetrics', slotIndex: msg.slotIndex, metrics: evalResult });
            } catch (e) {
                fireEvent({ type: 'slotEvalMetrics', slotIndex: msg.slotIndex, metrics: null });
            }
        }

        // ── IPFS ─────────────────────────────────────────────
        else if (command === 'ipfsPin') {
            fireEvent({
                type: 'ipfsResult', id: msg.id,
                ...webModeUnavailable('IPFS pinning')
            });
        }

        // ── Fallback: try as MCP tool call ───────────────────
        else {
            console.log('[shim] Unhandled command, attempting as tool call:', command);
            try {
                const result = await mcpToolCall(command, msg.args || msg.data || {});
                fireEvent({ type: 'toolResult', id: msg.id, data: result });
            } catch (err) {
                console.warn('[shim] Fallback tool call failed:', command, err.message);
            }
        }
    }

    // ═══════════════════════════════════════════════════════════
    // NOSTR COMMAND HANDLER
    // Maps webview nostr commands to capsule MCP tool equivalents
    // ═══════════════════════════════════════════════════════════

    async function handleNostrCommand(msg) {
        const command = msg.command;

        // Map nostr commands to capsule MCP tools where possible.
        // For commands without a direct capsule equivalent, return
        // graceful defaults so the Community tab renders cleanly
        // rather than showing error messages everywhere.

        // Commands that route through capsule MCP tools
        const toolMappings = {
            'nostrPublishChat': 'observe',
            'nostrFetchChat': 'feed',
            'nostrPublishDocument': 'observe',
            'nostrPublishIdentity': 'get_identity',
            'nostrGetIdentity': 'get_identity',
        };

        // Commands that return empty/default data for clean UI
        const defaultResponses = {
            'nostrFetchDMs': { type: 'nostrDMs', dms: [] },
            'nostrGetBlockList': { type: 'nostrBlockList', blocked: [] },
            'nostrGetPrivacy': { type: 'nostrPrivacy', settings: { chatEnabled: true, dmsEnabled: true, marketplaceEnabled: true, autoRedact: true, presenceEnabled: false, voiceEnabled: false } },
            'nostrGetOnlineUsers': { type: 'nostrOnlineUsers', users: [], count: 0 },
            'nostrFetchVoiceRooms': { type: 'nostrVoiceRooms', rooms: [] },
            'nostrGetVoiceRooms': { type: 'nostrVoiceRooms', rooms: [] },
        };

        // Commands that are write operations — acknowledge silently
        const writeOps = [
            'nostrSendDM', 'nostrBlockUser', 'nostrUnblockUser',
            'nostrSetPrivacy', 'nostrSetProfile', 'nostrDeleteEvent',
            'nostrReact', 'nostrZap', 'nostrResolveLud16',
            'nostrAwardBadge', 'nostrCreateBadge', 'nostrCreatePoll',
            'nostrVotePoll', 'nostrRedactPreview', 'nostrSendLiveChat',
            'nostrSubmitDvmJob', 'nostrCreateVoiceRoom', 'nostrJoinRoom',
            'nostrLeaveRoom', 'nostrRaiseHand', 'nostrSendVoiceNote',
        ];

        if (command === 'nostrGetIdentity') {
            // Identity needs special event type — main.js listens for 'nostrIdentity'
            try {
                const result = await mcpToolCall('get_identity', msg.args || {});
                const pubkey = result?.identity?.cascade_id || result?.cascade_id || '';
                fireEvent({
                    type: 'nostrIdentity', id: msg.id,
                    pubkey: pubkey,
                    npub: pubkey ? pubkey.substring(0, 16) + '...' : 'Web mode (capsule identity)',
                    connected: true,
                    relayCount: 0,
                    relays: [],
                    note: 'Using capsule identity — no Nostr relay connected'
                });
            } catch (err) {
                fireEvent({ type: 'nostrIdentity', id: msg.id, pubkey: '', npub: 'Web mode', connected: false, relayCount: 0, relays: [] });
            }
        }
        else if (toolMappings[command]) {
            try {
                const result = await mcpToolCall(toolMappings[command], msg.args || msg.data || {});
                fireEvent({ type: 'nostrResult', command, id: msg.id, data: result });
            } catch (err) {
                fireEvent({ type: 'nostrResult', command, id: msg.id, error: err.message });
            }
        }
        else if (command === 'nostrFetchWorkflows') {
            try {
                const result = await mcpToolCall('workflow_list', {});
                fireEvent({ type: 'nostrWorkflows', id: msg.id, data: result });
            } catch (err) {
                fireEvent({ type: 'nostrWorkflows', id: msg.id, error: err.message });
            }
        }
        else if (defaultResponses[command]) {
            // Return clean defaults so UI renders empty state instead of errors
            fireEvent({ ...defaultResponses[command], command, id: msg.id });
        }
        else if (writeOps.includes(command)) {
            // Write operations return a quiet acknowledgement
            // The UI won't show an error, just won't persist to relays
            console.log('[shim] Nostr write op (no relay):', command);
            fireEvent({ type: 'nostrResult', command, id: msg.id, data: { status: 'ok', note: 'No relay connected — operation logged locally only' } });
        }
        else {
            // Unknown nostr command — silent no-op
            console.log('[shim] Unknown nostr command:', command);
            fireEvent({ type: 'nostrResult', command, id: msg.id, data: {} });
        }
    }

    // ═══════════════════════════════════════════════════════════
    // GITHUB COMMAND HANDLER
    // ═══════════════════════════════════════════════════════════

    async function handleGithubCommand(msg) {
        const command = msg.command;

        // GitHub auth requires VS Code's built-in auth provider
        // These all gracefully no-op in web mode
        const authCommands = ['githubAuth', 'githubGetAuth', 'githubSignOut'];

        if (authCommands.includes(command)) {
            fireEvent({
                type: 'githubAuth', id: msg.id,
                authenticated: false,
                ...webModeUnavailable('GitHub authentication (requires VS Code auth provider)')
            });
        }
        else if (command === 'githubCreateGist' || command === 'githubForkGist') {
            fireEvent({
                type: 'githubResult', command, id: msg.id,
                ...webModeUnavailable('GitHub Gist operations')
            });
        }
        else if (command === 'githubGetHistory') {
            fireEvent({ type: 'githubHistory', id: msg.id, history: [] });
        }
        else if (command === 'githubImportFromUrl') {
            fireEvent({
                type: 'githubResult', command, id: msg.id,
                ...webModeUnavailable('GitHub import')
            });
        }
        else if (command === 'requestGistContent') {
            fireEvent({ type: 'gistContent', id: msg.id, content: null,
                ...webModeUnavailable('Gist content') });
        }
        else if (command === 'requestGistSearch') {
            fireEvent({ type: 'gistSearch', id: msg.id, results: [] });
        }
        else if (command === 'triggerGistIndexing') {
            // no-op
        }
        else {
            fireEvent({
                type: 'githubResult', command, id: msg.id,
                ...webModeUnavailable('This GitHub feature')
            });
        }
    }

    // ═══════════════════════════════════════════════════════════
    // WEB3 COMMAND HANDLER
    // ═══════════════════════════════════════════════════════════

    async function handleWeb3Command(msg) {
        const command = msg.command;

        if (command === 'web3GetCategories') {
            // Return the categories from __CATEGORIES__ if available
            fireEvent({
                type: 'web3Categories', id: msg.id,
                data: window.__CATEGORIES__ || {}
            });
        }
        else if (command === 'web3GetDID') {
            try {
                const result = await mcpToolCall('get_identity', {});
                fireEvent({ type: 'web3DID', id: msg.id, data: result });
            } catch (err) {
                fireEvent({ type: 'web3DID', id: msg.id, error: err.message });
            }
        }
        else if (command === 'web3GetDocTypes') {
            fireEvent({ type: 'web3DocTypes', id: msg.id, data: [] });
        }
        else {
            fireEvent({
                type: 'web3Result', command, id: msg.id,
                ...webModeUnavailable('This Web3 feature')
            });
        }
    }

    // ═══════════════════════════════════════════════════════════
    // BAG/GIT COMMAND HANDLER
    // ═══════════════════════════════════════════════════════════

    async function _resolveMaybeCachedPayload(payload, maxDepth) {
        let out = payload;
        let depth = 0;
        const limit = Number.isFinite(maxDepth) ? maxDepth : 4;
        while (out && typeof out === 'object' && out._cached && depth < limit) {
            out = await mcpToolCall('get_cached', { cache_id: out._cached });
            depth += 1;
        }
        if (typeof out === 'string') {
            try { out = JSON.parse(out); } catch {}
        }
        return out;
    }

    function _shortSnapshotId(value) {
        const s = String(value || '').trim();
        if (!s) return '';
        return s.length > 12 ? s.slice(0, 12) : s;
    }

    function _fmtSnapshotWhen(ts) {
        const n = Number(ts || 0);
        if (!Number.isFinite(n) || n <= 0) return '';
        try { return new Date(n).toLocaleString(); } catch { return ''; }
    }

    function _snapshotKeyFromEntry(entry) {
        if (!entry || typeof entry !== 'object') return '';
        return String(entry.checkpoint_key_display || entry.checkpoint_key || '').trim();
    }

    async function _loadCheckpointMetaForKey(key, includeDiffStat) {
        const versionsRaw = await _resolveMaybeCachedPayload(await mcpToolCall('bag_versions', { key: key, limit: 25 }));
        if (!versionsRaw || typeof versionsRaw !== 'object') {
            return { error: 'Invalid bag_versions response' };
        }
        if (versionsRaw.error) {
            return { error: String(versionsRaw.error) };
        }

        const checkpoints = Array.isArray(versionsRaw.checkpoints) ? versionsRaw.checkpoints : [];
        const head = checkpoints.length > 0 ? checkpoints[0] : null;
        const prev = checkpoints.length > 1 ? checkpoints[1] : null;
        let diffStat = '';

        if (includeDiffStat && head && prev) {
            const fromKey = _snapshotKeyFromEntry(prev);
            const toKey = _snapshotKeyFromEntry(head);
            if (fromKey && toKey) {
                const diffRaw = await _resolveMaybeCachedPayload(await mcpToolCall('bag_diff', {
                    key: key,
                    from_checkpoint: fromKey,
                    to_checkpoint: toKey
                }));
                if (diffRaw && typeof diffRaw === 'object' && !diffRaw.error) {
                    const added = Number(diffRaw.added_lines || 0);
                    const removed = Number(diffRaw.removed_lines || 0);
                    diffStat = '+' + added + ' / -' + removed + ' lines';
                }
            }
        }

        return {
            key: key,
            tracked: checkpoints.length > 0,
            commitCount: checkpoints.length,
            headSha: head ? _shortSnapshotId(head.checkpoint_id || head.checkpoint_key) : '',
            latestWhen: head ? _fmtSnapshotWhen(head.timestamp_ms || head.timestamp) : '',
            latestSubject: head ? String(head.message || head.tag || 'checkpoint') : '',
            diffStat: diffStat,
            filePath: 'FelixBag:' + key,
            checkpoints: checkpoints
        };
    }

    async function handleBagGitCommand(msg) {
        const command = msg.command;
        const key = String((msg && msg.key) || '').trim();

        if (command === 'checkGitAvailable') {
            const status = {
                available: true,
                backend: 'felixbag-checkpoints',
                note: 'Using FelixBag checkpoint versioning in web mode.'
            };
            fireEvent({ type: 'gitAvailability', ...status });
            // Backwards compatibility for any legacy listener.
            fireEvent({ type: 'gitAvailable', ...status });
        }
        else if (command === 'bagGitInspect') {
            if (!key) {
                fireEvent({ type: 'bagGitInfo', key: '', error: 'Missing FelixBag key' });
                return;
            }
            try {
                const meta = await _loadCheckpointMetaForKey(key, true);
                if (meta.error) {
                    fireEvent({ type: 'bagGitInfo', key: key, error: meta.error, filePath: 'FelixBag:' + key });
                    return;
                }
                fireEvent({
                    type: 'bagGitInfo',
                    key: key,
                    tracked: !!meta.tracked,
                    commitCount: Number(meta.commitCount || 0),
                    headSha: meta.headSha || '',
                    latestWhen: meta.latestWhen || '',
                    latestSubject: meta.latestSubject || '',
                    diffStat: meta.diffStat || '',
                    filePath: meta.filePath || ('FelixBag:' + key)
                });
            } catch (err) {
                fireEvent({ type: 'bagGitInfo', key: key, error: String(err && err.message ? err.message : err) });
            }
        }
        else if (command === 'bagGitDiff') {
            if (!key) {
                fireEvent({ type: 'bagGitDiffResult', key: '', error: 'Missing FelixBag key' });
                return;
            }
            try {
                const meta = await _loadCheckpointMetaForKey(key, false);
                if (meta.error) {
                    fireEvent({ type: 'bagGitDiffResult', key: key, error: meta.error });
                    return;
                }
                const checkpoints = Array.isArray(meta.checkpoints) ? meta.checkpoints : [];
                if (checkpoints.length < 2) {
                    fireEvent({ type: 'bagGitDiffResult', key: key, error: 'Need at least two checkpoints to diff.' });
                    return;
                }
                const toEntry = checkpoints[0];
                const fromEntry = checkpoints[1];
                const fromKey = _snapshotKeyFromEntry(fromEntry);
                const toKey = _snapshotKeyFromEntry(toEntry);
                const diffRaw = await _resolveMaybeCachedPayload(await mcpToolCall('bag_diff', {
                    key: key,
                    from_checkpoint: fromKey,
                    to_checkpoint: toKey
                }));
                if (!diffRaw || typeof diffRaw !== 'object') {
                    fireEvent({ type: 'bagGitDiffResult', key: key, error: 'Invalid bag_diff response' });
                    return;
                }
                if (diffRaw.error) {
                    fireEvent({ type: 'bagGitDiffResult', key: key, error: String(diffRaw.error) });
                    return;
                }
                fireEvent({
                    type: 'bagGitDiffResult',
                    key: key,
                    diff: String(diffRaw.diff || ''),
                    fromSha: _shortSnapshotId(fromEntry.checkpoint_id || fromEntry.checkpoint_key),
                    toSha: _shortSnapshotId(toEntry.checkpoint_id || toEntry.checkpoint_key),
                    fromCheckpoint: fromKey,
                    toCheckpoint: toKey,
                    addedLines: Number(diffRaw.added_lines || 0),
                    removedLines: Number(diffRaw.removed_lines || 0)
                });
            } catch (err) {
                fireEvent({ type: 'bagGitDiffResult', key: key, error: String(err && err.message ? err.message : err) });
            }
        }
        else if (command === 'commitBagVersion') {
            if (!key) {
                fireEvent({ type: 'bagCommitResult', key: '', error: 'Missing FelixBag key' });
                return;
            }
            try {
                const tsIso = new Date().toISOString();
                const checkpointRaw = await _resolveMaybeCachedPayload(await mcpToolCall('bag_checkpoint', {
                    key: key,
                    message: 'Memory commit from web UI at ' + tsIso,
                    tag: 'ui'
                }));
                if (!checkpointRaw || typeof checkpointRaw !== 'object') {
                    fireEvent({ type: 'bagCommitResult', key: key, error: 'Invalid bag_checkpoint response' });
                    return;
                }
                if (checkpointRaw.error || checkpointRaw.status === 'error') {
                    fireEvent({ type: 'bagCommitResult', key: key, error: String(checkpointRaw.error || 'Checkpoint failed') });
                    return;
                }

                const meta = await _loadCheckpointMetaForKey(key, true);
                const checkpointSha = _shortSnapshotId(checkpointRaw.checkpoint_id || checkpointRaw.checkpoint_key);
                fireEvent({
                    type: 'bagCommitResult',
                    key: key,
                    sha: checkpointSha || (meta.headSha || ''),
                    commitCount: Number(meta.commitCount || 0),
                    latestWhen: meta.latestWhen || '',
                    latestSubject: meta.latestSubject || 'checkpoint',
                    diffStat: meta.diffStat || '',
                    filePath: meta.filePath || ('FelixBag:' + key),
                    noChanges: false
                });
            } catch (err) {
                fireEvent({ type: 'bagCommitResult', key: key, error: String(err && err.message ? err.message : err) });
            }
        }
        else if (command === 'openBagDocFile') {
            if (!key) {
                fireEvent({ type: 'bagDocOpened', key: '', error: 'Missing FelixBag key' });
                return;
            }
            try {
                const got = await _resolveMaybeCachedPayload(await mcpToolCall('bag_get', { key: key }));
                if (!got || typeof got !== 'object') {
                    fireEvent({ type: 'bagDocOpened', key: key, error: 'Invalid bag_get response' });
                    return;
                }
                if (got.error) {
                    fireEvent({ type: 'bagDocOpened', key: key, error: String(got.error) });
                    return;
                }
                let val = (typeof got.value !== 'undefined') ? got.value : got.content;
                if (typeof val === 'undefined') val = got;
                const isString = typeof val === 'string';
                const text = isString ? val : JSON.stringify(val, null, 2);
                const safeBase = key.replace(/[\\/:*?"<>|]+/g, '_').slice(0, 120) || 'felixbag_item';
                const ext = isString ? '.txt' : '.json';
                const fileName = safeBase + ext;
                const blob = new Blob([text], { type: isString ? 'text/plain' : 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = fileName;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                setTimeout(function() { URL.revokeObjectURL(url); }, 1000);
                fireEvent({ type: 'bagDocOpened', key: key, filePath: 'Download:' + fileName });
            } catch (err) {
                fireEvent({ type: 'bagDocOpened', key: key, error: String(err && err.message ? err.message : err) });
            }
        }
        else if (command === 'bagGitOpenNativeDiff') {
            fireEvent({
                type: 'bagDocOpened',
                key: key,
                error: 'Native diff editor is not available in web mode. Use "View Last Diff".'
            });
        }
        else {
            console.log('[shim] VS Code git command ignored:', command);
        }
    }

    // ═══════════════════════════════════════════════════════════
    // EVENT DISPATCH
    // ═══════════════════════════════════════════════════════════

    function fireEvent(data) {
        window.dispatchEvent(new MessageEvent('message', { data }));
    }

    // Provide empty categories if not set
    if (!window.__CATEGORIES__) {
        window.__CATEGORIES__ = {};
    }

    // ═══════════════════════════════════════════════════════════
    // HEALTH POLLING — drives the header status in standalone mode
    // ═══════════════════════════════════════════════════════════

    var _startTime = Date.now();
    var _lastToolCount = 0;
    var _cachedCategories = {};
    var _toolRefreshInFlight = false;
    var _lastToolSyncTs = 0;
    var _lastToolSignature = '';
    var _toolSyncIntervalMs = 10000;
    var _activityLastEventId = null;
    var _activitySessionId = null;
    var _activityHydrated = false;
    var _activitySeenIds = {};
    var _activitySeenOrder = [];
    var _lastSseActivityTs = 0;
    var _activityFallbackCursor = '';
    var _lastServerStatus = '';
    var _slotSyncInFlight = false;
    var _lastSlotSyncTs = 0;
    var _slotSyncIntervalMs = 5000;

    function _normalizeActivitySessionId(sessionId) {
        if (sessionId === null || sessionId === undefined) return '';
        return String(sessionId).trim();
    }

    function _activityDedupKey(eventId, sessionId) {
        if (eventId === null || eventId === undefined || eventId === '') return '';
        var sid = _normalizeActivitySessionId(sessionId) || _activitySessionId || 'legacy';
        return sid + ':' + String(eventId);
    }

    function _resetActivityDedupState() {
        _activitySeenIds = {};
        _activitySeenOrder = [];
        _activityLastEventId = null;
        _activityFallbackCursor = '';
    }

    function _adoptActivitySession(sessionId, reason) {
        var sid = _normalizeActivitySessionId(sessionId);
        if (!sid) return;
        if (_activitySessionId === sid) return;

        var hadSession = !!_activitySessionId;
        _activitySessionId = sid;
        _resetActivityDedupState();

        if (hadSession) {
            console.log('[SSE-Activity] Session changed (' + reason + '), resetting activity timeline');
            fireEvent({ type: 'activityHistory', entries: [] });
            _activityHydrated = false;
            setTimeout(hydrateActivityHistory, 0);
        }
    }

    function rememberActivityEventId(eventId, sessionId) {
        if (eventId === null || eventId === undefined || eventId === '') return;
        var key = _activityDedupKey(eventId, sessionId);
        if (!key) return;
        if (_activitySeenIds[key]) return;
        _activitySeenIds[key] = true;
        _activitySeenOrder.push(key);
        if (_activitySeenOrder.length > 4000) {
            var drop = _activitySeenOrder.shift();
            if (drop) delete _activitySeenIds[drop];
        }
    }

    function isDuplicateActivityEventId(eventId, sessionId) {
        var key = _activityDedupKey(eventId, sessionId);
        if (!key) return false;
        return !!_activitySeenIds[key];
    }

    function rebuildCategoryCache(tools) {
        var categories = {};
        (tools || []).forEach(function(t) {
            var cat = (t && t.name ? t.name : '').split('_')[0] || 'other';
            if (!categories[cat]) categories[cat] = { total: 0, enabled: 0 };
            categories[cat].total++;
            categories[cat].enabled++;
        });
        _cachedCategories = categories;
    }

    function buildToolSignature(tools) {
        var names = (tools || [])
            .map(function(t) { return (t && t.name) ? String(t.name) : ''; })
            .filter(function(n) { return n.length > 0; })
            .sort();
        return names.join('|');
    }

    async function syncToolInventory(force) {
        var now = Date.now();
        if (_toolRefreshInFlight) return null;
        if (!force && (now - _lastToolSyncTs) < _toolSyncIntervalMs) return null;
        _toolRefreshInFlight = true;
        try {
            var toolsResp = await fetch(API_BASE + '/api/tools');
            var toolsData = await toolsResp.json();
            var tools = toolsData?.result?.tools || toolsData?.tools || [];
            if (tools.length > 0) {
                _lastToolCount = tools.length;
                rebuildCategoryCache(tools);
                var signature = buildToolSignature(tools);
                if (signature !== _lastToolSignature) {
                    _lastToolSignature = signature;
                    fireEvent({ type: 'toolSchemas', tools: tools });
                }
            }
            _lastToolSyncTs = now;
            return tools;
        } catch (e) {
            _lastToolSyncTs = now;
            return null;
        } finally {
            _toolRefreshInFlight = false;
        }
    }

    async function syncSlotsSnapshot(force) {
        var now = Date.now();
        if (_slotSyncInFlight) return null;
        if (!force && (now - _lastSlotSyncTs) < _slotSyncIntervalMs) return null;
        _slotSyncInFlight = true;
        try {
            var slots = await _silentToolCall('list_slots', {});
            if (slots && !slots.error) {
                fireEvent({ type: 'slots', data: slots });
            }
            _lastSlotSyncTs = Date.now();
            return slots;
        } catch (err) {
            _lastSlotSyncTs = Date.now();
            return null;
        } finally {
            _slotSyncInFlight = false;
        }
    }

    async function pollHealthAndDispatchState() {
        try {
            // Poll /api/health, and periodically re-sync /api/tools so the
            // header and registry recover automatically after MCP restarts.
            var healthResp = await fetch(API_BASE + '/api/health').then(function(r) { return r.json(); });

            var mcpUp = !!healthResp.mcp_session;
            var serverStatus = mcpUp ? 'running' : (healthResp.capsule_running ? 'starting' : 'stopped');

            if (mcpUp) {
                await syncToolInventory(false);
                if (serverStatus === 'running' && _lastServerStatus !== 'running') {
                    // Recover council grid immediately after backend/session recovery.
                    await syncSlotsSnapshot(true);
                }
            }

            var totalTools = _lastToolCount || 134;

            // Calculate uptime in ms since page load (or since capsule started)
            var uptimeMs = mcpUp ? (Date.now() - _startTime) : 0;

            // Dispatch a flat state message matching what main.js updateHeader expects.
            // Show the backend proxy port (panel origin), not capsule MCP port.
            var originPort = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
            fireEvent({
                type: 'state',
                serverStatus: serverStatus,
                toolCounts: { enabled: totalTools, total: totalTools },
                port: originPort,
                mcpPort: healthResp.mcp_port || 8766,
                uptime: uptimeMs,
                categories: _cachedCategories,
                version: healthResp.version || '0.8.9'
            });
            _lastServerStatus = serverStatus;
        } catch (err) {
            // Server unreachable — dispatch offline state
            var offlinePort = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
            fireEvent({
                type: 'state',
                serverStatus: 'stopped',
                toolCounts: { enabled: 0, total: _lastToolCount || 134 },
                port: offlinePort,
                uptime: 0,
                categories: {}
            });
            _lastServerStatus = 'stopped';
        }
    }

    // Initial poll on page load (slight delay to let DOM render)
    setTimeout(pollHealthAndDispatchState, 500);

    // Periodic poll every 10 seconds.
    setInterval(pollHealthAndDispatchState, 10000);

    // ═══════════════════════════════════════════════════════════
    // SSE ACTIVITY STREAM — listen for tool calls from ALL sources
    // (web UI proxy calls, external MCP from Kiro/Claude, etc.)
    // This is the SINGLE source of truth for the Activity tab.
    // ═══════════════════════════════════════════════════════════

    async function hydrateActivityHistory() {
        if (_activityHydrated) return;
        _activityHydrated = true;
        try {
            const resp = await fetch(API_BASE + '/api/activity-log?limit=500');
            if (!resp.ok) return;
            const data = await resp.json();
            const responseSessionId = data && data.sessionId ? String(data.sessionId) : _normalizeActivitySessionId(resp.headers.get('x-activity-session-id'));
            _adoptActivitySession(responseSessionId, 'hydrate');
            const entries = Array.isArray(data.entries) ? data.entries : [];
            if (entries.length === 0) return;
            entries.forEach(function(entry) {
                if (entry && entry.eventId !== undefined) {
                    rememberActivityEventId(entry.eventId, entry.sessionId || responseSessionId || _activitySessionId);
                }
            });
            var tail = entries[entries.length - 1];
            if (tail && tail.eventId !== undefined) _activityLastEventId = String(tail.eventId);
            var cursorSession = (tail && tail.sessionId) || responseSessionId || _activitySessionId || 'legacy';
            _activityFallbackCursor = String((tail && tail.eventId !== undefined)
                ? (cursorSession + ':id:' + tail.eventId)
                : (cursorSession + ':ts:' + (tail ? tail.timestamp : 0) + ':n=' + entries.length));
            fireEvent({ type: 'activityHistory', entries: entries });
        } catch (err) {
            console.log('[SSE-Activity] History hydrate failed:', err && err.message ? err.message : err);
        }
    }

    function connectActivitySSE() {
        try {
            const url = _activityLastEventId
                ? (API_BASE + '/api/activity-stream?since=' + encodeURIComponent(_activityLastEventId))
                : (API_BASE + '/api/activity-stream');
            const es = new EventSource(url);
            es.onopen = function() {
                _lastSseActivityTs = Date.now();
                syncSlotsSnapshot(false);
            };
            es.onmessage = function(e) {
                try {
                    const event = JSON.parse(e.data);
                    if (!event.tool) return;
                    _lastSseActivityTs = Date.now();
                    const eventSessionId = (event && event.sessionId !== undefined && event.sessionId !== null)
                        ? String(event.sessionId)
                        : _activitySessionId;
                    _adoptActivitySession(eventSessionId, 'sse');
                    const eventId = event.eventId !== undefined ? event.eventId : (e.lastEventId || null);
                    if (isDuplicateActivityEventId(eventId, eventSessionId)) return;
                    rememberActivityEventId(eventId, eventSessionId);
                    if (eventId !== null && eventId !== undefined && eventId !== '') {
                        _activityLastEventId = String(eventId);
                    }
                    console.log('[SSE-Activity]', event.tool, 'source=' + event.source, 'hasResult=' + !!event.result, 'resultType=' + typeof event.result, 'resultKeys=' + (event.result && typeof event.result === 'object' ? Object.keys(event.result).join(',') : 'N/A'), 'rawLen=' + e.data.length);
                    // Hydration noise is intentionally hidden from the user activity feed.
                    if (event.source === 'hydration') return;
                    // Fire to main.js activity feed
                    fireEvent({ type: 'activity', event: event });
                } catch (ex) {
                    console.warn('[SSE-Activity] Parse error:', ex, e.data);
                }
            };
            es.onerror = function() {
                es.close();
                // Reconnect after 5s
                setTimeout(connectActivitySSE, 5000);
            };
        } catch {}
    }

    async function pollActivityFallback() {
        // If SSE is active and recent, don't duplicate work.
        if (_lastSseActivityTs > 0 && (Date.now() - _lastSseActivityTs) < 12000) return;
        try {
            await syncSlotsSnapshot(false);
            const resp = await fetch(API_BASE + '/api/activity-log?limit=500');
            if (!resp.ok) return;
            const data = await resp.json();
            const responseSessionId = data && data.sessionId ? String(data.sessionId) : _normalizeActivitySessionId(resp.headers.get('x-activity-session-id'));
            _adoptActivitySession(responseSessionId, 'fallback');
            const entries = Array.isArray(data.entries) ? data.entries : [];
            if (entries.length === 0) return;

            const tail = entries[entries.length - 1];
            const cursorSession = (tail && tail.sessionId) || responseSessionId || _activitySessionId || 'legacy';
            const cursor = String((tail && tail.eventId !== undefined)
                ? (cursorSession + ':id:' + tail.eventId)
                : (cursorSession + ':ts:' + (tail ? tail.timestamp : 0) + ':n=' + entries.length));
            if (cursor === _activityFallbackCursor) return;
            _activityFallbackCursor = cursor;

            entries.forEach(function(entry) {
                if (entry && entry.eventId !== undefined) {
                    rememberActivityEventId(entry.eventId, entry.sessionId || responseSessionId || _activitySessionId);
                }
            });
            if (tail && tail.eventId !== undefined) _activityLastEventId = String(tail.eventId);
            fireEvent({ type: 'activityHistory', entries: entries });
        } catch (err) {
            console.log('[SSE-Activity] Fallback sync failed:', err && err.message ? err.message : err);
        }
    }

    // Start SSE listener after a brief delay
    setTimeout(function() {
        hydrateActivityHistory();
        connectActivitySSE();
    }, 1500);
    // Failsafe: periodic pull sync if SSE is stalled.
    setInterval(pollActivityFallback, 5000);

    // ═══════════════════════════════════════════════════════════
    // PROACTIVE DATA FETCH — populate all tabs on startup
    // Uses /api/tool with X-Source: hydration header so the server
    // tags these calls and the SSE listener can filter them out.
    // ═══════════════════════════════════════════════════════════

    async function _silentToolCall(toolName, args) {
        const resp = await fetch(`${API_BASE}/api/tool/${toolName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Source': 'hydration'
            },
            body: JSON.stringify(args || {})
        });
        const data = await resp.json();
        if (data.result && data.result.content) {
            try {
                const text = data.result.content[0]?.text;
                return text ? JSON.parse(text) : data.result;
            } catch { return data.result; }
        }
        return data;
    }

    async function hydrateAllTabs() {
        try {
            // 1. Overview: get_status for meta cards
            const status = await _silentToolCall('get_status', {});
            fireEvent({ type: 'capsuleStatus', data: status });

            // 2. Council: list_slots
            const slots = await _silentToolCall('list_slots', {});
            fireEvent({ type: 'slots', data: slots });

            // 3. Memory: bag_catalog
            const catalog = await _silentToolCall('bag_catalog', {});
            fireEvent({ type: 'memoryCatalog', data: catalog });

            // 4. Tools: fetch schemas
            await syncToolInventory(true);

            // 5. Workflows: workflow_list
            const workflows = await _silentToolCall('workflow_list', {});
            // Route through the same path as a manual callTool('workflow_list')
            // so handleWorkflowToolResult picks it up
            fireEvent({ type: 'toolResult', id: '__wf_hydrate__', data: workflows, _toolName: 'workflow_list' });

            // 6. Diagnostics: verify_integrity
            const integrity = await _silentToolCall('verify_integrity', {});
            fireEvent({ type: 'diagResult', diagKey: 'integrity', data: integrity });

        } catch (err) {
            console.log('[shim] Hydration partial failure:', err.message);
        }
    }

    // Hydrate after capsule has had time to start
    setTimeout(hydrateAllTabs, 3000);

    console.log('[Champion Council] VS Code shim loaded — running in standalone web mode');
    console.log('[Champion Council] 72 command types handled (tool proxy, nostr, github, web3, audio, git, settings)');
    console.log('[Champion Council] Health polling active — header status will update automatically');
    console.log('[Champion Council] Activity tracking + SSE stream active');
})();
