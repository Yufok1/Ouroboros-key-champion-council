# Resume Prompt - Agent Compiler Modalities

Read these files in order before taking action:

1. `F:\End-Game\ouroboros-key\data\claudeoctor.txt`
2. `F:\End-Game\ouroboros-key\data\AGENT_COMPILER_INTEGRATION_SURFACES.md`
3. `F:\End-Game\champion_councl\docs\AGENT_COMPILER_MODALITY_ACCLIMATION_REPORT_2026-03-14.md`

Use the report as the current authoritative handoff for the modality work.

Operating requirements:

- Do not edit `capsule/champion_gen8.py` directly.
- Do not build a second AGENT/facility UI.
- Do not trample the existing AGENT facility rail, voice facility staging, vision staging, Environment shell contracts, or debug system.
- Treat the current facility behavior as protected and patch the runtime adapter layer under it first.
- Source code is primary.
- Live MCP plus `feed` is the operational proof layer.
- Validate every meaningful change with `python -m py_compile agent_compiler.py`, regenerated runtime behavior, `slot_info`, `list_slots`, and `feed`.

What the previous audit already established:

- Local Whisper ASR is being misrouted away from `_load_as_asr(...)` because config refinement collapses Whisper into `SEQ2SEQ`.
- The emitted ASR wrapper is not safe yet on this CPU host unless dtype/device alignment and generation length are corrected.
- `RemoteProviderProxy` is still chat/embedding oriented and does not yet provide real `transcribe()` or `synthesize()` methods.
- Runtime type detection and slot reporting still under-report ASR/TTS/VLM.
- The current VLM provider binding `Qwen/Qwen2.5-VL-7B-Instruct` on `hf-router/together` is rejected upstream as unsupported.
- The current HF router loopback on this stack does not expose working remote speech endpoints.
- The existing AGENT voice facility is intentionally still transitional and must not be bulldozed during backend fixes.

Immediate next task:

- turn the implementation order from the acclimation report into a line-by-line edit plan for `agent_compiler.py`, starting with the lowest-regression-risk local ASR routing and wrapper fixes

