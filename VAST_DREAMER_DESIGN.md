# Vast GPU Fleet + Dreamer Training Panel — Design Document

## Scope
Two new tabs for the HF Space web panel + equivalent extension webview sections:
1. **GPU Fleet** — Vast.ai rental monitoring dashboard
2. **Dreamer** — World model training pipeline monitor + config editor

No backend (capsule) changes. All new code goes in `server.py` (API routes) and `static/panel.html` (+ `static/main.js` if separate).

---

## Part 1: GPU Fleet Dashboard

### 1.1 Data Sources (MCP Tools Already Available)

| Tool | Returns | Polling? |
|------|---------|----------|
| `vast_instances` | All active rentals: id, status, gpu, ssh, cost | Yes (10s) |
| `vast_search` | GPU offers: id, gpu, vram, price, reliability | On-demand |
| `vast_details` | Full specs for one offer | On-demand |
| `vast_ready` | Boolean readiness check | Poll until ready |
| `vast_connect` | SSH connection result | On-demand |
| `vast_stop` | Destroy confirmation | On-demand |
| `vast_rent` | New contract ID | On-demand |
| `vast_run` | Remote code execution result | On-demand |
| `vast_load_model` | Model load confirmation | On-demand |
| `vast_generate` | Remote generation result | On-demand |
| `vast_embed` | Remote embedding result | On-demand |
| `vast_broadcast` | Multi-GPU command result | On-demand |
| `vast_distribute` | Per-GPU command results | On-demand |
| `get_status` | Capsule state (includes vast state) | Yes (10s) |

### 1.2 TUI System Analysis (Existing in Capsule)

The TUI's `_render_vast_tab()` tracks per-instance state:
```python
_vast_state = {
    'id': None, 'status': 'OFF', 'gpu': None,
    'public_ip': None, 'ssh_host': None, 'ssh_port': None,
    'connected': False, 'cost_per_hr': 0.0, 'start_time': None,
    'logs': [], 'gpu_util': 0, 'vram_used': 0, 'vram_total': 0,
}
_vast_instances = {}       # Multi-instance: id -> state dict
_vast_activity_log = []    # Recent tool call history
_vast_offers_cache = []    # Last search results
```

Key TUI features to port:
- Multi-instance color-coded cards (magenta/cyan/yellow/green per instance)
- GPU utilization bar (█░ style, 20-char wide)
- VRAM usage bar with used/total GB
- Live cost accumulator (rate × runtime)
- Rental safety guards (max concurrent, in-progress lock, prerequisite checks)
- Activity stream (last 5 vast tool calls with ✓/✗ status)
- 10-second polling thread for instance status updates

### 1.3 HF Space Design — "GPU Fleet" Tab

#### server.py New Routes

```
POST /api/vast/poll       — Proxy to vast_instances + enrich with tracking state
POST /api/vast/search     — Proxy to vast_search with pagination
POST /api/vast/action     — Proxy to vast_rent/stop/connect/ready (with safety guards)
GET  /api/vast/state      — Return cached fleet state (no capsule call)
```

The proxy manages a `_vast_fleet_state` dict server-side, updated by polling.
This avoids hammering the capsule — the panel polls the proxy, the proxy polls the capsule on a slower cadence.

#### Panel HTML Structure

```
Tab: "GPU Fleet"
├── Fleet Header Bar
│   ├── Instance count badge
│   ├── Total $/hr rate
│   ├── Total accumulated spend
│   └── [SEARCH] [REFRESH] buttons
│
├── Instance Cards Grid (auto-wrapping)
│   └── Per-Instance Card
│       ├── Instance ID + status badge (🟢/🟡/🔴)
│       ├── GPU name + type
│       ├── GPU Utilization bar (animated)
│       ├── VRAM bar (used/total GB)
│       ├── SSH endpoint display
│       ├── Cost/hr + runtime
│       ├── Models loaded list
│       ├── Connection status indicator
│       └── Action buttons: [CONNECT] [STOP] [LOGS]
│
├── Search Panel (collapsible)
│   ├── Query input (gpu_ram>=48 reliability>0.95)
│   ├── Results table (sortable by price/vram/reliability)
│   └── [RENT] button per offer (with safety confirmation)
│
├── Activity Stream
│   └── Last 10 vast_* tool calls with timestamp, tool, status, duration
│
└── Safety Status Bar
    ├── Rental lock indicator
    ├── Max concurrent limit
    └── Active rental operation status
```

#### Key JavaScript Functions

```javascript
// Fleet state management
let vastFleetState = { instances: {}, offers: [], activity: [], safety: {} };

// Polling loop (10s interval)
async function pollVastFleet() {
    const resp = await fetch('/api/tool/vast_instances', { method: 'POST', body: '{}' });
    // Parse + update cards
}

// Render instance card with utilization bars
function renderInstanceCard(id, inst) {
    // GPU util bar: CSS width transition for animation
    // VRAM bar: gradient from green to red
    // Cost accumulator: computed from start_time
}

// Search with pagination
async function vastSearch(query, page = 1) { ... }

// Rent with safety confirmation modal
async function vastRent(offerId) {
    if (!confirm(`Rent GPU #${offerId}?`)) return;
    // Call via /api/tool/vast_rent
}
```

### 1.4 Extension Design — Vast Monitoring Section

Add to `src/webview/panel.ts` diagnostics tab or as a new "GPU Fleet" tab:

```
Tab: "GPU Fleet" (or section within Diagnostics)
├── Same layout as HF Space version
├── Uses vscode.postMessage → extension host → MCP tools
├── Extension host polls vast_instances every 10s when tab is active
└── Stores fleet state in extension globalState for persistence
```

Extension host message handlers in `panel.ts`:
```typescript
case 'vastSearch': { ... call MCP vast_search ... }
case 'vastRent': { ... call MCP vast_rent with safety guards ... }
case 'vastConnect': { ... call MCP vast_connect ... }
case 'vastStop': { ... call MCP vast_stop ... }
case 'vastInstances': { ... call MCP vast_instances ... }
case 'vastPollStart': { ... start 10s interval ... }
case 'vastPollStop': { ... clear interval ... }
```

---

## Part 2: Dreamer Training Panel

### 2.1 Data Sources (MCP Tools Already Available)

| Tool | Returns | Use |
|------|---------|-----|
| `get_status` | `dreamer.*` section: fitness, critic_value, reward_count, training_cycles, obs_buffer_size, reward_buffer_size, reward_rate, last_train.*, hold_config.*, causation_hold | Primary dashboard data |
| `show_rssm` | deter_dim, stoch_dim, stoch_classes, hidden_dim, action_dim, imagine_horizon, total_latent | Architecture display |
| `show_weights` | param count, NaN/Inf check, mean, std, lora shapes | Weight health |
| `show_lora` | lora_rank, alpha, A/B shapes, bias shape | Adapter info |
| `imagine` | Imagination rollout trajectories | Live imagination viewer |
| `show_dims` | Brain config dimensions | Architecture |
| `observe` | Feed an observation to the dreamer | Manual observation injection |
| `feed` | Get recent observations | Observation history |
| `hold_yield` | Trigger a HOLD pause | Manual hold |
| `hold_resolve` | Resolve a HOLD | Manual resolve |

### 2.2 Extension System Analysis (Existing)

The extension's Diagnostics tab has:
- **RSSM + DREAMER** button → calls `show_rssm`
- **IMAGINATION** button → calls `imagine`
- **DREAMER CONFIG** collapsible panel with 5 sections:
  - Reward Weights (hold_accept, hold_override, bag_induct, etc.)
  - Training (enabled, auto_train, frequencies, batch_size, noise_scale, gamma, lambda, tau)
  - Imagination (horizon, n_actions, auto_imagine_on_train)
  - Buffers (reward_buffer_max, obs_buffer_max, value_history_max, reward_rate_window)
  - Architecture (read-only: critic_hidden_dim, reward_head_hidden_dim, etc.)
- **Save Config** / **Reset Defaults** buttons
- Backend writes/reads `dreamer_config.json` in workspace

### 2.3 HF Space Design — "Dreamer" Tab

#### server.py New Routes

```
GET  /api/dreamer/state     — Aggregated dreamer state (get_status + show_rssm + show_weights)
POST /api/dreamer/config    — Save dreamer config to FelixBag (bag_induct)
GET  /api/dreamer/config    — Load dreamer config from FelixBag (bag_get)
POST /api/dreamer/imagine   — Run imagination rollout
POST /api/dreamer/observe   — Feed manual observation
```

#### Panel HTML Structure

```
Tab: "Dreamer"
├── Training Dashboard (top section)
│   ├── Vital Stats Row
│   │   ├── Fitness gauge (0-1 with color gradient)
│   │   ├── Critic value display
│   │   ├── Reward count (with rate sparkline)
│   │   ├── Training cycles count
│   │   └── Active/Paused status badge
│   │
│   ├── Training Metrics Panel
│   │   ├── Critic Loss Chart (baseline vs perturbed, last N cycles)
│   │   ├── Reward accumulation chart (rewards over time)
│   │   ├── Buffer fill bars (obs buffer, reward buffer)
│   │   └── Last train details (loss, accepted/rejected, timestamp)
│   │
│   └── HOLD Protocol Panel
│       ├── Confidence threshold display
│       ├── Active hold indicator
│       ├── Hold steps counter
│       ├── [YIELD] [RESOLVE] buttons
│       └── Auto-resolve timeout display
│
├── RSSM Architecture Panel (middle section)
│   ├── Architecture Diagram
│   │   ├── Deterministic path: input → deter_dim (4096)
│   │   ├── Stochastic path: stoch_dim × stoch_classes (32×32)
│   │   ├── Total latent: 5120
│   │   └── Action space: 8 discrete actions
│   │
│   ├── Weight Health
│   │   ├── Total params count
│   │   ├── NaN/Inf check badge (green/red)
│   │   ├── Mean/Std displays
│   │   └── LoRA adapter info (rank, alpha, shapes)
│   │
│   └── Imagination Controls
│       ├── Horizon slider (1-30)
│       ├── [RUN IMAGINATION] button
│       └── Trajectory viewer (per-action rollout display)
│
├── Config Editor (bottom section, collapsible)
│   ├── Reward Weights section
│   │   └── Slider + numeric input per reward type
│   ├── Training section
│   │   └── Toggle switches + numeric inputs
│   ├── Imagination section
│   │   └── Horizon, n_actions, auto_imagine toggle
│   ├── Buffers section
│   │   └── Max sizes with current fill indicators
│   ├── Architecture section (read-only)
│   │   └── Dim values displayed
│   └── [SAVE CONFIG] [RESET DEFAULTS] [LOAD FROM BAG] buttons
│
└── Observation Feed (collapsible)
    ├── Last N observations with timestamp
    ├── [INJECT OBSERVATION] button
    └── Manual observation text input
```

#### Key JavaScript Functions

```javascript
// Dreamer state (polled every 5s)
let dreamerState = { dreamer: {}, rssm: {}, weights: {}, config: {} };

// Poll dreamer metrics
async function pollDreamer() {
    const status = await callTool('get_status');
    dreamerState.dreamer = status.dreamer;
    updateDreamerDashboard();
}

// Training metrics chart (canvas-based, no external deps)
function drawLossChart(canvasId, data) {
    // Mini sparkline chart showing critic loss over training cycles
    // Green for decreasing trend, red for increasing
}

// Reward accumulation sparkline
function drawRewardSparkline(canvasId, rewardHistory) { ... }

// Buffer fill bars
function renderBufferBars(obsSize, obsMax, rewardSize, rewardMax) { ... }

// Config editor
function buildConfigEditor(config) {
    // Generates form fields per config section
    // Slider + numeric input for each value
    // Toggle switches for booleans
}

// Save config to FelixBag
async function saveDreamerConfig() {
    const config = gatherConfigFromForm();
    await callTool('bag_induct', {
        key: 'dreamer_config',
        content: JSON.stringify(config),
        item_type: 'config'
    });
}

// Load config from FelixBag
async function loadDreamerConfig() {
    const result = await callTool('bag_get', { key: 'dreamer_config' });
    if (result?.value) populateConfigForm(JSON.parse(result.value));
}

// Run imagination
async function runImagination(horizon) {
    const result = await callTool('imagine', { scenario: 'interactive', steps: horizon });
    renderTrajectories(result);
}
```

### 2.4 Extension Design — Dreamer Enhancements

The extension already has the config editor in Diagnostics. Enhancements:

1. **Add training metrics display** above the config editor (fitness, critic loss, reward rate)
2. **Add buffer fill indicators** next to buffer config fields
3. **Add loss chart** using canvas sparkline
4. **Add HOLD protocol controls** (yield/resolve buttons with status)
5. **Keep config save/load** using the existing `dreamer_config.json` mechanism

---

## Part 3: Implementation Plan

### Phase 1: Server.py API Routes (no backend changes)
1. Add `/api/dreamer/state` — aggregates get_status + show_rssm + show_weights in one call
2. Add `/api/dreamer/config` GET/POST — load/save via bag_get/bag_induct
3. Add `/api/vast/state` — returns cached fleet state
4. Server-side vast polling (optional, can also be client-side)

### Phase 2: HF Space Panel — Dreamer Tab
1. Add "Dreamer" tab button to tab bar in panel.html
2. Build the training dashboard HTML (vital stats, charts, HOLD controls)
3. Build the RSSM architecture display
4. Build the config editor with save/load to FelixBag
5. Add polling logic (5s for dreamer, only when tab active)
6. Add canvas-based sparkline charts for loss and reward curves

### Phase 3: HF Space Panel — GPU Fleet Tab
1. Add "GPU Fleet" tab button to tab bar in panel.html
2. Build instance cards grid with utilization bars
3. Build search panel with results table
4. Build activity stream display
5. Add safety confirmation modals for rent/stop
6. Add polling logic (10s for instances, only when tab active)

### Phase 4: Extension Webview — Vast Monitoring
1. Add "GPU Fleet" tab to panel.ts tab bar (or section in Diagnostics)
2. Port the HF Space HTML/JS to the webview template
3. Add message handlers in panel.ts for vast tool calls
4. Add polling start/stop based on tab visibility

### Phase 5: Extension Webview — Dreamer Enhancements
1. Add training metrics display above existing config editor
2. Add sparkline charts for loss/reward
3. Add HOLD protocol controls
4. Add buffer fill indicators

---

## Improvements Over TUI Implementation

| Aspect | TUI (Textual) | Web Panel (New) |
|--------|---------------|-----------------|
| GPU bars | ASCII ████░░░░ | CSS animated bars with gradients |
| Cost tracking | Text-only | Live counter with $/hr badge |
| Multi-instance | Color-coded text | Visual cards with status badges |
| Search results | Plain table | Sortable, filterable table |
| Dreamer metrics | Not displayed | Real-time charts with trends |
| Config editor | Not in TUI | Full form with sliders + toggles |
| Imagination | Text output | Visual trajectory viewer |
| HOLD protocol | Hidden | Prominent controls + status |
| Safety guards | Console warnings | Modal confirmations |
| Polling | Thread-based | Tab-aware, pauseable |
