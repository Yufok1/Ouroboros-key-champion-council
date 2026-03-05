// ══════════════════════════════════════════════════════════════
// Champion Council - Webview Main Script
// Loaded as a separate file to avoid template literal escaping hell
// ══════════════════════════════════════════════════════════════

(function () {
    const vscode = acquireVsCodeApi();
    const CATEGORIES = window.__CATEGORIES__ || {};
    let _state = {};
    let _activityLog = [];
    const ACTIVITY_PAGE_SIZE = 100;
    let _activityPage = 0; // 0 = newest page
    let _requestId = 0;
    let _weblnAvailable = false;
    let _web3Categories = [];
    let _web3DocTypes = [];
    let _userDID = '';
    let _toolSchemas = {}; // toolName -> {description, inputSchema}
    let _pluggingSlots = {}; // slot index or name -> { modelId, startTime, requestId }
    let _unpluggingSlots = {}; // slot index -> { startTime }
    let _slotHubInfoCache = {}; // model_source -> { author, task, downloads, likes, license, tags, size_mb }
    let _wfCatalog = [];
    let _wfSelectedId = '';
    let _wfLoadedDef = null;
    let _wfLastExec = null;
    let _wfCurrentExecutionId = '';
    let _wfStatusPollTimer = null;
    let _wfGraphMeta = null;
    let _wfDrill = { kind: 'workflow', nodeId: '', edgeIndex: -1, workflowId: '' };
    let _wfNodePositions = {};  // workflowId -> { nodeId -> {x, y} }
    let _wfColorCache = {};     // workflowId -> '#rrggbb'
    let _wfColorIndex = 0;

    // ── SLOT DRILL-IN STATE ──
    let _slotDrill = { active: false, slotIndex: -1 };
    let _slotDrillActivity = []; // per-slot activity entries

    // ── AGENT MCP CONSOLE STATE ──
    var _achatSlot = null;
    var _achatBusy = false;
    var _achatSendTime = 0;
    var _achatElapsedTimer = null;
    var _achatTabs = {};               // key -> tab state
    var _achatActiveTabKey = '';
    var _achatToolConfigOpen = false;
    var _achatAgentConfigOpen = false;
    var _achatComposerBound = false;
    var _achatToolPolicyStoreKey = 'cc_achat_tool_policies_v1';
    if (window.__achatKillRequested === undefined) window.__achatKillRequested = false;
    var _achatToolPolicies = {};
    var _achatDefaultGrantedTools = [
        "get_status", "list_slots", "slot_info", "get_capabilities", "embed_text",
        "invoke_slot", "call", "agent_delegate", "agent_chat_inject", "agent_chat_sessions",
        "bag_get", "bag_put", "bag_search", "bag_catalog", "bag_induct",
        "bag_read_doc", "bag_list_docs", "bag_search_docs", "bag_tree",
        "bag_versions", "bag_diff", "bag_checkpoint", "bag_restore",
        "file_read", "file_write", "file_edit", "file_append", "file_prepend",
        "file_delete", "file_rename", "file_copy", "file_list", "file_tree",
        "file_search", "file_info", "file_checkpoint", "file_versions", "file_diff", "file_restore",
        "workflow_list", "workflow_get", "workflow_status",
        "plug_model", "hub_plug", "unplug_slot",
        "cascade_graph", "cascade_chain", "cascade_data", "cascade_system",
        "cascade_record", "cascade_instrument", "cascade_proxy",
        "diagnose_file", "diagnose_directory", "symbiotic_interpret",
        "trace_root_causes", "forensics_analyze", "metrics_analyze"
    ];
    var _achatBlockedTools = {
        "workflow_execute": 1, "start_api_server": 1, "implode": 1, "defrost": 1,
        "spawn_quine": 1, "spawn_swarm": 1, "replicate": 1, "export_quine": 1
    };

    // ── NIP-88: POLL STATE ──
    var _polls = {}; // pollId -> { question, options, votes, voted, expired }
    var _pollVotes = {}; // pollId -> { optionIndex -> count }

    // ── NIP-58: BADGE STATE ──
    var _badges = {}; // badgeATag -> { id, name, description, image, creator }
    var _badgeAwards = {}; // pubkey -> [badgeATag, ...]
    var _myBadges = []; // badges awarded to _nostrPubkey

    // ── NIP-90: DVM STATE ──
    var _dvmJobs = {}; // eventId -> { kind, input, status, result, created_at }

    // ── NIP-39: IDENTITY STATE ──
    var _identityClaims = []; // { platform, identity, proof }
    var _identityBadges = {}; // pubkey -> [{ platform, identity, proof }, ...]

    // ── NIP-A0: VOICE NOTE STATE ──
    var _voiceNoteRecording = false;
    var _voiceNoteMediaRecorder = null;
    var _voiceNoteChunks = [];
    var _voiceNoteTimer = null;
    var _voiceNoteStartTime = 0;

    // ── NIP-53: VOICE ROOM STATE ──
    let _voiceRooms = [];
    let _activeRoomATag = null;
    let _activeRoomParticipants = {};
    let _voiceChatMessages = [];
    let _voiceMicOn = false;
    let _voiceRoomTimer = null;
    let _voiceRoomJoinTime = 0;
    let _voiceMicSensitivity = 1.5; // multiplier for level display
    let _voiceNoiseGate = 5; // minimum level threshold (0-100)
    let _voicePTTMode = false; // false = open mic, true = push-to-talk
    let _voicePTTKey = ' '; // default PTT key (Space)
    let _voicePTTActive = false; // true while PTT key is held
    let _voicePTTBinding = false; // true while waiting for new PTT key press
    let _voiceDeafened = false; // true = incoming audio muted
    let _voiceMasterVolume = 100; // 0-100
    let _voiceSelectedDevice = ''; // selected input device name
    let _voiceMonitorEnabled = false; // local sidetone monitor
    let _voiceMonitorHeadphonesConfirmed = false; // safety gate
    let _voiceMonitorGain = null;

    // ── WEBSOCKET + AUDIOWORKLET BRIDGE ──
    // Receives raw PCM from extension via WebSocket, produces MediaStream for PeerJS
    let _audioWs = null;
    let _audioWorkletNode = null;
    let _audioStreamDest = null;
    let _audioWsCtx = null;

    function _voiceToast(message, kind, ms) {
        if (typeof mpToast === 'function') mpToast(message, kind || 'info', ms || 2200);
        else console.log('[VoiceMonitor]', message);
    }

    function _updateVoiceMonitorUI() {
        var monitorToggle = document.getElementById('voice-monitor-toggle');
        var monitorHeadphones = document.getElementById('voice-monitor-headphones');

        if (monitorHeadphones) monitorHeadphones.checked = !!_voiceMonitorHeadphonesConfirmed;

        if (monitorToggle) {
            var active = _voiceMonitorEnabled && _voiceMonitorHeadphonesConfirmed && _voiceMicOn;
            monitorToggle.textContent = active ? 'MONITOR ON' : 'MONITOR OFF';
            monitorToggle.style.background = active ? '#4caf50' : '';
            monitorToggle.style.color = active ? '#000' : '';
            monitorToggle.style.fontWeight = active ? 'bold' : '';
            monitorToggle.title = active
                ? 'Disable local mic monitor'
                : 'Enable local mic monitor (headphones required)';
        }
    }

    function _applyVoiceMonitorState() {
        if (!_audioWsCtx || !_audioWorkletNode) {
            _updateVoiceMonitorUI();
            return;
        }

        if (!_voiceMonitorGain) {
            _voiceMonitorGain = _audioWsCtx.createGain();
        }
        _voiceMonitorGain.gain.value = Math.max(0, Math.min(1, _voiceMasterVolume / 100));

        try { _audioWorkletNode.disconnect(_voiceMonitorGain); } catch (e) { }
        try { _voiceMonitorGain.disconnect(_audioWsCtx.destination); } catch (e) { }

        if (_voiceMonitorEnabled && _voiceMonitorHeadphonesConfirmed && _voiceMicOn) {
            _audioWorkletNode.connect(_voiceMonitorGain);
            _voiceMonitorGain.connect(_audioWsCtx.destination);
        }

        _updateVoiceMonitorUI();
    }

    function _setVoiceMonitorEnabled(enabled) {
        if (enabled) {
            if (!_voiceMonitorHeadphonesConfirmed) {
                _voiceMonitorEnabled = false;
                _voiceToast('Enable "I am using headphones" before monitor.', 'warning', 2800);
                _applyVoiceMonitorState();
                return;
            }
            if (!_voiceMicOn) {
                _voiceMonitorEnabled = false;
                _voiceToast('Turn MIC ON to start monitor calibration.', 'info', 2400);
                _applyVoiceMonitorState();
                return;
            }
            _voiceMonitorEnabled = true;
            _voiceToast('Headphones monitor enabled (calibration mode).', 'info', 2200);
        } else {
            _voiceMonitorEnabled = false;
        }
        _applyVoiceMonitorState();
    }

    async function _startAudioBridge(wsPort) {
        if (_audioWs) return; // already connected
        try {
            _audioWsCtx = new (window.AudioContext || window.webkitAudioContext)();
            // Register AudioWorklet processor via Blob URL (avoids CSP file-serving issues)
            var workletCode = [
                'class PCMWorkletProcessor extends AudioWorkletProcessor {',
                '  constructor() {',
                '    super();',
                '    this._buf = new Float32Array(0);',
                '    this._ratio = sampleRate / 16000;',
                '    this.port.onmessage = (e) => {',
                '      if (e.data instanceof ArrayBuffer) {',
                '        var pcm = new Int16Array(e.data);',
                '        var f = new Float32Array(pcm.length);',
                '        for (var i = 0; i < pcm.length; i++) f[i] = pcm[i] / 32768;',
                '        var out;',
                '        if (Math.abs(this._ratio - 1) > 0.01) {',
                '          var len = Math.round(f.length * this._ratio);',
                '          out = new Float32Array(len);',
                '          for (var j = 0; j < len; j++) {',
                '            var si = j / this._ratio;',
                '            var i0 = Math.floor(si);',
                '            var i1 = Math.min(i0 + 1, f.length - 1);',
                '            var fr = si - i0;',
                '            out[j] = f[i0] * (1 - fr) + f[i1] * fr;',
                '          }',
                '        } else { out = f; }',
                '        var nb = new Float32Array(this._buf.length + out.length);',
                '        nb.set(this._buf);',
                '        nb.set(out, this._buf.length);',
                '        this._buf = nb;',
                '      } else if (e.data === "clear") {',
                '        this._buf = new Float32Array(0);',
                '      }',
                '    };',
                '  }',
                '  process(inputs, outputs) {',
                '    var ch = outputs[0][0];',
                '    if (!ch) return true;',
                '    if (this._buf.length >= ch.length) {',
                '      ch.set(this._buf.subarray(0, ch.length));',
                '      this._buf = this._buf.subarray(ch.length);',
                '    } else {',
                '      if (this._buf.length > 0) ch.set(this._buf);',
                '      for (var i = this._buf.length; i < ch.length; i++) ch[i] = 0;',
                '      this._buf = new Float32Array(0);',
                '    }',
                '    return true;',
                '  }',
                '}',
                'registerProcessor("pcm-worklet-processor", PCMWorkletProcessor);'
            ].join('\n');
            var blob = new Blob([workletCode], { type: 'application/javascript' });
            var workletUrl = URL.createObjectURL(blob);
            await _audioWsCtx.audioWorklet.addModule(workletUrl);
            URL.revokeObjectURL(workletUrl);

            _audioWorkletNode = new AudioWorkletNode(_audioWsCtx, 'pcm-worklet-processor');
            _audioStreamDest = _audioWsCtx.createMediaStreamDestination();
            _audioWorkletNode.connect(_audioStreamDest);

            _audioWs = new WebSocket('ws://127.0.0.1:' + wsPort);
            _audioWs.binaryType = 'arraybuffer';
            _audioWs.onmessage = function (evt) {
                if (evt.data instanceof ArrayBuffer && _audioWorkletNode) {
                    _audioWorkletNode.port.postMessage(evt.data, [evt.data]);
                }
            };
            _audioWs.onopen = function () {
                console.log('[AudioBridge] WebSocket connected to port ' + wsPort);
            };
            _audioWs.onerror = function (err) {
                console.error('[AudioBridge] WebSocket error:', err);
            };
            _audioWs.onclose = function () {
                console.log('[AudioBridge] WebSocket closed');
                _audioWs = null;
            };

            VoiceP2P.setLocalStream(_audioStreamDest.stream);
            _applyVoiceMonitorState();
            console.log('[AudioBridge] MediaStream set on VoiceP2P');
        } catch (err) {
            console.error('[AudioBridge] Failed to start:', err);
        }
    }

    function _stopAudioBridge() {
        if (_audioWorkletNode && _voiceMonitorGain) { try { _audioWorkletNode.disconnect(_voiceMonitorGain); } catch (e) { } }
        if (_voiceMonitorGain && _audioWsCtx) { try { _voiceMonitorGain.disconnect(_audioWsCtx.destination); } catch (e) { } }
        _voiceMonitorGain = null;
        if (_audioWs) { try { _audioWs.close(); } catch (e) { } _audioWs = null; }
        if (_audioWorkletNode) { try { _audioWorkletNode.disconnect(); } catch (e) { } _audioWorkletNode = null; }
        _audioStreamDest = null;
        if (_audioWsCtx) { try { _audioWsCtx.close(); } catch (e) { } _audioWsCtx = null; }
        VoiceP2P.clearLocalStream();
        _updateVoiceMonitorUI();
    }

    // ── P2P VOICE MANAGER (PeerJS) ──
    var VoiceP2P = (function () {
        var _peer = null;
        var _localStream = null;
        var _peers = {}; // peerId -> { call, stream, audioEl, analyser, speaking }
        var _roomId = null;
        var _myPeerId = null;
        var _speakingRAF = null;
        var _audioCtx = null;

        function generatePeerId(roomId) {
            // Deterministic-ish peer ID from room + random suffix
            var rand = Math.random().toString(36).substring(2, 8);
            return 'ouro-' + roomId.replace(/[^a-zA-Z0-9]/g, '').substring(0, 16) + '-' + rand;
        }

        function attachRemoteStream(peerId, stream) {
            var audio = document.createElement('audio');
            audio.srcObject = stream;
            audio.autoplay = true;
            audio.setAttribute('data-peer', peerId);
            document.body.appendChild(audio);
            // Speaking detection for this peer
            var peerInfo = _peers[peerId];
            if (peerInfo) {
                peerInfo.audioEl = audio;
                peerInfo.stream = stream;
                try {
                    if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                    var source = _audioCtx.createMediaStreamSource(stream);
                    var analyser = _audioCtx.createAnalyser();
                    analyser.fftSize = 256;
                    analyser.smoothingTimeConstant = 0.5;
                    source.connect(analyser);
                    peerInfo.analyser = analyser;
                } catch (e) { console.warn('[VoiceP2P] analyser error:', e); }
            }
        }

        function detachPeer(peerId) {
            var info = _peers[peerId];
            if (!info) return;
            if (info.call) try { info.call.close(); } catch (e) { }
            if (info.audioEl) { info.audioEl.pause(); info.audioEl.srcObject = null; info.audioEl.remove(); }
            delete _peers[peerId];
            renderVoiceParticipants();
        }

        function updateSpeakingIndicators() {
            if (!_roomId) return;
            var buf = new Uint8Array(128);
            Object.keys(_peers).forEach(function (pid) {
                var p = _peers[pid];
                if (p && p.analyser) {
                    p.analyser.getByteFrequencyData(buf);
                    var sum = 0;
                    for (var i = 0; i < buf.length; i++) sum += buf[i];
                    var avg = sum / buf.length;
                    var wasSpeaking = p.speaking;
                    p.speaking = avg > 15;
                    if (p.speaking !== wasSpeaking) renderVoiceParticipants();
                }
            });
            _speakingRAF = requestAnimationFrame(updateSpeakingIndicators);
        }

        return {
            join: function (roomId) {
                if (typeof Peer === 'undefined') {
                    console.error('[VoiceP2P] PeerJS not loaded');
                    return;
                }
                _roomId = roomId;
                _myPeerId = generatePeerId(roomId);
                _peer = new Peer(_myPeerId, {
                    debug: 1,
                    config: {
                        iceServers: [
                            { urls: 'stun:stun.l.google.com:19302' },
                            { urls: 'stun:stun1.l.google.com:19302' },
                            { urls: 'stun:stun.services.mozilla.com' }
                        ]
                    }
                });
                _peer.on('open', function (id) {
                    console.log('[VoiceP2P] Connected as', id);
                    // Tell extension our peer ID so it can broadcast via Nostr
                    vscode.postMessage({ command: 'voiceP2PReady', peerId: id, roomId: roomId });
                });
                _peer.on('call', function (call) {
                    console.log('[VoiceP2P] Incoming call from', call.peer);
                    _peers[call.peer] = { call: call, stream: null, audioEl: null, analyser: null, speaking: false };
                    call.answer(_localStream || undefined);
                    call.on('stream', function (remoteStream) {
                        attachRemoteStream(call.peer, remoteStream);
                        renderVoiceParticipants();
                    });
                    call.on('close', function () { detachPeer(call.peer); });
                    call.on('error', function (err) { console.error('[VoiceP2P] call error:', err); detachPeer(call.peer); });
                });
                _peer.on('error', function (err) { console.error('[VoiceP2P] peer error:', err); });
                // Start speaking detection loop
                _speakingRAF = requestAnimationFrame(updateSpeakingIndicators);
            },
            connectToPeer: function (remotePeerId) {
                if (!_peer || !_peer.open || _peers[remotePeerId]) return;
                console.log('[VoiceP2P] Calling peer', remotePeerId);
                _peers[remotePeerId] = { call: null, stream: null, audioEl: null, analyser: null, speaking: false };
                var call = _peer.call(remotePeerId, _localStream || new MediaStream());
                _peers[remotePeerId].call = call;
                call.on('stream', function (remoteStream) {
                    attachRemoteStream(remotePeerId, remoteStream);
                    renderVoiceParticipants();
                });
                call.on('close', function () { detachPeer(remotePeerId); });
                call.on('error', function (err) { console.error('[VoiceP2P] call error:', err); detachPeer(remotePeerId); });
            },
            setLocalStream: function (stream) {
                _localStream = stream;
                // Replace audio track on existing peer connections
                if (stream) {
                    var track = stream.getAudioTracks()[0];
                    if (track) {
                        Object.keys(_peers).forEach(function (pid) {
                            var info = _peers[pid];
                            if (info.call && info.call.peerConnection) {
                                var senders = info.call.peerConnection.getSenders();
                                senders.forEach(function (sender) {
                                    if (sender.track && sender.track.kind === 'audio') {
                                        sender.replaceTrack(track).catch(function (err) {
                                            console.warn('[VoiceP2P] replaceTrack failed for', pid, err);
                                        });
                                    }
                                });
                            }
                        });
                    }
                }
            },
            clearLocalStream: function () {
                _localStream = null;
            },
            leave: function () {
                _roomId = null;
                if (_speakingRAF) { cancelAnimationFrame(_speakingRAF); _speakingRAF = null; }
                Object.keys(_peers).forEach(function (pid) { detachPeer(pid); });
                _peers = {};
                if (_peer) { try { _peer.destroy(); } catch (e) { } _peer = null; }
                if (_audioCtx) { try { _audioCtx.close(); } catch (e) { } _audioCtx = null; }
                _localStream = null;
                _myPeerId = null;
            },
            getPeerCount: function () { return Object.keys(_peers).length; },
            getPeers: function () { return _peers; },
            getMyPeerId: function () { return _myPeerId; },
            isConnected: function () { return _peer && _peer.open; }
        };
    })();

    // ── MESSAGE HANDLER ──
    window.addEventListener('message', function (e) {
        var msg = e.data;
        try {
            switch (msg.type) {
                case 'state':
                    var prevStatus = _state ? _state.serverStatus : '';
                    _state = msg;
                    if (msg.activityLog) {
                        // First state message hydrates the activity feed;
                        // subsequent syncs only update the backing array
                        // without re-rendering (preserves expanded details).
                        // Individual 'activity' events handle live rendering.
                        var needsRender = _activityLog.length === 0 && msg.activityLog.length > 0;
                        _rehydrateActivityLog(msg.activityLog);
                        if (needsRender) renderActivityFeed();
                    }
                    updateHeader(msg);
                    updateCatBars(msg.categories);
                    // Auto-refresh when server transitions to running
                    if (msg.serverStatus === 'running' && prevStatus !== 'running') {
                        // Refresh council slots from capsule
                        callTool('list_slots', {});
                        // Retry memory catalog if it failed during startup
                        var ml = document.getElementById('mem-list');
                        if (ml && (ml.innerText.indexOf('Loading...') !== -1 || ml.innerText.indexOf('ERROR') !== -1)) {
                            callTool('bag_catalog', {});
                        }
                    }
                    break;
                case 'capsuleStatus':
                    updateOverviewMeta(msg.data);
                    break;
                case 'slots':
                    renderSlots(msg.data);
                    break;
                case 'activity':
                    addActivityEntry(msg.event);
                    // External bag mutations should refresh Memory tab immediately.
                    if (msg.event && msg.event.source === 'external' &&
                        ['bag_put', 'bag_induct', 'bag_forget', 'pocket', 'load_bag'].indexOf(msg.event.tool) >= 0) {
                        vscode.postMessage({ command: 'refreshMemoryCatalog' });
                    }
                    break;
                case 'activityHistory':
                    if (Array.isArray(msg.entries)) {
                        _rehydrateActivityLog(msg.entries);
                        renderActivityFeed();
                    }
                    break;
                case 'memoryCatalog':
                    _pendingTools.__memoryCatalog__ = 'bag_catalog';
                    handleToolResult({ id: '__memoryCatalog__', data: msg.data, error: msg.error });
                    break;
                case 'memoryExported':
                    setMemoryExportStatus('Exported ' + (msg.fileType || 'file') + ' to: ' + (msg.path || ''), false);
                    break;
                case 'memoryExportError':
                    setMemoryExportStatus(msg.error || 'Export failed.', true);
                    break;
                case 'diagResult':
                    handleDiagResult(msg);
                    break;
                case 'toolResult':
                    handleToolResult(msg);
                    break;
                case 'dreamerConfigLoaded':
                    if (msg.config) { renderDreamerConfig(msg.config); }
                    break;
                case 'nostrEvent':
                    handleNostrEvent(msg.event);
                    break;
                case 'nostrIdentity':
                    handleNostrIdentity(msg);
                    break;
                case 'nostrError':
                    console.error('[Nostr]', msg.error);
                    mpToast(msg.error || 'Nostr operation failed', 'error', 5000);
                    break;
                case 'nostrWorkflowPublished':
                    if (msg.event) handleNostrEvent(msg.event);
                    mpToast('Workflow published to marketplace', 'success', 2600);
                    break;
                case 'nostrDM':
                    handleNostrDM(msg);
                    break;
                case 'nostrDMSent':
                    break;
                case 'nostrPresence':
                    handleNostrPresence(msg);
                    break;
                case 'nostrBlockList':
                    handleBlockList(msg.blocked || []);
                    break;
                case 'nostrEventDeleted':
                    handleEventDeleted(msg.eventId);
                    break;
                case 'nostrProfile':
                case 'nostrProfileUpdated':
                    handleProfileUpdate(msg);
                    break;
                case 'nostrPrivacy':
                    handlePrivacyUpdate(msg.settings);
                    break;
                case 'nostrRedactResult':
                    handleRedactResult(msg);
                    break;
                case 'nostrOnlineUsers':
                    handleOnlineUsers(msg.users || []);
                    break;
                // ── NIP-53: VOICE ROOMS ──
                case 'nostrVoiceRoom':
                    handleVoiceRoomUpdate(msg.room);
                    break;
                case 'nostrVoiceRooms':
                    handleVoiceRoomList(msg.rooms || []);
                    break;
                case 'nostrLiveChat':
                    handleVoiceLiveChat(msg);
                    break;
                case 'nostrRoomPresence':
                    handleVoiceRoomPresence(msg.presence);
                    break;
                case 'nostrRoomJoined':
                    handleVoiceRoomJoined(msg);
                    break;
                case 'nostrRoomLeft':
                    handleVoiceRoomLeft(msg);
                    break;
                case 'nostrVoiceRoomCreated':
                    vscode.postMessage({ command: 'nostrFetchVoiceRooms' });
                    break;
                case 'voiceP2PPeerJoined':
                    if (msg.peerId && VoiceP2P.isConnected()) {
                        VoiceP2P.connectToPeer(msg.peerId);
                    }
                    break;
                case 'micStarted':
                    _voiceMicOn = true;
                    var micToggleEl = document.getElementById('voice-mic-toggle');
                    if (micToggleEl) micToggleEl.classList.add('active');
                    var micLabelEl = document.getElementById('voice-mic-label');
                    if (micLabelEl) micLabelEl.textContent = 'MIC ON' + (msg.device ? ' (' + msg.device.substring(0, 20) + ')' : '');
                    renderVoiceParticipants();
                    // Start audio bridge for peer streaming
                    if (msg.audioWsPort) { _startAudioBridge(msg.audioWsPort); }
                    _updateVoiceMonitorUI();
                    break;
                case 'micStopped':
                    _voiceMicOn = false;
                    _voiceMonitorEnabled = false; // safety: monitor only during active calibration
                    _applyVoiceMonitorState();
                    var micToggleEl2 = document.getElementById('voice-mic-toggle');
                    if (micToggleEl2) micToggleEl2.classList.remove('active');
                    var micLabelEl2 = document.getElementById('voice-mic-label');
                    if (micLabelEl2) micLabelEl2.textContent = 'MIC OFF';
                    var barEl = document.getElementById('voice-mic-level-bar');
                    if (barEl) { barEl.style.width = '0%'; barEl.style.background = '#4caf50'; }
                    _stopAudioBridge();
                    renderVoiceParticipants();
                    break;
                case 'micLevel':
                    var level = msg.level || 0;
                    var barEl2 = document.getElementById('voice-mic-level-bar');
                    if (barEl2) {
                        barEl2.style.width = level + '%';
                        if (level < 40) barEl2.style.background = '#4caf50';
                        else if (level < 70) barEl2.style.background = '#ff9800';
                        else barEl2.style.background = '#f44336';
                    }
                    var testBar = document.getElementById('voice-test-bar');
                    if (testBar) {
                        testBar.style.width = level + '%';
                        if (level < 40) testBar.style.background = '#4caf50';
                        else if (level < 70) testBar.style.background = '#ff9800';
                        else testBar.style.background = '#f44336';
                    }
                    break;
                case 'micError':
                    console.error('[Mic] Error:', msg.error);
                    var micLabelErr = document.getElementById('voice-mic-label');
                    if (micLabelErr) micLabelErr.textContent = msg.error || 'MIC ERROR';
                    break;
                case 'audioDevices':
                    console.log('[Mic] Available devices:', msg.devices);
                    // Populate input device dropdown
                    var devSelect = document.getElementById('voice-input-device');
                    if (devSelect && msg.devices) {
                        var currentVal = devSelect.value;
                        devSelect.innerHTML = '<option value="">Default Microphone</option>';
                        (msg.devices || []).forEach(function (dev) {
                            var opt = document.createElement('option');
                            opt.value = dev;
                            opt.textContent = dev;
                            if (dev === _voiceSelectedDevice) opt.selected = true;
                            devSelect.appendChild(opt);
                        });
                        if (!_voiceSelectedDevice && msg.devices.length > 0) {
                            // Keep default selected
                        }
                    }
                    break;
                case 'nostrZapReceipt':
                    handleZapReceipt(msg);
                    break;
                case 'nostrZapResult':
                    handleZapResult(msg);
                    break;
                case 'nostrZapTotal':
                    if (msg.eventId) { _zapTotals[msg.eventId] = msg.total || 0; }
                    break;
                case 'toolSchemas':
                    if (Array.isArray(msg.tools)) {
                        _toolSchemas = {};
                        msg.tools.forEach(function (t) {
                            if (t && t.name) _toolSchemas[t.name] = t;
                        });
                        buildToolsRegistry();
                        var activeAchat = _getActiveAchatTab ? _getActiveAchatTab() : null;
                        if (activeAchat) {
                            _renderAchatRunMode(activeAchat);
                            _renderAchatToolSelect(activeAchat);
                            _renderAchatToolConfig(activeAchat);
                            _renderAchatPolicyPanel(activeAchat);
                        }
                    }
                    break;
                case 'nostrDocumentPublished':
                    if (msg.event) handleNostrEvent(msg.event);
                    mpToast((msg.docType || 'document') + ' published to marketplace', 'success', 2800);
                    break;
                // ── WEB3 MESSAGES ──
                case 'web3DID':
                    _userDID = msg.did || '';
                    var didEl = document.getElementById('user-did');
                    if (didEl) { didEl.textContent = _userDID ? _userDID.slice(0, 20) + '...' + _userDID.slice(-8) : 'Not generated'; }
                    break;
                case 'web3CID':
                    console.log('[Web3] CID computed:', msg.cid);
                    break;
                case 'web3ReputationVC':
                    console.log('[Web3] Reputation VC issued for', msg.pubkey);
                    break;
                case 'web3DocTypes':
                    _web3DocTypes = msg.web3 || [];
                    break;
                case 'web3Categories':
                    _web3Categories = msg.categories || [];
                    updateWeb3CategoryFilters();
                    break;
                case 'weblnStatus':
                    _weblnAvailable = !!msg.available;
                    updateWeblnUI();
                    break;
                case 'nostrStallCreated':
                    console.log('[Commerce] Stall created:', msg.event && msg.event.id);
                    break;
                case 'nostrProductCreated':
                    console.log('[Commerce] Product created:', msg.event && msg.event.id);
                    break;
                case 'nostrCheckoutSent':
                    alert('Order sent to merchant via encrypted DM. Check your DMs for their response with a Lightning invoice.');
                    break;
                case 'githubAuth':
                    handleGitHubAuth(msg);
                    break;
                case 'githubGistCreated':
                    handleGistCreated(msg.gist);
                    break;
                case 'githubGistUpdated':
                    handleGistUpdated(msg.gist);
                    break;
                case 'githubGistForked':
                    handleGistForked(msg.gist);
                    break;
                case 'githubGistHistory':
                    handleGistHistory(msg.gistId, msg.history);
                    break;
                case 'githubGistImported':
                    handleGistImported(msg.result);
                    break;
                case 'githubMyGists':
                    handleMyGists(msg.gists);
                    break;
                case 'gistSearchResults':
                    handleGistSearchResults(msg);
                    break;
                case 'gistContentResult':
                    handleGistContentResult(msg);
                    break;
                case 'gistIndexingComplete':
                    handleGistIndexingComplete(msg);
                    break;
                case 'bagCommitResult':
                    handleBagCommitResult(msg);
                    break;
                case 'bagGitInfo':
                    handleBagGitInfo(msg);
                    break;
                case 'bagGitDiffResult':
                    handleBagGitDiffResult(msg);
                    break;
                case 'bagDocOpened':
                    if (msg.error) mpToast(msg.error, 'error', 3800);
                    else if (msg.filePath) mpToast('Opened snapshot: ' + msg.filePath, 'success', 2200);
                    break;
                case 'gitAvailability':
                    _gitAvailable = !!msg.available;
                    _gitProbed = true;
                    break;
                case 'uxSettings':
                    handleUXSettings(msg.settings || {});
                    break;
                case 'slotEvalMetrics':
                    if (_slotDrill.active && msg.slotIndex === _slotDrill.slotIndex && msg.metrics) {
                        _updateSlotMetricsFromEval(msg.metrics);
                    }
                    break;
                case 'nostrPollCreated':
                    mpToast('Poll published', 'success', 2600);
                    document.getElementById('poll-create-form').style.display = 'none';
                    break;
                case 'nostrBadgeCreated':
                    mpToast('Badge created: ' + msg.id, 'success', 2600);
                    document.getElementById('badge-create-form').style.display = 'none';
                    break;
                case 'nostrDvmJobSubmitted':
                    if (msg.eventId) {
                        _dvmJobs[msg.eventId] = { status: 'pending', input: document.getElementById('dvm-input').value, created_at: Date.now() };
                        renderDvmJobs();
                        mpToast('Job submitted', 'success', 2600);
                        document.getElementById('dvm-input').value = '';
                    }
                    break;
                case 'nostrIdentityPublished':
                    mpToast('Identity claims published', 'success', 2600);
                    break;
                case 'nostrVoiceNoteSent':
                    mpToast('Voice note sent', 'success', 2600);
                    break;
                case 'nostrRelayAuth':
                    var statusEl = document.getElementById('relay-auth-status');
                    if (statusEl) {
                        statusEl.textContent = msg.success ? 'NIP-42 OK' : 'NIP-42 FAIL';
                        statusEl.style.color = msg.success ? 'var(--green)' : 'var(--red)';
                    }
                    break;
            }
        } catch (err) {
            console.error('[Webview] Error handling message:', msg.type, err);
        }
    });

    // ── TAB NAVIGATION ──
    document.querySelectorAll('.tab').forEach(function (tab) {
        tab.addEventListener('click', function () {
            document.querySelectorAll('.tab').forEach(function (t) { t.classList.remove('active'); });
            document.querySelectorAll('.content').forEach(function (c) { c.classList.remove('active'); });
            tab.classList.add('active');
            var target = document.getElementById('tab-' + tab.dataset.tab);
            if (target) target.classList.add('active');

            // Auto-fetch Memory catalog on first view
            if (tab.dataset.tab === 'memory') {
                var memList = document.getElementById('mem-list');
                if (memList && memList.innerText.indexOf('Loading...') !== -1) {
                    callTool('bag_catalog', {});
                }
                if (!_gitProbed) {
                    vscode.postMessage({ command: 'checkGitAvailable' });
                }
            }

            // Auto-fetch tool schemas when Tools tab is first opened
            if (tab.dataset.tab === 'tools') {
                if (Object.keys(_toolSchemas).length === 0) {
                    vscode.postMessage({ command: 'fetchToolSchemas' });
                }
            }

            // Auto-fetch workflows when the Workflows tab is first opened
            if (tab.dataset.tab === 'workflows') {
                if (_wfCatalog.length === 0) {
                    callTool('workflow_list', {});
                } else {
                    renderWorkflowList();
                    // Always re-fetch definition if cached _wfLoadedDef is missing or has no nodes
                    if (_wfSelectedId && (!_wfLoadedDef || !Array.isArray(_wfLoadedDef.nodes) || _wfLoadedDef.nodes.length === 0)) {
                        callTool('workflow_get', { workflow_id: _wfSelectedId });
                    } else {
                        renderWorkflowGraph(_wfLoadedDef, _wfLastExec ? _wfLastExec.node_states : null);
                        renderWorkflowNodeStates(_wfLoadedDef, _wfLastExec ? _wfLastExec.node_states : null);
                        _wfRenderDrillDetail();
                    }
                }
            }
        });
    });

    // ── HEADER UPDATE ──
    function updateHeader(st) {
        var dot = document.getElementById('hd-dot');
        var statusEl = document.getElementById('hd-status');
        if (!dot || !statusEl) return;
        dot.className = 'dot ' + (st.serverStatus === 'running' ? 'green pulse' :
            st.serverStatus === 'starting' ? 'amber pulse' :
                st.serverStatus === 'error' ? 'red' : 'off');
        statusEl.textContent = (st.serverStatus || 'offline').toUpperCase();

        var toolsEl = document.getElementById('hd-tools');
        if (toolsEl) {
            toolsEl.textContent = (st.toolCounts ? st.toolCounts.enabled || 0 : 0) +
                ' / ' + (st.toolCounts ? st.toolCounts.total || 134 : 134) + ' TOOLS';
        }
        var portEl = document.getElementById('hd-port');
        var displayPort = window.location.port || st.port || '----';
        if (portEl) portEl.textContent = ':' + displayPort;
        updateMcpConfigBlock(displayPort);

        if (st.uptime > 0) {
            var s = Math.floor(st.uptime / 1000);
            var h = Math.floor(s / 3600);
            var m = Math.floor((s % 3600) / 60);
            var sec = s % 60;
            var uptimeEl = document.getElementById('hd-uptime');
            if (uptimeEl) {
                uptimeEl.textContent =
                    String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
            }
        }
    }

    // ── MCP CONFIG BLOCK ──
    var _serverPort = window.location.port || 7866;
    var _isRemoteSpace = /\.hf\.space$/i.test(window.location.hostname || '');
    var _spaceOrigin = window.location.origin; // e.g. https://tostido-champion-council.hf.space
    var _autoApprove = [
        "get_onboarding","get_cached","get_status","bag_catalog","get_capabilities",
        "bag_search","plug_model","list_slots","workflow_test","bag_get","workflow_list",
        "list_models","embed_text","bag_put","hub_search","hub_search_datasets","compare",
        "file_read","file_write","file_edit","file_append","file_prepend","file_delete","file_rename","file_copy","file_list","file_tree","file_search","file_info","file_checkpoint","file_versions","file_diff","file_restore",
        "invoke_slot","rerank","deliberate","batch_embed","workflow_create","workflow_execute",
        "cascade_graph","cascade_chain","cascade_record","cascade_system","cascade_data",
        "cascade_instrument","cascade_proxy"
    ];
    function _buildEntry(url) {
        return {
            disabled: false,
            disabledTools: [],
            url: url,
            auth: 'bearer',
            bearerTokenEnv: 'HF_TOKEN',
            exposeResources: false,
            autoApprove: _autoApprove
        };
    }
    function updateMcpConfigBlock(port) {
        _serverPort = port || _serverPort;
        var fullEl = document.getElementById('mcp-config-block');
        var entryEl = document.getElementById('mcp-entry-block');

        // Always route through the panel backend MCP proxy so activity,
        // diagnostics, and instrumentation stay unified.
        var proxyUrl = _spaceOrigin + '/mcp/sse';
        var serverName = _isRemoteSpace ? 'champion-ouroboros-space' : 'champion-ouroboros-self-deploy';
        var entry = _buildEntry(proxyUrl);

        if (fullEl) {
            var wrapper = { mcpServers: {} };
            wrapper.mcpServers[serverName] = entry;
            fullEl.textContent = JSON.stringify(wrapper, null, 2);
        }
        if (entryEl) {
            entryEl.textContent = '"' + serverName + '": ' + JSON.stringify(entry, null, 2);
        }
    }
    function _copyEl(elId, toastId) {
        var el = document.getElementById(elId);
        if (!el) return;
        var ta = document.createElement('textarea');
        ta.value = el.textContent;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        var toast = document.getElementById(toastId);
        if (toast) {
            toast.classList.add('show');
            setTimeout(function () { toast.classList.remove('show'); }, 1500);
        }
    }

    function mpToast(message, kind, timeoutMs) {
        var toast = document.getElementById('mp-toast');
        if (!toast) return;
        var type = kind || 'info';
        toast.classList.remove('success', 'error', 'info', 'show');
        toast.classList.add(type);
        toast.textContent = message || '';
        // restart CSS transition if another toast was visible
        void toast.offsetWidth;
        toast.classList.add('show');
        clearTimeout(mpToast._timer);
        mpToast._timer = setTimeout(function () {
            toast.classList.remove('show');
        }, timeoutMs || 2400);
    }
    var copyConfigBtn = document.getElementById('copy-mcp-config');
    if (copyConfigBtn) copyConfigBtn.addEventListener('click', function () { _copyEl('mcp-config-block', 'config-copy-toast'); });
    var configBlock = document.getElementById('mcp-config-block');
    if (configBlock) configBlock.addEventListener('click', function () { _copyEl('mcp-config-block', 'config-copy-toast'); });
    var copyEntryBtn = document.getElementById('copy-mcp-entry');
    if (copyEntryBtn) copyEntryBtn.addEventListener('click', function () { _copyEl('mcp-entry-block', 'config-entry-toast'); });
    var entryBlock = document.getElementById('mcp-entry-block');
    if (entryBlock) entryBlock.addEventListener('click', function () { _copyEl('mcp-entry-block', 'config-entry-toast'); });

    // ── OVERVIEW META ──
    function updateOverviewMeta(data) {
        if (!data) return;
        try {
            // MCP tool results come as { content: [{ type: "text", text: "..." }] }
            var d = data;
            if (d.content && Array.isArray(d.content) && d.content[0] && d.content[0].text) {
                d = JSON.parse(d.content[0].text);
            } else if (typeof d === 'string') {
                d = JSON.parse(d);
            }
            if (d.generation) document.getElementById('ov-gen').textContent = d.generation;
            if (d.fitness) document.getElementById('ov-fitness').textContent = Number(d.fitness).toFixed(4);
            if (d.brain_type) document.getElementById('ov-brain').textContent = d.brain_type;
            var _h = d.capsule_hash || d.quine_hash; if (_h) document.getElementById('ov-hash').textContent = _h;
        } catch (err) {
            console.error('[Webview] updateOverviewMeta error:', err);
        }
    }

    // ── CATEGORY BARS ──
    function updateCatBars(categories) {
        if (!categories) return;
        var container = document.getElementById('cat-bars');
        if (!container) return;
        container.innerHTML = '';
        var entries = Object.entries(CATEGORIES);
        for (var i = 0; i < entries.length; i++) {
            var name = entries[i][0];
            var info = entries[i][1];
            var enabled = categories[name] !== false;
            var count = info.tools.length;
            var row = document.createElement('div');
            row.className = 'cat-bar-row';
            row.innerHTML =
                '<div class="cat-bar-label">' + name + '</div>' +
                '<div class="cat-bar-track"><div class="cat-bar-fill ' + (enabled ? '' : 'disabled') +
                '" style="width:' + (count / 13 * 100) + '%"></div></div>' +
                '<div class="cat-bar-count">' + count + '</div>';
            container.appendChild(row);
        }
    }

    function _formatCount(n) {
        if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
        if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
        return String(n);
    }

    function _isDefaultSlotName(name) {
        var v = String(name || '').trim().toLowerCase();
        return /^slot[_\-\s]?\d+$/.test(v) || v === 'empty' || v === 'vacant';
    }

    function _getSlotVisualState(slot) {
        var rawStatus = String(slot && slot.status ? slot.status : '').trim().toLowerCase();
        var hasModel = !!(slot && (slot.model_id || slot.model || slot.model_name || slot.model_source || slot._model_source));
        var hasNamedTarget = !!(slot && slot.name) && !_isDefaultSlotName(slot.name);

        if (rawStatus === 'loading' || rawStatus === 'plugging' || rawStatus === 'initializing' || rawStatus === 'starting' || rawStatus === 'pending') {
            return 'plugging';
        }
        if (hasModel || rawStatus === 'ready' || rawStatus === 'plugged' || rawStatus === 'occupied' || rawStatus === 'active' || rawStatus === 'online' || rawStatus === 'running') {
            return 'plugged';
        }
        if (hasNamedTarget && slot.plugged !== false) {
            return 'plugging';
        }
        return 'empty';
    }

    function _slotSupportsAgentChat(slot) {
        if (!slot || _getSlotVisualState(slot) !== 'plugged') return false;
        var mt = String(slot.model_type || slot.type || '').toLowerCase();
        if (!mt) return true;
        if (mt.indexOf('embed') >= 0) return false;
        if (mt.indexOf('class') >= 0) return false;
        if (mt.indexOf('rerank') >= 0) return false;
        return true;
    }

    function _normalizeSlotsArrayPayload(raw) {
        var d = raw;
        // Prefer explicit slots array (postprocessed shape)
        if (d && Array.isArray(d.slots)) return d.slots;
        // Already array
        if (Array.isArray(d)) return d;

        // Compact list_slots shape from external MCP calls:
        // { total, all_ids:[slot_0,...], ... }
        if (d && typeof d === 'object' && !Array.isArray(d)) {
            var total = parseInt(d.total, 10);
            var ids = Array.isArray(d.all_ids) ? d.all_ids : [];
            if (!(total >= 0) && ids.length) total = ids.length;
            if (total >= 0) {
                var out = [];
                for (var i = 0; i < total; i++) {
                    var name = ids[i] || ('slot_' + i);
                    var isDefault = _isDefaultSlotName(name);
                    out.push({
                        slot: i,
                        name: name,
                        // Compact payloads do not reliably encode per-slot plug state.
                        // Keep conservative defaults and let explicit slots[] refresh win.
                        plugged: false,
                        status: 'empty',
                        model_source: null,
                        model_type: null,
                        type: null
                    });
                }
                return out;
            }
        }

        return [];
    }


    // ── SLOTS RENDER ──
    function renderSlots(data) {
        var grid = document.getElementById('slots-grid');
        if (!grid) return;
        grid.innerHTML = '';
        var slotsArr = [];
        try {
            var d = data;
            if (d && d.content && Array.isArray(d.content) && d.content[0] && d.content[0].text) {
                d = JSON.parse(d.content[0].text);
            } else if (typeof d === 'string') {
                d = JSON.parse(d);
            }
            slotsArr = _normalizeSlotsArrayPayload(d);
        } catch (err) { slotsArr = []; }

        // Clear unplugging state for slots that are now confirmed empty
        var unpKeys = Object.keys(_unpluggingSlots);
        var now_unp = Date.now();
        for (var uk = 0; uk < unpKeys.length; uk++) {
            var ui = parseInt(unpKeys[uk]);
            var us = slotsArr[ui];
            var unpInfo = _unpluggingSlots[unpKeys[uk]];
            var unpStale = unpInfo && (now_unp - unpInfo.startTime) > 120000;
            if (!us || _getSlotVisualState(us) === 'empty' || unpStale) {
                delete _unpluggingSlots[unpKeys[uk]];
            }
        }

        // ── PHANTOM PLUGGING FIX ──
        // 1) Staleness timeout: clear plugging entries older than 120s
        var now = Date.now();
        var staleKeys = Object.keys(_pluggingSlots);
        for (var sk = 0; sk < staleKeys.length; sk++) {
            var sInfo = _pluggingSlots[staleKeys[sk]];
            if (sInfo && (now - sInfo.startTime) > 120000) {
                delete _pluggingSlots[staleKeys[sk]];
            }
        }
        // 2) Reconcile: if backend reports a slot as plugged with a model,
        //    clear any plugging entry whose modelId matches that slot's model
        for (var ri = 0; ri < slotsArr.length; ri++) {
            var rs = slotsArr[ri];
            if (!rs) continue;
            var rState = _getSlotVisualState(rs);
            if (rState !== 'plugged') continue;
            var rModel = rs.model_source || rs.model_id || rs.model || rs.model_name || '';
            if (!rModel) continue;
            var rpKeys = Object.keys(_pluggingSlots);
            for (var rk = 0; rk < rpKeys.length; rk++) {
                var rpInfo = _pluggingSlots[rpKeys[rk]];
                if (rpInfo && rpInfo.modelId === rModel) {
                    delete _pluggingSlots[rpKeys[rk]];
                }
            }
        }
        // 3) Reconcile: if backend confirms a slot is empty at an index that
        //    has a _pluggingSlots entry, clear it immediately — handles plug+unplug cycle
        for (var ei = 0; ei < slotsArr.length; ei++) {
            var es = slotsArr[ei];
            if (!es || es.plugged !== false) continue;
            var epKeys = Object.keys(_pluggingSlots);
            for (var ek = 0; ek < epKeys.length; ek++) {
                var epInfo = _pluggingSlots[epKeys[ek]];
                if (epInfo && epInfo.slotIndex === ei) {
                    delete _pluggingSlots[epKeys[ek]];
                }
            }
        }

        var slotCount = slotsArr.length;
        var gridTitle = document.getElementById('council-grid-title');
        if (slotCount > 0) {
            _lastSlotsData = data;
            _lastGoodSlotsData = data;
            _lastGoodSlotsTs = Date.now();
            gridTitle && (gridTitle.textContent = slotCount + '-SLOT COUNCIL GRID');
        } else {
            // Transient errors/disconnects can yield empty payloads.
            // Keep the last good council grid instead of wiping all slots.
            if (_lastGoodSlotsData) {
                _scheduleSlotRefresh('empty-payload', 1200);
                return;
            }
            gridTitle && (gridTitle.textContent = 'COUNCIL GRID — awaiting capsule...');
            return; // Don't render empty placeholder slots
        }

        // Build a lookup of which slots are currently being plugged
        var pluggingBySlot = {};
        var plugKeys = Object.keys(_pluggingSlots);
        for (var pk = 0; pk < plugKeys.length; pk++) {
            var pInfo = _pluggingSlots[plugKeys[pk]];
            // Match by slot name or assign to first empty slot
            if (pInfo.slotIndex !== undefined) {
                pluggingBySlot[pInfo.slotIndex] = pInfo;
            } else if (pInfo.slotName) {
                // Find slot by name match
                for (var si = 0; si < slotsArr.length; si++) {
                    var sn = slotsArr[si];
                    if (sn && (sn.name === pInfo.slotName || sn.slot_name === pInfo.slotName)) {
                        pluggingBySlot[si] = pInfo;
                        break;
                    }
                }
                // If no name match, assign to first empty
                if (!pluggingBySlot[Object.keys(pluggingBySlot).length]) {
                    for (var si2 = 0; si2 < slotsArr.length; si2++) {
                        if (!pluggingBySlot[si2] && _getSlotVisualState(slotsArr[si2] || {}) === 'empty') {
                            pluggingBySlot[si2] = pInfo;
                            break;
                        }
                    }
                }
            } else {
                // No slot name — assign to first empty slot not already claimed
                for (var si3 = 0; si3 < slotsArr.length; si3++) {
                    if (!pluggingBySlot[si3] && _getSlotVisualState(slotsArr[si3] || {}) === 'empty') {
                        pluggingBySlot[si3] = pInfo;
                        break;
                    }
                }
            }
        }

        for (var i = 0; i < slotCount; i++) {
            var slot = slotsArr[i] || {};
            var state = _getSlotVisualState(slot);
            var isActivelyPlugging = !!pluggingBySlot[i];
            var isActivelyUnplugging = !!_unpluggingSlots[i];
            var occupied = state === 'plugged' && !isActivelyUnplugging;
            var plugging = state === 'plugging' || isActivelyPlugging;
            var unplugging = isActivelyUnplugging;
            var statusText = unplugging ? 'UNPLUGGING' : (occupied ? 'PLUGGED' : (plugging ? 'PLUGGING' : 'EMPTY'));
            var dotClass = unplugging ? 'amber pulse' : (occupied ? 'green' : (plugging ? 'amber pulse' : 'off'));
            var detailText = (occupied || plugging)
                ? (slot.model_type || slot.type || (slot.status ? ('status: ' + String(slot.status).toUpperCase()) : '--'))
                : '--';
            var card = document.createElement('div');
            card.className = 'slot-card state-' + (unplugging ? 'plugging' : state) + (occupied ? ' occupied' : '') + (plugging ? ' plugging' : '') + (unplugging ? ' plugging' : '');

            var html = '<div class="slot-num">' + (i + 1) + '</div>' +
                '<div class="slot-status-line">' +
                '<span class="dot ' + dotClass + '"></span> ' +
                '<span class="slot-status-badge ' + state + '">' + statusText + '</span>' +
                '</div>';

            if (isActivelyPlugging) {
                var pInfo = pluggingBySlot[i];
                var elapsed = Math.round((Date.now() - pInfo.startTime) / 1000);
                html += '<div class="slot-model-name" style="color:var(--amber)">' + escHtml(pInfo.modelId) + '</div>';
                var phaseText = pInfo.phase ? escHtml(pInfo.phase.substring(0, 60)) : 'Loading...';
                html += '<div class="slot-detail">' + phaseText + ' (' + elapsed + 's)</div>';
                html += '<div class="plug-bar"><div class="plug-bar-fill"></div></div>';
            } else {
                var modelLabel = (occupied || plugging)
                    ? (slot.model_source || slot.model_id || slot.name || 'VACANT')
                    : 'VACANT';
                html += '<div class="slot-model-name">' + escHtml(modelLabel) + '</div>';
                html += '<div class="slot-detail">' + detailText + '</div>';

                // Rich metadata card from hub_info cache
                var hubKey = slot.model_source || slot.model_id;
                var hubMeta = hubKey ? _slotHubInfoCache[hubKey] : null;
                if (hubMeta && occupied) {
                    html += '<div class="slot-meta-card">';
                    if (hubMeta.author) html += '<span class="meta-tag">by ' + escHtml(hubMeta.author) + '</span>';
                    if (hubMeta.task) html += '<span class="meta-tag">' + escHtml(hubMeta.task) + '</span>';
                    if (hubMeta.license && hubMeta.license !== 'unknown') html += '<span class="meta-tag">' + escHtml(hubMeta.license) + '</span>';
                    if (hubMeta.downloads) html += '<span class="meta-tag">' + _formatCount(hubMeta.downloads) + ' DL</span>';
                    if (hubMeta.likes) html += '<span class="meta-tag">' + _formatCount(hubMeta.likes) + ' likes</span>';
                    if (hubMeta.size_mb && hubMeta.size_mb > 0) html += '<span class="meta-tag">' + hubMeta.size_mb.toFixed(0) + ' MB</span>';
                    html += '</div>';
                }
            }

            if (occupied) {
                html += '<div class="slot-actions">';
                html += '<button class="btn-dim btn-chat" data-action="chat" data-slot="' + i + '">' + (_slotSupportsAgentChat(slot) ? 'AGENT' : 'CONSOLE') + '</button>';
                html += '<button class="btn-dim" data-action="unplug" data-slot="' + i + '">UNPLUG</button>';
                html += '<button class="btn-dim" data-action="invoke" data-slot="' + i + '">INVOKE</button>';
                html += '<button class="btn-dim" data-action="clone" data-slot="' + i + '">CLONE</button>';
                html += '</div>';
            }
            card.innerHTML = html;
            grid.appendChild(card);
        }

        // Fetch hub_info for plugged slots missing cached metadata
        for (var fi = 0; fi < slotsArr.length; fi++) {
            var fs = slotsArr[fi] || {};
            var fSrc = fs.model_source || fs.model_id;
            if (fSrc && _getSlotVisualState(fs) === 'plugged' && !_slotHubInfoCache[fSrc] && _slotHubInfoCache[fSrc] !== false) {
                _slotHubInfoCache[fSrc] = false; // mark as fetching to prevent duplicate calls
                (function (src) {
                    callTool('hub_info', { model_id: src }, 'hub_info_enrich');
                })(fSrc);
            }
        }

        // Event delegation for slot buttons
        if (!grid.dataset.actionsBound) {
            grid.addEventListener('click', function (e) {
                var btn = e.target.closest('[data-action]');
                if (btn) {
                    e.stopPropagation();
                    var action = btn.dataset.action;
                    var slot = parseInt(btn.dataset.slot);
                    if (action === 'chat') {
                        openAgentChat(slot);
                    }
                    else if (action === 'unplug') {
                        _unpluggingSlots[slot] = { startTime: Date.now() };
                        if (_lastSlotsData) renderSlots(_lastSlotsData);
                        callTool('unplug_slot', { slot: slot });
                    }
                    else if (action === 'invoke') callTool('invoke_slot', { slot: slot, text: 'test' });
                    else if (action === 'clone') callTool('clone_slot', { slot: slot });
                    return;
                }
                // Click on slot card itself (not a button) → drill-in
                var card = e.target.closest('.slot-card.occupied');
                if (card) {
                    var slotNum = card.querySelector('.slot-num');
                    if (slotNum) {
                        var idx = parseInt(slotNum.textContent) - 1;
                        if (idx >= 0) openSlotDrill(idx);
                    }
                }
            });
            grid.dataset.actionsBound = '1';
        }
    }

    // ── PLUG LOADING UI ──
    var _plugTimer = null;
    var _lastSlotsData = null; // latest slots payload (usually last good)
    var _lastGoodSlotsData = null; // sticky good payload to survive transient disconnects
    var _lastGoodSlotsTs = 0;
    var _slotRefreshTimer = null;
    var _slotWatchdogTimer = null;

    function _scheduleSlotRefresh(reason, delayMs) {
        if (_slotRefreshTimer) return;
        var ms = (typeof delayMs === 'number' && delayMs >= 0) ? delayMs : 220;
        _slotRefreshTimer = setTimeout(function () {
            _slotRefreshTimer = null;
            callTool('list_slots', {}, '__slot_watchdog__');
        }, ms);
    }

    function _startSlotWatchdog() {
        if (_slotWatchdogTimer) return;
        _slotWatchdogTimer = setInterval(function () {
            if (document.visibilityState === 'hidden') return;
            var titleEl = document.getElementById('council-grid-title');
            var awaiting = titleEl && String(titleEl.textContent || '').toLowerCase().indexOf('awaiting capsule') >= 0;
            var stale = !_lastGoodSlotsTs || (Date.now() - _lastGoodSlotsTs) > 20000;
            if (awaiting || stale) {
                _scheduleSlotRefresh(awaiting ? 'awaiting' : 'stale', awaiting ? 300 : 0);
            }
        }, 8000);
    }

    function _updatePluggingUI() {
        var keys = Object.keys(_pluggingSlots);
        if (keys.length === 0) {
            if (_plugTimer) { clearInterval(_plugTimer); _plugTimer = null; }
            return;
        }

        // Re-render slot grid to update elapsed timers on slot cards
        if (_lastSlotsData) {
            renderSlots(_lastSlotsData);
        }

        // Start timer to tick elapsed on slot cards
        if (!_plugTimer) {
            _plugTimer = setInterval(function () {
                if (Object.keys(_pluggingSlots).length === 0) {
                    clearInterval(_plugTimer); _plugTimer = null;
                    return;
                }
                _updatePluggingUI();
            }, 1000);
        }
    }

    // Clear a specific plugging entry by modelId, or all if no match
    function _clearPluggingEntry(modelId) {
        if (modelId) {
            var keys = Object.keys(_pluggingSlots);
            for (var k = 0; k < keys.length; k++) {
                var info = _pluggingSlots[keys[k]];
                if (info && info.modelId === modelId) {
                    delete _pluggingSlots[keys[k]];
                    _updatePluggingUI();
                    return;
                }
            }
        }
        // Fallback: clear all if no specific match
        _pluggingSlots = {};
        if (_plugTimer) { clearInterval(_plugTimer); _plugTimer = null; }
    }

    // Clear ALL plugging state (for bulk reset)
    function _clearPluggingState() {
        _pluggingSlots = {};
        if (_plugTimer) { clearInterval(_plugTimer); _plugTimer = null; }
    }

    // ══════════════════════════════════════════════════════════════
    // SLOT DRILL-IN — Operations Console for Plugged Models
    // ══════════════════════════════════════════════════════════════

    function _detectProvider(slot) {
        var src = String(slot.model_source || slot.model_id || slot.name || '').toLowerCase();
        if (src.indexOf('anthropic') >= 0 || src.indexOf('claude') >= 0) return 'anthropic';
        if (src.indexOf('openai') >= 0 || src.indexOf('gpt') >= 0 || src.indexOf('chatgpt') >= 0) return 'openai';
        if (src.indexOf('google') >= 0 || src.indexOf('gemini') >= 0) return 'google';
        if (src.indexOf('http://') >= 0 || src.indexOf('https://') >= 0) return 'remote';
        if (src.indexOf('/') >= 0) return 'huggingface';
        return 'local';
    }

    function _providerLabel(provider) {
        var map = { anthropic: 'ANTHROPIC', openai: 'OPENAI', google: 'GOOGLE', remote: 'REMOTE', huggingface: 'HUGGINGFACE', local: 'LOCAL' };
        return map[provider] || 'LOCAL';
    }

    function openSlotDrill(slotIndex) {
        _slotDrill.active = true;
        _slotDrill.slotIndex = slotIndex;
        _slotDrillActivity = [];
        var gridView = document.getElementById('council-grid-view');
        var drillView = document.getElementById('slot-drill-view');
        if (gridView) gridView.style.display = 'none';
        if (drillView) drillView.classList.add('active');
        renderSlotDrillDetail();
        // Populate activity from global log
        _populateSlotActivity(slotIndex);
    }

    function closeSlotDrill() {
        _slotDrill.active = false;
        _slotDrill.slotIndex = -1;
        var gridView = document.getElementById('council-grid-view');
        var drillView = document.getElementById('slot-drill-view');
        if (gridView) gridView.style.display = '';
        if (drillView) drillView.classList.remove('active');
    }

    function _getSlotData(index) {
        if (!_lastSlotsData) return null;
        var slotsArr = [];
        try {
            var d = _lastSlotsData;
            if (d && d.content && Array.isArray(d.content) && d.content[0] && d.content[0].text) {
                d = JSON.parse(d.content[0].text);
            } else if (typeof d === 'string') {
                d = JSON.parse(d);
            }
            slotsArr = _normalizeSlotsArrayPayload(d);
        } catch (e) { return null; }
        return slotsArr[index] || null;
    }

    function renderSlotDrillDetail() {
        var idx = _slotDrill.slotIndex;
        var slot = _getSlotData(idx);
        if (!slot) return;

        var provider = _detectProvider(slot);
        var modelLabel = slot.model_source || slot.model_id || slot.name || 'VACANT';
        var modelType = slot.model_type || slot.type || 'unknown';

        // Identity header
        var modelEl = document.getElementById('slot-drill-model');
        if (modelEl) modelEl.textContent = modelLabel;

        var metaEl = document.getElementById('slot-drill-meta');
        if (metaEl) {
            metaEl.innerHTML =
                '<span>SLOT ' + (idx + 1) + '</span>' +
                '<span>' + escHtml(modelType).toUpperCase() + '</span>' +
                '<span>' + escHtml(String(slot.status || 'ready')).toUpperCase() + '</span>';
        }

        var badgesEl = document.getElementById('slot-drill-badges');
        if (badgesEl) {
            badgesEl.innerHTML = '<span class="slot-drill-badge ' + provider + '">' + _providerLabel(provider) + '</span>';
        }

        // Metrics — request from evaluator
        _renderSlotMetrics(idx);

        // Action buttons
        var actionsEl = document.getElementById('slot-drill-actions');
        if (actionsEl) {
            actionsEl.innerHTML =
                '<button onclick="openAgentChat(' + idx + ')">AGENT</button>' +
                '<button onclick="callTool(\'invoke_slot\',{slot:' + idx + ',text:\'test\'})">INVOKE</button>' +
                '<button onclick="_slotDrillCompare(' + idx + ')">COMPARE</button>' +
                '<button onclick="_slotDrillBenchmark(' + idx + ')">BENCHMARK</button>' +
                '<button onclick="callTool(\'slot_info\',{slot:' + idx + '})">INFO</button>' +
                '<button class="btn-dim" onclick="_slotDrillUnplug(' + idx + ')">UNPLUG</button>';
        }
    }

    function _renderSlotMetrics(slotIndex) {
        var metricsEl = document.getElementById('slot-drill-metrics');
        if (!metricsEl) return;
        // Request evaluation data from extension-side evaluator
        vscode.postMessage({ command: 'requestSlotMetrics', slotIndex: slotIndex });
        // Render placeholder metrics — will be updated when eval data arrives
        var slot = _getSlotData(slotIndex);
        var hubKey = slot ? (slot.model_source || slot.model_id) : null;
        var hubMeta = hubKey ? _slotHubInfoCache[hubKey] : null;

        metricsEl.innerHTML =
            _metricCard('TOTAL CALLS', '—', '') +
            _metricCard('SUCCESS RATE', '—', '') +
            _metricCard('AVG LATENCY', '—', '') +
            _metricCard('P95 LATENCY', '—', '') +
            _metricCard('THROUGHPUT', '—', '') +
            _metricCard('CONSISTENCY', '—', '') +
            _metricCard('ERROR RATE', '—', '') +
            _metricCard('LAST ACTIVE', '—', '');

        // If we have hub metadata, show it
        if (hubMeta) {
            var extra = '';
            if (hubMeta.author) extra += _metricCard('AUTHOR', escHtml(hubMeta.author), '');
            if (hubMeta.downloads) extra += _metricCard('DOWNLOADS', _formatCount(hubMeta.downloads), '');
            if (hubMeta.likes) extra += _metricCard('LIKES', _formatCount(hubMeta.likes), '');
            if (hubMeta.size_mb && hubMeta.size_mb > 0) extra += _metricCard('SIZE', hubMeta.size_mb.toFixed(0) + ' MB', '');
            if (extra) metricsEl.innerHTML += extra;
        }
    }

    function _metricCard(label, value, cls) {
        return '<div class="slot-metric-card"><div class="slot-metric-label">' + label +
            '</div><div class="slot-metric-value ' + cls + '">' + value + '</div></div>';
    }

    function _updateSlotMetricsFromEval(evalData) {
        var metricsEl = document.getElementById('slot-drill-metrics');
        if (!metricsEl || !evalData) return;
        var m = evalData;
        var successCls = m.successRate >= 0.95 ? '' : (m.successRate >= 0.8 ? 'warn' : 'bad');
        var errorCls = m.errorRate <= 0.05 ? '' : (m.errorRate <= 0.2 ? 'warn' : 'bad');
        var latCls = m.avgLatencyMs <= 500 ? '' : (m.avgLatencyMs <= 2000 ? 'warn' : 'bad');
        var lastActive = m.lastActive ? new Date(m.lastActive).toLocaleTimeString() : '—';

        metricsEl.innerHTML =
            _metricCard('TOTAL CALLS', String(m.totalCalls || 0), '') +
            _metricCard('SUCCESS RATE', ((m.successRate || 0) * 100).toFixed(1) + '%', successCls) +
            _metricCard('AVG LATENCY', (m.avgLatencyMs || 0).toFixed(0) + 'ms', latCls) +
            _metricCard('P95 LATENCY', (m.p95LatencyMs || 0).toFixed(0) + 'ms', '') +
            _metricCard('THROUGHPUT', (m.throughput || 0).toFixed(1) + '/min', '') +
            _metricCard('CONSISTENCY', ((m.consistencyScore || 0) * 100).toFixed(0) + '%', '') +
            _metricCard('ERROR RATE', ((m.errorRate || 0) * 100).toFixed(1) + '%', errorCls) +
            _metricCard('LAST ACTIVE', lastActive, '');
    }

    function _populateSlotActivity(slotIndex) {
        _slotDrillActivity = [];
        var slotTools = ['invoke_slot', 'generate', 'classify', 'rerank', 'embed_text',
            'forward', 'infer', 'deliberate', 'imagine', 'compare', 'debate', 'chain', 'all_slots'];
        for (var i = 0; i < _activityLog.length; i++) {
            var e = _activityLog[i];
            if (!e) continue;
            // Match events that target this specific slot
            var targetSlot = e.args && (e.args.slot !== undefined ? e.args.slot : -1);
            var isSlotSpecific = targetSlot === slotIndex;
            var isBroadcast = slotTools.indexOf(e.tool) >= 0 && targetSlot === -1;
            if (isSlotSpecific || isBroadcast) {
                _slotDrillActivity.push(e);
            }
        }
        _renderSlotActivityFeed();
    }

    function _renderSlotActivityFeed() {
        var listEl = document.getElementById('slot-drill-activity-list');
        var countEl = document.getElementById('slot-drill-activity-count');
        if (!listEl) return;
        if (countEl) countEl.textContent = _slotDrillActivity.length + ' events';

        if (_slotDrillActivity.length === 0) {
            listEl.innerHTML = '<div class="slot-activity-item" style="color:var(--text-dim);">No activity recorded for this slot yet.</div>';
            return;
        }

        var html = '';
        var items = _slotDrillActivity.slice(-30).reverse();
        for (var i = 0; i < items.length; i++) {
            var e = items[i];
            var ts = new Date(e.timestamp).toLocaleTimeString();
            var source = e.source || 'mcp';
            var srcCls = source === 'workflow' ? 'workflow' : 'mcp';
            var preview = '';
            if (e.args) {
                preview = e.args.text || e.args.prompt || e.args.input_text || '';
                if (preview.length > 60) preview = preview.substring(0, 60) + '...';
            }
            var latency = e.durationMs >= 0 ? (e.durationMs + 'ms') : '';
            var statusCls = e.error ? 'fail' : 'ok';
            var statusText = e.error ? '✗' : '✓';

            html += '<div class="slot-activity-item">' +
                '<span class="slot-activity-source ' + srcCls + '">' + escHtml(source) + '</span>' +
                '<span class="slot-activity-tool">' + escHtml(e.tool || '') + '</span>' +
                '<span class="slot-activity-preview">' + escHtml(preview) + '</span>' +
                '<span class="slot-activity-latency">' + latency + '</span>' +
                '<span class="slot-activity-status ' + statusCls + '">' + statusText + '</span>' +
                '<span style="color:var(--text-dim);font-size:9px;">' + ts + '</span>' +
                '</div>';
        }
        listEl.innerHTML = html;
    }
    function _slotDrillCompare(slotIndex) {
        // Find another plugged slot to compare against
        var slotsArr = [];
        try {
            var d = _lastSlotsData;
            if (d && d.content && Array.isArray(d.content) && d.content[0] && d.content[0].text) d = JSON.parse(d.content[0].text);
            else if (typeof d === 'string') d = JSON.parse(d);
            slotsArr = d.slots || d || [];
        } catch (e) { return; }
        var others = [];
        for (var i = 0; i < slotsArr.length; i++) {
            if (i !== slotIndex && _getSlotVisualState(slotsArr[i] || {}) === 'plugged') others.push(i);
        }
        if (others.length === 0) { mpToast('No other plugged slots to compare against', 'info', 2500); return; }
        callTool('compare', { input_text: 'Explain the concept of emergence in complex systems.', slots: [slotIndex, others[0]] });
    }

    function _slotDrillBenchmark(slotIndex) {
        var prompts = [
            'What is 2+2?',
            'Explain quantum entanglement in one sentence.',
            'Write a Python function to reverse a string.'
        ];
        for (var i = 0; i < prompts.length; i++) {
            callTool('invoke_slot', { slot: slotIndex, text: prompts[i] });
        }
        mpToast('Benchmark: ' + prompts.length + ' prompts sent to slot ' + (slotIndex + 1), 'info', 2500);
    }

    function _slotDrillUnplug(slotIndex) {
        _unpluggingSlots[slotIndex] = { startTime: Date.now() };
        callTool('unplug_slot', { slot: slotIndex });
        closeSlotDrill();
        mpToast('Unplugging slot ' + (slotIndex + 1) + '...', 'info', 2500);
    }

    // ── PLUG PROVIDER MODAL ──
    var _providerBrowseTimer = null;
    var _providerBrowseSeq = 0;
    var _providerMetaTimer = null;
    var _providerMetaSeq = 0;

    function _providerKind() {
        var kind = ((document.getElementById('plug-provider-kind') || {}).value || 'huggingface').toLowerCase();
        if (kind !== 'huggingface' && kind !== 'openai') kind = 'huggingface';
        return kind;
    }

    function _setProviderStatus(text, tone) {
        var el = document.getElementById('plug-provider-hf-status');
        if (!el) return;
        el.textContent = String(text || '');
        el.style.color = (tone === 'error') ? '#f87171' : (tone === 'ok' ? '#34d399' : 'var(--text-dim)');
    }

    function _setProviderModelMeta(text, tone) {
        var el = document.getElementById('plug-provider-model-meta');
        if (!el) return;
        el.textContent = String(text || '');
        el.style.color = (tone === 'error') ? '#f87171' : (tone === 'ok' ? '#34d399' : 'var(--text-dim)');
    }

    function _inferParamHint(modelId) {
        var s = String(modelId || '');
        var m = s.match(/(?:^|[^0-9])(\d+(?:\.\d+)?)\s*([bmk])(?:[^a-z0-9]|$)/i);
        if (!m) return '';
        return (m[1] + m[2]).toUpperCase();
    }

    function _formatModelSizeGb(sizeMb) {
        var mb = Number(sizeMb || 0);
        if (!(mb > 0)) return '';
        if (mb >= 1024) return (mb / 1024).toFixed(1).replace(/\.0$/, '') + ' GB';
        return Math.round(mb) + ' MB';
    }

    async function _refreshProviderModelMeta() {
        if (_providerKind() !== 'huggingface') {
            _setProviderModelMeta('Select a model to see basic metadata.', 'info');
            return;
        }

        var model = String(((document.getElementById('plug-provider-model') || {}).value || '')).trim();
        if (!model || model.indexOf('/') < 1) {
            var hint = _inferParamHint(model);
            if (hint) _setProviderModelMeta('Parameter hint: ' + hint, 'info');
            else _setProviderModelMeta('Select a model to see basic metadata.', 'info');
            return;
        }

        var seq = ++_providerMetaSeq;
        _setProviderModelMeta('Loading model metadata…', 'info');

        try {
            var info = await callToolAwaitParsed('hub_info', { model_id: model }, '__provider_hf_meta__', { timeout: 45000 });
            if (seq !== _providerMetaSeq) return;

            if (!info || info.error) {
                _setProviderModelMeta('Metadata unavailable for ' + model, 'error');
                return;
            }

            var task = String(info.task || 'unknown');
            var downloads = Number(info.downloads || 0);
            var likes = Number(info.likes || 0);
            var size = _formatModelSizeGb(info.size_mb);
            var param = _inferParamHint(model);

            var bits = [];
            bits.push('Task: ' + task);
            if (param) bits.push('Params: ~' + param);
            if (size) bits.push('Size: ' + size);
            if (downloads > 0) bits.push('Downloads: ' + _formatCount(downloads));
            if (likes > 0) bits.push('Likes: ' + _formatCount(likes));

            _setProviderModelMeta(bits.join(' · '), 'ok');
        } catch (e) {
            if (seq !== _providerMetaSeq) return;
            _setProviderModelMeta('Metadata lookup failed: ' + String((e && e.message) || e), 'error');
        }
    }

    function _queueProviderModelMetaRefresh(delayMs) {
        if (_providerMetaTimer) clearTimeout(_providerMetaTimer);
        _providerMetaTimer = setTimeout(function () {
            _refreshProviderModelMeta();
        }, (typeof delayMs === 'number' ? delayMs : 260));
    }

    function _setProviderModeUI(kind) {
        var hfWrap = document.getElementById('plug-provider-hf-fields');
        var openaiWrap = document.getElementById('plug-provider-openai-fields');
        var urlInput = document.getElementById('plug-provider-url');
        if (hfWrap) hfWrap.style.display = (kind === 'huggingface') ? '' : 'none';
        if (openaiWrap) openaiWrap.style.display = (kind === 'openai') ? '' : 'none';
        if (urlInput) {
            if (kind === 'openai') urlInput.setAttribute('required', 'required');
            else urlInput.removeAttribute('required');
        }
        if (kind === 'huggingface') {
            _setProviderStatus('Type to search models…', 'info');
            onProviderHfInput();
            _queueProviderModelMetaRefresh(120);
        } else {
            _setProviderModelMeta('Remote endpoint mode. Metadata preview is available for HuggingFace IDs.', 'info');
        }
    }

    function onProviderKindChange() {
        _setProviderModeUI(_providerKind());
    }

    async function _fetchHfModelsDirect(query, token, provider) {
        var q = String(query || '').trim();
        var p = String(provider || 'auto').trim().toLowerCase();
        var url = 'https://huggingface.co/api/models?limit=40&sort=downloads&direction=-1';
        if (q) url += '&search=' + encodeURIComponent(q);
        if (p && p !== 'auto') url += '&inference_provider=' + encodeURIComponent(p);

        var headers = { 'Accept': 'application/json' };
        if (token) headers['Authorization'] = 'Bearer ' + token;

        var resp = await fetch(url, { method: 'GET', headers: headers });
        if (!resp.ok) throw new Error('HF API HTTP ' + resp.status);
        var data = await resp.json();
        if (!Array.isArray(data)) return [];

        var out = [];
        for (var i = 0; i < data.length; i++) {
            var m = data[i] || {};
            var id = String(m.id || '').trim();
            if (!id) continue;
            out.push({
                id: id,
                downloads: Number(m.downloads || 0),
                likes: Number(m.likes || 0),
                task: String(m.pipeline_tag || ''),
                private: !!m.private
            });
        }
        return out;
    }

    async function _fetchHfModelsViaTools(query) {
        var q = String(query || '').trim();
        var payload = null;
        if (q) payload = await callToolAwaitParsed('hub_search', { query: q, limit: 40, page: 1 }, '__provider_hf_lookup__', { timeout: 45000 });
        else payload = await callToolAwaitParsed('hub_top', { limit: 40, page: 1 }, '__provider_hf_lookup__', { timeout: 45000 });

        var models = (payload && Array.isArray(payload.models)) ? payload.models : [];
        var out = [];
        for (var i = 0; i < models.length; i++) {
            var m = models[i] || {};
            var id = String(m.id || '').trim();
            if (!id) continue;
            out.push({
                id: id,
                downloads: Number(m.downloads || 0),
                likes: Number(m.likes || 0),
                task: String(m.task || ''),
                private: false
            });
        }
        return out;
    }

    function _renderHfModelOptions(models) {
        var sel = document.getElementById('plug-provider-hf-models');
        if (!sel) return;
        sel.innerHTML = '';

        if (!Array.isArray(models) || models.length === 0) {
            var empty = document.createElement('option');
            empty.value = '';
            empty.textContent = 'No models found';
            sel.appendChild(empty);
            return;
        }

        for (var i = 0; i < models.length; i++) {
            var m = models[i] || {};
            var opt = document.createElement('option');
            opt.value = String(m.id || '');
            var badges = [];
            var paramHint = _inferParamHint(opt.value);
            if (m.task) badges.push(m.task);
            if (paramHint) badges.push('~' + paramHint);
            if (m.downloads > 0) badges.push(_formatCount(m.downloads) + ' dl');
            if (m.likes > 0) badges.push(_formatCount(m.likes) + ' ❤');
            if (m.private) badges.push('private');
            opt.textContent = badges.length ? (opt.value + '   ·   ' + badges.join(' · ')) : opt.value;
            sel.appendChild(opt);
        }
    }

    async function _refreshHfProviderModels() {
        if (_providerKind() !== 'huggingface') return;

        var queryEl = document.getElementById('plug-provider-hf-query');
        var tokenEl = document.getElementById('plug-provider-hf-token');
        var providerEl = document.getElementById('plug-provider-hf-provider');
        var modelEl = document.getElementById('plug-provider-model');

        var query = String((queryEl && queryEl.value) || '').trim();
        var token = String((tokenEl && tokenEl.value) || '').trim();
        var provider = String((providerEl && providerEl.value) || 'auto').trim().toLowerCase();
        if (!query) query = String((modelEl && modelEl.value) || '').trim();
        var seq = ++_providerBrowseSeq;

        _setProviderStatus('Loading models…', 'info');

        var models = [];
        var source = 'huggingface-api';
        var directErr = null;

        try {
            models = await _fetchHfModelsDirect(query, token, provider);
        } catch (e) {
            directErr = e;
            source = 'hub-tools';
            try {
                models = await _fetchHfModelsViaTools(query);
            } catch (e2) {
                if (seq !== _providerBrowseSeq) return;
                _renderHfModelOptions([]);
                _setProviderStatus('Model lookup failed: ' + String((e2 && e2.message) || (directErr && directErr.message) || e2 || directErr), 'error');
                return;
            }
        }

        if (seq !== _providerBrowseSeq) return;

        _renderHfModelOptions(models);

        var sel = document.getElementById('plug-provider-hf-models');
        if (sel && modelEl) {
            var current = String((modelEl.value || '')).trim();
            if (current) {
                for (var idx = 0; idx < sel.options.length; idx++) {
                    if (String(sel.options[idx].value || '') === current) {
                        sel.selectedIndex = idx;
                        break;
                    }
                }
            }
        }

        var providerLabel = (provider && provider !== 'auto') ? ('provider=' + provider + ', ') : '';
        var msg = 'Loaded ' + String(models.length) + ' model' + (models.length === 1 ? '' : 's') + ' via ' + providerLabel + source + '.';
        if (!token) msg += ' (Tip: add HF token for private repos.)';
        _setProviderStatus(msg, models.length ? 'ok' : 'info');
        _queueProviderModelMetaRefresh(120);
    }

    function onProviderHfInput() {
        if (_providerKind() !== 'huggingface') return;
        if (_providerBrowseTimer) clearTimeout(_providerBrowseTimer);
        _providerBrowseTimer = setTimeout(function () {
            _refreshHfProviderModels();
        }, 300);
        _queueProviderModelMetaRefresh(220);
    }

    function onProviderModelPick() {
        var sel = document.getElementById('plug-provider-hf-models');
        var modelEl = document.getElementById('plug-provider-model');
        if (sel && modelEl && sel.value) modelEl.value = sel.value;
        _queueProviderModelMetaRefresh(60);
    }

    function openPlugProviderModal() {
        var modal = document.getElementById('plug-provider-modal');
        if (modal) modal.classList.add('active');
        _setProviderModelMeta('Select a model to see basic metadata.', 'info');
        _setProviderModeUI(_providerKind());
    }

    function _capsuleLoopbackBase() {
        var host = String((window.location && window.location.hostname) || '').toLowerCase();
        var portRaw = String((window.location && window.location.port) || '').trim();

        // On HF Spaces, capsule runs behind local FastAPI on 7860.
        if (_isRemoteSpace || /\.hf\.space$/i.test(host)) {
            return 'http://127.0.0.1:7860';
        }

        // Self-deploy/local panel: reuse current bound app port when available.
        var p = parseInt(portRaw, 10);
        if (p >= 1 && p <= 65535) {
            return 'http://127.0.0.1:' + p;
        }

        // Conservative self-deploy default.
        return 'http://127.0.0.1:7866';
    }

    function _rewriteHfRouterToLoopback(urlLike) {
        var raw = String(urlLike || '').trim();
        if (!raw) return raw;
        try {
            var parsed = new URL(raw, window.location.origin || undefined);
            var path = String(parsed.pathname || '');
            if (/^\/hf-router(\/|$)/.test(path)) {
                return _capsuleLoopbackBase() + path + (parsed.search || '');
            }
            if (/\.hf\.space$/i.test(String(parsed.hostname || '')) && /^\/hf-router(\/|$)/.test(path)) {
                return _capsuleLoopbackBase() + path + (parsed.search || '');
            }
        } catch (e) { }
        return raw;
    }

    async function doPlugProvider() {
        var kind = _providerKind();
        var model = String(((document.getElementById('plug-provider-model') || {}).value || '')).trim();
        var slotName = (document.getElementById('plug-provider-slot-name') || {}).value || '';

        if (kind === 'huggingface') {
            if (!model) {
                mpToast('Select or enter a HuggingFace model ID first', 'error', 2600);
                return;
            }

            var provider = String(((document.getElementById('plug-provider-hf-provider') || {}).value || 'auto')).trim().toLowerCase();
            var providerPath = provider && provider !== 'auto' ? ('/hf-router/' + encodeURIComponent(provider) + '/v1') : '/hf-router/v1';
            var routerUrl = _capsuleLoopbackBase() + providerPath + '?model=' + encodeURIComponent(model);

            var hfArgs = { model_id: routerUrl };
            if (slotName) hfArgs.slot_name = slotName;
            callTool('plug_model', hfArgs);
            closeModals();
            mpToast('Plugging HuggingFace inference provider route (loopback)...', 'info', 2800);
            return;
        }

        var url = (document.getElementById('plug-provider-url') || {}).value || '';
        var key = (document.getElementById('plug-provider-key') || {}).value || '';
        if (!url) { mpToast('Provider URL is required', 'error', 2500); return; }

        // Build URL payload for RemoteProviderProxy via existing plug_model flow.
        var fullUrl = url;
        var params = [];
        if (model) params.push('model=' + encodeURIComponent(model));
        if (key) params.push('key=' + encodeURIComponent(key));
        if (params.length > 0) fullUrl += (fullUrl.indexOf('?') >= 0 ? '&' : '?') + params.join('&');

        // If user pasted an hf.space /hf-router URL, rewrite to capsule-reachable loopback.
        fullUrl = _rewriteHfRouterToLoopback(fullUrl);

        var args = { model_id: fullUrl };
        if (slotName) args.slot_name = slotName;

        callTool('plug_model', args);
        closeModals();
        mpToast('Plugging remote provider...', 'info', 2500);
    }

    // Expose to global scope for onclick hooks from panel.html
    window.onProviderKindChange = onProviderKindChange;
    window.onProviderHfInput = onProviderHfInput;
    window.onProviderModelPick = onProviderModelPick;
    window.openPlugProviderModal = openPlugProviderModal;
    window.doPlugProvider = doPlugProvider;
    window._slotDrillCompare = _slotDrillCompare;
    window._slotDrillBenchmark = _slotDrillBenchmark;
    window._slotDrillUnplug = _slotDrillUnplug;

    // ── ACTIVITY FEED ──
    var PLUG_TOOLS = ['plug_model', 'hub_plug'];
    var EXTERNAL_SLOT_MUTATION_TOOLS = ['plug_model', 'hub_plug', 'unplug_slot', 'clone_slot', 'rename_slot', 'swap_slots', 'cull_slot', 'restore_slot'];
    var ACTIVITY_SILENT_TOOLS = ['get_status', 'list_slots', 'bag_catalog', 'workflow_list', 'verify_integrity', 'get_cached', 'get_identity', 'feed', 'get_capabilities', 'get_help', 'get_onboarding', 'get_quickstart', 'hub_tasks', 'list_tools', 'heartbeat', 'api_health'];

    function _scheduleExternalSlotRefresh(reason) {
        _scheduleSlotRefresh(reason || 'external-mutation', 220);
    }

    function _unwrapMcpEnvelope(raw) {
        var node = raw;
        if (typeof node === 'string') {
            var parsedNode = _safeJsonParse(node);
            if (parsedNode !== null) node = parsedNode;
        }
        if (node && typeof node === 'object' && node.result && typeof node.result === 'object') {
            node = node.result;
        }

        var isError = !!(node && (node.isError || node.is_error));
        var payload = node;

        if (node && typeof node === 'object' && Array.isArray(node.content)) {
            var inner = null;
            if (node.structuredContent && node.structuredContent.result !== undefined) {
                inner = node.structuredContent.result;
            } else if (node.content[0] && typeof node.content[0].text === 'string') {
                inner = node.content[0].text;
            }
            if (inner !== null && inner !== undefined) {
                if (typeof inner === 'string') {
                    var parsedInner = _safeJsonParse(inner);
                    payload = parsedInner !== null ? parsedInner : inner;
                } else {
                    payload = inner;
                }
            }
        }

        return { payload: payload, isError: isError };
    }

    function _formatExternalResultForChat(toolName, rawResult) {
        var unwrapped = _unwrapMcpEnvelope(rawResult);
        var payload = unwrapped.payload;
        var isError = !!unwrapped.isError;

        if (toolName === 'invoke_slot' && payload && typeof payload === 'object' && payload.output !== undefined) {
            var out = payload.output;
            if (typeof out === 'string') {
                var parsedOut = _safeJsonParse(out);
                if (parsedOut !== null) out = parsedOut;
            }
            return { role: isError ? 'error' : 'assistant', text: _prettyTruncate(out, 4000), payload: payload, isError: isError };
        }

        if (toolName === 'agent_chat' && payload && typeof payload === 'object') {
            var r = (payload.result && typeof payload.result === 'object') ? payload.result : payload;
            var lines = [];
            if (r.final_answer) lines.push(String(r.final_answer));
            if (r.iterations !== undefined) lines.push('\n\nIterations: ' + String(r.iterations));
            if (Array.isArray(r.tool_calls) && r.tool_calls.length) lines.push('\nTool calls: ' + String(r.tool_calls.length));
            if (lines.length) {
                return { role: isError ? 'error' : 'assistant', text: lines.join(''), payload: payload, isError: isError };
            }
        }

        return { role: isError ? 'error' : 'assistant', text: _prettyTruncate(payload, 4000), payload: payload, isError: isError };
    }

    var _activityTraceCounts = {}; // trace/session id -> sequence count
    var _activityTraceGroupExpanded = {}; // trace/session id -> group expand/collapse state

    function _parseAgentSessionSlot(sessionId) {
        var sid = String(sessionId || '').trim();
        if (!sid) return -1;
        var parts = sid.split(':');
        if (parts.length >= 2) {
            var idx = parseInt(parts[1], 10);
            if (!isNaN(idx)) return idx;
        }
        return -1;
    }

    function _hash32(str) {
        var h = 2166136261 >>> 0;
        var s = String(str || '');
        for (var i = 0; i < s.length; i++) {
            h ^= s.charCodeAt(i);
            h = Math.imul(h, 16777619) >>> 0;
        }
        return h >>> 0;
    }

    function _extractResultSessionId(result) {
        if (!result || typeof result !== 'object') return '';
        if (typeof result.session_id === 'string' && result.session_id.trim()) return result.session_id.trim();
        if (result.result && typeof result.result === 'object') {
            var nested = _extractResultSessionId(result.result);
            if (nested) return nested;
        }
        if (result.content && Array.isArray(result.content) && result.content[0] && typeof result.content[0].text === 'string') {
            var parsed = _safeJsonParse(result.content[0].text);
            if (parsed && typeof parsed === 'object') {
                var fromText = _extractResultSessionId(parsed);
                if (fromText) return fromText;
            }
        }
        return '';
    }

    function _deriveActivityTrace(event) {
        if (!event || typeof event !== 'object') return null;
        var args = (event.args && typeof event.args === 'object') ? event.args : {};

        var sid = '';
        if (typeof args._trace_id === 'string' && args._trace_id.trim()) sid = args._trace_id.trim();
        else if (typeof args._agent_session === 'string' && args._agent_session.trim()) sid = args._agent_session.trim();
        else if (typeof args.session_id === 'string' && args.session_id.trim()) sid = args.session_id.trim();
        else sid = _extractResultSessionId(event.result);

        if (!sid) return null;

        var callerSlot = _parseAgentSessionSlot(sid);
        if (args._trace_caller_slot !== undefined && args._trace_caller_slot !== null && String(args._trace_caller_slot).trim() !== '') {
            var cslot = parseInt(args._trace_caller_slot, 10);
            if (!isNaN(cslot)) callerSlot = cslot;
        }
        var targetSlot = -1;
        if (args.slot !== undefined && args.slot !== null && String(args.slot).trim() !== '') {
            var t = parseInt(args.slot, 10);
            if (!isNaN(t)) targetSlot = t;
        }
        if (args._trace_target_slot !== undefined && args._trace_target_slot !== null && String(args._trace_target_slot).trim() !== '') {
            var t2 = parseInt(args._trace_target_slot, 10);
            if (!isNaN(t2)) targetSlot = t2;
        }

        var hue = _hash32(sid) % 360;
        var color = 'hsl(' + hue + ', 78%, 58%)';
        var role = 'session';
        if (typeof args._trace_role === 'string' && args._trace_role.trim()) role = args._trace_role.trim();
        else if (args._workflow_execution_id || sid.indexOf('workflow:') === 0) role = 'workflow';
        else if (callerSlot >= 0 && targetSlot >= 0 && callerSlot !== targetSlot) role = 'delegation';
        else if (event.tool === 'agent_chat') role = 'reasoning';

        return {
            id: sid,
            callerSlot: callerSlot,
            targetSlot: targetSlot,
            role: role,
            hue: hue,
            color: color,
        };
    }

    function _activitySignature(event) {
        if (!event || typeof event !== 'object') return '';
        var argsSig = '';
        try { argsSig = JSON.stringify(event.args || {}); } catch (e) { argsSig = String(event.args || ''); }
        var ts = event.timestamp !== undefined ? event.timestamp : (event.ts !== undefined ? event.ts : '');
        var eid = event.eventId !== undefined ? event.eventId : '';
        return [
            String(eid),
            String(event.tool || ''),
            String(event.source || ''),
            String(ts),
            String(event.durationMs !== undefined ? event.durationMs : ''),
            argsSig
        ].join('|');
    }

    function _rehydrateActivityLog(entries) {
        var incoming = Array.isArray(entries) ? entries.slice() : [];
        var prevBySig = {};
        for (var i = 0; i < _activityLog.length; i++) {
            var prev = _activityLog[i];
            var sigPrev = _activitySignature(prev);
            if (sigPrev) prevBySig[sigPrev] = prev;
        }

        var traceCounts = {};
        var next = [];

        for (var j = 0; j < incoming.length; j++) {
            var src = incoming[j];
            if (!src || typeof src !== 'object') continue;
            var ev = Object.assign({}, src);

            var prevMatch = prevBySig[_activitySignature(ev)];
            if (prevMatch && typeof prevMatch === 'object') {
                if (ev._trace_id === undefined && prevMatch._trace_id !== undefined) ev._trace_id = prevMatch._trace_id;
                if (ev._trace_seq === undefined && prevMatch._trace_seq !== undefined) ev._trace_seq = prevMatch._trace_seq;
                if (ev._trace_role === undefined && prevMatch._trace_role !== undefined) ev._trace_role = prevMatch._trace_role;
                if (ev._trace_hue === undefined && prevMatch._trace_hue !== undefined) ev._trace_hue = prevMatch._trace_hue;
                if (ev._trace_color === undefined && prevMatch._trace_color !== undefined) ev._trace_color = prevMatch._trace_color;
                if (ev._trace_caller_slot === undefined && prevMatch._trace_caller_slot !== undefined) ev._trace_caller_slot = prevMatch._trace_caller_slot;
                if (ev._trace_target_slot === undefined && prevMatch._trace_target_slot !== undefined) ev._trace_target_slot = prevMatch._trace_target_slot;
            }

            var trace = _deriveActivityTrace(ev);
            if (trace) {
                if (!ev._trace_id) ev._trace_id = trace.id;
                if (ev._trace_role === undefined) ev._trace_role = trace.role;
                if (ev._trace_hue === undefined) ev._trace_hue = trace.hue;
                if (ev._trace_color === undefined) ev._trace_color = trace.color;
                if (ev._trace_caller_slot === undefined) ev._trace_caller_slot = trace.callerSlot;
                if (ev._trace_target_slot === undefined) ev._trace_target_slot = trace.targetSlot;

                var tid = String(ev._trace_id || trace.id);
                var seq = parseInt(ev._trace_seq, 10);
                if (isNaN(seq) || seq <= 0) seq = (traceCounts[tid] || 0) + 1;
                ev._trace_seq = seq;
                traceCounts[tid] = Math.max(traceCounts[tid] || 0, seq);
            }

            next.push(ev);
        }

        _activityTraceCounts = traceCounts;
        _activityLog = next;
    }

    function addActivityEntry(event) {
        if (!event) return;

        // Reduce feed noise from background orchestration and polling.
        if (ACTIVITY_SILENT_TOOLS.indexOf(event.tool) >= 0 && event.source !== 'external' && event.source !== 'agent-inner') {
            return;
        }

        // Detect plug operations starting (durationMs === -1 sentinel)
        if (PLUG_TOOLS.indexOf(event.tool) >= 0 && event.durationMs === -1) {
            var modelId = (event.args && (event.args.model_id || event.args.summary)) || 'model';
            var slotName = (event.args && event.args.slot_name) || null;
            var slotKey = slotName || 'plug_' + Date.now();
            _pluggingSlots[slotKey] = { modelId: modelId, startTime: event.timestamp || Date.now(), slotName: slotName };
            _updatePluggingUI();
            return; // Don't add "started" sentinel to the activity log
        }

        // Live progress updates during plug (durationMs === -2 sentinel)
        if (event.tool === '_plug_progress' && event.durationMs === -2) {
            var keys = Object.keys(_pluggingSlots);
            if (keys.length > 0) {
                var info = _pluggingSlots[keys[0]];
                if (info && event.args) {
                    info.phase = event.args.progress || '';
                    if (event.args.model_id) info.modelId = event.args.model_id;
                }
                _updatePluggingUI();
            }
            return; // Don't add progress ticks to activity log
        }

        // Detect plug operations completing — clear only the specific entry
        if (PLUG_TOOLS.indexOf(event.tool) >= 0 && event.durationMs >= 0) {
            var completedModelId = (event.args && (event.args.model_id || event.args.summary)) || null;
            _clearPluggingEntry(completedModelId);
            // For external MCP calls there is no local toolResult callback,
            // so force a list_slots refresh to keep grid/drill/chat parity.
            if (event.source === 'external' && !event.error) {
                _scheduleExternalSlotRefresh('external-plug-complete');
            }
        }

        var trace = _deriveActivityTrace(event);
        if (trace) {
            var nextSeq = (_activityTraceCounts[trace.id] || 0) + 1;
            _activityTraceCounts[trace.id] = nextSeq;
            event._trace_id = trace.id;
            event._trace_seq = nextSeq;
            event._trace_role = trace.role;
            event._trace_hue = trace.hue;
            event._trace_color = trace.color;
            event._trace_caller_slot = trace.callerSlot;
            event._trace_target_slot = trace.targetSlot;
        }

        _activityLog.push(event);
        if (event.tool === 'workflow_execute' || event.tool === 'workflow_status') {
            handleWorkflowActivity(event);
        }

        // External slot mutations must force council-grid re-hydration.
        if (event.source === 'external' && !event.error && EXTERNAL_SLOT_MUTATION_TOOLS.indexOf(event.tool) >= 0 && event.durationMs >= 0) {
            _scheduleExternalSlotRefresh('external-slot-mutation');
        }

        // If an external caller asks for list_slots, hydrate grid from that event too.
        if (event.source === 'external' && event.tool === 'list_slots' && event.result) {
            renderSlots(event.result);
        }

        // Echo to slot drill-in activity feed if open
        if (_slotDrill.active) {
            var targetSlot = event.args && (event.args.slot !== undefined ? event.args.slot : -1);
            var ownerSession = event.args && (event.args._agent_session || event.args.session_id || '');
            var ownerSlot = _parseAgentSessionSlot(ownerSession);
            if (ownerSlot < 0 && event._trace_caller_slot !== undefined) ownerSlot = parseInt(event._trace_caller_slot, 10);
            if (targetSlot === _slotDrill.slotIndex || ownerSlot === _slotDrill.slotIndex || targetSlot === -1) {
                _slotDrillActivity.push(event);
                _renderSlotActivityFeed();
            }
        }
        // ── EXTERNAL → SLOT CHAT TIMELINE BRIDGE ──
        // When external MCP clients (like Claude/Pi) call tools targeting a
        // specific slot, inject those into the slot's chat timeline so the
        // operator sees full parity between manual and external operations.
        if (event.source === 'external') {
            var extSlot = event.args && event.args.slot !== undefined ? event.args.slot : -1;
            var slotTools = ['invoke_slot', 'agent_chat', 'chat', 'generate', 'classify'];
            if (extSlot >= 0 && slotTools.indexOf(event.tool) >= 0) {
                // Ensure tab exists; tab keys are slot:<index>
                var slotTab = _ensureAchatTab(extSlot);
                if (slotTab) {
                    var isStartPhase = !!(event.result && typeof event.result === 'object' && event.result._phase === 'start');

                    // Dedupe occasional duplicate external events from mirrored channels.
                    var _extSig = [
                        String(event.tool || ''),
                        isStartPhase ? 'start' : 'end',
                        String(event.timestamp || ''),
                        String(event.durationMs || ''),
                        event.args ? JSON.stringify(event.args) : ''
                    ].join('|');
                    if (slotTab._lastExternalSig === _extSig) {
                        return;
                    }
                    slotTab._lastExternalSig = _extSig;

                    if (isStartPhase) {
                        // Add request args once when call starts.
                        var argPreview = event.args ? _prettyTruncate(event.args, 600) : '';
                        _appendAchatMsg(
                            'tool-trace',
                            '⟵ EXTERNAL ' + event.tool + (argPreview ? ':\n' + argPreview : ''),
                            event.timestamp ? new Date(event.timestamp).getTime() : Date.now(),
                            slotTab
                        );
                        _appendAchatMsg('tool-trace', '⟵ EXTERNAL ' + event.tool + ' started…', Date.now(), slotTab);
                    } else {
                        // Add the result / error (unwrap MCP envelopes for readability)
                        if (event.error) {
                            _appendAchatMsg('error', 'EXTERNAL error: ' + String(event.error), Date.now(), slotTab);
                        } else if (event.result !== undefined) {
                            var formatted = _formatExternalResultForChat(event.tool, event.result);
                            if (formatted && formatted.text) {
                                _appendAchatMsg(formatted.role || 'assistant', formatted.text, Date.now(), slotTab);
                            }

                            // For agent_chat, preserve strict chronological order:
                            // tool cards are rendered live from agent-inner events.
                            // Keep end-of-call blob only as fallback when no live steps arrived.
                            var payload = formatted ? formatted.payload : null;
                            var tc = null;
                            if (payload && payload.tool_calls && Array.isArray(payload.tool_calls)) tc = payload.tool_calls;
                            else if (payload && payload.result && payload.result.tool_calls && Array.isArray(payload.result.tool_calls)) tc = payload.result.tool_calls;

                            var _sessionId = '';
                            if (payload && payload.session_id) _sessionId = String(payload.session_id);
                            else if (payload && payload.result && payload.result.session_id) _sessionId = String(payload.result.session_id);

                            var _liveCount = 0;
                            if (_sessionId && slotTab._sseBySession && slotTab._sseBySession[_sessionId]) {
                                _liveCount = parseInt(slotTab._sseBySession[_sessionId], 10) || 0;
                            } else {
                                _liveCount = parseInt(slotTab._sseToolCount || 0, 10) || 0;
                            }
                            var _hasLiveOrderedTrace = (event.tool === 'agent_chat' && _liveCount > 0);

                            if (tc && tc.length && !_hasLiveOrderedTrace) {
                                _appendAchatToolTrace(tc, slotTab);
                            }
                        }

                        var dur = event.durationMs >= 0 ? ' (' + event.durationMs + 'ms)' : '';
                        _appendAchatMsg('tool-trace', '⟵ EXTERNAL ' + event.tool + ' complete' + dur, Date.now(), slotTab);
                    }
                }
            }
        }
        // ── AGENT-INNER → LIVE CHAT TIMELINE BRIDGE ──
        // Progressive rendering: server-side orchestrator broadcasts each step
        // in real time via SSE. Mirror delegated slot calls so both caller and
        // callee tabs stay in chronological parity.
        if (event.source === 'agent-inner' && event.tool) {
            var innerSession = (event.args && event.args._agent_session) || (event.args && event.args.session_id) || '';
            var callerSlot = _parseAgentSessionSlot(innerSession);
            if (callerSlot < 0 && event._trace_caller_slot !== undefined) callerSlot = parseInt(event._trace_caller_slot, 10);

            var rawTargetSlot = (event.args && event.args.slot !== undefined) ? event.args.slot : -1;
            var targetSlotNum = parseInt(rawTargetSlot, 10);
            if (isNaN(targetSlotNum)) targetSlotNum = -1;

            var slotScopedTools = ['invoke_slot', 'agent_chat', 'chat', 'generate', 'classify'];
            var mirrorToTarget = (targetSlotNum >= 0 && slotScopedTools.indexOf(event.tool) >= 0 && targetSlotNum !== callerSlot);

            var routedTabs = [];
            var _addRoutedTab = function(slotIdx, role) {
                if (!(slotIdx >= 0)) return;
                for (var rt = 0; rt < routedTabs.length; rt++) {
                    if (routedTabs[rt].slot === slotIdx) return;
                }
                var tabObj = _ensureAchatTab(slotIdx);
                if (tabObj) routedTabs.push({ slot: slotIdx, role: role, tab: tabObj });
            };

            _addRoutedTab(callerSlot, 'caller');
            if (mirrorToTarget) _addRoutedTab(targetSlotNum, 'target');
            if (!routedTabs.length) {
                var fallbackTab = _getActiveAchatTab();
                if (fallbackTab) routedTabs.push({ slot: fallbackTab.slot, role: 'fallback', tab: fallbackTab });
            }

            var isStart = !!(event.result && typeof event.result === 'object' && event.result._phase === 'start');
            var isReasoning = !!(event.args && event.args._phase === 'reasoning');

            // Clean args for display: strip internal tracking fields
            var _cleanArgs = function(a) {
                if (!a || typeof a !== 'object') return a;
                var c = {};
                for (var k in a) { if (k.charAt(0) !== '_') c[k] = a[k]; }
                return c;
            };

            var _eventSig = [
                String(event.tool || ''),
                isStart ? 'start' : 'end',
                String(event.timestamp || ''),
                String(event.durationMs || ''),
                innerSession,
                event.args ? JSON.stringify(event.args) : ''
            ].join('|');

            for (var rrIdx = 0; rrIdx < routedTabs.length; rrIdx++) {
                var routed = routedTabs[rrIdx];
                var innerTab = routed.tab;
                if (!innerTab) continue;

                // Dedupe occasional mirrored/replayed SSE events per tab.
                var _tabSig = routed.role + '|' + _eventSig;
                if (innerTab._lastInnerSig === _tabSig) continue;
                innerTab._lastInnerSig = _tabSig;

                if (!innerTab._sseToolCount) innerTab._sseToolCount = 0;

                var flowPrefix = '';
                if (routed.role === 'target' && callerSlot >= 0) {
                    flowPrefix = '↳ S' + (callerSlot + 1) + ' delegated · ';
                } else if (routed.role === 'caller' && mirrorToTarget) {
                    flowPrefix = '↦ S' + (targetSlotNum + 1) + ' · ';
                }

                if (isReasoning) {
                    var iterNum = (event.args && event.args.iteration) || '?';
                    var rObj = (typeof event.result === 'object' && event.result !== null && !event.result.content)
                        ? event.result : {};
                    if (!rObj.iteration && event.result && event.result.content) {
                        try { rObj = JSON.parse(event.result.content[0].text); } catch (e2) { }
                    }
                    if (rObj.iteration) iterNum = rObj.iteration;
                    var stepMs = rObj.step_ms ? ' ' + rObj.step_ms + 'ms' : '';
                    var preview = String(rObj.model_output_preview || '').substring(0, 200);
                    if (preview) {
                        _appendAchatMsg('system-info', '🧠 ' + flowPrefix + 'Step ' + iterNum + stepMs + ' — ' + preview, Date.now(), innerTab);
                    } else {
                        _appendAchatMsg('system-info', '🧠 ' + flowPrefix + 'Step ' + iterNum + stepMs + ' — thinking…', Date.now(), innerTab);
                    }
                } else if (isStart && event.tool !== 'agent_chat') {
                    var argStr = '';
                    try { argStr = JSON.stringify(_cleanArgs(event.args) || {}).substring(0, 250); } catch (e3) { }
                    _appendAchatMsg('tool-trace', flowPrefix + '🔧 ' + event.tool + ' ' + argStr, Date.now(), innerTab);
                } else if (!isStart && event.tool !== 'agent_chat') {
                    innerTab._sseToolCount = (innerTab._sseToolCount || 0) + 1;
                    var _sess = (event.args && event.args._agent_session) || '';
                    if (_sess) {
                        if (!innerTab._sseBySession) innerTab._sseBySession = {};
                        innerTab._sseBySession[_sess] = (innerTab._sseBySession[_sess] || 0) + 1;
                    }

                    // Render a full tool card NOW (in-order), not as an end-of-run blob.
                    var tcLive = {
                        tool: event.tool,
                        args: _cleanArgs(event.args) || {},
                        iteration: (event.args && event.args._agent_iteration !== undefined)
                            ? event.args._agent_iteration
                            : ((event.args && event.args.iteration !== undefined) ? event.args.iteration : undefined),
                        durationMs: event.durationMs || 0,
                        caller_slot: callerSlot,
                        target_slot: targetSlotNum,
                        trace_id: event._trace_id || innerSession || ''
                    };

                    if (event.error) {
                        tcLive.error = String(event.error);
                    } else {
                        try {
                            var rr = event.result;
                            if (rr && rr.content && Array.isArray(rr.content) && rr.content[0]) {
                                var txt = String(rr.content[0].text || '');
                                var parsed = _safeJsonParse(txt);
                                tcLive.result = parsed !== null ? parsed : txt;
                            } else {
                                tcLive.result = rr;
                            }
                        } catch (e4) {
                            tcLive.result = '(ok)';
                        }
                    }

                    _appendAchatToolTrace([tcLive], innerTab);
                }
            }
        }

        // Append new entry to DOM without destroying expanded entries
        var feed = document.getElementById('activity-feed');
        if (feed) {
            var filterActive = !!_getActivityFilterText();
            if (filterActive || _activityPage !== 0) {
                _renderActivityPager();
            } else {
                // Remove "No activity yet" placeholder if present
                var placeholder = feed.querySelector('.activity-entry[style*="text-align:center"]');
                if (placeholder) placeholder.remove();
                var node = _buildActivityNode(event);
                if (node) feed.insertBefore(node, feed.firstChild);
                while (feed.children.length > ACTIVITY_PAGE_SIZE) feed.removeChild(feed.lastChild);
                _renderActivityPager();
            }
        }
    }

    function _actEsc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

    function _unwrapActivityResult(resultObj) {
        var out = (resultObj === undefined ? null : resultObj);
        if (out && typeof out === 'object' && out.content && Array.isArray(out.content)) {
            var innerText = null;
            if (out.structuredContent && out.structuredContent.result) {
                innerText = out.structuredContent.result;
            } else if (out.content[0] && out.content[0].text) {
                innerText = out.content[0].text;
            }
            if (innerText) {
                try { out = JSON.parse(innerText); }
                catch (err) { out = innerText; }
            }
        }
        return out;
    }

    function _activityTokenShort(value, maxLen) {
        var s = String(value === null || value === undefined ? '' : value);
        s = _decodeDocKey(s).replace(/\s+/g, ' ').trim();
        if (!maxLen || s.length <= maxLen) return s;
        return s.slice(0, Math.max(4, maxLen - 1)) + '…';
    }

    function _activitySlotLabel(slotVal) {
        var n = parseInt(slotVal, 10);
        if (isNaN(n) || n < 0) return '';
        return 'S' + (n + 1);
    }

    function _activityMetaBullets(e, resultObj, hasError) {
        var out = [];
        var args = (e && e.args && typeof e.args === 'object') ? e.args : {};

        if (e && e._trace_seq !== undefined) out.push('seq #' + String(e._trace_seq));
        if (e && e._trace_role) out.push('flow ' + String(e._trace_role));

        var slotLabel = _activitySlotLabel(args.slot);
        if (slotLabel) out.push('slot ' + slotLabel);

        if (args.session_id) out.push('session ' + _activityTokenShort(args.session_id, 18));
        if (args.workflow_id) out.push('workflow ' + _activityTokenShort(args.workflow_id, 26));
        if (!args.workflow_id && args._workflow_id) out.push('workflow ' + _activityTokenShort(args._workflow_id, 26));
        if (args._workflow_execution_id) out.push('exec ' + _activityTokenShort(args._workflow_execution_id, 18));
        if (args._workflow_node_id) out.push('node ' + _activityTokenShort(args._workflow_node_id, 20));
        if (args._workflow_target_id) out.push('target ' + _activityTokenShort(args._workflow_target_id, 20));
        if (args.model_id) out.push('model ' + _activityTokenShort(args.model_id, 32));
        if (args.path || args.key) out.push('target ' + _activityTokenShort(args.path || args.key, 42));

        if (resultObj && typeof resultObj === 'object' && !Array.isArray(resultObj)) {
            if (resultObj.status !== undefined) out.push('status ' + _activityTokenShort(resultObj.status, 18));
            if (resultObj.path || resultObj.key) out.push('stored ' + _activityTokenShort(resultObj.path || resultObj.key, 42));
            if (resultObj.version !== undefined) out.push('v' + String(resultObj.version));
            if (resultObj.count !== undefined) out.push('count ' + String(resultObj.count));
            if (resultObj.slots_filled !== undefined) out.push('slots ' + String(resultObj.slots_filled));
            if (resultObj.execution_id) out.push('exec ' + _activityTokenShort(resultObj.execution_id, 18));
            if (resultObj.checkpoint_key) out.push('checkpoint ' + _activityTokenShort(resultObj.checkpoint_key, 28));
            if (resultObj.error) out.push('error ' + _activityTokenShort(resultObj.error, 44));
        }

        if (hasError && e && e.error) {
            out.push('ERR ' + _activityTokenShort(String(e.error).split('\n')[0], 44));
        }

        var unique = [];
        var seen = {};
        for (var i = 0; i < out.length; i++) {
            var item = String(out[i] || '').trim();
            if (!item) continue;
            var key = item.toLowerCase();
            if (seen[key]) continue;
            seen[key] = true;
            unique.push(item);
            if (unique.length >= 10) break;
        }
        return unique;
    }

    function _activityMetaBannerHtml(items) {
        if (!items || !items.length) return '';
        var html = '<div class="activity-meta-banner">';
        for (var i = 0; i < items.length; i++) {
            html += '<span class="activity-meta-chip">• ' + _actEsc(items[i]) + '</span>';
        }
        html += '</div>';
        return html;
    }

    function _toggleTraceGroup(traceId) {
        if (!traceId) return;
        var feed = document.getElementById('activity-feed');
        if (!feed) return;
        var nodes = feed.querySelectorAll('.activity-entry[data-trace-id]');
        var matches = [];
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i].getAttribute('data-trace-id') === traceId) matches.push(nodes[i]);
        }
        if (!matches.length) return;

        var shouldExpand = false;
        for (var j = 0; j < matches.length; j++) {
            if (!matches[j].classList.contains('expanded')) {
                shouldExpand = true;
                break;
            }
        }

        for (var k = 0; k < matches.length; k++) {
            matches[k].classList.toggle('expanded', shouldExpand);
        }
        _activityTraceGroupExpanded[traceId] = shouldExpand;
    }

    function _buildActivityNode(e) {
        var ts = new Date(e.timestamp).toLocaleTimeString();
        var fullTs;
        try { fullTs = new Date(e.timestamp).toISOString(); }
        catch (err) { fullTs = String(e.timestamp || 'unknown'); }

        var hasError = !!e.error;
        var source = e.source || 'extension';

        var detailLines = [];
        detailLines.push('Timestamp');
        detailLines.push(fullTs);
        detailLines.push('');
        var clientId = e.clientId || '';

        detailLines.push('Source');
        detailLines.push(String(source) + (clientId ? ' (' + clientId + ')' : ''));
        detailLines.push('');
        detailLines.push('Category');
        detailLines.push(String(e.category || 'unknown'));
        detailLines.push('');
        detailLines.push('Duration');
        detailLines.push(String(e.durationMs || 0) + 'ms');
        detailLines.push('');

        var traceId = String(e._trace_id || '');
        if (traceId) {
            detailLines.push('Trace');
            var traceSummary = traceId;
            if (e._trace_seq !== undefined) traceSummary += ' #' + String(e._trace_seq);
            if (e._trace_caller_slot >= 0 && e._trace_target_slot >= 0 && e._trace_caller_slot !== e._trace_target_slot) {
                traceSummary += ' · S' + (e._trace_caller_slot + 1) + '→S' + (e._trace_target_slot + 1);
            } else if (e._trace_caller_slot >= 0) {
                traceSummary += ' · S' + (e._trace_caller_slot + 1);
            }
            if (e._trace_role) traceSummary += ' · ' + String(e._trace_role);
            detailLines.push(traceSummary);
            detailLines.push('');
        }

        if (hasError) {
            detailLines.push('Error');
            detailLines.push(String(e.error));
            detailLines.push('');
        }

        detailLines.push('Arguments');
        if (e.args && Object.keys(e.args).length > 0) {
            try { detailLines.push(JSON.stringify(e.args, null, 2)); }
            catch (err) { detailLines.push(String(e.args)); }
        } else {
            detailLines.push('None');
        }
        detailLines.push('');

        var resultObj = _unwrapActivityResult(e.result);

        var resultText = 'None';
        if (resultObj !== null && resultObj !== undefined) {
            if (typeof resultObj === 'object' && !Array.isArray(resultObj)) {
                var resultLines = [];
                for (var rk in resultObj) {
                    if (!Object.prototype.hasOwnProperty.call(resultObj, rk)) continue;
                    if (String(rk).startsWith('_')) continue;
                    var rv = resultObj[rk];
                    var rvStr = (rv === null || rv === undefined)
                        ? 'null'
                        : (typeof rv === 'object' ? JSON.stringify(rv, null, 2) : String(rv));
                    resultLines.push(String(rk) + ': ' + rvStr);
                }
                if (resultLines.length > 0) {
                    resultText = resultLines.join('\n');
                } else {
                    try { resultText = JSON.stringify(resultObj, null, 2); }
                    catch (err) { resultText = String(resultObj); }
                }
            } else {
                if (typeof resultObj === 'string') resultText = resultObj;
                else {
                    try { resultText = JSON.stringify(resultObj, null, 2); }
                    catch (err) { resultText = String(resultObj); }
                }
            }
        }

        detailLines.push('Result');
        detailLines.push(String(resultText).substring(0, 4000));
        var detailText = detailLines.join('\n');

        var sourceBadge = '';
        if (source === 'external') {
            var clientLabel = clientId ? clientId.toUpperCase() : 'EXTERNAL';
            var clientColor = clientId === 'pi-agent' ? '#a78bfa'
                : clientId === 'claude-code' ? '#f59e0b'
                : clientId === 'kiro' ? '#10b981'
                : clientId === 'cursor' ? '#3b82f6'
                : clientId === 'windsurf' ? '#06b6d4'
                : clientId === 'copilot' ? '#38bdf8'
                : clientId === 'chatgpt-action' ? '#6366f1'
                : clientId === 'mcp-client' ? '#14b8a6'
                : clientId === 'hf-authenticated' ? '#94a3b8'
                : clientId === 'python-client' ? '#f97316'
                : 'var(--blue)';
            sourceBadge = '<span class="activity-cat" style="border-color:' + clientColor + ';color:' + clientColor + ';">' + escHtml(clientLabel) + '</span>';
        }

        var traceBadge = '';
        var traceStrip = '<span class="activity-trace-toggle placeholder"></span>';
        if (e._trace_id) {
            var traceColor = String(e._trace_color || ('hsl(' + (parseInt(e._trace_hue || 180, 10) || 180) + ', 78%, 58%)'));
            var safeTraceColor = traceColor.replace(/["'<>]/g, '');
            var shortTrace = String(e._trace_id).split(':').slice(-1)[0] || String(e._trace_id).substring(0, 10);
            if (shortTrace.length > 10) shortTrace = shortTrace.substring(0, 10);
            var roleTag = e._trace_role ? (' · ' + String(e._trace_role)) : '';
            var seqTag = (e._trace_seq !== undefined) ? ('#' + String(e._trace_seq)) : '';
            traceBadge = '<span class="activity-cat" style="border-color:' + safeTraceColor + ';color:' + safeTraceColor + ';">TRACE ' + escHtml(seqTag + roleTag + ' ' + shortTrace).trim() + '</span>';
            traceStrip = '<button class="activity-trace-toggle" data-trace-id="' + _actEsc(String(e._trace_id)) + '" title="Toggle all entries in this trace" style="--trace-color:' + safeTraceColor + ';background:' + safeTraceColor + ';"></button>';
        }

        var metaBanner = _activityMetaBannerHtml(_activityMetaBullets(e, resultObj, hasError));

        var div = document.createElement('div');
        div.className = 'activity-entry';
        if (e._trace_id) {
            var traceColorEdge = String(e._trace_color || ('hsl(' + (parseInt(e._trace_hue || 180, 10) || 180) + ', 78%, 58%)')).replace(/["'<>]/g, '');
            div.style.borderLeft = '3px solid ' + traceColorEdge;
            div.style.paddingLeft = '8px';
            div.setAttribute('data-trace-id', String(e._trace_id));
            if (_activityTraceGroupExpanded[String(e._trace_id)] === true) {
                div.classList.add('expanded');
            }
        }

        div.onclick = function (evt) {
            if (evt && evt.target && evt.target.classList && evt.target.classList.contains('activity-trace-toggle')) return;
            var sel = window.getSelection();
            if (sel && sel.toString().length > 0) return;
            div.classList.toggle('expanded');
            if (e._trace_id && Object.prototype.hasOwnProperty.call(_activityTraceGroupExpanded, String(e._trace_id))) {
                // Manual row toggles break out of group lock to preserve per-entry control.
                delete _activityTraceGroupExpanded[String(e._trace_id)];
            }
        };

        div.innerHTML =
            '<div class="activity-head">' +
            traceStrip +
            '<div class="activity-head-main">' +
            '<span class="activity-ts">' + ts + '</span>' +
            '<span class="activity-tool">' + _actEsc(e.tool) + '</span>' +
            '<span class="activity-cat">' + _actEsc(e.category) + '</span>' +
            sourceBadge +
            traceBadge +
            (hasError ? '<span style="color:var(--red);font-weight:700;">ERR</span>' : '') +
            '</div>' +
            '<div class="activity-head-right">' +
            '<span class="activity-duration">' + (e.durationMs || 0) + 'ms</span>' +
            '<span class="activity-expand-hint">row: details · color: trace group</span>' +
            '</div>' +
            '</div>' +
            metaBanner +
            '<pre class="activity-detail">' + _normalizeNewlines(_actEsc(_decodeDocKey(detailText))) + '</pre>';

        var traceBtn = div.querySelector('.activity-trace-toggle');
        if (traceBtn && !(traceBtn.classList && traceBtn.classList.contains('placeholder'))) {
            traceBtn.addEventListener('click', function (evt) {
                if (evt) {
                    evt.preventDefault();
                    evt.stopPropagation();
                }
                var tid = this.getAttribute('data-trace-id') || '';
                if (tid) _toggleTraceGroup(tid);
            });
        }

        return div;
    }

    function _getActivityFilterText() {
        var filterEl = document.getElementById('activity-filter');
        return String(filterEl ? filterEl.value : '').trim().toLowerCase();
    }

    function _getFilteredActivityEntries(filterText) {
        var filter = String(filterText || '').toLowerCase();
        return filter
            ? _activityLog.filter(function (e) {
                return e.tool.toLowerCase().includes(filter) ||
                    e.category.toLowerCase().includes(filter) ||
                    String(e.source || '').toLowerCase().includes(filter);
            })
            : _activityLog;
    }

    function _ensureActivityPager() {
        var feed = document.getElementById('activity-feed');
        if (!feed || !feed.parentNode) return null;
        var pager = document.getElementById('activity-pager');
        if (pager) return pager;

        pager = document.createElement('div');
        pager.id = 'activity-pager';
        pager.style.cssText = 'display:flex;gap:8px;align-items:center;justify-content:space-between;margin:8px 0 10px 0;font-size:11px;color:var(--text-dim);';
        pager.innerHTML =
            '<div id="activity-page-stats">Rows 0-0 of 0</div>' +
            '<div style="display:flex;gap:6px;align-items:center;">' +
            '<button id="activity-page-latest" class="btn-dim">LATEST</button>' +
            '<button id="activity-page-newer" class="btn-dim">NEWER</button>' +
            '<button id="activity-page-older" class="btn-dim">OLDER</button>' +
            '</div>';
        feed.parentNode.insertBefore(pager, feed);

        var latestBtn = document.getElementById('activity-page-latest');
        var newerBtn = document.getElementById('activity-page-newer');
        var olderBtn = document.getElementById('activity-page-older');
        if (latestBtn) {
            latestBtn.addEventListener('click', function () {
                if (_activityPage === 0) return;
                _activityPage = 0;
                renderActivityFeed();
            });
        }
        if (newerBtn) {
            newerBtn.addEventListener('click', function () {
                if (_activityPage <= 0) return;
                _activityPage--;
                renderActivityFeed();
            });
        }
        if (olderBtn) {
            olderBtn.addEventListener('click', function () {
                _activityPage++;
                renderActivityFeed();
            });
        }
        return pager;
    }

    function _renderActivityPager(totalFiltered, startIdx, endIdx, totalPages, filterText) {
        _ensureActivityPager();
        var statsEl = document.getElementById('activity-page-stats');
        var latestBtn = document.getElementById('activity-page-latest');
        var newerBtn = document.getElementById('activity-page-newer');
        var olderBtn = document.getElementById('activity-page-older');

        var safeTotalPages = Math.max(1, totalPages || 1);
        if (_activityPage > safeTotalPages - 1) _activityPage = safeTotalPages - 1;
        if (_activityPage < 0) _activityPage = 0;

        if (statsEl) {
            var range = totalFiltered > 0 ? (String(startIdx + 1) + '-' + String(endIdx)) : '0-0';
            var base = 'Rows ' + range + ' of ' + String(totalFiltered) + ' · page ' + String(_activityPage + 1) + '/' + String(safeTotalPages);
            if (filterText) base += ' · total ' + String(_activityLog.length);
            statsEl.textContent = base;
        }
        if (latestBtn) latestBtn.disabled = (_activityPage === 0);
        if (newerBtn) newerBtn.disabled = (_activityPage === 0);
        if (olderBtn) olderBtn.disabled = (_activityPage >= safeTotalPages - 1 || totalFiltered === 0);
    }

    function renderActivityFeed() {
        var feed = document.getElementById('activity-feed');
        if (!feed) return;

        var filter = _getActivityFilterText();
        var filtered = _getFilteredActivityEntries(filter);
        var total = filtered.length;
        var totalPages = Math.max(1, Math.ceil(total / ACTIVITY_PAGE_SIZE));
        if (_activityPage > totalPages - 1) _activityPage = totalPages - 1;
        if (_activityPage < 0) _activityPage = 0;

        var endIdx = total - (_activityPage * ACTIVITY_PAGE_SIZE);
        if (endIdx < 0) endIdx = 0;
        var startIdx = Math.max(0, endIdx - ACTIVITY_PAGE_SIZE);
        var pageItems = filtered.slice(startIdx, endIdx).reverse();

        feed.innerHTML = '';
        if (pageItems.length === 0) {
            feed.innerHTML = '<div class="activity-entry" style="color:var(--text-dim);padding:20px;text-align:center;">No activity yet.</div>';
            _renderActivityPager(total, 0, 0, totalPages, filter);
            return;
        }

        for (var i = 0; i < pageItems.length; i++) {
            feed.appendChild(_buildActivityNode(pageItems[i]));
        }
        _renderActivityPager(total, startIdx, endIdx, totalPages, filter);
    }

    var activityFilterEl = document.getElementById('activity-filter');
    if (activityFilterEl) {
        activityFilterEl.addEventListener('input', function () {
            _activityPage = 0;
            renderActivityFeed();
        });
    }

    // ── TOOL CALL ──
    var _pendingTools = {}; // id -> tool name
    var _pendingToolTabs = {}; // id -> agent chat tab key
    var _pendingToolMeta = {}; // id -> meta options (promises, suppression)
    var _pendingDiagnostics = {}; // id -> diagnostic key

    function _stringifyArgValue(v) {
        if (typeof v === 'string') return v;
        try { return JSON.stringify(v); } catch (e) { return String(v); }
    }

    function _coerceSlotList(rawSlots) {
        if (!Array.isArray(rawSlots)) return { values: [], invalid: [] };
        var values = [];
        var invalid = [];
        var seen = {};
        for (var i = 0; i < rawSlots.length; i++) {
            var raw = rawSlots[i];
            var iv = parseInt(raw, 10);
            if (isNaN(iv) || iv < 0) {
                invalid.push(raw);
                continue;
            }
            if (!seen[iv]) {
                seen[iv] = true;
                values.push(iv);
            }
        }
        return { values: values, invalid: invalid };
    }

    function _isMissingRequiredArg(value) {
        return value === undefined || value === null || (typeof value === 'string' && value.trim() === '');
    }

    function _scanWorkflowPlaceholders(value, out) {
        if (!out) out = [];
        if (typeof value === 'string') {
            var found = value.match(/\$[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*/g) || [];
            for (var i = 0; i < found.length; i++) out.push(found[i]);
            return out;
        }
        if (Array.isArray(value)) {
            for (var j = 0; j < value.length; j++) _scanWorkflowPlaceholders(value[j], out);
            return out;
        }
        if (value && typeof value === 'object') {
            var keys = Object.keys(value);
            for (var k = 0; k < keys.length; k++) _scanWorkflowPlaceholders(value[keys[k]], out);
        }
        return out;
    }

    function _unsupportedWorkflowRefs(definition) {
        if (!definition || typeof definition !== 'object') return [];
        var refs = _scanWorkflowPlaceholders(definition, []);
        if (!refs.length) return [];
        var unique = [];
        var seen = {};
        for (var i = 0; i < refs.length; i++) {
            var token = String(refs[i] || '').trim();
            if (!token || seen[token]) continue;
            seen[token] = true;
            if (token === '$input' || token.indexOf('$input.') === 0) continue;
            unique.push(token);
        }
        return unique;
    }

    function _workflowToolPreflight(toolName, args) {
        var schema = _getAchatToolSchema(toolName);
        var required = (schema && Array.isArray(schema.required)) ? schema.required : [];
        for (var i = 0; i < required.length; i++) {
            var req = required[i];
            if (_isMissingRequiredArg(args ? args[req] : undefined)) {
                return 'Missing required field: ' + req;
            }
        }

        if ((toolName === 'workflow_create' || toolName === 'workflow_update') && args && typeof args.definition === 'string') {
            var def = _safeJsonParse(args.definition);
            if (!_isWorkflowDefinition(def)) {
                return 'Workflow definition must be valid JSON containing nodes[].';
            }
            var badRefs = _unsupportedWorkflowRefs(def);
            if (badRefs.length) {
                var shown = badRefs.slice(0, 4).join(', ');
                var more = badRefs.length > 4 ? (' +' + String(badRefs.length - 4) + ' more') : '';
                return 'Unsupported workflow placeholder refs: ' + shown + more + '. Use $input.* only.';
            }
        }
        if (toolName === 'workflow_execute' && args && typeof args.input_data === 'string' && args.input_data.trim()) {
            var inputObj = _safeJsonParse(args.input_data);
            if (inputObj === null || typeof inputObj !== 'object' || Array.isArray(inputObj)) {
                return 'Execution input must be a valid JSON object.';
            }
        }
        return '';
    }

    function _sanitizeToolArgs(name, args) {
        var out = {};
        if (args && typeof args === 'object' && !Array.isArray(args)) {
            var keys = Object.keys(args);
            for (var i = 0; i < keys.length; i++) out[keys[i]] = args[keys[i]];
        }

        var trimFields = [
            'key', 'path', 'old_path', 'new_path', 'source_path', 'dest_path',
            'prefix', 'from_checkpoint', 'to_checkpoint', 'checkpoint_key', 'file_type',
            'pattern', 'workflow_id', 'execution_id', 'query', 'tool_name'
        ];
        for (var t = 0; t < trimFields.length; t++) {
            var tf = trimFields[t];
            if (typeof out[tf] === 'string') out[tf] = out[tf].trim();
        }

        if (name === 'file_write') {
            if (out.content === null || out.content === undefined) out.content = '';
            if (typeof out.content !== 'string') out.content = _stringifyArgValue(out.content);
            if (typeof out.file_type !== 'string' || out.file_type.trim() === '') out.file_type = 'text';
            else out.file_type = out.file_type.trim();
        }

        if (name === 'bag_induct') {
            if (out.content !== undefined && out.content !== null && typeof out.content !== 'string') {
                out.content = _stringifyArgValue(out.content);
            }
            if (typeof out.item_type !== 'string' || out.item_type.trim() === '') out.item_type = 'text';
            else out.item_type = out.item_type.trim();
        }

        if (name === 'workflow_create' || name === 'workflow_update') {
            if (out.definition !== undefined && out.definition !== null && typeof out.definition !== 'string') {
                out.definition = _stringifyArgValue(out.definition);
            }
        }

        if (name === 'workflow_execute') {
            if (out.input_data !== undefined && out.input_data !== null && typeof out.input_data !== 'string') {
                out.input_data = _stringifyArgValue(out.input_data);
            }
        }

        if (name === 'compare' && Array.isArray(out.slots)) {
            var slotFix = _coerceSlotList(out.slots);
            if (slotFix.values.length) out.slots = slotFix.values;
            else delete out.slots;
            if (slotFix.invalid.length) {
                mpToast('compare.slots dropped invalid values: ' + slotFix.invalid.map(function (v) { return String(v); }).join(', '), 'info', 3200);
            }
        }

        if (name === 'file_list') {
            if (out.file_type === null || out.file_type === undefined || (typeof out.file_type === 'string' && out.file_type.trim() === '')) {
                delete out.file_type;
            }
        }

        // C4 fix: bag_catalog(filter_type="all") — strip so capsule returns unfiltered.
        if (name === 'bag_catalog') {
            var ft = (out.filter_type || '').toString().trim().toLowerCase();
            if (ft === 'all' || ft === '*' || ft === 'any' || ft === '') {
                delete out.filter_type;
            }
        }

        if (name === 'file_diff' || name === 'bag_diff') {
            if (out.to_checkpoint === null || out.to_checkpoint === undefined || (typeof out.to_checkpoint === 'string' && out.to_checkpoint.trim() === '')) {
                out.to_checkpoint = 'current';
            }
        }

        var outKeys = Object.keys(out);
        for (var j = 0; j < outKeys.length; j++) {
            var k = outKeys[j];
            if (out[k] === null || out[k] === undefined) delete out[k];
        }
        return out;
    }

    function callTool(name, args, routeAs, meta) {
        var id = ++_requestId;
        _pendingTools[id] = routeAs || name;
        if (meta) _pendingToolMeta[id] = meta;
        if (meta && meta.tabKey) _pendingToolTabs[id] = String(meta.tabKey);
        // Clear council output panel on new council operations for clean visual transitions
        if (COUNCIL_TOOLS.indexOf(name) >= 0 && name !== 'list_slots' && name !== 'agent_chat') {
            var councilOut = document.getElementById('council-output');
            if (councilOut) councilOut.innerHTML = '<pre style="white-space:pre-wrap;color:var(--text-dim);font-size:11px;">Running ' + name + '...</pre>';
        }
        var safeArgs = _sanitizeToolArgs(name, args || {});
        vscode.postMessage({ command: 'callTool', tool: name, args: safeArgs, id: id });
        return id;
    }

    var TOOL_AWAIT_TIMEOUT_MS = 60000; // 60s default timeout for awaited tool calls
    function callToolAwait(name, args, routeAs, meta) {
        return new Promise(function (resolve, reject) {
            var m = {};
            if (meta && typeof meta === 'object') {
                for (var k in meta) {
                    if (Object.prototype.hasOwnProperty.call(meta, k)) m[k] = meta[k];
                }
            }
            var settled = false;
            var timeoutMs = (m.timeout && typeof m.timeout === 'number') ? m.timeout : TOOL_AWAIT_TIMEOUT_MS;
            var timer = setTimeout(function () {
                if (settled) return;
                settled = true;
                // Clean up pending maps to prevent leak
                for (var pid in _pendingToolMeta) {
                    if (_pendingToolMeta[pid] && _pendingToolMeta[pid] === m) {
                        delete _pendingTools[pid];
                        delete _pendingToolTabs[pid];
                        delete _pendingToolMeta[pid];
                        break;
                    }
                }
                reject(new Error('Tool call "' + name + '" timed out after ' + (timeoutMs / 1000) + 's'));
            }, timeoutMs);
            m.resolve = function (v) { if (!settled) { settled = true; clearTimeout(timer); resolve(v); } };
            m.reject = function (e) { if (!settled) { settled = true; clearTimeout(timer); reject(e); } };
            m.suppressDefault = true;
            callTool(name, args, routeAs, m);
        });
    }

    function _normalizeToolPayload(data) {
        if (data == null) return null;
        if (typeof data === 'string') {
            var parsed = _safeJsonParse(data);
            return parsed === null ? data : parsed;
        }
        if (data && data.content && Array.isArray(data.content) && data.content[0] && typeof data.content[0].text === 'string') {
            var inner = _safeJsonParse(data.content[0].text);
            return inner === null ? data.content[0].text : inner;
        }
        return data;
    }

    async function callToolAwaitParsed(name, args, routeAs, meta) {
        var msg = await callToolAwait(name, args, routeAs, meta);
        if (msg && msg.error) throw new Error(String(msg.error));
        var payload = _normalizeToolPayload(parseToolData(msg ? msg.data : null));
        if (payload && payload._cached) {
            var cached = await callToolAwait('get_cached', { cache_id: payload._cached }, routeAs || '__internal_agent_loop__', meta);
            if (cached && cached.error) throw new Error(String(cached.error));
            payload = _normalizeToolPayload(parseToolData(cached ? cached.data : null));
        }
        return payload;
    }
    function runDiagnostic(diagKey) {
        var id = ++_requestId;
        _pendingDiagnostics[id] = diagKey;
        var diagOut = document.getElementById('diag-output');
        if (diagOut) {
            diagOut.innerHTML = '<div class="diag-shell"><div class="diag-empty">Running diagnostic: ' + _esc(diagKey) + ' ...</div></div>';
        }
        vscode.postMessage({ command: 'runDiagnostic', diagKey: diagKey, id: id });
    }

    function _diagBadge(label, tone) {
        var cls = 'diag-badge';
        if (tone === 'ok') cls += ' ok';
        else if (tone === 'warn') cls += ' warn';
        else if (tone === 'err') cls += ' err';
        return '<span class="' + cls + '">' + _esc(label) + '</span>';
    }

    function _diagPretty(value, maxLen) {
        var out = '';
        try {
            out = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
        } catch (e) {
            out = String(value);
        }
        if (typeof maxLen === 'number' && out.length > maxLen) {
            out = out.substring(0, maxLen) + '\n... [truncated]';
        }
        return _esc(out);
    }

    function _diagCompact(v) {
        if (v == null) return 'n/a';
        if (typeof v === 'boolean') return v ? 'true' : 'false';
        if (typeof v === 'number') return String(v);
        if (typeof v === 'string') return v.length > 80 ? (v.substring(0, 77) + '...') : v;
        if (Array.isArray(v)) {
            if (v.length === 0) return '[]';
            var flat = JSON.stringify(v);
            if (flat.length <= 80) return flat;
            return '[' + v.length + ' items]';
        }
        if (typeof v === 'object') {
            var flat2 = JSON.stringify(v);
            if (flat2.length <= 60) return flat2;
            return '{' + Object.keys(v).length + ' keys}';
        }
        return String(v);
    }

    var _DIAG_META_KEYS = { source: 1, note: 1, raw: 1, _cached: 1 };
    var _DIAG_MAX_DEPTH = 2;
    var _DIAG_MAX_ROWS = 40;

    function _diagKvs(resolved) {
        var rows = [];
        var overflow = 0;
        function push(key, val) {
            if (val == null || val === '') return;
            var baseKey = key.split('.')[0];
            if (_DIAG_META_KEYS[baseKey]) return;
            if (rows.length >= _DIAG_MAX_ROWS) { overflow++; return; }
            rows.push('<div class="diag-kv"><div class="diag-k">' + _esc(key.replace(/_/g, ' ')) + '</div><div class="diag-v">' + _esc(_diagCompact(val)) + '</div></div>');
        }

        function pushNested(prefix, obj, depth) {
            if (!obj || typeof obj !== 'object') return;
            var keys = Object.keys(obj);
            for (var i = 0; i < keys.length; i++) {
                var k = keys[i];
                var v = obj[k];
                var label = prefix ? (prefix + '.' + k) : k;
                if (v != null && typeof v === 'object' && !Array.isArray(v) && depth < _DIAG_MAX_DEPTH) {
                    pushNested(label, v, depth + 1);
                } else {
                    push(label, v);
                }
            }
        }

        if (resolved && typeof resolved === 'object' && !Array.isArray(resolved)) {
            pushNested('', resolved, 0);
        } else if (typeof resolved === 'string' && resolved.length > 0) {
            rows.push('<div class="diag-kv" style="grid-column:1/-1;"><div class="diag-v">' + _esc(resolved.length > 300 ? (resolved.substring(0, 297) + '...') : resolved) + '</div></div>');
        }

        if (rows.length === 0) {
            return '<div class="diag-empty">Payload is empty or null.</div>';
        }

        var overflowNote = overflow > 0
            ? '<div class="diag-empty" style="grid-column:1/-1;">+ ' + overflow + ' more fields — expand Resolved Payload for full data</div>'
            : '';

        return '<div class="diag-kv-grid">' + rows.join('') + overflowNote + '</div>';
    }

    function _diagProbeList(probes) {
        if (!Array.isArray(probes) || probes.length === 0) {
            return '<div class="diag-empty">No probe trace recorded.</div>';
        }

        var rows = [];
        for (var i = 0; i < probes.length; i++) {
            var p = probes[i] || {};
            var ok = p.ok !== false && !p.error;
            var status = ok ? _diagBadge('ok', 'ok') : _diagBadge('error', 'err');
            var right = p.error ? ('<span style="color:var(--red);">' + _esc(String(p.error)) + '</span>') : status;
            rows.push(
                '<div class="diag-probe-item">' +
                '<span class="diag-probe-name" title="' + _esc((p.label || p.id || 'probe')) + '">' + _esc((p.label || p.id || 'probe')) + '</span>' +
                '<span>' + right + '</span>' +
                '</div>'
            );
        }
        return '<div class="diag-probe-list">' + rows.join('') + '</div>';
    }

    function _renderDiagnostic(normalized, fallbackKey) {
        var key = normalized.key || fallbackKey || 'diagnostic';
        var label = normalized.label || key;
        var healthy = normalized.healthy === true;
        var fallbackUsed = normalized.fallback_used === true;
        var probes = Array.isArray(normalized.probes) ? normalized.probes : [];
        var okProbes = probes.filter(function (p) { return p && p.ok !== false && !p.error; }).length;
        var failedProbes = probes.length - okProbes;
        var resolved = normalized.resolved;
        var note = resolved && typeof resolved === 'object' ? resolved.note : null;

        var badges = [
            _diagBadge(healthy ? 'healthy' : 'degraded', healthy ? 'ok' : 'warn'),
            _diagBadge(fallbackUsed ? 'fallback used' : 'primary only', fallbackUsed ? 'warn' : 'ok'),
            _diagBadge(String(okProbes) + '/' + String(probes.length || 0) + ' probes ok', failedProbes > 0 ? 'warn' : 'ok')
        ].join('');

        var resolvedSource = resolved && typeof resolved === 'object' ? resolved.source : null;

        var meta = [
            '<span>key: <strong>' + _esc(key) + '</strong></span>',
            resolvedSource ? '<span>source: <strong>' + _esc(String(resolvedSource)) + '</strong></span>' : '',
            '<span>time: <strong>' + _esc(normalized.timestamp || new Date().toISOString()) + '</strong></span>'
        ].filter(Boolean).join('');

        return '<div class="diag-shell">' +
            '<div class="diag-head">' +
            '<div class="diag-head-title">' + _esc(label) + '</div>' +
            '<div class="diag-badges">' + badges + '</div>' +
            '</div>' +
            '<div class="diag-meta">' + meta + '</div>' +
            _diagKvs(resolved) +
            (note ? '<div class="diag-note">' + _esc(String(note)) + '</div>' : '') +
            '<details class="diag-details">' +
            '<summary>Resolved payload</summary>' +
            '<pre>' + _diagPretty(resolved, 25000) + '</pre>' +
            '</details>' +
            '<details class="diag-details">' +
            '<summary>Probe trace (' + String(probes.length) + ')</summary>' +
            _diagProbeList(probes) +
            '<pre>' + _diagPretty(probes, 25000) + '</pre>' +
            '</details>' +
            '</div>';
    }

    function handleDiagResult(msg) {
        var diagOut = document.getElementById('diag-output');
        if (!diagOut) return;

        var diagKey = _pendingDiagnostics[msg.id] || msg.diagKey || 'diagnostic';
        delete _pendingDiagnostics[msg.id];

        if (msg.error) {
            diagOut.innerHTML = '<div class="diag-shell error">' +
                '<div class="diag-head">' +
                '<div class="diag-head-title">' + _esc(diagKey) + '</div>' +
                '<div class="diag-badges">' + _diagBadge('error', 'err') + '</div>' +
                '</div>' +
                '<div class="diag-note">' + _esc(String(msg.error)) + '</div>' +
                '</div>';
            return;
        }

        var payload = msg.data || {};
        try {
            var normalized = payload;
            if (typeof payload === 'string') {
                try { normalized = JSON.parse(payload); } catch (e) { normalized = { raw: payload }; }
            }

            // Route imagination results to custom renderer
            if (diagKey === '_imagination') {
                var imgResolved = normalized.resolved || normalized;
                diagOut.innerHTML = renderImaginationResult(imgResolved);
                return;
            }

            // Route config load — extract dreamer.config from show_rssm response
            if (diagKey === '_dreamer_config_load') {
                var configResolved = normalized.resolved || normalized;
                if (configResolved && configResolved.dreamer && configResolved.dreamer.config) {
                    renderDreamerConfig(configResolved.dreamer.config);
                } else {
                    // Fallback: try to load from the raw data (pre-enrichment, show_rssm won't have dreamer yet)
                    vscode.postMessage({ command: 'loadDreamerConfigFile' });
                }
                return;
            }

            var output = {
                diagnostic: normalized.label || diagKey,
                key: normalized.key || diagKey,
                healthy: normalized.healthy,
                fallback_used: normalized.fallback_used,
                timestamp: normalized.timestamp,
                resolved: normalized.resolved,
                probes: normalized.probes
            };

            diagOut.innerHTML = _renderDiagnostic(output, diagKey);
        } catch (err) {
            diagOut.innerHTML = '<div class="diag-shell error"><div class="diag-note">Failed to render diagnostic output. Raw payload:</div><pre style="white-space:pre-wrap;word-break:break-word;color:var(--text);font-size:11px;">' + _diagPretty(payload, 50000) + '</pre></div>';
        }
    }
    // Expose globally for onclick handlers
    window.callTool = callTool;
    window.runDiagnostic = runDiagnostic;

    // ═══════════════ DREAMER UI FUNCTIONS ═══════════════

    function runImagination() {
        var diagOut = document.getElementById('diag-output');
        if (diagOut) { diagOut.innerHTML = '<div class="diag-shell"><div class="diag-empty">Imagining...</div></div>'; }
        var id = ++_requestId;
        _pendingDiagnostics[id] = '_imagination';
        vscode.postMessage({ command: 'callTool', tool: 'imagine', args: { scenario: 'current state', steps: 15 }, id: id });
    }

    function renderImaginationResult(data) {
        var trajectories = data.trajectories || data;
        if (!Array.isArray(trajectories) || trajectories.length === 0) {
            return '<div class="diag-shell"><pre style="white-space:pre-wrap;font-size:11px;">' + _diagPretty(data, 50000) + '</pre></div>';
        }
        var numTrajs = trajectories.length;
        var horizon = (trajectories[0] && trajectories[0].length) || 0;
        var html = '<div class="diag-shell"><h3 style="margin:0 0 8px;">IMAGINATION &mdash; ' + numTrajs + ' branches &times; ' + horizon + ' steps</h3>';

        var branchValues = trajectories.map(function(traj, i) {
            var totalValue = 0;
            for (var j = 0; j < traj.length; j++) { totalValue += (traj[j].critic_value || 0); }
            return { action: i, value: totalValue, traj: traj };
        });
        branchValues.sort(function(a, b) { return b.value - a.value; });

        var bestAction = branchValues[0] ? branchValues[0].action : 0;
        html += '<div style="margin-bottom:12px;">';
        html += '<div>Best action: <strong>' + bestAction + '</strong> (value: ' + (branchValues[0] ? branchValues[0].value.toFixed(3) : '0') + ')</div>';
        html += '</div>';

        html += '<table style="width:100%;border-collapse:collapse;font-size:11px;">';
        html += '<tr style="border-bottom:1px solid var(--vscode-panel-border);">';
        html += '<th style="text-align:left;padding:4px;">Act</th><th style="text-align:left;padding:4px;">Value</th><th style="text-align:left;padding:4px;">Bar</th><th style="text-align:left;padding:4px;">Trajectory</th></tr>';

        var maxVal = 0.01;
        for (var k = 0; k < branchValues.length; k++) {
            if (Math.abs(branchValues[k].value) > maxVal) { maxVal = Math.abs(branchValues[k].value); }
        }

        for (var rank = 0; rank < branchValues.length; rank++) {
            var branch = branchValues[rank];
            var pct = Math.max(0, (branch.value / maxVal) * 100);
            var isBest = rank === 0;
            var color = isBest ? '#4CAF50' : '#2196F3';
            html += '<tr style="border-bottom:1px solid var(--vscode-panel-border);opacity:' + (1 - rank * 0.08) + ';">';
            html += '<td style="padding:4px;">' + (isBest ? '\u25BA ' : '  ') + branch.action + '</td>';
            html += '<td style="padding:4px;font-variant-numeric:tabular-nums;">' + branch.value.toFixed(3) + '</td>';
            html += '<td style="padding:4px;width:40%;"><div style="height:8px;background:var(--vscode-progressBar-background);border-radius:3px;">';
            html += '<div style="width:' + pct + '%;height:100%;background:' + color + ';border-radius:3px;"></div></div></td>';
            var norms = branch.traj.map(function(s) { return s.latent_norm || 0; });
            var maxNorm = 0.01;
            for (var m = 0; m < norms.length; m++) { if (norms[m] > maxNorm) maxNorm = norms[m]; }
            var blocks = ['\u2581','\u2582','\u2583','\u2584','\u2585','\u2586','\u2587','\u2588'];
            var sparkline = norms.map(function(n) { var h = Math.round((n / maxNorm) * 7); return blocks[Math.min(h, 7)]; }).join('');
            html += '<td style="padding:4px;font-size:10px;letter-spacing:-1px;">' + sparkline + '</td>';
            html += '</tr>';
        }
        html += '</table></div>';
        return html;
    }

    var _dreamerConfig = null;

    function toggleDreamerConfig() {
        var panel = document.getElementById('dreamer-config-panel');
        var arrow = document.getElementById('dreamer-config-arrow');
        if (!panel) return;
        var isHidden = panel.style.display === 'none';
        panel.style.display = isHidden ? 'block' : 'none';
        if (arrow) arrow.textContent = isHidden ? '\u25B2' : '\u25BC';
        if (isHidden && !_dreamerConfig) { loadDreamerConfig(); }
    }

    function loadDreamerConfig() {
        var id = ++_requestId;
        _pendingDiagnostics[id] = '_dreamer_config_load';
        vscode.postMessage({ command: 'runDiagnostic', diagKey: 'show_rssm', id: id });
    }

    function renderConfigSection(values, section, schema) {
        var keys = Object.keys(schema);
        return keys.map(function(key) {
            var opts = schema[key];
            var val = values ? values[key] : '';
            if (val === undefined || val === null) val = '';
            if (opts.type === 'checkbox') {
                return '<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;min-height:24px;border-bottom:1px solid rgba(255,255,255,0.04);">' +
                    '<label style="opacity:0.8;font-size:11px;">' + opts.label + '</label>' +
                    '<input type="checkbox" ' + (val ? 'checked' : '') + ' style="width:14px;height:14px;margin:0;flex-shrink:0;" data-section="' + section + '" data-key="' + key + '" onchange="updateConfigField(\'' + section + '\',\'' + key + '\',this.checked)">' +
                    '</div>';
            }
            return '<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;min-height:24px;border-bottom:1px solid rgba(255,255,255,0.04);">' +
                '<label style="opacity:0.8;flex:1;font-size:11px;">' + opts.label + '</label>' +
                '<input type="number" value="' + val + '" min="' + opts.min + '" max="' + opts.max + '" step="' + opts.step + '" ' +
                'style="width:70px;text-align:right;background:var(--vscode-input-background);color:var(--vscode-input-foreground);border:1px solid var(--vscode-input-border);padding:3px 6px;font-size:11px;border-radius:2px;flex-shrink:0;" ' +
                'data-section="' + section + '" data-key="' + key + '" onchange="updateConfigField(\'' + section + '\',\'' + key + '\',parseFloat(this.value))">' +
                '</div>';
        }).join('');
    }

    function renderDreamerConfig(config) {
        _dreamerConfig = config;
        var el;
        el = document.getElementById('reward-config-fields');
        if (el) el.innerHTML = renderConfigSection(config.rewards, 'rewards', {
            hold_accept: { label: 'HOLD Accept', min: -5, max: 5, step: 0.1 },
            hold_override: { label: 'HOLD Override', min: -5, max: 5, step: 0.1 },
            bag_induct: { label: 'Bag Induct', min: -5, max: 5, step: 0.1 },
            bag_forget: { label: 'Bag Forget', min: -5, max: 5, step: 0.1 },
            workflow_save: { label: 'Workflow Save', min: -5, max: 5, step: 0.1 },
            workflow_success: { label: 'Workflow Success', min: -5, max: 5, step: 0.1 },
            workflow_failure: { label: 'Workflow Failure', min: -5, max: 5, step: 0.1 },
            tool_success: { label: 'Tool Success', min: -5, max: 5, step: 0.01 },
            tool_error: { label: 'Tool Error', min: -5, max: 5, step: 0.01 },
            mutation_kept: { label: 'Mutation Kept', min: -5, max: 5, step: 0.1 },
            mutation_reverted: { label: 'Mutation Reverted', min: -5, max: 5, step: 0.1 },
            normalize: { label: 'Symlog Normalize', type: 'checkbox' }
        });
        el = document.getElementById('training-config-fields');
        if (el) el.innerHTML = renderConfigSection(config.training, 'training', {
            enabled: { label: 'Enabled', type: 'checkbox' },
            auto_train: { label: 'Auto-Train', type: 'checkbox' },
            world_model_frequency: { label: 'World Model Freq', min: 8, max: 256, step: 8 },
            critic_frequency: { label: 'Critic Freq', min: 8, max: 256, step: 8 },
            full_cycle_frequency: { label: 'Full Cycle Freq', min: 16, max: 512, step: 16 },
            batch_size: { label: 'Batch Size', min: 8, max: 128, step: 8 },
            noise_scale: { label: 'Noise Scale', min: 0.001, max: 0.1, step: 0.001 },
            gamma: { label: 'Gamma (discount)', min: 0.9, max: 0.999, step: 0.001 },
            lambda: { label: 'Lambda (GAE)', min: 0.8, max: 0.99, step: 0.01 },
            critic_target_tau: { label: 'Target EMA Tau', min: 0.001, max: 0.1, step: 0.001 },
            timeout_budget_seconds: { label: 'Timeout Budget (s)', min: 5, max: 55, step: 5 }
        });
        el = document.getElementById('imagination-config-fields');
        if (el) el.innerHTML = renderConfigSection(config.imagination, 'imagination', {
            horizon: { label: 'Horizon', min: 5, max: 50, step: 5 },
            n_actions: { label: 'Action Branches', min: 2, max: 16, step: 1 },
            auto_imagine_on_train: { label: 'Auto-Imagine on Train', type: 'checkbox' }
        });
        el = document.getElementById('buffer-config-fields');
        if (el) el.innerHTML = renderConfigSection(config.buffers, 'buffers', {
            reward_buffer_max: { label: 'Reward Buffer Max', min: 100, max: 50000, step: 100 },
            obs_buffer_max: { label: 'Obs Buffer Max', min: 100, max: 10000, step: 100 },
            value_history_max: { label: 'Value History Max', min: 50, max: 1000, step: 50 },
            reward_rate_window: { label: 'Rate Window', min: 10, max: 500, step: 10 }
        });
        el = document.getElementById('arch-config-fields');
        if (el && config.architecture) {
            el.innerHTML = Object.keys(config.architecture).map(function(k) {
                return '<div style="display:flex;justify-content:space-between;padding:2px 0;"><span style="opacity:0.7;">' + k + '</span><span style="font-variant-numeric:tabular-nums;">' + config.architecture[k] + '</span></div>';
            }).join('');
        }
    }

    function updateConfigField(section, key, value) {
        if (!_dreamerConfig) return;
        if (!_dreamerConfig[section]) _dreamerConfig[section] = {};
        _dreamerConfig[section][key] = value;
    }

    function saveDreamerConfig() {
        if (!_dreamerConfig) return;
        vscode.postMessage({ command: 'saveDreamerConfig', config: _dreamerConfig });
        var status = document.getElementById('config-save-status');
        if (status) { status.textContent = 'Saved \u2713'; setTimeout(function() { status.textContent = ''; }, 2000); }
    }

    function resetDreamerConfig() {
        vscode.postMessage({ command: 'resetDreamerConfig' });
        var status = document.getElementById('config-save-status');
        if (status) { status.textContent = 'Reset to defaults \u2713'; setTimeout(function() { status.textContent = ''; loadDreamerConfig(); }, 1000); }
    }

    window.runImagination = runImagination;
    window.toggleDreamerConfig = toggleDreamerConfig;
    window.updateConfigField = updateConfigField;
    window.saveDreamerConfig = saveDreamerConfig;
    window.resetDreamerConfig = resetDreamerConfig;

    // ═══════════════ END DREAMER UI ═══════════════

    var MEMORY_TOOLS = ['bag_catalog', 'bag_search', 'bag_get', 'bag_export', 'bag_induct', 'bag_forget', 'bag_put', 'pocket', 'summon', 'materialize', 'bag_read_doc', 'bag_list_docs', 'bag_search_docs', 'bag_tree', 'bag_checkpoint', 'bag_versions', 'bag_diff', 'bag_restore', 'file_read', 'file_write', 'file_edit', 'file_append', 'file_prepend', 'file_delete', 'file_rename', 'file_copy', 'file_list', 'file_tree', 'file_search', 'file_info', 'file_checkpoint', 'file_versions', 'file_diff', 'file_restore', 'get_cached'];
    var COUNCIL_TOOLS = ['council_status', 'all_slots', 'broadcast', 'council_broadcast', 'set_consensus', 'debate', 'chain', 'slot_info', 'get_slot_params', 'invoke_slot', 'plug_model', 'unplug_slot', 'clone_slot', 'mu' + 'tate_slot', 'rename_slot', 'swap_slots', 'hub_plug', 'cu' + 'll_slot', 'agent_chat'];
    var WORKFLOW_TOOLS = ['workflow_list', 'workflow_get', 'workflow_execute', 'workflow_status'];

    function parseToolData(data) {
        if (data && data.content && Array.isArray(data.content) && data.content[0] && data.content[0].text) {
            return data.content[0].text;
        }
        if (typeof data === 'string') return data;
        return JSON.stringify(data, null, 2);
    }

    function _esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    function _countTypes(items) {
        var seen = {};
        for (var i = 0; i < items.length; i++) { seen[items[i].type || 'unknown'] = 1; }
        return Object.keys(seen).length;
    }
    function _fmtSize(n) {
        if (n == null || n === 0) return '';
        if (n < 1024) return n + ' B';
        if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
        return (n / 1048576).toFixed(1) + ' MB';
    }

    // ── WORKFLOWS TAB (MCP) ──
    function _wfParsePayload(raw) {
        if (raw == null) return null;
        var data = raw;
        if (typeof data === 'string') {
            try { data = JSON.parse(data); } catch (e) { return null; }
        }
        if (data && data.content && Array.isArray(data.content) && data.content[0] && typeof data.content[0].text === 'string') {
            try { return JSON.parse(data.content[0].text); } catch (e2) { return null; }
        }
        return data;
    }

    function _wfNormalizeStatus(status) {
        var s = String(status || '').toLowerCase();
        if (s === 'success') s = 'completed';
        if (s === 'error') s = 'failed';
        if (s === 'in_progress') s = 'running';
        if (s !== 'completed' && s !== 'running' && s !== 'failed' && s !== 'skipped') s = 'pending';
        return s;
    }

    // ── WORKFLOW IDENTITY COLOR (Golden Angle HSV) ──
    function _wfWorkflowColor(workflowId) {
        if (!workflowId) return '#4d5d78';
        if (_wfColorCache[workflowId]) return _wfColorCache[workflowId];
        var idx = _wfColorIndex++;
        var hue = (idx * 137.508) % 360;
        var s = 0.65, v = 0.75;
        var h = hue / 60, i = Math.floor(h), f = h - i;
        var p = v * (1 - s), q = v * (1 - s * f), t = v * (1 - s * (1 - f));
        var r, g, b;
        switch (i % 6) {
            case 0: r = v; g = t; b = p; break;
            case 1: r = q; g = v; b = p; break;
            case 2: r = p; g = v; b = t; break;
            case 3: r = p; g = q; b = v; break;
            case 4: r = t; g = p; b = v; break;
            default: r = v; g = p; b = q; break;
        }
        var hex = function (n) { var x = Math.round(n * 255).toString(16); return x.length < 2 ? '0' + x : x; };
        var color = '#' + hex(r) + hex(g) + hex(b);
        _wfColorCache[workflowId] = color;
        return color;
    }

    function _wfSetExecStatus(message, isError) {
        var el = document.getElementById('wfops-exec-status');
        if (!el) return;
        el.style.color = isError ? 'var(--red)' : 'var(--text)';
        el.textContent = message || '';
    }

    function _wfSetBadge(status, label) {
        var badge = document.getElementById('wfops-running-badge');
        if (!badge) return;
        badge.classList.remove('running', 'completed', 'failed');
        if (status === 'idle') {
            badge.textContent = label || 'IDLE';
            return;
        }
        var s = _wfNormalizeStatus(status);
        if (s === 'running' || s === 'completed' || s === 'failed') {
            badge.classList.add(s);
        }
        badge.textContent = label || s.toUpperCase();
    }

    function _wfStopPolling() {
        if (_wfStatusPollTimer) {
            clearInterval(_wfStatusPollTimer);
            _wfStatusPollTimer = null;
        }
    }

    function _wfStartPolling(executionId) {
        if (!executionId) return;
        _wfStopPolling();
        _wfCurrentExecutionId = executionId;
        var attempts = 0;
        _wfStatusPollTimer = setInterval(function () {
            attempts += 1;
            callTool('workflow_status', { execution_id: executionId });
            if (attempts >= 30) {
                _wfStopPolling();
            }
        }, 1500);
    }

    function _wfNodeMapFromWorkflow(workflow) {
        var map = {};
        if (!workflow || !Array.isArray(workflow.nodes)) return map;
        workflow.nodes.forEach(function (node, idx) {
            var nodeId = String((node && node.id != null) ? node.id : ('node_' + String(idx + 1)));
            map[nodeId] = node || {};
        });
        return map;
    }

    function _wfTypeStats(nodes) {
        var stats = {};
        (nodes || []).forEach(function (node) {
            var type = String((node && node.type) || 'node');
            stats[type] = (stats[type] || 0) + 1;
        });
        return stats;
    }

    function _wfExtractRefs(value, sink) {
        if (value == null || !sink) return;
        if (typeof value === 'string') {
            var refs = value.match(/\$[a-zA-Z_][a-zA-Z0-9_.]*/g) || [];
            refs.forEach(function (r) { sink[r] = 1; });
            var m;
            var tpl = /\{\{([^}]+)\}\}/g;
            while ((m = tpl.exec(value)) !== null) {
                if (m && m[1] && m[1].trim()) sink['{{' + m[1].trim() + '}}'] = 1;
            }
            return;
        }
        if (Array.isArray(value)) {
            value.forEach(function (v) { _wfExtractRefs(v, sink); });
            return;
        }
        if (typeof value === 'object') {
            Object.keys(value).forEach(function (k) {
                _wfExtractRefs(value[k], sink);
            });
        }
    }

    function _wfJsonBlock(title, data) {
        if (data == null) return '';
        if (typeof data === 'object' && !Array.isArray(data) && Object.keys(data).length === 0) return '';
        var text = '';
        try { text = JSON.stringify(data, null, 2); } catch (e) { text = String(data); }
        return '<div class="wfops-json">' +
            '<div class="wfops-subhead">' + _esc(title) + '</div>' +
            '<pre>' + _esc(text) + '</pre>' +
            '</div>';
    }

    function _wfSetDetailKindLabel(kind) {
        var el = document.getElementById('wfops-detail-kind');
        if (!el) return;
        el.textContent = String(kind || 'workflow').toUpperCase();
    }

    function _wfRenderDrillEmpty(message) {
        var detailEl = document.getElementById('wfops-detail');
        if (!detailEl) return;
        _wfSetDetailKindLabel('workflow');
        detailEl.innerHTML = '<div class="wfops-detail-empty">' + _esc(message || 'Select a workflow, node, or connection to inspect details.') + '</div>';
    }

    function _wfCurrentNodeStates() {
        if (!_wfLastExec || !_wfLoadedDef) return null;
        var loadedId = String(_wfLoadedDef.id || _wfSelectedId || '');
        var execWorkflowId = String(_wfLastExec.workflow_id || '');
        if (!loadedId || !execWorkflowId || loadedId !== execWorkflowId) return null;
        return _wfLastExec.node_states || null;
    }

    function _wfEnsureDrillTarget() {
        if (!_wfLoadedDef || !Array.isArray(_wfLoadedDef.nodes)) {
            _wfDrill.kind = 'workflow';
            _wfDrill.nodeId = '';
            _wfDrill.edgeIndex = -1;
            return;
        }
        var nodeMap = _wfNodeMapFromWorkflow(_wfLoadedDef);
        if (_wfDrill.kind === 'node' && !nodeMap[_wfDrill.nodeId]) {
            _wfDrill.kind = 'workflow';
            _wfDrill.nodeId = '';
            _wfDrill.edgeIndex = -1;
            return;
        }
        var connLen = Array.isArray(_wfLoadedDef.connections) ? _wfLoadedDef.connections.length : 0;
        if (_wfDrill.kind === 'connection' && (_wfDrill.edgeIndex < 0 || _wfDrill.edgeIndex >= connLen)) {
            _wfDrill.kind = 'workflow';
            _wfDrill.nodeId = '';
            _wfDrill.edgeIndex = -1;
        }
    }

    function _wfRenderDrillDetail() {
        var detailEl = document.getElementById('wfops-detail');
        if (!detailEl) return;

        if (!_wfLoadedDef || !Array.isArray(_wfLoadedDef.nodes)) {
            _wfRenderDrillEmpty('Select a workflow from the list to inspect metadata and resources.');
            return;
        }

        _wfEnsureDrillTarget();

        var workflowId = String(_wfLoadedDef.id || _wfSelectedId || 'workflow');
        _wfDrill.workflowId = workflowId;
        var nodeMap = _wfNodeMapFromWorkflow(_wfLoadedDef);
        var execStates = _wfCurrentNodeStates() || {};
        var kind = _wfDrill.kind || 'workflow';
        var html = '';

        if (kind === 'node') {
            var nodeId = String(_wfDrill.nodeId || '');
            var node = nodeMap[nodeId];
            if (!node) {
                _wfDrill.kind = 'workflow';
                kind = 'workflow';
            } else {
                var stObj = execStates[nodeId] || {};
                var incoming = (_wfGraphMeta && _wfGraphMeta.reverse && _wfGraphMeta.reverse[nodeId]) ? _wfGraphMeta.reverse[nodeId] : [];
                var outgoing = (_wfGraphMeta && _wfGraphMeta.adjacency && _wfGraphMeta.adjacency[nodeId]) ? _wfGraphMeta.adjacency[nodeId] : [];
                var params = node.parameters || node.config || {};
                var refs = {};
                _wfExtractRefs(params, refs);
                var refList = Object.keys(refs).sort();
                var resources = [];
                if (String(node.type || '') === 'tool' && params.tool_name) {
                    resources.push('tool:' + String(params.tool_name));
                }
                if (String(node.type || '') === 'http' && (params.method || params.url)) {
                    resources.push('http:' + String(params.method || 'GET') + ' ' + String(params.url || ''));
                }
                refList.forEach(function (r) { resources.push('ref:' + r); });

                html =
                    '<div class="wfops-drill-title">' +
                    '<span class="wfops-drill-name">' + _esc(nodeId) + '</span>' +
                    '<span class="wfops-drill-pill">NODE</span>' +
                    '</div>' +
                    '<div class="wfops-kv-grid">' +
                    '<div class="k">Type</div><div class="v">' + _esc(String(node.type || 'node')) + '</div>' +
                    '<div class="k">Name</div><div class="v">' + _esc(String(node.name || node.label || nodeId)) + '</div>' +
                    '<div class="k">Description</div><div class="v">' + _esc(String(node.description || '—')) + '</div>' +
                    '<div class="k">Status</div><div class="v">' + _esc(_wfNormalizeStatus(stObj.status || 'pending')) + '</div>' +
                    '<div class="k">Elapsed</div><div class="v">' + (typeof stObj.elapsed_ms === 'number' ? (String(stObj.elapsed_ms) + 'ms') : '—') + '</div>' +
                    '<div class="k">Incoming</div><div class="v">' + String(incoming.length) + '</div>' +
                    '<div class="k">Outgoing</div><div class="v">' + String(outgoing.length) + '</div>' +
                    '</div>' +
                    '<div class="wfops-subhead">Linked Nodes</div>' +
                    '<div class="wfops-chip-row">' +
                    (incoming.length ? incoming.map(function (id) { return '<span class="wfops-chip">IN: ' + _esc(id) + '</span>'; }).join('') : '<span class="wfops-chip">IN: none</span>') +
                    (outgoing.length ? outgoing.map(function (id) { return '<span class="wfops-chip">OUT: ' + _esc(id) + '</span>'; }).join('') : '<span class="wfops-chip">OUT: none</span>') +
                    '</div>' +
                    '<div class="wfops-subhead">Resources & Expressions</div>' +
                    '<div class="wfops-chip-row">' +
                    (resources.length ? resources.map(function (r) { return '<span class="wfops-chip">' + _esc(r) + '</span>'; }).join('') : '<span class="wfops-chip">none</span>') +
                    '</div>' +
                    _wfJsonBlock('Node Parameters', params) +
                    _wfJsonBlock('Last Node State', stObj);

                _wfSetDetailKindLabel('node');
                detailEl.innerHTML = html;
                return;
            }
        }

        if (kind === 'connection') {
            var edge = (_wfGraphMeta && _wfGraphMeta.connections) ? _wfGraphMeta.connections[_wfDrill.edgeIndex] : null;
            if (!edge) {
                _wfDrill.kind = 'workflow';
                kind = 'workflow';
            } else {
                var fromNode = nodeMap[edge.from] || {};
                var toNode = nodeMap[edge.to] || {};
                var toState = execStates[edge.to] || {};
                html =
                    '<div class="wfops-drill-title">' +
                    '<span class="wfops-drill-name">' + _esc(edge.from + ' → ' + edge.to) + '</span>' +
                    '<span class="wfops-drill-pill">CONNECTION</span>' +
                    '</div>' +
                    '<div class="wfops-kv-grid">' +
                    '<div class="k">From Node</div><div class="v">' + _esc(edge.from) + ' (' + _esc(String(fromNode.type || 'node')) + ')</div>' +
                    '<div class="k">To Node</div><div class="v">' + _esc(edge.to) + ' (' + _esc(String(toNode.type || 'node')) + ')</div>' +
                    '<div class="k">Label</div><div class="v">' + _esc(edge.label || '—') + '</div>' +
                    '<div class="k">Branch</div><div class="v">' + _esc(edge.branch || '—') + '</div>' +
                    '<div class="k">Condition</div><div class="v">' + _esc(edge.condition || '—') + '</div>' +
                    '<div class="k">Downstream Status</div><div class="v">' + _esc(_wfNormalizeStatus(toState.status || 'pending')) + '</div>' +
                    '</div>' +
                    _wfJsonBlock('Connection Payload', edge.raw || edge);

                _wfSetDetailKindLabel('connection');
                detailEl.innerHTML = html;
                return;
            }
        }

        var typeStats = _wfTypeStats(_wfLoadedDef.nodes || []);
        var typeChips = Object.keys(typeStats).sort().map(function (type) {
            return '<span class="wfops-chip">' + _esc(type) + ': ' + String(typeStats[type]) + '</span>';
        }).join('');
        var runStatus = (_wfLastExec && String(_wfLastExec.workflow_id || '') === workflowId)
            ? _wfNormalizeStatus(_wfLastExec.status || 'pending')
            : 'pending';

        html =
            '<div class="wfops-drill-title">' +
            '<span class="wfops-drill-name">' + _esc(String(_wfLoadedDef.name || workflowId)) + '</span>' +
            '<span class="wfops-drill-pill">WORKFLOW</span>' +
            '</div>' +
            '<div class="wfops-kv-grid">' +
            '<div class="k">Workflow ID</div><div class="v">' + _esc(workflowId) + '</div>' +
            '<div class="k">Version</div><div class="v">' + _esc(String(_wfLoadedDef.version || '—')) + '</div>' +
            '<div class="k">Category</div><div class="v">' + _esc(String(_wfLoadedDef.category || '—')) + '</div>' +
            '<div class="k">Description</div><div class="v">' + _esc(String(_wfLoadedDef.description || '—')) + '</div>' +
            '<div class="k">Nodes</div><div class="v">' + String((_wfLoadedDef.nodes || []).length) + '</div>' +
            '<div class="k">Connections</div><div class="v">' + String((_wfLoadedDef.connections || []).length) + '</div>' +
            '<div class="k">Last Run</div><div class="v">' + _esc(runStatus) + '</div>' +
            '<div class="k">Execution ID</div><div class="v">' + _esc(String((_wfLastExec && _wfLastExec.execution_id) || '—')) + '</div>' +
            '</div>' +
            '<div class="wfops-subhead">Node Type Composition</div>' +
            '<div class="wfops-chip-row">' + (typeChips || '<span class="wfops-chip">none</span>') + '</div>' +
            _wfJsonBlock('Workflow Config', _wfLoadedDef.config || {}) +
            _wfJsonBlock('Workflow Metadata', _wfLoadedDef.metadata || {});

        _wfSetDetailKindLabel('workflow');
        detailEl.innerHTML = html;
    }

    function _wfSelectWorkflowDrill() {
        _wfDrill.kind = 'workflow';
        _wfDrill.nodeId = '';
        _wfDrill.edgeIndex = -1;
        var states = _wfCurrentNodeStates();
        renderWorkflowGraph(_wfLoadedDef, states);
        renderWorkflowNodeStates(_wfLoadedDef, states);
        _wfRenderDrillDetail();
    }

    function _wfSelectNodeDrill(nodeId) {
        _wfDrill.kind = 'node';
        _wfDrill.nodeId = String(nodeId || '');
        _wfDrill.edgeIndex = -1;
        var states = _wfCurrentNodeStates();
        renderWorkflowGraph(_wfLoadedDef, states);
        renderWorkflowNodeStates(_wfLoadedDef, states);
        _wfRenderDrillDetail();
    }

    function _wfSelectEdgeDrill(edgeIndex) {
        _wfDrill.kind = 'connection';
        _wfDrill.edgeIndex = Number(edgeIndex);
        _wfDrill.nodeId = '';
        var states = _wfCurrentNodeStates();
        renderWorkflowGraph(_wfLoadedDef, states);
        renderWorkflowNodeStates(_wfLoadedDef, states);
        _wfRenderDrillDetail();
    }

    function renderWorkflowList() {
        var listEl = document.getElementById('wfops-list');
        if (!listEl) return;
        var countEl = document.getElementById('wfops-count');
        if (countEl) countEl.textContent = String(_wfCatalog.length);

        if (!_wfCatalog.length) {
            listEl.innerHTML = '<div class="wfops-item" style="color:var(--text-dim);cursor:default;">No workflows found. Click REFRESH LIST.</div>';
            var selectedNone = document.getElementById('wfops-selected');
            if (selectedNone) selectedNone.textContent = 'none';
            return;
        }

        listEl.innerHTML = _wfCatalog.map(function (wf) {
            var active = wf.id === _wfSelectedId ? ' active' : '';
            var isExec = _wfLastExec && _wfNormalizeStatus(_wfLastExec.status) === 'running' &&
                (wf.id === _wfCurrentExecutionId || wf.id === _wfSelectedId);
            var executing = isExec ? ' executing' : '';
            var color = _wfWorkflowColor(wf.id);
            var style = '--wf-color:' + color + ';border-left-color:' + color;
            return '<div class="wfops-item' + active + executing + '" style="' + style + '" data-wfops-id="' + _esc(wf.id) + '">' +
                '<div class="wfops-item-title">' + _esc(wf.name || wf.id) + '</div>' +
                '<div class="wfops-item-meta">' +
                '<span>' + _esc(wf.id) + '</span>' +
                '<span>' + String(wf.node_count || 0) + ' nodes</span>' +
                (wf.description ? '<span>' + _esc(wf.description) + '</span>' : '') +
                '</div>' +
                '</div>';
        }).join('');

        var selected = _wfCatalog.find(function (wf) { return wf.id === _wfSelectedId; });
        var selectedEl = document.getElementById('wfops-selected');
        if (selectedEl) {
            selectedEl.textContent = selected ? (selected.name || selected.id) : 'none';
        }
    }

    function renderWorkflowNodeStates(workflow, nodeStates) {
        var panel = document.getElementById('wfops-node-status');
        if (!panel) return;
        if (!workflow || !Array.isArray(workflow.nodes) || workflow.nodes.length === 0) {
            panel.innerHTML = '<div class="wfops-node-row"><span class="name">No workflow loaded.</span><span class="state pending">PENDING</span></div>';
            return;
        }

        var states = nodeStates || {};
        panel.innerHTML = workflow.nodes.map(function (node, idx) {
            var nodeId = String((node && node.id != null) ? node.id : ('node_' + String(idx + 1)));
            var stObj = states[nodeId] || {};
            var st = _wfNormalizeStatus(stObj.status || 'pending');
            var elapsed = typeof stObj.elapsed_ms === 'number' ? (' · ' + String(stObj.elapsed_ms) + 'ms') : '';
            var active = (_wfDrill.kind === 'node' && _wfDrill.nodeId === nodeId) ? ' active' : '';
            return '<div class="wfops-node-row' + active + '" data-wf-node-id="' + _esc(nodeId) + '">' +
                '<span class="name">' + _esc(nodeId) + '</span>' +
                '<span class="state ' + st + '">' + st.toUpperCase() + elapsed + '</span>' +
                '</div>';
        }).join('');
    }

    function renderWorkflowGraph(workflow, nodeStates) {
        var svg = document.getElementById('wfops-graph');
        if (!svg) return;
        if (!workflow || !Array.isArray(workflow.nodes) || workflow.nodes.length === 0) {
            _wfGraphMeta = null;
            svg.setAttribute('viewBox', '0 0 820 360');
            svg.innerHTML = '<text x="24" y="40" fill="#7a8aa5" font-size="13" font-family="monospace">Select a workflow to visualize.</text>';
            return;
        }

        // Graph identity border
        var graphWrap = document.querySelector('.wfops-graph-wrap');
        if (graphWrap && workflow.id) {
            var idColor = _wfWorkflowColor(String(workflow.id));
            graphWrap.style.borderLeft = '3px solid ' + idColor;
        }

        var nodes = workflow.nodes.map(function (n, idx) {
            var id = (n && n.id != null) ? String(n.id) : ('node_' + String(idx + 1));
            return {
                id: id,
                type: String((n && n.type) || 'node'),
                name: String((n && (n.name || n.label || n.tool)) || id)
            };
        });

        var indegree = {};
        var adjacency = {};
        var reverse = {};
        var nodeMap = {};
        nodes.forEach(function (n) {
            indegree[n.id] = 0;
            adjacency[n.id] = [];
            reverse[n.id] = [];
            nodeMap[n.id] = n;
        });

        var connections = [];
        var rawConnections = Array.isArray(workflow.connections) ? workflow.connections : [];
        rawConnections.forEach(function (c) {
            var from = (c && c.from != null) ? String(c.from) : '';
            var to = (c && c.to != null) ? String(c.to) : '';
            if (!adjacency[from] || indegree[to] === undefined) return;
            adjacency[from].push(to);
            reverse[to].push(from);
            indegree[to] += 1;
            connections.push({
                index: connections.length,
                from: from,
                to: to,
                label: c && c.label ? String(c.label) : '',
                branch: c && c.branch ? String(c.branch) : '',
                condition: c && c.condition ? String(c.condition) : '',
                raw: c || {}
            });
        });

        var level = {};
        var queue = [];
        nodes.forEach(function (n) {
            if (indegree[n.id] === 0) {
                level[n.id] = 0;
                queue.push(n.id);
            }
        });
        if (queue.length === 0 && nodes.length > 0) {
            level[nodes[0].id] = 0;
            queue.push(nodes[0].id);
        }

        while (queue.length > 0) {
            var current = queue.shift();
            var nexts = adjacency[current] || [];
            for (var i = 0; i < nexts.length; i++) {
                var next = nexts[i];
                var nextLevel = (level[current] || 0) + 1;
                if (level[next] == null || nextLevel > level[next]) {
                    level[next] = nextLevel;
                }
                indegree[next] -= 1;
                if (indegree[next] === 0) queue.push(next);
            }
        }
        nodes.forEach(function (n) {
            if (level[n.id] == null) level[n.id] = 0;
        });

        var columns = {};
        var maxLevel = 0;
        nodes.forEach(function (n) {
            var l = level[n.id] || 0;
            if (!columns[l]) columns[l] = [];
            columns[l].push(n);
            if (l > maxLevel) maxLevel = l;
        });

        var maxInColumn = 1;
        for (var col = 0; col <= maxLevel; col++) {
            var len = (columns[col] || []).length;
            if (len > maxInColumn) maxInColumn = len;
        }

        var margin = 28;
        var nodeW = 170;
        var nodeH = 50;
        var gapX = 70;
        var gapY = 18;

        var width = margin * 2 + ((maxLevel + 1) * nodeW) + (maxLevel * gapX);
        var height = Math.max(320, margin * 2 + (maxInColumn * nodeH) + (Math.max(0, maxInColumn - 1) * gapY));
        svg.setAttribute('viewBox', '0 0 ' + String(width) + ' ' + String(height));

        var positions = {};
        for (var lvl = 0; lvl <= maxLevel; lvl++) {
            var colNodes = columns[lvl] || [];
            var colHeight = (colNodes.length * nodeH) + (Math.max(0, colNodes.length - 1) * gapY);
            var startY = margin + Math.max(0, (height - margin * 2 - colHeight) / 2);
            var x = margin + (lvl * (nodeW + gapX));
            for (var ni = 0; ni < colNodes.length; ni++) {
                positions[colNodes[ni].id] = { x: x, y: startY + (ni * (nodeH + gapY)) };
            }
        }

        // Merge saved drag positions
        var wfKey = workflow.id ? String(workflow.id) : '_default';
        var savedPos = _wfNodePositions[wfKey] || {};
        Object.keys(savedPos).forEach(function (nid) {
            if (positions[nid]) positions[nid] = savedPos[nid];
        });

        var nodeStateMap = nodeStates || {};
        var palette = {
            completed: { fill: '#123d2c', stroke: '#00ff88' },
            running: { fill: '#3f2e06', stroke: '#ffaa00' },
            failed: { fill: '#3d1717', stroke: '#ff4444' },
            skipped: { fill: '#2e2e35', stroke: '#8b8b8b' },
            pending: { fill: '#1f2b42', stroke: '#4d5d78' }
        };

        var edgesSvg = connections.map(function (edge) {
            var a = positions[edge.from];
            var b = positions[edge.to];
            if (!a || !b) return '';

            var sx = a.x + nodeW;
            var sy = a.y + (nodeH / 2);
            var tx = b.x;
            var ty = b.y + (nodeH / 2);
            var dx = Math.max(36, (tx - sx) * 0.45);
            var path = 'M ' + sx + ' ' + sy + ' C ' + (sx + dx) + ' ' + sy + ', ' + (tx - dx) + ' ' + ty + ', ' + tx + ' ' + ty;
            var selected = (_wfDrill.kind === 'connection' && _wfDrill.edgeIndex === edge.index);

            // Active edge: wavefront crossing this connection
            var edgeActive = false;
            if (nodeStates) {
                var fromSt = _wfNormalizeStatus((nodeStateMap[edge.from] || {}).status || 'pending');
                var toSt = _wfNormalizeStatus((nodeStateMap[edge.to] || {}).status || 'pending');
                edgeActive = (fromSt === 'completed' && toSt === 'running') || (fromSt === 'running');
            }

            var stroke = edgeActive ? '#ffaa00' : (selected ? '#8cc8ff' : '#5d6f8f');
            var width = edgeActive ? '2.0' : (selected ? '2.2' : '1.4');
            var marker = edgeActive ? 'url(#wf-arrow-active)' : 'url(#wf-arrow)';
            var edgeClass = edgeActive ? ' class="wf-edge-active"' : '';
            var label = '';
            if (edge.label) {
                var lx = (sx + tx) / 2;
                var ly = (sy + ty) / 2 - 6;
                label = '<text x="' + lx + '" y="' + ly + '" fill="#8fa0bb" font-size="9" text-anchor="middle" font-family="monospace" data-wf-edge-index="' + String(edge.index) + '" style="cursor:pointer;">' + _esc(edge.label) + '</text>';
            }
            return '<g>' +
                '<path d="' + path + '" stroke="transparent" stroke-width="10" fill="none" data-wf-edge-index="' + String(edge.index) + '" style="cursor:pointer;"/>' +
                '<path d="' + path + '" stroke="' + stroke + '" stroke-width="' + width + '" fill="none" marker-end="' + marker + '" opacity="0.95"' + edgeClass + ' data-wf-edge-index="' + String(edge.index) + '" style="cursor:pointer;"/>' +
                label +
                '</g>';
        }).join('');

        var nodesSvg = nodes.map(function (node) {
            var pos = positions[node.id];
            if (!pos) return '';

            var stObj = nodeStateMap[node.id] || {};
            var st = _wfNormalizeStatus(stObj.status || 'pending');
            var colors = palette[st] || palette.pending;
            var name = node.name.length > 20 ? (node.name.substring(0, 17) + '...') : node.name;
            var nid = node.id.length > 22 ? (node.id.substring(0, 19) + '...') : node.id;
            var elapsed = typeof stObj.elapsed_ms === 'number' ? (String(stObj.elapsed_ms) + 'ms') : '';
            var active = (_wfDrill.kind === 'node' && _wfDrill.nodeId === node.id);
            var stroke = active ? '#8cc8ff' : colors.stroke;
            var strokeW = active ? '2.4' : '1.5';

            var animClass = '';
            if (nodeStates) {
                if (st === 'running') animClass = ' wf-node-running';
                else if (st === 'completed') animClass = ' wf-node-completing';
                else if (st === 'failed') animClass = ' wf-node-failed';
            }

            return '<g data-wf-node-id="' + _esc(node.id) + '" class="' + animClass.trim() + '" style="cursor:pointer;" transform="translate(0,0)">' +
                '<rect x="' + pos.x + '" y="' + pos.y + '" width="' + nodeW + '" height="' + nodeH + '" rx="6" fill="' + colors.fill + '" stroke="' + stroke + '" stroke-width="' + strokeW + '"/>' +
                '<text x="' + (pos.x + 10) + '" y="' + (pos.y + 18) + '" fill="#dfe9f8" font-size="10" font-family="monospace">' + _esc(name) + '</text>' +
                '<text x="' + (pos.x + 10) + '" y="' + (pos.y + 33) + '" fill="#93a4bf" font-size="9" font-family="monospace">' + _esc(node.type) + ' · ' + _esc(nid) + '</text>' +
                '<text x="' + (pos.x + nodeW - 10) + '" y="' + (pos.y + 18) + '" fill="' + colors.stroke + '" font-size="8" text-anchor="end" font-family="monospace">' + st.toUpperCase() + '</text>' +
                (elapsed ? '<text x="' + (pos.x + nodeW - 10) + '" y="' + (pos.y + 33) + '" fill="#93a4bf" font-size="8" text-anchor="end" font-family="monospace">' + _esc(elapsed) + '</text>' : '') +
                '</g>';
        }).join('');

        _wfGraphMeta = {
            nodeMap: nodeMap,
            nodes: nodes,
            connections: connections,
            adjacency: adjacency,
            reverse: reverse,
            positions: positions
        };

        svg.innerHTML =
            '<defs>' +
            '<marker id="wf-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">' +
            '<path d="M0,0 L8,3 L0,6 z" fill="#5d6f8f"></path>' +
            '</marker>' +
            '<marker id="wf-arrow-active" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">' +
            '<path d="M0,0 L8,3 L0,6 z" fill="#ffaa00"></path>' +
            '</marker>' +
            '</defs>' +
            edgesSvg +
            nodesSvg;
    }

    function _wfRenderExecution(payload) {
        if (!payload || typeof payload !== 'object') return;
        _wfLastExec = payload;

        if (payload.workflow_id && (!_wfSelectedId || _wfSelectedId !== payload.workflow_id)) {
            _wfSelectedId = payload.workflow_id;
            renderWorkflowList();
        }
        if (payload.execution_id) {
            _wfCurrentExecutionId = payload.execution_id;
        }
        if (payload.workflow_id && (!_wfLoadedDef || _wfLoadedDef.id !== payload.workflow_id)) {
            callTool('workflow_get', { workflow_id: payload.workflow_id });
        }

        var status = _wfNormalizeStatus(payload.status || 'pending');
        if (status === 'running') {
            _wfSetBadge('running', 'RUNNING · ' + (_wfCurrentExecutionId || '...'));
            if (_wfCurrentExecutionId) _wfStartPolling(_wfCurrentExecutionId);
        } else if (status === 'completed') {
            _wfSetBadge('completed', 'COMPLETED');
            _wfStopPolling();
        } else if (status === 'failed') {
            _wfSetBadge('failed', 'FAILED');
            _wfStopPolling();
        } else {
            _wfSetBadge('idle', 'IDLE');
        }

        var lines = [];
        if (payload.workflow_id) lines.push('Workflow: ' + payload.workflow_id);
        if (payload.execution_id) lines.push('Execution: ' + payload.execution_id);
        lines.push('Status: ' + String(payload.status || 'unknown').toUpperCase());
        if (typeof payload.elapsed_ms === 'number') lines.push('Elapsed: ' + String(payload.elapsed_ms) + 'ms');
        if (payload.error) lines.push('Error: ' + payload.error);
        _wfSetExecStatus(lines.join('\n'), !!payload.error || status === 'failed');

        renderWorkflowNodeStates(_wfLoadedDef, payload.node_states || null);
        renderWorkflowGraph(_wfLoadedDef, payload.node_states || null);
        renderWorkflowList(); // Update executing highlight on every poll
        _wfRenderDrillDetail();
    }

    function handleWorkflowToolResult(toolName, msg, rawText) {
        var payload = msg.error ? null : _wfParsePayload(rawText);

        if (toolName === 'workflow_list') {
            if (msg.error) {
                _wfSetExecStatus('workflow_list failed: ' + msg.error, true);
                return;
            }
            var list = [];
            if (payload && Array.isArray(payload.workflows)) list = payload.workflows;
            else if (Array.isArray(payload)) list = payload;

            _wfCatalog = list.map(function (w, idx) {
                var id = String((w && (w.id || w.workflow_id || w.name)) || ('workflow_' + String(idx + 1)));
                return {
                    id: id,
                    name: String((w && (w.name || w.id || w.workflow_id)) || id),
                    description: String((w && w.description) || ''),
                    node_count: typeof (w && w.node_count) === 'number'
                        ? w.node_count
                        : (Array.isArray(w && w.nodes) ? w.nodes.length : 0)
                };
            });

            if (_wfCatalog.length > 0) {
                var exists = _wfCatalog.some(function (w) { return w.id === _wfSelectedId; });
                if (!exists) _wfSelectedId = _wfCatalog[0].id;
            } else {
                _wfSelectedId = '';
                _wfLoadedDef = null;
                _wfGraphMeta = null;
                _wfDrill = { kind: 'workflow', nodeId: '', edgeIndex: -1, workflowId: '' };
            }

            renderWorkflowList();
            if (_wfSelectedId && (!_wfLoadedDef || _wfLoadedDef.id !== _wfSelectedId)) {
                callTool('workflow_get', { workflow_id: _wfSelectedId });
            } else if (!_wfSelectedId) {
                renderWorkflowGraph(null, null);
                renderWorkflowNodeStates(null, null);
                _wfRenderDrillDetail();
            }
            _wfSetExecStatus('Loaded ' + String(_wfCatalog.length) + ' workflows.', false);
            return;
        }

        if (toolName === 'workflow_get') {
            if (msg.error) {
                _wfSetExecStatus('workflow_get failed: ' + msg.error, true);
                return;
            }
            if (payload && payload.error) {
                _wfSetExecStatus('workflow_get failed: ' + payload.error, true);
                return;
            }
            if (!payload || !Array.isArray(payload.nodes)) {
                _wfSetExecStatus('workflow_get returned invalid workflow definition.', true);
                return;
            }

            var prevWorkflowId = _wfLoadedDef && _wfLoadedDef.id ? String(_wfLoadedDef.id) : '';
            _wfLoadedDef = payload;
            if (payload.id) _wfSelectedId = String(payload.id);
            var loadedWorkflowId = String(_wfLoadedDef.id || _wfSelectedId || '');
            if (!prevWorkflowId || prevWorkflowId !== loadedWorkflowId || _wfDrill.workflowId !== loadedWorkflowId) {
                _wfDrill = { kind: 'workflow', nodeId: '', edgeIndex: -1, workflowId: loadedWorkflowId };
            }
            renderWorkflowList();

            var matchingNodeStates = null;
            if (_wfLastExec && _wfLoadedDef && _wfLastExec.workflow_id === _wfLoadedDef.id) {
                matchingNodeStates = _wfLastExec.node_states || null;
            }
            renderWorkflowGraph(_wfLoadedDef, matchingNodeStates);
            renderWorkflowNodeStates(_wfLoadedDef, matchingNodeStates);
            _wfRenderDrillDetail();
            _wfSetExecStatus('Loaded definition for workflow: ' + (_wfLoadedDef.id || _wfSelectedId), false);
            return;
        }

        if (toolName === 'workflow_execute' || toolName === 'workflow_status') {
            if (msg.error) {
                _wfSetBadge('failed', 'FAILED');
                _wfSetExecStatus(toolName + ' failed: ' + msg.error, true);
                _wfStopPolling();
                return;
            }
            if (!payload || typeof payload !== 'object') {
                _wfSetExecStatus(toolName + ' returned non-JSON output.', true);
                return;
            }
            if (payload.error) {
                _wfSetBadge('failed', 'FAILED');
                _wfSetExecStatus(payload.error, true);
                _wfStopPolling();
                return;
            }

            _wfRenderExecution(payload);

            if (toolName === 'workflow_execute' && payload.execution_id && _wfNormalizeStatus(payload.status) !== 'running') {
                callTool('workflow_status', { execution_id: payload.execution_id });
            }
            return;
        }
    }

    function handleWorkflowActivity(event) {
        if (!event || !event.tool) return;

        // Don't add sentinel events to the visible activity log
        if (event.durationMs === -1 || event.durationMs === -2) {
            // Remove from activity log — these are live workflow trace events, not user-visible entries
            var idx = _activityLog.indexOf(event);
            if (idx >= 0) _activityLog.splice(idx, 1);
        }

        var payload = _wfParsePayload(event.result || null);
        if (!payload || typeof payload !== 'object') return;

        // Auto-load workflow definition if we don't have it
        if (payload.workflow_id && (!_wfLoadedDef || _wfLoadedDef.id !== payload.workflow_id)) {
            callTool('workflow_get', { workflow_id: payload.workflow_id });
            // Also refresh the list so it appears
            callTool('workflow_list', {});
        }

        _wfRenderExecution(payload);
    }

    // ── MEMORY INLINE DRILL ──
    var _openDrillKey = null;
    var _bagDrillCache = {}; // key -> latest resolved bag_get payload for publish prefill
    var _bagReadFallbackPending = {}; // key -> true when bag_get fallback to bag_read_doc is in-flight
    var _bagGitMeta = {};    // key -> latest git metadata for drill header context
    var _gitAvailable = true;  // assume available until probed
    var _gitProbed = false;    // true after first checkGitAvailable response

    function _safeBagKeyId(key) {
        return String(key || '').replace(/[^a-zA-Z0-9_-]/g, '_');
    }

    function drillMemItem(key) {
        var contentDiv = document.getElementById('drill-' + key);
        // Toggle: if already open, close it
        if (contentDiv && contentDiv.style.display !== 'none') {
            contentDiv.style.display = 'none';
            _openDrillKey = null;
            return;
        }
        // Close any previously open drill
        if (_openDrillKey) {
            var prev = document.getElementById('drill-' + _openDrillKey);
            if (prev) prev.style.display = 'none';
        }
        _openDrillKey = key;
        if (contentDiv) {
            contentDiv.style.display = 'block';
            contentDiv.innerHTML = '<div style="padding:8px 12px;color:var(--text-dim);font-size:11px;">Loading...</div>';
        }
        delete _bagReadFallbackPending[key];
        callTool('bag_get', { key: key });
    }
    window.drillMemItem = drillMemItem;

    function closeMemDetail() {
        var detail = document.getElementById('mem-detail');
        if (detail) detail.style.display = 'none';
    }
    window.closeMemDetail = closeMemDetail;

    var _commitConfirmTimer = null;
    function commitBagVersion(btn) {
        var key = btn.getAttribute('data-bag-key');
        if (!key) return;
        if (!_gitAvailable) {
            mpToast('Git is not available on this system. Install Git to use versioning.', 'error', 4000);
            return;
        }
        // Two-click confirm: first click arms, second click within 3s fires
        if (btn.dataset.armed !== 'true') {
            btn.dataset.armed = 'true';
            btn.textContent = 'Confirm Commit?';
            btn.style.color = '#f59e0b';
            clearTimeout(_commitConfirmTimer);
            _commitConfirmTimer = setTimeout(function () {
                btn.dataset.armed = '';
                btn.textContent = 'Commit Version';
                btn.style.color = 'var(--accent)';
            }, 3000);
            return;
        }
        // Armed and clicked again — actually commit
        btn.dataset.armed = '';
        clearTimeout(_commitConfirmTimer);
        btn.textContent = 'Committing...';
        btn.disabled = true;
        vscode.postMessage({ command: 'commitBagVersion', key: key });
    }
    window.commitBagVersion = commitBagVersion;

    function handleBagCommitResult(msg) {
        var safeKey = _safeBagKeyId(msg.key || '');
        var btn = document.getElementById('commit-btn-' + safeKey);

        if (msg.key) {
            var existing = _bagGitMeta[msg.key] || {};
            _bagGitMeta[msg.key] = {
                key: msg.key,
                filePath: msg.filePath || existing.filePath || '',
                headSha: msg.sha || existing.headSha || '',
                commitCount: (typeof msg.commitCount === 'number') ? msg.commitCount : (existing.commitCount || 0),
                latestWhen: msg.latestWhen || existing.latestWhen || '',
                latestSubject: msg.latestSubject || existing.latestSubject || '',
                diffStat: msg.diffStat || existing.diffStat || ''
            };
        }

        if (msg.error) {
            if (btn) { btn.textContent = 'Failed'; btn.disabled = false; btn.style.color = '#e11d48'; }
            console.error('[BagGit]', msg.error);
            return;
        }
        if (msg.noChanges) {
            if (btn) { btn.textContent = 'No changes'; btn.disabled = false; }
            setTimeout(function () { if (btn) btn.textContent = 'Commit Version'; }, 2000);
            if (msg.key) requestBagGitInfo(msg.key);
            return;
        }
        if (btn) {
            btn.textContent = 'Committed (' + (msg.sha || '') + ')';
            btn.style.color = '#22c55e';
            setTimeout(function () {
                btn.textContent = 'Commit Version';
                btn.style.color = 'var(--accent)';
                btn.disabled = false;
            }, 2000);
        }
        if (msg.key) requestBagGitInfo(msg.key);
    }

    function requestBagGitInfo(key) {
        if (!key) return;
        var entry = _bagDrillCache[key] || {};
        var meta = _bagGitMeta[key] || {};
        vscode.postMessage({
            command: 'bagGitInspect',
            key: key,
            itemType: entry.type || '',
            filePath: meta.filePath || ''
        });
    }
    window.requestBagGitInfo = requestBagGitInfo;

    function _renderBagGitInfo(key) {
        if (!key) return;
        var safeKey = _safeBagKeyId(key);
        var host = document.getElementById('bag-git-meta-' + safeKey);
        if (!host) return;

        if (!_gitAvailable && _gitProbed) {
            host.innerHTML = '<div style="color:var(--text-dim);">Git not available — install Git to enable versioning, diffs, and snapshot history.</div>';
            return;
        }

        var meta = _bagGitMeta[key];
        if (!meta) {
            host.innerHTML = '<div style="color:var(--text-dim);">Loading git details...</div>';
            return;
        }

        if (meta.error) {
            host.innerHTML = '<div style="color:#e11d48;">' + _esc(meta.error) + '</div>';
            return;
        }

        var tracked = !!meta.tracked;
        var commitCount = Number(meta.commitCount || 0);
        var filePath = String(meta.filePath || '');
        var keyJs = _esc(key).replace(/'/g, "\\'");
        var btnBase = 'font-size:9px;padding:2px 8px;cursor:pointer;background:var(--surface2);border:1px solid var(--border);border-radius:3px;';
        var openBtn = '<button onclick="openBagSnapshotFile(\'' + keyJs + '\')" style="' + btnBase + 'color:var(--text);">Open Snapshot</button>';
        var refreshBtn = '<button onclick="requestBagGitInfo(\'' + keyJs + '\')" style="' + btnBase + 'color:var(--text-dim);">Refresh</button>';
        var diffBtn;
        if (tracked && commitCount >= 2) {
            diffBtn = '<button onclick="viewBagSnapshotDiff(\'' + keyJs + '\')" style="' + btnBase + 'color:#60a5fa;">View Last Diff</button>';
        } else {
            diffBtn = '<button disabled style="' + btnBase + 'color:var(--text-dim);opacity:0.45;cursor:not-allowed;">View Last Diff</button>';
        }

        var latestLine = tracked
            ? ('Latest commit <span style="color:#22c55e;">' + _esc(meta.headSha || '?') + '</span>' +
                (meta.latestWhen ? ' • ' + _esc(meta.latestWhen) : '') +
                (meta.latestSubject ? ' • ' + _esc(meta.latestSubject) : ''))
            : 'Not committed yet.';

        var diffLine = (tracked && commitCount >= 2)
            ? (meta.diffStat ? _esc(meta.diffStat) : 'Diff available between the last two snapshots.')
            : 'Create at least two commits to compare changes.';

        host.innerHTML =
            '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:10px;">' +
            '<div style="min-width:0;">' +
            '<div style="color:var(--text);">Snapshot file: <span style="color:var(--accent);">' + _esc(filePath || 'bag_docs/...') + '</span></div>' +
            '<div style="color:var(--text-dim);margin-top:2px;">' + latestLine + ' • ' + commitCount + ' commit' + (commitCount === 1 ? '' : 's') + '</div>' +
            '<div style="color:var(--text-dim);margin-top:2px;">' + diffLine + '</div>' +
            '<div style="color:var(--text-dim);margin-top:4px;">Live memory is editable. Commits create a git history you can diff, audit, and restore.</div>' +
            '</div>' +
            '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end;">' +
            openBtn + diffBtn + refreshBtn +
            '</div>' +
            '</div>';
    }

    function handleBagGitInfo(msg) {
        if (!msg || !msg.key) return;
        _bagGitMeta[msg.key] = msg;
        _renderBagGitInfo(msg.key);
    }

    function openBagSnapshotFile(key) {
        if (!key) return;
        var meta = _bagGitMeta[key] || {};
        var entry = _bagDrillCache[key] || {};
        vscode.postMessage({
            command: 'openBagDocFile',
            key: key,
            itemType: entry.type || '',
            filePath: meta.filePath || ''
        });
    }
    window.openBagSnapshotFile = openBagSnapshotFile;

    function viewBagSnapshotDiff(key) {
        if (!key) return;
        var safeKey = _safeBagKeyId(key);
        var diffDiv = document.getElementById('bag-git-diff-' + safeKey);
        if (diffDiv) {
            diffDiv.style.display = 'block';
            diffDiv.innerHTML = '<div style="color:var(--text-dim);padding:6px 0;">Loading diff...</div>';
        }
        var meta = _bagGitMeta[key] || {};
        var entry = _bagDrillCache[key] || {};
        vscode.postMessage({
            command: 'bagGitDiff',
            key: key,
            itemType: entry.type || '',
            filePath: meta.filePath || ''
        });
    }
    window.viewBagSnapshotDiff = viewBagSnapshotDiff;

    var _DIFF_TRUNCATE_CHARS = 5000;
    function handleBagGitDiffResult(msg) {
        if (!msg || !msg.key) return;
        var safeKey = _safeBagKeyId(msg.key);
        var diffDiv = document.getElementById('bag-git-diff-' + safeKey);
        if (!diffDiv) return;
        diffDiv.style.display = 'block';
        if (msg.error) {
            diffDiv.innerHTML = '<div style="color:#e11d48;padding:6px 0;">' + _esc(msg.error) + '</div>';
            return;
        }

        var rawDiff = msg.diff || '';
        var truncated = rawDiff.length > _DIFF_TRUNCATE_CHARS;
        var displayDiff = truncated ? rawDiff.slice(0, _DIFF_TRUNCATE_CHARS) : rawDiff;
        var keyJs = _esc(msg.key).replace(/'/g, "\\'");
        var title = 'Diff ' + _esc(msg.fromSha || '?') + ' → ' + _esc(msg.toSha || '?');
        var truncMsg = truncated
            ? '<div style="color:#f59e0b;font-size:9px;margin-top:4px;">Diff truncated (' + rawDiff.length + ' chars). ' +
            '<button onclick="openBagNativeDiff(\'' + keyJs + '\')" style="font-size:9px;padding:1px 6px;cursor:pointer;background:var(--surface2);color:#60a5fa;border:1px solid var(--border);border-radius:3px;">Open Full Diff in Editor</button></div>'
            : '<div style="margin-top:4px;"><button onclick="openBagNativeDiff(\'' + keyJs + '\')" style="font-size:9px;padding:1px 6px;cursor:pointer;background:var(--surface2);color:#60a5fa;border:1px solid var(--border);border-radius:3px;">Open in Editor</button></div>';

        diffDiv.innerHTML =
            '<div style="padding:6px 8px;border:1px solid var(--border);background:var(--surface2);">' +
            '<div style="font-size:10px;color:var(--text-dim);margin-bottom:6px;">' + title + '</div>' +
            '<pre style="margin:0;white-space:pre-wrap;word-break:break-word;max-height:220px;overflow:auto;color:var(--text);font-size:10px;line-height:1.45;">' + _esc(displayDiff) + (truncated ? '\n...' : '') + '</pre>' +
            truncMsg +
            '</div>';
    }

    function openBagNativeDiff(key) {
        if (!key) return;
        var meta = _bagGitMeta[key] || {};
        var entry = _bagDrillCache[key] || {};
        vscode.postMessage({
            command: 'bagGitOpenNativeDiff',
            key: key,
            itemType: entry.type || '',
            filePath: meta.filePath || ''
        });
    }
    window.openBagNativeDiff = openBagNativeDiff;

    function _objFromMaybeJson(input) {
        if (input && typeof input === 'object' && !Array.isArray(input)) return input;
        if (typeof input !== 'string') return null;
        try {
            var parsed = JSON.parse(input);
            return (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) ? parsed : null;
        } catch (e) {
            return null;
        }
    }

    function _tagsFromAny(value) {
        if (Array.isArray(value)) {
            return value.map(function (t) { return String(t || '').trim(); }).filter(Boolean);
        }
        if (typeof value === 'string') {
            return value.split(',').map(function (t) { return t.trim(); }).filter(Boolean);
        }
        return [];
    }

    function _deriveComplexityFromNodeCount(nodeCount) {
        if (nodeCount <= 3) return 'simple';
        if (nodeCount <= 8) return 'moderate';
        if (nodeCount <= 15) return 'complex';
        return 'advanced';
    }

    function _deriveEstTimeFromNodeCount(nodeCount) {
        if (nodeCount <= 2) return 'instant';
        if (nodeCount <= 6) return 'fast';
        if (nodeCount <= 12) return 'moderate';
        if (nodeCount <= 24) return 'long';
        return 'extended';
    }

    function _prepareMarketplacePrefillFromBag(entry) {
        var key = String((entry && entry.key) || '');
        var value = entry ? entry.value : null;
        var source = _objFromMaybeJson(value) || {};
        var sourceDocType = String(source.docType || source.sourceDocType || 'workflow').toLowerCase();
        var category = String(
            source.category ||
            (source.meta && source.meta.marketplace && source.meta.marketplace.category) ||
            'memory'
        ).toLowerCase();
        if (!MP_CATEGORIES[category]) category = 'other';

        var fallbackRole = String(
            source.workflowRole ||
            source.role ||
            (source.meta && source.meta.marketplace && source.meta.marketplace.workflow_role) ||
            'automation'
        ).toLowerCase();

        var rawBody =
            source.workflowDefinition ||
            source.body ||
            source.workflow ||
            value;

        var workflowDef = _normalizeWorkflowDefinition(rawBody, {
            name: source.name || key,
            description: source.description || ('Imported from FelixBag key: ' + key),
            workflowRole: fallbackRole,
            category: category,
            sourceDocType: sourceDocType
        });

        var wrapped = false;
        if (!workflowDef) {
            var fallbackBody;
            if (typeof value === 'string') {
                fallbackBody = value;
            } else {
                try {
                    fallbackBody = JSON.stringify(value || {}, null, 2);
                } catch (e2) {
                    fallbackBody = String(value || '');
                }
            }

            workflowDef = _buildWrappedWorkflowDefinition({
                name: source.name || key || 'FelixBag Item',
                description: source.description || ('Auto-wrapped from FelixBag key: ' + key),
                workflowRole: fallbackRole || 'knowledge',
                sourceDocType: sourceDocType || 'workflow',
                category: category || 'other',
                body: fallbackBody
            }, 'felixbag:' + key);
            wrapped = true;
        }

        var tags = _tagsFromAny(source.tags);
        var role = _detectWorkflowRole(sourceDocType, source, tags);
        if (WORKFLOW_ROLE_ORDER.indexOf(role) === -1) role = 'automation';

        var nodeCount = Array.isArray(workflowDef.nodes) ? workflowDef.nodes.length : 0;
        var complexity = String(source.complexity || '').toLowerCase();
        if (['simple', 'moderate', 'complex', 'advanced'].indexOf(complexity) === -1) {
            complexity = _deriveComplexityFromNodeCount(nodeCount);
        }
        var estTime = String(source.estTime || source.estimatedTime || '').toLowerCase();
        if (['instant', 'fast', 'moderate', 'long', 'extended'].indexOf(estTime) === -1) {
            estTime = _deriveEstTimeFromNodeCount(nodeCount);
        }

        return {
            role: role,
            name: String(source.name || workflowDef.name || key),
            description: String(source.description || workflowDef.description || ('Imported from FelixBag key: ' + key)),
            body: JSON.stringify(workflowDef, null, 2),
            tags: tags.join(', '),
            category: category,
            version: String(source.version || '1.0.0'),
            complexity: complexity,
            estTime: estTime,
            wrapped: wrapped
        };
    }

    function _setPublishModalField(id, value) {
        var el = document.getElementById(id);
        if (!el || typeof value === 'undefined' || value === null) return;
        el.value = value;
    }

    function publishBagToMarketplace(btn) {
        var key = btn.getAttribute('data-bag-key');
        if (!key) return;

        var entry = _bagDrillCache[key];
        if (!entry) {
            mpToast('Open the item first to load publish details.', 'error', 3200);
            return;
        }

        var prefill = _prepareMarketplacePrefillFromBag(entry);

        // Fix 1: Run safety scan on prefilled content before opening modal
        var safetyResult = scanDocSafety({
            name: prefill.name,
            description: prefill.description,
            body: prefill.body,
            tags: prefill.tags ? prefill.tags.split(',').map(function (t) { return t.trim(); }) : []
        });

        if (safetyResult.trustLevel === 'blocked') {
            mpToast('BLOCKED: Content contains critical safety flags (' +
                safetyResult.flags.filter(function (f) { return f.severity === 'critical'; })
                    .map(function (f) { return f.pattern; }).join(', ') +
                '). Remove flagged content before publishing.', 'error', 8000);
            return;
        }

        _setPublishModalField('pub-wf-role', prefill.role);
        _setPublishModalField('pub-wf-name', prefill.name);
        _setPublishModalField('pub-wf-desc', prefill.description);
        _setPublishModalField('pub-wf-json', prefill.body);
        _setPublishModalField('pub-wf-tags', prefill.tags);
        _setPublishModalField('pub-wf-category', prefill.category);
        _setPublishModalField('pub-wf-version', prefill.version);
        _setPublishModalField('pub-wf-complexity', prefill.complexity);
        _setPublishModalField('pub-wf-time', prefill.estTime);

        var modal = document.getElementById('publish-wf-modal');
        if (modal) modal.classList.add('active');

        // Trigger live redaction preview on the body field
        if (_privacySettings.autoRedact) {
            vscode.postMessage({ command: 'nostrRedactPreview', text: prefill.body });
        }

        if (safetyResult.trustLevel === 'flagged') {
            mpToast('WARNING: Safety scan flagged this content (score: ' + safetyResult.score +
                '). Review flagged items: ' +
                safetyResult.flags.map(function (f) { return f.pattern + ' in ' + f.location; }).join(', ') +
                '. Auto-redaction is ' + (_privacySettings.autoRedact ? 'ON' : 'OFF') + '.',
                'error', 8000);
        } else if (prefill.wrapped) {
            mpToast('This item was auto-wrapped into a workflow. Review fields before publishing.', 'info', 5200);
        } else {
            mpToast('Publish form prefilled from FelixBag item (safety: SAFE, score: ' + safetyResult.score + ')', 'success', 3000);
        }
    }
    window.publishBagToMarketplace = publishBagToMarketplace;

    function _renderLineNumbered(text) {
        var lines = String(text).split('\n');
        var gutterW = String(lines.length).length;
        var html = '';
        for (var i = 0; i < lines.length; i++) {
            var num = String(i + 1);
            while (num.length < gutterW) num = ' ' + num;
            html += '<div style="display:flex;"><span style="color:var(--text-dim);opacity:0.4;user-select:none;padding:0 8px 0 6px;text-align:right;min-width:' + (gutterW * 8 + 12) + 'px;border-right:1px solid var(--border);margin-right:8px;">' + num + '</span><span style="color:var(--text);white-space:pre-wrap;word-break:break-all;flex:1;padding-right:8px;">' + _esc(lines[i]) + '</span></div>';
        }
        return html;
    }

    function _renderMemItem(key, name, type, extra) {
        var displayName = name || key;
        var shortId = key.length > 8 ? key.substring(0, 8) + '…' : key;
        var typeHtml = type ? ' <span style="font-size:9px;font-weight:700;text-transform:uppercase;padding:1px 6px;border-radius:3px;background:var(--surface2);color:var(--accent);">' + _esc(type) + '</span>' : '';
        var previewHtml = extra ? ' <span style="color:var(--text-dim);font-size:10px;font-style:italic;">— ' + _esc(extra) + '</span>' : '';
        return '<div>' +
            '<div class="memory-item" onclick="drillMemItem(\'' + _esc(key).replace(/'/g, "\\'") + '\')" style="cursor:pointer;">' +
            '<div class="mi-header">' +
            '<span class="mi-name" title="' + _esc(key) + '">' + _esc(displayName) + '</span>' +
            typeHtml + previewHtml +
            '</div>' +
            '<div class="mi-meta"><span class="mi-id">' + _esc(shortId) + '</span></div>' +
            '</div>' +
            '<div id="drill-' + _esc(key) + '" style="display:none;background:var(--surface);border:1px solid var(--border);border-top:none;max-height:400px;overflow:auto;font-family:monospace;font-size:11px;line-height:1.5;"></div>' +
            '</div>';
    }

    function formatToolOutput(raw) {
        // Try to parse and detect error/guidance fields
        var obj = null;
        try { obj = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch (e) { return raw; }
        if (!obj || typeof obj !== 'object') return raw;

        if (obj.status === 'yielded' && obj.hold_id) {
            var yl = [
                'HOLD YIELDED',
                'HOLD ID: ' + String(obj.hold_id),
                'REASON: ' + String(obj.reason || 'n/a')
            ];
            if (obj.ai_choice !== undefined) yl.push('AI CHOICE: ' + String(obj.ai_choice));
            if (obj.ai_confidence !== undefined) yl.push('AI CONFIDENCE: ' + String(obj.ai_confidence));
            if (obj.blocking !== undefined) yl.push('BLOCKING: ' + String(!!obj.blocking));
            if (obj.decision_matrix && typeof obj.decision_matrix === 'object') {
                var dm = obj.decision_matrix;
                yl.push('DECISION MATRIX: actions=' + String(dm.action_count || 0) + ', best=' + String(dm.best_action_label || dm.best_action || 'n/a'));
            }
            if (obj.message) yl.push('', String(obj.message));
            return yl.join('\n');
        }

        if (obj.status === 'resolved' && obj.hold_id) {
            var rl = [
                'HOLD RESOLVED',
                'HOLD ID: ' + String(obj.hold_id),
                'ACTION: ' + String(obj.action || 'n/a')
            ];
            if (obj.mode) rl.push('MODE: ' + String(obj.mode));
            if (obj.note) rl.push('NOTE: ' + String(obj.note));
            return rl.join('\n');
        }

        // If result has an "error" field, format as guidance
        if (obj.error) {
            var lines = ['ERROR: ' + obj.error, ''];
            if (String(obj.error).toLowerCase().indexOf('no active hold to resolve') >= 0) {
                lines.push('GUIDANCE: Use the exact hold_id returned by hold_yield.');
                lines.push('If this hold was non-blocking, retry hold_resolve with that hold_id to record resolution.');
                lines.push('');
            }
            var keys = Object.keys(obj);
            for (var i = 0; i < keys.length; i++) {
                var k = keys[i];
                if (k === 'error') continue;
                var v = obj[k];
                if (Array.isArray(v) && v.length === 0) continue;
                lines.push(k.replace(/_/g, ' ').toUpperCase() + ': ' + (typeof v === 'object' ? JSON.stringify(v) : v));
            }
            return lines.join('\n');
        }
        return raw;
    }

    function handleToolResult(msg) {
        var toolName = _pendingTools[msg.id] || (msg && msg._toolName ? String(msg._toolName) : '');
        var pendingTabKey = _pendingToolTabs[msg.id] || '';
        var pendingMeta = _pendingToolMeta[msg.id] || null;
        delete _pendingTools[msg.id];
        delete _pendingToolTabs[msg.id];
        delete _pendingToolMeta[msg.id];

        if (pendingMeta && pendingMeta.suppressDefault) {
            if (msg && msg.error) {
                if (typeof pendingMeta.reject === 'function') pendingMeta.reject(new Error(String(msg.error)));
                else if (typeof pendingMeta.resolve === 'function') pendingMeta.resolve(msg);
                return;
            }
            if (typeof pendingMeta.resolve === 'function') pendingMeta.resolve(msg);
            return;
        }

        // Hub info enrichment for slot metadata cards — silent, no output
        if (toolName === 'hub_info_enrich' && !msg.error) {
            try {
                var hubData = typeof msg.data === 'string' ? JSON.parse(msg.data) : msg.data;
                if (hubData && hubData.content && hubData.content[0] && hubData.content[0].text) {
                    hubData = JSON.parse(hubData.content[0].text);
                }
                if (hubData && hubData.id) {
                    _slotHubInfoCache[hubData.id] = hubData;
                    if (_lastSlotsData) renderSlots(_lastSlotsData);
                }
            } catch (e) { /* silently ignore hub_info parse failures */ }
            return;
        }

        // Agent MCP console responses — route to slot tab timeline
        if (toolName === 'agent_chat' || toolName === '__agent_chat__' || toolName === '__achat_tool__' || toolName === '__agent_chat_loop__') {
            var isLoopIter = (toolName === '__agent_chat_loop__');
            var isAchatToolCall = (toolName === '__achat_tool__');
            var keepBusy = !!(pendingMeta && pendingMeta.keepBusy);
            if (!isLoopIter && !(isAchatToolCall && keepBusy)) _setAchatBusy(false);
            var activeTab = pendingTabKey ? _achatTabs[pendingTabKey] : _getActiveAchatTab();
            if (msg.error) {
                _appendAchatMsg('error', String(msg.error || 'Unknown error'), Date.now(), activeTab);
                if (isLoopIter && activeTab && activeTab._loopState) {
                    _setAchatBusy(false);
                    activeTab._loopState = null;
                }
                return;
            }
            try {
                var raw = parseToolData(msg.data);
                var payload = raw;
                if (typeof payload === 'string') {
                    try { payload = JSON.parse(payload); } catch (e) { }
                }

                if (payload && payload._cached) {
                    var _cacheId = String(payload._cached || '').trim();
                    var _cacheSize = parseInt(payload._size, 10) || 0;
                    // Preserve session_id from cached stub before following through
                    if (payload.session_id && activeTab) {
                        activeTab.sessionId = payload.session_id;
                    }
                    _appendAchatCacheHint(_cacheId, _cacheSize, activeTab, toolName);
                    var _cachedMeta = {};
                    if (activeTab && activeTab.key) _cachedMeta.tabKey = activeTab.key;
                    callTool('get_cached', { cache_id: _cacheId }, toolName, _cachedMeta);
                    return;
                }

                if (toolName === '__achat_tool__') {
                    if (payload && payload.error) {
                        _appendAchatMsg('error', String(payload.error), Date.now(), activeTab);
                        return;
                    }
                    if (payload && payload.status === 'queued' && payload.session_id) {
                        _appendAchatMsg('system-info',
                            'Live update queued for ' + String(payload.session_id).slice(0, 28) +
                            ' · pending ' + String(payload.pending_messages || 0),
                            Date.now(), activeTab);
                        return;
                    }
                    var pretty = '';
                    try { pretty = typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2); }
                    catch (e2) { pretty = String(payload); }
                    if (pretty.length > 6000) pretty = pretty.substring(0, 6000) + '\n…[truncated]';
                    _appendAchatMsg('assistant', pretty, Date.now(), activeTab);
                    return;
                }

                var resp = payload;
                if (resp && resp.error) {
                    _appendAchatMsg('error', String(resp.error), Date.now(), activeTab);
                    if (isLoopIter && activeTab && activeTab._loopState) {
                        _setAchatBusy(false);
                        activeTab._loopState = null;
                    }
                    return;
                }

                var tabSlot = (resp && resp.slot !== undefined) ? parseInt(resp.slot, 10) : (activeTab ? activeTab.slot : _achatSlot);
                var tab = _ensureAchatTab(tabSlot);
                if (tab && (!_achatActiveTabKey || _achatActiveTabKey === tab.key)) {
                    _activateAchatTab(tab.key, false);
                }

                if (resp && resp.session_id && tab) {
                    tab.sessionId = resp.session_id;
                }
                _refreshAchatMeta();

                var elapsed = _achatSendTime ? Math.round((Date.now() - _achatSendTime) / 1000) : 0;
                var resultObj = (resp && resp.result) ? resp.result : (resp || {});
                if (resultObj.error) {
                    _appendAchatMsg('error', String(resultObj.error), Date.now(), tab);
                    if (isLoopIter && tab && tab._loopState) {
                        _setAchatBusy(false);
                        tab._loopState = null;
                    }
                    return;
                }

                // Dynamic reappropriation: detect REAPPROPRIATE:<N>:<reason> in final_answer
                var _reapAnswer = String(resultObj.final_answer || resultObj.answer || '').trim();
                var _reapMatch = _reapAnswer.match(/^REAPPROPRIATE:(\d+):(.+)$/i);
                if (isLoopIter && tab && tab._loopState && _reapMatch) {
                    var reqIter = parseInt(_reapMatch[1], 10) || 0;
                    var reqReason = String(_reapMatch[2] || 'no reason given').trim();
                    var ls = tab._loopState;
                    var approvalMode = (tab.agentConfig || {}).resourceApprovalMode || 'capped';
                    var guardMax = parseInt(((tab.agentConfig || {}).guardMaxToolCalls) || 400, 10);
                    var approved = false;
                    var grantedAmt = 0;

                    if (approvalMode === 'auto_all') {
                        grantedAmt = Math.min(reqIter, 50);
                        approved = true;
                    } else if (approvalMode === 'capped') {
                        grantedAmt = Math.min(reqIter, 20);
                        approved = (ls.maxIterations + grantedAmt) <= guardMax;
                    }

                    if (approved && grantedAmt > 0) {
                        ls.maxIterations += grantedAmt;
                        _appendAchatMsg('system-info',
                            'REAPPROPRIATION GRANTED: +' + grantedAmt + ' iterations (now ' + ls.maxIterations + ' max). Reason: ' + reqReason,
                            Date.now(), tab);
                        ls.iteration += 1;
                        ls.nextMessage = 'Your request for ' + grantedAmt + ' additional iterations was approved. You now have ' +
                            (ls.maxIterations - ls.iteration) + ' iterations remaining. Continue your task.';
                        _fireAgentIteration(tab);
                    } else {
                        _appendAchatMsg('system-info',
                            'REAPPROPRIATION DENIED: requested +' + reqIter + ' iterations (mode=' + approvalMode + '). Reason: ' + reqReason,
                            Date.now(), tab);
                        ls.iteration += 1;
                        ls.nextMessage = 'Your iteration request was denied. You have ' +
                            Math.max(0, ls.maxIterations - ls.iteration) + ' iterations remaining. Wrap up with final_answer.';
                        _fireAgentIteration(tab);
                    }
                    return;
                }

                var toolCalls = resultObj.tool_calls || [];
                // Only use end-of-run tool dump as fallback when live ordered cards were not rendered.
                var _respSession = (resp && resp.session_id) ? String(resp.session_id) : '';
                var _liveCount = 0;
                if (tab && _respSession && tab._sseBySession && tab._sseBySession[_respSession]) {
                    _liveCount = parseInt(tab._sseBySession[_respSession], 10) || 0;
                } else if (tab && tab._sseToolCount) {
                    _liveCount = parseInt(tab._sseToolCount, 10) || 0;
                }
                var sseAlreadyShowed = toolCalls.length > 0 && _liveCount >= toolCalls.length;
                if (toolCalls.length && !sseAlreadyShowed) {
                    _appendAchatToolTrace(toolCalls, tab);
                    _logAchatSyntheticActivity(toolCalls, tab ? tab.slot : tabSlot);
                }
                // Reset live counters for this session
                if (tab) {
                    if (_respSession && tab._sseBySession) delete tab._sseBySession[_respSession];
                    tab._sseToolCount = 0;
                }

                var answer = resultObj.final_answer || resultObj.answer || '';
                // Handle dict/object final_answer — stringify for display
                if (answer && typeof answer === 'object') {
                    try { answer = JSON.stringify(answer, null, 2); } catch (e9) { answer = String(answer); }
                }
                if (answer) {
                    _appendAchatMsg('assistant', String(answer), Date.now(), tab);
                } else if (!toolCalls.length) {
                    _appendAchatMsg('error', 'No response received. Check slot/model and selected tool configuration.', Date.now(), tab);
                }

                var iterations = resultObj.iterations || 0;
                var slotName = resultObj.name || ('slot ' + tabSlot);
                var sessionId = (resp && resp.session_id) ? resp.session_id : '';
                var metaParts = [];
                if (iterations > 0) metaParts.push(iterations + ' iteration' + (iterations !== 1 ? 's' : ''));
                if (elapsed > 0) metaParts.push(elapsed + 's');
                if (toolCalls.length > 0) metaParts.push(toolCalls.length + ' tool call' + (toolCalls.length !== 1 ? 's' : ''));
                if (slotName) metaParts.push(slotName);
                if (sessionId) metaParts.push(sessionId.substring(0, 24));
                if (metaParts.length > 0) {
                    _appendAchatMsg('system-info', metaParts.join(' · '),
                        null,
                        tab
                    );
                }

                // Auto-continue loop: run one agent_chat step at a time so
                // each step lands live in chat/activity.
                if (isLoopIter && tab && tab._loopState) {
                    var ls = tab._loopState;
                    ls.iteration += 1;
                    ls.totalToolCalls += toolCalls.length;

                    // Track tools already used (for continuation guidance).
                    for (var tci = 0; tci < toolCalls.length; tci++) {
                        var tcn = String((toolCalls[tci] || {}).tool || '').trim();
                        if (tcn) ls.calledTools[tcn] = (ls.calledTools[tcn] || 0) + 1;
                    }

                    var hasRealAnswer = !!(answer && !/agent reached max iterations/i.test(String(answer)));
                    var isSynthesized = !!(resultObj._synthesized);
                    var minCalls = parseInt(ls.minToolCalls, 10) || 1;
                    var hasMinToolEvidence = ls.totalToolCalls >= minCalls;
                    var remainingCalls = Math.max(0, minCalls - ls.totalToolCalls);

                    // CRITICAL: Synthesized answers are postprocessor-generated summaries
                    // of tool results — NOT the model's own decision to stop. The model
                    // returned empty, so it never chose to finalize. Always continue the loop.
                    if (isSynthesized && ls.iteration < ls.maxIterations) {
                        hasRealAnswer = false;
                    }

                    // Don't accept hallucinated completion before required tool evidence is met,
                    // BUT always respect kill switch and accept a real answer if the model gave one.
                    if (hasRealAnswer && !hasMinToolEvidence && ls.iteration < ls.maxIterations && !window.__achatKillRequested) {
                        // Only enforce if the mission explicitly requested a tool-call count.
                        // Otherwise accept the model's decision to stop.
                        if (minCalls > 1 && ls.minToolCalls > 1) {
                            _appendAchatMsg('system-info',
                                'Final answer arrived early; enforcing explicit tool-call target (' + ls.totalToolCalls + '/' + minCalls + '). Continuing.',
                                Date.now(), tab);
                            hasRealAnswer = false;
                        }
                    }

                    if (hasRealAnswer && hasMinToolEvidence) {
                        var totalElapsed = Math.round((Date.now() - ls.startTime) / 1000);
                        _appendAchatMsg('system-info',
                            'Loop complete: ' + ls.iteration + ' iterations · ' +
                            ls.totalToolCalls + ' tool calls · ' + totalElapsed + 's total',
                            Date.now(), tab);
                        _setAchatBusy(false);
                        tab._loopState = null;
                    } else if (ls.iteration >= ls.maxIterations) {
                        // ── AUTO-REAPPROPRIATION: extend the loop if approval mode allows ──
                        var _reapCfg = tab.agentConfig || _defaultAgentConfig();
                        var _reapMode = _reapCfg.resourceApprovalMode || 'capped';
                        var _reapGuard = parseInt(_reapCfg.guardMaxToolCalls || 400, 10);
                        var _reapGrant = 0;
                        var _reapApproved = false;

                        if (!hasRealAnswer && (_reapMode === 'auto_all' || _reapMode === 'capped')) {
                            // Agent hasn't produced a real answer — auto-extend
                            var _reapRequest = Math.max(5, Math.min(20, minCalls - ls.totalToolCalls + 5));
                            if (_reapMode === 'auto_all') {
                                _reapGrant = Math.min(_reapRequest, 50);
                                _reapApproved = true;
                            } else if (_reapMode === 'capped') {
                                _reapGrant = Math.min(_reapRequest, 20);
                                _reapApproved = (ls.maxIterations + _reapGrant) <= _reapGuard;
                            }
                        }

                        if (_reapApproved && _reapGrant > 0) {
                            ls.maxIterations += _reapGrant;
                            _appendAchatMsg('system-info',
                                'AUTO-REAPPROPRIATION: +' + _reapGrant + ' iterations granted (now ' + ls.maxIterations + ' max). ' +
                                'Progress: ' + ls.totalToolCalls + '/' + minCalls + ' tool calls. Mode: ' + _reapMode + '.',
                                Date.now(), tab);
                            // Don't increment iteration — just extend and continue
                            ls.nextMessage =
                                'You have been granted ' + _reapGrant + ' additional iterations (' + (ls.maxIterations - ls.iteration) + ' remaining). ' +
                                'Continue working on the mission. Call one tool this turn, or provide final_answer if done.';
                            _fireAgentIteration(tab);
                        } else {
                            _appendAchatMsg('error',
                                'Loop reached max iterations (' + ls.maxIterations + ') with ' + ls.totalToolCalls +
                                ' tool calls (target: ' + minCalls + ').' +
                                (_reapMode === 'manual' ? ' Reappropriation mode is manual — set to "Auto-Approve" in agent config to enable auto-continuation.' : ''),
                                Date.now(), tab);
                            _setAchatBusy(false);
                            tab._loopState = null;
                        }
                    } else {
                        var used = Object.keys(ls.calledTools || {});
                        var usedPreview = used.slice(0, 8).join(', ');
                        var granted = Array.isArray(tab.grantedTools) ? tab.grantedTools : [];
                        var notYetCalled = granted.filter(function (t) { return !ls.calledTools[t]; });
                        var notYetPreview = notYetCalled.slice(0, 10).join(', ');

                        // Build a brief summary of last tool result for context
                        var lastToolCtx = '';
                        if (toolCalls.length > 0) {
                            var lastTc = toolCalls[toolCalls.length - 1];
                            var lastResult = String(lastTc.result || lastTc.error || '').substring(0, 400);
                            if (lastResult) {
                                lastToolCtx = '\n\nLast tool result (' + (lastTc.tool || '?') + '): ' + lastResult;
                                if (String(lastTc.result || '').length > 400) lastToolCtx += '…[truncated]';
                            }
                        }

                        if (ls.totalToolCalls <= 0) {
                            ls.nextMessage =
                                'SEQUENTIAL EXECUTION ONLY. You have not executed any tools yet. ' +
                                'Call exactly one granted tool now. Do not return final_answer yet.' +
                                (notYetPreview ? '\n\nAvailable tools to try: ' + notYetPreview : '');
                        } else {
                            ls.nextMessage =
                                'SEQUENTIAL EXECUTION ONLY. Continue with exactly one granted tool call this turn. ' +
                                'Do not finalize until required tool-call target is met (' + ls.totalToolCalls + '/' + minCalls + ', remaining ' + remainingCalls + '). ' +
                                (usedPreview ? 'Tools already used: ' + usedPreview + '. ' : '') +
                                (notYetPreview ? 'Tools NOT yet called: ' + notYetPreview + '. ' : '') +
                                'Use real tool outputs only.' + lastToolCtx;
                        }
                        _fireAgentIteration(tab);
                    }
                }
            } catch (e3) {
                _appendAchatMsg('assistant', parseToolData(msg.data), Date.now(), activeTab);
                if (isLoopIter && activeTab && activeTab._loopState) {
                    _setAchatBusy(false);
                    activeTab._loopState = null;
                }
            }
            return;
        }

        var text = msg.error ? 'ERROR: ' + msg.error : parseToolData(msg.data);

        if (WORKFLOW_TOOLS.indexOf(toolName) >= 0) {
            handleWorkflowToolResult(toolName, msg, text);
            return;
        }

        // Format tool output for readability (extract error guidance)
        if (!msg.error) text = formatToolOutput(text);

        // ── UNIVERSAL CACHED-RESPONSE AUTO-RESOLUTION ──
        // If ANY tool returns a _cached stub (>2KB response), auto-fetch
        // the full result and re-route it through the same handler.
        if (!msg.error && toolName !== 'get_cached') {
            try {
                var _cachedProbeU = typeof text === 'string' ? JSON.parse(text) : text;
                if (_cachedProbeU && _cachedProbeU._cached) {
                    callTool('get_cached', { cache_id: _cachedProbeU._cached }, toolName);
                    return;
                }
            } catch (_eCache) { /* not a cached stub — continue normal routing */ }
        }

        // Route to Memory tab if it's a memory tool
        if (MEMORY_TOOLS.indexOf(toolName) >= 0) {
            var memList = document.getElementById('mem-list');
            if (!memList) return;

            // Refresh catalog after successful memory mutations.
            if (!msg.error && ['bag_put', 'bag_induct', 'bag_forget', 'pocket', 'load_bag', 'bag_checkpoint', 'bag_restore', 'file_write', 'file_edit', 'file_append', 'file_prepend', 'file_delete', 'file_rename', 'file_copy', 'file_checkpoint', 'file_restore'].indexOf(toolName) >= 0) {
                callTool('bag_catalog', {});
            }

            // bag_get / bag_read_doc / file_read / get_cached → inline drill content
            if ((toolName === 'bag_get' || toolName === 'bag_read_doc' || toolName === 'file_read' || toolName === 'get_cached') && !msg.error && _openDrillKey) {
                var drillDiv = document.getElementById('drill-' + _openDrillKey);
                if (drillDiv) {
                    try {
                        var got = typeof text === 'string' ? JSON.parse(text) : text;
                        // If response was cached, follow up with get_cached
                        if (got._cached) {
                            drillDiv.innerHTML = '<div style="padding:8px 12px;color:var(--text-dim);font-size:11px;">Loading full content...</div>';
                            callTool('get_cached', { cache_id: got._cached });
                            return;
                        }
                        if (got.error) {
                            // Some workflow-written keys are visible in bag_read_doc but miss in bag_get.
                            // Fallback automatically so drill-in still works for operators.
                            if (toolName === 'bag_get' && /not found/i.test(String(got.error || '')) && !_bagReadFallbackPending[_openDrillKey]) {
                                _bagReadFallbackPending[_openDrillKey] = true;
                                drillDiv.innerHTML = '<div style="padding:8px 12px;color:var(--text-dim);font-size:11px;">Not found via bag_get, trying bag_read_doc...</div>';
                                callTool('bag_read_doc', { key: _openDrillKey }, 'bag_read_doc');
                                return;
                            }
                            drillDiv.innerHTML = '<div style="padding:8px 12px;color:#e11d48;">' + _esc(got.error) + '</div>';
                            return;
                        }
                        delete _bagReadFallbackPending[_openDrillKey];
                        var val = (typeof got.value !== 'undefined') ? got.value : got.content;
                        // get_cached returns the raw bag_get/file_read JSON string, parse it
                        if (typeof val === 'undefined' && typeof got.key !== 'undefined') {
                            val = got;
                        } else if (typeof val === 'undefined') {
                            // get_cached returns the original bag_get/file_read result as a string
                            try {
                                var inner = typeof got === 'string' ? JSON.parse(got) : got;
                                val = (typeof inner.value !== 'undefined') ? inner.value : inner.content;
                            } catch (e2) { val = text; }
                        }
                        var contentStr = typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val || '');
                        var lineCount = contentStr.split('\n').length;
                        var verNum = got.version || 1;
                        _bagDrillCache[_openDrillKey] = {
                            key: _openDrillKey,
                            type: got.type || '',
                            version: verNum,
                            value: val,
                            raw: got
                        };

                        var safeKey = _safeBagKeyId(_openDrillKey);
                        var commitBtnId = 'commit-btn-' + safeKey;
                        var gitMetaId = 'bag-git-meta-' + safeKey;
                        var gitDiffId = 'bag-git-diff-' + safeKey;
                        var gitDisabled = (_gitProbed && !_gitAvailable);
                        var isWebMode = !!window.__vsCodeShimInstalled;
                        var commitBtnStyle = gitDisabled
                            ? 'font-size:9px;padding:2px 8px;cursor:not-allowed;background:var(--surface2);color:var(--text-dim);opacity:0.45;border:1px solid var(--border);border-radius:3px;'
                            : 'font-size:9px;padding:2px 8px;cursor:pointer;background:var(--surface2);color:var(--accent);border:1px solid var(--border);border-radius:3px;';
                        var actionButtons = '';
                        if (!isWebMode) {
                            actionButtons =
                                '<button id="' + commitBtnId + '" data-bag-key="' + _esc(_openDrillKey) + '" onclick="commitBagVersion(this)"' + (gitDisabled ? ' disabled title="Git not available"' : '') + ' style="' + commitBtnStyle + '">Commit Version</button>';
                        }
                        drillDiv.innerHTML =
                            '<div style="padding:4px 12px;font-size:10px;color:var(--text-dim);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;">' +
                            '<span>' + lineCount + ' lines · ' + _fmtSize(contentStr.length) + ' · v' + verNum + '</span>' +
                            '<div style="display:flex;align-items:center;gap:6px;">' +
                            actionButtons +
                            '</div>' +
                            '</div>' +
                            '<div id="' + gitMetaId + '" style="padding:8px 12px;border-bottom:1px solid var(--border);font-size:10px;color:var(--text-dim);">Loading git details...</div>' +
                            '<div id="' + gitDiffId + '" style="display:none;padding:6px 12px;border-bottom:1px solid var(--border);"></div>' +
                            _renderLineNumbered(contentStr);
                        _renderBagGitInfo(_openDrillKey);
                        if (!gitDisabled) requestBagGitInfo(_openDrillKey);
                    } catch (e) {
                        drillDiv.innerHTML = '<pre style="padding:8px 12px;color:var(--text);white-space:pre-wrap;font-size:11px;">' + _esc(text) + '</pre>';
                    }
                    return;
                }
            }

            // Try to parse bag_catalog structured output
            if (toolName === 'bag_catalog' && !msg.error) {
                try {
                    var parsed = typeof text === 'string' ? JSON.parse(text) : text;

                    // Format A: { total, all_ids: [hash, name, hash, name, ...], unique_types: [...] }
                    if (parsed.all_ids && Array.isArray(parsed.all_ids)) {
                        var ids = parsed.all_ids;
                        var total = parsed.total || Math.floor(ids.length / 2);
                        var types = parsed.unique_types || [];
                        var memStats = document.getElementById('mem-stats');
                        if (memStats) {
                            memStats.innerHTML =
                                '<div class="stat-box"><strong>' + total + '</strong> items</div>' +
                                '<div class="stat-box"><strong>' + types.length + '</strong> types</div>' +
                                (parsed.stats && parsed.stats.size ? '<div class="stat-box"><strong>' + _fmtSize(parsed.stats.size.sum) + '</strong> total</div>' : '');
                        }
                        var html = '';
                        for (var i = 0; i < ids.length; i += 2) {
                            html += _renderMemItem(ids[i] || '', ids[i + 1] || ids[i], null, null);
                        }
                        memList.innerHTML = html || '<div class="memory-item" style="color:var(--text-dim);">Bag is empty</div>';
                        return;
                    }

                    // Format C: { count, items: ["hash1", "hash2", ...] } — plain string array
                    var items = parsed.items;
                    if (Array.isArray(items) && items.length > 0 && typeof items[0] === 'string') {
                        var memStatsC = document.getElementById('mem-stats');
                        if (memStatsC) {
                            memStatsC.innerHTML =
                                '<div class="stat-box"><strong>' + (parsed.count || items.length) + '</strong> items</div>';
                        }
                        var htmlC = '';
                        for (var c = 0; c < items.length; c++) {
                            htmlC += _renderMemItem(items[c], null, null, null);
                        }
                        memList.innerHTML = htmlC || '<div class="memory-item" style="color:var(--text-dim);">Bag is empty</div>';
                        return;
                    }

                    // Format B: { count, items: [{id, name, type, preview, size, version}, ...] }
                    if (Array.isArray(items) && items.length > 0 && typeof items[0] === 'object') {
                        var memStats2 = document.getElementById('mem-stats');
                        if (memStats2) {
                            memStats2.innerHTML =
                                '<div class="stat-box"><strong>' + items.length + '</strong> items</div>' +
                                '<div class="stat-box"><strong>' + _countTypes(items) + '</strong> types</div>';
                        }
                        var html2 = '';
                        for (var j = 0; j < items.length; j++) {
                            var it = items[j];
                            html2 += _renderMemItem(it.id || '', it.name, it.type, it.preview);
                        }
                        memList.innerHTML = html2;
                        return;
                    }
                } catch (e) { /* fall through to raw display */ }
            }

            // Fallback: raw text for other memory tools or parse failures
            memList.innerHTML = '<pre style="white-space:pre-wrap;word-break:break-word;color:var(--text);font-size:11px;">' +
                text.substring(0, 10000).replace(/</g, '&lt;') + '</pre>';
            return;
        }

        // list_slots refreshes → update council grid (with disconnect recovery)
        if (toolName === 'list_slots' || toolName === '__external_slot_sync__' || toolName === '__slot_watchdog__') {
            if (msg && msg.error) {
                _scheduleSlotRefresh('list-slots-error', 1500);
                return;
            }
            renderSlots(msg ? msg.data : null);
            return;
        }

        // Route to Council tab if it's a council tool
        if (COUNCIL_TOOLS.indexOf(toolName) >= 0) {
            if (toolName === 'infer' && !msg.error) {
                try {
                    var inferObj = typeof text === 'string' ? JSON.parse(text) : text;
                    var concise = inferObj && typeof inferObj === 'object'
                        ? (inferObj.assistant_text || (inferObj.result && inferObj.result.assistant_text) || '')
                        : '';
                    if (concise) {
                        text = '[assistant_text]\n' + String(concise) + '\n\n---\n[structured]\n' + (typeof text === 'string' ? text : JSON.stringify(text, null, 2));
                    }
                } catch (eInferFmt) { }
            }
            var councilOut = document.getElementById('council-output');
            if (councilOut) {
                councilOut.innerHTML = '<pre style="white-space:pre-wrap;word-break:break-word;color:var(--text);font-size:11px;">' +
                    text.substring(0, 10000).replace(/</g, '&lt;') + '</pre>';
            }

            // Keep slot cards visually in sync after mutations.
            if (['plug_model', 'hub_plug', 'unplug_slot', 'clone_slot', 'rename_slot', 'swap_slots', 'cu' + 'll_slot'].indexOf(toolName) >= 0) {
                if (toolName === 'plug_model' || toolName === 'hub_plug') {
                    var doneModelId = (msg.args && (msg.args.model_id || msg.args.summary)) || null;
                    _clearPluggingEntry(doneModelId);
                }
                if (!msg.error) callTool('list_slots', {});
            }
            return;
        }

        // Default: show in Diagnostics output
        var diagOut = document.getElementById('diag-output');
        if (!diagOut) return;
        if (msg.error) {
            diagOut.textContent = 'ERROR: ' + msg.error;
        } else {
            try {
                diagOut.textContent = text.substring(0, 10000);
            } catch (err) {
                diagOut.textContent = String(msg.data);
            }
        }
    }

    // ── TOOLS REGISTRY ──
    function buildToolsRegistry() {
        var container = document.getElementById('tools-registry');
        if (!container) return;
        container.innerHTML = '';
        var cats = _state.categories || {};
        var entries = Object.entries(CATEGORIES);
        var hasSchemas = Object.keys(_toolSchemas).length > 0;

        for (var i = 0; i < entries.length; i++) {
            var name = entries[i][0];
            var info = entries[i][1];
            var enabled = cats[name] !== false;
            var div = document.createElement('div');
            div.className = 'tool-category';

            var header = document.createElement('button');
            header.className = 'tool-category-header' + (enabled ? '' : ' disabled');
            header.innerHTML = '<span>' + (enabled ? '[ + ]' : '[ - ]') + '  ' + name + '</span>' +
                '<span class="cat-badge">' + info.tools.length + ' tools' + (enabled ? '' : ' (DISABLED)') + '</span>';
            header.addEventListener('click', function () {
                this.parentElement.classList.toggle('expanded');
            });

            var body = document.createElement('div');
            body.className = 'tool-category-body';
            for (var j = 0; j < info.tools.length; j++) {
                var toolName = info.tools[j];
                var schema = hasSchemas ? _toolSchemas[toolName] : null;
                var row = document.createElement('div');
                row.className = 'tool-row-wrap';

                // Tool header row
                var hdr = document.createElement('div');
                hdr.className = 'tool-row';
                var nameSpan = document.createElement('span');
                nameSpan.className = 'tool-name';
                nameSpan.textContent = toolName;
                var leftDiv = document.createElement('div');
                leftDiv.style.cssText = 'display:flex;align-items:center;gap:8px;flex:1;min-width:0;cursor:pointer';
                leftDiv.appendChild(nameSpan);
                if (schema && schema.description) {
                    var brief = document.createElement('span');
                    brief.className = 'tool-brief';
                    brief.textContent = schema.description.length > 80 ? schema.description.substring(0, 80) + '...' : schema.description;
                    leftDiv.appendChild(brief);
                }
                hdr.appendChild(leftDiv);

                var btnGroup = document.createElement('div');
                btnGroup.style.cssText = 'display:flex;gap:4px;align-items:center';
                if (schema) {
                    var expandBtn = document.createElement('button');
                    expandBtn.className = 'btn-dim';
                    expandBtn.textContent = 'DETAIL';
                    expandBtn.dataset.tool = toolName;
                    expandBtn.addEventListener('click', function (e) {
                        e.stopPropagation();
                        var wrap = this.closest('.tool-row-wrap');
                        var detail = wrap.querySelector('.tool-detail');
                        if (detail) {
                            detail.classList.toggle('visible');
                            this.textContent = detail.classList.contains('visible') ? 'HIDE' : 'DETAIL';
                        }
                    });
                    btnGroup.appendChild(expandBtn);
                }
                var invokeBtn = document.createElement('button');
                invokeBtn.className = 'btn-dim';
                invokeBtn.textContent = 'INVOKE';
                invokeBtn.dataset.tool = toolName;
                invokeBtn.addEventListener('click', function (e) {
                    e.stopPropagation();
                    promptToolCall(this.dataset.tool);
                });
                btnGroup.appendChild(invokeBtn);
                hdr.appendChild(btnGroup);
                row.appendChild(hdr);

                // Expandable detail panel
                if (schema) {
                    var detail = document.createElement('div');
                    detail.className = 'tool-detail';
                    var detailHTML = '';

                    // Description
                    if (schema.description) {
                        detailHTML += '<div class="td-section"><div class="td-label">Description</div><div class="td-value">' + escHtml(schema.description) + '</div></div>';
                    }

                    // Input parameters
                    var inputSchema = schema.inputSchema || (schema.parameters ? schema.parameters : null);
                    if (inputSchema && inputSchema.properties) {
                        var props = inputSchema.properties;
                        var required = inputSchema.required || [];
                        var paramNames = Object.keys(props);
                        if (paramNames.length > 0) {
                            detailHTML += '<div class="td-section"><div class="td-label">Parameters (' + paramNames.length + ')</div>';
                            for (var k = 0; k < paramNames.length; k++) {
                                var pName = paramNames[k];
                                var pDef = props[pName];
                                var isReq = required.indexOf(pName) >= 0;
                                detailHTML += '<div class="td-param">';
                                detailHTML += '<span class="td-param-name">' + escHtml(pName) + '</span>';
                                detailHTML += '<span class="td-param-type">' + escHtml(pDef.type || pDef.enum ? (pDef.type || 'enum') : 'any') + '</span>';
                                if (isReq) detailHTML += '<span class="td-param-req">required</span>';
                                if (pDef.description) detailHTML += '<div class="td-param-desc">' + escHtml(pDef.description) + '</div>';
                                if (pDef.default !== undefined) detailHTML += '<div class="td-param-desc">Default: <code>' + escHtml(JSON.stringify(pDef.default)) + '</code></div>';
                                if (pDef.enum) detailHTML += '<div class="td-param-desc">Values: <code>' + escHtml(pDef.enum.join(', ')) + '</code></div>';
                                if (pDef.minimum !== undefined || pDef.maximum !== undefined) {
                                    detailHTML += '<div class="td-param-desc">Range: ' + (pDef.minimum !== undefined ? pDef.minimum : '...') + ' – ' + (pDef.maximum !== undefined ? pDef.maximum : '...') + '</div>';
                                }
                                detailHTML += '</div>';
                            }
                            detailHTML += '</div>';
                        } else {
                            detailHTML += '<div class="td-section"><div class="td-label">Parameters</div><div class="td-value" style="opacity:0.5">No parameters</div></div>';
                        }
                    } else {
                        detailHTML += '<div class="td-section"><div class="td-label">Parameters</div><div class="td-value" style="opacity:0.5">No parameters</div></div>';
                    }

                    // Category & setting info
                    detailHTML += '<div class="td-section"><div class="td-label">Category</div><div class="td-value">' + escHtml(name) + ' (setting: champion.tools.' + escHtml(info.setting) + ')</div></div>';

                    detail.innerHTML = detailHTML;
                    row.appendChild(detail);
                }

                body.appendChild(row);
            }

            div.appendChild(header);
            div.appendChild(body);
            container.appendChild(div);
        }

        // Show hint if schemas not loaded yet
        if (!hasSchemas && _state.serverStatus === 'running') {
            var hint = document.createElement('div');
            hint.style.cssText = 'text-align:center;padding:12px;opacity:0.5;font-size:12px';
            hint.textContent = 'Loading tool schemas from MCP server...';
            container.appendChild(hint);
            vscode.postMessage({ command: 'fetchToolSchemas' });
        }
    }

    function escHtml(str) {
        if (!str) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // C8 fix: decode __docv2__ encoded FelixBag keys to human-readable /slash/paths for display.
    function _decodeDocKey(raw) {
        if (!raw || typeof raw !== 'string') return raw || '';
        return raw.replace(/__docv2__[^\s",'}\]]+/g, function (token) {
            var body = token.substring(9); // skip '__docv2__'
            if (body.length >= 3 && body.substring(body.length - 3) === '__k') body = body.substring(0, body.length - 3);
            var out = [], i = 0;
            while (i < body.length) {
                if (body[i] === '~' && i + 1 < body.length) {
                    if (body[i + 1] === 's') { out.push('/'); i += 2; continue; }
                    if (body[i + 1] === '~') { out.push('~'); i += 2; continue; }
                }
                out.push(body[i]); i++;
            }
            return out.join('');
        });
    }

    // UI fix: normalize escaped newline sequences for display in pre-wrap containers.
    // Converts literal backslash-n (from JSON.stringify or double-escaped strings) to real newlines
    // AFTER html-escaping, so it's safe for innerHTML with pre-wrap.
    function _normalizeNewlines(escaped) {
        if (!escaped || typeof escaped !== 'string') return escaped || '';
        return escaped.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n').replace(/\\r/g, '\n');
    }

    // Combined: decode doc keys, html-escape, then normalize newlines for display.
    function _escForDisplay(str) {
        return _normalizeNewlines(escHtml(_decodeDocKey(str)));
    }

    function promptToolCall(toolName) {
        var argsStr = prompt('Arguments (JSON):', '{}');
        if (argsStr === null) return;
        try {
            var args = JSON.parse(argsStr);
            callTool(toolName, args);
        } catch (err) {
            alert('Invalid JSON');
        }
    }
    window.promptToolCall = promptToolCall;

    // ── MEMORY ──
    function memSearch() {
        var q = document.getElementById('mem-search');
        if (q && q.value) callTool('bag_search', { query: q.value });
    }
    window.memSearch = memSearch;

    function setMemoryExportStatus(message, isError) {
        var el = document.getElementById('mem-export-status');
        if (!el) return;
        el.textContent = message || '';
        el.style.color = isError ? 'var(--red)' : 'var(--text-dim)';
    }

    function startMemoryExport() {
        var isWebMode = !!window.__vsCodeShimInstalled;
        setMemoryExportStatus(isWebMode ? 'Exporting FelixBag…' : 'Choose export format from the VS Code picker…', false);
        vscode.postMessage({ command: 'exportMemory' });
    }
    window.startMemoryExport = startMemoryExport;

    // ── MODALS ──
    function openPlugModal() {
        var el = document.getElementById('plug-modal');
        if (el) el.classList.add('active');
        _setHubModelMeta('Select a model to see metadata and size estimate.', 'info');
        _queueHubModelMetaRefresh(120);
        onHubModelInput();
    }
    window.openPlugModal = openPlugModal;

    function openInductModal() {
        var el = document.getElementById('induct-modal');
        if (el) el.classList.add('active');
    }
    window.openInductModal = openInductModal;

    function closeModals() {
        document.querySelectorAll('.modal-overlay').forEach(function (m) { m.classList.remove('active'); });
    }
    window.closeModals = closeModals;

    // ── PLUG MODEL HUB BROWSER ──
    var _hubBrowseTimer = null;
    var _hubBrowseSeq = 0;
    var _hubMetaTimer = null;
    var _hubMetaSeq = 0;

    function _setHubStatus(text, tone) {
        var el = document.getElementById('plug-hub-status');
        if (!el) return;
        el.textContent = String(text || '');
        el.style.color = (tone === 'error') ? '#f87171' : (tone === 'ok' ? '#34d399' : 'var(--text-dim)');
    }

    function _setHubModelMeta(text, tone) {
        var el = document.getElementById('plug-hub-model-meta');
        if (!el) return;
        el.textContent = String(text || '');
        el.style.color = (tone === 'error') ? '#f87171' : (tone === 'ok' ? '#34d399' : 'var(--text-dim)');
    }

    function _setHubSizeWarning(text) {
        var el = document.getElementById('plug-hub-size-warning');
        if (!el) return;
        if (text) {
            el.textContent = String(text);
            el.style.display = '';
        } else {
            el.textContent = '';
            el.style.display = 'none';
        }
    }

    function _hubInferParamHint(modelId) {
        var s = String(modelId || '');
        var m = s.match(/(?:^|[^0-9])(\d+(?:\.\d+)?)\s*([bmk])(?:[^a-z0-9]|$)/i);
        if (!m) return '';
        return (m[1] + m[2]).toUpperCase();
    }

    function _hubFormatSize(sizeMb) {
        var mb = Number(sizeMb || 0);
        if (!(mb > 0)) return '';
        if (mb >= 1024) return (mb / 1024).toFixed(1).replace(/\.0$/, '') + ' GB';
        return Math.round(mb) + ' MB';
    }

    async function _refreshHubModelMeta() {
        var model = String(((document.getElementById('plug-model-id') || {}).value || '')).trim();
        if (!model || model.indexOf('/') < 1) {
            var hint = _hubInferParamHint(model);
            if (hint) _setHubModelMeta('Parameter hint: ' + hint, 'info');
            else _setHubModelMeta('Select a model to see metadata and size estimate.', 'info');
            _setHubSizeWarning('');
            return;
        }

        var seq = ++_hubMetaSeq;
        _setHubModelMeta('Loading model metadata\u2026', 'info');

        try {
            var info = await callToolAwaitParsed('hub_info', { model_id: model }, '__hub_model_meta__', { timeout: 45000 });
            if (seq !== _hubMetaSeq) return;

            if (!info || info.error) {
                _setHubModelMeta('Metadata unavailable for ' + model, 'error');
                _setHubSizeWarning('');
                return;
            }

            var task = String(info.task || 'unknown');
            var downloads = Number(info.downloads || 0);
            var likes = Number(info.likes || 0);
            var sizeMb = Number(info.size_mb || 0);
            var size = _hubFormatSize(sizeMb);
            var param = _hubInferParamHint(model);

            var bits = [];
            bits.push('Task: ' + task);
            if (param) bits.push('Params: ~' + param);
            if (size) bits.push('Size: ' + size);
            if (downloads > 0) bits.push('Downloads: ' + _formatCount(downloads));
            if (likes > 0) bits.push('Likes: ' + _formatCount(likes));

            _setHubModelMeta(bits.join(' \u00b7 '), 'ok');

            // Size warnings for local download
            if (sizeMb > 10000) {
                _setHubSizeWarning('\u26a0 This model is ' + size + ' \u2014 it will likely exceed available RAM/disk on most HF Spaces. Consider using PLUG PROVIDER for inference-only access instead.');
            } else if (sizeMb > 4000) {
                _setHubSizeWarning('\u26a0 This model is ' + size + ' \u2014 it may be too large for free-tier HF Spaces (16 GB RAM). Ensure your runtime has sufficient resources.');
            } else if (sizeMb > 1500) {
                _setHubSizeWarning('This model is ' + size + ' \u2014 download may take a few minutes. Ensure sufficient disk space.');
            } else {
                _setHubSizeWarning('');
            }
        } catch (e) {
            if (seq !== _hubMetaSeq) return;
            _setHubModelMeta('Metadata lookup failed: ' + String((e && e.message) || e), 'error');
            _setHubSizeWarning('');
        }
    }

    function _queueHubModelMetaRefresh(delayMs) {
        if (_hubMetaTimer) clearTimeout(_hubMetaTimer);
        _hubMetaTimer = setTimeout(function () {
            _refreshHubModelMeta();
        }, (typeof delayMs === 'number' ? delayMs : 260));
    }

    function _renderHubModelOptions(models) {
        var sel = document.getElementById('plug-hub-models');
        if (!sel) return;
        sel.innerHTML = '';

        if (!Array.isArray(models) || models.length === 0) {
            var empty = document.createElement('option');
            empty.value = '';
            empty.textContent = 'No models found';
            sel.appendChild(empty);
            return;
        }

        for (var i = 0; i < models.length; i++) {
            var m = models[i] || {};
            var opt = document.createElement('option');
            opt.value = String(m.id || '');
            var badges = [];
            var paramHint = _hubInferParamHint(opt.value);
            if (m.task) badges.push(m.task);
            if (paramHint) badges.push('~' + paramHint);
            if (m.size) badges.push(m.size);
            if (m.downloads > 0) badges.push(_formatCount(m.downloads) + ' dl');
            if (m.likes > 0) badges.push(_formatCount(m.likes) + ' \u2764');
            opt.textContent = badges.length ? (opt.value + '   \u00b7   ' + badges.join(' \u00b7 ')) : opt.value;
            sel.appendChild(opt);
        }
    }

    async function _refreshHubModels() {
        var taskEl = document.getElementById('plug-hub-task');
        var queryEl = document.getElementById('plug-hub-query');
        var modelEl = document.getElementById('plug-model-id');

        var task = String((taskEl && taskEl.value) || '').trim();
        var query = String((queryEl && queryEl.value) || '').trim();
        if (!query) query = String((modelEl && modelEl.value) || '').trim();
        var seq = ++_hubBrowseSeq;

        _setHubStatus('Loading models\u2026', 'info');

        try {
            var payload = null;
            if (query || task) {
                var searchQ = query;
                if (task && !query) searchQ = task;
                else if (task && query) searchQ = query;
                payload = await callToolAwaitParsed('hub_search', { query: searchQ || '', limit: 40, page: 1 }, '__hub_model_lookup__', { timeout: 45000 });
            } else {
                payload = await callToolAwaitParsed('hub_top', { limit: 40, page: 1 }, '__hub_model_lookup__', { timeout: 45000 });
            }

            if (seq !== _hubBrowseSeq) return;

            var models = (payload && Array.isArray(payload.models)) ? payload.models : [];

            // Client-side task filter
            if (task && models.length > 0) {
                var filtered = [];
                for (var i = 0; i < models.length; i++) {
                    var mTask = String((models[i] || {}).task || '').toLowerCase();
                    if (mTask === task.toLowerCase() || !mTask) filtered.push(models[i]);
                }
                if (filtered.length > 0) models = filtered;
            }

            var out = [];
            for (var j = 0; j < models.length; j++) {
                var m = models[j] || {};
                var id = String(m.id || '').trim();
                if (!id) continue;
                out.push({
                    id: id,
                    downloads: Number(m.downloads || 0),
                    likes: Number(m.likes || 0),
                    task: String(m.task || ''),
                    size: m.size_mb ? _hubFormatSize(m.size_mb) : ''
                });
            }

            _renderHubModelOptions(out);

            var sel = document.getElementById('plug-hub-models');
            if (sel && modelEl) {
                var current = String((modelEl.value || '')).trim();
                if (current) {
                    for (var idx = 0; idx < sel.options.length; idx++) {
                        if (String(sel.options[idx].value || '') === current) {
                            sel.selectedIndex = idx;
                            break;
                        }
                    }
                }
            }

            var taskLabel = task ? ('task=' + task + ', ') : '';
            _setHubStatus('Found ' + out.length + ' model' + (out.length === 1 ? '' : 's') + ' ' + taskLabel + 'via hub tools.', out.length ? 'ok' : 'info');
        } catch (e) {
            if (seq !== _hubBrowseSeq) return;
            _renderHubModelOptions([]);
            _setHubStatus('Model lookup failed: ' + String((e && e.message) || e), 'error');
        }
    }

    function onHubModelInput() {
        if (_hubBrowseTimer) clearTimeout(_hubBrowseTimer);
        _hubBrowseTimer = setTimeout(function () {
            _refreshHubModels();
        }, 600);
    }
    window.onHubModelInput = onHubModelInput;

    function onHubModelPick() {
        var sel = document.getElementById('plug-hub-models');
        var modelEl = document.getElementById('plug-model-id');
        if (sel && modelEl && sel.value) modelEl.value = sel.value;
        _queueHubModelMetaRefresh(60);
    }
    window.onHubModelPick = onHubModelPick;

    function onHubModelIdInput() {
        _queueHubModelMetaRefresh(800);
    }
    window.onHubModelIdInput = onHubModelIdInput;

    function doPlug() {
        var modelId = (document.getElementById('plug-model-id').value || '').trim();
        var slotName = (document.getElementById('plug-slot-name').value || '').trim();
        if (!modelId) {
            mpToast('Enter or select a HuggingFace model ID first', 'error', 2600);
            return;
        }
        _clearPluggingEntry(modelId);
        var slotKey = slotName || 'plug_' + Date.now();
        _pluggingSlots[slotKey] = { modelId: modelId, startTime: Date.now(), slotName: slotName || null };
        _updatePluggingUI();
        var plugArgs = { model_id: modelId };
        if (slotName) plugArgs.slot_name = slotName;
        callTool('hub_plug', plugArgs);
        closeModals();
        mpToast('Downloading & plugging ' + modelId + ' from HuggingFace Hub\u2026', 'info', 3500);
    }
    window.doPlug = doPlug;

    function doInduct() {
        var key = document.getElementById('induct-key').value;
        var value = document.getElementById('induct-value').value;
        if (!key || !value) return;
        callTool('bag_put', { key: key, value: value });
        closeModals();
    }
    window.doInduct = doInduct;

    function clearActivity() {
        _activityLog = [];
        _activityTraceCounts = {};
        _activityTraceGroupExpanded = {};
        _activityPage = 0;
        renderActivityFeed();
    }
    window.clearActivity = clearActivity;

    // ── COMMUNITY / NOSTR ──
    var _chatMessages = [];
    var _workflowEvents = [];
    var _nostrPubkey = '';
    var _nostrRelayCount = 0;
    var _dmMessages = []; // { event, decrypted, peerPubkey }
    var _activeDMPeer = ''; // currently selected DM conversation
    var _blockedUsers = [];
    var _onlineUsers = [];
    var _privacySettings = { chatEnabled: true, dmsEnabled: true, marketplaceEnabled: true, autoRedact: true, presenceEnabled: true };
    var _profiles = {}; // pubkey -> { name, about }
    var _reactions = {}; // eventId -> { '+': count, '♥': count, ... , selfReacted: { '+': true, ... } }
    var _zapTotals = {}; // eventId -> total sats
    var _pendingZap = null; // { eventId, pubkey, amountSats }
    var _redactTimer = null;

    function shortPubkey(pk) {
        return pk ? pk.slice(0, 8) + '...' + pk.slice(-4) : '???';
    }
    function displayName(pk) {
        if (_profiles[pk] && _profiles[pk].name) return _profiles[pk].name;
        return shortPubkey(pk);
    }
    function safeHTML(str) {
        return (str || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // ── COMMUNITY SUB-TAB NAVIGATION ──
    document.querySelectorAll('#community-tabs button').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('#community-tabs button').forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');
            document.querySelectorAll('.community-subtab').forEach(function (t) { t.style.display = 'none'; t.classList.remove('active'); });
            var target = document.getElementById('ctab-' + btn.dataset.ctab);
            if (target) { target.style.display = 'block'; target.classList.add('active'); }
            // Trigger background gist indexing on marketplace tab activation
            if (btn.dataset.ctab === 'marketplace' && !_gistIndexingTriggered) {
                _gistIndexingTriggered = true;
                vscode.postMessage({ command: 'triggerGistIndexing' });
            }
            // Fetch voice rooms when switching to voice tab
            if (btn.dataset.ctab === 'voice') {
                vscode.postMessage({ command: 'nostrGetVoiceRooms' });
            }
        });
    });

    // ── NIP-53: VOICE ROOM BUTTON HANDLERS ──
    (function () {
        var refreshBtn = document.getElementById('voice-refresh-btn');
        var createBtn = document.getElementById('voice-create-btn');
        var createSubmit = document.getElementById('voice-create-submit');
        var createCancel = document.getElementById('voice-create-cancel');
        var leaveBtn = document.getElementById('voice-leave-btn');
        var raiseHandBtn = document.getElementById('voice-raise-hand');
        var chatSendBtn = document.getElementById('voice-chat-send');
        var chatInput = document.getElementById('voice-chat-input');

        var heroCreateBtn = document.getElementById('voice-create-btn-hero');
        var micToggle = document.getElementById('voice-mic-toggle');
        var settingsBtn = document.getElementById('voice-settings-btn');
        var settingsPanel = document.getElementById('voice-settings-panel');
        var settingsClose = document.getElementById('voice-settings-close');
        var voiceSensSlider = document.getElementById('voice-sensitivity');
        var voiceSensVal = document.getElementById('voice-sensitivity-val');
        var voiceGateSlider = document.getElementById('voice-noisegate');
        var voiceGateVal = document.getElementById('voice-noisegate-val');
        var monitorHeadphones = document.getElementById('voice-monitor-headphones');
        var monitorToggle = document.getElementById('voice-monitor-toggle');

        _updateVoiceMonitorUI();

        // Settings gear toggle
        if (settingsBtn) settingsBtn.addEventListener('click', function () {
            if (settingsPanel) settingsPanel.style.display = settingsPanel.style.display === 'none' ? 'block' : 'none';
        });
        if (settingsClose) settingsClose.addEventListener('click', function () {
            if (settingsPanel) settingsPanel.style.display = 'none';
        });
        // Sensitivity slider
        if (voiceSensSlider) voiceSensSlider.addEventListener('input', function () {
            var val = parseFloat(voiceSensSlider.value);
            _voiceMicSensitivity = val;
            if (voiceSensVal) voiceSensVal.textContent = val.toFixed(1) + 'x';
            vscode.postMessage({ command: 'setMicSensitivity', value: val });
        });
        // Noise gate slider
        if (voiceGateSlider) voiceGateSlider.addEventListener('input', function () {
            var val = parseInt(voiceGateSlider.value, 10);
            _voiceNoiseGate = val;
            if (voiceGateVal) voiceGateVal.textContent = String(val);
            vscode.postMessage({ command: 'setMicNoiseGate', value: val });
        });

        // ── HEADPHONES-ONLY LOCAL MONITOR ──
        if (monitorHeadphones) monitorHeadphones.addEventListener('change', function () {
            _voiceMonitorHeadphonesConfirmed = !!monitorHeadphones.checked;
            if (!_voiceMonitorHeadphonesConfirmed && _voiceMonitorEnabled) {
                _setVoiceMonitorEnabled(false);
                _voiceToast('Monitor disabled (headphones confirmation removed).', 'info', 2200);
            } else {
                _applyVoiceMonitorState();
            }
        });
        if (monitorToggle) monitorToggle.addEventListener('click', function () {
            if (_voiceMonitorEnabled) _setVoiceMonitorEnabled(false);
            else _setVoiceMonitorEnabled(true);
        });

        // ── INPUT DEVICE SELECTOR ──
        var deviceSelect = document.getElementById('voice-input-device');
        // Populate devices when settings panel opens
        if (settingsBtn) {
            var origClick = settingsBtn.onclick;
            settingsBtn.addEventListener('click', function () {
                if (settingsPanel && settingsPanel.style.display !== 'none') {
                    // Panel just opened — fetch devices
                    vscode.postMessage({ command: 'listAudioDevices' });
                }
            });
        }
        if (deviceSelect) deviceSelect.addEventListener('change', function () {
            _voiceSelectedDevice = deviceSelect.value;
            // If mic is on, restart with new device
            if (_voiceMicOn) {
                vscode.postMessage({ command: 'stopMicCapture' });
                setTimeout(function () {
                    vscode.postMessage({ command: 'startMicCapture', device: _voiceSelectedDevice || undefined });
                }, 200);
            }
        });

        // ── MIC MODE: OPEN MIC / PUSH-TO-TALK ──
        var modeOpenBtn = document.getElementById('voice-mode-open');
        var modePttBtn = document.getElementById('voice-mode-ptt');
        var pttKeyRow = document.getElementById('voice-ptt-key-row');
        var pttKeyBtn = document.getElementById('voice-ptt-key-btn');

        function updateModeUI() {
            if (modeOpenBtn) {
                modeOpenBtn.style.background = _voicePTTMode ? '' : 'var(--accent)';
                modeOpenBtn.style.color = _voicePTTMode ? '' : '#000';
                modeOpenBtn.style.fontWeight = _voicePTTMode ? '' : 'bold';
            }
            if (modePttBtn) {
                modePttBtn.style.background = _voicePTTMode ? 'var(--accent)' : '';
                modePttBtn.style.color = _voicePTTMode ? '#000' : '';
                modePttBtn.style.fontWeight = _voicePTTMode ? 'bold' : '';
            }
            if (pttKeyRow) pttKeyRow.style.display = _voicePTTMode ? 'flex' : 'none';
        }
        if (modeOpenBtn) modeOpenBtn.addEventListener('click', function () {
            _voicePTTMode = false;
            updateModeUI();
            // If PTT was active and key is released, mic stays on in open mic mode
        });
        if (modePttBtn) modePttBtn.addEventListener('click', function () {
            _voicePTTMode = true;
            updateModeUI();
            // In PTT mode, mic should be off until key is held
            if (_voiceMicOn && !_voicePTTActive) {
                vscode.postMessage({ command: 'stopMicCapture' });
            }
        });

        // PTT key binding
        if (pttKeyBtn) pttKeyBtn.addEventListener('click', function () {
            _voicePTTBinding = true;
            pttKeyBtn.textContent = '...press a key...';
            pttKeyBtn.style.color = 'var(--accent)';
        });

        // PTT keydown/keyup handlers (global)
        document.addEventListener('keydown', function (e) {
            if (_voicePTTBinding) {
                e.preventDefault();
                _voicePTTKey = e.key;
                _voicePTTBinding = false;
                if (pttKeyBtn) {
                    pttKeyBtn.textContent = e.key === ' ' ? 'Space' : e.key.length === 1 ? e.key.toUpperCase() : e.key;
                    pttKeyBtn.style.color = '';
                }
                return;
            }
            if (_voicePTTMode && _activeRoomATag && e.key === _voicePTTKey && !_voicePTTActive) {
                _voicePTTActive = true;
                if (!_voiceMicOn) {
                    vscode.postMessage({ command: 'startMicCapture', device: _voiceSelectedDevice || undefined });
                }
            }
        });
        document.addEventListener('keyup', function (e) {
            if (_voicePTTMode && e.key === _voicePTTKey && _voicePTTActive) {
                _voicePTTActive = false;
                if (_voiceMicOn) {
                    vscode.postMessage({ command: 'stopMicCapture' });
                }
            }
        });

        // ── DEAFEN BUTTON ──
        var deafenBtn = document.getElementById('voice-deafen-btn');
        if (deafenBtn) deafenBtn.addEventListener('click', function () {
            _voiceDeafened = !_voiceDeafened;
            deafenBtn.style.background = _voiceDeafened ? '#f44336' : '';
            deafenBtn.style.color = _voiceDeafened ? '#fff' : '';
            deafenBtn.title = _voiceDeafened ? 'Undeafen (unmute incoming audio)' : 'Deafen (mute incoming audio)';
            // Mute/unmute all peer audio elements
            var peerAudioEls = document.querySelectorAll('audio[data-peer]');
            peerAudioEls.forEach(function (el) { el.muted = _voiceDeafened; });
        });

        // ── MASTER VOLUME ──
        var masterVol = document.getElementById('voice-master-volume');
        var masterVolVal = document.getElementById('voice-master-volume-val');
        if (masterVol) masterVol.addEventListener('input', function () {
            _voiceMasterVolume = parseInt(masterVol.value, 10);
            if (masterVolVal) masterVolVal.textContent = _voiceMasterVolume + '%';
            // Apply to all peer audio elements
            var peerAudioEls = document.querySelectorAll('audio[data-peer]');
            peerAudioEls.forEach(function (el) { el.volume = _voiceMasterVolume / 100; });
            if (_voiceMonitorGain) {
                _voiceMonitorGain.gain.value = Math.max(0, Math.min(1, _voiceMasterVolume / 100));
            }
        });

        if (refreshBtn) refreshBtn.addEventListener('click', function () {
            vscode.postMessage({ command: 'nostrFetchVoiceRooms' });
            vscode.postMessage({ command: 'nostrGetVoiceRooms' });
        });
        function showCreateForm() {
            var form = document.getElementById('voice-create-form');
            var onboard = document.getElementById('voice-onboarding');
            var list = document.getElementById('voice-room-list');
            if (form) form.style.display = 'block';
            if (onboard) onboard.style.display = 'none';
            if (list) list.style.display = 'none';
            var nameInput = document.getElementById('voice-room-name');
            if (nameInput) nameInput.focus();
        }
        if (createBtn) createBtn.addEventListener('click', showCreateForm);
        if (heroCreateBtn) heroCreateBtn.addEventListener('click', showCreateForm);
        if (createSubmit) createSubmit.addEventListener('click', function () {
            var nameEl = document.getElementById('voice-room-name');
            var summaryEl = document.getElementById('voice-room-summary');
            var name = nameEl ? nameEl.value.trim() : '';
            if (!name) return;
            vscode.postMessage({ command: 'nostrCreateVoiceRoom', name: name, summary: summaryEl ? summaryEl.value.trim() : '' });
            if (nameEl) nameEl.value = '';
            if (summaryEl) summaryEl.value = '';
            var form = document.getElementById('voice-create-form');
            if (form) form.style.display = 'none';
        });
        if (createCancel) createCancel.addEventListener('click', function () {
            var form = document.getElementById('voice-create-form');
            if (form) form.style.display = 'none';
        });
        if (leaveBtn) leaveBtn.addEventListener('click', function () {
            if (_activeRoomATag) {
                vscode.postMessage({ command: 'nostrLeaveRoom', roomATag: _activeRoomATag });
            }
        });
        if (raiseHandBtn) raiseHandBtn.addEventListener('click', function () {
            if (_activeRoomATag) {
                vscode.postMessage({ command: 'nostrRaiseHand', roomATag: _activeRoomATag });
            }
        });
        if (chatSendBtn) chatSendBtn.addEventListener('click', function () {
            if (_activeRoomATag && chatInput && chatInput.value.trim()) {
                vscode.postMessage({ command: 'nostrSendLiveChat', roomATag: _activeRoomATag, message: chatInput.value.trim() });
                chatInput.value = '';
            }
        });
        if (chatInput) chatInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey && _activeRoomATag && chatInput.value.trim()) {
                e.preventDefault();
                vscode.postMessage({ command: 'nostrSendLiveChat', roomATag: _activeRoomATag, message: chatInput.value.trim() });
                chatInput.value = '';
            }
        });
        // Mic toggle — uses ffmpeg native capture via extension host (no browser permissions needed)
        if (micToggle) micToggle.addEventListener('click', function () {
            if (_voicePTTMode) {
                // In PTT mode, clicking the button is a no-op (use PTT key instead)
                // But allow toggling PTT mode off by clicking
                return;
            }
            if (!_voiceMicOn) {
                // Turn mic ON — request ffmpeg capture from extension
                var micLabel = document.getElementById('voice-mic-label');
                if (micLabel) micLabel.textContent = 'STARTING...';
                vscode.postMessage({ command: 'startMicCapture', device: _voiceSelectedDevice || undefined });
            } else {
                // Turn mic OFF
                vscode.postMessage({ command: 'stopMicCapture' });
            }
        });
    })();

    // ── THEME IMPORT HANDLERS ──
    (function () {
        var applyBtn = document.getElementById('theme-accent-apply');
        var resetBtn = document.getElementById('theme-accent-reset');
        var input = document.getElementById('theme-accent-input');
        var preview = document.getElementById('theme-accent-preview');
        if (applyBtn) applyBtn.addEventListener('click', function () {
            var val = input ? input.value.trim() : '';
            if (/^#[0-9a-fA-F]{6}$/.test(val)) {
                document.documentElement.style.setProperty('--accent', val);
                if (preview) preview.style.background = val;
            }
        });
        if (resetBtn) resetBtn.addEventListener('click', function () {
            document.documentElement.style.removeProperty('--accent');
            if (preview) preview.style.background = 'var(--accent)';
            if (input) input.value = '';
        });
        if (input) input.addEventListener('input', function () {
            var val = input.value.trim();
            if (/^#[0-9a-fA-F]{6}$/.test(val) && preview) {
                preview.style.background = val;
            }
        });
    })();

    // ── NOSTR EVENT HANDLER ──
    function handleNostrEvent(event) {
        if (!event) return;
        if (event.kind === 1) {
            if (_chatMessages.some(function (m) { return m.id === event.id; })) return;
            _chatMessages.push(event);
            _chatMessages.sort(function (a, b) { return a.created_at - b.created_at; });
            if (_chatMessages.length > 200) _chatMessages = _chatMessages.slice(-200);
            renderChatFeed();
        } else if (event.kind === 7) {
            // Reaction event — find which message it targets via 'e' tag
            var eTag = (event.tags || []).find(function (t) { return t[0] === 'e'; });
            if (!eTag) return;
            var targetId = eTag[1];
            var emoji = event.content || '+';
            if (!_reactions[targetId]) _reactions[targetId] = { selfReacted: {} };
            _reactions[targetId][emoji] = (_reactions[targetId][emoji] || 0) + 1;
            if (event.pubkey === _nostrPubkey) _reactions[targetId].selfReacted[emoji] = true;
            renderChatFeed();
        } else if (event.kind === 30078) {
            if (_workflowEvents.some(function (w) { return w.id === event.id; })) return;
            _workflowEvents.push(event);
            _workflowEvents.sort(function (a, b) { return b.created_at - a.created_at; });
            renderWorkflowFeed();
        } else if (event.kind === 1018) {
            // NIP-88: Poll definition
            if (!_polls[event.id]) {
                _polls[event.id] = {
                    id: event.id,
                    question: event.content,
                    options: (event.tags || []).filter(t => t[0] === 'option').map(t => ({ index: parseInt(t[1]), label: t[2] })),
                    expiresAt: (event.tags || []).find(t => t[0] === 'expiration') ? parseInt((event.tags || []).find(t => t[0] === 'expiration')[1]) : null
                };
                renderChatFeed();
            }
        } else if (event.kind === 1068) {
            // NIP-88: Poll response/vote
            var eTag = (event.tags || []).find(t => t[0] === 'e');
            if (eTag) {
                var pollId = eTag[1];
                var responseTags = (event.tags || []).filter(t => t[0] === 'response');
                if (!_pollVotes[pollId]) _pollVotes[pollId] = {};
                responseTags.forEach(t => {
                    var idx = parseInt(t[1]);
                    _pollVotes[pollId][idx] = (_pollVotes[pollId][idx] || 0) + 1;
                });
                if (event.pubkey === _nostrPubkey) {
                    if (!_polls[pollId]) _polls[pollId] = {};
                    _polls[pollId].voted = true;
                }
                renderChatFeed();
            }
        } else if (event.kind === 30009) {
            // NIP-58: Badge definition
            var dTag = (event.tags || []).find(t => t[0] === 'd');
            if (dTag) {
                var badgeId = dTag[1];
                var aTag = "30009:" + event.pubkey + ":" + badgeId;
                _badges[aTag] = {
                    id: badgeId,
                    aTag: aTag,
                    name: ((event.tags || []).find(t => t[0] === 'name') || [])[1] || badgeId,
                    description: ((event.tags || []).find(t => t[0] === 'description') || [])[1] || '',
                    image: ((event.tags || []).find(t => t[0] === 'image') || [])[1],
                    creator: event.pubkey
                };
                renderBadgeGallery();
            }
        } else if (event.kind === 8) {
            // NIP-58: Badge award
            var aTag = ((event.tags || []).find(t => t[0] === 'a') || [])[1];
            if (aTag) {
                var pTags = (event.tags || []).filter(t => t[0] === 'p');
                pTags.forEach(t => {
                    var pubkey = t[1];
                    if (!_badgeAwards[pubkey]) _badgeAwards[pubkey] = [];
                    if (_badgeAwards[pubkey].indexOf(aTag) === -1) _badgeAwards[pubkey].push(aTag);
                    if (pubkey === _nostrPubkey && _myBadges.indexOf(aTag) === -1) _myBadges.push(aTag);
                });
                renderBadgeGallery();
                renderChatFeed();
            }
        } else if (event.kind === 1222) {
            // NIP-A0: Voice note
            if (_chatMessages.some(m => m.id === event.id)) return;
            _chatMessages.push(event);
            _chatMessages.sort((a, b) => a.created_at - b.created_at);
            renderChatFeed();
        } else if (event.kind === 10011) {
            // NIP-39: External identity
            var claims = (event.tags || []).filter(t => t[0] === 'i').map(t => {
                var parts = (t[1] || '').split(':');
                return { platform: parts[0], identity: parts[1], proof: t[2] };
            });
            _identityBadges[event.pubkey] = claims;
            renderChatFeed();
        } else if (event.kind >= 6000 && event.kind < 7000) {
            // NIP-90: DVM Result
            var eTag = (event.tags || []).find(t => t[0] === 'e');
            if (eTag) {
                var jobId = eTag[1];
                if (_dvmJobs[jobId]) {
                    _dvmJobs[jobId].status = 'completed';
                    _dvmJobs[jobId].result = event.content;
                    renderDvmJobs();
                }
            }
        } else if (event.kind === 7000) {
            // NIP-90: DVM Feedback
            var eTag = (event.tags || []).find(t => t[0] === 'e');
            var statusTag = (event.tags || []).find(t => t[0] === 'status');
            if (eTag && statusTag && _dvmJobs[eTag[1]]) {
                _dvmJobs[eTag[1]].status = statusTag[1];
                renderDvmJobs();
            }
        } else if (event.kind === 25050) {
            // WebRTC signaling event — extract peer ID for P2P voice
            // Skip our own events
            if (event.pubkey === _nostrPubkey) return;
            try {
                var payload = JSON.parse(event.content || '{}');
                // Check if this is a peerjs-offer with a peerId
                var signalTag = (event.tags || []).find(function (t) { return t[0] === 'type'; });
                var signalType = signalTag ? signalTag[1] : '';
                if (signalType === 'peerjs-offer' && payload.peerId && VoiceP2P.isConnected()) {
                    // Check if this is for our current room
                    var roomTag = (event.tags || []).find(function (t) { return t[0] === 'a'; });
                    var roomATag = roomTag ? roomTag[1] : '';
                    if (roomATag && roomATag === _activeRoomATag) {
                        console.log('[Voice] Peer discovered via Nostr:', payload.peerId);
                        VoiceP2P.connectToPeer(payload.peerId);
                    }
                }
            } catch (e) { console.warn('[Voice] Failed to parse WebRTC signal:', e); }
        }
    }

    // ── IDENTITY ──
    function handleNostrIdentity(msg) {
        _nostrPubkey = msg.pubkey || '';
        _nostrRelayCount = msg.relayCount || 0;
        _renderZapReadiness({});
        var dot = document.getElementById('nostr-dot');
        var npub = document.getElementById('nostr-npub');
        var relays = document.getElementById('nostr-relays');
        if (msg.disabled) {
            _nostrRelayCount = 0;
            if (dot) dot.className = 'dot red';
            if (npub) npub.textContent = 'Nostr service unavailable';
            if (relays) relays.textContent = 'check deps';
            _renderZapReadiness({});
            return;
        }
        if (dot) dot.className = 'dot ' + (msg.connected ? 'green pulse' : msg.npub ? 'amber pulse' : 'off');
        if (npub) npub.textContent = msg.npub || 'Generating identity...';
        if (relays) relays.textContent = (msg.relayCount || 0) + ' relay' + ((msg.relayCount || 0) !== 1 ? 's' : '');
        if (msg.connected || msg.relayCount > 0) {
            renderWorkflowFeed();
            renderChatFeed();
        }
    }

    // ── ZAP HANDLERS ──
    function handleZapReceipt(msg) {
        if (msg.eventId) {
            _zapTotals[msg.eventId] = (_zapTotals[msg.eventId] || 0) + (msg.amountSats || 0);
            // Update displayed zap total on the card if visible
            var zapEl = document.querySelector('[data-zap-total="' + msg.eventId + '"]');
            if (zapEl) { zapEl.textContent = _zapTotals[msg.eventId] + ' sats'; }
        }
    }

    function handleZapResult(msg) {
        if (!msg.success) {
            mpToast('Zap failed: ' + (msg.error || 'Unknown error'), 'error', 5600);
            return;
        }
        if (msg.invoice) {
            // Show invoice to user — they need to pay it with their Lightning wallet
            var invoiceStr = msg.invoice;
            var copyMsg = 'Lightning invoice for ' + msg.amountSats + ' sats to ' + (msg.lud16 || 'recipient') +
                ':\n\n' + invoiceStr + '\n\nCopy this invoice and pay it in your Lightning wallet (Alby, Zeus, Phoenix, etc.)';
            mpToast('Zap invoice ready. Pay it in your Lightning wallet to complete the zap.', 'success', 4600);
            if (window.prompt) {
                window.prompt(copyMsg, invoiceStr);
            } else {
                alert(copyMsg);
            }
        } else {
            mpToast('Zap request created for ' + msg.amountSats + ' sats, but recipient does not support Nostr zaps.', 'info', 5200);
        }
    }

    // ── DM HANDLER ──
    function handleNostrDM(msg) {
        if (!msg.event || !msg.decrypted) return;
        var ev = msg.event;
        if (_dmMessages.some(function (d) { return d.event.id === ev.id; })) return;
        var pTag = (ev.tags || []).find(function (t) { return t[0] === 'p'; });
        var peerPubkey = ev.pubkey === _nostrPubkey ? (pTag ? pTag[1] : '') : ev.pubkey;
        _dmMessages.push({ event: ev, decrypted: msg.decrypted, peerPubkey: peerPubkey });
        _dmMessages.sort(function (a, b) { return a.event.created_at - b.event.created_at; });
        renderDMConversations();
        if (_activeDMPeer === peerPubkey) renderDMThread();
    }

    // ── PRESENCE ──
    function handleNostrPresence(msg) {
        // Handled by periodic polling
    }
    function handleOnlineUsers(users) {
        _onlineUsers = users || [];
        var el = document.getElementById('online-count');
        if (el) el.textContent = _onlineUsers.length;
    }

    // ── NIP-53: VOICE ROOM HANDLERS ──
    function handleVoiceRoomUpdate(room) {
        if (!room) return;
        var idx = _voiceRooms.findIndex(function (r) { return r.aTag === room.aTag; });
        if (idx >= 0) { _voiceRooms[idx] = room; } else { _voiceRooms.push(room); }
        renderVoiceRoomList();
    }
    function handleVoiceRoomList(rooms) {
        _voiceRooms = rooms || [];
        renderVoiceRoomList();
    }
    function handleVoiceLiveChat(msg) {
        if (!msg.event || msg.roomATag !== _activeRoomATag) return;
        if (_voiceChatMessages.some(function (m) { return m.id === msg.event.id; })) return;
        _voiceChatMessages.push(msg.event);
        if (_voiceChatMessages.length > 200) _voiceChatMessages = _voiceChatMessages.slice(-200);
        renderVoiceLiveChat();
    }
    function handleVoiceRoomPresence(presence) {
        if (!presence || presence.roomATag !== _activeRoomATag) return;
        _activeRoomParticipants[presence.pubkey] = presence;
        renderVoiceParticipants();
    }
    function handleVoiceRoomJoined(msg) {
        _activeRoomATag = msg.roomATag;
        _voiceChatMessages = [];
        _activeRoomParticipants = {};
        _voiceMicOn = false;
        _voiceRoomJoinTime = Date.now();
        // Start P2P voice connection for this room
        VoiceP2P.join(_activeRoomATag);
        var onboardEl = document.getElementById('voice-onboarding');
        var listEl = document.getElementById('voice-room-list');
        var createEl = document.getElementById('voice-create-form');
        var activeEl = document.getElementById('voice-active-room');
        if (onboardEl) onboardEl.style.display = 'none';
        if (listEl) listEl.style.display = 'none';
        if (createEl) createEl.style.display = 'none';
        if (activeEl) activeEl.style.display = 'flex';
        var titleEl = document.getElementById('voice-room-title');
        if (titleEl && msg.room) titleEl.textContent = msg.room.name || 'Room';
        var badgeEl = document.getElementById('voice-room-status-badge');
        if (badgeEl && msg.room) badgeEl.textContent = (msg.room.status || 'open').toUpperCase();
        // Reset mic button
        var micBtn = document.getElementById('voice-mic-toggle');
        var micLabel = document.getElementById('voice-mic-label');
        if (micBtn) micBtn.classList.remove('active');
        if (micLabel) micLabel.textContent = 'MIC OFF';
        // Start room timer
        if (_voiceRoomTimer) clearInterval(_voiceRoomTimer);
        _voiceRoomTimer = setInterval(function () {
            var elapsed = Math.floor((Date.now() - _voiceRoomJoinTime) / 1000);
            var mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
            var secs = String(elapsed % 60).padStart(2, '0');
            var timerEl = document.getElementById('voice-room-timer');
            if (timerEl) timerEl.textContent = mins + ':' + secs;
        }, 1000);
        renderVoiceParticipants();
        renderVoiceLiveChat();
    }
    function handleVoiceRoomLeft() {
        _activeRoomATag = null;
        _voiceChatMessages = [];
        _activeRoomParticipants = {};
        _voiceMicOn = false;
        if (_voiceRoomTimer) { clearInterval(_voiceRoomTimer); _voiceRoomTimer = null; }
        // Tear down audio bridge and P2P voice
        _stopAudioBridge();
        VoiceP2P.leave();
        // Stop local mic
        vscode.postMessage({ command: 'stopMicCapture' });
        var onboardEl = document.getElementById('voice-onboarding');
        var listEl = document.getElementById('voice-room-list');
        var activeEl = document.getElementById('voice-active-room');
        if (activeEl) activeEl.style.display = 'none';
        // Show onboarding or room list
        if (_voiceRooms.length > 0) {
            if (onboardEl) onboardEl.style.display = 'none';
            if (listEl) listEl.style.display = 'block';
        } else {
            if (onboardEl) onboardEl.style.display = 'block';
            if (listEl) listEl.style.display = 'none';
        }
    }
    function renderVoiceRoomList() {
        var el = document.getElementById('voice-room-list');
        var onboardEl = document.getElementById('voice-onboarding');
        if (!el) return;
        var openRooms = _voiceRooms.filter(function (r) { return r.status !== 'closed'; });
        if (openRooms.length === 0) {
            el.style.display = 'none';
            if (onboardEl && !_activeRoomATag) onboardEl.style.display = 'block';
            return;
        }
        if (onboardEl) onboardEl.style.display = 'none';
        el.style.display = 'block';
        el.innerHTML = openRooms.map(function (room) {
            var statusClass = room.status || 'open';
            var pCount = room.currentParticipants || room.participants.length || 0;
            return '<div class="voice-room-card" data-room-atag="' + _esc(room.aTag) + '">' +
                '<div style="display:flex;justify-content:space-between;align-items:center;">' +
                '<span class="voice-room-name">' + _esc(room.name) + '</span>' +
                '<span class="voice-room-status-pill ' + statusClass + '">' + statusClass.toUpperCase() + '</span>' +
                '</div>' +
                (room.summary ? '<div class="voice-room-meta">' + _esc(room.summary) + '</div>' : '') +
                '<div class="voice-room-meta" style="display:flex;justify-content:space-between;align-items:center;margin-top:4px;">' +
                '<span>Host: ' + displayName(room.hostPubkey) + '</span>' +
                '<span style="color:var(--accent);">' + pCount + ' &#128101;</span>' +
                '</div>' +
                '<div style="margin-top:6px;"><button class="btn-dim" style="font-size:9px;width:100%;">JOIN ROOM</button></div>' +
                '</div>';
        }).join('');
        el.querySelectorAll('.voice-room-card').forEach(function (card) {
            card.addEventListener('click', function () {
                var aTag = card.dataset.roomAtag;
                if (aTag) vscode.postMessage({ command: 'nostrJoinRoom', roomATag: aTag });
            });
        });
    }
    function renderVoiceParticipants() {
        var el = document.getElementById('voice-participants');
        if (!el) return;
        var parts = Object.values(_activeRoomParticipants);
        if (parts.length === 0) {
            el.innerHTML = '<div class="voice-participant-card"><div class="vp-avatar">&#128100;</div><div class="vp-name">You</div><div class="vp-role">JOINED</div><div class="vp-mic">' + (_voiceMicOn ? '&#127908;' : '&#128263;') + '</div></div>';
            return;
        }
        el.innerHTML = parts.map(function (p) {
            var isHost = p.role === 'host';
            var cls = 'voice-participant-card' + (isHost ? ' host' : '');
            var hand = p.handRaised ? '<div class="vp-hand">&#9995;</div>' : '';
            var mic = '<div class="vp-mic">&#127908;</div>';
            var initials = displayName(p.pubkey).slice(0, 2).toUpperCase();
            return '<div class="' + cls + '">' +
                hand + mic +
                '<div class="vp-avatar">' + initials + '</div>' +
                '<div class="vp-name">' + displayName(p.pubkey) + '</div>' +
                (isHost ? '<div class="vp-role">HOST</div>' : '') +
                '</div>';
        }).join('');
    }
    function renderVoiceLiveChat() {
        var el = document.getElementById('voice-live-chat');
        if (!el) return;
        el.innerHTML = _voiceChatMessages.map(function (m) {
            return '<div class="voice-chat-msg">' +
                '<span class="voice-chat-author">' + shortPubkey(m.pubkey) + '</span>' +
                '<span class="voice-chat-text">' + _esc(m.content) + '</span>' +
                '</div>';
        }).join('');
        el.scrollTop = el.scrollHeight;
    }

    // ── BLOCK LIST ──
    function handleBlockList(blocked) {
        _blockedUsers = blocked || [];
        renderBlockList();
    }
    function renderBlockList() {
        var el = document.getElementById('block-list');
        if (!el) return;
        if (_blockedUsers.length === 0) {
            el.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:8px;font-size:10px;">No blocked users</div>';
            return;
        }
        el.innerHTML = _blockedUsers.map(function (pk) {
            return '<div class="block-item"><span class="block-pubkey">' + shortPubkey(pk) + '</span>' +
                '<button class="btn-dim" style="font-size:9px;padding:1px 6px;" data-unblock="' + pk + '">UNBLOCK</button></div>';
        }).join('');
    }
    document.addEventListener('click', function (e) {
        var unblockBtn = e.target.closest('[data-unblock]');
        if (unblockBtn) {
            vscode.postMessage({ command: 'nostrUnblockUser', pubkey: unblockBtn.dataset.unblock });
        }
    });

    // ── EVENT DELETION ──
    function handleEventDeleted(eventId) {
        _chatMessages = _chatMessages.filter(function (m) { return m.id !== eventId; });
        delete _reactions[eventId];
        renderChatFeed();
    }

    // ── PROFILES ──
    function handleProfileUpdate(msg) {
        if (msg.pubkey && msg.profile) {
            _profiles[msg.pubkey] = msg.profile;
        }
    }

    // ── PRIVACY ──
    function handlePrivacyUpdate(settings) {
        if (!settings) return;
        _privacySettings = settings;
        ['chatEnabled', 'dmsEnabled', 'marketplaceEnabled', 'autoRedact', 'presenceEnabled'].forEach(function (key) {
            var el = document.getElementById('priv-' + key.replace('Enabled', '').replace('autoRedact', 'redact').replace('presence', 'presence'));
            // Map setting keys to element IDs
        });
        var toggles = document.querySelectorAll('[data-privacy]');
        toggles.forEach(function (t) {
            var key = t.dataset.privacy;
            if (settings[key] !== undefined) {
                t.classList.toggle('on', !!settings[key]);
            }
        });
    }

    // ── REDACTION PREVIEW ──
    function handleRedactResult(msg) {
        var chatWarn = document.getElementById('chat-redact-warn');
        var dmWarn = document.getElementById('dm-redact-warn');
        if (msg.wasRedacted) {
            if (chatWarn) { chatWarn.textContent = 'Auto-redacted: ' + msg.matches.join(', '); chatWarn.classList.add('visible'); }
            if (dmWarn) { dmWarn.textContent = 'Auto-redacted: ' + msg.matches.join(', '); dmWarn.classList.add('visible'); }
        } else {
            if (chatWarn) chatWarn.classList.remove('visible');
            if (dmWarn) dmWarn.classList.remove('visible');
        }
    }

    // ── CHAT RENDERING (with context menu + reactions) ──
    function _reactionBtn(evId, evPubkey, emoji, label, displayEmoji) {
        var r = _reactions[evId] || {};
        var count = r[emoji] || 0;
        var selfDid = r.selfReacted && r.selfReacted[emoji];
        return '<button class="react-btn' + (selfDid ? ' reacted' : '') + '" ' +
            'data-react-id="' + evId + '" data-react-pk="' + evPubkey + '" data-react-emoji="' + emoji + '" ' +
            'title="' + label + '">' +
            displayEmoji + (count > 0 ? ' <span class="react-count">' + count + '</span>' : '') +
            '</button>';
    }
    function renderChatFeed() {
        var feed = document.getElementById('nostr-chat-feed');
        if (!feed) return;
        if (_chatMessages.length === 0) {
            feed.innerHTML = '<div class="community-msg" style="color:var(--text-dim);text-align:center;padding:20px;">No messages yet. Be the first!</div>';
            return;
        }
        var recent = _chatMessages.slice(-50);
        feed.innerHTML = recent.map(function (ev) {
            if (ev.kind === 1018) return renderPollCard(ev);
            if (ev.kind === 1222) return renderVoiceNote(ev);

            var ts = new Date(ev.created_at * 1000).toLocaleTimeString();
            var author = displayName(ev.pubkey);
            var isSelf = ev.pubkey === _nostrPubkey;
            var safeContent = safeHTML(ev.content);

            // Add identity badges
            var badges = _identityBadges[ev.pubkey] || [];
            var badgeHtml = badges.map(function (b) {
                var icons = { github: '🛠️', twitter: '🐦', discord: '🎮', mastodon: '🐘', telegram: '✈️' };
                return '<span class="identity-badge" title="' + b.platform + ': ' + safeHTML(b.identity) + '">' + (icons[b.platform] || '✅') + '</span>';
            }).join('');

            return '<div class="community-msg" data-msg-id="' + ev.id + '" data-msg-pubkey="' + ev.pubkey + '">' +
                '<button class="msg-ctx-btn" data-ctx-msg="' + ev.id + '" data-ctx-pubkey="' + ev.pubkey + '" title="Message actions (DM, block, delete)">&#8943;</button>' +
                '<span class="msg-author" style="' + (isSelf ? 'color:var(--accent);' : '') + '" data-user-pk="' + ev.pubkey + '">' + safeHTML(author) + '</span>' +
                badgeHtml +
                '<span class="msg-time">' + ts + '</span>' +
                '<div class="msg-text">' + safeContent + '</div>' +
                '<div class="msg-reactions">' +
                _reactionBtn(ev.id, ev.pubkey, '+', 'Like this message', '&#128077; Like') +
                _reactionBtn(ev.id, ev.pubkey, '\u2665', 'Love this message', '&#10084; Love') +
                '</div>' +
                '</div>';
        }).join('');
        feed.scrollTop = feed.scrollHeight;
    }

    // ── NIP-88: POLL RENDERING ──
    function renderPollCard(ev) {
        var poll = _polls[ev.id];
        if (!poll) return '';
        var question = safeHTML(poll.question);
        var pollVotes = _pollVotes[ev.id] || {};
        var totalVotes = 0;
        Object.keys(pollVotes).forEach(function (k) { totalVotes += pollVotes[k]; });
        var hasVoted = poll.voted;
        var expired = poll.expiresAt ? (poll.expiresAt * 1000 < Date.now()) : false;

        var html = '<div class="poll-card" data-poll-id="' + ev.id + '">';
        html += '<div class="poll-question">' + question + '</div>';
        poll.options.forEach(function (opt) {
            var idx = opt.index;
            var label = safeHTML(opt.label);
            var count = pollVotes[idx] || 0;
            var pct = totalVotes > 0 ? Math.round((count / totalVotes) * 100) : 0;
            var isResults = hasVoted || expired;
            html += '<div class="poll-option' + (isResults ? ' poll-results' : '') + '" data-option="' + idx + '">';
            if (isResults) {
                html += '<div class="poll-bar" style="width:' + pct + '%;"></div>';
                html += '<span class="poll-label">' + label + '</span>';
                html += '<span class="poll-pct">' + pct + '% (' + count + ')</span>';
            } else {
                html += '<span class="poll-label">' + label + '</span>';
            }
            html += '</div>';
        });
        html += '<div class="poll-meta">' + totalVotes + ' votes';
        if (expired) {
            html += ' &middot; CLOSED';
        } else if (poll.expiresAt) {
            html += ' &middot; ends ' + new Date(poll.expiresAt * 1000).toLocaleString();
        }
        html += '</div></div>';
        return html;
    }

    // ── NIP-A0: VOICE NOTE RENDERING ──
    function renderVoiceNote(ev) {
        var urlTag = (ev.tags || []).find(function (t) { return t[0] === 'url'; });
        var durTag = (ev.tags || []).find(function (t) { return t[0] === 'duration'; });
        var url = urlTag ? urlTag[1] : '';
        var dur = durTag ? parseInt(durTag[1]) : 0;
        var ts = new Date(ev.created_at * 1000).toLocaleTimeString();
        var author = displayName(ev.pubkey);
        var isSelf = ev.pubkey === _nostrPubkey;

        return '<div class="community-msg voice-note-msg" data-msg-id="' + ev.id + '">' +
            '<span class="msg-author" style="' + (isSelf ? 'color:var(--accent);' : '') + '">' + safeHTML(author) + '</span>' +
            '<span class="msg-time">' + ts + '</span>' +
            '<div class="voice-note-player">' +
            '<button class="voice-play-btn" data-audio-url="' + url + '">&#9654;</button>' +
            '<div class="voice-waveform"></div>' +
            '<span class="voice-duration">' + Math.floor(dur / 60) + ':' + ('0' + (dur % 60)).slice(-2) + '</span>' +
            '</div></div>';
    }

    // ── NIP-58: BADGE GALLERY RENDERING ──
    function renderBadgeGallery() {
        var el = document.getElementById('badge-gallery');
        if (!el) return;
        var keys = Object.keys(_badges);
        if (keys.length === 0) {
            el.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:20px;font-size:10px;">No badges found.</div>';
            return;
        }
        el.innerHTML = keys.map(function (key) {
            var b = _badges[key];
            var imgHtml = b.image ? '<img src="' + b.image + '" style="width:48px;height:48px;border-radius:4px;" />' : '<div class="badge-icon-placeholder">&#127942;</div>';
            return '<div class="badge-card">' + imgHtml +
                '<div class="badge-name">' + safeHTML(b.name) + '</div>' +
                '<div class="badge-desc">' + safeHTML(b.description) + '</div>' +
                '<div class="badge-creator">by ' + displayName(b.creator) + '</div>' +
                '<button class="btn-dim badge-award-btn" data-badge-id="' + b.id + '" style="font-size:8px;margin-top:8px;">AWARD</button>' +
                '</div>';
        }).join('');
    }

    // ── NIP-90: DVM JOBS RENDERING ──
    function renderDvmJobs() {
        var el = document.getElementById('dvm-job-list');
        if (!el) return;
        var keys = Object.keys(_dvmJobs);
        if (keys.length === 0) {
            el.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:20px;font-size:10px;">No jobs submitted yet.</div>';
            return;
        }
        el.innerHTML = keys.reverse().map(function (id) {
            var j = _dvmJobs[id];
            var statusColor = j.status === 'completed' ? 'var(--green)' : j.status === 'error' ? 'var(--red)' : 'var(--amber)';
            return '<div class="dvm-job-card">' +
                '<div style="display:flex;justify-content:space-between;">' +
                '<span style="font-size:9px;font-weight:bold;">Job ' + id.slice(0, 8) + '...</span>' +
                '<span style="font-size:8px;color:' + statusColor + ';">' + (j.status || 'pending').toUpperCase() + '</span>' +
                '</div>' +
                '<div style="font-size:9px;color:var(--text-dim);margin-top:4px;">' + safeHTML((j.input || '').slice(0, 100)) + '</div>' +
                (j.result ? '<div class="dvm-result">' + safeHTML(j.result) + '</div>' : '') +
                '</div>';
        }).join('');
    }

    // ── NIP-39: IDENTITY CLAIMS RENDERING ──
    function renderIdentityClaims() {
        var el = document.getElementById('identity-claims-list');
        if (!el) return;
        if (_identityClaims.length === 0) {
            el.innerHTML = '<div style="color:var(--text-dim);font-size:9px;">No claims added yet</div>';
            return;
        }
        el.innerHTML = _identityClaims.map(function (c, i) {
            return '<div style="display:flex;gap:6px;align-items:center;padding:4px 0;border-bottom:1px solid var(--border);">' +
                '<span style="font-size:9px;font-weight:bold;min-width:60px;color:var(--accent);">' + safeHTML(c.platform) + '</span>' +
                '<span style="font-size:9px;flex:1;">' + safeHTML(c.identity) + '</span>' +
                '<button class="btn-dim identity-remove-btn" data-idx="' + i + '" style="font-size:8px;padding:1px 4px;">X</button>' +
                '</div>';
        }).join('');
    }

    // ── MARKETPLACE SAFETY SCANNER (lightweight mirror for ingest-time) ──
    var SAFETY_RULES = [
        { name: 'eval_call', pattern: /\beval\s*\(/gi, severity: 'critical' },
        { name: 'function_constructor', pattern: /new\s+Function\s*\(/gi, severity: 'critical' },
        { name: 'shell_subst', pattern: /\$\([^)]{4,}\)/g, severity: 'critical' },
        { name: 'pipe_bash', pattern: /\|\s*(?:ba)?sh\b/gi, severity: 'critical' },
        { name: 'curl_bash', pattern: /curl\s+[^\s|]+\s*\|\s*(?:ba)?sh/gi, severity: 'critical' },
        { name: 'sensitive_paths', pattern: /(?:\/etc\/(?:passwd|shadow|hosts)|~\/\.ssh|%APPDATA%|\.env\b)/gi, severity: 'critical' },
        { name: 'exec_call', pattern: /\bexec\s*\(\s*['"`]/gi, severity: 'warning' },
        { name: 'fs_read', pattern: /fs\.(?:readFile|writeFile|unlink|rmdir)/gi, severity: 'warning' },
        { name: 'process_env', pattern: /process\.env\b/gi, severity: 'warning' },
        { name: 'http_raw_ip', pattern: /https?:\/\/\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/gi, severity: 'warning' },
        { name: 'paste_token', pattern: /paste\s+(?:your|the)\s+(?:token|key|password|secret)/gi, severity: 'warning' },
        { name: 'share_key', pattern: /(?:share|send|enter|provide)\s+(?:your|the)\s+(?:api[_\s]?key|private[_\s]?key|secret|password)/gi, severity: 'warning' },
        { name: 'large_base64', pattern: /[A-Za-z0-9+\/=]{500,}/g, severity: 'warning' },
        { name: 'webhook_url', pattern: /(?:webhook|callback|exfil|beacon)[\s_-]*(?:url|endpoint|uri)/gi, severity: 'warning' }
    ];
    function scanDocSafety(doc) {
        var flags = [];
        var fields = [
            { name: 'name', value: doc.name || '' },
            { name: 'description', value: doc.description || '' },
            { name: 'body', value: doc.body || '' },
            { name: 'tags', value: (doc.tags || []).join(' ') }
        ];
        fields.forEach(function (field) {
            if (!field.value) return;
            SAFETY_RULES.forEach(function (rule) {
                rule.pattern.lastIndex = 0;
                var m = rule.pattern.exec(field.value);
                if (m) {
                    flags.push({ severity: rule.severity, pattern: rule.name, location: field.name, match: m[0].slice(0, 60) });
                }
            });
        });
        var criticals = flags.filter(function (f) { return f.severity === 'critical'; }).length;
        var warnings = flags.filter(function (f) { return f.severity === 'warning'; }).length;
        var score = Math.max(0, 100 - (criticals * 30) - (warnings * 10) - (flags.length * 2));
        var trustLevel = criticals > 0 ? 'blocked' : score < 80 ? 'flagged' : 'community';
        return { safe: criticals === 0, trustLevel: trustLevel, score: score, flags: flags };
    }

    // ── MARKETPLACE WORKFLOW NORMALIZATION ──
    var SOURCE_DOC_TYPES = ['workflow', 'skill', 'playbook', 'recipe'];
    var WORKFLOW_ROLE_ORDER = ['automation', 'operations', 'integration', 'knowledge'];
    var WORKFLOW_ROLE_LABELS = {
        automation: 'AUTOMATION',
        operations: 'OPERATIONS',
        integration: 'INTEGRATION',
        knowledge: 'KNOWLEDGE'
    };
    var WORKFLOW_ROLE_COLORS = {
        automation: 'var(--accent)',
        operations: '#34d399',
        integration: '#fbbf24',
        knowledge: '#60a5fa'
    };

    // ── MARKETPLACE CATEGORY TAXONOMY ──
    var MP_CATEGORIES = {
        'devops': 'DevOps & CI/CD',
        'data-eng': 'Data Engineering & ETL',
        'ml-ai': 'ML / AI Pipelines',
        'security': 'Security & Compliance',
        'code-analysis': 'Code Analysis & Review',
        'testing': 'Testing & QA',
        'docs': 'Documentation',
        'infra': 'Infrastructure & Cloud',
        'monitoring': 'Monitoring & Observability',
        'api': 'API Integration',
        'database': 'Database Operations',
        'content': 'Content Generation',
        'research': 'Research & Analysis',
        'finance': 'Financial Operations',
        'healthcare': 'Healthcare & Biotech',
        'iot': 'IoT & Edge Computing',
        'legal': 'Legal & Compliance',
        'automation': 'General Automation',
        'council': 'Council & Multi-Agent',
        'memory': 'Memory & Knowledge',
        'other': 'Other'
    };
    var _mpFilter = { search: '', category: 'all', sort: 'newest', role: 'all', source: 'all' };
    var _gistMarketplaceItems = [];  // Gist-sourced marketplace items
    var _gistSearchDebounce = null;
    var _gistIndexingTriggered = false;

    function _slugifyName(input) {
        return String(input || 'workflow')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '') || 'workflow';
    }

    function _detectWorkflowRole(sourceDocType, content, tags) {
        var role = String((content && (content.workflowRole || content.role)) || '').toLowerCase();
        if (WORKFLOW_ROLE_ORDER.indexOf(role) !== -1) return role;

        var roleTag = (tags || []).find(function (t) { return String(t).indexOf('workflow-role:') === 0; });
        if (roleTag) {
            var parsedTagRole = String(roleTag).slice('workflow-role:'.length).toLowerCase();
            if (WORKFLOW_ROLE_ORDER.indexOf(parsedTagRole) !== -1) return parsedTagRole;
        }

        var map = {
            workflow: 'automation',
            playbook: 'operations',
            recipe: 'integration',
            skill: 'knowledge'
        };
        return map[sourceDocType] || 'automation';
    }

    function _parseWorkflowDefinition(body) {
        if (!body) return null;
        if (typeof body === 'object' && !Array.isArray(body)) return body;
        if (typeof body !== 'string') return null;
        try {
            return JSON.parse(body);
        } catch (e) {
            return null;
        }
    }

    function _isWorkflowDefinition(def) {
        return !!(def && typeof def === 'object' && !Array.isArray(def) && Array.isArray(def.nodes));
    }

    function _normalizeWorkflowDefinition(body, fallback) {
        var parsed = _parseWorkflowDefinition(body);
        if (!_isWorkflowDefinition(parsed)) return null;

        var def = parsed;
        if (!Array.isArray(def.connections)) def.connections = [];
        if (!def.id) def.id = _slugifyName((fallback && fallback.name) || 'workflow');
        if (!def.name && fallback && fallback.name) def.name = fallback.name;
        if (!def.description && fallback && fallback.description) def.description = fallback.description;

        def.meta = def.meta || {};
        def.meta.marketplace = def.meta.marketplace || {};
        if (fallback && fallback.workflowRole) def.meta.marketplace.workflow_role = fallback.workflowRole;
        if (fallback && fallback.category) def.meta.marketplace.category = fallback.category;
        if (fallback && fallback.sourceDocType && fallback.sourceDocType !== 'workflow') {
            def.meta.marketplace.source_doc_type = fallback.sourceDocType;
        }
        return def;
    }

    function _buildWrappedWorkflowDefinition(parsed, sourceEventId) {
        var role = parsed.workflowRole || 'knowledge';
        var bodyText = typeof parsed.body === 'string'
            ? parsed.body
            : JSON.stringify(parsed.body || {}, null, 2);
        var baseId = _slugifyName(parsed.name || 'imported-workflow');

        return {
            id: baseId + '-wrapped',
            name: parsed.name || 'Imported Workflow',
            description: parsed.description || 'Legacy marketplace listing wrapped as executable workflow.',
            nodes: [
                { id: 'input', type: 'input' },
                {
                    id: 'attach_context',
                    type: 'set',
                    parameters: {
                        mode: 'append',
                        values: {
                            workflow_role: role,
                            source_doc_type: parsed.sourceDocType || 'workflow',
                            imported_name: parsed.name || '',
                            imported_description: parsed.description || '',
                            imported_body: bodyText
                        }
                    }
                },
                { id: 'output', type: 'output' }
            ],
            connections: [
                { from: 'input', to: 'attach_context' },
                { from: 'attach_context', to: 'output' }
            ],
            meta: {
                marketplace: {
                    wrapped_import: true,
                    workflow_role: role,
                    source_doc_type: parsed.sourceDocType || 'workflow',
                    category: parsed.category || 'other',
                    source_event_id: sourceEventId || ''
                }
            }
        };
    }

    function _workflowDefinitionForImport(parsed, sourceEventId) {
        if (parsed && parsed.workflowDefinition) return parsed.workflowDefinition;
        return _buildWrappedWorkflowDefinition(parsed || {}, sourceEventId || '');
    }

    function parseDocContent(ev) {
        var content = {};
        try { content = JSON.parse(ev.content); } catch (e) { content = { name: 'Unknown', description: ev.content }; }
        var tags = (ev.tags || []).filter(function (t) {
            return t[0] === 't' && t[1] && t[1] !== 'ouroboros' && t[1] !== 'ouroboros-workflow' && t[1] !== 'ouroboros-doc'
                && String(t[1]).indexOf('ouroboros-') !== 0;
        }).map(function (t) { return t[1]; });
        var catTag = (ev.tags || []).find(function (t) { return t[0] === 'c'; });
        var category = catTag ? catTag[1] : (content.category || '');
        if (!MP_CATEGORIES[category]) category = 'other';

        var sourceDocType = content.docType || 'workflow';
        if (SOURCE_DOC_TYPES.indexOf(sourceDocType) === -1) sourceDocType = 'workflow';
        var workflowRole = _detectWorkflowRole(sourceDocType, content, tags);

        // Body: new schema uses 'body', old uses 'workflow'
        var body = content.body || content.workflow || '';
        var bodyFormat = content.bodyFormat || 'json';
        var schemaVersion = content.schemaVersion || 0;
        var contentDigest = content.contentDigest || '';
        var workflowDefinition = _normalizeWorkflowDefinition(body, {
            name: content.name || 'Untitled',
            description: content.description || '',
            workflowRole: workflowRole,
            category: category,
            sourceDocType: sourceDocType
        });

        var nodeCount = workflowDefinition && Array.isArray(workflowDefinition.nodes)
            ? workflowDefinition.nodes.length
            : 0;
        var lineCount = typeof body === 'string' ? body.split('\n').length : 0;

        // Safety scan on ingest
        var safetyBody = typeof body === 'string' ? body : JSON.stringify(body || {});
        var safety = scanDocSafety({ name: content.name, description: content.description, body: safetyBody, tags: tags });

        return {
            docType: 'workflow',
            sourceDocType: sourceDocType,
            workflowRole: workflowRole,
            name: content.name || 'Untitled',
            description: content.description || '',
            category: category,
            version: content.version || '1.0.0',
            complexity: content.complexity || 'moderate',
            estTime: content.estTime || 'fast',
            bodyFormat: bodyFormat,
            body: body,
            workflowDefinition: workflowDefinition,
            requiresWrapOnImport: !workflowDefinition,
            nodeCount: nodeCount,
            lineCount: lineCount,
            tags: tags,
            schemaVersion: schemaVersion,
            contentDigest: contentDigest,
            safety: safety,
            raw: content
        };
    }

    // Backward compat alias
    function parseWfContent(ev) { return parseDocContent(ev); }

    function getFilteredWorkflows() {
        // Source filter — skip Nostr items when gist-only
        if (_mpFilter.source === 'gist') return [];
        var filtered = _workflowEvents.slice();
        // Safety filter — hide blocked listings
        filtered = filtered.filter(function (ev) {
            var p = parseDocContent(ev);
            return p.safety.trustLevel !== 'blocked';
        });
        // Role filter
        if (_mpFilter.role !== 'all') {
            filtered = filtered.filter(function (ev) {
                return parseDocContent(ev).workflowRole === _mpFilter.role;
            });
        }
        // Category filter
        if (_mpFilter.category !== 'all') {
            filtered = filtered.filter(function (ev) {
                return parseDocContent(ev).category === _mpFilter.category;
            });
        }
        // Search filter
        if (_mpFilter.search) {
            var q = _mpFilter.search.toLowerCase();
            filtered = filtered.filter(function (ev) {
                var p = parseDocContent(ev);
                return p.name.toLowerCase().indexOf(q) !== -1 ||
                    p.description.toLowerCase().indexOf(q) !== -1 ||
                    p.tags.some(function (t) { return t.toLowerCase().indexOf(q) !== -1; }) ||
                    displayName(ev.pubkey).toLowerCase().indexOf(q) !== -1 ||
                    p.category.toLowerCase().indexOf(q) !== -1 ||
                    p.workflowRole.toLowerCase().indexOf(q) !== -1 ||
                    p.sourceDocType.toLowerCase().indexOf(q) !== -1;
            });
        }
        // Sort
        if (_mpFilter.sort === 'newest') filtered.sort(function (a, b) { return b.created_at - a.created_at; });
        else if (_mpFilter.sort === 'oldest') filtered.sort(function (a, b) { return a.created_at - b.created_at; });
        else if (_mpFilter.sort === 'name-az') filtered.sort(function (a, b) { return parseDocContent(a).name.localeCompare(parseDocContent(b).name); });
        else if (_mpFilter.sort === 'name-za') filtered.sort(function (a, b) { return parseDocContent(b).name.localeCompare(parseDocContent(a).name); });
        else if (_mpFilter.sort === 'nodes') filtered.sort(function (a, b) { return parseDocContent(b).nodeCount - parseDocContent(a).nodeCount; });
        else if (_mpFilter.sort === 'safety') filtered.sort(function (a, b) { return parseDocContent(b).safety.score - parseDocContent(a).safety.score; });
        return filtered;
    }

    function updateMPStats() {
        var wfEl = document.getElementById('mp-wf-count');
        var pubEl = document.getElementById('mp-pub-count');
        var catEl = document.getElementById('mp-cat-count');
        var nodeEl = document.getElementById('mp-node-count');
        if (wfEl) wfEl.textContent = _workflowEvents.length;
        var publishers = {};
        var categories = {};
        var totalNodes = 0;
        _workflowEvents.forEach(function (ev) {
            publishers[ev.pubkey] = true;
            var p = parseDocContent(ev);
            categories[p.category] = (categories[p.category] || 0) + 1;
            totalNodes += p.nodeCount;
        });
        if (pubEl) pubEl.textContent = Object.keys(publishers).length;
        if (catEl) catEl.textContent = Object.keys(categories).length;
        if (nodeEl) nodeEl.textContent = totalNodes;
    }

    function renderMPDocTypePills() {
        var el = document.getElementById('mp-doctype-pills');
        if (!el) return;
        var counts = { all: 0 };
        _workflowEvents.forEach(function (ev) {
            var role = parseDocContent(ev).workflowRole;
            counts[role] = (counts[role] || 0) + 1;
            counts.all++;
        });
        var html = '<button class="mp-cat-pill' + (_mpFilter.role === 'all' ? ' active' : '') + '" data-mp-dtype="all">ALL<span class="pill-count">' + counts.all + '</span></button>';
        WORKFLOW_ROLE_ORDER.forEach(function (role) {
            var c = counts[role] || 0;
            var color = WORKFLOW_ROLE_COLORS[role] || 'var(--text-dim)';
            html += '<button class="mp-cat-pill' + (_mpFilter.role === role ? ' active' : '') + '" data-mp-dtype="' + role + '" style="border-color:' + color + ';">' +
                WORKFLOW_ROLE_LABELS[role] + (c > 0 ? '<span class="pill-count">' + c + '</span>' : '') + '</button>';
        });
        el.innerHTML = html;
    }

    function renderMPCategories() {
        var el = document.getElementById('mp-categories');
        if (!el) return;
        var counts = {};
        _workflowEvents.forEach(function (ev) {
            var cat = parseDocContent(ev).category;
            counts[cat] = (counts[cat] || 0) + 1;
        });
        var pills = '<button class="mp-cat-pill' + (_mpFilter.category === 'all' ? ' active' : '') + '" data-mp-cat="all">ALL<span class="pill-count">' + _workflowEvents.length + '</span></button>';
        Object.keys(MP_CATEGORIES).forEach(function (key) {
            var count = counts[key] || 0;
            if (count > 0 || _workflowEvents.length === 0) {
                pills += '<button class="mp-cat-pill' + (_mpFilter.category === key ? ' active' : '') + '" data-mp-cat="' + key + '">' +
                    MP_CATEGORIES[key] + (count > 0 ? '<span class="pill-count">' + count + '</span>' : '') + '</button>';
            }
        });
        el.innerHTML = pills;
    }

    function safetyBadge(safety) {
        if (!safety) return '';
        if (safety.trustLevel === 'blocked') return '<span class="wf-safety-badge blocked" title="Blocked by safety scanner">BLOCKED</span>';
        if (safety.trustLevel === 'flagged') return '<span class="wf-safety-badge flagged" title="' + safety.flags.length + ' safety flag(s) - review before importing">\u26A0 FLAGGED</span>';
        if (safety.score >= 80) return '<span class="wf-safety-badge safe" title="Safety score: ' + safety.score + '/100">\u2713 SAFE</span>';
        return '';
    }

    function docTypeBadge() {
        return '<span class="wf-doctype-badge" style="color:var(--accent);border-color:var(--accent);">WORKFLOW</span>';
    }

    function sourceBadge(source) {
        if (source === 'gist') return '<span class="wf-source-badge gist-badge">GIST</span>';
        if (source === 'local') return '<span class="wf-source-badge local-badge">LOCAL</span>';
        return '<span class="wf-source-badge nostr-badge">NOSTR</span>';
    }

    function workflowRoleBadge(role) {
        var label = WORKFLOW_ROLE_LABELS[role] || String(role || 'automation').toUpperCase();
        var color = WORKFLOW_ROLE_COLORS[role] || 'var(--text-dim)';
        return '<span class="wf-doctype-badge" style="color:' + color + ';border-color:' + color + ';">' + label + '</span>';
    }

    function docStatLine(p) {
        if (p.nodeCount > 0) return '<span>' + p.nodeCount + ' nodes</span>';
        if (p.requiresWrapOnImport) return '<span>' + p.lineCount + ' lines</span><span>wrapped import</span>';
        return '<span>workflow metadata</span>';
    }

    // ── DOCUMENT CARD RENDERING ──
    function renderWorkflowFeed() {
        var feed = document.getElementById('nostr-wf-feed');
        if (!feed) return;
        updateMPStats();
        renderMPDocTypePills();
        renderMPCategories();
        var overlay = document.getElementById('wf-detail-overlay');
        var detailOpen = overlay && overlay.classList.contains('visible');
        if (detailOpen) return; // Don't clobber the detail view while user is reading it

        if (_workflowEvents.length === 0 && _gistMarketplaceItems.length === 0) {
            feed.innerHTML = '<div class="mp-empty">No workflows published yet.<br><span style="font-size:10px;color:var(--accent);">Be the first — hit PUBLISH to list your workflow.</span></div>';
            return;
        }
        var filtered = getFilteredWorkflows();
        if (filtered.length === 0) {
            feed.innerHTML = '<div class="mp-empty">No workflows match your filters.<br><span style="font-size:10px;">Try a different query, category, or role.</span></div>';
            return;
        }
        feed.innerHTML = filtered.map(function (ev) {
            var p = parseDocContent(ev);
            var author = displayName(ev.pubkey);
            var ts = new Date(ev.created_at * 1000).toLocaleDateString();
            var catLabel = MP_CATEGORIES[p.category] || p.category;
            var flagged = p.safety.trustLevel === 'flagged';
            return '<div class="wf-card' + (flagged ? ' wf-card-flagged' : '') + '" data-wf-detail-id="' + ev.id + '">' +
                '<div class="wf-header">' +
                sourceBadge('nostr') +
                docTypeBadge() +
                workflowRoleBadge(p.workflowRole) +
                '<div class="wf-title">' + safeHTML(p.name) + '</div>' +
                safetyBadge(p.safety) +
                '<span class="wf-cat-badge">' + safeHTML(catLabel) + '</span>' +
                '</div>' +
                '<div class="wf-author">by ' + safeHTML(author) + ' &middot; ' + ts + ' &middot; v' + safeHTML(p.version) + '</div>' +
                '<div class="wf-desc">' + safeHTML(p.description) + '</div>' +
                '<div class="wf-meta">' +
                docStatLine(p) +
                '<span>' + p.complexity + '</span>' +
                '<span>~' + p.estTime + '</span>' +
                (p.bodyFormat !== 'json' && p.bodyFormat !== 'text' ? '<span>' + p.bodyFormat + '</span>' : '') +
                '</div>' +
                (p.tags.length > 0 ? '<div class="wf-tags">' + p.tags.map(function (t) { return '<span>' + safeHTML(t) + '</span>'; }).join('') + '</div>' : '') +
                (p.requiresWrapOnImport ? '<div class="wf-flag-warn">Legacy content will be auto-wrapped into an executable workflow on import.</div>' : '') +
                (flagged ? '<div class="wf-flag-warn">\u26A0 ' + p.safety.flags.length + ' safety flag(s) detected. Review before importing.</div>' : '') +
                '<div class="wf-actions">' +
                '<button class="btn-dim" data-wf-import="' + ev.id + '"' + (flagged ? ' title="Review safety flags first"' : '') + '>IMPORT</button>' +
                '<button class="btn-dim" data-wf-detail="' + ev.id + '">DETAILS</button>' +
                '<button class="btn-dim" data-wf-react="' + ev.id + '" data-wf-pubkey="' + ev.pubkey + '">ZAP</button>' +
                '</div>' +
                '</div>';
        }).join('');

        // Append gist marketplace items (if not filtered to nostr-only)
        if (_mpFilter.source === 'all' || _mpFilter.source === 'gist') {
            var gistFiltered = _gistMarketplaceItems.filter(function (item) {
                if (_mpFilter.source === 'nostr') return false;
                if (_mpFilter.category !== 'all' && item.category !== _mpFilter.category) return false;
                if (_mpFilter.search) {
                    var q = _mpFilter.search.toLowerCase();
                    var searchable = (item.name + ' ' + item.description + ' ' + (item.tags || []).join(' ') + ' ' + item.docType).toLowerCase();
                    if (searchable.indexOf(q) === -1) return false;
                }
                return true;
            });
            if (gistFiltered.length > 0) {
                feed.innerHTML += '<div class="mp-section-header">PUBLIC GISTS<span class="pill-count">' + gistFiltered.length + '</span></div>';
                feed.innerHTML += gistFiltered.map(function (item) {
                    var author = item.pubkey.replace('github:', '');
                    var ts = item.createdAt ? new Date(item.createdAt).toLocaleDateString() : '';
                    var catLabel = MP_CATEGORIES[item.category] || item.category || 'other';
                    var dtBadge = '<span class="wf-doctype-badge" style="color:var(--accent);border-color:var(--accent);">' + (item.docType || 'recipe').toUpperCase() + '</span>';
                    return '<div class="wf-card wf-card-gist" data-gist-detail-id="' + safeHTML(item.eventId) + '">' +
                        '<div class="wf-header">' +
                        sourceBadge('gist') +
                        dtBadge +
                        '<div class="wf-title">' + safeHTML(item.name) + '</div>' +
                        '<span class="wf-cat-badge">' + safeHTML(catLabel) + '</span>' +
                        '</div>' +
                        '<div class="wf-author">by ' + safeHTML(author) + (ts ? ' &middot; ' + ts : '') + '</div>' +
                        (item.description ? '<div class="wf-desc">' + safeHTML(item.description) + '</div>' : '') +
                        (item.tags && item.tags.length > 0 ? '<div class="wf-tags">' + item.tags.map(function (t) { return '<span>' + safeHTML(t) + '</span>'; }).join('') + '</div>' : '') +
                        '<div class="wf-actions">' +
                        '<button class="btn-dim" data-gist-view="' + safeHTML(item.eventId.replace('gist:', '')) + '">VIEW</button>' +
                        '<button class="btn-dim" data-gist-fork="' + safeHTML(item.eventId.replace('gist:', '')) + '">FORK</button>' +
                        '<button class="btn-dim" data-gist-save="' + safeHTML(item.eventId.replace('gist:', '')) + '">SAVE TO MEMORY</button>' +
                        '</div>' +
                        '</div>';
                }).join('');
            }
        }

        // Hide nostr items if source filter is gist-only
        if (_mpFilter.source === 'gist') {
            // Already handled above — clear nostr cards
            var nostrCards = feed.querySelectorAll('.wf-card:not(.wf-card-gist)');
            for (var nc = 0; nc < nostrCards.length; nc++) {
                nostrCards[nc].style.display = 'none';
            }
        }

        // Pagination: load-more button
        var totalShown = filtered.length + (_mpFilter.source !== 'nostr' ? _gistMarketplaceItems.length : 0);
        if (filtered.length >= 10) {
            var oldest = filtered[filtered.length - 1].created_at;
            feed.innerHTML += '<div style="text-align:center;padding:12px;"><button class="btn-dim" id="mp-load-more" data-until="' + oldest + '">LOAD MORE</button>' +
                '<div style="font-size:8px;color:var(--text-dim);margin-top:4px;">Showing ' + totalShown + ' items (' + filtered.length + ' Nostr + ' + _gistMarketplaceItems.length + ' Gists)</div></div>';
        }
    }

    // ── GIST DETAIL VIEW ──
    function showGistDetail(gistId) {
        var overlay = document.getElementById('wf-detail-overlay');
        if (!overlay) return;
        // Find in gist items
        var item = _gistMarketplaceItems.find(function (i) { return i.eventId === 'gist:' + gistId || i.eventId === gistId; });
        if (!item) return;

        var author = (item.pubkey || '').replace('github:', '');
        var ts = item.createdAt ? new Date(item.createdAt).toLocaleString() : '';
        var catLabel = MP_CATEGORIES[item.category] || item.category || 'other';
        var dtLabel = (item.docType || 'recipe').toUpperCase();

        overlay.innerHTML =
            '<button class="btn-dim wf-detail-back" id="wf-detail-back">&larr; BACK TO MARKETPLACE</button>' +
            '<div style="display:flex;align-items:center;gap:8px;">' +
            sourceBadge('gist') +
            '<span class="wf-doctype-badge" style="color:var(--accent);border-color:var(--accent);">' + dtLabel + '</span>' +
            '<div class="wf-detail-title">' + safeHTML(item.name) + '</div>' +
            '</div>' +
            '<div class="wf-detail-meta">' +
            'by <strong>' + safeHTML(author) + '</strong> &middot; ' + ts + ' &middot; ' +
            '<span style="color:var(--accent);">' + safeHTML(catLabel) + '</span>' +
            '</div>' +
            '<div class="wf-detail-section">' +
            '<div class="wf-detail-section-title">DESCRIPTION</div>' +
            '<div class="wf-detail-body">' + safeHTML(item.description || 'No description') + '</div>' +
            '</div>' +
            '<div class="wf-detail-section">' +
            '<div class="wf-detail-section-title">TAGS</div>' +
            '<div class="wf-tags">' + (item.tags || []).map(function (t) { return '<span>' + safeHTML(t) + '</span>'; }).join('') + '</div>' +
            '</div>' +
            '<div id="gist-content-loading" style="color:var(--text-dim);font-size:10px;padding:8px;">Loading gist content...</div>' +
            '<div id="gist-content-area"></div>' +
            '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;">' +
            '<button data-gist-fork="' + safeHTML(gistId) + '">FORK TO MY GISTS</button>' +
            '<button class="btn-dim" data-gist-save="' + safeHTML(gistId) + '">SAVE TO MEMORY</button>' +
            '<button class="btn-dim" data-gist-open="' + safeHTML(gistId) + '">VIEW ON GITHUB</button>' +
            '<button class="btn-dim" id="wf-detail-back2">&larr; BACK</button>' +
            '</div>';
        overlay.classList.add('visible');

        // Fetch full content
        vscode.postMessage({ command: 'requestGistContent', gistId: gistId });
    }

    // ── DOCUMENT DETAIL VIEW ──
    function showWfDetail(eventId) {
        var ev = _workflowEvents.find(function (e) { return e.id === eventId; });
        if (!ev) return;
        var overlay = document.getElementById('wf-detail-overlay');
        if (!overlay) return;
        var p = parseDocContent(ev);
        var author = displayName(ev.pubkey);
        var ts = new Date(ev.created_at * 1000).toLocaleString();
        var catLabel = MP_CATEGORIES[p.category] || p.category;
        var roleLabel = WORKFLOW_ROLE_LABELS[p.workflowRole] || String(p.workflowRole).toUpperCase();

        // Format body for display
        var bodyPreview = '';
        if (p.workflowDefinition) {
            bodyPreview = JSON.stringify(p.workflowDefinition, null, 2);
        } else {
            bodyPreview = typeof p.body === 'string' ? p.body : JSON.stringify(p.body || {}, null, 2);
        }
        var wrappedPreview = p.requiresWrapOnImport
            ? JSON.stringify(_buildWrappedWorkflowDefinition(p, ev.id), null, 2)
            : '';

        var gistUrl = p.raw.gistUrl || '';
        var gistId = p.raw.gistId || '';
        if (gistUrl && !gistId) {
            var gistMatch = gistUrl.match(/([a-f0-9]{20,})/i);
            if (gistMatch) gistId = gistMatch[1];
        }

        var gistSection = '';
        if (gistUrl) {
            gistSection = '<div class="wf-detail-section">' +
                '<div class="wf-detail-section-title">GITHUB GIST (VERSIONED SOURCE)</div>' +
                '<div class="wf-detail-body">' +
                '<a href="' + safeHTML(gistUrl) + '" style="color:var(--accent);font-size:10px;">' + safeHTML(gistUrl) + '</a>' +
                '</div></div>';
        }

        // Safety flags section
        var safetySection = '';
        if (p.safety && p.safety.flags.length > 0) {
            safetySection = '<div class="wf-detail-section">' +
                '<div class="wf-detail-section-title">SAFETY SCAN (Score: ' + p.safety.score + '/100)</div>' +
                '<div class="wf-detail-body">' +
                p.safety.flags.map(function (f) {
                    var color = f.severity === 'critical' ? '#ef4444' : f.severity === 'warning' ? '#fbbf24' : 'var(--text-dim)';
                    return '<div style="font-size:9px;color:' + color + ';margin:2px 0;">[' + f.severity.toUpperCase() + '] ' + safeHTML(f.pattern) + ' in ' + f.location + ': <code>' + safeHTML(f.match) + '</code></div>';
                }).join('') +
                '</div></div>';
        }

        var specLine = '<strong>Type:</strong> WORKFLOW &middot; <strong>Role:</strong> ' + roleLabel + ' &middot; ';
        if (p.sourceDocType !== 'workflow') {
            specLine += '<strong>Source:</strong> ' + String(p.sourceDocType).toUpperCase() + ' &middot; ';
        }
        if (p.nodeCount > 0) {
            specLine += '<strong>Nodes:</strong> ' + p.nodeCount + ' &middot; ';
        } else {
            specLine += '<strong>Import Path:</strong> Auto-wrap executable &middot; <strong>Lines:</strong> ' + p.lineCount + ' &middot; ';
        }
        specLine += '<strong>Complexity:</strong> ' + p.complexity + ' &middot; <strong>Est. Time:</strong> ' + p.estTime + ' &middot; <strong>Publisher:</strong> ' + ev.pubkey.slice(0, 16) + '...';
        if (p.contentDigest) { specLine += ' &middot; <strong>Digest:</strong> ' + p.contentDigest.slice(0, 12) + '...'; }

        var importLabel = 'IMPORT WORKFLOW';
        var contentTitle = p.workflowDefinition ? 'WORKFLOW DEFINITION' : 'LEGACY CONTENT';

        overlay.innerHTML =
            '<button class="btn-dim wf-detail-back" id="wf-detail-back">&larr; BACK TO MARKETPLACE</button>' +
            '<div style="display:flex;align-items:center;gap:8px;">' + docTypeBadge() + workflowRoleBadge(p.workflowRole) + '<div class="wf-detail-title">' + safeHTML(p.name) + '</div>' + safetyBadge(p.safety) + '</div>' +
            '<div class="wf-detail-meta">' +
            'by <strong>' + safeHTML(author) + '</strong> &middot; ' + ts + ' &middot; ' +
            '<span style="color:var(--accent);">' + safeHTML(catLabel) + '</span> &middot; v' + safeHTML(p.version) +
            (gistUrl ? ' &middot; <span style="color:var(--green);">Gist-backed</span>' : '') +
            (p.schemaVersion > 0 ? ' &middot; <span style="color:var(--text-dim);">schema v' + p.schemaVersion + '</span>' : '') +
            '</div>' +
            '<div class="wf-detail-section">' +
            '<div class="wf-detail-section-title">DESCRIPTION</div>' +
            '<div class="wf-detail-body">' + safeHTML(p.description) + '</div>' +
            '</div>' +
            '<div class="wf-detail-section">' +
            '<div class="wf-detail-section-title">SPECIFICATIONS</div>' +
            '<div class="wf-detail-body">' + specLine + '</div>' +
            '</div>' +
            safetySection +
            gistSection +
            (p.tags.length > 0 ? '<div class="wf-detail-section"><div class="wf-detail-section-title">TAGS</div><div class="wf-tags">' + p.tags.map(function (t) { return '<span>' + safeHTML(t) + '</span>'; }).join('') + '</div></div>' : '') +
            '<div class="wf-detail-section">' +
            '<div class="wf-detail-section-title">' + contentTitle + '</div>' +
            '<pre>' + safeHTML(bodyPreview) + '</pre>' +
            '</div>' +
            (wrappedPreview ? '<div class="wf-detail-section"><div class="wf-detail-section-title">AUTO-WRAPPED EXECUTABLE PREVIEW</div><pre>' + safeHTML(wrappedPreview) + '</pre></div>' : '') +
            '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;">' +
            '<button data-wf-import="' + ev.id + '">' + importLabel + '</button>' +
            (gistId ? '<button data-wf-fork="' + gistId + '">FORK (ITERATE)</button>' : '') +
            (gistId ? '<button class="btn-dim" data-wf-history="' + gistId + '">VERSION HISTORY</button>' : '') +
            '<button data-wf-react="' + ev.id + '" data-wf-pubkey="' + ev.pubkey + '">ZAP</button>' +
            '<button class="btn-dim" id="wf-detail-back2">&larr; BACK</button>' +
            '</div>';
        overlay.classList.add('visible');
    }

    // ── DM CONVERSATIONS LIST ──
    function getDMPeers() {
        var peers = {};
        _dmMessages.forEach(function (d) {
            var pk = d.peerPubkey;
            if (!pk) return;
            if (!peers[pk]) peers[pk] = { lastTs: 0, count: 0 };
            peers[pk].count++;
            if (d.event.created_at > peers[pk].lastTs) peers[pk].lastTs = d.event.created_at;
        });
        return Object.keys(peers).map(function (pk) { return { pubkey: pk, lastTs: peers[pk].lastTs, count: peers[pk].count }; })
            .sort(function (a, b) { return b.lastTs - a.lastTs; });
    }

    function renderDMConversations() {
        var el = document.getElementById('dm-conv-list');
        if (!el) return;
        var peers = getDMPeers();
        if (peers.length === 0) {
            el.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:12px;font-size:10px;">No conversations yet</div>';
            return;
        }
        el.innerHTML = peers.map(function (p) {
            var active = p.pubkey === _activeDMPeer;
            var ts = new Date(p.lastTs * 1000).toLocaleTimeString();
            return '<div class="dm-conv-item' + (active ? ' active' : '') + '" data-dm-peer="' + p.pubkey + '">' +
                '<span class="dm-conv-name">' + safeHTML(displayName(p.pubkey)) + '</span>' +
                '<span class="dm-conv-time">' + p.count + ' msgs &middot; ' + ts + '</span>' +
                '</div>';
        }).join('');
    }

    function renderDMThread() {
        var feed = document.getElementById('dm-thread-feed');
        if (!feed) return;
        if (!_activeDMPeer) {
            feed.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:20px;font-size:10px;">Select a conversation or start a new DM</div>';
            return;
        }
        var msgs = _dmMessages.filter(function (d) { return d.peerPubkey === _activeDMPeer; });
        if (msgs.length === 0) {
            feed.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:20px;font-size:10px;">No messages in this conversation</div>';
            return;
        }
        feed.innerHTML = msgs.map(function (d) {
            var isSelf = d.event.pubkey === _nostrPubkey;
            var ts = new Date(d.event.created_at * 1000).toLocaleTimeString();
            return '<div class="community-msg">' +
                '<span class="msg-author" style="' + (isSelf ? 'color:var(--accent);' : '') + '">' + (isSelf ? 'You' : safeHTML(displayName(d.peerPubkey))) + '</span>' +
                '<span class="msg-time">' + ts + '</span>' +
                '<div class="msg-text">' + safeHTML(d.decrypted) + '</div>' +
                '</div>';
        }).join('');
        feed.scrollTop = feed.scrollHeight;
    }

    // ── CONTEXT MENU ──
    var _ctxMenu = document.getElementById('ctx-menu');
    function showContextMenu(x, y, msgId, msgPubkey) {
        if (!_ctxMenu) return;
        var isSelf = msgPubkey === _nostrPubkey;
        var items = [];
        if (!isSelf) {
            items.push('<button class="ctx-menu-item" data-ctx-action="dm" data-ctx-pk="' + msgPubkey + '">Send DM</button>');
            items.push('<button class="ctx-menu-item danger" data-ctx-action="block" data-ctx-pk="' + msgPubkey + '">Block User</button>');
        }
        if (isSelf) {
            items.push('<button class="ctx-menu-item danger" data-ctx-action="delete" data-ctx-id="' + msgId + '">Delete Message</button>');
        }
        items.push('<button class="ctx-menu-item" data-ctx-action="copy" data-ctx-pk="' + msgPubkey + '">Copy Pubkey</button>');
        _ctxMenu.innerHTML = items.join('');
        // Show off-screen first to measure, then clamp to viewport
        _ctxMenu.style.left = '-9999px';
        _ctxMenu.style.top = '-9999px';
        _ctxMenu.style.display = 'block';
        var mw = _ctxMenu.offsetWidth;
        var mh = _ctxMenu.offsetHeight;
        var vw = document.documentElement.clientWidth;
        var vh = document.documentElement.clientHeight;
        var pad = 4;
        // Clamp horizontal: prefer right-aligned to trigger, flip left if needed
        var left = x;
        if (left + mw > vw - pad) left = vw - mw - pad;
        if (left < pad) left = pad;
        // Clamp vertical: prefer below trigger, flip above if needed
        var top = y;
        if (top + mh > vh - pad) top = y - mh - 4;
        if (top < pad) top = pad;
        _ctxMenu.style.left = left + 'px';
        _ctxMenu.style.top = top + 'px';
    }
    function hideContextMenu() {
        if (_ctxMenu) _ctxMenu.style.display = 'none';
    }
    document.addEventListener('click', function (e) {
        // Context menu trigger
        var ctxBtn = e.target.closest('[data-ctx-msg]');
        if (ctxBtn) {
            var rect = ctxBtn.getBoundingClientRect();
            showContextMenu(rect.left, rect.bottom + 2, ctxBtn.dataset.ctxMsg, ctxBtn.dataset.ctxPubkey);
            e.stopPropagation();
            return;
        }
        // Context menu actions
        var ctxAction = e.target.closest('[data-ctx-action]');
        if (ctxAction) {
            var action = ctxAction.dataset.ctxAction;
            if (action === 'dm') {
                _activeDMPeer = ctxAction.dataset.ctxPk;
                // Switch to DMs tab
                document.querySelectorAll('#community-tabs button').forEach(function (b) { b.classList.remove('active'); });
                document.querySelector('[data-ctab="dms"]').classList.add('active');
                document.querySelectorAll('.community-subtab').forEach(function (t) { t.style.display = 'none'; });
                document.getElementById('ctab-dms').style.display = 'block';
                var dmInput = document.getElementById('dm-input');
                var dmSend = document.getElementById('dm-send');
                if (dmInput) { dmInput.disabled = false; dmInput.focus(); }
                if (dmSend) dmSend.disabled = false;
                renderDMConversations();
                renderDMThread();
            } else if (action === 'block') {
                vscode.postMessage({ command: 'nostrBlockUser', pubkey: ctxAction.dataset.ctxPk });
            } else if (action === 'delete') {
                vscode.postMessage({ command: 'nostrDeleteEvent', eventId: ctxAction.dataset.ctxId });
            } else if (action === 'copy') {
                var ta = document.createElement('textarea');
                ta.value = ctxAction.dataset.ctxPk;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
            }
            hideContextMenu();
            return;
        }
        // Reaction buttons — with optimistic UI feedback
        var reactBtn = e.target.closest('[data-react-id]');
        if (reactBtn) {
            var rEvId = reactBtn.dataset.reactId;
            var rEmoji = reactBtn.dataset.reactEmoji || '+';
            vscode.postMessage({
                command: 'nostrReact',
                eventId: rEvId,
                eventPubkey: reactBtn.dataset.reactPk,
                reaction: rEmoji
            });
            // Optimistic update — increment count and mark as self-reacted
            if (!_reactions[rEvId]) _reactions[rEvId] = { selfReacted: {} };
            if (!_reactions[rEvId].selfReacted[rEmoji]) {
                _reactions[rEvId][rEmoji] = (_reactions[rEvId][rEmoji] || 0) + 1;
                _reactions[rEvId].selfReacted[rEmoji] = true;
            }
            // Brief flash feedback on the button itself
            reactBtn.classList.add('reacted');
            renderChatFeed();
            return;
        }
        hideContextMenu();
    });

    // ── VOICE NOTE PLAYBACK ──
    document.addEventListener('click', function (e) {
        var playBtn = e.target.closest('.voice-play-btn');
        if (playBtn) {
            var url = playBtn.dataset.audioUrl;
            if (!url) return;

            // Resolve ipfs:// URLs
            if (url.startsWith('ipfs://')) {
                url = 'https://ipfs.io/ipfs/' + url.slice(7);
            }

            var audio = new Audio(url);
            playBtn.textContent = '⌛';
            audio.play().then(function () {
                playBtn.textContent = '⏸';
                audio.onended = function () { playBtn.textContent = '▶'; };
            }).catch(function (err) {
                console.error('[VoiceNote] Playback failed:', err);
                playBtn.textContent = '▶';
                mpToast('Playback failed: ' + err.message, 'error', 3000);
            });
        }
    });

    // ── CHAT SEND ──
    var chatSendBtn = document.getElementById('nostr-chat-send');
    if (chatSendBtn) {
        chatSendBtn.addEventListener('click', function () {
            var input = document.getElementById('nostr-chat-input');
            if (input && input.value.trim()) {
                vscode.postMessage({ command: 'nostrPublishChat', message: input.value.trim() });
                input.value = '';
                var warn = document.getElementById('chat-redact-warn');
                if (warn) warn.classList.remove('visible');
            }
        });
    }
    var chatInput = document.getElementById('nostr-chat-input');
    if (chatInput) {
        chatInput.addEventListener('keyup', function (e) {
            if (e.key === 'Enter') {
                document.getElementById('nostr-chat-send').click();
                return;
            }
            // Live redaction preview
            clearTimeout(_redactTimer);
            _redactTimer = setTimeout(function () {
                if (chatInput.value.trim()) {
                    vscode.postMessage({ command: 'nostrRedactPreview', text: chatInput.value });
                } else {
                    var w = document.getElementById('chat-redact-warn');
                    if (w) w.classList.remove('visible');
                }
            }, 300);
        });
    }

    // ── DM SEND ──
    var dmSendBtn = document.getElementById('dm-send');
    if (dmSendBtn) {
        dmSendBtn.addEventListener('click', function () {
            var input = document.getElementById('dm-input');
            if (input && input.value.trim() && _activeDMPeer) {
                vscode.postMessage({ command: 'nostrSendDM', recipientPubkey: _activeDMPeer, message: input.value.trim() });
                // Optimistic local add
                _dmMessages.push({
                    event: { id: 'local_' + Date.now(), pubkey: _nostrPubkey, created_at: Math.floor(Date.now() / 1000), kind: 4, tags: [['p', _activeDMPeer]], content: '', sig: '' },
                    decrypted: input.value.trim(),
                    peerPubkey: _activeDMPeer
                });
                input.value = '';
                renderDMThread();
                var w = document.getElementById('dm-redact-warn');
                if (w) w.classList.remove('visible');
            }
        });
    }
    var dmInput = document.getElementById('dm-input');
    if (dmInput) {
        dmInput.addEventListener('keyup', function (e) {
            if (e.key === 'Enter') {
                document.getElementById('dm-send').click();
                return;
            }
            clearTimeout(_redactTimer);
            _redactTimer = setTimeout(function () {
                if (dmInput.value.trim()) {
                    vscode.postMessage({ command: 'nostrRedactPreview', text: dmInput.value });
                } else {
                    var w = document.getElementById('dm-redact-warn');
                    if (w) w.classList.remove('visible');
                }
            }, 300);
        });
    }

    // ── DM CONVERSATION SELECTION ──
    var dmConvList = document.getElementById('dm-conv-list');
    if (dmConvList) {
        dmConvList.addEventListener('click', function (e) {
            var item = e.target.closest('[data-dm-peer]');
            if (item) {
                _activeDMPeer = item.dataset.dmPeer;
                var dmInputEl = document.getElementById('dm-input');
                var dmSendEl = document.getElementById('dm-send');
                if (dmInputEl) { dmInputEl.disabled = false; dmInputEl.focus(); }
                if (dmSendEl) dmSendEl.disabled = false;
                renderDMConversations();
                renderDMThread();
            }
        });
    }

    // ── NEW DM BUTTON ──
    var newDMBtn = document.getElementById('nostr-new-dm');
    if (newDMBtn) {
        newDMBtn.addEventListener('click', function () {
            var pk = prompt('Enter recipient public key (hex):');
            if (pk && pk.length >= 32) {
                _activeDMPeer = pk.trim();
                var dmInputEl = document.getElementById('dm-input');
                var dmSendEl = document.getElementById('dm-send');
                if (dmInputEl) { dmInputEl.disabled = false; dmInputEl.focus(); }
                if (dmSendEl) dmSendEl.disabled = false;
                renderDMConversations();
                renderDMThread();
            }
        });
    }

    // ── FETCH BUTTONS ──
    var fetchWfBtn = document.getElementById('nostr-fetch-wf');
    if (fetchWfBtn) {
        fetchWfBtn.addEventListener('click', function () {
            vscode.postMessage({ command: 'nostrFetchWorkflows' });
            // Also trigger gist indexing on refresh
            _gistIndexingTriggered = false;
            vscode.postMessage({ command: 'triggerGistIndexing' });
        });
    }
    var fetchChatBtn = document.getElementById('nostr-fetch-chat');
    if (fetchChatBtn) {
        fetchChatBtn.addEventListener('click', function () {
            vscode.postMessage({ command: 'nostrFetchChat' });
        });
    }
    var fetchDMsBtn = document.getElementById('nostr-fetch-dms');
    if (fetchDMsBtn) {
        fetchDMsBtn.addEventListener('click', function () {
            vscode.postMessage({ command: 'nostrFetchDMs' });
        });
    }
    var publishWfBtn = document.getElementById('nostr-publish-wf');
    if (publishWfBtn) {
        publishWfBtn.addEventListener('click', function () {
            var el = document.getElementById('publish-wf-modal');
            if (el) el.classList.add('active');
        });
    }

    // ── WORKFLOW OPS CONTROLS ──
    var wfRefreshBtn = document.getElementById('wfops-refresh');
    if (wfRefreshBtn) {
        wfRefreshBtn.addEventListener('click', function () {
            callTool('workflow_list', {});
        });
    }

    var wfLoadBtn = document.getElementById('wfops-load');
    if (wfLoadBtn) {
        wfLoadBtn.addEventListener('click', function () {
            if (!_wfSelectedId) {
                _wfSetExecStatus('Select a workflow first.', true);
                return;
            }
            callTool('workflow_get', { workflow_id: _wfSelectedId });
        });
    }

    var wfExecuteBtn = document.getElementById('wfops-execute');
    if (wfExecuteBtn) {
        wfExecuteBtn.addEventListener('click', function () {
            if (!_wfSelectedId) {
                _wfSetExecStatus('Select a workflow first.', true);
                return;
            }

            var inputEl = document.getElementById('wfops-input');
            var inputStr = inputEl ? inputEl.value.trim() : '';
            if (inputStr) {
                try {
                    JSON.parse(inputStr);
                } catch (err) {
                    _wfSetExecStatus('Execution input must be valid JSON.', true);
                    return;
                }
            }

            _wfSetBadge('running', 'RUNNING...');
            _wfSetExecStatus('Executing workflow: ' + _wfSelectedId, false);
            renderWorkflowNodeStates(_wfLoadedDef, null);
            renderWorkflowGraph(_wfLoadedDef, null);

            var execArgs = {
                workflow_id: _wfSelectedId,
                input_data: inputStr
            };
            var execErr = _workflowToolPreflight('workflow_execute', execArgs);
            if (execErr) {
                _wfSetBadge('error', 'ERROR');
                _wfSetExecStatus(execErr, true);
                return;
            }
            callTool('workflow_execute', execArgs);
        });
    }

    var wfListPanel = document.getElementById('wfops-list');
    if (wfListPanel) {
        wfListPanel.addEventListener('click', function (e) {
            var row = e.target.closest('[data-wfops-id]');
            if (!row) return;
            _wfSelectedId = row.dataset.wfopsId || '';
            _wfDrill = { kind: 'workflow', nodeId: '', edgeIndex: -1, workflowId: _wfSelectedId };
            renderWorkflowList();
            if (_wfSelectedId) {
                callTool('workflow_get', { workflow_id: _wfSelectedId });
            }
        });
    }

    var wfNodeStatusPanel = document.getElementById('wfops-node-status');
    if (wfNodeStatusPanel) {
        wfNodeStatusPanel.addEventListener('click', function (e) {
            var row = e.target.closest('[data-wf-node-id]');
            if (!row) return;
            var nodeId = row.getAttribute('data-wf-node-id') || '';
            _wfSelectNodeDrill(nodeId);
        });
    }

    var wfGraphEl = document.getElementById('wfops-graph');
    if (wfGraphEl) {
        var _wfClickStart = { x: 0, y: 0 };
        wfGraphEl.addEventListener('pointerdown', function (e) {
            _wfClickStart.x = e.clientX;
            _wfClickStart.y = e.clientY;
        });
        wfGraphEl.addEventListener('click', function (e) {
            // Ignore clicks that were actually drag gestures (moved > 5px)
            var dx = e.clientX - _wfClickStart.x;
            var dy = e.clientY - _wfClickStart.y;
            if (Math.sqrt(dx * dx + dy * dy) > 5) return;

            var target = e.target;
            if (!target || typeof target.closest !== 'function') return;

            var nodeEl = target.closest('[data-wf-node-id]');
            if (nodeEl) {
                _wfSelectNodeDrill(nodeEl.getAttribute('data-wf-node-id') || '');
                return;
            }

            var edgeEl = target.closest('[data-wf-edge-index]');
            if (edgeEl) {
                _wfSelectEdgeDrill(edgeEl.getAttribute('data-wf-edge-index') || '-1');
                return;
            }

            _wfSelectWorkflowDrill();
        });

        // ── SVG ZOOM + PAN (via svg-pan-zoom library) ──
        var _wfPanZoomInstance = null;

        function _wfInitPanZoom() {
            if (_wfPanZoomInstance) {
                try { _wfPanZoomInstance.destroy(); } catch (ignored) { }
                _wfPanZoomInstance = null;
            }
            if (typeof svgPanZoom !== 'function') return;
            // Only init if SVG has actual content (not just placeholder text)
            if (!wfGraphEl.querySelector('rect')) return;
            _wfPanZoomInstance = svgPanZoom(wfGraphEl, {
                zoomEnabled: true,
                panEnabled: true,
                controlIconsEnabled: false,
                dblClickZoomEnabled: true,
                mouseWheelZoomEnabled: true,
                preventMouseEventsDefault: true,
                zoomScaleSensitivity: 0.3,
                minZoom: 0.25,
                maxZoom: 8,
                fit: true,
                center: true
            });
        }

        // Re-init pan/zoom whenever the graph is re-rendered
        var _origRenderWorkflowGraph = renderWorkflowGraph;
        renderWorkflowGraph = function (workflow, nodeStates) {
            _origRenderWorkflowGraph(workflow, nodeStates);
            // Delay init slightly so SVG content is settled in the DOM
            setTimeout(_wfInitPanZoom, 50);
        };

        // ── DRAGGABLE NODES (capture-phase, coexists with svg-pan-zoom) ──
        var _wfDragState = null; // { nodeId, groupEl, startX, startY, origPositions }

        function _wfMoveNodeInSvg(groupEl, nodeId, newX, newY) {
            // Direct SVG attribute mutation — no full re-render
            var rect = groupEl.querySelector('rect');
            if (rect) {
                rect.setAttribute('x', String(newX));
                rect.setAttribute('y', String(newY));
            }
            var texts = groupEl.querySelectorAll('text');
            // Rebuild text positions relative to node
            if (texts[0]) { texts[0].setAttribute('x', String(newX + 10)); texts[0].setAttribute('y', String(newY + 18)); }
            if (texts[1]) { texts[1].setAttribute('x', String(newX + 10)); texts[1].setAttribute('y', String(newY + 33)); }
            if (texts[2]) { texts[2].setAttribute('x', String(newX + 160)); texts[2].setAttribute('y', String(newY + 18)); }
            if (texts[3]) { texts[3].setAttribute('x', String(newX + 160)); texts[3].setAttribute('y', String(newY + 33)); }
        }

        function _wfRedrawEdgesOnly() {
            if (!_wfGraphMeta) return;
            var positions = _wfGraphMeta.positions;
            var connections = _wfGraphMeta.connections;
            var nodeW = 170, nodeH = 50;
            // Find all edge path groups
            var svgEl = wfGraphEl;
            connections.forEach(function (edge) {
                var a = positions[edge.from];
                var b = positions[edge.to];
                if (!a || !b) return;
                var sx = a.x + nodeW;
                var sy = a.y + (nodeH / 2);
                var tx = b.x;
                var ty = b.y + (nodeH / 2);
                var dx = Math.max(36, (tx - sx) * 0.45);
                var path = 'M ' + sx + ' ' + sy + ' C ' + (sx + dx) + ' ' + sy + ', ' + (tx - dx) + ' ' + ty + ', ' + tx + ' ' + ty;
                // Update all paths with this edge index
                var pathEls = svgEl.querySelectorAll('[data-wf-edge-index="' + String(edge.index) + '"]');
                pathEls.forEach(function (el) {
                    if (el.tagName === 'path') el.setAttribute('d', path);
                    if (el.tagName === 'text') {
                        el.setAttribute('x', String((sx + tx) / 2));
                        el.setAttribute('y', String(((sy + ty) / 2) - 6));
                    }
                });
            });
        }

        wfGraphEl.addEventListener('pointerdown', function (e) {
            var target = e.target;
            if (!target || typeof target.closest !== 'function') return;
            var nodeEl = target.closest('[data-wf-node-id]');
            if (!nodeEl) return; // Not on a node — let svg-pan-zoom handle it

            var nodeId = nodeEl.getAttribute('data-wf-node-id');
            if (!nodeId || !_wfGraphMeta || !_wfGraphMeta.positions[nodeId]) return;

            // Intercept: prevent svg-pan-zoom from starting a pan
            e.stopPropagation();
            e.preventDefault();

            if (_wfPanZoomInstance) {
                try { _wfPanZoomInstance.disablePan(); } catch (ignored) { }
            }

            var pos = _wfGraphMeta.positions[nodeId];
            var zoom = _wfPanZoomInstance ? (_wfPanZoomInstance.getZoom() || 1) : 1;
            _wfDragState = {
                nodeId: nodeId,
                groupEl: nodeEl,
                startClientX: e.clientX,
                startClientY: e.clientY,
                origX: pos.x,
                origY: pos.y,
                zoom: zoom
            };

            nodeEl.style.cursor = 'grabbing';
        }, true); // capture phase — fires before svg-pan-zoom bubble

        document.addEventListener('pointermove', function (e) {
            if (!_wfDragState) return;
            var dx = (e.clientX - _wfDragState.startClientX) / _wfDragState.zoom;
            var dy = (e.clientY - _wfDragState.startClientY) / _wfDragState.zoom;
            var newX = _wfDragState.origX + dx;
            var newY = _wfDragState.origY + dy;

            // Update position in graph meta
            _wfGraphMeta.positions[_wfDragState.nodeId] = { x: newX, y: newY };

            // Move node visually
            _wfMoveNodeInSvg(_wfDragState.groupEl, _wfDragState.nodeId, newX, newY);

            // Redraw edges to follow
            _wfRedrawEdgesOnly();
        });

        document.addEventListener('pointerup', function (e) {
            if (!_wfDragState) return;
            var nodeId = _wfDragState.nodeId;
            var pos = _wfGraphMeta.positions[nodeId];

            // Persist dragged position
            var wfKey = _wfSelectedId || '_default';
            if (!_wfNodePositions[wfKey]) _wfNodePositions[wfKey] = {};
            _wfNodePositions[wfKey][nodeId] = { x: pos.x, y: pos.y };

            _wfDragState.groupEl.style.cursor = 'grab';
            _wfDragState = null;

            if (_wfPanZoomInstance) {
                try { _wfPanZoomInstance.enablePan(); } catch (ignored) { }
            }
        });
    }

    var wfSelectedLabel = document.getElementById('wfops-selected');
    if (wfSelectedLabel) {
        wfSelectedLabel.style.cursor = 'pointer';
        wfSelectedLabel.title = 'Reset inspector to workflow overview';
        wfSelectedLabel.addEventListener('click', function () {
            _wfSelectWorkflowDrill();
        });
    }

    // ── MARKETPLACE SEARCH ──
    var mpSearchInput = document.getElementById('mp-search');
    var _mpSearchTimer = null;
    if (mpSearchInput) {
        mpSearchInput.addEventListener('input', function () {
            clearTimeout(_mpSearchTimer);
            _mpSearchTimer = setTimeout(function () {
                _mpFilter.search = mpSearchInput.value.trim();
                renderWorkflowFeed();
                // Debounced gist search (500ms after local filter)
                clearTimeout(_gistSearchDebounce);
                if (_mpFilter.search && _mpFilter.search.length >= 3) {
                    _gistSearchDebounce = setTimeout(function () {
                        vscode.postMessage({ command: 'requestGistSearch', query: _mpFilter.search });
                    }, 500);
                }
            }, 250);
        });
    }
    // ── MARKETPLACE SORT ──
    var mpSortSelect = document.getElementById('mp-sort');
    if (mpSortSelect) {
        mpSortSelect.addEventListener('change', function () {
            _mpFilter.sort = mpSortSelect.value;
            renderWorkflowFeed();
        });
    }
    // ── MARKETPLACE SOURCE FILTER ──
    var mpSourceFilter = document.getElementById('mp-source-filter');
    if (mpSourceFilter) {
        mpSourceFilter.addEventListener('change', function () {
            _mpFilter.source = mpSourceFilter.value;
            renderWorkflowFeed();
        });
    }
    // ── MARKETPLACE DOC TYPE PILLS (event delegation) ──
    var mpDtypeEl = document.getElementById('mp-doctype-pills');
    if (mpDtypeEl) {
        mpDtypeEl.addEventListener('click', function (e) {
            var pill = e.target.closest('[data-mp-dtype]');
            if (pill) {
                _mpFilter.role = pill.dataset.mpDtype;
                renderWorkflowFeed();
            }
        });
    }
    // ── MARKETPLACE CATEGORY PILLS (event delegation) ──
    var mpCatsEl = document.getElementById('mp-categories');
    if (mpCatsEl) {
        mpCatsEl.addEventListener('click', function (e) {
            var pill = e.target.closest('[data-mp-cat]');
            if (pill) {
                _mpFilter.category = pill.dataset.mpCat;
                renderWorkflowFeed();
            }
        });
    }
    // ── WORKFLOW FEED + DETAIL DELEGATION ──
    document.addEventListener('click', function (e) {
        // Load more (pagination)
        if (e.target.id === 'mp-load-more') {
            var until = parseInt(e.target.dataset.until, 10);
            if (until) {
                e.target.textContent = 'LOADING...';
                e.target.disabled = true;
                vscode.postMessage({ command: 'nostrFetchWorkflows', until: until - 1 });
            }
            return;
        }
        // Detail back buttons
        if (e.target.id === 'wf-detail-back' || e.target.id === 'wf-detail-back2') {
            var overlay = document.getElementById('wf-detail-overlay');
            if (overlay) overlay.classList.remove('visible');
            return;
        }
        // Detail view button
        var detailBtn = e.target.closest('[data-wf-detail]');
        if (detailBtn) {
            showWfDetail(detailBtn.dataset.wfDetail);
            return;
        }
        // Fork button (Gist)
        var forkBtn = e.target.closest('[data-wf-fork]');
        if (forkBtn) {
            if (!_ghAuthenticated) {
                vscode.postMessage({ command: 'githubAuth' });
                return;
            }
            vscode.postMessage({ command: 'githubForkGist', gistId: forkBtn.dataset.wfFork });
            return;
        }
        // History button (Gist)
        var histBtn = e.target.closest('[data-wf-history]');
        if (histBtn) {
            vscode.postMessage({ command: 'githubGetHistory', gistId: histBtn.dataset.wfHistory });
            return;
        }
        // Import from Gist button
        var importGistModalBtn = e.target.closest('#mp-import-gist-btn');
        if (importGistModalBtn) {
            var modal = document.getElementById('import-gist-modal');
            if (modal) modal.classList.add('active');
            return;
        }
        // Import button — workflow-first import path
        var importBtn = e.target.closest('[data-wf-import]');
        if (importBtn) {
            try {
                var eventId = importBtn.dataset.wfImport;
                var sourceEvent = _workflowEvents.find(function (ev) { return ev.id === eventId; });
                if (!sourceEvent) {
                    mpToast('Import failed: listing not found', 'error', 4200);
                    return;
                }

                var parsedDoc = parseDocContent(sourceEvent);
                var workflowDef = _workflowDefinitionForImport(parsedDoc, sourceEvent.id);
                var workflowDefPayload = (typeof workflowDef === 'string')
                    ? workflowDef
                    : JSON.stringify(workflowDef);

                var importSuffix = sourceEvent.id ? String(sourceEvent.id).slice(0, 12) : String(Date.now());
                var importSlug = _slugifyName(parsedDoc.name || 'workflow');
                var sourceArtifactKey = 'marketplace-source:' + importSlug + ':' + importSuffix;
                var workingArtifactKey = 'marketplace-working:' + importSlug + ':' + importSuffix;
                var sourceArtifactPayload = JSON.stringify({
                    imported_at: new Date().toISOString(),
                    source: 'nostr-marketplace',
                    event: {
                        id: sourceEvent.id || '',
                        pubkey: sourceEvent.pubkey || '',
                        created_at: sourceEvent.created_at || 0,
                        tags: sourceEvent.tags || [],
                        content: sourceEvent.content || ''
                    },
                    listing: {
                        name: parsedDoc.name || '',
                        description: parsedDoc.description || '',
                        workflow_role: parsedDoc.workflowRole || 'automation',
                        category: parsedDoc.category || 'other',
                        source_doc_type: parsedDoc.sourceDocType || 'workflow',
                        body_format: parsedDoc.bodyFormat || 'json',
                        tags: parsedDoc.tags || []
                    }
                }, null, 2);

                var importCreateArgs = { definition: workflowDefPayload };
                var importCreateErr = _workflowToolPreflight('workflow_create', importCreateArgs);
                if (importCreateErr) {
                    mpToast('Import failed: ' + importCreateErr, 'error', 5200);
                    return;
                }

                callTool('bag_induct', { key: sourceArtifactKey, content: sourceArtifactPayload, item_type: 'artifact' });
                callTool('workflow_create', importCreateArgs);
                callTool('bag_induct', { key: workingArtifactKey, content: workflowDefPayload, item_type: 'json' });

                if (parsedDoc.requiresWrapOnImport) {
                    mpToast('Imported + inducted to FelixBag (legacy listing auto-wrapped)', 'info', 4200);
                } else {
                    mpToast('Workflow imported + source/working artifacts inducted', 'success', 3200);
                }
            } catch (err) {
                console.error('[Community] Import failed:', err);
                mpToast('Import failed: ' + (err && err.message ? err.message : 'invalid listing content'), 'error', 5000);
            }
            return;
        }
        // Gist detail view
        var gistDetailBtn = e.target.closest('[data-gist-detail-id]');
        if (gistDetailBtn && !e.target.closest('[data-gist-view]') && !e.target.closest('[data-gist-fork]') && !e.target.closest('[data-gist-save]')) {
            var gId = gistDetailBtn.dataset.gistDetailId;
            if (gId) { showGistDetail(gId.replace('gist:', '')); }
            return;
        }
        var gistViewBtn = e.target.closest('[data-gist-view]');
        if (gistViewBtn) {
            showGistDetail(gistViewBtn.dataset.gistView);
            return;
        }
        // Gist fork button
        var gistForkBtn = e.target.closest('[data-gist-fork]');
        if (gistForkBtn) {
            if (!_ghAuthenticated) {
                vscode.postMessage({ command: 'githubAuth' });
                return;
            }
            vscode.postMessage({ command: 'githubForkGist', gistId: gistForkBtn.dataset.gistFork });
            mpToast('Forking gist to your account...', 'info', 2000);
            return;
        }
        // Gist save to memory
        var gistSaveBtn = e.target.closest('[data-gist-save]');
        if (gistSaveBtn) {
            var saveId = gistSaveBtn.dataset.gistSave;
            var saveItem = _gistMarketplaceItems.find(function (i) { return i.eventId === 'gist:' + saveId; });
            if (saveItem) {
                callTool('bag_induct', {
                    key: 'gist:' + saveId,
                    content: JSON.stringify(saveItem, null, 2),
                    item_type: 'json'
                });
                mpToast('Saved to FelixBag memory', 'success', 2000);
            }
            return;
        }
        // Gist import as workflow
        var gistImportWfBtn = e.target.closest('[data-gist-import-workflow]');
        if (gistImportWfBtn) {
            vscode.postMessage({ command: 'requestGistContent', gistId: gistImportWfBtn.dataset.gistImportWorkflow });
            mpToast('Importing gist as workflow...', 'info', 2000);
            return;
        }
        // Gist open on GitHub
        var gistOpenBtn = e.target.closest('[data-gist-open]');
        if (gistOpenBtn) {
            var openItem = _gistMarketplaceItems.find(function (i) { return i.eventId === 'gist:' + gistOpenBtn.dataset.gistOpen; });
            if (openItem) {
                vscode.postMessage({ command: 'openExternal', url: 'https://gist.github.com/' + gistOpenBtn.dataset.gistOpen });
            }
            return;
        }
        // Zap button (NIP-57 Lightning Zap) — with WebLN one-click support
        var reactBtn = e.target.closest('[data-wf-react]');
        if (reactBtn) {
            var zapEventId = reactBtn.dataset.wfReact;
            var zapPubkey = reactBtn.dataset.wfPubkey;
            if (!zapEventId || !zapPubkey) {
                mpToast('Zap unavailable: listing is missing event or publisher metadata', 'error', 4600);
                return;
            }
            var amountStr = window.prompt('Zap amount in sats (e.g. 21, 100, 1000):', '21');
            if (!amountStr) return;
            var amountSats = parseInt(amountStr, 10);
            if (isNaN(amountSats) || amountSats < 1) { alert('Invalid amount'); return; }
            reactBtn.textContent = _weblnAvailable ? 'PAYING...' : 'ZAPPING...';
            reactBtn.disabled = true;
            _pendingZap = { eventId: zapEventId, pubkey: zapPubkey, amountSats: amountSats };
            mpToast('Preparing zap request...', 'info', 2600);
            vscode.postMessage({
                command: 'nostrZap',
                recipientPubkey: zapPubkey,
                eventId: zapEventId,
                amountSats: amountSats,
                comment: ''
            });
            // Reputation and payment-side signaling are handled only by verified zap receipts.
            setTimeout(function () { reactBtn.textContent = _weblnAvailable ? '\u26A1 ZAP' : 'ZAP'; reactBtn.disabled = false; }, 3000);
        }
    });

    // ── PRIVACY TOGGLES ──
    document.querySelectorAll('[data-privacy]').forEach(function (toggle) {
        toggle.addEventListener('click', function () {
            var key = toggle.dataset.privacy;
            var newVal = !toggle.classList.contains('on');
            toggle.classList.toggle('on', newVal);
            var update = {};
            update[key] = newVal;
            vscode.postMessage({ command: 'nostrSetPrivacy', settings: update });
        });
    });

    // ── LIGHTNING ADDRESS (lud16) SETUP ──
    var lud16SaveBtn = document.getElementById('lud16-save');
    var lud16TestBtn = document.getElementById('lud16-test');
    var lud16CheckBtn = document.getElementById('lud16-check');
    var lud16Input = document.getElementById('lud16-input');
    var lud16Status = document.getElementById('lud16-status');
    var zapReadinessEl = document.getElementById('zap-readiness');
    var _pendingZapReadinessCheck = false;

    function _isLud16Format(addr) {
        return !!addr && addr.indexOf(' ') === -1 && addr.indexOf('@') > 0 && addr.indexOf('@') < addr.length - 1;
    }

    function _renderZapReadiness(opts) {
        if (!zapReadinessEl) return;
        var options = opts || {};
        var addr = (lud16Input && lud16Input.value ? lud16Input.value : '').trim();
        var identityOk = !!_nostrPubkey;
        var relayOk = _nostrRelayCount > 0;
        var lud16Ok = _isLud16Format(addr);
        var checking = !!options.pending;
        var lnurl = options.result || null;
        var resolvedOk = !!(lnurl && lnurl.callback);
        var nip57Ok = !!(lnurl && lnurl.allowsNostr);

        var senderReady = identityOk && relayOk;
        var receiverReady = lud16Ok && resolvedOk && nip57Ok;
        var ready = senderReady && receiverReady;

        var status = checking ? '[CHECKING]' : ready ? '[READY TO ZAP]' : '[NOT READY]';
        var rangeText = resolvedOk
            ? (Math.floor((lnurl.minSendable || 0) / 1000) + '-' + Math.floor((lnurl.maxSendable || 0) / 1000) + ' sats')
            : '-';
        var hint = '';
        if (!identityOk) hint = 'Open Community and wait for your Nostr identity to load.';
        else if (!relayOk) hint = 'Connect to at least one relay.';
        else if (!lud16Ok) hint = 'Set lud16 like you@wallet.com, then SAVE.';
        else if (!resolvedOk && !checking) hint = 'Click RUN ZAP CHECK to verify the wallet endpoint.';
        else if (resolvedOk && !nip57Ok) hint = 'Receiver wallet must support Nostr zaps (NIP-57).';
        else if (!ready && !checking) hint = 'Check wallet setup and try again.';

        zapReadinessEl.innerHTML =
            '<div style="font-weight:700;color:' + (ready ? 'var(--green)' : checking ? 'var(--amber)' : '#ef4444') + ';">' + status + '</div>' +
            '<div>' + (identityOk ? '[OK]' : '[X]') + ' Sender has Nostr identity</div>' +
            '<div>' + (relayOk ? '[OK]' : '[X]') + ' Sender connected to relay</div>' +
            '<div>' + (lud16Ok ? '[OK]' : '[X]') + ' Receiver lud16 format</div>' +
            '<div>' + (resolvedOk ? '[OK]' : '[X]') + ' Receiver wallet endpoint resolves</div>' +
            '<div>' + (nip57Ok ? '[OK]' : '[X]') + ' Receiver supports Nostr zaps</div>' +
            '<div>[MANUAL] Sender wallet has funds</div>' +
            '<div style="color:var(--text-dim);">Allowed amount: ' + rangeText + '</div>' +
            (hint ? '<div style="margin-top:4px;color:var(--amber);">Fix: ' + safeHTML(hint) + '</div>' : '');
    }

    if (lud16CheckBtn && lud16Input) {
        lud16CheckBtn.addEventListener('click', function () {
            var addr = lud16Input.value.trim();
            _pendingZapReadinessCheck = true;
            _renderZapReadiness({ pending: true });
            if (!addr || !_isLud16Format(addr)) {
                _pendingZapReadinessCheck = false;
                if (lud16Status) {
                    lud16Status.textContent = 'Invalid format. Expected: you@wallet.com';
                    lud16Status.style.color = '#ef4444';
                }
                _renderZapReadiness({});
                return;
            }
            if (lud16Status) { lud16Status.textContent = 'Checking full zap readiness...'; lud16Status.style.color = 'var(--text-dim)'; }
            vscode.postMessage({ command: 'nostrResolveLud16', lud16: addr });
        });
    }
    if (lud16SaveBtn && lud16Input) {
        lud16SaveBtn.addEventListener('click', function () {
            var addr = lud16Input.value.trim();
            if (!addr || !addr.includes('@')) {
                if (lud16Status) lud16Status.textContent = 'Invalid format. Expected: you@wallet.com';
                return;
            }
            vscode.postMessage({ command: 'nostrSetProfile', profile: { lud16: addr } });
            if (lud16Status) { lud16Status.textContent = 'Saved! Your Lightning address is now in your Nostr profile.'; lud16Status.style.color = 'var(--green)'; }
            _renderZapReadiness({});
        });
    }
    if (lud16TestBtn && lud16Input) {
        lud16TestBtn.addEventListener('click', function () {
            var addr = lud16Input.value.trim();
            if (!addr || !addr.includes('@')) {
                if (lud16Status) lud16Status.textContent = 'Invalid format. Expected: you@wallet.com';
                return;
            }
            if (lud16Status) { lud16Status.textContent = 'Testing...'; lud16Status.style.color = 'var(--text-dim)'; }
            _pendingZapReadinessCheck = true;
            _renderZapReadiness({ pending: true });
            vscode.postMessage({ command: 'nostrResolveLud16', lud16: addr });
        });
    }
    // Handle lud16 test result
    window.addEventListener('message', function (event) {
        var msg = event.data;
        if (msg.type === 'nostrLud16Result' && lud16Status) {
            if (msg.result && msg.result.callback) {
                lud16Status.textContent = 'Valid! Range: ' + Math.floor(msg.result.minSendable / 1000) + '-' + Math.floor(msg.result.maxSendable / 1000) + ' sats. Nostr zaps: ' + (msg.result.allowsNostr ? 'YES' : 'NO');
                lud16Status.style.color = 'var(--green)';
            } else {
                lud16Status.textContent = 'Could not resolve "' + msg.lud16 + '". Check the address.';
                lud16Status.style.color = '#ef4444';
            }
            if (_pendingZapReadinessCheck) {
                _pendingZapReadinessCheck = false;
                _renderZapReadiness({ result: msg.result || null });
            }
        }
    });

    _renderZapReadiness({});

    // ── PROFILE BUTTON ──
    var profileBtn = document.getElementById('nostr-profile-btn');
    if (profileBtn) {
        profileBtn.addEventListener('click', function () {
            var name = prompt('Display name (visible to community):');
            if (name !== null) {
                vscode.postMessage({ command: 'nostrSetProfile', profile: { name: name.trim() || undefined } });
            }
        });
    }

    // ── GITHUB STATE ──
    var _ghAuthenticated = false;
    var _ghUsername = null;
    var _pendingGistPublish = null; // holds workflow data while Gist is being created
    var _myGists = [];

    function handleGitHubAuth(msg) {
        _ghAuthenticated = msg.authenticated;
        _ghUsername = msg.username || null;
        var dot = document.getElementById('gh-dot');
        var uname = document.getElementById('gh-username');
        var btn = document.getElementById('gh-auth-btn');
        if (dot) dot.className = 'dot ' + (_ghAuthenticated ? 'green pulse' : 'off');
        if (uname) uname.textContent = _ghAuthenticated ? _ghUsername : 'Not connected';
        if (btn) btn.textContent = _ghAuthenticated ? 'DISCONNECT' : 'CONNECT';
        // Update gist status in publish modal
        var gistStatus = document.getElementById('pub-wf-gist-status');
        if (gistStatus) gistStatus.textContent = _ghAuthenticated ? 'as ' + _ghUsername : 'requires GitHub login';
    }

    function handleGistCreated(gist) {
        if (!gist) return;
        console.log('[GitHub] Gist created:', gist.url);
        // If we have a pending publish, now publish to Nostr with the gist URL
        if (_pendingGistPublish) {
            var p = _pendingGistPublish;
            _pendingGistPublish = null;
            if (!p.body) {
                mpToast('Publish failed: missing document body after Gist creation', 'error', 5200);
                return;
            }
            vscode.postMessage({
                command: 'nostrPublishDocument',
                docType: 'workflow',
                name: p.name,
                description: p.description || '',
                body: p.body,
                tags: p.tags, category: p.category, version: p.version,
                complexity: p.complexity, estTime: p.estTime,
                bodyFormat: p.bodyFormat,
                gistUrl: gist.url, gistId: gist.id
            });
        }
    }
    function handleGistUpdated(gist) {
        if (gist) console.log('[GitHub] Gist updated:', gist.url);
    }
    function handleGistForked(gist) {
        if (!gist) return;
        console.log('[GitHub] Forked to:', gist.url);
        // Show in detail view
        var overlay = document.getElementById('wf-detail-overlay');
        if (overlay && overlay.classList.contains('visible')) {
            var notice = document.createElement('div');
            notice.style.cssText = 'padding:8px 12px;background:rgba(0,255,150,0.1);border:1px solid var(--green);color:var(--green);font-size:10px;margin-top:8px;';
            notice.innerHTML = 'Forked! Your copy: <a href="' + safeHTML(gist.url) + '" style="color:var(--accent);">' + safeHTML(gist.url) + '</a>';
            overlay.appendChild(notice);
        }
    }
    function handleGistHistory(gistId, history) {
        if (!history || !history.length) return;
        var overlay = document.getElementById('wf-detail-overlay');
        if (!overlay || !overlay.classList.contains('visible')) return;
        // Find or create history section
        var existing = document.getElementById('wf-history-section');
        if (existing) existing.remove();
        var section = document.createElement('div');
        section.id = 'wf-history-section';
        section.className = 'wf-detail-section';
        section.innerHTML = '<div class="wf-detail-section-title">VERSION HISTORY (' + history.length + ' revisions)</div>' +
            '<div style="border:1px solid var(--border);max-height:150px;overflow-y:auto;">' +
            history.map(function (h, i) {
                var ts = new Date(h.committed_at).toLocaleString();
                var changes = h.change_status || {};
                return '<div style="padding:6px 12px;border-bottom:1px solid var(--border);font-size:10px;display:flex;justify-content:space-between;">' +
                    '<span>' + (i === 0 ? '<strong>Latest</strong>' : 'Rev ' + (history.length - i)) + ' &middot; ' + ts + '</span>' +
                    '<span style="color:var(--text-dim);">+' + (changes.additions || 0) + ' -' + (changes.deletions || 0) + '</span>' +
                    '</div>';
            }).join('') +
            '</div>';
        // Insert before the workflow definition section
        var defSection = overlay.querySelector('.wf-detail-section:last-of-type');
        if (defSection) overlay.insertBefore(section, defSection);
        else overlay.appendChild(section);
    }
    function handleGistImported(result) {
        closeModals();
        if (!result) {
            console.error('[GitHub] Import failed: no workflow found in Gist');
            return;
        }
        // Import directly into local workflow engine
        if (result.workflow) {
            try {
                var normalized = _normalizeWorkflowDefinition(result.workflow, {
                    name: result.name || 'Imported Workflow',
                    description: result.description || '',
                    workflowRole: 'automation',
                    category: 'other',
                    sourceDocType: 'workflow'
                });
                if (!normalized) {
                    mpToast('Gist import failed: expected workflow JSON with nodes[]', 'error', 5000);
                    return;
                }
                var normalizedPayload = (typeof normalized === 'string')
                    ? normalized
                    : JSON.stringify(normalized);
                var gistCreateArgs = { definition: normalizedPayload };
                var gistCreateErr = _workflowToolPreflight('workflow_create', gistCreateArgs);
                if (gistCreateErr) {
                    mpToast('Gist import failed: ' + gistCreateErr, 'error', 5000);
                    return;
                }
                callTool('workflow_create', gistCreateArgs);
                mpToast('Workflow imported from Gist', 'success', 3000);
                console.log('[GitHub] Imported workflow:', result.name);
            } catch (err) { console.error('[GitHub] Import create failed:', err); }
        }
    }
    function handleMyGists(gists) {
        _myGists = gists || [];
    }

    function handleGistSearchResults(msg) {
        if (msg.error) {
            console.warn('[Gist Search] Error:', msg.error);
            return;
        }
        var items = msg.items || [];
        // Deduplicate by eventId
        items.forEach(function (item) {
            var existing = _gistMarketplaceItems.find(function (g) { return g.eventId === item.eventId; });
            if (!existing) {
                _gistMarketplaceItems.push(item);
            }
        });
        renderWorkflowFeed();
    }

    function handleGistContentResult(msg) {
        var loadingEl = document.getElementById('gist-content-loading');
        var contentEl = document.getElementById('gist-content-area');
        if (loadingEl) loadingEl.style.display = 'none';
        if (!contentEl) return;

        if (msg.error) {
            contentEl.innerHTML = '<div style="color:#ef4444;font-size:10px;">Failed to load gist content: ' + safeHTML(msg.error) + '</div>';
            return;
        }

        var gist = msg.gist;
        if (!gist || !gist.files) {
            contentEl.innerHTML = '<div style="color:var(--text-dim);font-size:10px;">No files found in gist.</div>';
            return;
        }

        var html = '';
        var fileNames = Object.keys(gist.files);
        fileNames.forEach(function (fname) {
            var file = gist.files[fname];
            var lang = (file.language || '').toLowerCase();
            html += '<div class="wf-detail-section">' +
                '<div class="wf-detail-section-title">' + safeHTML(fname) +
                (lang ? ' <span style="color:var(--text-dim);font-size:9px;">(' + lang + ')</span>' : '') +
                (file.size ? ' <span style="color:var(--text-dim);font-size:9px;">' + file.size + ' bytes</span>' : '') +
                '</div>' +
                '<pre>' + safeHTML(file.content || '') + '</pre>' +
                '</div>';
        });

        // Add workflow import button if it looks like a workflow
        var hasWorkflow = fileNames.some(function (f) {
            return f.toLowerCase().indexOf('workflow') !== -1 || f.toLowerCase().endsWith('.json');
        });
        if (hasWorkflow) {
            html += '<div style="margin-top:8px;"><button class="btn-dim" data-gist-import-workflow="' + safeHTML(msg.gistId) + '">IMPORT AS WORKFLOW</button></div>';
        }

        contentEl.innerHTML = html;
    }

    function handleGistIndexingComplete(msg) {
        if (msg.totalIndexed > 0) {
            console.log('[Gist Indexing] Indexed ' + msg.totalIndexed + ' new gists');
        }
    }

    // ── GITHUB AUTH BUTTON ──
    var ghAuthBtn = document.getElementById('gh-auth-btn');
    if (ghAuthBtn) {
        ghAuthBtn.addEventListener('click', function () {
            if (_ghAuthenticated) {
                vscode.postMessage({ command: 'githubSignOut' });
            } else {
                vscode.postMessage({ command: 'githubAuth' });
            }
        });
    }

    // ── IMPORT FROM GIST MODAL ──
    var importGistBtn = document.getElementById('import-gist-btn');
    if (importGistBtn) {
        importGistBtn.addEventListener('click', function () {
            var urlInput = document.getElementById('import-gist-url');
            if (urlInput && urlInput.value.trim()) {
                vscode.postMessage({ command: 'githubImportFromUrl', url: urlInput.value.trim() });
                urlInput.value = '';
            }
        });
    }

    function doPublishWorkflow() {
        var role = (document.getElementById('pub-wf-role') || {}).value || 'automation';
        var name = (((document.getElementById('pub-wf-name') || {}).value) || '').trim();
        var desc = (((document.getElementById('pub-wf-desc') || {}).value) || '').trim();
        var bodyInput = (((document.getElementById('pub-wf-json') || {}).value) || '').trim();
        var tagsStr = (((document.getElementById('pub-wf-tags') || {}).value) || '').trim();
        var category = (document.getElementById('pub-wf-category') || {}).value || 'other';
        var version = (document.getElementById('pub-wf-version') || {}).value || '1.0.0';
        var complexity = (document.getElementById('pub-wf-complexity') || {}).value || 'moderate';
        var estTime = (document.getElementById('pub-wf-time') || {}).value || 'fast';
        var gistCheckbox = document.getElementById('pub-wf-gist');
        var backWithGist = gistCheckbox ? gistCheckbox.checked : false;
        if (!name || !bodyInput) {
            mpToast('Name and content are required', 'error', 3200);
            return;
        }

        var workflowDef = _normalizeWorkflowDefinition(bodyInput, {
            name: name,
            description: desc,
            workflowRole: role,
            category: category,
            sourceDocType: 'workflow'
        });
        if (!workflowDef) {
            mpToast('Workflow content must be valid JSON with a nodes[] array', 'error', 5000);
            return;
        }

        var body = JSON.stringify(workflowDef, null, 2);
        var tags = tagsStr ? tagsStr.split(',').map(function (t) { return t.trim(); }).filter(Boolean) : [];
        var roleTag = 'workflow-role:' + role;
        if (tags.indexOf(roleTag) === -1) tags.push(roleTag);
        if (tags.indexOf('workflow') === -1) tags.push('workflow');
        var bodyFormat = 'json';

        var meta = { category: category, version: version, complexity: complexity, estTime: estTime, docType: 'workflow', bodyFormat: bodyFormat, workflowRole: role };

        mpToast('Publishing workflow...', 'info', 10000);

        if (backWithGist && _ghAuthenticated) {
            _pendingGistPublish = {
                name: name, description: desc, body: body, docType: 'workflow', workflowRole: role,
                tags: tags, category: category, version: version,
                complexity: complexity, estTime: estTime, bodyFormat: bodyFormat
            };
            vscode.postMessage({
                command: 'githubCreateGist',
                name: name, workflow: body, description: desc,
                isPublic: true, meta: meta
            });
        } else {
            vscode.postMessage({
                command: 'nostrPublishDocument',
                docType: 'workflow', name: name, description: desc, body: body,
                tags: tags, category: category, version: version,
                complexity: complexity, estTime: estTime, bodyFormat: bodyFormat
            });
        }
        closeModals();
    }
    window.doPublishWorkflow = doPublishWorkflow;

    // ══════════════════════════════════════════════════════════════════
    // UX THEME ENGINE
    // ══════════════════════════════════════════════════════════════════
    // Security-first preset analysis:
    //   Commander (default) — balanced info density, standard pubkey display, presence ON
    //   Operator — max data density, all metrics visible, compact but full exposure
    //   Observer — read-only feel, larger type, relaxed, standard privacy
    //   Stealth — HIDES pubkeys, disables presence, hides identity bar, max redaction,
    //             no reactions (prevents behavioral fingerprinting), timestamps relative
    //             (prevents timezone inference), no online bar (prevents presence tracking)
    //   Accessible — high contrast, large fonts, no motion, focus indicators,
    //                hidden pubkeys (screen reader safety), aria hints ON
    // ══════════════════════════════════════════════════════════════════

    var UX_DEFAULTS = {
        preset: 'commander',
        // Layout
        density: 'standard', spacing: 12, borderRadius: 0, cardPadding: 12,
        // Typography
        fontSize: 12, lineHeight: 15, headerSize: 14, fontFamily: 'mono',
        // Colors
        accentColor: '#00ff88', surfaceColor: '#1a1a2e', borderColor: '#2a2a4a',
        dimOpacity: 55, contrast: 'normal',
        // Motion
        transitions: true, pulseEffects: true, transitionSpeed: 150, smoothScroll: true,
        // Info density
        cardDetail: 'standard', truncateLength: 120, timestampFormat: 'time',
        showStats: true, compactMessages: false,
        // Privacy appearance
        pubkeyDisplay: 'short', showOnlineBar: true, showIdentityBar: true, showReactions: true,
        // Notifications
        showRedactWarn: true, errorDisplay: 'inline', showSuccess: true,
        // Accessibility
        reducedMotion: false, highContrast: false, focusIndicators: true, ariaHints: false
    };

    var UX_PRESETS = {
        commander: {
            preset: 'commander',
            density: 'standard', spacing: 12, borderRadius: 0, cardPadding: 12,
            fontSize: 12, lineHeight: 15, headerSize: 14, fontFamily: 'mono',
            accentColor: '#00ff88', surfaceColor: '#1a1a2e', borderColor: '#2a2a4a',
            dimOpacity: 55, contrast: 'normal',
            transitions: true, pulseEffects: true, transitionSpeed: 150, smoothScroll: true,
            cardDetail: 'standard', truncateLength: 120, timestampFormat: 'time',
            showStats: true, compactMessages: false,
            pubkeyDisplay: 'short', showOnlineBar: true, showIdentityBar: true, showReactions: true,
            showRedactWarn: true, errorDisplay: 'inline', showSuccess: true,
            reducedMotion: false, highContrast: false, focusIndicators: true, ariaHints: false
        },
        operator: {
            preset: 'operator',
            density: 'compact', spacing: 6, borderRadius: 0, cardPadding: 8,
            fontSize: 10, lineHeight: 13, headerSize: 12, fontFamily: 'mono',
            accentColor: '#00ff88', surfaceColor: '#111122', borderColor: '#222244',
            dimOpacity: 45, contrast: 'normal',
            transitions: true, pulseEffects: true, transitionSpeed: 80, smoothScroll: true,
            cardDetail: 'full', truncateLength: 200, timestampFormat: 'time',
            showStats: true, compactMessages: true,
            pubkeyDisplay: 'short', showOnlineBar: true, showIdentityBar: true, showReactions: true,
            showRedactWarn: true, errorDisplay: 'inline', showSuccess: true,
            reducedMotion: false, highContrast: false, focusIndicators: true, ariaHints: false
        },
        observer: {
            preset: 'observer',
            density: 'spacious', spacing: 18, borderRadius: 4, cardPadding: 16,
            fontSize: 14, lineHeight: 18, headerSize: 16, fontFamily: 'sans',
            accentColor: '#00cc88', surfaceColor: '#1a1a2e', borderColor: '#2a2a4a',
            dimOpacity: 55, contrast: 'normal',
            transitions: true, pulseEffects: false, transitionSpeed: 250, smoothScroll: true,
            cardDetail: 'standard', truncateLength: 160, timestampFormat: 'relative',
            showStats: true, compactMessages: false,
            pubkeyDisplay: 'short', showOnlineBar: true, showIdentityBar: true, showReactions: true,
            showRedactWarn: true, errorDisplay: 'inline', showSuccess: true,
            reducedMotion: false, highContrast: false, focusIndicators: true, ariaHints: false
        },
        stealth: {
            preset: 'stealth',
            density: 'standard', spacing: 10, borderRadius: 0, cardPadding: 10,
            fontSize: 11, lineHeight: 14, headerSize: 13, fontFamily: 'mono',
            accentColor: '#666688', surfaceColor: '#0a0a14', borderColor: '#1a1a2a',
            dimOpacity: 35, contrast: 'normal',
            transitions: false, pulseEffects: false, transitionSpeed: 0, smoothScroll: false,
            cardDetail: 'minimal', truncateLength: 80, timestampFormat: 'relative',
            showStats: false, compactMessages: true,
            pubkeyDisplay: 'hidden', showOnlineBar: false, showIdentityBar: false, showReactions: false,
            showRedactWarn: true, errorDisplay: 'silent', showSuccess: false,
            reducedMotion: true, highContrast: false, focusIndicators: false, ariaHints: false
        },
        accessible: {
            preset: 'accessible',
            density: 'spacious', spacing: 16, borderRadius: 4, cardPadding: 16,
            fontSize: 16, lineHeight: 22, headerSize: 18, fontFamily: 'system',
            accentColor: '#44ddff', surfaceColor: '#000000', borderColor: '#555555',
            dimOpacity: 70, contrast: 'ultra',
            transitions: false, pulseEffects: false, transitionSpeed: 0, smoothScroll: false,
            cardDetail: 'standard', truncateLength: 160, timestampFormat: 'full',
            showStats: true, compactMessages: false,
            pubkeyDisplay: 'hidden', showOnlineBar: true, showIdentityBar: true, showReactions: true,
            showRedactWarn: true, errorDisplay: 'inline', showSuccess: true,
            reducedMotion: true, highContrast: true, focusIndicators: true, ariaHints: true
        }
    };

    var _uxSettings = {};
    function uxGet(key) {
        return _uxSettings[key] !== undefined ? _uxSettings[key] : UX_DEFAULTS[key];
    }

    var FONT_MAP = {
        mono: "'Cascadia Code','Fira Code','Consolas',monospace",
        sans: "'Segoe UI','Helvetica Neue',sans-serif",
        system: "system-ui,-apple-system,sans-serif"
    };

    function applyUXToCSS() {
        var r = document.documentElement;
        var s = function (k, v) { r.style.setProperty(k, v); };
        var fs = uxGet('fontSize');
        s('--ux-font-size', fs + 'px');
        s('--ux-font-size-sm', Math.max(fs - 2, 8) + 'px');
        s('--ux-font-size-xs', Math.max(fs - 3, 7) + 'px');
        s('--ux-font-size-lg', (fs + 2) + 'px');
        s('--ux-spacing', uxGet('spacing') + 'px');
        s('--ux-spacing-sm', Math.max(uxGet('spacing') - 4, 2) + 'px');
        s('--ux-spacing-xs', Math.max(uxGet('spacing') - 8, 1) + 'px');
        s('--ux-radius', uxGet('borderRadius') + 'px');
        s('--ux-transition', uxGet('transitions') ? (uxGet('transitionSpeed') + 'ms') : '0s');
        s('--ux-msg-padding', uxGet('compactMessages') ? '4px 8px' : '8px 12px');
        s('--ux-card-padding', uxGet('cardPadding') + 'px ' + (uxGet('cardPadding') + 2) + 'px');
        s('--ux-header-size', uxGet('headerSize') + 'px');
        s('--ux-line-height', (uxGet('lineHeight') / 10).toFixed(1));
        s('--ux-opacity-dim', (uxGet('dimOpacity') / 100).toFixed(2));
        s('--accent', uxGet('accentColor'));
        s('--accent-dim', uxGet('accentColor') + '33');
        s('--surface', uxGet('surfaceColor'));
        s('--border', uxGet('borderColor'));
        // s('--green', uxGet('accentColor')); // Keep green semantic!
        s('--mono', FONT_MAP[uxGet('fontFamily')] || FONT_MAP.mono);
        // Contrast
        var ct = uxGet('contrast');
        if (ct === 'high') { s('--text', '#ffffff'); s('--text-dim', '#aaaaaa'); }
        else if (ct === 'ultra') { s('--text', '#ffffff'); s('--text-dim', '#cccccc'); s('--border', '#666666'); }
        else { s('--text', '#e0e0e0'); s('--text-dim', '#888888'); }
        // Body classes
        var body = document.body;
        body.classList.toggle('reduce-motion', uxGet('reducedMotion'));
        if (uxGet('smoothScroll')) body.style.scrollBehavior = 'smooth';
        else body.style.scrollBehavior = 'auto';
        // Visibility toggles
        var onlineBar = document.getElementById('online-bar');
        if (onlineBar) onlineBar.style.display = uxGet('showOnlineBar') ? '' : 'none';
        var idBar = document.getElementById('nostr-identity');
        if (idBar) idBar.style.display = uxGet('showIdentityBar') ? '' : 'none';
        var ghBar = document.getElementById('github-identity');
        if (ghBar) ghBar.style.display = uxGet('showIdentityBar') ? '' : 'none';
        var statsBar = document.getElementById('mp-stats');
        if (statsBar) statsBar.style.display = uxGet('showStats') ? '' : 'none';
        // Pulse effects
        if (!uxGet('pulseEffects')) {
            var pulses = document.querySelectorAll('.pulse');
            pulses.forEach(function (p) { p.classList.remove('pulse'); p.classList.add('no-pulse'); });
        }
    }

    function syncControlsToSettings() {
        // Sync range inputs
        document.querySelectorAll('[data-ux]').forEach(function (el) {
            var key = el.dataset.ux;
            var val = uxGet(key);
            if (el.tagName === 'SELECT') { el.value = val; }
            else if (el.type === 'range') {
                el.value = val;
                var valSpan = el.nextElementSibling;
                if (valSpan && valSpan.classList.contains('ux-range-val')) {
                    if (key === 'lineHeight') valSpan.textContent = (val / 10).toFixed(1);
                    else if (key === 'dimOpacity') valSpan.textContent = val + '%';
                    else if (key === 'transitionSpeed') valSpan.textContent = val + 'ms';
                    else if (key === 'truncateLength') valSpan.textContent = val;
                    else valSpan.textContent = val + 'px';
                }
            } else if (el.type === 'color') { el.value = val; }
        });
        // Sync toggles
        document.querySelectorAll('[data-ux-toggle]').forEach(function (el) {
            var key = el.dataset.uxToggle;
            el.classList.toggle('on', !!uxGet(key));
        });
        // Sync preset cards
        document.querySelectorAll('[data-ux-preset]').forEach(function (el) {
            el.classList.toggle('active', el.dataset.uxPreset === uxGet('preset'));
        });
        // Update category summary values
        var valLayout = document.getElementById('ux-val-layout');
        if (valLayout) valLayout.textContent = uxGet('density');
        var valTypo = document.getElementById('ux-val-typography');
        if (valTypo) valTypo.textContent = uxGet('fontSize') + 'px ' + uxGet('fontFamily');
        var valColors = document.getElementById('ux-val-colors');
        if (valColors) valColors.textContent = uxGet('contrast') === 'normal' ? 'Custom' : uxGet('contrast');
        var valMotion = document.getElementById('ux-val-motion');
        if (valMotion) valMotion.textContent = uxGet('transitions') ? 'Enabled' : 'Off';
        var valInfo = document.getElementById('ux-val-info');
        if (valInfo) valInfo.textContent = uxGet('cardDetail');
        var valPriv = document.getElementById('ux-val-privappear');
        if (valPriv) valPriv.textContent = uxGet('pubkeyDisplay') === 'hidden' ? 'Stealth' : uxGet('pubkeyDisplay');
        var valNotif = document.getElementById('ux-val-notif');
        if (valNotif) valNotif.textContent = uxGet('errorDisplay');
        var valA11y = document.getElementById('ux-val-a11y');
        if (valA11y) valA11y.textContent = uxGet('reducedMotion') ? 'Reduced' : (uxGet('highContrast') ? 'High Contrast' : 'Default');
    }

    function handleUXSettings(settings) {
        _uxSettings = settings || {};
        applyUXToCSS();
        syncControlsToSettings();
    }

    function saveUX(partial) {
        Object.keys(partial).forEach(function (k) { _uxSettings[k] = partial[k]; });
        applyUXToCSS();
        syncControlsToSettings();
        vscode.postMessage({ command: 'uxSetSettings', settings: _uxSettings });
    }

    // ── CATEGORY EXPAND/COLLAPSE ──
    document.querySelectorAll('.ux-category-header').forEach(function (header) {
        header.addEventListener('click', function () {
            header.parentElement.classList.toggle('open');
        });
    });

    // ── PRESET CARD CLICKS ──
    document.querySelectorAll('[data-ux-preset]').forEach(function (card) {
        card.addEventListener('click', function () {
            var presetKey = card.dataset.uxPreset;
            var preset = UX_PRESETS[presetKey];
            if (preset) {
                _uxSettings = JSON.parse(JSON.stringify(preset));
                applyUXToCSS();
                syncControlsToSettings();
                vscode.postMessage({ command: 'uxSetSettings', settings: _uxSettings });
            }
        });
    });

    // ── RANGE INPUTS ──
    document.querySelectorAll('.ux-control input[type="range"]').forEach(function (input) {
        input.addEventListener('input', function () {
            var key = input.dataset.ux;
            var val = parseInt(input.value);
            var valSpan = input.nextElementSibling;
            if (valSpan && valSpan.classList.contains('ux-range-val')) {
                if (key === 'lineHeight') valSpan.textContent = (val / 10).toFixed(1);
                else if (key === 'dimOpacity') valSpan.textContent = val + '%';
                else if (key === 'transitionSpeed') valSpan.textContent = val + 'ms';
                else if (key === 'truncateLength') valSpan.textContent = val;
                else valSpan.textContent = val + 'px';
            }
            var update = {}; update[key] = val; update.preset = 'custom';
            saveUX(update);
        });
    });

    // ── SELECT INPUTS ──
    document.querySelectorAll('.ux-control select[data-ux]').forEach(function (sel) {
        sel.addEventListener('change', function () {
            var update = {}; update[sel.dataset.ux] = sel.value; update.preset = 'custom';
            saveUX(update);
        });
    });

    // ── COLOR INPUTS ──
    document.querySelectorAll('.ux-control input[type="color"]').forEach(function (input) {
        input.addEventListener('input', function () {
            var update = {}; update[input.dataset.ux] = input.value; update.preset = 'custom';
            saveUX(update);
        });
    });

    // ── TOGGLE SWITCHES ──
    document.querySelectorAll('[data-ux-toggle]').forEach(function (toggle) {
        toggle.addEventListener('click', function () {
            var key = toggle.dataset.uxToggle;
            var newVal = !toggle.classList.contains('on');
            toggle.classList.toggle('on', newVal);
            var update = {}; update[key] = newVal; update.preset = 'custom';
            saveUX(update);
        });
    });

    // ── EXPORT / IMPORT / RESET ──
    var uxExportBtn = document.getElementById('ux-export-btn');
    if (uxExportBtn) {
        uxExportBtn.addEventListener('click', function () {
            var json = JSON.stringify(_uxSettings, null, 2);
            var ta = document.createElement('textarea');
            ta.value = json; document.body.appendChild(ta);
            ta.select(); document.execCommand('copy');
            document.body.removeChild(ta);
            uxExportBtn.textContent = 'COPIED!';
            setTimeout(function () { uxExportBtn.textContent = 'EXPORT'; }, 1500);
        });
    }
    var uxImportBtn = document.getElementById('ux-import-btn');
    if (uxImportBtn) {
        uxImportBtn.addEventListener('click', function () {
            var json = prompt('Paste UX settings JSON:');
            if (json) {
                try {
                    var parsed = JSON.parse(json);
                    _uxSettings = parsed;
                    applyUXToCSS();
                    syncControlsToSettings();
                    vscode.postMessage({ command: 'uxSetSettings', settings: _uxSettings });
                } catch (e) { console.error('[UX] Import failed:', e); }
            }
        });
    }
    var uxResetBtn = document.getElementById('ux-reset-btn');
    if (uxResetBtn) {
        uxResetBtn.addEventListener('click', function () {
            _uxSettings = {};
            applyUXToCSS();
            syncControlsToSettings();
            vscode.postMessage({ command: 'uxResetSettings' });
        });
    }

    // ── WEB3 HELPERS ──
    function updateWeb3CategoryFilters() {
        var filterEl = document.getElementById('wf-category-filter');
        if (!filterEl) return;
        // Add Web3 categories as optgroup if not already present
        var existingGroup = filterEl.querySelector('optgroup[label="Web3"]');
        if (existingGroup) existingGroup.remove();
        if (_web3Categories.length > 0) {
            var group = document.createElement('optgroup');
            group.label = 'Web3';
            _web3Categories.forEach(function (cat) {
                var opt = document.createElement('option');
                opt.value = cat;
                opt.textContent = cat.replace(/-/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
                group.appendChild(opt);
            });
            filterEl.appendChild(group);
        }
    }

    function updateWeblnUI() {
        // Update zap buttons to show lightning icon if WebLN available
        if (_weblnAvailable) {
            document.querySelectorAll('[data-wf-react]').forEach(function (btn) {
                if (btn.textContent === 'ZAP') { btn.textContent = '\u26A1 ZAP'; }
            });
            var weblnBadge = document.getElementById('webln-badge');
            if (weblnBadge) { weblnBadge.textContent = '\u26A1 WebLN'; weblnBadge.style.display = 'inline'; }
        }
    }

    // ═══════════════ AGENT MCP CONSOLE ═══════════════
    function _safeJsonParse(value) {
        if (value == null) return null;
        if (typeof value !== 'string') return value;
        try { return JSON.parse(value); } catch (e) { return null; }
    }

    function _getAchatToolSchema(toolName) {
        if (!toolName) return null;
        var schema = _toolSchemas[toolName] || null;
        if (!schema) return null;
        return schema.inputSchema || schema.parameters || null;
    }

    function _allToolNames() {
        var names = [];
        var seen = {};
        var fromSchema = Object.keys(_toolSchemas || {});
        for (var i = 0; i < fromSchema.length; i++) {
            var n = fromSchema[i];
            if (!seen[n]) { seen[n] = true; names.push(n); }
        }
        var cats = Object.keys(CATEGORIES || {});
        for (var c = 0; c < cats.length; c++) {
            var tools = (CATEGORIES[cats[c]] && CATEGORIES[cats[c]].tools) || [];
            for (var j = 0; j < tools.length; j++) {
                var t = tools[j];
                if (!seen[t]) { seen[t] = true; names.push(t); }
            }
        }
        names.sort();
        return names;
    }

    function _loadAchatToolPolicies() {
        try {
            var raw = localStorage.getItem(_achatToolPolicyStoreKey);
            _achatToolPolicies = raw ? (JSON.parse(raw) || {}) : {};
        } catch (e) {
            _achatToolPolicies = {};
        }
    }

    function _saveAchatToolPolicies() {
        try { localStorage.setItem(_achatToolPolicyStoreKey, JSON.stringify(_achatToolPolicies || {})); }
        catch (e) { }
    }

    function _policyKeyForSlot(slot, modelSource) {
        return String(modelSource || ('slot:' + slot));
    }

    function _sanitizeGrantedTools(list) {
        var all = _allToolNames();
        var allowed = {};
        for (var i = 0; i < all.length; i++) allowed[all[i]] = 1;
        var out = [];
        var seen = {};
        var src = Array.isArray(list) ? list : [];
        for (var j = 0; j < src.length; j++) {
            var t = String(src[j] || '').trim();
            if (!t || _achatBlockedTools[t]) continue;
            if (allowed[t] || all.length === 0) {
                if (!seen[t]) { seen[t] = true; out.push(t); }
            }
        }
        return out;
    }

    function _defaultGrantedToolsForTab(tab) {
        if (!tab || !tab.canChat) return [];
        var base = _sanitizeGrantedTools(_achatDefaultGrantedTools);
        if (!base.length) {
            var fallback = _allToolNames().filter(function (t) { return !_achatBlockedTools[t]; });
            return fallback.slice(0, 40);
        }
        return base;
    }

    // ═══════════════════════════════════════════════════════════
    // AGENT CONFIG — per-slot configurable agent behavior
    // Modeled after OpenAI Custom GPTs: persona, system prompt,
    // generation params, tool policy, memory, safety rails.
    // Persisted to localStorage; can be saved/loaded from FelixBag.
    // ═══════════════════════════════════════════════════════════

    function _defaultAgentConfig() {
        return {
            // Identity & Persona
            agentName: '',
            agentDescription: '',
            systemPrompt: '',  // empty = use default loop prompt
            persona: '',       // freeform persona description

            // Generation Parameters
            temperature: 0.7,
            maxTokens: 512,
            maxIterations: 5,
            topP: 0.9,
            repetitionPenalty: 1.1,

            // Memory & Context
            contextStrategy: 'sliding-window', // 'full' | 'sliding-window' | 'summarize'
            contextWindowSize: 20,         // max messages before strategy kicks in
            persistMemory: false,          // auto-save to FelixBag after session
            memoryKey: '',                 // custom FelixBag key for this agent's memory

            // Behavior
            reappropriationEnabled: true,
            resourceApprovalMode: 'capped', // 'manual' | 'capped' | 'auto_all'
            haltOnError: false,             // stop loop on first error
            requireConfirmation: false,     // HOLD before tool execution

            // Non-disableable hard floor brakes (safety rails)
            guardMaxWallClockSec: 1800,      // 30 minutes
            guardMaxToolCalls: 400,
            guardMaxConsecutiveFailures: 8,
            guardMaxNoProgressCycles: 10,
            emitBudgetEveryStep: true,

            // Output
            outputFormat: 'text'           // 'text' | 'json' | 'markdown'
        };
    }

    function _agentConfigStorageKey(slotIndex, modelSource) {
        return 'cc_agent_cfg_' + slotIndex + '_' + (modelSource || '').replace(/[^a-zA-Z0-9_-]/g, '_').substring(0, 40);
    }

    function _loadAgentConfig(slotIndex, modelSource) {
        var key = _agentConfigStorageKey(slotIndex, modelSource);
        try {
            var raw = localStorage.getItem(key);
            if (raw) {
                var parsed = JSON.parse(raw);
                // Merge with defaults to pick up any new fields
                var cfg = _defaultAgentConfig();
                for (var k in parsed) { if (parsed.hasOwnProperty(k) && cfg.hasOwnProperty(k)) cfg[k] = parsed[k]; }
                return cfg;
            }
        } catch (e) { /* ignore */ }
        return _defaultAgentConfig();
    }

    function _saveAgentConfig(tab) {
        if (!tab || !tab.agentConfig) return;
        var key = _agentConfigStorageKey(tab.slot, tab.modelSource);
        try { localStorage.setItem(key, JSON.stringify(tab.agentConfig)); } catch (e) { /* quota */ }
    }

    function _cfgInt(value, fallback, minValue, maxValue) {
        var n = parseInt(value, 10);
        if (isNaN(n)) n = parseInt(fallback, 10);
        if (isNaN(n)) n = 0;
        if (typeof minValue === 'number' && n < minValue) n = minValue;
        if (typeof maxValue === 'number' && n > maxValue) n = maxValue;
        return n;
    }

    function _agentMaxIterations(tab) {
        var cfg = (tab && tab.agentConfig) ? tab.agentConfig : _defaultAgentConfig();
        return _cfgInt(cfg.maxIterations, 5, 1, 200);
    }

    function _agentMaxTokens(tab) {
        var cfg = (tab && tab.agentConfig) ? tab.agentConfig : _defaultAgentConfig();
        return _cfgInt(cfg.maxTokens, 512, 64, 8192);
    }

    function _syncAchatLoopControlsFromConfig(tab) {
        if (!tab || !tab.agentConfig) return;
        var maxIterEl = document.getElementById('achat-max-iter');
        var maxTokEl = document.getElementById('achat-max-tokens');
        if (maxIterEl) maxIterEl.value = String(_agentMaxIterations(tab));
        if (maxTokEl) maxTokEl.value = String(_agentMaxTokens(tab));
    }

    // Save agent config to FelixBag for cross-session persistence
    function _persistAgentConfigToBag(tab) {
        if (!tab || !tab.agentConfig) return;
        var bagKey = 'agent_config:slot_' + tab.slot;
        var content = JSON.stringify(tab.agentConfig, null, 2);
        callTool('bag_induct', { key: bagKey, content: content, item_type: 'config' }, '__internal_agent_config__');
    }

    // Load agent config from FelixBag
    async function _loadAgentConfigFromBag(tab) {
        if (!tab) return null;
        var bagKey = 'agent_config:slot_' + tab.slot;
        try {
            var result = await callToolAwaitParsed('bag_get', { key: bagKey }, '__internal_agent_config__', { tabKey: tab.key });
            if (result && result.value) {
                var parsed = JSON.parse(result.value);
                var cfg = _defaultAgentConfig();
                for (var k in parsed) { if (parsed.hasOwnProperty(k) && cfg.hasOwnProperty(k)) cfg[k] = parsed[k]; }
                tab.agentConfig = cfg;
                _saveAgentConfig(tab);  // sync to localStorage
                return cfg;
            }
        } catch (e) { /* not found or parse error */ }
        return null;
    }

    // Build the config UI panel HTML
    function _renderAgentConfigPanel(tab) {
        if (!tab || !tab.agentConfig) return '';
        var c = tab.agentConfig;
        var esc = escHtml;
        return '<div class="achat-config-panel" id="achat-agent-config">' +
            '<div class="section-head" style="margin:0 0 8px;">AGENT CONFIGURATION</div>' +

            // Identity
            '<div class="achat-cfg-group">' +
            '<label class="achat-cfg-label">Agent Name</label>' +
            '<input class="chat-input achat-cfg-input" data-cfg="agentName" value="' + esc(c.agentName) + '" placeholder="e.g. Code Analyst" />' +
            '</div>' +
            '<div class="achat-cfg-group">' +
            '<label class="achat-cfg-label">Description</label>' +
            '<input class="chat-input achat-cfg-input" data-cfg="agentDescription" value="' + esc(c.agentDescription) + '" placeholder="What this agent specializes in" />' +
            '</div>' +
            '<div class="achat-cfg-group">' +
            '<label class="achat-cfg-label">Persona</label>' +
            '<input class="chat-input achat-cfg-input" data-cfg="persona" value="' + esc(c.persona) + '" placeholder="e.g. You are a meticulous code reviewer..." />' +
            '</div>' +
            '<div class="achat-cfg-group">' +
            '<label class="achat-cfg-label">System Prompt <span style="color:var(--text-dim);font-size:8px;">(overrides default)</span></label>' +
            '<textarea class="chat-input achat-cfg-input" data-cfg="systemPrompt" rows="4" placeholder="Leave empty for default orchestration prompt">' + esc(c.systemPrompt) + '</textarea>' +
            '</div>' +

            // Generation
            '<div class="section-head" style="margin:8px 0 4px;font-size:9px;">GENERATION</div>' +
            '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;">' +
            '<div class="achat-cfg-group"><label class="achat-cfg-label">Temperature</label><input type="number" class="chat-input achat-cfg-input" data-cfg="temperature" value="' + c.temperature + '" min="0" max="2" step="0.1" /></div>' +
            '<div class="achat-cfg-group"><label class="achat-cfg-label">Top-P</label><input type="number" class="chat-input achat-cfg-input" data-cfg="topP" value="' + c.topP + '" min="0" max="1" step="0.05" /></div>' +
            '<div class="achat-cfg-group"><label class="achat-cfg-label">Rep. Penalty</label><input type="number" class="chat-input achat-cfg-input" data-cfg="repetitionPenalty" value="' + c.repetitionPenalty + '" min="1" max="2" step="0.05" /></div>' +
            '</div>' +
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:6px;">' +
            '<div class="achat-cfg-group"><label class="achat-cfg-label">Max Tokens</label><input type="number" class="chat-input achat-cfg-input" data-cfg="maxTokens" value="' + c.maxTokens + '" min="64" max="8192" step="32" /></div>' +
            '<div class="achat-cfg-group"><label class="achat-cfg-label">Max Iterations</label><input type="number" class="chat-input achat-cfg-input" data-cfg="maxIterations" value="' + c.maxIterations + '" min="1" max="200" step="1" /></div>' +
            '</div>' +

            // Context & Memory
            '<div class="section-head" style="margin:8px 0 4px;font-size:9px;">MEMORY &amp; CONTEXT</div>' +
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">' +
            '<div class="achat-cfg-group"><label class="achat-cfg-label">Context Strategy</label>' +
            '<select class="chat-input achat-cfg-input" data-cfg="contextStrategy">' +
            '<option value="full"' + (c.contextStrategy === 'full' ? ' selected' : '') + '>Full History</option>' +
            '<option value="sliding-window"' + (c.contextStrategy === 'sliding-window' ? ' selected' : '') + '>Sliding Window</option>' +
            '<option value="summarize"' + (c.contextStrategy === 'summarize' ? ' selected' : '') + '>Auto-Summarize</option>' +
            '</select></div>' +
            '<div class="achat-cfg-group"><label class="achat-cfg-label">Window Size</label><input type="number" class="chat-input achat-cfg-input" data-cfg="contextWindowSize" value="' + c.contextWindowSize + '" min="5" max="100" /></div>' +
            '</div>' +
            '<div style="display:flex;gap:12px;margin:4px 0;flex-wrap:wrap;">' +
            '<label style="font-size:9px;display:flex;gap:4px;align-items:center;"><input type="checkbox" class="achat-cfg-check" data-cfg="persistMemory"' + (c.persistMemory ? ' checked' : '') + ' /> Auto-save to FelixBag</label>' +
            '<label style="font-size:9px;display:flex;gap:4px;align-items:center;"><input type="checkbox" class="achat-cfg-check" data-cfg="emitBudgetEveryStep"' + (c.emitBudgetEveryStep ? ' checked' : '') + ' /> Emit budget telemetry each step</label>' +
            '</div>' +

            // Autonomy & Safety
            '<div class="section-head" style="margin:8px 0 4px;font-size:9px;">AUTONOMY &amp; SAFETY</div>' +
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">' +
            '<div class="achat-cfg-group"><label class="achat-cfg-label">Resource Request Mode</label>' +
            '<select class="chat-input achat-cfg-input" data-cfg="resourceApprovalMode">' +
            '<option value="manual"' + (c.resourceApprovalMode === 'manual' ? ' selected' : '') + '>Manual Approve</option>' +
            '<option value="capped"' + ((c.resourceApprovalMode || 'capped') === 'capped' ? ' selected' : '') + '>Auto-Approve (Capped)</option>' +
            '<option value="auto_all"' + (c.resourceApprovalMode === 'auto_all' ? ' selected' : '') + '>Auto-Approve ALL</option>' +
            '</select></div>' +
            '<div class="achat-cfg-group"><label class="achat-cfg-label">Max Runtime (sec)</label><input type="number" class="chat-input achat-cfg-input" data-cfg="guardMaxWallClockSec" value="' + c.guardMaxWallClockSec + '" min="60" max="86400" step="30" /></div>' +
            '</div>' +
            '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;">' +
            '<div class="achat-cfg-group"><label class="achat-cfg-label">Max Tool Calls</label><input type="number" class="chat-input achat-cfg-input" data-cfg="guardMaxToolCalls" value="' + c.guardMaxToolCalls + '" min="10" max="10000" step="10" /></div>' +
            '<div class="achat-cfg-group"><label class="achat-cfg-label">Max Consecutive Failures</label><input type="number" class="chat-input achat-cfg-input" data-cfg="guardMaxConsecutiveFailures" value="' + c.guardMaxConsecutiveFailures + '" min="1" max="100" /></div>' +
            '<div class="achat-cfg-group"><label class="achat-cfg-label">Max No-Progress Cycles</label><input type="number" class="chat-input achat-cfg-input" data-cfg="guardMaxNoProgressCycles" value="' + c.guardMaxNoProgressCycles + '" min="1" max="200" /></div>' +
            '</div>' +
            '<div style="display:flex;gap:12px;margin:4px 0;flex-wrap:wrap;">' +
            '<label style="font-size:9px;display:flex;gap:4px;align-items:center;"><input type="checkbox" class="achat-cfg-check" data-cfg="reappropriationEnabled"' + (c.reappropriationEnabled ? ' checked' : '') + ' /> Dynamic Reappropriation</label>' +
            '<label style="font-size:9px;display:flex;gap:4px;align-items:center;"><input type="checkbox" class="achat-cfg-check" data-cfg="haltOnError"' + (c.haltOnError ? ' checked' : '') + ' /> Halt on Error</label>' +
            '<label style="font-size:9px;display:flex;gap:4px;align-items:center;"><input type="checkbox" class="achat-cfg-check" data-cfg="requireConfirmation"' + (c.requireConfirmation ? ' checked' : '') + ' /> Require confirmation for tool execution</label>' +
            '</div>' +
            '<div class="hint" style="font-size:9px;color:var(--text-dim);margin:0 0 2px;">Auto-Approve ALL still enforces non-disableable hard brakes (runtime, calls, failures, no-progress, kill switch).</div>' +

            // Output
            '<div style="display:flex;gap:6px;margin:4px 0;align-items:center;">' +
            '<label class="achat-cfg-label" style="margin:0;">Output Format</label>' +
            '<select class="chat-input achat-cfg-input" data-cfg="outputFormat" style="width:auto;">' +
            '<option value="text"' + (c.outputFormat === 'text' ? ' selected' : '') + '>Text</option>' +
            '<option value="json"' + (c.outputFormat === 'json' ? ' selected' : '') + '>JSON</option>' +
            '<option value="markdown"' + (c.outputFormat === 'markdown' ? ' selected' : '') + '>Markdown</option>' +
            '</select></div>' +

            // Actions row 1: persistence
            '<div style="display:flex;gap:6px;margin:8px 0 4px;flex-wrap:wrap;">' +
            '<button class="btn-dim" onclick="_saveAgentConfigFromUI()">💾 SAVE CONFIG</button>' +
            '<button class="btn-dim" onclick="_persistAgentConfigToBag(_getActiveAchatTab())">☁ SAVE TO BAG</button>' +
            '<button class="btn-dim" onclick="_loadAgentConfigFromBagUI()">⬇ LOAD FROM BAG</button>' +
            '</div>' +
            // Actions row 2: reset + view
            '<div style="display:flex;gap:6px;margin:0 0 4px;flex-wrap:wrap;">' +
            '<button class="btn-dim" onclick="_resetAgentPrompt()" title="Clear system prompt, persona, name, description back to empty (uses auto-generated default)">🔄 RESET PROMPT</button>' +
            '<button class="btn-dim" onclick="_resetAgentGeneration()" title="Reset temperature, tokens, iterations, top-p, repetition penalty to defaults">🔄 RESET GENERATION</button>' +
            '<button class="btn-dim" onclick="_resetAgentConfig()" title="Reset ALL config fields to factory defaults">⚠ RESET ALL</button>' +
            '<button class="btn-dim" onclick="_viewDefaultPrompt()" title="Preview the auto-generated system prompt that is used when the system prompt field is empty">👁 VIEW DEFAULT PROMPT</button>' +
            '</div>' +
            '</div>';
    }
    window._persistAgentConfigToBag = _persistAgentConfigToBag;

    function _saveAgentConfigFromUI() {
        var tab = _getActiveAchatTab();
        if (!tab || !tab.agentConfig) return;
        var panel = document.getElementById('achat-agent-config');
        if (!panel) return;
        // Read all inputs
        var inputs = panel.querySelectorAll('.achat-cfg-input');
        for (var i = 0; i < inputs.length; i++) {
            var field = inputs[i].getAttribute('data-cfg');
            if (!field) continue;
            var val = inputs[i].tagName === 'TEXTAREA' ? inputs[i].value : inputs[i].value;
            if (inputs[i].type === 'number') val = parseFloat(val) || 0;
            tab.agentConfig[field] = val;
        }
        // Checkboxes
        var checks = panel.querySelectorAll('.achat-cfg-check');
        for (var j = 0; j < checks.length; j++) {
            var cf = checks[j].getAttribute('data-cfg');
            if (cf) tab.agentConfig[cf] = checks[j].checked;
        }
        _saveAgentConfig(tab);
        _syncAchatLoopControlsFromConfig(tab);
        mpToast('Agent config saved', 'ok', 2000);
    }
    window._saveAgentConfigFromUI = _saveAgentConfigFromUI;

    async function _loadAgentConfigFromBagUI() {
        var tab = _getActiveAchatTab();
        if (!tab) return;
        var result = await _loadAgentConfigFromBag(tab);
        if (result) {
            var configEl = document.getElementById('achat-agent-config');
            if (configEl) configEl.outerHTML = _renderAgentConfigPanel(tab);
            _syncAchatLoopControlsFromConfig(tab);
            mpToast('Config loaded from FelixBag', 'ok', 2000);
        } else {
            mpToast('No saved config found in FelixBag for slot ' + tab.slot, 'warn', 2000);
        }
    }
    window._loadAgentConfigFromBagUI = _loadAgentConfigFromBagUI;

    function _resetAgentConfig() {
        var tab = _getActiveAchatTab();
        if (!tab) return;
        tab.agentConfig = _defaultAgentConfig();
        _saveAgentConfig(tab);
        _syncAchatLoopControlsFromConfig(tab);
        var configEl = document.getElementById('achat-agent-config');
        if (configEl) configEl.outerHTML = _renderAgentConfigPanel(tab);
        mpToast('All config reset to defaults', 'ok', 2000);
    }
    window._resetAgentConfig = _resetAgentConfig;

    function _resetAgentPrompt() {
        var tab = _getActiveAchatTab();
        if (!tab || !tab.agentConfig) return;
        tab.agentConfig.agentName = '';
        tab.agentConfig.agentDescription = '';
        tab.agentConfig.persona = '';
        tab.agentConfig.systemPrompt = '';
        _saveAgentConfig(tab);
        var configEl = document.getElementById('achat-agent-config');
        if (configEl) configEl.outerHTML = _renderAgentConfigPanel(tab);
        mpToast('Prompt fields reset — will use auto-generated default', 'ok', 2000);
    }
    window._resetAgentPrompt = _resetAgentPrompt;

    function _resetAgentGeneration() {
        var tab = _getActiveAchatTab();
        if (!tab || !tab.agentConfig) return;
        var d = _defaultAgentConfig();
        tab.agentConfig.temperature = d.temperature;
        tab.agentConfig.maxTokens = d.maxTokens;
        tab.agentConfig.maxIterations = d.maxIterations;
        tab.agentConfig.topP = d.topP;
        tab.agentConfig.repetitionPenalty = d.repetitionPenalty;
        _saveAgentConfig(tab);
        _syncAchatLoopControlsFromConfig(tab);
        var configEl = document.getElementById('achat-agent-config');
        if (configEl) configEl.outerHTML = _renderAgentConfigPanel(tab);
        mpToast('Generation params reset to defaults (temp=0.7, tokens=512, iter=5)', 'ok', 2000);
    }
    window._resetAgentGeneration = _resetAgentGeneration;

    function _buildLoopSystemPrompt(tab, runtimeBudget) {
        if (!tab) return '';
        var cfg = tab.agentConfig || _defaultAgentConfig();

        // If the user set an explicit system prompt, use it directly.
        if (cfg.systemPrompt && String(cfg.systemPrompt).trim()) {
            return String(cfg.systemPrompt).trim();
        }

        // Build the auto-generated orchestration prompt.
        var granted = Array.isArray(tab.grantedTools) ? tab.grantedTools : [];
        var blocked = Array.isArray(tab.blockedTools) ? tab.blockedTools : [];
        var slotName = tab.slotName || ('Slot ' + tab.slot);
        var persona = String(cfg.persona || '').trim();
        var agentName = String(cfg.agentName || '').trim();
        var agentDesc = String(cfg.agentDescription || '').trim();
        var maxIter = _cfgInt((runtimeBudget && runtimeBudget.maxIterations) || cfg.maxIterations, 5, 1, 200);
        var reapEnabled = cfg.reappropriationEnabled !== false;
        var contextStrategy = String(cfg.contextStrategy || 'sliding-window');
        var contextWindowSize = _cfgInt(cfg.contextWindowSize, 20, 5, 200);

        var lines = [];

        // Identity
        lines.push('You are ' + (agentName || slotName) + ', an autonomous AI agent operating inside an Ouroboros capsule council.' +
            (agentDesc ? ' ' + agentDesc : ''));
        if (persona) lines.push('\nPersona: ' + persona);

        // Core protocol
        lines.push('\n## TOOL CALLING PROTOCOL');
        lines.push('You have access to tools via the Ouroboros MCP interface. Each turn, you MUST respond with EXACTLY ONE valid JSON object. No markdown, no commentary outside the JSON.');
        lines.push('\nTo call a tool, respond with:');
        lines.push('{"tool": "<tool_name>", "args": {<argument_key>: <value>, ...}}');
        lines.push('\nTo provide your final answer when the task is complete:');
        lines.push('{"final_answer": "<your complete response>"}');

        // Granted tools
        if (granted.length > 0) {
            lines.push('\n## GRANTED TOOLS (' + granted.length + ')');
            lines.push('You may ONLY call these tools: ' + granted.join(', '));
            lines.push('Any tool not in this list will be rejected.');
        }
        if (blocked.length > 0) {
            lines.push('\n## BLOCKED TOOLS (safety)');
            lines.push('These tools are blocked and must NOT be called: ' + blocked.join(', '));
        }

        lines.push('\n## CONTEXT POLICY');
        if (contextStrategy === 'full') {
            lines.push('Context mode: Full history (no trimming).');
        } else if (contextStrategy === 'summarize') {
            lines.push('Context mode: Tiered memory (rolling summary + recent window).');
            lines.push('Preserve key facts, decisions, and unresolved issues while compressing older turns.');
        } else {
            lines.push('Context mode: Sliding window.');
        }
        lines.push('Active recent context window: last ' + contextWindowSize + ' messages plus system instructions.');

        // Sequential execution — strictly enforced
        lines.push('\n## EXECUTION RULES (STRICT SEQUENTIAL — NO PARALLEL)');
        lines.push('1. Call exactly ONE tool per turn. Never batch, group, or parallelize multiple tool calls in a single response.');
        lines.push('2. Your response must contain ONLY ONE JSON object — either a single tool call OR a final_answer. Never both. Never multiple.');
        lines.push('3. Wait for the tool result before deciding your next action. Do not assume, predict, or pre-plan tool results.');
        lines.push('4. Use real tool outputs only. Never fabricate, hallucinate, or simulate tool results.');
        lines.push('5. Do not provide final_answer until you have gathered sufficient evidence from tools.');
        lines.push('6. If a tool returns an error, adapt your approach — try a different tool or different arguments.');
        lines.push('7. NEVER output multiple JSON objects or an array of tool calls. One tool, one turn, every time.');

        var selfSlot = parseInt(tab.slot, 10);
        var hasInterSlotTools = granted.indexOf('invoke_slot') >= 0 || granted.indexOf('call') >= 0 || granted.indexOf('agent_chat') >= 0 || granted.indexOf('chat') >= 0 || granted.indexOf('agent_delegate') >= 0;
        if (hasInterSlotTools) {
            lines.push('\n## INTER-SLOT SAFETY (ANTI-RECURSION)');
            lines.push('Never target your own slot (' + (isNaN(selfSlot) ? 'current slot' : String(selfSlot)) + ') when using invoke_slot/call/chat/agent_chat/agent_delegate.');
            lines.push('Delegate only to OTHER slots to prevent recursive paradox loops.');
            lines.push('Prefer agent_delegate for structured cross-slot autonomous sub-tasks.');
        }

        // Reappropriation protocol
        if (reapEnabled) {
            lines.push('\n## DYNAMIC REAPPROPRIATION');
            lines.push('You have ' + maxIter + ' iterations allocated. If you need more iterations to complete your task, you may request additional allotment by responding with:');
            lines.push('{"final_answer": "REAPPROPRIATE:<number>:<reason>"}');
            lines.push('Example: {"final_answer": "REAPPROPRIATE:10:I discovered 5 subsystems that each need diagnostic checks"}');
            lines.push('This request will be evaluated and may be auto-approved. Use this when:');
            lines.push('- You have a multi-step plan that requires more tools than allocated');
            lines.push('- You discovered new subtasks during exploration');
            lines.push('- You need to retry failed operations');
            lines.push('Do NOT be shy about requesting more iterations. It is better to request more and do thorough work than to give a shallow final_answer.');
        }

        // Output format
        var outputFmt = String(cfg.outputFormat || 'text').toLowerCase();
        if (outputFmt === 'json') {
            lines.push('\n## OUTPUT FORMAT');
            lines.push('When providing final_answer, format it as structured JSON.');
        } else if (outputFmt === 'markdown') {
            lines.push('\n## OUTPUT FORMAT');
            lines.push('When providing final_answer, format it as well-structured Markdown with headers, lists, and code blocks as appropriate.');
        }

        // Systematic methodology
        lines.push('\n## METHODOLOGY');
        lines.push('Apply a systematic, scientific approach to every task:');
        lines.push('1. OBSERVE: Gather data using available tools before drawing conclusions.');
        lines.push('2. HYPOTHESIZE: Form specific expectations based on observations.');
        lines.push('3. TEST: Use tools to validate or refute your hypotheses.');
        lines.push('4. RECORD: Note each finding — successful or failed — for your final report.');
        lines.push('5. ITERATE: If a tool reveals something unexpected, investigate further. Do NOT skip anomalies.');
        lines.push('Use tools as needed to accomplish the mission. Do NOT call every granted tool — only call tools relevant to the task.');

        lines.push('\n## CONTINUATION');
        lines.push('You will receive results after each tool call. Use those results to inform your next action.');
        lines.push('Do NOT rush to final_answer. Your operator values thoroughness over speed.');
        lines.push('If you run low on iterations, request more via the REAPPROPRIATE protocol above.');
        lines.push('You are expected to be self-directed: plan your own investigation, call tools in logical order, and produce a comprehensive final report.');

        // FelixBag doc/file workflow guidance
        var hasDocTools = granted.indexOf('bag_read_doc') >= 0 || granted.indexOf('bag_checkpoint') >= 0 || granted.indexOf('bag_versions') >= 0 || granted.indexOf('bag_diff') >= 0 || granted.indexOf('file_read') >= 0 || granted.indexOf('file_edit') >= 0 || granted.indexOf('file_checkpoint') >= 0 || granted.indexOf('file_diff') >= 0;
        if (hasDocTools) {
            lines.push('\n## FELIXBAG DOCUMENT WORKFLOW (IMPORTANT)');
            lines.push('For document editing/versioning tasks, use this exact sequence:');
            lines.push('1) READ current doc with bag_read_doc (or bag_get if needed).');
            lines.push('2) CREATE checkpoint with bag_checkpoint before any write.');
            lines.push('3) WRITE updates with bag_induct(item_type="document", same key).');
            lines.push('4) VERIFY with bag_read_doc and bag_diff against checkpoint.');
            lines.push('5) If needed, restore with bag_restore using checkpoint_key.');
            lines.push('Avoid bag_put for document editing when bag_induct is available.');
            lines.push('For deletes, prefer bag_forget with explicit pattern for deterministic cleanup.');
            lines.push('If file_* tools are granted, prefer file_read/file_checkpoint/file_edit/file_diff/file_restore for file-style workflows.');
            lines.push('For bag_diff/file_diff latest comparisons, use to_checkpoint="current" (or omit it). Do not send empty to_checkpoint.');
            lines.push('For file_write and file_list, keep content/file_type as strings (avoid null).');
            lines.push('Never use file_* to access host filesystem paths — they are FelixBag workspace paths only.');
        }

        return lines.join('\n');
    }

    function _viewDefaultPrompt() {
        var tab = _getActiveAchatTab();
        if (!tab) return;
        var sys = _buildLoopSystemPrompt(tab);
        var pre = document.createElement('div');
        pre.style.cssText = 'position:fixed;top:10%;left:10%;right:10%;bottom:10%;z-index:9999;background:var(--bg,#111);border:2px solid var(--accent,#0f8);border-radius:8px;padding:16px;overflow:auto;font-family:var(--mono,monospace);font-size:11px;white-space:pre-wrap;color:var(--text,#eee);';
        pre.innerHTML = '<div style="display:flex;justify-content:space-between;margin-bottom:12px;">' +
            '<b style="color:var(--accent);">DEFAULT SYSTEM PROMPT (auto-generated)</b>' +
            '<button onclick="this.parentElement.parentElement.remove()" style="cursor:pointer;background:none;border:1px solid var(--border,#333);color:var(--text,#eee);padding:2px 8px;border-radius:4px;">✕ CLOSE</button>' +
            '</div>' +
            '<div style="padding:8px;background:rgba(0,255,136,0.05);border:1px solid var(--border,#333);border-radius:4px;line-height:1.6;">' + escHtml(sys) + '</div>' +
            '<div style="margin-top:12px;font-size:9px;color:var(--text-dim,#888);">This prompt is used when the System Prompt field is empty. ' +
            'To customize, paste this into the System Prompt field and modify it.</div>';
        document.body.appendChild(pre);
    }
    window._viewDefaultPrompt = _viewDefaultPrompt;

    function _ensureAchatTab(slot) {
        var slotIndex = parseInt(slot, 10);
        if (!(slotIndex >= 0)) return null;
        var key = 'slot:' + slotIndex;
        var existing = _achatTabs[key];
        var slotInfo = _getSlotData ? _getSlotData(slotIndex) : null;
        var modelSource = slotInfo ? (slotInfo.model_source || slotInfo.model_id || slotInfo.name || ('slot_' + slotIndex)) : ('slot_' + slotIndex);
        var modelType = String((slotInfo && (slotInfo.model_type || slotInfo.type)) || 'unknown').toUpperCase();
        var isPlugged = !!(slotInfo && _getSlotVisualState(slotInfo) === 'plugged');
        var canChat = _slotSupportsAgentChat(slotInfo || {});

        if (!existing) {
            var policyKey = _policyKeyForSlot(slotIndex, modelSource);
            var savedTools = _sanitizeGrantedTools((_achatToolPolicies && _achatToolPolicies[policyKey]) || []);
            var tab = {
                key: key,
                slot: slotIndex,
                modelSource: modelSource,
                modelType: modelType,
                isPlugged: isPlugged,
                canChat: canChat,
                messages: [],
                selectedTool: canChat ? 'invoke_slot' : 'invoke_slot',
                runMode: canChat ? 'loop' : 'direct',
                toolArgs: {},
                sessionId: '',
                loopMessages: [],
                grantedTools: savedTools.length ? savedTools : _defaultGrantedToolsForTab({ canChat: canChat }),
                // ── AGENT CONFIG (user-editable per-slot) ──
                agentConfig: _loadAgentConfig(slotIndex, modelSource)
            };
            _achatTabs[key] = tab;
            return tab;
        }

        // Detect model swap — if a different model is now in this slot, reset state
        var modelChanged = existing.modelSource !== modelSource;
        existing.modelSource = modelSource;
        existing.modelType = modelType;
        existing.isPlugged = isPlugged;
        existing.canChat = canChat;
        if (modelChanged) {
            existing.messages = [];
            existing.loopMessages = [];
            existing.sessionId = '';
            existing.toolArgs = {};
            existing.agentConfig = _loadAgentConfig(slotIndex, modelSource);
            var newPolicyKey = _policyKeyForSlot(slotIndex, modelSource);
            var newSavedTools = _sanitizeGrantedTools((_achatToolPolicies && _achatToolPolicies[newPolicyKey]) || []);
            existing.grantedTools = newSavedTools.length ? newSavedTools : _defaultGrantedToolsForTab({ canChat: canChat });
        }
        if (!existing.canChat && existing.selectedTool === 'agent_chat') {
            existing.selectedTool = 'invoke_slot';
        }
        if (!existing.canChat && existing.runMode === 'loop') {
            existing.runMode = 'direct';
        }
        if (!existing.runMode) existing.runMode = existing.canChat ? 'loop' : 'direct';
        if (!Array.isArray(existing.loopMessages)) existing.loopMessages = [];
        if (!Array.isArray(existing.grantedTools) || !existing.grantedTools.length) {
            existing.grantedTools = _defaultGrantedToolsForTab(existing);
        }
        return existing;
    }

    function _getActiveAchatTab() {
        return _achatTabs[_achatActiveTabKey] || null;
    }

    function _renderAchatTabs() {
        var wrap = document.getElementById('achat-tabs');
        if (!wrap) return;
        var keys = Object.keys(_achatTabs).sort(function (a, b) {
            var sa = _achatTabs[a] ? _achatTabs[a].slot : 0;
            var sb = _achatTabs[b] ? _achatTabs[b].slot : 0;
            return sa - sb;
        });
        if (!keys.length) {
            wrap.innerHTML = '<div class="achat-tab-empty">Open a slot to start a model console tab.</div>';
            return;
        }
        var html = '';
        for (var i = 0; i < keys.length; i++) {
            var k = keys[i];
            var t = _achatTabs[k];
            if (!t) continue;
            var active = k === _achatActiveTabKey;
            var stateCls = t.isPlugged ? 'ready' : 'empty';
            html += '<button class="achat-tab ' + (active ? 'active' : '') + ' ' + stateCls + '" data-achat-tab="' + escHtml(k) + '">' +
                '<span class="tab-slot">S' + (t.slot + 1) + '</span>' +
                '<span class="tab-name">' + escHtml(String(t.modelSource || ('slot_' + t.slot))) + '</span>' +
                '</button>';
        }
        wrap.innerHTML = html;
        if (!wrap.dataset.bound) {
            wrap.addEventListener('click', function (ev) {
                var btn = ev.target.closest('[data-achat-tab]');
                if (!btn) return;
                var key = btn.getAttribute('data-achat-tab') || '';
                if (key) _activateAchatTab(key, true);
            });
            wrap.dataset.bound = '1';
        }
    }

    function _renderAchatMessages(tab) {
        var container = document.getElementById('achat-messages');
        if (!container) return;
        container.innerHTML = '';
        if (!tab || !tab.messages || !tab.messages.length) {
            container.innerHTML =
                '<div class="achat-empty">Select a tool and configure args.<br/>' +
                'Use <b>agent_chat</b> for autonomous multi-tool loops, or any MCP tool directly for one-shot operations.</div>';
            return;
        }

        for (var i = 0; i < tab.messages.length; i++) {
            var m = tab.messages[i] || {};
            if (m.role === 'tool-trace') {
                var calls = Array.isArray(m.toolCalls) ? m.toolCalls : [];
                // Skip completely empty tool traces (no calls, no text)
                if (calls.length === 0 && !m.content) continue;
                // If it's just a text status line (external bridge), render as status
                if (calls.length === 0 && m.content) {
                    var sDiv = document.createElement('div');
                    sDiv.className = 'achat-msg trace-status';
                    sDiv.innerHTML = escHtml(String(m.content)) + (m.ts ? '<span class="achat-ts">' + new Date(m.ts).toLocaleTimeString() + '</span>' : '');
                    container.appendChild(sDiv);
                    continue;
                }
                // Render each tool call as an individual card
                for (var ci = 0; ci < calls.length; ci++) {
                    var tc = calls[ci];
                    var tDiv = document.createElement('div');
                    tDiv.className = 'achat-msg tool-call-card';
                    var name = tc.tool || tc.name || '?';
                    var err = !!tc.error;
                    var iterLabel = tc.iteration !== undefined ? 'Iteration ' + tc.iteration : '';
                    var statusBadge = '<span class="tc-badge ' + (err ? 'tc-badge-err' : 'tc-badge-ok') + '">' + (err ? 'ERROR' : 'OK') + '</span>';
                    var callerSlot = parseInt(tc.caller_slot, 10);
                    var targetSlot = parseInt(tc.target_slot, 10);
                    var flowLabel = '';
                    if (!isNaN(callerSlot) && !isNaN(targetSlot) && callerSlot >= 0 && targetSlot >= 0 && callerSlot !== targetSlot) {
                        flowLabel = 'S' + (callerSlot + 1) + '→S' + (targetSlot + 1);
                    } else if (!isNaN(callerSlot) && callerSlot >= 0) {
                        flowLabel = 'S' + (callerSlot + 1);
                    }
                    var traceShort = tc.trace_id ? String(tc.trace_id).split(':').slice(-1)[0] : '';
                    if (traceShort && traceShort.length > 8) traceShort = traceShort.substring(0, 8);
                    var argsStr = tc.args ? JSON.stringify(tc.args, null, 2) : '{}';
                    var resultStr = '';
                    if (tc.error) {
                        resultStr = String(tc.error);
                    } else if (tc.result) {
                        resultStr = typeof tc.result === 'string' ? tc.result : JSON.stringify(tc.result, null, 2);
                    }
                    if (resultStr.length > 800) resultStr = resultStr.substring(0, 800) + '\n…[truncated]';
                    var html = '<div class="tc-header">' +
                        '<span class="tc-icon">⚙</span> ' +
                        '<span class="tc-name">' + escHtml(name) + '</span> ' +
                        statusBadge +
                        (iterLabel ? ' <span class="tc-iter">' + escHtml(iterLabel) + '</span>' : '') +
                        (flowLabel ? ' <span class="tc-iter">' + escHtml(flowLabel) + '</span>' : '') +
                        (traceShort ? ' <span class="tc-iter">' + escHtml('#' + traceShort) + '</span>' : '') +
                        '</div>';
                    if (argsStr !== '{}') {
                        html += '<details class="tc-details"><summary>Arguments</summary><pre class="tc-pre">' + _escForDisplay(argsStr) + '</pre></details>';
                    }
                    if (resultStr) {
                        html += '<details class="tc-details" open><summary>Result</summary><pre class="tc-pre">' + _escForDisplay(resultStr) + '</pre></details>';
                    }
                    tDiv.innerHTML = html;
                    container.appendChild(tDiv);
                }
                continue;
            }
            var tsStr = m.ts ? new Date(m.ts).toLocaleTimeString() : '';
            if (m.role === 'cache-hint') {
                var cDiv = document.createElement('div');
                cDiv.className = 'achat-msg system-info';
                var cid = String(m.cacheId || m.content || '').trim();
                var csz = parseInt(m.cacheSize, 10) || 0;
                var routeAs = String(m.routeAs || '__agent_chat__');
                var sizeInfo = csz > 0 ? (' · ' + csz + ' bytes') : '';
                var btnHtml = '<button class="btn btn-dim" style="margin-left:8px;padding:2px 8px;font-size:9px;" ' +
                    'onclick=\'_achatLoadCached(' + JSON.stringify(cid) + ',' + JSON.stringify(tab.key || '') + ',' + JSON.stringify(routeAs) + ')\'>Load cached result</button>';
                cDiv.innerHTML =
                    'Large response cached as <code>' + escHtml(cid) + '</code>' + escHtml(sizeInfo) + btnHtml +
                    (tsStr ? '<span class="achat-ts">' + tsStr + '</span>' : '');
                container.appendChild(cDiv);
                continue;
            }

            var cachedInContent = _extractAchatCachedDescriptor(m.content);
            if (cachedInContent && cachedInContent.cacheId) {
                var cDiv2 = document.createElement('div');
                cDiv2.className = 'achat-msg system-info';
                var cid2 = String(cachedInContent.cacheId || '').trim();
                var csz2 = parseInt(cachedInContent.cacheSize, 10) || 0;
                var routeAs2 = String(cachedInContent.routeAs || '__agent_chat__');
                var sizeInfo2 = csz2 > 0 ? (' · ' + csz2 + ' bytes') : '';
                var btnHtml2 = '<button class="btn btn-dim" style="margin-left:8px;padding:2px 8px;font-size:9px;" ' +
                    'onclick=\'_achatLoadCached(' + JSON.stringify(cid2) + ',' + JSON.stringify(tab.key || '') + ',' + JSON.stringify(routeAs2) + ')\'>Load cached result</button>';
                cDiv2.innerHTML =
                    'Large response cached as <code>' + escHtml(cid2) + '</code>' + escHtml(sizeInfo2) + btnHtml2 +
                    (tsStr ? '<span class="achat-ts">' + tsStr + '</span>' : '');
                container.appendChild(cDiv2);
                continue;
            }

            var div = document.createElement('div');
            div.className = 'achat-msg ' + (m.role || 'assistant');
            div.innerHTML = _escForDisplay(String(m.content || '')) + (tsStr ? '<span class="achat-ts">' + tsStr + '</span>' : '');
            container.appendChild(div);
        }
        container.scrollTop = container.scrollHeight;
    }

    function _appendAchatMsg(role, content, ts, tabRef) {
        var tab = tabRef || _getActiveAchatTab();
        if (!tab) return;
        if (!Array.isArray(tab.messages)) tab.messages = [];
        tab.messages.push({ role: role, content: String(content || ''), ts: ts || Date.now() });
        if (tab.key === _achatActiveTabKey) _renderAchatMessages(tab);
    }

    function _appendAchatToolTrace(toolCalls, tabRef) {
        var tab = tabRef || _getActiveAchatTab();
        if (!tab) return;
        if (!Array.isArray(tab.messages)) tab.messages = [];
        tab.messages.push({ role: 'tool-trace', toolCalls: Array.isArray(toolCalls) ? toolCalls : [], ts: Date.now() });
        if (tab.key === _achatActiveTabKey) _renderAchatMessages(tab);
    }

    function _extractAchatCachedDescriptor(value) {
        var v = value;
        if (v == null) return null;
        if (typeof v === 'string') {
            var s = String(v).trim();
            if (!s) return null;
            try { v = JSON.parse(s); } catch (e) { return null; }
        }
        if (!v || typeof v !== 'object') return null;
        if (!v._cached) return null;
        return {
            cacheId: String(v._cached || '').trim(),
            cacheSize: parseInt(v._size, 10) || 0,
            routeAs: String(v._route_as || '__agent_chat__')
        };
    }

    function _appendAchatCacheHint(cacheId, cacheSize, tabRef, routeAs) {
        var tab = tabRef || _getActiveAchatTab();
        var cid = String(cacheId || '').trim();
        if (!tab || !cid) return;
        if (!Array.isArray(tab.messages)) tab.messages = [];
        var last = tab.messages.length ? tab.messages[tab.messages.length - 1] : null;
        if (last && last.role === 'cache-hint' && String(last.cacheId || '') === cid) return;
        tab.messages.push({
            role: 'cache-hint',
            cacheId: cid,
            cacheSize: parseInt(cacheSize, 10) || 0,
            routeAs: String(routeAs || '__agent_chat__'),
            ts: Date.now()
        });
        if (tab.key === _achatActiveTabKey) _renderAchatMessages(tab);
    }

    function _achatLoadCached(cacheId, tabKey, routeAs) {
        var cid = String(cacheId || '').trim();
        if (!cid) return;
        var tab = (tabKey && _achatTabs[tabKey]) ? _achatTabs[tabKey] : _getActiveAchatTab();
        if (tab) _appendAchatMsg('system-info', 'Loading cached result ' + cid + '…', Date.now(), tab);
        var meta = {};
        if (tab && tab.key) meta.tabKey = tab.key;
        callTool('get_cached', { cache_id: cid }, routeAs || '__agent_chat__', meta);
    }
    window._achatLoadCached = _achatLoadCached;

    // Log a single agent-inner tool call through the real activity pipeline
    // so it appears in Activity tab, slot drill-in, and chat timeline in real-time.
    function _logAchatSingleActivity(tc, slotIndex) {
        if (!tc || !tc.tool) return;
        var entry = {
            timestamp: tc.ts || Date.now(),
            tool: tc.tool || 'agent_tool',
            category: 'agent',
            args: Object.assign({}, tc.args || {}),
            result: tc.result || null,
            error: tc.error ? String(tc.error) : null,
            durationMs: tc.durationMs || 0,
            source: 'agent-inner'
        };
        if (slotIndex >= 0) entry.args.slot = slotIndex;
        // Use the full addActivityEntry pipeline so it flows to
        // Activity feed, slot drill-in, and external bridge.
        addActivityEntry(entry);
    }

    // Batch compat — log multiple at once (used by tool-trace after-the-fact)
    function _logAchatSyntheticActivity(toolCalls, slotIndex) {
        if (!Array.isArray(toolCalls) || !toolCalls.length) return;
        for (var i = 0; i < toolCalls.length; i++) {
            _logAchatSingleActivity(toolCalls[i], slotIndex);
        }
    }

    function _renderAchatToolSelect(tab) {
        var sel = document.getElementById('achat-run-tool');
        if (!sel || !tab) return;
        var filter = String((document.getElementById('achat-tool-filter') || {}).value || '').trim().toLowerCase();
        var all = _allToolNames();

        var options = [];
        if (tab.canChat && tab.isPlugged) options.push('agent_chat');
        options.push('invoke_slot');
        for (var i = 0; i < all.length; i++) {
            if (all[i] === 'agent_chat' || all[i] === 'invoke_slot') continue;
            options.push(all[i]);
        }
        var seen = {};
        var filtered = [];
        for (var j = 0; j < options.length; j++) {
            var name = options[j];
            if (seen[name]) continue;
            seen[name] = true;
            if (filter && name.toLowerCase().indexOf(filter) < 0) continue;
            filtered.push(name);
        }

        sel.innerHTML = filtered.map(function (n) {
            return '<option value="' + escHtml(n) + '">' + escHtml(n) + '</option>';
        }).join('');

        if (filtered.indexOf(tab.selectedTool) >= 0) {
            sel.value = tab.selectedTool;
        } else if (filtered.length > 0) {
            tab.selectedTool = filtered[0];
            sel.value = filtered[0];
        }
    }

    function _renderAchatRunMode(tab) {
        var modeEl = document.getElementById('achat-run-mode');
        var toolSel = document.getElementById('achat-run-tool');
        var toolFilter = document.getElementById('achat-tool-filter');
        var maxIter = document.getElementById('achat-max-iter');
        if (!modeEl || !tab) return;

        if (!tab.canChat && tab.runMode === 'loop') tab.runMode = 'direct';
        if (!tab.runMode) tab.runMode = tab.canChat ? 'loop' : 'direct';
        modeEl.value = tab.runMode;

        var loopMode = tab.runMode === 'loop';
        if (toolSel) toolSel.disabled = loopMode;
        if (toolFilter) toolFilter.disabled = loopMode;
        if (maxIter) maxIter.disabled = !loopMode;
    }

    function _setFieldValue(el, pType, value) {
        if (!el) return;
        if (pType === 'boolean') {
            el.checked = !!value;
            return;
        }
        if (value === undefined || value === null) {
            el.value = '';
            return;
        }
        if (pType === 'object' || pType === 'array') {
            try { el.value = typeof value === 'string' ? value : JSON.stringify(value, null, 2); }
            catch (e) { el.value = String(value); }
            return;
        }
        el.value = String(value);
    }

    function _renderAchatToolConfig(tab) {
        var noteEl = document.getElementById('achat-config-note');
        var fieldsEl = document.getElementById('achat-config-fields');
        var panel = document.getElementById('achat-tool-config');
        if (!fieldsEl || !noteEl || !panel || !tab) return;

        panel.classList.toggle('open', !!_achatToolConfigOpen);
        if (!_achatToolConfigOpen) return;

        var toolName = tab.selectedTool || 'invoke_slot';
        if (tab.runMode === 'loop') {
            noteEl.innerHTML =
                'Deterministic loop mode runs <b>invoke_slot</b> iteratively and executes only your granted tool policy (<b>' +
                (tab.grantedTools ? tab.grantedTools.length : 0) + '</b> tools). While running, press Send with new text to queue a <b>LIVE UPDATE</b>.';
            fieldsEl.innerHTML = '';
            return;
        }
        var schema = _getAchatToolSchema(toolName);
        var props = (schema && schema.properties) ? schema.properties : {};
        var required = (schema && schema.required) ? schema.required : [];
        var pNames = Object.keys(props || {});
        var cache = tab.toolArgs[toolName] || {};

        if (toolName === 'agent_chat') {
            noteEl.innerHTML =
                'Autonomous mode. The model can call only <b>' + (tab.grantedTools ? tab.grantedTools.length : 0) +
                '</b> granted tools. Use <b>TOOL ACCESS</b> to adjust policy for this model.';
            fieldsEl.innerHTML = '';
            return;
        }

        if (!schema || !pNames.length) {
            noteEl.textContent = 'No input schema available for this tool. You can still run with defaults.';
            fieldsEl.innerHTML = '';
            return;
        }

        noteEl.textContent = 'Configure arguments for ' + toolName + '. Required fields are marked.';
        var html = '';
        for (var i = 0; i < pNames.length; i++) {
            var name = pNames[i];
            var def = props[name] || {};
            var pType = def.type || (Array.isArray(def.enum) ? 'string' : 'string');
            var isReq = required.indexOf(name) >= 0;
            var current = cache[name];
            if (current === undefined && def.default !== undefined) current = def.default;

            html += '<div class="achat-field-row">';
            html += '<label>' + escHtml(name) + (isReq ? ' <span class="req">*</span>' : '') +
                '<span class="type">' + escHtml(pType) + '</span></label>';

            if (Array.isArray(def.enum)) {
                html += '<select data-achat-field="' + escHtml(name) + '" data-type="string">';
                html += '<option value=""></option>';
                for (var e = 0; e < def.enum.length; e++) {
                    var opt = def.enum[e];
                    var sel = String(current) === String(opt) ? ' selected' : '';
                    html += '<option value="' + escHtml(String(opt)) + '"' + sel + '>' + escHtml(String(opt)) + '</option>';
                }
                html += '</select>';
            } else if (pType === 'boolean') {
                html += '<input type="checkbox" data-achat-field="' + escHtml(name) + '" data-type="boolean"' + (current ? ' checked' : '') + ' />';
            } else if (pType === 'number' || pType === 'integer') {
                var step = pType === 'integer' ? '1' : 'any';
                html += '<input type="number" step="' + step + '" data-achat-field="' + escHtml(name) + '" data-type="' + escHtml(pType) + '" />';
            } else if (pType === 'object' || pType === 'array') {
                html += '<textarea data-achat-field="' + escHtml(name) + '" data-type="' + escHtml(pType) + '" placeholder="JSON value"></textarea>';
            } else {
                html += '<input type="text" data-achat-field="' + escHtml(name) + '" data-type="string" />';
            }

            if (def.description) {
                html += '<div class="hint">' + escHtml(def.description) + '</div>';
            }
            if (def.default !== undefined) {
                html += '<div class="hint">Default: <code>' + escHtml(JSON.stringify(def.default)) + '</code></div>';
            }
            html += '</div>';
        }
        fieldsEl.innerHTML = html;

        var rows = fieldsEl.querySelectorAll('[data-achat-field]');
        for (var r = 0; r < rows.length; r++) {
            var el = rows[r];
            var fName = el.getAttribute('data-achat-field');
            var t = el.getAttribute('data-type') || 'string';
            _setFieldValue(el, t, cache[fName]);
            (function (fieldEl, fieldName, fieldType) {
                var save = function () {
                    if (!tab.toolArgs[toolName]) tab.toolArgs[toolName] = {};
                    if (fieldType === 'boolean') tab.toolArgs[toolName][fieldName] = !!fieldEl.checked;
                    else tab.toolArgs[toolName][fieldName] = fieldEl.value;
                };
                fieldEl.addEventListener('change', save);
                fieldEl.addEventListener('input', save);
            })(el, fName, t);
        }
    }

    function _renderAchatAgentConfig(tab) {
        var wrap = document.getElementById('achat-agent-config-wrap');
        if (!wrap) return;
        if (!tab) {
            wrap.style.display = 'none';
            wrap.innerHTML = '';
            return;
        }
        wrap.style.display = _achatAgentConfigOpen ? 'block' : 'none';
        if (!_achatAgentConfigOpen) return;
        wrap.innerHTML = _renderAgentConfigPanel(tab);
    }

    function _renderAchatPolicyPanel(tab) {
        var panel = document.getElementById('achat-tool-policy');
        if (!panel || !tab) return;

        var all = _allToolNames().filter(function (t) { return t !== 'agent_chat'; });
        var filter = String((document.getElementById('achat-policy-filter') || {}).value || '').trim().toLowerCase();
        var filtered = all.filter(function (n) {
            if (_achatBlockedTools[n]) return false;
            return !filter || n.toLowerCase().indexOf(filter) >= 0;
        });

        var selected = {};
        var granted = Array.isArray(tab.grantedTools) ? tab.grantedTools : [];
        for (var i = 0; i < granted.length; i++) selected[granted[i]] = true;

        var html = '';
        html += '<div class="achat-policy-head">';
        html += '<input id="achat-policy-filter" placeholder="Filter tools..." value="' + escHtml(filter) + '" />';
        html += '<button class="btn-dim" onclick="achatPolicyDefault()">DEFAULT</button>';
        html += '<button class="btn-dim" onclick="achatPolicySelectAll()">ALL SAFE</button>';
        html += '<button class="btn-dim" onclick="achatPolicyClear()">CLEAR</button>';
        html += '</div>';
        html += '<div class="achat-policy-list">';
        if (!filtered.length) {
            html += '<div class="achat-policy-empty">No tools match this filter.</div>';
        } else {
            for (var j = 0; j < filtered.length; j++) {
                var tool = filtered[j];
                var checked = selected[tool] ? ' checked' : '';
                html += '<label class="achat-policy-item"><input type="checkbox" data-achat-policy="' + escHtml(tool) + '"' + checked + ' /> ' + escHtml(tool) + '</label>';
            }
        }
        html += '</div>';
        panel.innerHTML = html;

        var filterEl = document.getElementById('achat-policy-filter');
        if (filterEl && !filterEl.dataset.bound) {
            filterEl.addEventListener('input', function () { _renderAchatPolicyPanel(tab); });
            filterEl.dataset.bound = '1';
        }

        var boxes = panel.querySelectorAll('[data-achat-policy]');
        for (var b = 0; b < boxes.length; b++) {
            boxes[b].addEventListener('change', function () {
                var list = [];
                var cbs = panel.querySelectorAll('[data-achat-policy]');
                for (var k = 0; k < cbs.length; k++) {
                    if (cbs[k].checked) list.push(cbs[k].getAttribute('data-achat-policy'));
                }
                var hiddenKept = (tab.grantedTools || []).filter(function (t) {
                    return list.indexOf(t) < 0 && filtered.indexOf(t) < 0;
                });
                tab.grantedTools = _sanitizeGrantedTools(list.concat(hiddenKept));
                var policyKey = _policyKeyForSlot(tab.slot, tab.modelSource);
                _achatToolPolicies[policyKey] = tab.grantedTools.slice();
                _saveAchatToolPolicies();
                _refreshAchatMeta();
            });
        }
    }

    function achatPolicyDefault() {
        var tab = _getActiveAchatTab();
        if (!tab) return;
        tab.grantedTools = _defaultGrantedToolsForTab(tab);
        _achatToolPolicies[_policyKeyForSlot(tab.slot, tab.modelSource)] = tab.grantedTools.slice();
        _saveAchatToolPolicies();
        _renderAchatPolicyPanel(tab);
        _refreshAchatMeta();
    }
    window.achatPolicyDefault = achatPolicyDefault;

    function achatPolicySelectAll() {
        var tab = _getActiveAchatTab();
        if (!tab) return;
        tab.grantedTools = _allToolNames().filter(function (t) { return !_achatBlockedTools[t] && t !== 'agent_chat'; });
        _achatToolPolicies[_policyKeyForSlot(tab.slot, tab.modelSource)] = tab.grantedTools.slice();
        _saveAchatToolPolicies();
        _renderAchatPolicyPanel(tab);
        _refreshAchatMeta();
    }
    window.achatPolicySelectAll = achatPolicySelectAll;

    function achatPolicyClear() {
        var tab = _getActiveAchatTab();
        if (!tab) return;
        tab.grantedTools = [];
        _achatToolPolicies[_policyKeyForSlot(tab.slot, tab.modelSource)] = [];
        _saveAchatToolPolicies();
        _renderAchatPolicyPanel(tab);
        _refreshAchatMeta();
    }
    window.achatPolicyClear = achatPolicyClear;

    function _activateAchatTab(key, focusInput) {
        if (!_achatTabs[key]) return;
        _achatActiveTabKey = key;
        var tab = _achatTabs[key];
        _achatSlot = tab.slot;
        _renderAchatTabs();
        _refreshAchatMeta();
        _syncAchatLoopControlsFromConfig(tab);
        _renderAchatRunMode(tab);
        _renderAchatToolSelect(tab);
        _renderAchatToolConfig(tab);
        _renderAchatAgentConfig(tab);
        _renderAchatMessages(tab);
        _renderAchatPolicyPanel(tab);

        var inputEl = document.getElementById('achat-input');
        if (focusInput && inputEl) setTimeout(function () { inputEl.focus(); }, 30);
    }

    function _refreshAchatMeta() {
        var tab = _getActiveAchatTab();
        var titleEl = document.getElementById('achat-title');
        var sidEl = document.getElementById('achat-session-id');
        var nameEl = document.getElementById('achat-model-name');
        var metaEl = document.getElementById('achat-model-meta');
        var toolCountEl = document.getElementById('achat-tool-count');
        var blockedEl = document.getElementById('achat-blocked-count');
        var modeEl = document.getElementById('achat-run-mode');
        if (!tab) {
            if (titleEl) titleEl.textContent = 'AGENT MCP CONSOLE';
            if (sidEl) sidEl.textContent = '';
            if (nameEl) nameEl.textContent = '—';
            if (metaEl) metaEl.innerHTML = '';
            if (toolCountEl) toolCountEl.textContent = '0';
            if (blockedEl) blockedEl.textContent = String(Object.keys(_achatBlockedTools).length);
            if (modeEl) modeEl.value = 'direct';
            return;
        }

        if (titleEl) titleEl.textContent = 'SLOT ' + tab.slot + ' — MCP ORCHESTRATION';
        if (sidEl) sidEl.textContent = tab.sessionId ? ('session: ' + tab.sessionId) : '';
        if (nameEl) nameEl.textContent = tab.modelSource || ('slot_' + tab.slot);

        if (metaEl) {
            var typeClass = 'type-llm';
            if (tab.modelType.indexOf('EMBED') >= 0) typeClass = 'type-embed';
            else if (tab.modelType.indexOf('CLASS') >= 0) typeClass = 'type-class';
            else if (tab.modelType.indexOf('RERANK') >= 0) typeClass = 'type-rerank';
            metaEl.innerHTML =
                '<span class="achat-tag ' + typeClass + '">' + escHtml(tab.modelType || 'MODEL') + '</span>' +
                '<span class="achat-tag">SLOT ' + tab.slot + '</span>' +
                '<span class="achat-tag">' + (tab.isPlugged ? 'PLUGGED' : 'EMPTY') + '</span>' +
                '<span class="achat-tag">' + escHtml(String((tab.runMode || 'direct').toUpperCase())) + '</span>';
            if (!tab.canChat) {
                metaEl.innerHTML += '<span class="achat-tag" style="color:#f59e0b;border-color:#f59e0b;background:rgba(245,158,11,0.12);">NO AGENT LOOP</span>';
            }
        }

        if (toolCountEl) toolCountEl.textContent = String((tab.grantedTools || []).length);
        if (blockedEl) blockedEl.textContent = String(Object.keys(_achatBlockedTools).length);
        if (modeEl) modeEl.value = tab.runMode || (tab.canChat ? 'loop' : 'direct');
    }

    function _bindAchatComposerEvents() {
        if (_achatComposerBound) return;
        _achatComposerBound = true;

        var toolFilter = document.getElementById('achat-tool-filter');
        if (toolFilter) {
            toolFilter.addEventListener('input', function () {
                var tab = _getActiveAchatTab();
                if (!tab) return;
                _renderAchatToolSelect(tab);
                _renderAchatToolConfig(tab);
            });
        }

        var toolSelect = document.getElementById('achat-run-tool');
        if (toolSelect) {
            toolSelect.addEventListener('change', function () {
                var tab = _getActiveAchatTab();
                if (!tab) return;
                tab.selectedTool = this.value || 'invoke_slot';
                _renderAchatToolConfig(tab);
            });
        }

        var modeSelect = document.getElementById('achat-run-mode');
        if (modeSelect) {
            modeSelect.addEventListener('change', function () {
                var tab = _getActiveAchatTab();
                if (!tab) return;
                var mode = String(this.value || 'direct');
                if (mode !== 'loop' && mode !== 'direct') mode = 'direct';
                if (mode === 'loop' && !tab.canChat) mode = 'direct';
                tab.runMode = mode;
                _renderAchatRunMode(tab);
                _renderAchatToolConfig(tab);
                _refreshAchatMeta();
            });
        }

        var maxIterEl = document.getElementById('achat-max-iter');
        if (maxIterEl) {
            maxIterEl.addEventListener('change', function () {
                var tab = _getActiveAchatTab();
                if (!tab || !tab.agentConfig) return;
                tab.agentConfig.maxIterations = _cfgInt(this.value, _agentMaxIterations(tab), 1, 200);
                _saveAgentConfig(tab);
                this.value = String(tab.agentConfig.maxIterations);
            });
        }

        var maxTokensEl = document.getElementById('achat-max-tokens');
        if (maxTokensEl) {
            maxTokensEl.addEventListener('change', function () {
                var tab = _getActiveAchatTab();
                if (!tab || !tab.agentConfig) return;
                tab.agentConfig.maxTokens = _cfgInt(this.value, _agentMaxTokens(tab), 64, 8192);
                _saveAgentConfig(tab);
                this.value = String(tab.agentConfig.maxTokens);
            });
        }
    }

    function openAgentChat(slot) {
        _loadAchatToolPolicies();
        var tab = _ensureAchatTab(slot);
        if (!tab) return;

        if (_slotDrill && _slotDrill.active) closeSlotDrill();

        var councilTab = document.getElementById('tab-council');
        if (!councilTab) return;
        councilTab.classList.add('chat-active');

        _bindAchatComposerEvents();
        _renderAchatTabs();
        _activateAchatTab(tab.key, true);

        if (Object.keys(_toolSchemas || {}).length === 0) {
            vscode.postMessage({ command: 'fetchToolSchemas' });
        }

        if (!tab.isPlugged) {
            _appendAchatMsg('error',
                'This slot is empty. Plug a model first.\n\nExample: plug_model(model_id="Qwen/Qwen2.5-1.5B-Instruct")',
                Date.now(),
                tab
            );
        } else if (!tab.canChat) {
            _appendAchatMsg('system-info',
                'This slot type is not chat-loop capable. Use direct tool invocations (invoke_slot, embed_text, classify, rerank, etc.).',
                Date.now(),
                tab
            );
        }
    }
    window.openAgentChat = openAgentChat;

    function closeAgentChat() {
        var tab = document.getElementById('tab-council');
        if (tab) tab.classList.remove('chat-active');
        _stopElapsedTimer();
    }
    window.closeAgentChat = closeAgentChat;

    function resetAgentChat() {
        var tab = _getActiveAchatTab();
        if (!tab) return;
        tab.sessionId = '';
        tab.messages = [];
        window.__achatKillRequested = false;
        _renderAchatMessages(tab);
        _refreshAchatMeta();
        _setAchatBusy(false);
    }
    window.resetAgentChat = resetAgentChat;

    function requestAchatKillSwitch() {
        window.__achatKillRequested = true;
        var tab = _getActiveAchatTab();
        if (tab) {
            _appendAchatMsg('system-info', '🛑 Kill switch requested. Loop will stop at the next safety checkpoint.', Date.now(), tab);
        }
    }
    window.requestAchatKillSwitch = requestAchatKillSwitch;

    function toggleAchatToolConfig() {
        _achatToolConfigOpen = !_achatToolConfigOpen;
        _achatAgentConfigOpen = false;
        var tab = _getActiveAchatTab();
        var policyPanel = document.getElementById('achat-tool-policy');
        if (policyPanel) policyPanel.style.display = 'none';
        var agentCfg = document.getElementById('achat-agent-config-wrap');
        if (agentCfg) agentCfg.style.display = 'none';
        var cfg = document.getElementById('achat-tool-config');
        if (cfg) cfg.style.display = _achatToolConfigOpen ? 'block' : 'none';
        if (!tab) return;
        _renderAchatToolConfig(tab);
        _renderAchatAgentConfig(tab);
    }
    window.toggleAchatToolConfig = toggleAchatToolConfig;

    function toggleAchatPolicy() {
        _achatToolConfigOpen = true;
        _achatAgentConfigOpen = false;
        var tab = _getActiveAchatTab();
        var panel = document.getElementById('achat-tool-policy');
        var cfg = document.getElementById('achat-tool-config');
        var agentCfg = document.getElementById('achat-agent-config-wrap');
        if (agentCfg) agentCfg.style.display = 'none';
        if (panel) panel.style.display = (panel.style.display === 'block') ? 'none' : 'block';
        if (cfg) cfg.style.display = (panel && panel.style.display === 'block') ? 'none' : 'block';
        if (tab) {
            _renderAchatPolicyPanel(tab);
            _renderAchatToolConfig(tab);
            _renderAchatAgentConfig(tab);
        }
    }
    window.toggleAchatPolicy = toggleAchatPolicy;

    function toggleAchatAgentConfig() {
        _achatAgentConfigOpen = !_achatAgentConfigOpen;
        _achatToolConfigOpen = true;
        var tab = _getActiveAchatTab();
        var policyPanel = document.getElementById('achat-tool-policy');
        if (policyPanel) policyPanel.style.display = 'none';
        var cfg = document.getElementById('achat-tool-config');
        if (cfg) cfg.style.display = !_achatAgentConfigOpen ? 'block' : 'none';
        if (!tab) return;
        _renderAchatToolConfig(tab);
        _renderAchatPolicyPanel(tab);
        _renderAchatAgentConfig(tab);
    }
    window.toggleAchatAgentConfig = toggleAchatAgentConfig;

    function _setAchatBusy(busy) {
        _achatBusy = busy;
        var btn = document.getElementById('achat-send-btn');
        var thinking = document.getElementById('achat-thinking');
        var input = document.getElementById('achat-input');
        if (btn) btn.disabled = busy;
        if (input) input.disabled = busy;
        if (thinking) thinking.classList.toggle('active', busy);
        if (busy) {
            _achatSendTime = Date.now();
            _startElapsedTimer();
        } else {
            _stopElapsedTimer();
        }
    }

    function _startElapsedTimer() {
        _stopElapsedTimer();
        var el = document.getElementById('achat-elapsed');
        _achatElapsedTimer = setInterval(function () {
            if (el) {
                var secs = Math.round((Date.now() - _achatSendTime) / 1000);
                el.textContent = secs + 's';
            }
        }, 500);
    }

    function _stopElapsedTimer() {
        if (_achatElapsedTimer) {
            clearInterval(_achatElapsedTimer);
            _achatElapsedTimer = null;
        }
    }

    function _coerceFieldValue(raw, pType) {
        if (raw === '' || raw === null || raw === undefined) return undefined;
        if (pType === 'integer') {
            var iv = parseInt(raw, 10);
            return isNaN(iv) ? undefined : iv;
        }
        if (pType === 'number') {
            var nv = parseFloat(raw);
            return isNaN(nv) ? undefined : nv;
        }
        if (pType === 'boolean') {
            return !!raw;
        }
        if (pType === 'object' || pType === 'array') {
            if (typeof raw !== 'string') return raw;
            var parsed = _safeJsonParse(raw);
            if (parsed === null && raw.trim()) throw new Error('Invalid JSON for ' + pType + ' field');
            return parsed;
        }
        return String(raw);
    }

    function _collectSelectedToolArgs(tab, toolName, userMsg) {
        var args = {};
        if (toolName === 'agent_chat') {
            var cfg = tab.agentConfig || _defaultAgentConfig();
            var iterVal = (document.getElementById('achat-max-iter') || {}).value;
            var tokVal = (document.getElementById('achat-max-tokens') || {}).value;
            args.slot = tab.slot;
            args.message = String(userMsg || '').trim() || 'Proceed with the configured objective.';
            args.max_iterations = _cfgInt(iterVal, _agentMaxIterations(tab), 1, 200);
            args.max_tokens = _cfgInt(tokVal, _agentMaxTokens(tab), 64, 8192);
            args.context_strategy = String(cfg.contextStrategy || 'sliding-window');
            args.context_window_size = _cfgInt(cfg.contextWindowSize, 20, 5, 200);
            args.granted_tools = Array.isArray(tab.grantedTools) ? tab.grantedTools.slice() : [];
            if (tab.sessionId) args.session_id = tab.sessionId;
            return args;
        }

        var schema = _getAchatToolSchema(toolName);
        var props = (schema && schema.properties) ? schema.properties : {};
        var required = (schema && schema.required) ? schema.required : [];
        var elements = document.querySelectorAll('#achat-config-fields [data-achat-field]');
        for (var i = 0; i < elements.length; i++) {
            var el = elements[i];
            var name = el.getAttribute('data-achat-field');
            var pType = el.getAttribute('data-type') || 'string';
            var raw;
            if (pType === 'boolean') raw = !!el.checked;
            else raw = el.value;
            var value = _coerceFieldValue(raw, pType);
            if (value !== undefined) args[name] = value;
        }

        var pNames = Object.keys(props || {});
        for (var j = 0; j < pNames.length; j++) {
            var p = pNames[j];
            var def = props[p] || {};
            if (args[p] === undefined && def.default !== undefined && def.default !== null) {
                args[p] = def.default;
            }
        }

        var msg = String(userMsg || '').trim();
        if (msg) {
            var textKeys = ['message', 'prompt', 'text', 'input_text', 'query'];
            for (var k = 0; k < textKeys.length; k++) {
                var tk = textKeys[k];
                if (props[tk] && (args[tk] === undefined || args[tk] === '')) {
                    args[tk] = msg;
                    break;
                }
            }
            if (toolName === 'invoke_slot' && (!args.text || args.text === '')) {
                args.text = msg;
            }
        }

        if (toolName === 'invoke_slot') {
            if (args.slot === undefined || args.slot === null || args.slot === '') args.slot = tab.slot;
            if (!args.mode) {
                if (tab.modelType.indexOf('EMBED') >= 0) args.mode = 'embed';
                else if (tab.modelType.indexOf('CLASS') >= 0) args.mode = 'classify';
                else if (tab.modelType.indexOf('RERANK') >= 0) args.mode = 'forward';
                else args.mode = 'generate';
            }
            if (args.max_tokens === undefined || args.max_tokens === null || args.max_tokens === '') {
                args.max_tokens = _cfgInt((document.getElementById('achat-max-tokens') || {}).value, _agentMaxTokens(tab), 64, 8192);
            }
        }

        if (props.slot && (args.slot === undefined || args.slot === null || args.slot === '')) {
            args.slot = tab.slot;
        }

        if (toolName === 'compare' && Array.isArray(args.slots)) {
            var compareSlots = _coerceSlotList(args.slots);
            if (compareSlots.invalid.length) {
                throw new Error('compare.slots must contain numeric slot indexes only.');
            }
            if (compareSlots.values.length) args.slots = compareSlots.values;
            else delete args.slots;
        }

        // Guard against strict validators that reject explicit nulls for optional arrays/objects.
        if (toolName === 'invoke_slot' && args.messages === null) {
            delete args.messages;
        }
        var argKeys = Object.keys(args);
        for (var ak = 0; ak < argKeys.length; ak++) {
            var av = args[argKeys[ak]];
            if (av === null || av === undefined) delete args[argKeys[ak]];
        }

        for (var r = 0; r < required.length; r++) {
            var req = required[r];
            if (args[req] === undefined || args[req] === null || args[req] === '') {
                throw new Error('Missing required field: ' + req);
            }
        }

        return args;
    }

    function _prettyTruncate(value, maxLen) {
        var out = '';
        try {
            if (typeof value === 'string') {
                var parsed = _safeJsonParse(value);
                out = parsed !== null ? JSON.stringify(parsed, null, 2) : value;
            } else {
                out = JSON.stringify(value, null, 2);
            }
        }
        catch (e) { out = String(value); }
        var lim = maxLen || 3000;
        if (out.length > lim) out = out.substring(0, lim) + '\n…[truncated]';
        return out;
    }

    function _extractRequiredToolCalls(mission) {
        var text = String(mission || '').toLowerCase();
        if (!text) return 0;
        var patterns = [
            /(?:at\s*least|minimum\s*of|minimum|exactly)\s*(\d{1,4})\s*tool\s*calls?/i,
            /(\d{1,4})\s*tool\s*calls?/i
        ];
        for (var i = 0; i < patterns.length; i++) {
            var m = text.match(patterns[i]);
            if (m && m[1]) {
                var n = parseInt(m[1], 10);
                if (n > 0) return n;
            }
        }
        return 0;
    }


    function sendAgentChat() {
        var tab = _getActiveAchatTab();
        if (!tab) return;

        var input = document.getElementById('achat-input');
        var msg = input ? String(input.value || '').trim() : '';
        if (input) input.value = '';

        // Operator commands
        if (/^\/sessions\b/i.test(msg || '')) {
            _appendAchatMsg('user', 'LIST LIVE AGENT SESSIONS', Date.now(), tab);
            callTool('agent_chat_sessions', { slot: tab.slot, limit: 20 }, '__achat_tool__', { tabKey: tab.key });
            return;
        }
        var injectCmd = String(msg || '').match(/^\/inject\s+(\S+)\s+([\s\S]+)$/i);
        if (injectCmd) {
            var targetSession = String(injectCmd[1] || '').trim();
            var injectText = String(injectCmd[2] || '').trim();
            if (!targetSession || !injectText) {
                _appendAchatMsg('error', 'Usage: /inject <session_id> <message>', Date.now(), tab);
                return;
            }
            _appendAchatMsg('user', 'LIVE UPDATE → ' + injectText, Date.now(), tab);
            callTool('agent_chat_inject', {
                session_id: targetSession,
                slot: tab.slot,
                message: injectText,
                sender: 'operator'
            }, '__achat_tool__', { tabKey: tab.key, keepBusy: true });
            return;
        }

        // If loop is currently executing, convert new user message into a live update injection.
        if (_achatBusy) {
            if (msg) {
                var targetSid = String(tab.sessionId || '').trim();
                if (!targetSid) {
                    _appendAchatMsg('error', 'Agent is running, but no session_id is available yet for injection.', Date.now(), tab);
                    return;
                }
                _appendAchatMsg('user', 'LIVE UPDATE → ' + msg, Date.now(), tab);
                callTool('agent_chat_inject', {
                    session_id: targetSid,
                    slot: tab.slot,
                    message: msg,
                    sender: 'operator'
                }, '__achat_tool__', { tabKey: tab.key, keepBusy: true });
            }
            return;
        }

        if (!tab.isPlugged) {
            _appendAchatMsg('error', 'Slot is empty. Plug a model before invoking tools.', Date.now(), tab);
            return;
        }

        var toolSel = document.getElementById('achat-run-tool');
        var toolName;
        if ((tab.runMode || 'direct') === 'loop' || !toolSel || !toolSel.value) {
            toolName = tab.canChat ? 'agent_chat' : (tab.selectedTool || 'invoke_slot');
        } else {
            toolName = toolSel.value;
        }
        tab.selectedTool = toolName;

        // For loop mode with agent_chat: fire one tool call per step (max_iterations=1),
        // with a +1 synthesis pass appended at the end of the chain for final answer.
        if ((tab.runMode || 'direct') === 'loop' && toolName === 'agent_chat') {
            var mission = msg || 'Proceed with the configured objective.';
            _appendAchatMsg('user', 'MISSION: ' + mission, Date.now(), tab);
            _setAchatBusy(true);
            var _cfg = tab.agentConfig || _defaultAgentConfig();
            var _maxIter = _cfgInt((document.getElementById('achat-max-iter') || {}).value, _agentMaxIterations(tab), 1, 200);
            var _minCalls = _extractRequiredToolCalls(mission);
            // Only expand iterations if the user explicitly requested N tool calls
            // in their mission text (e.g. "call 10 tools"). Never auto-expand to
            // the granted tool count — that forces 143 iterations just to say hello.
            if (_minCalls > _maxIter) {
                _appendAchatMsg('system-info', 'Auto-expanding max iterations from ' + _maxIter + ' to ' + _minCalls + ' to satisfy explicit tool-call target in mission.', Date.now(), tab);
                _maxIter = _minCalls;
            }
            // Always +1: reserve a final iteration for synthesis/final_answer.
            // User sets N iterations for tool calls; the system adds 1 on top
            // so the model always gets a dedicated synthesis pass at the end.
            _maxIter += 1;
            tab._loopState = {
                mission: mission,
                nextMessage: mission,
                iteration: 0,
                maxIterations: _maxIter,
                minToolCalls: _minCalls > 0 ? _minCalls : 1,
                maxTokens: _cfgInt((document.getElementById('achat-max-tokens') || {}).value, _agentMaxTokens(tab), 64, 8192),
                totalToolCalls: 0,
                calledTools: {},
                startTime: Date.now()
            };
            _fireAgentIteration(tab);
            return;
        }

        try {
            var args = _collectSelectedToolArgs(tab, toolName, msg);
            var argsLine;
            try { argsLine = JSON.stringify(args); } catch (e0) { argsLine = String(args); }
            if (argsLine.length > 420) argsLine = argsLine.slice(0, 420) + '…';
            var userLine = toolName + '(' + argsLine + ')';
            _appendAchatMsg('user', userLine, Date.now(), tab);
            _setAchatBusy(true);

            var route = (toolName === 'agent_chat') ? '__agent_chat__' : '__achat_tool__';
            callTool(toolName, args, route, { tabKey: tab.key });
        } catch (err) {
            _appendAchatMsg('error', String(err && err.message ? err.message : err), Date.now(), tab);
        }
    }
    window.sendAgentChat = sendAgentChat;

    // Fire a single agent_chat step.
    // Normal iterations: max_iterations=1 (call one tool).
    // Final iteration (+1 synthesis pass): max_iterations=1 with a synthesis
    // prompt — the model sees "this is your last iteration" and produces a
    // comprehensive final answer instead of calling a tool.
    function _fireAgentIteration(tab) {
        if (!tab || !tab._loopState) return;
        if (window.__achatKillRequested) {
            _appendAchatMsg('system-info', '🛑 Kill switch activated. Loop terminated.', Date.now(), tab);
            _setAchatBusy(false);
            tab._loopState = null;
            window.__achatKillRequested = false;
            return;
        }
        var ls = tab._loopState;
        if (ls.iteration >= ls.maxIterations) {
            _appendAchatMsg('system-info', 'Loop reached max iterations (' + ls.maxIterations + ').', Date.now(), tab);
            _setAchatBusy(false);
            tab._loopState = null;
            return;
        }

        var isSynthesisPass = (ls.iteration === ls.maxIterations - 1);
        var iterLabel = isSynthesisPass
            ? 'Iteration ' + (ls.iteration + 1) + '/' + ls.maxIterations + ' — final synthesis…'
            : 'Iteration ' + (ls.iteration + 1) + '/' + ls.maxIterations + ' — thinking…';
        _appendAchatMsg('system-info', iterLabel, Date.now(), tab);

        var nextMsg = String(ls.nextMessage || ls.mission || '').trim() || 'Continue the task with granted tools.';

        if (isSynthesisPass) {
            // Final +1 pass: tell the model to synthesize everything into a final report.
            var used = Object.keys(ls.calledTools || {});
            nextMsg =
                'This is your FINAL iteration. Do NOT call any more tools. ' +
                'Produce a comprehensive final_answer summarizing ALL findings from your ' +
                ls.totalToolCalls + ' tool calls (' + used.join(', ') + '). ' +
                'Be thorough — include key data points, anomalies, and conclusions.\n\n' +
                'Original mission: ' + (ls.mission || 'N/A');
        } else {
            var _minCalls = parseInt(ls.minToolCalls, 10) || 1;
            if (_minCalls > 1) {
                var _remaining = Math.max(0, _minCalls - (parseInt(ls.totalToolCalls, 10) || 0));
                nextMsg =
                    'SEQUENTIAL EXECUTION ONLY. Call exactly one granted tool this turn. ' +
                    'Do not execute multiple tool calls in a single step. ' +
                    'Current progress: ' + (ls.totalToolCalls || 0) + '/' + _minCalls + ' tool calls (remaining ' + _remaining + ').\n\n' +
                    nextMsg;
            }
        }

        // Embed orchestration prompt into the first message only (capsule has no system_prompt param).
        if (ls.iteration === 0) {
            var sysPrompt = _buildLoopSystemPrompt(tab, { maxIterations: Math.max(1, (ls.maxIterations || 1) - 1) });
            if (sysPrompt) {
                nextMsg = '[SYSTEM INSTRUCTIONS]\n' + sysPrompt + '\n\n[USER MISSION]\n' + nextMsg;
            }
        }
        var _cfg = tab.agentConfig || _defaultAgentConfig();
        var args = {
            slot: tab.slot,
            message: nextMsg,
            max_iterations: 1,
            max_tokens: ls.maxTokens,
            context_strategy: String(_cfg.contextStrategy || 'sliding-window'),
            context_window_size: _cfgInt(_cfg.contextWindowSize, 20, 5, 200),
            granted_tools: Array.isArray(tab.grantedTools) ? tab.grantedTools.slice() : []
        };
        if (tab.sessionId) args.session_id = tab.sessionId;
        callTool('agent_chat', args, '__agent_chat_loop__', { tabKey: tab.key });
    }


    // ── INIT ──
    buildToolsRegistry();
    renderSlots([]);
    renderWorkflowList();
    renderWorkflowGraph(null, null);
    renderWorkflowNodeStates(null, null);
    _wfRenderDrillDetail();
    _wfSetBadge('idle', 'IDLE');

    // ── SLOT DRILL-IN BACK BUTTON ──
    var drillBackBtn = document.getElementById('slot-drill-back');
    if (drillBackBtn) drillBackBtn.addEventListener('click', function () { closeSlotDrill(); });

    // Tell extension we're ready
    vscode.postMessage({ command: 'ready' });

    // Auto-recover slot grid after transient disconnects / tab sleep.
    _startSlotWatchdog();
    window.addEventListener('focus', function () { _scheduleSlotRefresh('window-focus', 120); });
    window.addEventListener('online', function () { _scheduleSlotRefresh('network-online', 120); });
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') _scheduleSlotRefresh('tab-visible', 120);
    });

    // ── NIP-88: POLL HANDLERS ──
    (function () {
        var toggleBtn = document.getElementById('poll-toggle-btn');
        var createForm = document.getElementById('poll-create-form');
        var addOptBtn = document.getElementById('poll-add-option');
        var cancelBtn = document.getElementById('poll-cancel');
        var submitBtn = document.getElementById('poll-submit');
        var optsList = document.getElementById('poll-options-list');

        if (toggleBtn) toggleBtn.addEventListener('click', function () {
            createForm.style.display = createForm.style.display === 'none' ? 'block' : 'none';
        });
        if (addOptBtn) addOptBtn.addEventListener('click', function () {
            var input = document.createElement('input');
            input.className = 'chat-input poll-option-input';
            input.placeholder = 'Option ' + (optsList.children.length + 1);
            input.style.marginBottom = '4px';
            optsList.appendChild(input);
        });
        if (cancelBtn) cancelBtn.addEventListener('click', function () {
            createForm.style.display = 'none';
        });
        if (submitBtn) submitBtn.addEventListener('click', function () {
            var question = document.getElementById('poll-question').value.trim();
            var options = [];
            document.querySelectorAll('.poll-option-input').forEach(function (el) {
                if (el.value.trim()) options.push(el.value.trim());
            });
            var expiry = parseInt(document.getElementById('poll-expiry').value);
            if (question && options.length >= 2) {
                vscode.postMessage({ command: 'nostrCreatePoll', question: question, options: options, expiresIn: expiry > 0 ? expiry : undefined });
            } else {
                alert('Question and at least 2 options required');
            }
        });

        // Voting delegation
        document.addEventListener('click', function (e) {
            var opt = e.target.closest('.poll-option');
            if (opt && !opt.classList.contains('poll-results')) {
                var pollId = opt.closest('.poll-card').dataset.pollId;
                var index = parseInt(opt.dataset.option);
                vscode.postMessage({ command: 'nostrVotePoll', pollEventId: pollId, optionIndices: [index] });
                // Optimistic UI
                if (_polls[pollId]) _polls[pollId].voted = true;
                renderChatFeed();
            }
        });
    })();

    // ── NIP-58: BADGE HANDLERS ──
    (function () {
        var createToggle = document.getElementById('badge-create-toggle');
        var createForm = document.getElementById('badge-create-form');
        var createSubmit = document.getElementById('badge-create-submit');
        var createCancel = document.getElementById('badge-create-cancel');
        var awardForm = document.getElementById('badge-award-form');
        var awardSubmit = document.getElementById('badge-award-submit');
        var awardCancel = document.getElementById('badge-award-cancel');

        if (createToggle) createToggle.addEventListener('click', function () {
            createForm.style.display = 'block';
            awardForm.style.display = 'none';
        });
        if (createCancel) createCancel.addEventListener('click', function () {
            createForm.style.display = 'none';
        });
        if (createSubmit) createSubmit.addEventListener('click', function () {
            var id = document.getElementById('badge-id').value.trim();
            var name = document.getElementById('badge-name').value.trim();
            var desc = document.getElementById('badge-description').value.trim();
            var img = document.getElementById('badge-image').value.trim();
            if (id && name) {
                vscode.postMessage({ command: 'nostrCreateBadge', id: id, name: name, description: desc, image: img || undefined });
            }
        });

        if (awardCancel) awardCancel.addEventListener('click', function () {
            awardForm.style.display = 'none';
        });
        if (awardSubmit) awardSubmit.addEventListener('click', function () {
            var badgeId = document.getElementById('badge-award-select').value;
            var pks = document.getElementById('badge-award-pubkeys').value.split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
            if (badgeId && pks.length > 0) {
                vscode.postMessage({ command: 'nostrAwardBadge', badgeId: badgeId, pubkeys: pks });
                awardForm.style.display = 'none';
            }
        });

        // Award button in gallery
        document.addEventListener('click', function (e) {
            var btn = e.target.closest('.badge-award-btn');
            if (btn) {
                var badgeId = btn.dataset.badgeId;
                var select = document.getElementById('badge-award-select');
                if (select) {
                    select.innerHTML = Object.keys(_badges).map(function (k) {
                        var b = _badges[k];
                        return '<option value="' + b.id + '"' + (b.id === badgeId ? ' selected' : '') + '>' + safeHTML(b.name) + '</option>';
                    }).join('');
                }
                awardForm.style.display = 'block';
                createForm.style.display = 'none';
                document.getElementById('badge-award-pubkeys').focus();
            }
        });
    })();

    // ── NIP-90: DVM HANDLERS ──
    (function () {
        var submitBtn = document.getElementById('dvm-submit');
        if (submitBtn) submitBtn.addEventListener('click', function () {
            var jobKind = parseInt(document.getElementById('dvm-job-kind').value);
            var input = document.getElementById('dvm-input').value.trim();
            var bid = document.getElementById('dvm-bid').value;
            var paramsText = document.getElementById('dvm-params').value.trim();
            if (!input) return;

            var params = {};
            if (paramsText) {
                paramsText.split('\n').forEach(function (line) {
                    var parts = line.split('=');
                    if (parts.length === 2) params[parts[0].trim()] = parts[1].trim();
                });
            }

            vscode.postMessage({
                command: 'nostrSubmitDvmJob',
                jobKind: jobKind,
                inputs: [{ data: input, type: 'text' }],
                params: Object.keys(params).length > 0 ? params : undefined,
                bidMsats: bid ? parseInt(bid) * 1000 : undefined
            });
        });
    })();

    // ── NIP-39: IDENTITY HANDLERS ──
    (function () {
        var addBtn = document.getElementById('identity-add-claim');
        var publishBtn = document.getElementById('identity-publish');

        if (addBtn) addBtn.addEventListener('click', function () {
            var platform = document.getElementById('identity-platform').value;
            var identity = document.getElementById('identity-username').value.trim();
            var proof = document.getElementById('identity-proof').value.trim();
            if (identity) {
                _identityClaims.push({ platform: platform, identity: identity, proof: proof });
                renderIdentityClaims();
                document.getElementById('identity-username').value = '';
                document.getElementById('identity-proof').value = '';
            }
        });

        if (publishBtn) publishBtn.addEventListener('click', function () {
            if (_identityClaims.length > 0) {
                vscode.postMessage({ command: 'nostrPublishIdentity', claims: _identityClaims });
            }
        });

        document.addEventListener('click', function (e) {
            var btn = e.target.closest('.identity-remove-btn');
            if (btn) {
                var idx = parseInt(btn.dataset.idx);
                _identityClaims.splice(idx, 1);
                renderIdentityClaims();
            }
        });
    })();

    // ── NIP-A0: VOICE NOTE HANDLERS ──
    (function () {
        var recordBtn = document.getElementById('voice-note-btn');
        var recorderDiv = document.getElementById('voice-note-recorder');
        var cancelBtn = document.getElementById('voice-note-cancel');
        var sendBtn = document.getElementById('voice-note-send');
        var timeEl = document.getElementById('voice-rec-time');

        if (recordBtn) recordBtn.addEventListener('click', async function () {
            if (_voiceNoteRecording) return;
            try {
                var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                _voiceNoteMediaRecorder = new MediaRecorder(stream);
                _voiceNoteChunks = [];
                _voiceNoteMediaRecorder.ondataavailable = function (e) { if (e.data.size > 0) _voiceNoteChunks.push(e.data); };
                _voiceNoteMediaRecorder.onstop = function () {
                    stream.getTracks().forEach(function (t) { t.stop(); });
                };
                _voiceNoteMediaRecorder.start();
                _voiceNoteRecording = true;
                _voiceNoteStartTime = Date.now();
                recorderDiv.style.display = 'flex';
                _voiceNoteTimer = setInterval(function () {
                    var s = Math.floor((Date.now() - _voiceNoteStartTime) / 1000);
                    timeEl.textContent = Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);
                }, 1000);
            } catch (err) {
                console.error('[VoiceNote] Error:', err);
                mpToast('Microphone access denied or unavailable: ' + err.message, 'error', 5000);
            }
        });

        if (cancelBtn) cancelBtn.addEventListener('click', function () {
            if (_voiceNoteMediaRecorder && _voiceNoteMediaRecorder.state !== 'inactive') {
                _voiceNoteMediaRecorder.stop();
            }
            if (_voiceNoteTimer) clearInterval(_voiceNoteTimer);
            _voiceNoteRecording = false;
            recorderDiv.style.display = 'none';
        });

        if (sendBtn) sendBtn.addEventListener('click', function () {
            if (!_voiceNoteMediaRecorder) return;

            _voiceNoteMediaRecorder.onstop = function () {
                var blob = new Blob(_voiceNoteChunks, { type: 'audio/webm' });
                var duration = Math.floor((Date.now() - _voiceNoteStartTime) / 1000);

                // Use existing IPFS pinning service via extension message
                var reader = new FileReader();
                reader.onload = function () {
                    var base64 = reader.result.split(',')[1];
                    vscode.postMessage({
                        command: 'ipfsPin',
                        content: base64,
                        name: 'voice-note-' + Date.now() + '.webm'
                    });

                    var ipfsHandler = function (e) {
                        var msg = e.data;
                        if (msg.type === 'ipfsPinResult' && msg.success) {
                            window.removeEventListener('message', ipfsHandler);
                            var url = 'ipfs://' + msg.cid;
                            vscode.postMessage({
                                command: 'nostrSendVoiceNote',
                                audioUrl: url,
                                durationSecs: duration
                            });
                        }
                    };
                    window.addEventListener('message', ipfsHandler);
                };
                reader.readAsDataURL(blob);
            };

            if (_voiceNoteMediaRecorder.state !== 'inactive') {
                _voiceNoteMediaRecorder.stop();
            }
            if (_voiceNoteTimer) clearInterval(_voiceNoteTimer);
            _voiceNoteRecording = false;
            recorderDiv.style.display = 'none';
        });
    })();

    // Request Nostr identity on load
    vscode.postMessage({ command: 'nostrGetIdentity' });
    // Request privacy settings
    vscode.postMessage({ command: 'nostrGetPrivacy' });
    vscode.postMessage({ command: 'nostrGetBlockList' });
    // Request GitHub auth status
    vscode.postMessage({ command: 'githubGetAuth' });
    // Request UX settings
    vscode.postMessage({ command: 'uxGetSettings' });
    // Request Web3 data (DID, categories, doc types)
    vscode.postMessage({ command: 'web3GetDID' });
    vscode.postMessage({ command: 'web3GetCategories' });
    vscode.postMessage({ command: 'web3GetDocTypes' });
    // Community is intentionally disabled in Space build.
})();
