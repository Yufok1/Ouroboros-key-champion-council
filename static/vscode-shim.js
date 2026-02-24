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

    // --- MCP tool call helper ---
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
            try {
                const result = await mcpToolCall('get_status', {});
                fireEvent({ type: 'state', data: result });
            } catch {}
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
                fireEvent({ type: 'toolResult', id: msg.id, data: result });
            } catch (err) {
                fireEvent({ type: 'toolResult', id: msg.id, error: err.message });
            }
        }

        // ── Diagnostics ──────────────────────────────────────
        else if (command === 'runDiagnostic') {
            fireEvent({
                type: 'diagResult', id: msg.id, diagKey: msg.diagKey,
                error: 'Diagnostics not available in web mode'
            });
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
            try {
                const result = await mcpToolCall('bag_get', { key: 'dreamer_config' });
                let cfg = null;
                if (result && result.value) {
                    try { cfg = typeof result.value === 'string' ? JSON.parse(result.value) : result.value; }
                    catch { cfg = result.value; }
                }
                fireEvent({ type: 'dreamerConfigLoaded', config: cfg });
            } catch {
                fireEvent({ type: 'dreamerConfigLoaded', config: null });
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

    console.log('[Champion Council] VS Code shim loaded — running in standalone web mode');
    console.log('[Champion Council] 72 command types handled (tool proxy, nostr, github, web3, audio, git, settings)');
})();