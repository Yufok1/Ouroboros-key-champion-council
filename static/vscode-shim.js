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
        const data = await resp.json();
        // Extract result from JSON-RPC envelope
        if (data.result && data.result.content) {
            try {
                const text = data.result.content[0]?.text;
                return text ? JSON.parse(text) : data.result;
            } catch { return data.result; }
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
                const resp = await fetch(`${API_BASE}/api/tools`);
                const data = await resp.json();
                let tools = data.result?.tools || data.tools || [];
                fireEvent({ type: 'toolSchemas', tools });
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
                 command === 'commitBagVersion') {
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
        else if (command === 'openSettings' || command === 'openBagDocFile' ||
                 command === 'openExternal') {
            if (command === 'openExternal' && msg.url) {
                window.open(msg.url, '_blank');
            } else {
                console.log('[shim] VS Code-specific command ignored:', command);
            }
        }

        // ── Slot Drill-In Terminal (WebSocket bridge) ────────
        else if (command === 'spawnSlotTerminal') {
            var si = msg.slotIndex;
            // Close existing WebSocket for this slot
            if (window._slotWs && window._slotWs[si]) {
                try { window._slotWs[si].close(); } catch (e) {}
            }
            if (!window._slotWs) window._slotWs = {};
            var wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            var ws = new WebSocket(wsProto + '//' + location.host + '/ws/terminal/' + si);
            window._slotWs[si] = ws;
            ws.onmessage = function(ev) {
                try {
                    var d = JSON.parse(ev.data);
                    if (d.type === 'output') {
                        fireEvent({ type: 'slotTerminalOutput', slotIndex: si, data: d.data });
                    } else if (d.type === 'ready') {
                        fireEvent({ type: 'slotTerminalReady', slotIndex: si });
                    } else if (d.type === 'exited') {
                        fireEvent({ type: 'slotTerminalExited', slotIndex: si, code: d.code || 0 });
                    }
                } catch (e) {}
            };
            ws.onerror = function() {
                fireEvent({ type: 'slotTerminalOutput', slotIndex: si, data: '\x1b[31mWebSocket connection failed\x1b[0m\r\n' });
            };
            ws.onclose = function() {
                fireEvent({ type: 'slotTerminalExited', slotIndex: si, code: 0 });
                delete window._slotWs[si];
            };
        }
        else if (command === 'slotTerminalInput') {
            if (window._slotWs && window._slotWs[msg.slotIndex]) {
                try { window._slotWs[msg.slotIndex].send(JSON.stringify({ type: 'input', data: msg.data })); } catch (e) {}
            }
        }
        else if (command === 'killSlotTerminal') {
            if (window._slotWs && window._slotWs[msg.slotIndex]) {
                try { window._slotWs[msg.slotIndex].close(); } catch (e) {}
                delete window._slotWs[msg.slotIndex];
            }
        }
        else if (command === 'requestSlotMetrics') {
            // Route through MCP tool call to get evaluator data
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

        // Map nostr commands to their MCP tool names where possible.
        // The capsule doesn't have direct nostr MCP tools — these are
        // VS Code extension features that use the nostr relay directly.
        // In web mode, we attempt to route through the capsule if a
        // matching tool exists, otherwise graceful no-op with message.

        // Commands that can work through the capsule's observe/bag system
        const toolMappings = {
            'nostrPublishChat': 'observe',
            'nostrFetchChat': 'feed',
            'nostrPublishDocument': 'observe',
            'nostrPublishIdentity': 'get_identity',
            'nostrGetIdentity': 'get_identity',
        };

        // Commands that are purely VS Code extension features
        const vsCodeOnly = [
            'nostrSendDM', 'nostrFetchDMs', 'nostrBlockUser', 'nostrUnblockUser',
            'nostrGetBlockList', 'nostrSetPrivacy', 'nostrGetPrivacy', 'nostrSetProfile',
            'nostrDeleteEvent', 'nostrReact', 'nostrZap', 'nostrResolveLud16',
            'nostrAwardBadge', 'nostrCreateBadge', 'nostrCreatePoll', 'nostrVotePoll',
            'nostrRedactPreview', 'nostrSendLiveChat', 'nostrGetOnlineUsers',
            'nostrSubmitDvmJob',
        ];

        // Voice room commands
        const voiceCommands = [
            'nostrCreateVoiceRoom', 'nostrFetchVoiceRooms', 'nostrGetVoiceRooms',
            'nostrJoinRoom', 'nostrLeaveRoom', 'nostrRaiseHand', 'nostrSendVoiceNote',
        ];

        if (toolMappings[command]) {
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
        else if (voiceCommands.includes(command)) {
            fireEvent({
                type: 'nostrResult', command, id: msg.id,
                ...webModeUnavailable('Voice rooms (requires WebRTC + HTTPS)')
            });
        }
        else if (vsCodeOnly.includes(command)) {
            fireEvent({
                type: 'nostrResult', command, id: msg.id,
                ...webModeUnavailable('Nostr relay features')
            });
        }
        else {
            // Unknown nostr command — try as generic tool
            console.log('[shim] Unknown nostr command:', command);
            fireEvent({
                type: 'nostrResult', command, id: msg.id,
                ...webModeUnavailable('This Nostr feature')
            });
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

    async function handleBagGitCommand(msg) {
        const command = msg.command;

        if (command === 'checkGitAvailable') {
            fireEvent({ type: 'gitAvailable', available: false,
                ...webModeUnavailable('Git operations') });
        }
        else if (command === 'bagGitDiff' || command === 'bagGitInspect') {
            fireEvent({ type: 'bagGitResult', command, id: msg.id,
                ...webModeUnavailable('Git diff/inspect') });
        }
        else if (command === 'commitBagVersion') {
            fireEvent({ type: 'bagGitResult', command, id: msg.id,
                ...webModeUnavailable('Git commit') });
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
    var _toolsFetchedOnce = false;

    async function pollHealthAndDispatchState() {
        try {
            // Only fetch /api/tools once (or when we don't have data yet).
            // After that, just poll /api/health which is lightweight.
            var healthResp = await fetch(API_BASE + '/api/health').then(function(r) { return r.json(); });

            var capsuleUp = healthResp.capsule_running && healthResp.mcp_session;
            var serverStatus = capsuleUp ? 'running' : (healthResp.capsule_running ? 'starting' : 'stopped');

            // Fetch tools list only once, or if capsule just came up and we have no data
            if (!_toolsFetchedOnce && capsuleUp) {
                try {
                    var toolsResp = await fetch(API_BASE + '/api/tools').then(function(r) { return r.json(); });
                    var tools = toolsResp?.result?.tools || toolsResp?.tools || [];
                    if (tools.length > 0) {
                        _lastToolCount = tools.length;
                        _cachedCategories = {};
                        tools.forEach(function(t) {
                            var cat = (t.name || '').split('_')[0] || 'other';
                            if (!_cachedCategories[cat]) _cachedCategories[cat] = { total: 0, enabled: 0 };
                            _cachedCategories[cat].total++;
                            _cachedCategories[cat].enabled++;
                        });
                        _toolsFetchedOnce = true;
                    }
                } catch (e) { /* tools fetch failed, will retry next poll */ }
            }

            var totalTools = _lastToolCount || 134;

            // Calculate uptime in ms since page load (or since capsule started)
            var uptimeMs = capsuleUp ? (Date.now() - _startTime) : 0;

            // Dispatch a flat state message matching what main.js updateHeader expects.
            // Show panel proxy port, not internal capsule port.
            var originPort = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
            fireEvent({
                type: 'state',
                serverStatus: serverStatus,
                toolCounts: { enabled: totalTools, total: totalTools },
                port: originPort,
                mcpPort: healthResp.mcp_port || 8765,
                uptime: uptimeMs,
                categories: _cachedCategories,
                version: healthResp.version || '0.8.9'
            });
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
        }
    }

    // Initial poll on page load (slight delay to let DOM render)
    setTimeout(pollHealthAndDispatchState, 500);

    // Periodic poll every 30 seconds (lightweight — only /api/health after first tools fetch)
    setInterval(pollHealthAndDispatchState, 30000);

    // ═══════════════════════════════════════════════════════════
    // SSE ACTIVITY STREAM — listen for tool calls from ALL sources
    // (web UI proxy calls, external MCP from Kiro/Claude, etc.)
    // This is the SINGLE source of truth for the Activity tab.
    // ═══════════════════════════════════════════════════════════

    // Tools that are internal plumbing — suppress from activity feed
    // (Also filtered server-side, this is a safety net)
    const _HYDRATION_TOOLS = [
        'get_status', 'list_slots', 'bag_catalog', 'workflow_list',
        'verify_integrity', 'get_cached', 'get_identity', 'feed',
        'get_capabilities', 'get_help', 'get_onboarding', 'get_quickstart',
        'hub_tasks'
    ];

    function connectActivitySSE() {
        try {
            const es = new EventSource(API_BASE + '/api/activity-stream');
            es.onmessage = function(e) {
                try {
                    const event = JSON.parse(e.data);
                    if (!event.tool) return;
                    console.log('[SSE-Activity]', event.tool, 'source=' + event.source, 'hasResult=' + !!event.result, 'resultType=' + typeof event.result, 'resultKeys=' + (event.result && typeof event.result === 'object' ? Object.keys(event.result).join(',') : 'N/A'), 'rawLen=' + e.data.length);
                    // Double-check: skip hydration noise (server should already filter)
                    if (event.source === 'hydration') return;
                    if (_HYDRATION_TOOLS.indexOf(event.tool) >= 0 && event.source !== 'external') return;
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
    // Start SSE listener after a brief delay
    setTimeout(connectActivitySSE, 1500);

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
            const toolsResp = await fetch(API_BASE + '/api/tools').then(r => r.json()).catch(() => null);
            if (toolsResp) {
                const tools = toolsResp.result?.tools || toolsResp.tools || [];
                fireEvent({ type: 'toolSchemas', tools });
            }

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
