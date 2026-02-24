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
 */

(function() {
    // Prevent double-init
    if (window.__vsCodeShimInstalled) return;
    window.__vsCodeShimInstalled = true;

    const API_BASE = window.location.origin;
    let _state = {};
    let _listeners = [];

    // Shim: acquireVsCodeApi
    window.acquireVsCodeApi = function() {
        return {
            postMessage: function(msg) {
                handleMessage(msg);
            },
            getState: function() {
                return _state;
            },
            setState: function(s) {
                _state = s;
                return s;
            }
        };
    };

    // Route messages to the appropriate handler
    async function handleMessage(msg) {
        const command = msg.command;

        if (command === 'callTool') {
            try {
                const resp = await fetch(`${API_BASE}/api/tool/${msg.tool}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(msg.args || {})
                });
                const data = await resp.json();
                // Extract result from JSON-RPC response
                let result = data;
                if (data.result && data.result.content) {
                    try {
                        // MCP returns content as [{type: "text", text: "..."}]
                        const text = data.result.content[0]?.text;
                        result = text ? JSON.parse(text) : data.result;
                    } catch {
                        result = data.result;
                    }
                }
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
        else if (command === 'refresh') {
            // Trigger a full state refresh by calling get_status
            try {
                const resp = await fetch(`${API_BASE}/api/tool/get_status`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}'
                });
                const data = await resp.json();
                let result = data;
                if (data.result?.content) {
                    try { result = JSON.parse(data.result.content[0].text); } catch {}
                }
                fireEvent({ type: 'state', data: result });
            } catch {}
        }
        else if (command === 'refreshMemoryCatalog') {
            try {
                const resp = await fetch(`${API_BASE}/api/tool/bag_catalog`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}'
                });
                const data = await resp.json();
                let result = data;
                if (data.result?.content) {
                    try { result = JSON.parse(data.result.content[0].text); } catch {}
                }
                fireEvent({ type: 'memoryCatalog', data: result });
            } catch (err) {
                fireEvent({ type: 'memoryCatalog', error: err.message });
            }
        }
        else if (command === 'runDiagnostic') {
            // Diagnostics not available in standalone mode
            fireEvent({
                type: 'diagResult', id: msg.id, diagKey: msg.diagKey,
                error: 'Diagnostics not available in web mode'
            });
        }
        else if (command === 'openSettings' || command === 'openBagDocFile' ||
                 command === 'bagGitOpenNativeDiff') {
            // VS Code-specific commands — no-op in web mode
            console.log('[shim] VS Code-specific command ignored:', command);
        }
        else {
            // For any unhandled command, try calling it as a tool
            console.log('[shim] Unhandled command, attempting as tool call:', command);
        }
    }

    // Fire event back to main.js via window message
    function fireEvent(data) {
        window.dispatchEvent(new MessageEvent('message', { data }));
    }

    // Provide empty categories if not set
    if (!window.__CATEGORIES__) {
        window.__CATEGORIES__ = {};
    }

    console.log('[Champion Council] VS Code shim loaded — running in standalone web mode');
})();
