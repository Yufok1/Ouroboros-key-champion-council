// ══════════════════════════════════════════════════════════════
// Champion Council - Webview Main Script
// Loaded as a separate file to avoid template literal escaping hell
// ══════════════════════════════════════════════════════════════

(function () {
    const vscode = acquireVsCodeApi();
    const CATEGORIES = window.__CATEGORIES__ || {};
    let _state = {};
    let _activityLog = [];
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
                        _activityLog = msg.activityLog;
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
        if (portEl) portEl.textContent = ':' + (st.port || '----');
        updateMcpConfigBlock(st.port);

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
    var _serverPort = 8765;
    var _serverEntry = {
        disabled: false,
        disabledTools: [],
        url: 'http://127.0.0.1:8765/sse'
    };
    function updateMcpConfigBlock(port) {
        _serverPort = port || _serverPort;
        _serverEntry.url = 'http://127.0.0.1:' + _serverPort + '/sse';
        // Full config (for new files)
        var fullEl = document.getElementById('mcp-config-block');
        if (fullEl) {
            fullEl.textContent = JSON.stringify({ mcpServers: { 'champion-ouroboros': _serverEntry } }, null, 2);
        }
        // Entry snippet (for existing files)
        var entryEl = document.getElementById('mcp-entry-block');
        if (entryEl) {
            entryEl.textContent = '"champion-ouroboros": ' + JSON.stringify(_serverEntry, null, 2);
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

    // ── SLOTS RENDER ──
    function renderSlots(data) {
        _lastSlotsData = data;
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
            slotsArr = d.slots || d || [];
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
            gridTitle && (gridTitle.textContent = slotCount + '-SLOT COUNCIL GRID');
        } else {
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
            var detailText = slot.model_type || slot.type || (slot.status ? ('status: ' + String(slot.status).toUpperCase()) : '--');
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
                var modelLabel = slot.model_source || slot.model_id || slot.name || 'VACANT';
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
                if (!btn) return;
                var action = btn.dataset.action;
                var slot = parseInt(btn.dataset.slot);
                if (action === 'unplug') {
                    _unpluggingSlots[slot] = { startTime: Date.now() };
                    if (_lastSlotsData) renderSlots(_lastSlotsData);
                    callTool('unplug_slot', { slot: slot });
                }
                else if (action === 'invoke') callTool('invoke_slot', { slot: slot, text: 'test' });
                else if (action === 'clone') callTool('clone_slot', { slot: slot });
            });
            grid.dataset.actionsBound = '1';
        }
    }

    // ── PLUG LOADING UI ──
    var _plugTimer = null;
    var _lastSlotsData = null; // cache last slots data for re-render during plug

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

    // ── ACTIVITY FEED ──
    var PLUG_TOOLS = ['plug_model', 'hub_plug'];
    function addActivityEntry(event) {
        if (!event) return;

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
            // list_slots refresh is handled by the toolResult handler — no duplicate call here
        }

        _activityLog.push(event);
        if (_activityLog.length > 500) _activityLog = _activityLog.slice(-500);
        if (event.tool === 'workflow_execute' || event.tool === 'workflow_status') {
            handleWorkflowActivity(event);
        }
        // Append new entry to DOM without destroying expanded entries
        var feed = document.getElementById('activity-feed');
        if (feed) {
            // Remove "No activity yet" placeholder if present
            var placeholder = feed.querySelector('.activity-entry[style*="text-align:center"]');
            if (placeholder) placeholder.remove();
            var node = _buildActivityNode(event);
            if (node) feed.insertBefore(node, feed.firstChild);
            // Trim to 50 visible entries
            while (feed.children.length > 50) feed.removeChild(feed.lastChild);
        }
    }

    function _actEsc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

    function _buildActivityNode(e) {
        var ts = new Date(e.timestamp).toLocaleTimeString();
        var fullTs = new Date(e.timestamp).toISOString();
        var hasError = !!e.error;
        var source = e.source || 'extension';

        var detail = '';
        detail += '<div class="ad-section"><span class="ad-label">Timestamp</span>\n' + fullTs + '</div>';
        detail += '<div class="ad-section"><span class="ad-label">Source</span>\n' + _actEsc(source) + '</div>';
        detail += '<div class="ad-section"><span class="ad-label">Category</span>\n' + _actEsc(e.category || 'unknown') + '</div>';
        detail += '<div class="ad-section"><span class="ad-label">Duration</span>\n' + (e.durationMs || 0) + 'ms</div>';
        if (hasError) {
            detail += '<div class="ad-section" style="color:var(--red)"><span class="ad-label">Error</span>\n' + _actEsc(e.error) + '</div>';
        }
        if (e.args && Object.keys(e.args).length > 0) {
            detail += '<div class="ad-section"><span class="ad-label">Arguments</span>\n' + _actEsc(JSON.stringify(e.args, null, 2)) + '</div>';
        } else {
            detail += '<div class="ad-section"><span class="ad-label">Arguments</span>\nNone</div>';
        }
        if (e.result) {
            var resultObj = e.result;
            // ── Unwrap MCP protocol envelope for extension-source calls ──
            // callTool returns { content: [{ type: "text", text: "..." }], structuredContent: {...} }
            if (typeof resultObj === 'object' && resultObj !== null && resultObj.content && Array.isArray(resultObj.content)) {
                // Try structuredContent.result first (parsed), then content[0].text (raw)
                var innerText = null;
                if (resultObj.structuredContent && resultObj.structuredContent.result) {
                    innerText = resultObj.structuredContent.result;
                } else if (resultObj.content[0] && resultObj.content[0].text) {
                    innerText = resultObj.content[0].text;
                }
                if (innerText) {
                    // Try to parse as JSON for structured rendering
                    try {
                        resultObj = JSON.parse(innerText);
                    } catch (ex) {
                        resultObj = innerText;
                    }
                }
            }
            // Render structured results with per-key formatting
            if (typeof resultObj === 'object' && resultObj !== null && !Array.isArray(resultObj)) {
                var resultLines = [];
                for (var rk in resultObj) {
                    if (!resultObj.hasOwnProperty(rk)) continue;
                    if (rk.startsWith('_')) continue; // skip internal keys like _cached, _size
                    var rv = resultObj[rk];
                    var rvStr = (rv === null || rv === undefined) ? 'null' : (typeof rv === 'object' ? JSON.stringify(rv, null, 2) : String(rv));
                    resultLines.push(_actEsc(rk) + ': ' + _actEsc(rvStr));
                }
                detail += '<div class="ad-section"><span class="ad-label">Result</span>\n' + resultLines.join('\n') + '</div>';
            } else {
                var resultStr = typeof resultObj === 'string' ? resultObj : JSON.stringify(resultObj, null, 2);
                detail += '<div class="ad-section"><span class="ad-label">Result</span>\n' + _actEsc(resultStr.substring(0, 4000)) + '</div>';
            }
        }

        // ── CASCADE enrichment for external structured calls ──
        if (source === 'external') {
            var metaLines = [];
            // Metrics extracted from result
            if (e.result && typeof e.result === 'object' && e.result.metrics && typeof e.result.metrics === 'object') {
                var mParts = [];
                for (var mk in e.result.metrics) {
                    if (e.result.metrics.hasOwnProperty(mk)) mParts.push(_actEsc(mk) + '=' + _actEsc(String(e.result.metrics[mk])));
                }
                if (mParts.length > 0) metaLines.push('Metrics: ' + mParts.join(', '));
            }
            // Cascade step
            if (e.result && typeof e.result === 'object' && e.result.cascade_step) {
                metaLines.push('CASCADE Step: #' + _actEsc(String(e.result.cascade_step)));
            }
            // Result size + cached
            if (e.result && typeof e.result === 'object' && e.result.result_size) {
                var sizeStr = e.result.result_size > 1024 ? (e.result.result_size / 1024).toFixed(1) + 'KB' : e.result.result_size + 'B';
                metaLines.push('Result Size: ' + sizeStr + (e.result.cached ? ' (cached)' : ''));
            }
            if (metaLines.length > 0) {
                detail += '<div class="ad-section" style="opacity:0.7"><span class="ad-label">CASCADE</span>\n' + metaLines.join('\n') + '</div>';
            }
        }

        var sourceBadge = source === 'external'
            ? '<span class="activity-cat" style="border-color:var(--blue);color:var(--blue);">EXTERNAL</span>'
            : '';
        var div = document.createElement('div');
        div.className = 'activity-entry';
        div.onclick = function () {
            var sel = window.getSelection();
            if (sel && sel.toString().length > 0) return; // don't toggle when selecting text
            div.classList.toggle('expanded');
        };
        div.innerHTML =
            '<span class="activity-ts">' + ts + '</span> ' +
            '<span class="activity-tool">' + _actEsc(e.tool) + '</span>' +
            '<span class="activity-cat">' + _actEsc(e.category) + '</span>' +
            sourceBadge +
            '<span class="activity-duration">' + (e.durationMs || 0) + 'ms</span>' +
            (hasError ? ' <span style="color:var(--red);">ERR</span>' : '') +
            '<span class="activity-expand-hint">click to expand</span>' +
            '<pre class="activity-detail">' + detail + '</pre>';
        return div;
    }

    function renderActivityFeed() {
        var feed = document.getElementById('activity-feed');
        if (!feed) return;
        var filterEl = document.getElementById('activity-filter');
        var filter = (filterEl ? filterEl.value : '').toLowerCase();
        var filtered = filter
            ? _activityLog.filter(function (e) {
                return e.tool.toLowerCase().includes(filter) ||
                    e.category.toLowerCase().includes(filter) ||
                    String(e.source || '').toLowerCase().includes(filter);
            })
            : _activityLog;

        if (filtered.length === 0) {
            feed.innerHTML = '<div class="activity-entry" style="color:var(--text-dim);padding:20px;text-align:center;">No activity yet.</div>';
            return;
        }

        var recent = filtered.slice(-50).reverse();
        feed.innerHTML = '';
        recent.forEach(function (e) {
            feed.appendChild(_buildActivityNode(e));
        });
    }

    var activityFilterEl = document.getElementById('activity-filter');
    if (activityFilterEl) activityFilterEl.addEventListener('input', renderActivityFeed);

    // ── TOOL CALL ──
    var _pendingTools = {}; // id -> tool name
    var _pendingDiagnostics = {}; // id -> diagnostic key
    function callTool(name, args, routeAs) {
        var id = ++_requestId;
        _pendingTools[id] = routeAs || name;
        // Clear council output panel on new council operations for clean visual transitions
        if (COUNCIL_TOOLS.indexOf(name) >= 0 && name !== 'list_slots') {
            var councilOut = document.getElementById('council-output');
            if (councilOut) councilOut.innerHTML = '<pre style="white-space:pre-wrap;color:var(--text-dim);font-size:11px;">Running ' + name + '...</pre>';
        }
        vscode.postMessage({ command: 'callTool', tool: name, args: args || {}, id: id });
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

    var MEMORY_TOOLS = ['bag_catalog', 'bag_search', 'bag_get', 'bag_export', 'bag_induct', 'bag_forget', 'bag_put', 'pocket', 'summon', 'materialize', 'get_cached'];
    var COUNCIL_TOOLS = ['council_status', 'all_slots', 'broadcast', 'council_broadcast', 'set_consensus', 'debate', 'chain', 'slot_info', 'get_slot_params', 'invoke_slot', 'plug_model', 'unplug_slot', 'clone_slot', 'mu' + 'tate_slot', 'rename_slot', 'swap_slots', 'hub_plug', 'cu' + 'll_slot'];
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
        callTool('bag_get', { key: key });
    }
    window.drillMemItem = drillMemItem;

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

        // If result has an "error" field, format as guidance
        if (obj.error) {
            var lines = ['ERROR: ' + obj.error, ''];
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
        var toolName = _pendingTools[msg.id] || '';
        delete _pendingTools[msg.id];

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

        var text = msg.error ? 'ERROR: ' + msg.error : parseToolData(msg.data);

        if (WORKFLOW_TOOLS.indexOf(toolName) >= 0) {
            handleWorkflowToolResult(toolName, msg, text);
            return;
        }

        // Format tool output for readability (extract error guidance)
        if (!msg.error) text = formatToolOutput(text);

        // Auto-resolve cached memory responses so Memory tab can render full data.
        if (!msg.error && MEMORY_TOOLS.indexOf(toolName) >= 0) {
            try {
                var cachedProbe = typeof text === 'string' ? JSON.parse(text) : text;
                if (cachedProbe && cachedProbe._cached && toolName !== 'get_cached') {
                    callTool('get_cached', { cache_id: cachedProbe._cached }, toolName);
                    return;
                }
            } catch (e) { /* not cached summary */ }
        }

        // Route to Memory tab if it's a memory tool
        if (MEMORY_TOOLS.indexOf(toolName) >= 0) {
            var memList = document.getElementById('mem-list');
            if (!memList) return;

            // Refresh catalog after successful memory mutations.
            if (!msg.error && ['bag_put', 'bag_induct', 'bag_forget', 'pocket', 'load_bag'].indexOf(toolName) >= 0) {
                callTool('bag_catalog', {});
            }

            // bag_get / get_cached → inline drill content
            if ((toolName === 'bag_get' || toolName === 'get_cached') && !msg.error && _openDrillKey) {
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
                            drillDiv.innerHTML = '<div style="padding:8px 12px;color:#e11d48;">' + _esc(got.error) + '</div>';
                            return;
                        }
                        var val = got.value;
                        // get_cached returns the raw bag_get JSON string, parse it
                        if (typeof val === 'undefined' && typeof got.key !== 'undefined') {
                            val = got;
                        } else if (typeof val === 'undefined') {
                            // get_cached returns the original bag_get result as a string
                            try { var inner = typeof got === 'string' ? JSON.parse(got) : got; val = inner.value; } catch (e2) { val = text; }
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
                        var publishBtnId = 'publish-btn-' + safeKey;
                        var commitBtnId = 'commit-btn-' + safeKey;
                        var gitMetaId = 'bag-git-meta-' + safeKey;
                        var gitDiffId = 'bag-git-diff-' + safeKey;
                        var gitDisabled = (_gitProbed && !_gitAvailable);
                        var commitBtnStyle = gitDisabled
                            ? 'font-size:9px;padding:2px 8px;cursor:not-allowed;background:var(--surface2);color:var(--text-dim);opacity:0.45;border:1px solid var(--border);border-radius:3px;'
                            : 'font-size:9px;padding:2px 8px;cursor:pointer;background:var(--surface2);color:var(--accent);border:1px solid var(--border);border-radius:3px;';
                        drillDiv.innerHTML =
                            '<div style="padding:4px 12px;font-size:10px;color:var(--text-dim);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;">' +
                            '<span>' + lineCount + ' lines · ' + _fmtSize(contentStr.length) + ' · v' + verNum + '</span>' +
                            '<div style="display:flex;align-items:center;gap:6px;">' +
                            '<button id="' + publishBtnId + '" data-bag-key="' + _esc(_openDrillKey) + '" onclick="publishBagToMarketplace(this)" style="font-size:9px;padding:2px 8px;cursor:pointer;background:var(--surface2);color:#60a5fa;border:1px solid var(--border);border-radius:3px;">Publish to Marketplace</button>' +
                            '<button id="' + commitBtnId + '" data-bag-key="' + _esc(_openDrillKey) + '" onclick="commitBagVersion(this)"' + (gitDisabled ? ' disabled title="Git not available"' : '') + ' style="' + commitBtnStyle + '">Commit Version</button>' +
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

        // list_slots button → re-render the slots grid
        if (toolName === 'list_slots') {
            renderSlots(msg.data);
            return;
        }

        // Route to Council tab if it's a council tool
        if (COUNCIL_TOOLS.indexOf(toolName) >= 0) {
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
        setMemoryExportStatus('Choose export format from the VS Code picker…', false);
        vscode.postMessage({ command: 'exportMemory' });
    }
    window.startMemoryExport = startMemoryExport;

    // ── MODALS ──
    function openPlugModal() {
        var el = document.getElementById('plug-modal');
        if (el) el.classList.add('active');
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

    function doPlug() {
        var modelId = document.getElementById('plug-model-id').value;
        var slotName = document.getElementById('plug-slot-name').value;
        if (!modelId) return;
        // Clear any existing plugging entry for same modelId to prevent duplicates
        // (addActivityEntry will also create one when the sentinel event arrives)
        _clearPluggingEntry(modelId);
        var slotKey = slotName || 'plug_' + Date.now();
        _pluggingSlots[slotKey] = { modelId: modelId, startTime: Date.now(), slotName: slotName || null };
        _updatePluggingUI();
        callTool('plug_model', { model_id: modelId, slot_name: slotName || undefined });
        closeModals();
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

            callTool('workflow_execute', {
                workflow_id: _wfSelectedId,
                input_data: inputStr
            });
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

                callTool('bag_induct', { key: sourceArtifactKey, content: sourceArtifactPayload, item_type: 'artifact' });
                callTool('workflow_create', { definition: workflowDefPayload });
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
                callTool('workflow_create', { definition: normalizedPayload });
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

    // ── INIT ──
    buildToolsRegistry();
    renderSlots([]);
    renderWorkflowList();
    renderWorkflowGraph(null, null);
    renderWorkflowNodeStates(null, null);
    _wfRenderDrillDetail();
    _wfSetBadge('idle', 'IDLE');

    // Tell extension we're ready
    vscode.postMessage({ command: 'ready' });

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
    // Auto-fetch community content
    setTimeout(function () {
        vscode.postMessage({ command: 'nostrFetchWorkflows' });
        vscode.postMessage({ command: 'nostrFetchChat' });
        vscode.postMessage({ command: 'nostrFetchDMs' });
        vscode.postMessage({ command: 'nostrGetOnlineUsers' });
    }, 2000);
    // Periodic presence polling
    setInterval(function () {
        vscode.postMessage({ command: 'nostrGetOnlineUsers' });
    }, 60000);
})();
