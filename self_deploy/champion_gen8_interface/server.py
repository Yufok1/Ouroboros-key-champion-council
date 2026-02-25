#!/usr/bin/env python3
"""
Model Interface Server - Bridges game engine to champion_gen8

Auto-generated. Do not edit directly.
Run this server, then connect from any game engine (Panda3D, Pygame, Godot, etc.).

Usage:
    python server.py              # Start on default port 8766
    python server.py --port 9000  # Custom port
"""

import sys
import json
import argparse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Add model directory to path
MODEL_PATH = r"F:\End-Game\vscode-extension\Champion_Council\capsule\champion_gen8.py"
sys.path.insert(0, str(Path(MODEL_PATH).parent))

# Import the model
import importlib.util
spec = importlib.util.spec_from_file_location("model", MODEL_PATH)
model_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model_module)

# Create agent instance
AGENT = model_module.CapsuleAgent(observe=False)

# ═══════════════════════════════════════════════════════════════
# CASCADE-LATTICE INTEGRATION
# Cryptographic receipts for every AI decision
# ═══════════════════════════════════════════════════════════════
try:
    from cascade import sdk as cascade_sdk
    cascade_sdk.init()
    CASCADE_ENABLED = True
    print("[CASCADE] Provenance layer active - all decisions will be recorded")
except ImportError:
    CASCADE_ENABLED = False
    print("[CASCADE] Not installed - pip install cascade-lattice for provenance")

# ═══════════════════════════════════════════════════════════════
# PRIVACY SAFEGUARDS - NO DOXXING
# ═══════════════════════════════════════════════════════════════
# What we record:  AI decisions, agent lineage, model behavior
# What we NEVER record:
#   - Usernames, emails, real names
#   - IP addresses, device IDs
#   - Session tokens, auth data
#   - File paths containing usernames
#   - Any PII whatsoever
# ═══════════════════════════════════════════════════════════════

def _sanitize_path(path_str):
    """Strip any path info that could contain usernames."""
    from pathlib import Path
    return Path(path_str).stem  # Just the filename, no directories

def _cascade_observe_event(event_type, data):
    """Record event to cascade-lattice (IPFS + Merkle tree).
    
    PRIVACY: Only AI decision data is recorded. No user identity.
    """
    if not CASCADE_ENABLED:
        return None
    try:
        # Build safe observation - NO PII
        safe_data = {
            "type": event_type,
            "agent": _sanitize_path(MODEL_PATH),  # Just model name, no path
            "generation": AGENT.generation,
            # Timestamp rounded to hour for temporal anonymity
            "timestamp_hour": int(__import__("time").time() // 3600) * 3600,
        }
        
        # Only copy known-safe fields from data
        SAFE_FIELDS = {"step", "candidate_count", "accepted_idx", "top_candidate",
                      "combo", "original_choice", "override_choice", 
                      "original_candidate", "override_candidate", "total_overrides",
                      "inputs", "output_keys", "inference_count"}
        for k, v in data.items():
            if k in SAFE_FIELDS:
                safe_data[k] = v
        
        # CASCADE SDK: observe(model_id, input_data, output_data)
        model_id = _sanitize_path(MODEL_PATH)
        return cascade_sdk.observe(model_id, {"event": event_type}, safe_data)
    except Exception as e:
        print(f"[CASCADE] Observation failed: {e}")
        return None

# Causation Hold state (arcade-style inference interception)
HOLD_STATE = {
    "enabled": False,
    "paused": False,
    "step_index": 0,
    "history": [],       # List of step dicts
    "combo": 0,          # Current combo streak
    "total_overrides": 0,
    "high_score": 0,
    "playback_speed": 1.0,
}

def capture_hold_step(candidates, accepted_idx, attention=None):
    """Capture a step for causation hold review."""
    step = {
        "step": len(HOLD_STATE["history"]),
        "candidates": candidates,  # List of {word, prob} dicts
        "accepted": accepted_idx,
        "attention": attention,
        "timestamp": __import__("time").time(),
    }
    HOLD_STATE["history"].append(step)
    if len(HOLD_STATE["history"]) > 1000:
        HOLD_STATE["history"] = HOLD_STATE["history"][-500:]  # Keep recent
    
    # Record to cascade-lattice
    _cascade_observe_event("causation_step", {
        "step": step["step"],
        "candidate_count": len(candidates),
        "accepted_idx": accepted_idx,
        "top_candidate": candidates[0] if candidates else None,
    })
    
    return step


def _inference_to_candidates(inputs, result):
    """
    Convert inference inputs/outputs to human-readable candidates.
    This is where the Glass Box reveals what the AI is "thinking".
    """
    import numpy as np
    
    candidates = []
    
    # Handle dict results (typical from forward())
    if isinstance(result, dict):
        # If there's an 'action' field, show action possibilities
        if 'action' in result:
            action_val = result['action']
            if isinstance(action_val, (int, float)):
                # Create candidates around the action value
                base = float(action_val)
                candidates = [
                    {"word": f"action={base:.3f}", "probability": 0.6},
                    {"word": f"action={base+0.1:.3f}", "probability": 0.2},
                    {"word": f"action={base-0.1:.3f}", "probability": 0.15},
                    {"word": f"action={base+0.2:.3f}", "probability": 0.05},
                ]
        # If there's an 'embedding' field, show top dimensions
        elif 'embedding' in result:
            emb = np.array(result['embedding']).flatten()
            top_idx = np.argsort(np.abs(emb))[-5:][::-1]
            total = np.sum(np.abs(emb[top_idx]))
            for i, idx in enumerate(top_idx):
                prob = abs(emb[idx]) / total if total > 0 else 0.2
                candidates.append({
                    "word": f"dim[{idx}]={emb[idx]:.3f}",
                    "probability": float(prob),
                })
        else:
            # Generic: show all result keys as candidates
            keys = list(result.keys())
            for i, k in enumerate(keys[:5]):
                val = result[k]
                if isinstance(val, (int, float)):
                    candidates.append({
                        "word": f"{k}={val:.3f}" if isinstance(val, float) else f"{k}={val}",
                        "probability": 1.0 / (i + 1),
                    })
    
    # Handle raw numeric results
    elif isinstance(result, (int, float)):
        base = float(result)
        candidates = [
            {"word": f"output={base:.3f}", "probability": 0.7},
            {"word": f"output={base*1.1:.3f}", "probability": 0.2},
            {"word": f"output={base*0.9:.3f}", "probability": 0.1},
        ]
    
    # Fallback: show input as context
    if not candidates:
        input_str = str(inputs)[:30]
        candidates = [
            {"word": f"[{input_str}]→processed", "probability": 1.0},
        ]
    
    # Normalize probabilities
    total_prob = sum(c["probability"] for c in candidates)
    if total_prob > 0:
        for c in candidates:
            c["probability"] = c["probability"] / total_prob
    
    return candidates

class ModelHandler(BaseHTTPRequestHandler):
    """HTTP handler for model actions."""
    
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == "/manifest":
            manifest = json.loads(Path("manifest.json").read_text(encoding="utf-8"))
            self._send_json(manifest)
        
        elif path == "/capabilities":
            self._send_json(model_module.get_action_manifest())
        
        elif path == "/info":
            self._send_json({
                "generation": AGENT.generation,
                "fitness": AGENT.fitness,
                "traits": AGENT.traits,
                "inference_count": AGENT._inference_count,
            })
        
        elif path == "/readme":
            self._send_json({"readme": AGENT.get_readme()})
        
        elif path == "/provenance":
            self._send_json(AGENT.get_full_provenance())
        
        elif path == "/hold":
            # GET hold state (for game client polling)
            step = None
            if 0 <= HOLD_STATE["step_index"] < len(HOLD_STATE["history"]):
                step = HOLD_STATE["history"][HOLD_STATE["step_index"]]
            self._send_json({
                "enabled": HOLD_STATE["enabled"],
                "paused": HOLD_STATE["paused"],
                "step_index": HOLD_STATE["step_index"],
                "total_steps": len(HOLD_STATE["history"]),
                "current_step": step,
                "combo": HOLD_STATE["combo"],
                "total_overrides": HOLD_STATE["total_overrides"],
                "high_score": HOLD_STATE["high_score"],
                "speed": HOLD_STATE["playback_speed"],
            })
        
        else:
            self._send_json({"error": "Unknown endpoint"}, 404)
    
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length else "{}"
        params = json.loads(body) if body else {}
        
        try:
            if path == "/forward":
                inputs = params.get("inputs", {})
                result = AGENT.forward(inputs)
                
                # AUTO-CAPTURE for Causation Hold
                # Convert inference result to reviewable candidates
                if HOLD_STATE["enabled"]:
                    candidates = _inference_to_candidates(inputs, result)
                    accepted_idx = 0  # Model's top choice
                    capture_hold_step(candidates, accepted_idx)
                
                # CASCADE: Record every inference
                _cascade_observe_event("inference", {
                    "inputs": list(inputs.keys()),
                    "output_keys": list(result.keys()) if isinstance(result, dict) else ["raw"],
                    "inference_count": AGENT._inference_count,
                })
                
                self._send_json({"result": _serialize(result)})
            
            elif path == "/export_pt":
                AGENT.export_pt(params.get("path", "model.pt"))
                self._send_json({"status": "ok"})
            
            elif path == "/export_onnx":
                AGENT.export_onnx(params.get("path", "model.onnx"))
                self._send_json({"status": "ok"})
            
            elif path == "/clone":
                new_path = AGENT.export_capsule(params.get("path"))
                self._send_json({"path": new_path})
            
            elif path == "/bridge":
                bridge = AGENT.get_bridge()
                result = bridge.bridge(params["old_form"], params["new_form"])
                self._send_json({"result": result})
            
            # ═══════════════════════════════════════════════════════
            # CAUSATION HOLD - Arcade-style inference interception
            # ═══════════════════════════════════════════════════════
            
            elif path == "/hold/toggle":
                HOLD_STATE["enabled"] = not HOLD_STATE["enabled"]
                self._send_json({"enabled": HOLD_STATE["enabled"]})
            
            elif path == "/hold/pause":
                HOLD_STATE["paused"] = True
                self._send_json({"paused": True, "step": HOLD_STATE["step_index"]})
            
            elif path == "/hold/resume":
                HOLD_STATE["paused"] = False
                self._send_json({"paused": False})
            
            elif path == "/hold/accept":
                # Accept current candidate (SPACE key)
                idx = HOLD_STATE["step_index"]
                if 0 <= idx < len(HOLD_STATE["history"]):
                    step = HOLD_STATE["history"][idx]
                    HOLD_STATE["combo"] += 1
                    HOLD_STATE["high_score"] = max(HOLD_STATE["high_score"], HOLD_STATE["combo"])
                    HOLD_STATE["step_index"] += 1
                    
                    # CASCADE: Record acceptance to provenance chain
                    _cascade_observe_event("causation_accept", {
                        "step": idx,
                        "accepted_idx": step["accepted"],
                        "combo": HOLD_STATE["combo"],
                    })
                    
                    self._send_json({
                        "accepted": step["accepted"],
                        "combo": HOLD_STATE["combo"],
                        "step": HOLD_STATE["step_index"],
                    })
                else:
                    self._send_json({"error": "No step to accept"}, 400)
            
            elif path == "/hold/override":
                # Override with different candidate (1-9 keys)
                idx = params.get("index", 0)
                step_idx = HOLD_STATE["step_index"]
                if 0 <= step_idx < len(HOLD_STATE["history"]):
                    step = HOLD_STATE["history"][step_idx]
                    if 0 <= idx < len(step["candidates"]):
                        # Record the override
                        original_choice = step["accepted"]
                        step["overridden"] = True
                        step["override_idx"] = idx
                        HOLD_STATE["total_overrides"] += 1
                        HOLD_STATE["combo"] = 0  # Break combo on override
                        HOLD_STATE["step_index"] += 1
                        
                        # CASCADE: Record override - THIS IS THE GOLD
                        # Human intervention in AI decision, cryptographically recorded
                        _cascade_observe_event("causation_override", {
                            "step": step_idx,
                            "original_choice": original_choice,
                            "override_choice": idx,
                            "original_candidate": step["candidates"][original_choice] if original_choice < len(step["candidates"]) else None,
                            "override_candidate": step["candidates"][idx],
                            "total_overrides": HOLD_STATE["total_overrides"],
                        })
                        
                        self._send_json({
                            "overridden": idx,
                            "candidate": step["candidates"][idx],
                            "total_overrides": HOLD_STATE["total_overrides"],
                            "step": HOLD_STATE["step_index"],
                        })
                    else:
                        self._send_json({"error": f"Invalid candidate index {idx}"}, 400)
                else:
                    self._send_json({"error": "No step to override"}, 400)
            
            elif path == "/hold/navigate":
                # Navigate through history (arrow keys)
                direction = params.get("direction", 0)  # -1=back, +1=forward
                HOLD_STATE["step_index"] = max(0, min(
                    len(HOLD_STATE["history"]) - 1,
                    HOLD_STATE["step_index"] + direction
                ))
                step = None
                if 0 <= HOLD_STATE["step_index"] < len(HOLD_STATE["history"]):
                    step = HOLD_STATE["history"][HOLD_STATE["step_index"]]
                self._send_json({
                    "step_index": HOLD_STATE["step_index"],
                    "step": step,
                    "total": len(HOLD_STATE["history"]),
                })
            
            elif path == "/hold/speed":
                # Adjust playback speed (+/- keys)
                delta = params.get("delta", 0)  # e.g., +0.25 or -0.25
                HOLD_STATE["playback_speed"] = max(0.25, min(4.0, 
                    HOLD_STATE["playback_speed"] + delta))
                self._send_json({"speed": HOLD_STATE["playback_speed"]})
            
            elif path == "/hold/state":
                # Get full hold state
                step = None
                if 0 <= HOLD_STATE["step_index"] < len(HOLD_STATE["history"]):
                    step = HOLD_STATE["history"][HOLD_STATE["step_index"]]
                self._send_json({
                    "enabled": HOLD_STATE["enabled"],
                    "paused": HOLD_STATE["paused"],
                    "step_index": HOLD_STATE["step_index"],
                    "total_steps": len(HOLD_STATE["history"]),
                    "current_step": step,
                    "combo": HOLD_STATE["combo"],
                    "total_overrides": HOLD_STATE["total_overrides"],
                    "high_score": HOLD_STATE["high_score"],
                    "playback_speed": HOLD_STATE["playback_speed"],
                })
            
            elif path == "/hold/capture":
                # Capture a new step (called during inference)
                candidates = params.get("candidates", [])
                accepted_idx = params.get("accepted", 0)
                attention = params.get("attention")
                step = capture_hold_step(candidates, accepted_idx, attention)
                self._send_json({"step": step, "total": len(HOLD_STATE["history"])})
            
            else:
                self._send_json({"error": "Unknown action"}, 404)
        
        except Exception as e:
            self._send_json({"error": str(e)}, 500)
    
    def log_message(self, format, *args):
        print(f"[ModelServer] {args[0]}")

def _serialize(obj):
    """Make object JSON-serializable."""
    import numpy as np
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    return obj

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    
    print(f"Model Interface Server for champion_gen8")
    print(f"   Serving on http://{args.host}:{args.port}")
    print(f"   Model: {MODEL_PATH}")
    print()
    print("Endpoints:")
    print("   GET  /manifest       - Model manifest")
    print("   GET  /capabilities   - Available actions")  
    print("   GET  /info           - Current state")
    print("   GET  /readme         - Documentation")
    print("   GET  /provenance     - Full provenance chain")
    print("   GET  /hold           - Causation hold state (poll)")
    print()
    print("   POST /forward        - Run inference")
    print("   POST /export_pt      - Export to PyTorch")
    print("   POST /export_onnx    - Export to ONNX")
    print("   POST /clone          - Clone agent")
    print("   POST /bridge         - Data bridging")
    print()
    print("   POST /hold/toggle    - Enable/disable causation hold")
    print("   POST /hold/pause     - Pause at current step")
    print("   POST /hold/resume    - Resume playback")
    print("   POST /hold/accept    - Accept current candidate (SPACE)")
    print("   POST /hold/override  - Override with index (1-9)")
    print("   POST /hold/navigate  - Navigate history (arrows)")
    print("   POST /hold/speed     - Adjust playback speed (+/-)")
    print("   POST /hold/capture   - Capture inference step")
    print()
    
    server = HTTPServer((args.host, args.port), ModelHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
